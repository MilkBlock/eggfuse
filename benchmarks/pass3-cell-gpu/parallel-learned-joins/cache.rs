use std::sync::Arc;

enum EpochColumn {
    Local(Vec<u64>),
    Shared(Arc<[u64]>),
}
impl std::ops::Deref for EpochColumn {
    type Target = [u64];
    fn deref(&self) -> &[u64] {
        match self {
            Self::Local(v) => v,
            Self::Shared(v) => v,
        }
    }
}
enum BucketColumn<'a> {
    Local(FxHashMap<u32, &'a [usize]>),
    Shared(Arc<FxHashMap<u32, Vec<usize>>>),
}
impl BucketColumn<'_> {
    fn get(&self, k: &u32) -> Option<&[usize]> {
        match self {
            Self::Local(v) => v.get(k).copied(),
            Self::Shared(v) => v.get(k).map(Vec::as_slice),
        }
    }
}
#[derive(Default)]
struct WorkerColumns {
    budget: usize,
    used: usize,
    epochs: FxHashMap<usize, (u64, u64, usize, Arc<[u64]>)>,
    buckets: FxHashMap<(usize, usize), (u64, u64, usize, Arc<FxHashMap<u32, Vec<usize>>>)>,
}
impl WorkerColumns {
    fn epochs(&mut self, f: &Frame, work: &mut WorkerStats) -> EpochColumn {
        let charge = 64 + f.rows.len() * 8;
        if self.budget != 0 {
            if let Some((v, u, _, col)) = self.epochs.get(&f.table)
                && (*v, *u) == (f.generation, f.born_at_union)
            {
                work.epoch_hits += 1;
                return EpochColumn::Shared(col.clone());
            }
            if let Some((_, _, size, _)) = self.epochs.remove(&f.table) {
                self.used -= size;
            }
            if self.used + charge <= self.budget {
                let col: Arc<[u64]> = f.rows.iter().map(|r| r.epoch).collect::<Vec<_>>().into();
                self.epochs.insert(
                    f.table,
                    (f.generation, f.born_at_union, charge, col.clone()),
                );
                self.used += charge;
                work.epoch_installs += 1;
                work.peak_retained = work.peak_retained.max(self.used);
                return EpochColumn::Shared(col);
            }
            work.budget_refusals += 1;
        }
        EpochColumn::Local(f.rows.iter().map(|r| r.epoch).collect())
    }
    fn groups<'a>(
        &mut self,
        f: &Frame,
        col: usize,
        index: &'a FxHashMap<u32, Rc<Vec<usize>>>,
        work: &mut WorkerStats,
    ) -> BucketColumn<'a> {
        let key = (f.table, col);
        let charge = 128 + index.len() * 64 + f.rows.len() * std::mem::size_of::<usize>();
        if self.budget != 0 {
            if let Some((v, u, _, g)) = self.buckets.get(&key)
                && (*v, *u) == (f.generation, f.born_at_union)
            {
                work.bucket_hits += 1;
                return BucketColumn::Shared(g.clone());
            }
            if let Some((_, _, size, _)) = self.buckets.remove(&key) {
                self.used -= size;
            }
            if self.used + charge <= self.budget {
                let groups = Arc::new(
                    index
                        .iter()
                        .map(|(&k, v)| (k, v.as_ref().clone()))
                        .collect(),
                );
                self.buckets.insert(
                    key,
                    (f.generation, f.born_at_union, charge, Arc::clone(&groups)),
                );
                self.used += charge;
                work.bucket_installs += 1;
                work.peak_retained = work.peak_retained.max(self.used);
                return BucketColumn::Shared(groups);
            }
            work.budget_refusals += 1;
        }
        BucketColumn::Local(index.iter().map(|(&k, v)| (k, v.as_slice())).collect())
    }
}
