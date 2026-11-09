//! Short read epochs: move the base into shared ownership, retain writes in a
//! coordinator-owned overlay, then merge after all readers have joined.
//! No epoch is nested and no base container is cloned to create a snapshot.
use rustc_hash::FxHashMap as HashMap;
use serde::Serialize;
use std::{
    hash::Hash,
    ops::{Index, IndexMut},
    sync::Arc,
};

#[derive(Clone, Copy, Debug, Default, Serialize)]
pub(crate) struct Work {
    pub writes: u64,
    pub growths: u64,
    pub copied_units: u64,
    pub merged_entries: u64,
}
impl Work {
    pub fn add(&mut self, other: Self) {
        self.writes += other.writes;
        self.growths += other.growths;
        self.copied_units += other.copied_units;
        self.merged_entries += other.merged_entries;
    }
}

#[derive(Debug)]
pub(crate) struct Map<K, V> {
    local: HashMap<K, V>,
    base: Option<Arc<HashMap<K, V>>>,
    changes: HashMap<K, Option<V>>,
    work: Work,
}
impl<K, V> Default for Map<K, V> {
    fn default() -> Self {
        Self {
            local: HashMap::default(),
            base: None,
            changes: HashMap::default(),
            work: Work::default(),
        }
    }
}
impl<K: Copy + Eq + Hash, V> Map<K, V> {
    pub fn get(&self, key: &K) -> Option<&V> {
        match &self.base {
            None => self.local.get(key),
            Some(base) => self
                .changes
                .get(key)
                .map_or_else(|| base.get(key), Option::as_ref),
        }
    }
    pub fn insert(&mut self, key: K, value: V) -> Option<V> {
        // Pure constructor completion can retire nodes, but cannot create one.
        assert!(
            self.base.is_none(),
            "node birth during a completion read epoch"
        );
        self.local.insert(key, value)
    }
    pub fn remove(&mut self, key: &K) -> bool {
        if self.base.is_none() {
            return self.local.remove(key).is_some();
        }
        let present = self.get(key).is_some();
        if present {
            let before = self.changes.capacity();
            self.changes.insert(*key, None);
            self.work.writes += 1;
            self.work.growths += u64::from(self.changes.capacity() != before);
        }
        present
    }
    pub fn len(&self) -> usize {
        self.base
            .as_ref()
            .map_or(self.local.len(), |base| base.len() - self.changes.len())
    }
    pub fn reader(&self) -> MapRead<'_, K, V> {
        MapRead {
            base: self.base.as_deref().unwrap_or(&self.local),
            changes: self.base.as_ref().map(|_| &self.changes),
        }
    }
    pub fn freeze(&mut self) -> Arc<HashMap<K, V>> {
        assert!(self.base.is_none());
        self.work = Work::default();
        let base = Arc::new(std::mem::take(&mut self.local));
        self.base = Some(base.clone());
        base
    }
    pub fn thaw(&mut self) -> Work {
        let base = self.base.take().expect("active map epoch");
        self.local = Arc::try_unwrap(base).unwrap_or_else(|_| panic!("map readers still live"));
        self.work.merged_entries += self.changes.len() as u64;
        for (key, value) in self.changes.drain() {
            assert!(value.is_none());
            self.local.remove(&key);
        }
        self.work
    }
}
pub(crate) struct MapRead<'a, K, V> {
    pub base: &'a HashMap<K, V>,
    pub changes: Option<&'a HashMap<K, Option<V>>>,
}
impl<K, V> Copy for MapRead<'_, K, V> {}
impl<K, V> Clone for MapRead<'_, K, V> {
    fn clone(&self) -> Self {
        *self
    }
}
impl<K: Eq + Hash, V> MapRead<'_, K, V> {
    pub fn get(&self, key: &K) -> Option<&V> {
        self.changes
            .and_then(|c| c.get(key))
            .map_or_else(|| self.base.get(key), Option::as_ref)
    }
}

