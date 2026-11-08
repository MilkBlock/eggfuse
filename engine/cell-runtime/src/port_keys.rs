//! Exact constructor lookup through the existing symbolic port domains.
//! Every admitted key has an equality input. Its canonical-root boundary entry
//! (or native port) reaches a shared template slice containing every live use.
//! This is a completeness argument, not a sampled candidate list. No operator
//! bucket is scanned and no per-constructor reverse list is installed.
//! Immutable birth hashes are optional candidate hints. A hit still needs an
//! exact equality proof; aliases can cause misses, never index repair.
use super::*;

impl Graph {
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
        if completing.is_none() && self.dirty_facts[table].is_empty() {
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
            if completing.is_some() && self.ownership.as_ref().unwrap().pending.contains(&f) {
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
    pub(super) fn exact_port_candidate(&self, f: FactRef, table: usize, key: &[Value]) -> Result<Option<Row>> {
        let stats = self.stable_ports.as_ref().unwrap();
        stats.key_candidates.set(stats.key_candidates.get() + 1);
        let Some(state) = self.cells.get(&f.cell).and_then(|c| c.facts.get(&f.op)) else {
            return Ok(None);
        };
        let Some(row) = &state.ports else {
            return Ok(None);
        };
        if row.table != table || row.fields.len() != key.len() + 1 {
            return Ok(None);
        }
        for (field, want) in row.fields.iter().zip(key) {
            stats
                .key_field_comparisons
                .set(stats.key_field_comparisons.get() + 1);
            if self.stable_field_value(field, true)? != *want {
                return Ok(None);
            }
        }
        self.read_stable_fact(f, state, row).map(Some)
    }
    pub(in crate::graph) fn complete_port_key(&mut self, f: FactRef, row: Row) -> Result<()> {
        self.dirty_facts[row.table].remove(&f);
        self.stable_ports.as_mut().unwrap().equality_completions += 1;
        let found = if let Some(found) = self.local_port_collision(f, &row)? {
            found
        } else {
            self.lookup_port_key(row.table, &row.values[..row.values.len() - 1], Some(f))?
        };
        if let Some(other) = &found {
            self.enqueue_union(
                row.values.last().unwrap().clone(),
                other.values.last().unwrap().clone(),
            )?;
        }
        // The shared commit handles visibility, receipts and retirement only.
        // None means no key hash, no canonical bucket removal/insertion.
        self.commit_constructor_collision(f, row, None, found)
    }
}
