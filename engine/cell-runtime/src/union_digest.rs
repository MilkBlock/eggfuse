//! Constructor equality joins over the graph's existing row fields, reverse
//! incidences and interning buckets. ChangeBatch is the only wake-up queue
//! consumed by shared Entry; source Run barriers still control observation.
use super::*;
use std::rc::Rc;

#[derive(Default, Debug, Serialize)]
pub(super) struct DigestStats {
    pub equality_events: u64,
    pub shared_incidence_visits: u64,
    pub changed_argument_positions: u64,
    pub key_packets_updated: u64,
    pub result_only_updates: u64,
    pub shared_row_copies: u64,
    pub full_key_checks: u64,
    pub congruence_matches: u64,
    pub output_union_requests: u64,
    pub publication_visits: u64,
    pub duplicate_rows_retired: u64,
    pub peak_packets: usize,
    pub relation_key_matches: u64,
    pub unit_notifications: u64,
    pub unit_rows_rekeyed: u64,
    pub unit_key_matches: u64,
    pub unit_rows_retired: u64,
    pub unit_compact_rekeys: u64,
    pub unit_compact_retired: u64,
}

pub(super) struct Matcher {
    // Typed schema positions, reusable across Runs; no learned IDs or rows.
    eq_columns: Vec<Box<[usize]>>,
    duplicates: BTreeSet<FactRef>,
    unit_pending: BTreeSet<usize>,
    stats: DigestStats,
    live_rows: usize,
    hash_bits: u32,
    hash_mask: u64,
}

impl Matcher {
    pub fn validate(p: &Program) -> Result<()> {
        for t in &p.tables {
            let presence = t.schema.last().is_some_and(|s| s["kind"] == "Unit")
                && (t.merge.is_null() || t.merge == json!({"var": "old"}));
            if !(t.constructor && t.virtual_fact) && !presence {
                return Err(format!(
                    "union digest requires immutable constructor or Unit-presence tables; unsupported table {}",
                    t.name
                ));
            }
            if t.schema.iter().any(|s| {
                !matches!(
                    s["kind"].as_str(),
                    Some("eq" | "i64" | "f64" | "String" | "bool" | "Unit")
                )
            }) {
                return Err(format!(
                    "union digest requires scalar fields; unsupported table {}",
                    t.name
                ));
            }
        }
        if p.templates
            .iter()
            .any(|t| t.ops.iter().any(|op| matches!(op, Op::Hide(..))))
            || p.initial.iter().any(|r| r["subsumed"] == true)
        {
            return Err("union digest does not support deletion or subsumption".into());
        }
        Ok(())
    }

    pub fn new(p: &Program, hash_bits: u32) -> Result<Self> {
        Self::validate(p)?;
        if hash_bits > 64 {
            return Err("union digest hash bits must be in 0..=64".into());
        }
        Ok(Self {
            eq_columns: p
                .tables
                .iter()
                .map(|t| {
                    t.schema
                        .iter()
                        .enumerate()
                        .filter_map(|(i, s)| (s["kind"] == "eq").then_some(i))
                        .collect()
                })
                .collect(),
            duplicates: BTreeSet::new(),
            unit_pending: BTreeSet::new(),
            stats: DigestStats::default(),
            live_rows: 0,
            hash_bits,
            hash_mask: if hash_bits == 64 {
                u64::MAX
            } else {
                (1u64 << hash_bits) - 1
            },
        })
    }

    pub fn removed(&mut self, f: FactRef) {
        self.live_rows -= 1;
        self.duplicates.remove(&f);
    }

    pub fn report(&self) -> J {
        json!({"enabled": true, "stats": self.stats,
            "live_packets": self.live_rows, "owned_key_packets": 0,
            "owned_argument_postings": 0, "owned_key_buckets": 0,
            "hash_bits": self.hash_bits,
            "storage": "Graph RowFields, reverse incidences and constructor interning",
            "delivery": "existing ChangeBatch to shared Entry at source Run boundaries",
            "pending_unit_rows": self.unit_pending.len(),
            "scope": "constructor congruence and scalar Unit presence; ordered/value-producing merges excluded"})
    }
}

impl Graph {
    #[inline]
    pub(super) fn constructor_hash(&self, table: usize, key: &[Value]) -> u64 {
        let h = hashkey(table, key);
        self.union_digest.as_ref().map_or(h, |m| h & m.hash_mask)
    }

    pub(super) fn register_digest(&mut self, f: FactRef) -> Result<()> {
        let matcher = self.union_digest.as_mut().unwrap();
        matcher.live_rows += 1;
        matcher.stats.peak_packets = matcher.stats.peak_packets.max(matcher.live_rows);
        // Activation already installed the packet in the shared constructor
        // bucket. Normally singleton, but imports can contain duplicate keys.
        self.join_digest(f)
    }