pub(crate) trait EpochValue: Clone {
    /// Logical values copied, not allocator bytes or a latency estimate.
    fn copy_units(&self) -> usize;
}
pub(crate) struct Slots<T> {
    local: Vec<T>,
    base: Option<Arc<Vec<T>>>,
    changes: HashMap<usize, T>,
    work: Work,
}
impl<T> Default for Slots<T> {
    fn default() -> Self {
        Self {
            local: vec![],
            base: None,
            changes: HashMap::default(),
            work: Work::default(),
        }
    }
}
impl<T> From<Vec<T>> for Slots<T> {
    fn from(local: Vec<T>) -> Self {
        Self {
            local,
            ..Self::default()
        }
    }
}
impl<T> Slots<T> {
    /// Birth/shape updates are forbidden while workers retain a read epoch.
    /// Unlike IndexMut, this path does not require or permit cloning a value.
    pub fn local_mut(&mut self, index: usize) -> &mut T {
        assert!(self.base.is_none(), "slot mutation during a read epoch");
        &mut self.local[index]
    }
    pub fn len(&self) -> usize {
        self.base.as_ref().map_or(self.local.len(), |b| b.len())
    }
    pub fn get(&self, index: usize) -> Option<&T> {
        match &self.base {
            None => self.local.get(index),
            Some(base) => self.changes.get(&index).or_else(|| base.get(index)),
        }
    }
    pub fn iter(&self) -> impl Iterator<Item = &T> {
        (0..self.len()).map(|i| self.get(i).unwrap())
    }
    pub fn push(&mut self, value: T) {
        assert!(
            self.base.is_none(),
            "component birth during a completion read epoch"
        );
        self.local.push(value);
    }
    pub fn reader(&self) -> SlotsRead<'_, T> {
        SlotsRead {
            base: self.base.as_deref().unwrap_or(&self.local),
            changes: self.base.as_ref().map(|_| &self.changes),
        }
    }
    pub fn freeze(&mut self) -> Arc<Vec<T>> {
        assert!(self.base.is_none());
        self.work = Work::default();
        let base = Arc::new(std::mem::take(&mut self.local));
        self.base = Some(base.clone());
        base
    }
    pub fn thaw(&mut self) -> Work {
        let base = self.base.take().expect("active slot epoch");
        self.local = Arc::try_unwrap(base).unwrap_or_else(|_| panic!("slot readers still live"));
        self.work.merged_entries += self.changes.len() as u64;
        for (index, value) in self.changes.drain() {
            self.local[index] = value;
        }
        self.work
    }
}
impl<T> Index<usize> for Slots<T> {
    type Output = T;
    fn index(&self, index: usize) -> &T {
        self.get(index).expect("slot index")
    }
}
impl<T> Slots<Option<T>> {
    /// Retire a whole entry without first copying it. Its old value remains
    /// in the immutable base until every reader has joined.
    pub fn retire(&mut self, index: usize) {
        assert!(self[index].is_some(), "retire a live slot once");
        if self.base.is_none() {
            self.local[index] = None;
        } else {
            let before = self.changes.capacity();
            self.changes.insert(index, None);
            self.work.writes += 1;
            self.work.growths += u64::from(self.changes.capacity() != before);
        }
    }
}
impl<T: EpochValue> IndexMut<usize> for Slots<T> {
    fn index_mut(&mut self, index: usize) -> &mut T {
        let Some(base) = &self.base else {
            return &mut self.local[index];
        };
        self.work.writes += 1;
        if !self.changes.contains_key(&index) {
            let before = self.changes.capacity();
            self.work.copied_units += base[index].copy_units() as u64;
            self.changes.insert(index, base[index].clone());
            self.work.growths += u64::from(self.changes.capacity() != before);
        }
        self.changes.get_mut(&index).unwrap()
    }
}
pub(crate) struct SlotsRead<'a, T> {
    pub base: &'a [T],
    pub changes: Option<&'a HashMap<usize, T>>,
}
impl<T> Copy for SlotsRead<'_, T> {}
impl<T> Clone for SlotsRead<'_, T> {
    fn clone(&self) -> Self {
        *self
    }
}
impl<T> SlotsRead<'_, T> {
    pub fn get(&self, index: usize) -> Option<&T> {
        self.changes
            .and_then(|c| c.get(&index))
            .or_else(|| self.base.get(index))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn whole_slot_retirement_keeps_nonclone_snapshot_without_copying() {
        struct NonClone(u64);
        let mut slots: Slots<Option<NonClone>> = vec![Some(NonClone(7))].into();
        let snapshot = slots.freeze();
        slots.retire(0);
        assert!(slots[0].is_none());
        assert_eq!(snapshot[0].as_ref().unwrap().0, 7);
        drop(snapshot);
        let work = slots.thaw();
        assert_eq!(
            (work.writes, work.copied_units, work.merged_entries),
            (1, 0, 1)
        );
        *slots.local_mut(0) = Some(NonClone(8));
        assert_eq!(slots[0].as_ref().unwrap().0, 8);
    }
    impl EpochValue for Vec<u64> {
        fn copy_units(&self) -> usize {
            self.len()
        }
    }
    #[test]
    fn snapshots_move_bases_and_copy_only_written_slots() {
        let mut slots: Slots<Vec<u64>> = vec![vec![1, 2, 3]; 128].into();
        let original = slots.reader().base.as_ptr();
        let snapshot = slots.freeze();
        assert_eq!(snapshot.as_ptr(), original);
        slots[7][0] = 9;
        slots[7][1] = 8;
        assert_eq!(snapshot[7], [1, 2, 3]);
        assert_eq!(slots[7], [9, 8, 3]);
        drop(snapshot);
        let work = slots.thaw();
        assert_eq!(
            (work.writes, work.copied_units, work.merged_entries),
            (2, 3, 1)
        );
        assert_eq!(slots.reader().base.as_ptr(), original);
        assert_eq!(slots[7], [9, 8, 3]);
    }
    #[test]
    fn retired_nodes_remain_in_the_snapshot_only_until_readers_join() {
        let mut nodes = Map::default();
        nodes.insert(7u32, vec![1u64, 2]);
        let snapshot = nodes.freeze();
        assert!(nodes.remove(&7));
        assert!(!nodes.remove(&7));
        assert!(nodes.get(&7).is_none());
        assert_eq!(snapshot[&7], [1, 2]);
        drop(snapshot);
        assert_eq!(nodes.thaw().merged_entries, 1);
        assert_eq!(nodes.len(), 0);
        nodes.insert(8, vec![3]);
        assert_eq!(nodes.get(&8).unwrap(), &[3]);
    }
}
