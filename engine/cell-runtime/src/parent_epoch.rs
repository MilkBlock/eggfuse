use crate::read_epoch::Work;
use rustc_hash::FxHashMap;
use std::sync::Arc;
#[cfg(feature = "sparse-cells")]
pub(crate) type Base = super::root_directory::Parents;
#[cfg(not(feature = "sparse-cells"))]
pub(crate) type Base = FxHashMap<u64, u64>;

#[derive(Clone, Debug, Default)]
pub struct Parents {
    local: Base,
    base: Option<Arc<Base>>,
    delta: FxHashMap<u64, u64>,
    work: Work,
}
impl Parents {
    #[inline]
    pub fn get(&self, id: &u64) -> Option<&u64> {
        match &self.base {
            None => self.local.get(id),
            Some(base) => self.delta.get(id).or_else(|| base.get(id)),
        }
    }
    pub fn contains_key(&self, id: &u64) -> bool {
        self.get(id).is_some()
    }
    pub fn insert(&mut self, id: u64, to: u64) -> Option<u64> {
        if self.base.is_none() {
            return self.local.insert(id, to);
        }
        let old = self.get(&id).copied();
        let before = self.delta.capacity();
        self.delta.insert(id, to);
        self.work.writes += 1;
        self.work.growths += u64::from(self.delta.capacity() != before);
        old
    }
    pub fn clear(&mut self) {
        assert!(self.base.is_none(), "clear during a parent read epoch");
        self.local.clear();
    }
    pub fn len(&self) -> usize {
        self.base.as_ref().map_or(self.local.len(), |base| {
            base.len()
                + self
                    .delta
                    .keys()
                    .filter(|id| base.get(id).is_none())
                    .count()
        })
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
    pub(crate) fn reader(&self) -> Read<'_> {
        Read {
            base: self.base.as_deref().unwrap_or(&self.local),
            delta: self.base.as_ref().map(|_| &self.delta),
        }
    }
    pub(crate) fn freeze(&mut self) -> Arc<Base> {
        assert!(self.base.is_none());
        self.work = Work::default();
        let base = Arc::new(std::mem::take(&mut self.local));
        self.base = Some(base.clone());
        base
    }
    pub(crate) fn thaw(&mut self) -> Work {
        self.local = Arc::try_unwrap(self.base.take().expect("active parent epoch"))
            .unwrap_or_else(|_| panic!("parent readers still live"));
        self.work.merged_entries += self.delta.len() as u64;
        for (id, to) in self.delta.drain() {
            self.local.insert(id, to);
        }
        self.work
    }
}
#[derive(Clone, Copy)]
pub(crate) struct Read<'a> {
    pub base: &'a Base,
    pub delta: Option<&'a FxHashMap<u64, u64>>,
}
impl Read<'_> {
    pub fn root(&self, mut id: u64) -> u64 {
        while let Some(&to) = self
            .delta
            .and_then(|d| d.get(&id))
            .or_else(|| self.base.get(&id))
        {
            if to == id {
                break;
            }
            id = to;
        }
        id
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn snapshot_roots_stay_fixed_while_live_roots_follow_new_unions() {
        let mut parents = Parents::default();
        parents.insert(30, 20);
        let snapshot = parents.freeze();
        parents.insert(20, 10);
        let reader = Read {
            base: &snapshot,
            delta: None,
        };
        assert_eq!(reader.root(30), 20);
        assert_eq!(parents.reader().root(30), 10);
        assert_eq!(crate::value::root(&parents, 30), 10);
        drop(snapshot);
        let work = parents.thaw();
        assert_eq!((work.writes, work.merged_entries), (1, 1));
        assert_eq!(parents.reader().root(30), 10);
    }
}
