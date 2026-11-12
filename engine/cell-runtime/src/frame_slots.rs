//! Keep published slots readable while a unique continuation appends results.
//! Sealing moves the original allocation; it never rebuilds the bindings.
use super::{ReadSlots, Slots};
use crate::value::Value;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::{
    collections::{BTreeMap, BTreeSet},
    ops::Index,
    sync::Arc,
};

#[derive(Clone, Debug, Default)]
pub struct FrameSlots {
    current: Slots,
    prefix: Option<Arc<FrameSlots>>,
    removed: Option<Box<BTreeSet<usize>>>,
}
impl From<Slots> for FrameSlots {
    fn from(current: Slots) -> Self {
        Self {
            current,
            ..Self::default()
        }
    }
}
impl FromIterator<(usize, Value)> for FrameSlots {
    fn from_iter<I: IntoIterator<Item = (usize, Value)>>(items: I) -> Self {
        Slots::from_iter(items).into()
    }
}
impl FrameSlots {
    #[cfg(feature="storage-metrics")]
    pub(crate) fn owned_slots(&self) -> Vec<usize> {
        if self.prefix.is_some() { return Vec::new(); }
        self.current.keys().copied().collect()
    }
    /// A shared prefix is not ours to invalidate. The unique owned array can
    /// hand equality slots to its composed instance without a copy or overlay.
    pub(crate) fn retain_owned(&mut self, keep: impl FnMut(&usize, &Value) -> bool) -> usize {
        if self.prefix.is_some() { return 0; }
        let before = self.current.len();
        self.current.retain(keep);
        before - self.current.len()
    }

    #[cfg(feature="storage-metrics")]
    pub(crate) fn compact_capacity(&mut self) {
        self.current.compact_capacity();
        if let Some(prefix)=self.prefix.as_mut().and_then(Arc::get_mut) {
            prefix.compact_capacity();
        }
    }

    #[cfg(feature = "storage-metrics")]
    pub(crate) fn storage_census(&self, seen: &mut BTreeSet<usize>) -> (usize,usize) {
        let mut bytes=self.current.capacity_bytes();
        let mut removals=self.removed.as_ref().map_or(0,|r|r.len());
        if let Some(prefix)=&self.prefix {
            if seen.insert(Arc::as_ptr(prefix) as usize) {
                bytes+=Self::seal_bytes();
                let (b,r)=prefix.storage_census(seen);bytes+=b;removals+=r;
            }
        }
        (bytes,removals)
    }

