// Observations are per execution; all state transitions still use the original ordered worklist.
#[derive(Default, serde::Serialize)]
struct RepairReuse {
    mode: u8,
    audit: bool,
    #[serde(skip)]
    eq_masks: Vec<Option<u64>>,
    #[serde(skip)]
    pending: HashMap<FactRef, (usize, RowFields)>,
    pending_saved: u64,
    pending_consumed: u64,
    pending_cap: u64,
    peak_pending: usize,
    unions: u64,
    displaced_edges: u64,
    survivor_edges: u64,
    merge_insertions: u64,
    reverse_audits: u64,
    payload_attempts: u64,
    fact_payloads: u64,
    function_payloads: u64,
    missing_payloads: u64,
    unsupported_schemas: u64,
    scalar_positions: u64,
    substitutions: u64,
    untouched_payloads: u64,
    copied_payloads: u64,
    payload_audits: u64,
    fact_kept_index: u64,
    function_kept_index: u64,
    retired_index_once: u64,
    retirement_row_reads_saved: u64,
    index_audits: u64,
    fact_adoptions: u64,
    function_adoptions: u64,
    source_fields: u64,
    eager_forward_edges: u64,
    deferred_forward_headers: u64,
    audited_adoptions: u64,
}
impl Graph {
    pub fn configure_repair_reuse(&mut self, mode: u64, audit: bool) -> Result<()> {
        if mode > 63
            || mode & 24 == 24
            || mode & 34 == 34
            || cfg!(feature = "sparse-cells")
            || self.union_digest.is_some()
            || self.stable_ports.is_some()
            || self.local_unions.is_some()
        {
            return Err("ordered repair experiment requires ordinary source storage".into());
        }
        let eq_masks = self
            .program
            .tables
            .iter()
            .map(|t| {
                if t.schema.len() > 64 {
                    return None;
                }
                let mut mask = 0;
                for (i, s) in t.schema.iter().enumerate() {
                    match s["kind"].as_str()? {
                        "eq" => mask |= 1 << i,
                        "i64" | "f64" | "String" | "Unit" | "bool" | "structural_key" => (),
                        _ => return None,
                    }
                }
                Some(mask)
            })
            .collect();
        self.repair_reuse = RepairReuse {
            mode: mode as u8,
            audit,
            eq_masks,
            ..Default::default()
        };
        Ok(())
    }
    pub fn repair_reuse_report(&self) -> J {
        let mut normalized = 0;
        if self.repair_reuse.audit && self.repair_reuse.mode & 24 != 0 {
            let mut expected: HashMap<u64, BTreeSet<Dependency>> = HashMap::default();
            for (&d, forward) in &self.dependencies {
                for id in forward {
                    expected
                        .entry(root(&self.parents, *id))
                        .or_default()
                        .insert(d);
                }
            }
            for (id, members) in &expected {
                assert!(
                    self.uses
                        .get(id)
                        .is_some_and(|s| s.iter().eq(members.iter())),
                    "reverse bucket differs after forward adoption"
                );
                normalized += members.len();
            }
            assert_eq!(
                normalized,
                self.uses.values().map(|s| s.len()).sum::<usize>()
            );
        }
        json!({"raw_forward_entries":self.dependencies.values().map(|d|d.len()).sum::<usize>(),
             "forward_headers":self.dependencies.len(),"verified_reverse_edges":normalized,"work":self.repair_reuse,"native":self.maintenance_report(),"repaired_dependencies":self.stats.repaired_dependencies,
            "repair_key_hash_changes":self.stats.repair_key_hash_changes,"repair_collisions":self.stats.repair_collisions})
    }
    fn adopt_canonical_subscription(
        &mut self,
        table: usize,
        d: Dependency,
        fields: &[Value],
    ) -> bool {
        if self.repair_reuse.mode & 24 == 0 {
            return false;
        }
        let Some(old) = self.dependencies.get(&d) else {
            return false;
        };
        if self.repair_reuse.audit {
            let current: BTreeSet<_> = old.iter().map(|id| root(&self.parents, *id)).collect();
            let mut actual = BTreeSet::new();
            fn scan(value: &Value, result: &mut BTreeSet<u64>) {
                match value {
                    Value::Eq(id) => {
                        result.insert(*id);
                    }
                    Value::Set(xs) => {
                        for v in xs.iter() {
                            scan(v, result)
                        }
                    }
                    _ => (),
                }
            }
            for v in fields {
                scan(v, &mut actual)
            }
            let actual = actual
                .into_iter()
                .map(|id| root(&self.parents, id))
                .collect::<BTreeSet<_>>();
            assert_eq!(
                current, actual,
                "repaired row changed its dependency domain"
            );
            assert!(
                current.iter().all(|id| self
                    .uses
                    .get(id)
                    .is_some_and(|b| b.iter().any(|addr| *addr == d))),
                "actual reverse membership must already be redirected by the union"
            );
            self.repair_reuse.audited_adoptions += 1;
        }
        if self.repair_reuse.mode & 8 != 0 {
            self.repair_reuse.eager_forward_edges += old.len() as u64;
            let rebased = old.iter().map(|id| root(&self.parents, *id)).collect();
            self.dependencies.insert(d, rebased);
        } else {
            self.repair_reuse.deferred_forward_headers += 1;
        }
        self.query_versions[table] += 1;
        self.repair_reuse.source_fields += fields.len() as u64;
        match d {
            Dependency::Fact(_) => self.repair_reuse.fact_adoptions += 1,
            Dependency::Function(_) => self.repair_reuse.function_adoptions += 1,
        }
        true
    }
    fn defer_displaced_fact(&mut self, d: Dependency) -> bool {
        let Dependency::Fact(f) = d else { return false };
        if self.repair_reuse.pending.len() >= 32768 {
            self.repair_reuse.pending_cap += 1;
            return false;
        }
        let Some(state) = self
            .cells
            .get_mut(&f.cell)
            .and_then(|c| c.facts.get_mut(&f.op))
        else {
            return false;
        };
        if let Some((t, _)) = &state.decoded
            && self.repair_reuse.eq_masks[*t].is_some()
        {
            let payload = state.decoded.take().unwrap();
            self.repair_reuse.pending.insert(f, payload);
            self.repair_reuse.pending_saved += 1;
            self.repair_reuse.peak_pending = self
                .repair_reuse
                .peak_pending
                .max(self.repair_reuse.pending.len());
            return true;
        }
        false
    }
    fn consume_displaced_fact(&mut self, f: FactRef) {
        let Some((table, mut fields)) = self.repair_reuse.pending.remove(&f) else {
            return;
        };
        if self.stable_node(f).is_some() {
            return;
        }
        let Some(state) = self
            .cells
            .get_mut(&f.cell)
            .and_then(|c| c.facts.get_mut(&f.op))
        else {
            return;
        };
        if state.decoded.is_some() {
            return;
        }
        let mut mask = self.repair_reuse.eq_masks[table].unwrap();
        while mask != 0 {
            let i = mask.trailing_zeros() as usize;
            mask &= mask - 1;
            if let Value::Eq(v) = fields[i] {
                let id = root(&self.parents, v);
                if id != v {
                    #[cfg(not(feature = "sparse-cells"))]
                    {
                        std::rc::Rc::make_mut(&mut fields)[i] = Value::Eq(id);
                    }
                    #[cfg(feature = "sparse-cells")]
                    {
                        std::sync::Arc::make_mut(&mut fields)[i] = Value::Eq(id);
                    }
                    self.repair_reuse.substitutions += 1;
                }
            }
        }
        state.decoded = Some((table, fields));
        self.repair_reuse.pending_consumed += 1;
        if self.repair_reuse.audit {
            let c = &self.cells[&f.cell];
            let state = &c.facts[&f.op];
            let source = self
                .decode_fact(f, c, state)
                .expect("current immutable fact operands");
            assert_eq!(
                source.values,
                state.decoded.as_ref().unwrap().1,
                "late source normalization"
            );
            self.repair_reuse.payload_audits += 1;
        }
    }
    fn update_displaced_fields(
        &mut self,
        d: Dependency,
        table: Option<usize>,
        from: u64,
        to: u64,
    ) -> bool {
        self.repair_reuse.payload_attempts += 1;
        let Some(table) = table else { return false };
        let Some(Some(mut mask)) = self.repair_reuse.eq_masks.get(table).copied() else {
            self.repair_reuse.unsupported_schemas += 1;
            return false;
        };
        let fields = match d {
            Dependency::Fact(f) => self
                .cells
                .get_mut(&f.cell)
                .and_then(|c| c.facts.get_mut(&f.op))
                .and_then(|s| s.decoded.as_mut())
                .filter(|(t, _)| *t == table)
                .map(|(_, v)| v),
            Dependency::Function(i) => self.function_decoded.get_mut(i).and_then(Option::as_mut),
        };
        let Some(fields) = fields else {
            self.repair_reuse.missing_payloads += 1;
            return false;
        };
        if fields.len() != self.program.tables[table].schema.len() {
            return false;
        }
        let mut changed = 0u64;
        self.repair_reuse.scalar_positions += mask.count_ones() as u64;
        while mask != 0 {
            let col = mask.trailing_zeros() as usize;
            if fields[col] == Value::Eq(from) {
                changed |= 1 << col;
            }
            mask &= mask - 1;
        }
        self.repair_reuse.substitutions += changed.count_ones() as u64;
        if changed == 0 {
            self.repair_reuse.untouched_payloads += 1;
        } else {
            #[cfg(not(feature = "sparse-cells"))]
            let payload = {
                self.repair_reuse.copied_payloads +=
                    u64::from(std::rc::Rc::strong_count(fields) > 1);
                &mut std::rc::Rc::make_mut(fields)[..]
            };
            #[cfg(feature = "sparse-cells")]
            let payload = {
                self.repair_reuse.copied_payloads +=
                    u64::from(std::sync::Arc::strong_count(fields) > 1);
                std::sync::Arc::make_mut(fields)
            };
            while changed != 0 {
                let col = changed.trailing_zeros() as usize;
                payload[col] = Value::Eq(to);
                changed &= changed - 1;
            }
        }
        match d {
            Dependency::Fact(_) => self.repair_reuse.fact_payloads += 1,
            Dependency::Function(_) => self.repair_reuse.function_payloads += 1,
        }
        if self.repair_reuse.audit {
            let saved = fields.clone();
            let original = match d {
                Dependency::Fact(f) => {
                    let c = &self.cells[&f.cell];
                    self.decode_fact(f, c, &c.facts[&f.op])
                        .expect("independent source fact decode")
                        .values
                }
                Dependency::Function(i) => self.decode_function(i, &self.functions[i]),
            };
            assert_eq!(
                saved, original,
                "displaced-port substitution must equal current source fields"
            );
            self.repair_reuse.payload_audits += 1;
        }
        true
    }
}
