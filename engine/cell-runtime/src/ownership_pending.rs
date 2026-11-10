//! Table-owned ready queues. The ordinary path retains its original flat set.
//! Scoped completion indexes only each nonempty table's head, not every pair
//! of producers and consumers. Membership remains in one queue per fact.
use super::*;
#[path = "pending_epoch.rs"]
mod epoch;

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
    tables: epoch::Tables,
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
    tables: &'a [BTreeMap<FactRef, u64>],
}
impl ReadView<'_> {
    pub fn contains(&self, table: usize, fact: &FactRef) -> bool {
        self.flat.map_or_else(
            || self.tables[table].contains_key(fact),
            |s| s.contains(fact),
        )
    }
}
impl<'a> ReadView<'a> {
    pub fn frozen(tables: &'a [BTreeMap<FactRef, u64>]) -> Self {
        Self { flat: None, tables }
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
            tables: self.tables.plain(),
        }
    }
    pub fn epoch_report(&self) -> J {
        self.tables.report()
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
            .map_or_else(|| self.tables.get(table, f).is_some(), |s| s.contains(f))
    }
    fn refresh(&mut self, table: usize, before: Option<FactRef>) {
        let after = self.tables.first(table);
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
        let before = self.tables.first(table);
        assert!(
            self.mixed_epochs || self.epochs[table].is_none_or(|e| e == epoch),
            "uncompleted table crossed a dependent source epoch"
        );
        self.counts.mixed_epoch_inserts +=
            u64::from(self.epochs[table].is_some_and(|e| e != epoch));
        self.epochs[table].get_or_insert(epoch);
        let (added, advanced) = self.tables.insert(table, f, epoch);
        self.counts.advanced_task_epochs += u64::from(advanced);
        self.len += usize::from(added);
        self.refresh(table, before);
        added
    }
    pub fn remove(&mut self, table: usize, f: &FactRef) -> bool {
        if let Some(flat) = &mut self.flat {
            return flat.remove(f);
        }
        let before = self.tables.first(table);
        let removed = self.tables.remove(table, f);
        self.len -= usize::from(removed);
        self.refresh(table, before);
        removed
    }
    pub fn first(&self, allowed: Option<crate::table_mask::Selection<'_>>) -> Option<(FactRef, usize)> {
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
        let epoch = self.tables.get(table, &f);
        assert!(self.remove(table, &f));
        epoch
    }
    pub fn iter(&self) -> impl Iterator<Item = &FactRef> {
        self.flat
            .iter()
            .flat_map(|s| s.iter())
            .chain(self.tables.keys())
    }
    /// A bounded, non-consuming merge of table queues. Only active heads and
    /// successors needed for this prefix are visited; no table-body scan.
    pub fn prefix_before(
        &self,
        before: Option<Dependency>,
        allowed: Option<crate::table_mask::Selection<'_>>,
        limit: usize,
    ) -> (
        smallvec::SmallVec<[(FactRef, usize); 16]>,
        u64,
        u64,
        u64,
        u64,
        usize,
    ) {
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
                if let Some(next) = self.tables.successor(table, f)
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

#[cfg(test)]
mod tests {
    use super::*;
    fn fact(n: u32) -> FactRef {
        FactRef { cell: n, op: n % 3 }
    }
    fn pending() -> Pending {
        let mut p = Pending::default();
        p.enable_scopes(3);
        p.enable_mixed_epochs();
        p.enable_causes();
        p
    }
    #[test]
    fn queue_snapshot_preserves_membership_while_live_epochs_advance() {
        let mut p = pending();
        p.insert(0, fact(3), 1);
        p.insert(0, fact(5), 2);
        p.insert(1, fact(1), 3);
        p.cause(0, 100);
        let snapshot = p.freeze();
        let reader = ReadView::frozen(&snapshot);
        assert!(p.remove(0, &fact(3)));
        assert!(!p.contains(0, &fact(3)));
        assert!(reader.contains(0, &fact(3)));
        assert!(p.insert(0, fact(3), 9));
        assert!(!p.insert(0, fact(5), 8));
        assert!(!p.insert(0, fact(5), 4));
        assert_eq!(p.first(Some(crate::table_mask::Selection::Flags(&[true, false, false]))), Some((fact(3), 0)));
        assert_eq!(p.pop(fact(3), 0), Some(9));
        // Re-enqueue after removal starts a new task, even at an earlier epoch.
        assert!(p.insert(0, fact(3), 2));
        assert_eq!(p.pop(fact(3), 0), Some(2));
        assert_eq!(p.pop(fact(5), 0), Some(8));
        assert!(p.causes(0).is_empty());
        assert_eq!(snapshot[0][&fact(3)], 1);
        assert_eq!(snapshot[0][&fact(5)], 2);
        drop(snapshot);
        let work = p.thaw();
        assert_eq!(work.copied_units, 0);
        assert_eq!(work.merged_entries, 2);
        assert_eq!(p.first(None), Some((fact(1), 1)));
        assert_eq!(p.pop(fact(1), 1), Some(3));
        assert!(p.is_empty());
    }
    #[test]
    fn epoch_queue_deltas_match_ordered_reference_through_reinsertion() {
        let (mut live, mut reference) = (pending(), pending());
        for n in 0..120 {
            live.insert(n as usize % 3, fact(n), n as u64 % 5);
            reference.insert(n as usize % 3, fact(n), n as u64 % 5);
        }
        let original = live.tables.plain().as_ptr();
        let snapshot = live.freeze();
        assert_eq!(snapshot.as_ptr(), original);
        let mut seed = 7u64;
        for step in 0..2000 {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            let n = ((seed >> 32) % 180) as u32;
            let table = n as usize % 3;
            match seed % 4 {
                0 | 1 => {
                    let epoch = (seed >> 16) % 11;
                    assert_eq!(
                        live.insert(table, fact(n), epoch),
                        reference.insert(table, fact(n), epoch)
                    );
                }
                2 => assert_eq!(
                    live.remove(table, &fact(n)),
                    reference.remove(table, &fact(n))
                ),
                _ => {
                    let mask = [true, step % 2 == 0, step % 3 == 0];
                    let first = reference.first(Some(crate::table_mask::Selection::Flags(&mask)));
                    let packed:crate::table_mask::Mask=mask.iter().copied().collect();
                    let selected=crate::table_mask::Selection::Packed(&packed);
                    assert_eq!(live.first(Some(selected)), first);
                    if let Some((f, t)) = first {
                        assert_eq!(live.pop(f, t), reference.pop(f, t));
                    }
                }
            }
            assert_eq!(live.len(), reference.len());
            assert_eq!(live.first(None), reference.first(None));
            assert_eq!(
                live.contains(table, &fact(n)),
                reference.contains(table, &fact(n))
            );
            assert_eq!(
                live.iter().copied().collect::<BTreeSet<_>>(),
                reference.iter().copied().collect()
            );
        }
        assert_eq!(snapshot.iter().map(BTreeMap::len).sum::<usize>(), 120);
        drop(snapshot);
        assert_eq!(live.thaw().copied_units, 0);
        assert_eq!(live.tables.plain().as_ptr(), original);
        assert_eq!(live.tables.plain(), reference.tables.plain());
        assert_eq!(
            serde_json::to_value(&live.counts).unwrap(),
            serde_json::to_value(&reference.counts).unwrap()
        );
        assert_eq!(
            live.prefix_before(None, None, 16),
            reference.prefix_before(None, None, 16)
        );
        // Prefix traversal uses the settled queues, not a frozen read epoch.
        let mask=[true,false,true];
        let packed:crate::table_mask::Mask=mask.into_iter().collect();
        assert_eq!(live.prefix_before(None,Some(crate::table_mask::Selection::Packed(&packed)),16),
            reference.prefix_before(None,Some(crate::table_mask::Selection::Flags(&mask)),16));
        // Retained delta capacities must carry no membership or old head into
        // a later epoch, including after ordinary writes between epochs.
        for round in 0..3 {
            let f = fact(200 + round);
            live.insert(0, f, 1);
            reference.insert(0, f, 1);
            let expected = reference.tables.plain().to_vec();
            let snapshot = live.freeze();
            for n in 0..40 {
                let table = n as usize % 3;
                assert_eq!(
                    live.remove(table, &fact(n)),
                    reference.remove(table, &fact(n))
                );
                assert_eq!(
                    live.insert(table, fact(n), round as u64),
                    reference.insert(table, fact(n), round as u64)
                );
                assert_eq!(live.first(None), reference.first(None));
            }
            assert_eq!(*snapshot, expected);
            drop(snapshot);
            assert_eq!(live.thaw().copied_units, 0);
            assert_eq!(live.tables.plain(), reference.tables.plain());
        }
    }
}
