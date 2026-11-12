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
    pub(crate) fn canon(&self, value: &crate::value::Value) -> crate::value::Value {
        use crate::value::Value;
        match value {
            Value::Eq(id) => Value::Eq(self.root_counted(*id).0),
            Value::Set(values) => {
                let mut values = values.iter().map(|v| self.canon(v)).collect::<Vec<_>>();
                values.sort();
                values.dedup();
                Value::Set(values.into())
            }
            _ => value.clone(),
        }
    }
    #[cfg(test)]
    pub fn root(&self, id: u64) -> u64 {
        self.root_counted(id).0
    }
    /// Logical parent-directory probes, including the terminating lookup.
    /// An overlay probe can consult both the delta and the base map.
    pub fn root_counted(&self, mut id: u64) -> (u64, u64) {
        let mut probes = 0;
        loop {
            probes += 1;
            let Some(&to) = self
                .delta
                .and_then(|d| d.get(&id))
                .or_else(|| self.base.get(&id))
            else {
                break;
            };
            if to == id {
                break;
            }
            id = to;
        }
        (id, probes)
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

#[cfg(all(feature="storage-metrics",feature="sparse-cells"))]
impl Parents {
    pub(crate) fn storage_payload(&self)->serde_json::Value {
        let (local_map,local_bits)=self.local.storage_payload();
        let (base_map,base_bits)=self.base.as_ref().map_or((0,0),|b|b.storage_payload());
        serde_json::json!({"map_capacity_payload":local_map+base_map+self.delta.capacity()*std::mem::size_of::<(u64,u64)>(),
            "directory_bytes":local_bits+base_bits,"shared_base":self.base.is_some()})
    }
}
