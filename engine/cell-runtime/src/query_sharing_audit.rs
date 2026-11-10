//! Opt-in observation only. All queries still execute and report their original
//! result. These diagnostic keys live for one chunk in one immutable Run view;
//! they are never used as a fact cache or retained by production Cell instances.
use crate::{cell::Query, graph::Dependency, value::Value};
use rustc_hash::FxHashMap;
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Default, Serialize)]
pub(super) struct Counts {
    pub compiled_prefixes: u64,
    pub compiled_prefix_bytes: u64,
    pub entries: u64,
    pub successful_entries: u64,
    pub rejected_entries: u64,
    pub error_entries: u64,
    pub cell_scopes: u64,
    pub multi_entry_scopes: u64,
    pub point_reads: u64,
    pub cross_entry_repeated_reads: u64,
    pub same_entry_repeated_reads: u64,
    pub cross_rule_repeated_reads: u64,
    pub repeated_reads_in_successful_entries: u64,
    pub repeated_reads_in_rejected_entries: u64,
    pub prefix_steps: u64,
    pub same_anchor_prefix_steps: u64,
    pub same_anchor_prefix_reads: u64,
    pub same_anchor_prefix_guards: u64,
    pub distinct_read_keys: u64,
    pub distinct_prefix_keys: u64,
    pub diagnostic_value_clones: u64,
    pub peak_chunk_records: u64,
    // Key = template:old-rule:old-pivot:new-rule:new-pivot:table. Each
    // cross-entry repeated read belongs to exactly one first-observer pair.
    pub repeated_read_pairs: BTreeMap<String, u64>,
}
impl Counts {
    pub fn add(&mut self, other: &Self) {
        macro_rules! add { ($($f:ident),*) => { $(self.$f += other.$f;)* }; }
        add!(compiled_prefixes, compiled_prefix_bytes, entries, successful_entries, rejected_entries,
            error_entries, cell_scopes, multi_entry_scopes, point_reads, cross_entry_repeated_reads,
            same_entry_repeated_reads, cross_rule_repeated_reads, repeated_reads_in_successful_entries,
            repeated_reads_in_rejected_entries, prefix_steps, same_anchor_prefix_steps,
            same_anchor_prefix_reads, same_anchor_prefix_guards, distinct_read_keys,
            distinct_prefix_keys, diagnostic_value_clones);
        self.peak_chunk_records = self.peak_chunk_records.max(other.peak_chunk_records);
        for (key, count) in &other.repeated_read_pairs {
            *self.repeated_read_pairs.entry(key.clone()).or_default() += count;
        }
    }
}

/// Identical ordinary query prefixes, excluding only the source atom label.
/// Calls, argument projection, guards and every preceding step remain in the
/// identity. Entry watermark, delta ownership and witness atom labels remain
/// per-entry obligations, even when these calculations can be shared.
#[derive(Default)]
pub(super) struct Prefixes { ids: BTreeMap<String, usize> }
impl Prefixes {
    pub fn compile(&mut self, query: &Query) -> Vec<usize> {
        let mut parent = 0;
        query.steps.iter().map(|step| {
            assert!(step.expansion.is_none(), "point-only audit");
            let key = serde_json::to_string(&(parent, &step.call, &step.key, &step.check_result)).unwrap();
            let next = self.ids.len() + 1;
            parent = *self.ids.entry(key).or_insert(next);
            parent
        }).collect()
    }
}

