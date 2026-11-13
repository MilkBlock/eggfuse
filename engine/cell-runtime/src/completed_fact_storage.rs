//! Completed facts inherit their source Cell's stage epoch. Only facts whose
//! lifecycle diverged carry an independent lifecycle record. Each row allocates
//! at most one exception until its containing owner is compacted or retired.
use crate::graph::fact_states::{OwnedFact,FactLifecycle};

const RETIRED:u32=u32::MAX;
// An empty hash array represents all zero hashes. Port-domain-only facts no
// longer own a hash index; mixed owners retain the ordinary dense array.
#[derive(Default)]
pub(super) struct Facts {hashes:Box<[u64]>, states:Box<[u32]>, exceptions:Vec<FactLifecycle>}
pub(super) struct Builder {hashes:Vec<u64>,states:Vec<u32>,exceptions:Vec<FactLifecycle>}
impl Builder {
    pub fn len(&self)->usize {self.states.len()}
    pub fn push(&mut self,state:Option<OwnedFact>,epoch:u64) {
        let Some(state)=state else {if !self.hashes.is_empty() {self.hashes.push(0);}
            self.states.push(RETIRED);return;};
        let exception=if state.inherits(epoch) {0} else {
            self.exceptions.push(state.lifecycle());
            u32::try_from(self.exceptions.len()).expect("completed fact exceptions")
        };
        assert_ne!(exception,RETIRED);
        let hash=state.read().hash;
        if hash!=0 && self.hashes.is_empty() {
            self.hashes.reserve_exact(self.states.capacity());
            self.hashes.resize(self.states.len(),0);
        }
        if hash!=0 || !self.hashes.is_empty() {self.hashes.push(hash);}
        self.states.push(exception);
    }
    pub fn finish(mut self)->Facts {
        self.exceptions.shrink_to_fit();
        let hashes=self.hashes.into_boxed_slice();
        Facts{hashes,states:self.states.into_boxed_slice(),exceptions:self.exceptions}
    }
}
#[derive(Clone,Copy)]
pub(crate) struct View<'a> {facts:&'a Facts, start:usize, ops:&'a [u32], epoch:u64}
impl<'a> View<'a> {
    pub fn into_iter(self)->impl Iterator<Item=(u32,OwnedFact)>+'a {
        self.ops.iter().enumerate().filter_map(move |(i,op)|Some((*op,self.facts.read(self.start+i,self.epoch)?)))
    }
    pub fn get(&self,op:u32)->Option<OwnedFact> {
        self.facts.read(self.start+self.ops.binary_search(&op).ok()?,self.epoch)
    }
    pub fn iter(&self)->impl Iterator<Item=(u32,OwnedFact)>+'_ {(*self).into_iter()}
    #[cfg(test)]
    pub fn as_ptr(&self)->*const () {self.facts.states[self.start..].as_ptr().cast()}
}
impl Facts {
    pub fn builder(capacity:usize)->Builder {Builder{hashes:Vec::new(),states:Vec::with_capacity(capacity),exceptions:Vec::new()}}
    #[cfg(test)]
    pub fn from_rows(rows:Vec<(u32,Option<OwnedFact>)>,epochs:impl Iterator<Item=u64>)->Self {
        let mut build=Self::builder(rows.len());let mut epochs=epochs;
        for (_,state) in rows {build.push(state,epochs.next().expect("completed fact stage layout"));}
        assert!(epochs.next().is_none(),"completed fact stage count");
        build.finish()
    }
    pub fn view<'a>(&'a self,start:usize,ops:&'a [u32],epoch:u64)->View<'a> {View{facts:self,start,ops,epoch}}
    fn read(&self,i:usize,epoch:u64)->Option<OwnedFact> {
        let state=self.states[i];let hash=self.hashes.get(i).copied().unwrap_or(0);
        if state==RETIRED {return None;}
        Some(if state==0 {OwnedFact::inherited(epoch,hash)} else {
            OwnedFact::from_lifecycle(self.exceptions[state as usize-1],hash)
        })
    }
    pub fn take(&mut self,start:usize,ops:&[u32],epoch:u64,op:u32)->Option<OwnedFact> {
        self.take_at(start+ops.binary_search(&op).ok()?,epoch)
    }
    pub fn take_at(&mut self,i:usize,epoch:u64)->Option<OwnedFact> {
        let state=self.read(i,epoch)?;self.states[i]=RETIRED;Some(state)
    }
    pub fn write(&mut self,start:usize,ops:&[u32],epoch:u64,op:u32,state:OwnedFact) {
        let i=start+ops.binary_search(&op).expect("completed fact operation");
        assert_ne!(self.states[i],RETIRED,"write retired completed fact");
        let hash=state.read().hash;
        if self.hashes.is_empty() && hash!=0 {self.hashes=vec![0;self.states.len()].into_boxed_slice();}
        if !self.hashes.is_empty() {self.hashes[i]=hash;}
        let entry=&mut self.states[i];
        if *entry!=0 {self.exceptions[*entry as usize-1]=state.lifecycle();}
        else if !state.inherits(epoch) {
            self.exceptions.push(state.lifecycle());
            *entry=u32::try_from(self.exceptions.len()).expect("completed fact exceptions");
            assert_ne!(*entry,RETIRED);
        }
    }
    pub fn len(&self)->usize {self.states.len()}
    pub fn live(&self)->usize {self.states.iter().filter(|&&s|s!=RETIRED).count()}
    pub fn inherited(&self)->usize {self.states.iter().filter(|&&s|s==0).count()}
    pub fn live_bytes(&self)->usize {
        self.states.iter().filter(|&&s|s!=RETIRED).map(|&s|
            (4+if self.hashes.is_empty() {0} else {8})+if s==0 {0} else {std::mem::size_of::<FactLifecycle>()}).sum()
    }
    pub fn hash_bytes(&self)->usize {std::mem::size_of_val(self.hashes.as_ref())}
    pub fn bytes(&self)->usize {std::mem::size_of_val(self.hashes.as_ref())+std::mem::size_of_val(self.states.as_ref())+self.exceptions.capacity()*std::mem::size_of::<FactLifecycle>()}
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mixed_owner_preserves_zero_prefix_and_retired_positions() {
        let facts=Facts::from_rows(vec![(0,Some(OwnedFact::inherited(7,0))),
            (1,None),(2,Some(OwnedFact::inherited(7,91)))],[7,7,7].into_iter());
        assert_eq!(facts.len(),3);assert_eq!(facts.hash_bytes(),24);
        assert_eq!(facts.view(0,&[0,1,2],7).get(0).unwrap().read().hash,0);
        assert!(facts.view(0,&[0,1,2],7).get(1).is_none());
        assert_eq!(facts.view(0,&[0,1,2],7).get(2).unwrap().read().hash,91);
    }
    #[test]
    fn zero_hash_owners_need_no_hash_array_and_restore_nonzero_writes() {
        let mut facts=Facts::from_rows(vec![(2,Some(OwnedFact::inherited(7,0))),
            (5,Some(OwnedFact::inherited(7,0)))],[7,7].into_iter());
        assert_eq!(facts.len(),2);assert_eq!(facts.bytes(),8);assert_eq!(facts.hash_bytes(),0);
        assert_eq!(facts.live_bytes(),8);
        let mut state=facts.view(0,&[2,5],7).get(2).unwrap().restore();
        state.hidden=true;
        facts.write(0,&[2,5],7,2,OwnedFact::checked(&state).unwrap());
        assert_eq!(facts.hash_bytes(),0,"lifecycle changes do not restore unused hashes");
        state.hash=99;
        facts.write(0,&[2,5],7,2,OwnedFact::checked(&state).unwrap());
        assert_eq!(facts.hash_bytes(),16);
        assert_eq!(facts.view(0,&[2,5],7).get(2).unwrap().read().hash,99);
        assert_eq!(facts.view(0,&[2,5],7).get(5).unwrap().read().hash,0);
        assert!(facts.take(0,&[2,5],7,2).is_some());
        assert_eq!(facts.live(),1);
    }
    #[test]
    fn common_stage_is_inherited_and_divergent_lifecycle_does_not_accumulate_history() {
        let mut facts=Facts::from_rows(vec![(2,Some(OwnedFact::inherited(7,41))),
            (5,Some(OwnedFact::inherited(7,53)))], [7,7].into_iter());
        assert_eq!(facts.inherited(),2);
        assert_eq!(facts.bytes(),24);
        let mut state=facts.view(0,&[2,5],7).get(2).unwrap().restore();
        state.hash=99;
        facts.write(0,&[2,5],7,2,OwnedFact::checked(&state).unwrap());
        assert_eq!(facts.bytes(),24,"hash writes do not need lifecycle exceptions");
        state.hidden=true;state.epoch=9;
        facts.write(0,&[2,5],7,2,OwnedFact::checked(&state).unwrap());
        let bytes=facts.bytes();
        for epoch in 10..110 {
            state.epoch=epoch;
            facts.write(0,&[2,5],7,2,OwnedFact::checked(&state).unwrap());
        }
        assert_eq!(facts.bytes(),bytes,"one exception per fact, not one per update");
        let read=facts.view(0,&[2,5],7).get(2).unwrap().read();
        assert_eq!((read.born,read.epoch,read.hidden,read.hash),(7,109,true,99));
        assert_eq!(facts.view(0,&[2,5],7).get(5).unwrap().read().epoch,7);
        facts.take(0,&[2,5],7,2).unwrap();
        assert!(facts.view(0,&[2,5],7).get(2).is_none());
        assert_eq!(facts.live(),1);
    }
    #[test]
    fn each_source_slice_keeps_its_own_stage_after_composition() {
        let facts=Facts::from_rows(vec![(0,Some(OwnedFact::inherited(3,1))),
            (0,Some(OwnedFact::inherited(12,2)))], [3,12].into_iter());
        assert_eq!(facts.inherited(),2);
        assert_eq!(facts.view(0,&[0],3).get(0).unwrap().read().born,3);
        assert_eq!(facts.view(1,&[0],12).get(0).unwrap().read().born,12);
    }
}
