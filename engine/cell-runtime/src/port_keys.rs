//! Exact constructor lookup through the existing symbolic port domains.
//! Every admitted key has an equality input. Its canonical-root boundary entry
//! (or native port) reaches a shared template slice containing every live use.
//! This is a completeness argument, not a sampled candidate list. No operator
//! bucket is scanned and no per-constructor reverse list is installed.
//! Immutable birth hashes are optional candidate hints. A hit still needs an
//! exact equality proof; aliases can cause misses, never index repair.
use super::*;

impl Graph {
    /// Drop only optional birth hints where complete Cell port domains already
    /// prove enumeration. Configure before executing; uncovered keys keep intern.
    pub fn use_port_domains_only(&mut self)->Result<()> {
        self.use_port_constructor_matching()?;
        if !self.ownership_settled() || !self.pending_unions.is_empty() || !self.dirty.is_empty() {
            return Err("port-domain takeover requires a settled boundary".into());
        }
        let retired=self.cells.cell_ids().flat_map(|cell|self.cells.fact_states(cell))
            .filter_map(|(fact,state)|self.live_table(Dependency::Fact(fact))
                .filter(|&t|self.port_keys_enabled(t)).map(|_|(fact,state.hash))).collect::<Vec<_>>();
        for (fact,hash) in retired {
            self.cells.fact_state_mut(fact).unwrap().hash=0;
            if let Some(bucket)=self.intern.get_mut(&hash) {
                bucket.remove(&fact);
                if bucket.is_empty() {self.intern.remove(&hash);}
            }
        }
        self.intern.shrink_to_fit();
        self.port_birth_hints=false;
        Ok(())
    }
    pub(in crate::graph) fn constructor_hint_enabled(&self,table:usize)->bool {
        self.port_birth_hints || !self.port_keys_enabled(table)
    }

