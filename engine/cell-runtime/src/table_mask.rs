//! Packed immutable scope membership. Keep boolean wire format and exact width;
//! repair consumers borrow either this mask or their existing mutable flags.
use serde::{Serialize, Serializer, ser::SerializeSeq};
use std::ops::Index;

#[derive(Clone, Debug)]
pub(crate) struct Mask {
    words: Box<[u64]>,
    len: usize,
}
impl Mask {
    pub(crate) fn len(&self) -> usize { self.len }
    pub(crate) fn payload_bytes(&self) -> usize { std::mem::size_of_val(self.words.as_ref()) }
}
impl FromIterator<bool> for Mask {
    fn from_iter<T: IntoIterator<Item=bool>>(values: T) -> Self {
        let values=values.into_iter();
        let mut words=Vec::with_capacity(values.size_hint().0.div_ceil(64));
        let mut len=0;
        for value in values {
            if len%64==0 { words.push(0u64); }
            if value { words[len/64] |= 1<<(len%64); }
            len+=1;
        }
        Self { words:words.into_boxed_slice(), len }
    }
}
impl Index<usize> for Mask {
    type Output=bool;
    fn index(&self, table: usize) -> &bool {
        assert!(table<self.len, "scope table outside exact mask width");
        if self.words[table/64] & (1<<(table%64)) != 0 { &true } else { &false }
    }
}
impl Serialize for Mask {
    fn serialize<S: Serializer>(&self, serializer:S) -> Result<S::Ok,S::Error> {
        let mut seq=serializer.serialize_seq(Some(self.len))?;
        for table in 0..self.len { seq.serialize_element(&self[table])?; }
        seq.end()
    }
}

#[derive(Clone, Copy)]
pub(crate) enum Selection<'a> {
    Flags(&'a [bool]),
    Packed(&'a Mask),
}
impl Index<usize> for Selection<'_> {
    type Output=bool;
    fn index(&self, table:usize)->&bool {
        match self { Self::Flags(flags)=>&flags[table], Self::Packed(mask)=>&mask[table] }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn packed_selection_matches_flags_and_preserves_wire_width() {
        for width in [0usize,1,63,64,65,127,128,129,401] {
            for pattern in 0..3 {
                let flags:Vec<_>=(0..width).map(|i| match pattern {0=>false,1=>true,_=>i%3==0}).collect();
                let mask:Mask=flags.iter().copied().collect();
                assert_eq!(mask.len(),width);
                assert_eq!(mask.payload_bytes(),width.div_ceil(64)*8);
                let clone=mask.clone();drop(mask);
                for i in 0..width { assert_eq!(Selection::Flags(&flags)[i],Selection::Packed(&clone)[i]); }
                assert_eq!(serde_json::to_value(&clone).unwrap(),serde_json::to_value(flags).unwrap());
                if width%64!=0 { assert_eq!(clone.words.last().unwrap()>>(width%64),0); }
            }
        }
    }
    #[test]
    #[should_panic(expected="scope table outside exact mask width")]
    fn padding_is_not_an_extra_table() {
        let mask:Mask=[true].into_iter().collect();
        let _=mask[1];
    }
}
