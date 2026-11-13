//! Column types in a validated table make a single scalar a complete index
//! key. Other keys index only candidate IDs; exact equality reads the one
//! authoritative function row, so the index never owns a second key vector.
use super::*;
pub(super) struct FunctionKeys {
    scalar: Option<Kind>,
    words: HashMap<u64, usize>,
    other: HashMap<u64, crate::tiny_set::TinySet<usize>>,
    #[cfg(test)]
    pub(super) hash_mask: u64,
}
#[derive(Clone, Copy)]
enum Kind {
    Eq,
    Int,
    Float,
    Held,
}
impl FunctionKeys {
    /// Move the actual directory into a terminal Cell owner. Any unproved
    /// keyed access during adoption must fail, rather than see an empty table.
    pub fn take_owner(&mut self)->Self {
        assert!(!matches!(self.scalar,Some(Kind::Held)),"nested Unit table owner");
        std::mem::replace(self,Self {scalar:Some(Kind::Held),words:Default::default(),other:Default::default(),
            #[cfg(test)] hash_mask:u64::MAX})
    }
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
            (Some(Kind::Held),_)=>panic!("Unit directory is held by its terminal Cell owner"),
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
        self.get_if(key, |i| functions.get(i).is_some_and(|f| f.live && f.key() == key))
    }
    /// Read the compiler's operand projection directly from the same Cell.
    /// Missing slots reject preparation; neither a digest nor a partial key
    /// can establish equality. Hash and exact comparison borrow the values.
    pub(crate) fn get_projected<'a>(&self, len: usize,
        field: impl Fn(usize)->Option<&'a Value>, functions: &[Function]) -> std::result::Result<Option<&usize>, ()> {
        let scalar = if len == 1 { self.word(std::slice::from_ref(field(0).ok_or(())?)) }
            else { self.word(&[]) };
        if let Some(word) = scalar { return Ok(self.words.get(&word)); }
        // Match hashkey(0, slice): table, slice length, then Value::hash for
        // each field. Insert/remove keep their existing authoritative keys.
        let mut hash = rustc_hash::FxHasher::default();
        0usize.hash(&mut hash);
        len.hash(&mut hash);
        for i in 0..len { field(i).ok_or(())?.hash(&mut hash); }
        let hash = hash.finish();
        #[cfg(test)]
        let hash = hash & self.hash_mask;
        Ok(self.other.get(&hash).and_then(|bucket|bucket.iter().find(|&&i|
            functions.get(i).is_some_and(|row|row.live && row.key().len()==len
                && row.key().iter().enumerate().all(|(i,v)|Some(v)==field(i))))))
    }
    /// Terminal owners pin only relevant immutable rows. Exact comparison
    /// still belongs to the worker, including rows it has just registered.
    pub(super) fn get_if(&self, key: &[Value], mut matches: impl FnMut(usize)->bool) -> Option<&usize> {
        match self.word(key) {
            Some(x) => self.words.get(&x),
            None => self
                .other
                .get(&self.hash(key))?
                .iter()
                .find(|&&i| matches(i)),
        }
    }
    pub(super) fn candidates(&self, key:&[Value])->Option<&crate::tiny_set::TinySet<usize>> {
        if self.word(key).is_some() {None} else {self.other.get(&self.hash(key))}
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
    fn projected_keys_match_inserted_slice_keys_including_collisions_and_missing_slots() {
        let keys = vec![vec![], vec![Value::Eq(7)], vec![Value::Int(-3)],
            vec![Value::Float(f64::NAN.to_bits() as i64)], vec![Value::Text("long text".to_string().into())],
            vec![Value::Set(vec![Value::Eq(7),Value::Int(3)].into())],
            (0..17).map(|i|if i%2==0 {Value::Eq(i)} else {Value::Int(-(i as i64))}).collect()];
        let mut rows:Vec<Function> = keys.iter().map(|key|serde_json::from_value(json!({
            "table":0,"key":key,"value":Value::Int(0),"epoch":0,"live":true
        })).unwrap()).collect();
        for kind in [None,Some(Kind::Eq),Some(Kind::Int),Some(Kind::Float)] {
            for mask in [u64::MAX,0] {
                let mut index=FunctionKeys {scalar:kind,words:Default::default(),other:Default::default(),hash_mask:mask};
                for (i,key) in keys.iter().enumerate() {index.insert(key,i);}
                for (i,key) in keys.iter().enumerate() {
                    // The projection need not use contiguous or ascending slots.
                    let slots=key.iter().rev().cloned().collect::<Vec<_>>();
                    assert_eq!(index.get_projected(key.len(),|col|slots.get(key.len()-1-col),&rows),Ok(Some(&i)));
                    assert_eq!(index.get_projected(key.len()+1,|col|key.get(col),&rows),Err(()));
                }
                assert_eq!(index.get_projected(2,|_|Some(&Value::Int(99)),&rows),Ok(None));
                index.remove(&keys[6],6);
                assert_eq!(index.get_projected(keys[6].len(),|col|keys[6].get(col),&rows),Ok(None));
                rows[6].live=false;
                index.insert(&keys[6],6);
                assert_eq!(index.get_projected(keys[6].len(),|col|keys[6].get(col),&rows),Ok(None));
                rows[6].live=true;
            }
        }
    }
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
