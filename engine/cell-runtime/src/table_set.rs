//! Immutable ordered table obligations. Dense sorted sets iterate bitmap bits
//! directly; sparse and non-set sequences retain their exact source order.
use std::rc::Rc;
use serde::{Serialize, Serializer};

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
enum Repr { Sparse(Box<[usize]>), Dense(Box<[u64]>) }
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
struct Data { len: usize, repr: Repr }
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub struct TableSet(Rc<Data>);
impl Default for TableSet { fn default() -> Self { Vec::new().into() } }
impl From<Vec<usize>> for TableSet {
    fn from(values: Vec<usize>) -> Self {
        let len = values.len();
        let words = values.last().and_then(|v| v.checked_div(64)?.checked_add(1));
        let dense = words.filter(|w| w.checked_mul(8).is_some_and(|bytes|
            bytes < len.saturating_mul(std::mem::size_of::<usize>())))
            .filter(|_| values.windows(2).all(|w|w[0]<w[1]));
        let repr = if let Some(words) = dense {
            let mut bits = vec![0u64; words];
            for value in values { bits[value/64] |= 1 << (value%64); }
            Repr::Dense(bits.into_boxed_slice())
        } else { Repr::Sparse(values.into_boxed_slice()) };
        Self(Rc::new(Data { len, repr }))
    }
}
impl From<&[usize]> for TableSet { fn from(v: &[usize]) -> Self { v.to_vec().into() } }
impl FromIterator<usize> for TableSet {
    fn from_iter<T: IntoIterator<Item=usize>>(iter:T)->Self { iter.into_iter().collect::<Vec<_>>().into() }
}
impl TableSet {
    pub fn len(&self)->usize { self.0.len }
    pub fn is_empty(&self)->bool { self.len()==0 }
    pub fn ptr_eq(&self, other:&Self)->bool { Rc::ptr_eq(&self.0,&other.0) }
    pub fn as_ptr(&self)->*const () { Rc::as_ptr(&self.0).cast() }
    pub fn contains(&self, value:&usize)->bool { match &self.0.repr {
        Repr::Sparse(values)=>values.contains(value),
        Repr::Dense(words)=>words.get(value/64).is_some_and(|w|w & (1 << (value%64)) != 0),
    } }
    pub fn iter(&self)->Iter<'_> { match &self.0.repr {
        Repr::Sparse(values)=>Iter::Sparse(values.iter()),
        Repr::Dense(words)=>Iter::Dense { words, index:0, bits:words.first().copied().unwrap_or(0) },
    } }
    pub fn to_vec(&self)->Vec<usize> { self.iter().collect() }
    pub fn owner_bytes()->usize { std::mem::size_of::<Data>()+2*std::mem::size_of::<usize>() }
    pub fn storage_bytes(&self)->usize { Self::owner_bytes()+match &self.0.repr {
        Repr::Sparse(v)=>std::mem::size_of_val(v.as_ref()),
        Repr::Dense(v)=>std::mem::size_of_val(v.as_ref()),
    } }
}
impl Serialize for TableSet {
    fn serialize<S:Serializer>(&self,s:S)->Result<S::Ok,S::Error> { s.collect_seq(self.iter()) }
}
#[derive(Clone)]
pub enum Iter<'a> {
    Sparse(std::slice::Iter<'a,usize>),
    Dense { words:&'a [u64], index:usize, bits:u64 },
}
impl Iterator for Iter<'_> {
    type Item=usize;
    fn next(&mut self)->Option<usize> { match self {
        Self::Sparse(v)=>v.next().copied(),
        Self::Dense{words,index,bits}=>loop {
            if *bits!=0 { let bit=bits.trailing_zeros() as usize; *bits &= *bits-1; return Some(*index*64+bit); }
            if *index>=words.len() { return None; }
            *index+=1; *bits=*words.get(*index)?;
        }
    } }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_iteration_membership_and_wire_for_sparse_dense_and_sequences() {
        for values in [vec![],vec![usize::MAX],vec![4,1,4],vec![0,63,64,129],(0..401).filter(|x|x%3!=0).collect()] {
            let set=TableSet::from(values.clone());
            assert_eq!(set.to_vec(),values);
            assert_eq!(serde_json::to_value(&set).unwrap(),serde_json::to_value(&values).unwrap());
            for value in (0..450).chain([usize::MAX]) { assert_eq!(set.contains(&value),values.contains(&value)); }
            let clone=set.clone(); assert!(clone.ptr_eq(&set)); drop(set); assert_eq!(clone.to_vec(),values);
        }
    }
    #[test]
    fn dense_iterator_crosses_empty_words_and_is_repeatable() {
        let values:Vec<_>=(0..64).chain(256..320).collect();
        let set=TableSet::from(values.clone());
        assert!(matches!(set.0.repr,Repr::Dense(_)));
        let mut it=set.iter();assert_eq!(it.next(),Some(0));
        assert_eq!(it.clone().collect::<Vec<_>>(),values[1..]);
        assert_eq!(set.to_vec(),values);
    }
}