    /// Exact correlated join against the SAME buckets used by constructor
    /// lookup. A hash collision only adds candidate work, never equality.
    fn join_digest(&mut self, f: FactRef) -> Result<()> {
        let state = &self.cells[&f.cell].facts[&f.op];
        let (table, fields) = state
            .decoded
            .as_ref()
            .ok_or("missing shared digest fields")?;
        let key = &fields[..fields.len() - 1];
        let mut found = None;
        let matcher = self.union_digest.as_mut().unwrap();
        for &other in self.intern.get(&state.hash).into_iter().flatten() {
            if other == f {
                continue;
            }
            matcher.stats.full_key_checks += 1;
            let other_state = &self.cells[&other.cell].facts[&other.op];
            let (other_table, other_fields) = other_state
                .decoded
                .as_ref()
                .ok_or("missing shared candidate fields")?;
            if table == other_table && key == &other_fields[..other_fields.len() - 1] {
                found = Some((other, other_fields.last().unwrap().clone()));
                break;
            }
        }
        if let Some((other, other_result)) = found {
            let result = fields.last().unwrap().clone();
            matcher.duplicates.insert(f);
            matcher.duplicates.insert(other);
            if self.program.tables[*table].constructor {
                matcher.stats.congruence_matches += 1;
                matcher.stats.output_union_requests += 1;
                self.enqueue_union(result, other_result)?;
            } else {
                if result != Value::Int(0) || other_result != Value::Int(0) {
                    return Err("Unit presence has a non-Unit value".into());
                }
                matcher.stats.relation_key_matches += 1;
            }
        }
        Ok(())
    }

    /// Consume one equality delta through the reverse relation already used by
    /// matching. Typed columns distinguish key changes from result-only wakes.
    /// Update ALL correlated fields before joining any changed packet.
    pub(super) fn match_equality_digest(
        &mut self,
        from: u64,
        to: u64,
        affected: &UseSet,
    ) -> Result<()> {
        let matcher = self.union_digest.as_mut().unwrap();
        matcher.stats.equality_events += 1;
        let mut rekeyed = Vec::new();
        for d in affected.iter() {
            matcher.stats.shared_incidence_visits += 1;
            let f = match *d {
                Dependency::Fact(f) => f,
                Dependency::Function(i) => {
                    // Unit cannot cause another equality. Coalesce notifications
                    // across the constructor closure before joining these keys.
                    self.functions[i].decoded = None;
                    matcher.unit_pending.insert(i);
                    matcher.stats.unit_notifications += 1;
                    continue;
                }
            };
            let Some(state) = self
                .cells
                .get_mut(&f.cell)
                .and_then(|c| c.facts.get_mut(&f.op))
            else {
                continue;
            };
            let (table, fields) = state
                .decoded
                .as_mut()
                .ok_or("missing shared digest fields")?;
            let result_column = fields.len() - 1;
            matcher.stats.shared_row_copies += u64::from(Rc::strong_count(fields) > 1);
            // Entry packets may still own the preceding Run's fields. COW keeps
            // those snapshots immutable while new packets use the updated row.
            let values = Rc::make_mut(fields);
            let mut changed_key = false;
            let mut changed = false;
            for &column in &matcher.eq_columns[*table] {
                if values[column] == Value::Eq(from) {
                    values[column] = Value::Eq(to);
                    changed = true;
                    if column != result_column {
                        changed_key = true;
                        matcher.stats.changed_argument_positions += 1;
                    }
                }
            }
            debug_assert!(changed, "stale reverse incidence in digest matcher");
            if !changed {
                continue;
            }
            if changed_key {
                matcher.stats.key_packets_updated += 1;
                let old = state.hash;
                if let Some(bucket) = self.intern.get_mut(&old) {
                    bucket.remove(&f);
                    if bucket.is_empty() {
                        self.intern.remove(&old);
                    }
                }
                state.hash = hashkey(*table, &values[..result_column]) & matcher.hash_mask;
                self.stats.repair_key_hash_changes += u64::from(state.hash != old);
                rekeyed.push(f);
            } else {
                matcher.stats.result_only_updates += 1;
            }
            state.epoch = self.epoch;
            self.query_versions[*table] += 1;
            self.changes.touch(*table, *d);
            matcher.stats.publication_visits += 1;
        }
        // Deterministic proposal ordering; incidence storage itself is unordered.
        rekeyed.sort_unstable();
        for f in rekeyed {
            self.join_digest(f)?;
            let h = self.cells[&f.cell].facts[&f.op].hash;
            self.intern.entry(h).or_default().insert(f);
        }
        Ok(())
    }