    pub(crate) fn seal_bytes() -> usize {
        std::mem::size_of::<Self>() + 2 * std::mem::size_of::<usize>()
    }
    pub fn get(&self, slot: &usize) -> Option<&Value> {
        let mut layer = self;
        loop {
            if let Some(value) = layer.current.get(slot) {
                return Some(value);
            }
            if layer.removed.as_ref().is_some_and(|r| r.contains(slot)) {
                return None;
            }
            layer = layer.prefix.as_deref()?;
        }
    }
    pub fn contains_key(&self, slot: &usize) -> bool {
        self.get(slot).is_some()
    }
    pub fn insert(&mut self, slot: usize, value: Value) -> Option<Value> {
        if self.prefix.is_none() {
            return self.current.insert(slot, value);
        }
        let old = self.get(&slot).cloned();
        if let Some(removed) = &mut self.removed {
            removed.remove(&slot);
        }
        self.current.insert(slot, value);
        old
    }
    pub fn remove(&mut self, slot: &usize) -> Option<Value> {
        if self.prefix.is_none() {
            return self.current.remove(slot);
        }
        let old = self.get(slot).cloned();
        self.current.remove(slot);
        if self.prefix.as_ref().is_some_and(|p| p.contains_key(slot)) {
            self.removed
                .get_or_insert_with(Default::default)
                .insert(*slot);
        }
        old
    }
    pub(crate) fn capacity_bytes(&self) -> usize {
        self.current.capacity_bytes() + self.prefix.as_ref().map_or(0, |p| p.capacity_bytes())
    }
    /// The caller retains this public prefix; the returned owner is its only
    /// writable suffix. Empty subsequent leases share the existing prefix.
    pub(crate) fn lease(&mut self) -> (Self, bool) {
        let sealed = !(self.current.is_empty() && self.removed.is_none() && self.prefix.is_some());
        if sealed {
            self.prefix = Some(Arc::new(std::mem::take(self)));
        }
        (
            Self {
                prefix: self.prefix.clone(),
                ..Self::default()
            },
            sealed,
        )
    }
    pub(crate) fn reattach(&mut self, owner: Self) -> Result<(), Self> {
        let same = match (&self.prefix, &owner.prefix) {
            (Some(a), Some(b)) => Arc::ptr_eq(a, b),
            _ => false,
        };
        if !same || !self.current.is_empty() || self.removed.is_some() {
            return Err(owner);
        }
        *self = owner;
        // Fresh implicit constructor results usually need no explicit slot
        // writes. Reclaim that unchanged allocation when its last reader joins.
        if self.current.is_empty() && self.removed.is_none() {
            match Arc::try_unwrap(self.prefix.take().unwrap()) {
                Ok(prefix) => *self = prefix,
                Err(prefix) => self.prefix = Some(prefix),
            }
        }
        Ok(())
    }
    /// Result-slot evaluators share immutable inputs; no existing binding is
    /// cloned and only the returned owner may append explicit result aliases.
    pub(crate) fn shared_suffix(&self) -> Self {
        assert!(self.current.is_empty() && self.removed.is_none() && self.prefix.is_some());
        Self { prefix:self.prefix.clone(), ..Self::default() }
    }
    // Checkpointing gathers references only. Normal operand reads never flatten
    // a frame, and source execution never reconstitutes its input vector.
    fn visible(&self) -> BTreeMap<&usize, &Value> {
        let mut result = self
            .prefix
            .as_ref()
            .map_or_else(BTreeMap::new, |p| p.visible());
        if let Some(removed) = &self.removed {
            for slot in removed.iter() {
                result.remove(slot);
            }
        }
        result.extend(self.current.iter());
        result
    }
    pub fn len(&self) -> usize {
        self.visible().len()
    }
    pub fn is_empty(&self) -> bool {
        if self.prefix.is_none() {
            self.current.is_empty()
        } else {
            self.visible().is_empty()
        }
    }
}
impl ReadSlots for FrameSlots {
    fn get(&self, slot: &usize) -> Option<&Value> {
        FrameSlots::get(self, slot)
    }
}
impl Index<&usize> for FrameSlots {
    type Output = Value;
    fn index(&self, slot: &usize) -> &Value {
        self.get(slot).expect("missing Cell slot")
    }
}
impl Serialize for FrameSlots {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        self.visible().serialize(s)
    }
}
impl<'de> Deserialize<'de> for FrameSlots {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        Slots::deserialize(d).map(Into::into)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[cfg(feature="storage-metrics")]
    fn compaction_preserves_shared_prefix_and_mutable_suffix() {
        let mut public:FrameSlots=[(0,Value::Int(7)),(3,Value::Int(8))].into_iter().collect();
        let pointer=public.get(&0).unwrap() as *const Value;
        let (mut owner,_)=public.lease();
        owner.insert(9,Value::Int(10));owner.remove(&3);
        public.compact_capacity();owner.compact_capacity();
        assert_eq!(public.get(&0).unwrap() as *const Value,pointer);
        assert_eq!(owner.get(&0).unwrap() as *const Value,pointer);
        assert_eq!(public.get(&3),Some(&Value::Int(8)));
        assert_eq!(owner.get(&3),None);
        public.reattach(owner).unwrap();public.compact_capacity();
        assert_eq!(public.get(&9),Some(&Value::Int(10)));
        assert_eq!(public.get(&3),None);
    }
    #[test]
    fn unique_suffixes_keep_the_original_allocation_and_published_prefix_readable() {
        let mut public: FrameSlots = [(0, Value::Int(7)), (3, Value::Int(8))]
            .into_iter()
            .collect();
        let pointer = public.get(&0).unwrap() as *const Value;
        let (mut owner, sealed) = public.lease();
        assert!(sealed);
        assert_eq!(public.get(&0).unwrap() as *const Value, pointer);
        assert_eq!(owner.get(&0).unwrap() as *const Value, pointer);
        std::thread::scope(|scope| {
            let worker = scope.spawn(|| {
                owner.insert(9, Value::Int(10));
            });
            assert_eq!(public.get(&3), Some(&Value::Int(8)));
            assert!(public.get(&9).is_none());
            worker.join().unwrap();
        });
        public.reattach(owner).unwrap();
        assert_eq!(public.get(&9), Some(&Value::Int(10)));
        assert_eq!(public.get(&0).unwrap() as *const Value, pointer);
        let (mut owner, sealed) = public.lease();
        assert!(sealed);
        owner.remove(&3);
        owner.insert(0, Value::Int(11));
        assert_eq!(public.get(&0), Some(&Value::Int(7)));
        public.reattach(owner).unwrap();
        assert_eq!(
            serde_json::to_string(&public).unwrap(),
            r#"{"0":{"Int":11},"9":{"Int":10}}"#
        );
        let (owner, sealed) = public.lease();
        assert!(sealed);
        public.reattach(owner).unwrap();
        let (owner, _) = public.lease();
        public.reattach(owner).unwrap();
    }
    #[test]
    fn a_foreign_or_modified_owner_cannot_replace_a_public_frame() {
        let mut a: FrameSlots = [(0, Value::Int(1))].into_iter().collect();
        let mut b: FrameSlots = [(0, Value::Int(2))].into_iter().collect();
        let (owner, _) = a.lease();
        let _ = b.lease();
        let owner = b.reattach(owner).unwrap_err();
        a.insert(1, Value::Int(3));
        assert!(a.reattach(owner).is_err());
    }
}
