//! A completed Cell owner supplies representation invariants. Only mutable
//! lifecycle data remains per fact; exceptional writes restore an ordinary Cell.
use super::{FactRef,FactState};
use crate::graph::RowFields;

#[derive(Clone,Copy)]
pub(crate) struct FactRead<'a> {
    pub owned:bool,
    pub local_union_owned:bool,
    #[cfg(feature="receipt-slots")]
    pub port_slot:u32,
    pub decoded:Option<&'a (usize,RowFields)>,
    pub entry:Option<FactRef>,
    pub hidden:bool,
    pub epoch:u64,
    pub born:u64,
    pub hash:u64,
}
impl<'a> From<&'a FactState> for FactRead<'a> {
    fn from(s:&'a FactState)->Self {Self{owned:s.owned,local_union_owned:s.local_union_owned,
        #[cfg(feature="receipt-slots")] port_slot:s.port_slot,
        decoded:s.decoded.as_ref(),entry:s.entry,hidden:s.hidden,epoch:s.epoch,born:s.born,hash:s.hash}}
}
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
#[derive(Clone,Copy)]
pub(crate) struct OwnedFact {
    epoch:u64,
    born:u64,
    hash:u64,
    hidden:bool,
}
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
impl OwnedFact {
    pub fn checked(s:&FactState)->Option<Self> {
        if !s.owned || s.local_union_owned || s.decoded.is_some() || s.entry.is_some() {return None;}
        #[cfg(feature="receipt-slots")]
        if s.port_slot!=0 {return None;}
        Some(Self{epoch:s.epoch,born:s.born,hash:s.hash,hidden:s.hidden})
    }
    pub fn read(&self)->FactRead<'static> {FactRead{owned:true,local_union_owned:false,
        #[cfg(feature="receipt-slots")] port_slot:0,
        decoded:None,entry:None,hidden:self.hidden,epoch:self.epoch,born:self.born,hash:self.hash}}
    pub fn restore(self)->FactState {FactState{owned:true,local_union_owned:false,
        #[cfg(feature="receipt-slots")] port_slot:0,
        decoded:None,entry:None,hidden:self.hidden,epoch:self.epoch,born:self.born,hash:self.hash}}
}

pub(crate) enum FactWrite<'a> {
    Ordinary(&'a mut FactState),
    #[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
    Owned {cells:&'a mut crate::graph::arena::Cells,fact:FactRef,state:Option<FactState>},
}
impl std::ops::Deref for FactWrite<'_> {
    type Target=FactState;
    fn deref(&self)->&FactState {match self {Self::Ordinary(s)=>s,
        #[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
        Self::Owned{state,..}=>state.as_ref().unwrap()}}
}
impl std::ops::DerefMut for FactWrite<'_> {
    fn deref_mut(&mut self)->&mut FactState {match self {Self::Ordinary(s)=>s,
        #[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
        Self::Owned{state,..}=>state.as_mut().unwrap()}}
}
impl Drop for FactWrite<'_> {
    fn drop(&mut self) {
        #[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
        if let Self::Owned{cells,fact,state}=self {cells.write_completed_fact(*fact,state.take().unwrap());}
    }
}
