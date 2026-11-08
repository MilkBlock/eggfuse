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
}

pub(super) struct Matcher {
    // Typed schema positions, reusable across Runs; no learned IDs or rows.
    eq_columns: Vec<Box<[usize]>>,
    duplicates: BTreeSet<FactRef>,
    stats: DigestStats,
    live_rows: usize,
    hash_bits: u32,
    hash_mask: u64,
}

impl Matcher {
    pub fn validate(p: &Program) -> Result<()> {
        if !p.marker_tables.is_empty() {
            return Err("union digest does not yet support marker tables".into());
        }
        for t in &p.tables {
            if !t.constructor || !t.virtual_fact {
                return Err(format!(
                    "union digest requires immutable constructor tables; unsupported table {}",
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
            "scope": "constructor-only relational congruence with shared storage and publication"})
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
            matcher.stats.congruence_matches += 1;
            matcher.stats.output_union_requests += 1;
            matcher.duplicates.insert(f);
            matcher.duplicates.insert(other);
            self.enqueue_union(result, other_result)?;
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
            let Dependency::Fact(f) = *d else {
                return Err("function entered constructor digest".into());
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
        Ok(())
    }
}
