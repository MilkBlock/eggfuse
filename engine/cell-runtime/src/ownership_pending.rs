//! Table-owned ready queues. The ordinary path retains its original flat set.
//! Scoped completion indexes only each nonempty table's head, not every pair
//! of producers and consumers. Membership remains in one queue per fact.
use super::*;
impl crate::read_epoch::EpochValue for BTreeMap<FactRef, u64> {
    fn copy_units(&self) -> usize {
        self.len()
    }
}

#[derive(Default, Serialize)]
pub(in crate::graph) struct Counts {
    pub scope_requests: u64,
    pub head_probes: Counter<u64>,
    pub head_updates: u64,
    pub legacy_frontier_probes: u64,
    pub bypassed_tasks: u64,
    pub opaque_full_completions: u64,
    pub cause_probes: u64,
    pub cause_comparisons: u64,
    pub cause_growths: u64,
    pub mixed_epoch_inserts: u64,
    pub advanced_task_epochs: u64,
    pub completion_epoch_checks: u64,
    pub completion_epoch_joins: u64,
}
pub(in crate::graph) struct Pending {
    flat: Option<BTreeSet<FactRef>>,
    tables: crate::read_epoch::Slots<BTreeMap<FactRef, u64>>,
    heads: BTreeSet<(FactRef, usize)>,
    epochs: Vec<Option<u64>>,
    causes: Option<Vec<smallvec::SmallVec<[u64; 2]>>>,
    len: usize,
    mixed_epochs: bool,
    pub counts: Counts,
}
/// Counter-free membership access into the authoritative queues. Borrowing it
/// across a worker read phase prevents inserts/pops until all readers return.
#[derive(Clone, Copy)]
pub(in crate::graph) struct ReadView<'a> {
    flat: Option<&'a BTreeSet<FactRef>>,
    tables: crate::read_epoch::SlotsRead<'a, BTreeMap<FactRef, u64>>,
}
impl ReadView<'_> {
    pub fn contains(&self, table: usize, fact: &FactRef) -> bool {
        self.flat.map_or_else(
            || self.tables.get(table).unwrap().contains_key(fact),
            |s| s.contains(fact),
        )
    }
}
impl<'a> ReadView<'a> {
    pub fn frozen(tables: &'a [BTreeMap<FactRef, u64>]) -> Self {
        Self {
            flat: None,
            tables: crate::read_epoch::SlotsRead {
                base: tables,
                changes: None,
            },
        }
    }
}
impl Default for Pending {
    fn default() -> Self {
        Self {
            flat: Some(BTreeSet::new()),
            tables: Default::default(),
            heads: BTreeSet::new(),
            epochs: vec![],
            causes: None,
            len: 0,
            mixed_epochs: false,
            counts: Counts::default(),
        }
    }
}
impl Pending {
    pub fn freeze(&mut self) -> std::sync::Arc<Vec<BTreeMap<FactRef, u64>>> {
        assert!(self.scoped());
        self.tables.freeze()
    }
    pub fn thaw(&mut self) -> crate::read_epoch::Work {
        self.tables.thaw()
    }
    pub fn reader(&self) -> ReadView<'_> {
        ReadView {
            flat: self.flat.as_ref(),
            tables: self.tables.reader(),
        }
    }
    pub fn enable_scopes(&mut self, n: usize) {
        assert!(
            self.is_empty(),
            "enable scoped queues at a settled boundary"
        );
        if self.flat.take().is_some() {
            self.tables = vec![BTreeMap::new(); n].into();
            self.epochs = vec![None; n];
        }
    }
    pub fn enable_mixed_epochs(&mut self) {
        assert!(self.scoped() && self.is_empty());
        self.mixed_epochs = true;
    }
    pub fn mixed_epochs(&self) -> bool {
        self.mixed_epochs
    }
    pub fn completion_epoch(&mut self, epoch: u64, row: u64, peer: Option<u64>) -> u64 {
        if !self.mixed_epochs {
            return epoch;
        }
        self.counts.completion_epoch_checks += 1;
        let joined = epoch.max(row).max(peer.unwrap_or(0));
        self.counts.completion_epoch_joins += u64::from(joined > epoch);
        joined
    }
    pub fn enable_causes(&mut self) {
        assert!(self.scoped() && self.is_empty());
        self.causes = Some(vec![smallvec::SmallVec::new(); self.tables.len()]);
    }
    pub fn cause(&mut self, table: usize, root: u64) {
        if let Some(causes) = &mut self.causes {
            self.counts.cause_probes += 1;
            if !causes[table].iter().any(|&old| {
                self.counts.cause_comparisons += 1;
                old == root
            }) {
                let before = causes[table].capacity();
                causes[table].push(root);
                self.counts.cause_growths += u64::from(before != causes[table].capacity());
            }
        }
    }
    pub fn causes(&self, table: usize) -> &[u64] {
        self.causes
            .as_ref()
            .map_or(&[], |causes| causes[table].as_slice())
    }
    pub fn scoped(&self) -> bool {
        self.flat.is_none()
    }
    pub fn len(&self) -> usize {
        self.flat.as_ref().map_or(self.len, BTreeSet::len)
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
    pub fn contains(&self, table: usize, f: &FactRef) -> bool {
        self.flat
            .as_ref()
            .map_or_else(|| self.tables[table].contains_key(f), |s| s.contains(f))
    }
    fn refresh(&mut self, table: usize, before: Option<FactRef>) {
        let after = self.tables[table].first_key_value().map(|(&f, _)| f);
        if after != before {
            if let Some(old) = before {
                self.heads.remove(&(old, table));
            }
            if let Some(new) = after {
                self.heads.insert((new, table));
            }
            self.counts.head_updates += 1;
        }
        if after.is_none() {
            self.epochs[table] = None;
            if let Some(causes) = &mut self.causes {
                causes[table].clear();
            }
        }
    }
    pub fn insert(&mut self, table: usize, f: FactRef, epoch: u64) -> bool {
        if let Some(flat) = &mut self.flat {
            return flat.insert(f);
        }
        let before = self.tables[table].first_key_value().map(|(&f, _)| f);
        assert!(
            self.mixed_epochs || self.epochs[table].is_none_or(|e| e == epoch),
            "uncompleted table crossed a dependent source epoch"
        );
        self.counts.mixed_epoch_inserts +=
            u64::from(self.epochs[table].is_some_and(|e| e != epoch));
        self.epochs[table].get_or_insert(epoch);
        let added = match self.tables[table].entry(f) {
            std::collections::btree_map::Entry::Vacant(entry) => {
                entry.insert(epoch);
                true
            }
            std::collections::btree_map::Entry::Occupied(mut entry) => {
                if epoch > *entry.get() {
                    self.counts.advanced_task_epochs += 1;
                    *entry.get_mut() = epoch;
                }
                false
            }
        };
        self.len += usize::from(added);
        self.refresh(table, before);
        added
    }
    pub fn remove(&mut self, table: usize, f: &FactRef) -> bool {
        if let Some(flat) = &mut self.flat {
            return flat.remove(f);
        }
        let before = self.tables[table].first_key_value().map(|(&f, _)| f);
        let removed = self.tables[table].remove(f).is_some();
        self.len -= usize::from(removed);
        self.refresh(table, before);
        removed
    }
    pub fn first(&self, allowed: Option<&[bool]>) -> Option<(FactRef, usize)> {
        if let Some(flat) = &self.flat {
            assert!(allowed.is_none(), "scoped queue is not enabled");
            return flat.first().map(|&f| (f, usize::MAX));
        }
        self.heads.iter().copied().find(|&(_, t)| {
            self.counts
                .head_probes
                .set(self.counts.head_probes.get() + 1);
            allowed.is_none_or(|a| a[t])
        })
    }
    pub fn pop(&mut self, f: FactRef, table: usize) -> Option<u64> {
        if let Some(flat) = &mut self.flat {
            assert!(flat.remove(&f));
            return None;
        }
        let epoch = self.tables[table].get(&f).copied();
        assert!(self.remove(table, &f));
        epoch
    }
    pub fn iter(&self) -> impl Iterator<Item = &FactRef> {
        self.flat
            .iter()
            .flat_map(|s| s.iter())
            .chain(self.tables.iter().flat_map(|s| s.keys()))
    }
    /// A bounded, non-consuming merge of table queues. Only active heads and
    /// successors needed for this prefix are visited; no table-body scan.
    pub fn prefix_before(
        &self,
        before: Option<Dependency>,
        allowed: Option<&[bool]>,
        limit: usize,
    ) -> (
        smallvec::SmallVec<[(FactRef, usize); 16]>,
        u64,
        u64,
        u64,
        u64,
        usize,
    ) {
        use std::ops::Bound::{Excluded, Unbounded};
        assert!(self.scoped());
        let mut heads = smallvec::SmallVec::<[(FactRef, usize); 16]>::new();
        let mut visits = 0;
        for &(f, table) in &self.heads {
            visits += 1;
            if before.is_some_and(|d| d < Dependency::Fact(f)) {
                break;
            }
            if allowed.is_none_or(|a| a[table]) {
                heads.push((f, table));
            }
            if heads.len() == limit {
                break;
            }
        }
        let mut out = smallvec::SmallVec::new();
        let mut comparisons = 0;
        let mut successors = 0;
        while out.len() < limit && !heads.is_empty() {
            let index = (0..heads.len())
                .min_by(|&a, &b| {
                    comparisons += 1;
                    heads[a].cmp(&heads[b])
                })
                .unwrap();
            let (f, table) = heads.swap_remove(index);
            out.push((f, table));
            if out.len() < limit {
                successors += 1;
                if let Some((&next, _)) = self.tables[table].range((Excluded(f), Unbounded)).next()
                    && before.is_none_or(|d| Dependency::Fact(next) <= d)
                {
                    heads.push((next, table));
                }
            }
        }
        let allocations = u64::from(out.spilled()) + u64::from(heads.spilled());
        let bytes = (if out.spilled() { out.capacity() } else { 0 }
            + if heads.spilled() { heads.capacity() } else { 0 })
            * std::mem::size_of::<(FactRef, usize)>();
        (out, visits, comparisons, successors, allocations, bytes)
    }
    pub fn active_tables(&self) -> impl Iterator<Item = usize> + '_ {
        self.heads.iter().map(|&(_, t)| t)
    }
}
