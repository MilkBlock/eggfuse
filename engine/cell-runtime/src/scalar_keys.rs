//! Column types in a validated table make a single scalar a complete index
//! key. Other keys index only candidate IDs; exact equality reads the one
//! authoritative function row, so the index never owns a second key vector.
use super::*;
pub(super) struct FunctionKeys {
    scalar: Option<Kind>,
    words: HashMap<u64, usize>,
    other: HashMap<u64, crate::tiny_set::TinySet<usize>>,
    #[cfg(test)]
    hash_mask: u64,
}
#[derive(Clone, Copy)]
enum Kind {
    Eq,
    Int,
    Float,
}
impl FunctionKeys {
    pub fn new(t: &Table) -> Self {
        let scalar = if t.schema.len() == 2 {
            match t.schema[0]["kind"].as_str() {
                Some("eq") => Some(Kind::Eq),
                Some("i64") => Some(Kind::Int),
                Some("f64") => Some(Kind::Float),
                _ => None,
            }
        } else {
            None
        };
        Self {
            scalar,
            words: Default::default(),
            other: Default::default(),
            #[cfg(test)]
            hash_mask: u64::MAX,
        }
    }
    #[inline]
    fn word(&self, key: &[Value]) -> Option<u64> {
        match (self.scalar, key) {
            (Some(Kind::Eq), [Value::Eq(x)]) => Some(*x),
            (Some(Kind::Int), [Value::Int(x)]) | (Some(Kind::Float), [Value::Float(x)]) => {
                Some(*x as u64)
            }
            _ => None,
        }
    }
    fn hash(&self, key: &[Value]) -> u64 {
        let h = hashkey(0, key);
        #[cfg(test)]
        let h = h & self.hash_mask;
        h
    }
    #[inline]
    pub fn get(&self, key: &[Value], functions: &[Function]) -> Option<&usize> {
        match self.word(key) {
            Some(x) => self.words.get(&x),
            None => self
                .other
                .get(&self.hash(key))?
                .iter()
                .find(|&&i| functions.get(i).is_some_and(|f| f.live && f.key() == key)),
        }
    }
    pub fn insert(&mut self, key: &[Value], v: usize) {
        match self.word(key) {
            Some(x) => {
                self.words.insert(x, v);
            }
            None => {
                self.other.entry(self.hash(key)).or_default().insert(v);
            }
        }
    }
    pub fn remove(&mut self, key: &[Value], index: usize) {
        match self.word(key) {
            Some(x) => {
                if self.words.get(&x) == Some(&index) {
                    self.words.remove(&x);
                }
            }
            None => {
                let hash = self.hash(key);
                if let Some(bucket) = self.other.get_mut(&hash) {
                    bucket.remove(&index);
                    if bucket.is_empty() {
                        self.other.remove(&hash);
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn colliding_keys_read_authoritative_rows_and_remove_only_the_selected_id() {
        let mut index = FunctionKeys {
            scalar: None,
            words: Default::default(),
            other: Default::default(),
            hash_mask: 0,
        };
        let row = |key: Vec<Value>| {
            serde_json::from_value::<Function>(json!({
                "table":0,"key":key,"value":Value::Int(1),"epoch":0,"live":true
            }))
            .unwrap()
        };
        let a = vec![Value::Eq(7), Value::Int(3)];
        let b = vec![Value::Eq(8), Value::Int(3)];
        let mut rows = vec![row(a.clone()), row(b.clone())];
        index.insert(&a, 0);
        index.insert(&b, 1);
        assert_eq!(index.other.len(), 1, "force a real hash collision");
        assert_eq!(index.get(&a, &rows), Some(&0));
        assert_eq!(index.get(&b, &rows), Some(&1));
        assert_eq!(index.get(&[Value::Eq(9), Value::Int(3)], &rows), None);
        // Repair removes the old incidence before replacing the stored row.
        index.remove(&a, 0);
        rows[0].set_fields(Graph::shared_fields(&b, &Value::Int(2)));
        assert_eq!(index.get(&a, &rows), None);
        assert_eq!(index.get(&b, &rows), Some(&1));
        // A retired row cannot become a candidate through a colliding key.
        rows[1].live = false;
        assert_eq!(index.get(&b, &rows), None);
        index.remove(&b, 1);
        index.insert(&b, 0);
        assert_eq!(index.get(&b, &rows), Some(&0));
        assert_eq!(index.other.len(), 1);
    }
}

#[cfg(feature = "storage-metrics")]
impl FunctionKeys {
    pub(super) fn storage_payload(&self) -> usize {
        self.words.capacity() * std::mem::size_of::<(u64, usize)>()
            + self.other.capacity() * std::mem::size_of::<(u64, crate::tiny_set::TinySet<usize>)>()
    }
}