#[derive(Clone, Copy)]
struct Source { entry: usize, rule: usize, pivot: usize }
#[derive(Default)]
struct Seen {
    entries: usize,
    reads: FxHashMap<(usize, Vec<Value>), Source>,
    prefixes: FxHashMap<(usize, Dependency, Vec<Value>), usize>,
}
#[derive(Default)]
pub(super) struct Probe {
    scopes: FxHashMap<(usize, Dependency), Seen>,
    current: Option<((usize, Dependency), Source)>,
    pending_repeats: u64,
    counts: Counts,
}
impl Probe {
    pub fn start(&mut self, scope: (usize, Dependency), entry: usize, rule: usize, pivot: usize) {
        let seen = self.scopes.entry(scope).or_default();
        self.counts.cell_scopes += u64::from(seen.entries == 0);
        self.counts.multi_entry_scopes += u64::from(seen.entries == 1);
        seen.entries += 1;
        self.counts.entries += 1;
        self.current = Some((scope, Source { entry, rule, pivot }));
        self.pending_repeats = 0;
    }
    pub fn prefix(&mut self, id: usize, anchor: &[Value], witness: Dependency, table: bool) {
        let (scope, source) = self.current.unwrap();
        self.counts.prefix_steps += 1;
        self.counts.diagnostic_value_clones += anchor.len() as u64;
        match self.scopes.get_mut(&scope).unwrap().prefixes.entry((id, witness, anchor.to_vec())) {
            std::collections::hash_map::Entry::Occupied(first) if *first.get() != source.entry => {
                self.counts.same_anchor_prefix_steps += 1;
                self.counts.same_anchor_prefix_reads += u64::from(table);
                self.counts.same_anchor_prefix_guards += u64::from(!table);
            }
            std::collections::hash_map::Entry::Occupied(_) => {}
            std::collections::hash_map::Entry::Vacant(first) => {
                first.insert(source.entry);
                self.counts.distinct_prefix_keys += 1;
            }
        }
    }
    pub fn read(&mut self, table: usize, args: &[Value]) {
        let (scope, source) = self.current.unwrap();
        self.counts.point_reads += 1;
        self.counts.diagnostic_value_clones += args.len() as u64;
        match self.scopes.get_mut(&scope).unwrap().reads.entry((table, args.to_vec())) {
            std::collections::hash_map::Entry::Occupied(first) => {
                let first = first.get();
                if first.entry == source.entry {
                    self.counts.same_entry_repeated_reads += 1;
                } else {
                    self.counts.cross_entry_repeated_reads += 1;
                    self.counts.cross_rule_repeated_reads += u64::from(first.rule != source.rule);
                    self.pending_repeats += 1;
                    let pair = format!("{}:{}:{}:{}:{}:{}", scope.0, first.rule, first.pivot, source.rule, source.pivot, table);
                    *self.counts.repeated_read_pairs.entry(pair).or_default() += 1;
                }
            }
            std::collections::hash_map::Entry::Vacant(first) => {
                first.insert(source);
                self.counts.distinct_read_keys += 1;
            }
        }
    }
    pub fn end(&mut self, matched: bool, error: bool) {
        self.counts.successful_entries += u64::from(matched);
        self.counts.error_entries += u64::from(error);
        self.counts.rejected_entries += u64::from(!matched && !error);
        if matched { self.counts.repeated_reads_in_successful_entries += self.pending_repeats; }
        else if !error { self.counts.repeated_reads_in_rejected_entries += self.pending_repeats; }
        self.current = None;
    }
    pub fn finish(mut self) -> Counts {
        self.counts.peak_chunk_records = self.scopes.values().map(|s| s.reads.len() + s.prefixes.len()).sum::<usize>() as u64;
        self.counts
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn witness(n: usize) -> Dependency { Dependency::Function(n) }
    #[test]
    fn overlap_is_scoped_to_actual_cells_and_the_current_snapshot() {
        let mut p = Probe::default();
        let key = [Value::Int(4)];
        for (entry, cell, rule, matched) in [(0, 3, 1, true), (1, 3, 2, false), (2, 4, 2, true)] {
            p.start((9, witness(cell)), entry, rule, 0);
            p.prefix(1, &key, witness(7), true);
            p.read(5, &key);
            if entry == 0 { p.read(5, &key); }
            p.end(matched, false);
        }
        let c = p.finish();
        assert_eq!((c.cell_scopes, c.multi_entry_scopes, c.point_reads), (2, 1, 4));
        assert_eq!((c.cross_entry_repeated_reads, c.same_entry_repeated_reads), (1, 1));
        assert_eq!((c.same_anchor_prefix_reads, c.cross_rule_repeated_reads), (1, 1));
        assert_eq!(c.repeated_reads_in_rejected_entries, 1);
        let mut next = Probe::default();
        next.start((9, witness(3)), 0, 2, 0);
        next.read(5, &key);
        next.end(true, false);
        assert_eq!(next.finish().cross_entry_repeated_reads, 0);
    }
    #[test]
    fn dynamic_overlap_does_not_prove_a_shared_prefix() {
        let mut p = Probe::default();
        for (entry, prefix, anchor) in [(0, 1, 7), (1, 2, 7), (2, 1, 8)] {
            p.start((9, witness(3)), entry, entry, 0);
            p.prefix(prefix, &[Value::Int(4)], witness(anchor), true);
            p.read(5, &[Value::Int(4)]);
            p.end(true, false);
        }
        let c = p.finish();
        assert_eq!(c.cross_entry_repeated_reads, 2);
        assert_eq!(c.same_anchor_prefix_reads, 0);
    }
}