    /// Equality witnesses can be retired immediately after the event's reverse
    /// incidences have migrated. Their queued result unions remain obligations;
    /// removing a duplicate does not count as committing that result union.
    pub(super) fn retire_digest_duplicates(&mut self) -> Result<()> {
        let duplicates = std::mem::take(&mut self.union_digest.as_mut().unwrap().duplicates);
        for f in duplicates {
            let Some(state) = self.cells.get(&f.cell).and_then(|c| c.facts.get(&f.op)) else {
                continue;
            };
            let (table, fields) = state.decoded.as_ref().ok_or("missing duplicate fields")?;
            let table = *table;
            let key = &fields[..fields.len() - 1];
            let keep = self.intern[&state.hash]
                .iter()
                .copied()
                .find(|other| {
                    let (t, vs) = self.cells[&other.cell].facts[&other.op]
                        .decoded
                        .as_ref()
                        .unwrap();
                    *t == table && key == &vs[..vs.len() - 1]
                })
                .ok_or("missing digest keeper")?;
            if keep == f {
                continue;
            }
            self.union_digest
                .as_mut()
                .unwrap()
                .stats
                .duplicate_rows_retired += 1;
            let target = self
                .cells
                .get_mut(&keep.cell)
                .unwrap()
                .facts
                .get_mut(&keep.op)
                .unwrap();
            target.epoch = self.epoch;
            self.query_versions[table] += 1;
            self.changes.touch(table, Dependency::Fact(keep));
            if self.receipt_tracking {
                self.receipt_forwards
                    .insert(Dependency::Fact(f), Dependency::Fact(keep));
            }
            self.retire(f)?;
        }
        Ok(())
    }

    pub(super) fn propagate_union_digests(&mut self) -> Result<()> {
        // Imported equal keys may have emitted proposals before any event.
        self.retire_digest_duplicates()?;
        while !self.pending_unions.is_empty() {
            let pairs = std::mem::take(&mut self.pending_unions);
            for (a, b) in pairs {
                self.union(a, b)?;
            }
        }
        self.publish_unit_digests()
    }

    /// Unit presence has no result equality or effectful merge. Its canonical
    /// key join can therefore wait for the equality stream's fixed point. Keep
    /// each tuple correlated, and detach every old key before probing new keys.
    fn publish_unit_digests(&mut self) -> Result<()> {
        let pending = std::mem::take(&mut self.union_digest.as_mut().unwrap().unit_pending);
        let mut rows = Vec::with_capacity(pending.len());
        for i in pending {
            let Some(row) = self.function(i) else {
                continue;
            };
            if row.values.last() != Some(&Value::Int(0)) {
                return Err("Unit presence has a non-Unit value".into());
            }
            let alias = self.units.detach_key(i);
            if alias.is_none() {
                let old = &self.functions[i].key;
                if self.function_keys[row.table].get(old) == Some(&i) {
                    self.function_keys[row.table].remove(old);
                }
            }
            rows.push((i, row, alias));
        }
        for (i, row, alias) in rows {
            let table = row.table;
            let key = &row.values[..row.values.len() - 1];
            self.union_digest.as_mut().unwrap().stats.unit_rows_rekeyed += 1;
            if let Some(j) = self.function_index(table, key) {
                if self.functions[j].value != Value::Int(0) {
                    return Err("Unit presence keeper has a non-Unit value".into());
                }
                let stats = &mut self.union_digest.as_mut().unwrap().stats;
                stats.unit_key_matches += 1;
                stats.unit_rows_retired += 1;
                stats.unit_compact_retired += u64::from(alias.is_some());
                self.units.stats.lost += u64::from(alias.is_some());
                // Both values are the unique Unit value and the typed merge is
                // exactly old/null. No merge callback or result union is needed.
                self.functions[j].epoch = self.epoch;
                #[cfg(feature = "receipt-slots")]
                if self.functions[i].port_slot != 0 {
                    self.retired_port_slots.insert(
                        Dependency::Function(i),
                        std::mem::take(&mut self.functions[i].port_slot),
                    );
                }
                self.functions[i].live = false;
                self.changes.retire(table, Dependency::Function(i));
                if self.receipt_tracking {
                    self.receipt_forwards
                        .insert(Dependency::Function(i), Dependency::Function(j));
                }
                self.function_origin(i, None);
                self.members[table].remove(&(i as u64));
                self.subscribe(table, Dependency::Function(i), &[]);
                self.query_versions[table] += 1;
                self.changes.touch(table, Dependency::Function(j));
                continue;
            }
            let f = &mut self.functions[i];
            f.epoch = self.epoch;
            f.decoded = Some(row.values.clone());
            if let Some(alias) = alias {
                self.units.restore_key(i, alias, row.values);
                self.union_digest
                    .as_mut()
                    .unwrap()
                    .stats
                    .unit_compact_rekeys += 1;
            } else {
                f.key = key.to_vec();
                #[cfg(feature = "sparse-cells")]
                self.function_keys[table].insert(key, i);
                #[cfg(not(feature = "sparse-cells"))]
                self.function_keys[table].insert(key.to_vec(), i);
            }
            // Union already migrated every reverse incidence; no key/value
            // changes beyond canonicalization require resubscribing this row.
            self.query_versions[table] += 1;
            self.changes.touch(table, Dependency::Function(i));
        }
        Ok(())
    }
}