    #[cfg(feature = "sparse-cells")]
    pub(in crate::graph) fn port_constructor_keys_active(&self) -> bool {
        self.stable_ports.as_ref().is_some_and(|p| p.keys)
    }
    #[cfg(feature = "sparse-cells")]
    pub(in crate::graph) fn record_query_key_work(&self, w: &query_read::Work) {
        let s = self.stable_ports.as_ref().unwrap();
        macro_rules! add { ($f:ident, $v:expr) => { s.$f.set(s.$f.get() + $v); }; }
        // Ordinary canonical constructor reads are also measured here, but
        // key_lookups remains the original port-key subset.
        add!(key_lookups, w.port_lookups); add!(key_candidates, w.candidates);
        add!(birth_hint_probes, w.hint_probes); add!(birth_hint_hits, w.hint_hits);
        add!(port_domain_probes, w.domains);
        self.record_guard_reads(&w.reads);
    }
    pub fn new_with_port_keys(p: Program) -> Result<Self> {
        let mut g = Self::new_with_stable_ports(p)?;
        g.use_port_constructor_matching()?;
        Ok(g)
    }
    pub fn use_port_constructor_matching(&mut self) -> Result<()> {
        self.use_stable_port_fields()?;
        if self.stable_ports.as_ref().unwrap().keys {
            return Ok(());
        }
        if !self.ownership_settled() || !self.pending_unions.is_empty() || !self.dirty.is_empty() {
            return Err("enable port constructor matching at a settled boundary".into());
        }
        for (table, columns) in self.program.repair_ports.key_eq_columns.iter().enumerate() {
            if columns.as_ref().is_some_and(|c| !c.is_empty()) {
                if self.ownership.as_ref().unwrap().tables[table] != self.witness_count(table) {
                    return Err("constructor table lacks complete symbolic-port coverage".into());
                }
            }
        }
        let plan = &mut self.program.cell_ownership;
        plan.composition.prepare_queries(&plan.programs);
        self.stable_ports.as_mut().unwrap().keys = true;
        // Existing hints freeze here. Subsequent unions never relocate them.
        Ok(())
    }
    pub(in crate::graph) fn port_keys_enabled(&self, table: usize) -> bool {
        self.stable_ports.as_ref().is_some_and(|p| p.keys)
            && self.program.repair_ports.key_eq_columns[table]
                .as_ref()
                .is_some_and(|c| !c.is_empty())
    }
    pub(in crate::graph) fn lookup_port_key(
        &self,
        table: usize,
        key: &[Value],
        completing: Option<FactRef>,
    ) -> Result<Option<Row>> {
        let stats = self.stable_ports.as_ref().ok_or("port key mode disabled")?;
        stats.key_lookups.set(stats.key_lookups.get() + 1);
        let columns = self.program.repair_ports.key_eq_columns[table]
            .as_ref()
            .ok_or("uncovered port key")?;
        if key.len() + 1 != self.program.tables[table].schema.len()
            || columns
                .iter()
                .any(|&c| !matches!(key.get(c), Some(Value::Eq(_))))
        {
            return Ok(None);
        }
        assert!(
            !columns.is_empty(),
            "port candidate lookup requires an equality input"
        );
        if self.port_birth_hints && completing.is_none() && self.dirty_facts[table].is_empty() {
            stats
                .birth_hint_probes
                .set(stats.birth_hint_probes.get() + 1);
            let hint = self.constructor_hash(table, key);
            for &f in self.intern.get(&hint).into_iter().flatten() {
                if let Some(row) = self.exact_port_candidate(f, table, key)? {
                    stats.birth_hint_hits.set(stats.birth_hint_hits.get() + 1);
                    return Ok(Some(row));
                }
            }
        }
        stats
            .port_domain_probes
            .set(stats.port_domain_probes.get() + 1);
        let bound = key
            .iter()
            .cloned()
            .map(Some)
            .collect::<smallvec::SmallVec<[_; 4]>>();
        // This always has an equality input, so owned_candidates cannot fall
        // back to enumerating the operator's members.
        for candidate in self.owned_candidates(table, &bound) {
            let Dependency::Fact(f) = candidate else {
                return Err("constructor port domain contains a function".into());
            };
            if completing == Some(f) {
                continue;
            }
            // Preserve source-order collision commits: an unprocessed changed
            // key is not a completed survivor yet. Ordinary constructor reads
            // still see every live exact candidate, including pending ones.
            if completing.is_some() && self.ownership.as_ref().unwrap().pending.contains(table, &f)
            {
                stats
                    .pending_candidate_skips
                    .set(stats.pending_candidate_skips.get() + 1);
                continue;
            }
            if let Some(row) = self.exact_port_candidate(f, table, key)? {
                return Ok(Some(row));
            }
        }
        Ok(None)
    }
    pub(super) fn exact_port_candidate(
        &self,
        f: FactRef,
        table: usize,
        key: &[Value],
    ) -> Result<Option<Row>> {
        let stats = self.stable_ports.as_ref().unwrap();
        stats.key_candidates.set(stats.key_candidates.get() + 1);
        let Some(row) = self.stable_node(f) else {
            return Ok(None);
        };
        let mut work = guard::Work::default();
        let matched = self
            .stable_port_reader()?
            .key_matches(&row, table, key, &mut work);
        self.record_guard_reads(&work);
        if !matched? {
            return Ok(None);
        }
        self.read_stable_fact(f, self.cells.fact_state(f).unwrap(), &row)
            .map(Some)
    }
    pub(in crate::graph) fn complete_port_key(&mut self, f: FactRef, row: Row) -> Result<()> {
        self.dirty_facts[row.table].remove(&f);
        self.stable_ports.as_mut().unwrap().equality_completions += 1;
        let found = if let Some(found) = self.local_port_collision(f, &row)? {
            found
        } else {
            self.lookup_port_key(row.table, &row.values[..row.values.len() - 1], Some(f))?
        };
        self.complete_cell_collision(f, row, None, found, None)
    }
}
