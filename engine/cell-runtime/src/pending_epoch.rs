//! Ordered queue overlays. Readers retain the original table maps; current
//! mutations shadow individual facts, never clone an entire queue table.
use super::*;
use rustc_hash::FxHashSet;
use std::{
    ops::Bound::{Excluded, Unbounded},
    sync::Arc,
};

type Table = BTreeMap<FactRef, u64>;
#[derive(Default, Serialize)]
struct Counts {
    table_probes: Counter<u64>,
    shadow_probes: Counter<u64>,
    live_probes: Counter<u64>,
    base_probes: Counter<u64>,
    base_head_reads: Counter<u64>,
    overlay_head_reads: Counter<u64>,
    table_activations: u64,
    shadow_insert_attempts: u64,
    changed_facts: u64,
    live_inserts: u64,
    live_removes: u64,
    base_successor_ranges: u64,
    base_successor_steps: u64,
    merge_live_probes: u64,
}
fn inc(n: &Counter<u64>) {
    n.set(n.get() + 1);
}
#[derive(Default)]
struct Delta {
    // Once shadowed, a base key never becomes visible again in this epoch.
    // Re-enqueue goes into live, so the base head never needs to move backward.
    shadow: FxHashSet<FactRef>,
    live: Table,
    base_head: Option<FactRef>,
}
#[derive(Default)]
pub(super) struct Tables {
    local: Vec<Table>,
    base: Option<Arc<Vec<Table>>>,
    deltas: HashMap<usize, Delta>,
    touched: Vec<usize>,
    work: crate::read_epoch::Work,
    counts: Counts,
}
impl From<Vec<Table>> for Tables {
    fn from(local: Vec<Table>) -> Self {
        Self {
            local,
            ..Self::default()
        }
    }
}
impl Tables {
    pub fn len(&self) -> usize {
        self.base.as_ref().map_or(self.local.len(), |b| b.len())
    }
    pub fn plain(&self) -> &[Table] {
        assert!(
            self.base.is_none(),
            "ordinary queue reader inside a read epoch"
        );
        &self.local
    }
    pub fn freeze(&mut self) -> Arc<Vec<Table>> {
        assert!(self.base.is_none() && self.touched.is_empty());
        self.work = Default::default();
        let base = Arc::new(std::mem::take(&mut self.local));
        self.base = Some(base.clone());
        base
    }
    pub fn thaw(&mut self) -> crate::read_epoch::Work {
        self.local = Arc::try_unwrap(self.base.take().expect("active queue epoch"))
            .unwrap_or_else(|_| panic!("queue readers still live"));
        for table in self.touched.drain(..) {
            inc(&self.counts.table_probes);
            let delta = self.deltas.get_mut(&table).unwrap();
            self.work.merged_entries += delta.shadow.len() as u64;
            for fact in delta.shadow.drain() {
                self.counts.merge_live_probes += 1;
                if !delta.live.contains_key(&fact) {
                    self.local[table].remove(&fact);
                }
            }
            for (fact, epoch) in std::mem::take(&mut delta.live) {
                self.local[table].insert(fact, epoch);
            }
        }
        self.work
    }
    pub fn get(&self, table: usize, fact: &FactRef) -> Option<u64> {
        let Some(base) = &self.base else {
            return self.local[table].get(fact).copied();
        };
        inc(&self.counts.table_probes);
        if let Some(delta) = self.deltas.get(&table) {
            inc(&self.counts.shadow_probes);
            if delta.shadow.contains(fact) {
                inc(&self.counts.live_probes);
                return delta.live.get(fact).copied();
            }
        }
        inc(&self.counts.base_probes);
        base[table].get(fact).copied()
    }
    pub fn first(&self, table: usize) -> Option<FactRef> {
        let Some(base) = &self.base else {
            return self.local[table].first_key_value().map(|(&f, _)| f);
        };
        inc(&self.counts.table_probes);
        if let Some(delta) = self.deltas.get(&table).filter(|d| !d.shadow.is_empty()) {
            inc(&self.counts.overlay_head_reads);
            return delta
                .base_head
                .into_iter()
                .chain(delta.live.first_key_value().map(|(&f, _)| f))
                .min();
        }
        inc(&self.counts.base_head_reads);
        base[table].first_key_value().map(|(&f, _)| f)
    }
    fn edit(&mut self, table: usize, fact: FactRef, value: Option<u64>) {
        let base = &self.base.as_ref().unwrap()[table];
        inc(&self.counts.table_probes);
        let table_capacity = self.deltas.capacity();
        let delta = self.deltas.entry(table).or_default();
        if delta.shadow.is_empty() {
            self.counts.table_activations += 1;
            inc(&self.counts.base_head_reads);
            delta.base_head = base.first_key_value().map(|(&f, _)| f);
            let capacity = self.touched.capacity();
            self.touched.push(table);
            self.work.growths += u64::from(capacity != self.touched.capacity());
        }
        self.counts.shadow_insert_attempts += 1;
        let capacity = delta.shadow.capacity();
        self.counts.changed_facts += u64::from(delta.shadow.insert(fact));
        self.work.growths += u64::from(capacity != delta.shadow.capacity());
        match value {
            Some(epoch) => {
                delta.live.insert(fact, epoch);
                self.counts.live_inserts += 1;
            }
            None => {
                delta.live.remove(&fact);
                self.counts.live_removes += 1;
            }
        }
        if delta.base_head == Some(fact) {
            self.counts.base_successor_ranges += 1;
            delta.base_head = None;
            for (&next, _) in base.range((Excluded(fact), Unbounded)) {
                self.counts.base_successor_steps += 1;
                inc(&self.counts.shadow_probes);
                if !delta.shadow.contains(&next) {
                    delta.base_head = Some(next);
                    break;
                }
            }
        }
        self.work.growths += u64::from(table_capacity != self.deltas.capacity());
    }
    /// Return (new membership, advanced source epoch), matching BTreeMap entry.
    pub fn insert(&mut self, table: usize, fact: FactRef, epoch: u64) -> (bool, bool) {
        if self.base.is_none() {
            return match self.local[table].entry(fact) {
                std::collections::btree_map::Entry::Vacant(e) => {
                    e.insert(epoch);
                    (true, false)
                }
                std::collections::btree_map::Entry::Occupied(mut e) => {
                    let advanced = epoch > *e.get();
                    if advanced {
                        *e.get_mut() = epoch;
                    }
                    (false, advanced)
                }
            };
        }
        self.work.writes += 1;
        let old = self.get(table, &fact);
        if old.is_some_and(|v| v >= epoch) {
            return (false, false);
        }
        self.edit(table, fact, Some(epoch));
        (old.is_none(), old.is_some())
    }
    pub fn remove(&mut self, table: usize, fact: &FactRef) -> bool {
        if self.base.is_none() {
            return self.local[table].remove(fact).is_some();
        }
        self.work.writes += 1;
        if self.get(table, fact).is_none() {
            return false;
        }
        self.edit(table, *fact, None);
        true
    }
    pub fn successor(&self, table: usize, fact: FactRef) -> Option<FactRef> {
        // A new batch is prepared only after the previous epoch has joined.
        self.plain()[table]
            .range((Excluded(fact), Unbounded))
            .next()
            .map(|(&f, _)| f)
    }
    /// Diagnostic membership only; base and live keys are not merged in order.
    /// Scheduling must use first/successor instead.
    pub fn keys(&self) -> impl Iterator<Item = &FactRef> {
        let base = self.base.as_deref().unwrap_or(&self.local);
        let changes = self.base.as_ref().map(|_| &self.deltas);
        base.iter().enumerate().flat_map(move |(table, map)| {
            let delta = changes.and_then(|d| d.get(&table));
            map.keys()
                .filter(move |f| delta.is_none_or(|d| !d.shadow.contains(*f)))
                .chain(delta.into_iter().flat_map(|d| d.live.keys()))
        })
    }
    pub fn report(&self) -> J {
        json!({"stats":self.counts,
            "retained_tables":self.deltas.len(),
            "retained_shadow_slots":self.deltas.values().map(|d| d.shadow.capacity()).sum::<usize>(),
            "touched_table_capacity":self.touched.capacity(),
            "scope":"fact overlays and monotone base heads; snapshot queues are never cloned"})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn requeued_early_keys_never_rescan_a_shadowed_base_prefix() {
        let fact = |cell| FactRef { cell, op: 0 };
        let map = (0..10_000).map(|n| (fact(n), 1)).collect();
        let mut queues: Tables = vec![map].into();
        let snapshot = queues.freeze();
        for n in 0..100 {
            assert!(queues.remove(0, &fact(n)));
        }
        let steps = queues.counts.base_successor_steps;
        let searches = queues.counts.base_successor_ranges;
        assert_eq!((steps, searches), (100, 100));
        for epoch in 2..1002 {
            assert_eq!(queues.insert(0, fact(0), epoch), (true, false));
            assert_eq!(queues.first(0), Some(fact(0)));
            assert!(queues.remove(0, &fact(0)));
            assert_eq!(queues.first(0), Some(fact(100)));
        }
        assert_eq!(
            (
                queues.counts.base_successor_steps,
                queues.counts.base_successor_ranges
            ),
            (steps, searches)
        );
        assert!(queues.remove(0, &fact(9999)));
        assert_eq!(queues.insert(0, fact(10001), 7), (true, false));
        assert_eq!(snapshot[0].len(), 10_000);
        drop(snapshot);
        let work = queues.thaw();
        assert_eq!(work.copied_units, 0);
        assert_eq!(work.merged_entries, 102);
        assert_eq!(queues.plain()[0].len(), 9900);
    }
}
