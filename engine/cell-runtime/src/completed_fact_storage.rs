//! Completed facts inherit their source Cell's stage epoch. Only facts whose
//! lifecycle diverged carry an independent lifecycle record. Each row allocates
//! at most one exception until its containing owner is compacted or retired.
use crate::graph::fact_states::{OwnedFact,FactLifecycle};
use std::ops::Range;

const RETIRED:u32=u32::MAX;
#[derive(Clone,Copy)]
struct Row {op:u32, exception:u32, hash:u64}
#[derive(Default)]
pub(super) struct Facts {rows:Box<[Row]>, exceptions:Vec<FactLifecycle>}
pub(super) struct Builder {rows:Vec<Row>,exceptions:Vec<FactLifecycle>}
impl Builder {
    pub fn len(&self)->usize {self.rows.len()}
    pub fn push(&mut self,op:u32,state:Option<OwnedFact>,epoch:u64) {
        let Some(state)=state else {self.rows.push(Row{op,exception:RETIRED,hash:0});return;};
        let exception=if state.inherits(epoch) {0} else {
            self.exceptions.push(state.lifecycle());
            u32::try_from(self.exceptions.len()).expect("completed fact exceptions")
        };
        assert_ne!(exception,RETIRED);
        self.rows.push(Row{op,exception,hash:state.read().hash});
    }
    pub fn finish(mut self)->Facts {
        self.exceptions.shrink_to_fit();
        Facts{rows:self.rows.into_boxed_slice(),exceptions:self.exceptions}
    }
}
#[derive(Clone,Copy)]
pub(crate) struct View<'a> {facts:&'a Facts, start:usize, end:usize, epoch:u64}
impl<'a> View<'a> {
    pub fn into_iter(self)->impl Iterator<Item=(u32,OwnedFact)>+'a {
        (self.start..self.end).filter_map(move |i|Some((self.facts.rows[i].op,self.facts.read(i,self.epoch)?)))
    }
    pub fn get(&self,op:u32)->Option<OwnedFact> {
        let i=self.facts.rows[self.start..self.end].binary_search_by_key(&op,|r|r.op).ok()?+self.start;
        self.facts.read(i,self.epoch)
    }
    pub fn iter(&self)->impl Iterator<Item=(u32,OwnedFact)>+'_ {
        (self.start..self.end).filter_map(|i|Some((self.facts.rows[i].op,self.facts.read(i,self.epoch)?)))
    }
    #[cfg(test)]
    pub fn as_ptr(&self)->*const () {self.facts.rows[self.start..].as_ptr().cast()}
}
impl Facts {
    pub fn builder(capacity:usize)->Builder {Builder{rows:Vec::with_capacity(capacity),exceptions:Vec::new()}}
    #[cfg(test)]
    pub fn from_rows(rows:Vec<(u32,Option<OwnedFact>)>,epochs:impl Iterator<Item=u64>)->Self {
        let mut build=Self::builder(rows.len());let mut epochs=epochs;
        for (op,state) in rows {build.push(op,state,epochs.next().expect("completed fact stage layout"));}
        assert!(epochs.next().is_none(),"completed fact stage count");
        build.finish()
    }
    pub fn view(&self,range:Range<usize>,epoch:u64)->View<'_> {View{facts:self,start:range.start,end:range.end,epoch}}
    fn read(&self,i:usize,epoch:u64)->Option<OwnedFact> {
        let row=self.rows[i];
        if row.exception==RETIRED {return None;}
        Some(if row.exception==0 {OwnedFact::inherited(epoch,row.hash)} else {
            OwnedFact::from_lifecycle(self.exceptions[row.exception as usize-1],row.hash)
        })
    }
    pub fn take(&mut self,range:Range<usize>,epoch:u64,op:u32)->Option<OwnedFact> {
        let i=self.rows[range.clone()].binary_search_by_key(&op,|r|r.op).ok()?+range.start;
        self.take_at(i,epoch)
    }
    pub fn take_at(&mut self,i:usize,epoch:u64)->Option<OwnedFact> {
        let state=self.read(i,epoch)?;self.rows[i].exception=RETIRED;Some(state)
    }
    pub fn op(&self,i:usize)->u32 {self.rows[i].op}
    pub fn write(&mut self,range:Range<usize>,epoch:u64,op:u32,state:OwnedFact) {
        let i=self.rows[range.clone()].binary_search_by_key(&op,|r|r.op).expect("completed fact operation")+range.start;
        let row=&mut self.rows[i];assert_ne!(row.exception,RETIRED,"write retired completed fact");
        row.hash=state.read().hash;
        if row.exception!=0 {self.exceptions[row.exception as usize-1]=state.lifecycle();}
        else if !state.inherits(epoch) {
            self.exceptions.push(state.lifecycle());
            row.exception=u32::try_from(self.exceptions.len()).expect("completed fact exceptions");
            assert_ne!(row.exception,RETIRED);
        }
    }
    pub fn len(&self)->usize {self.rows.len()}
    pub fn live(&self)->usize {self.rows.iter().filter(|r|r.exception!=RETIRED).count()}
    pub fn inherited(&self)->usize {self.rows.iter().filter(|r|r.exception==0).count()}
    pub fn live_bytes(&self)->usize {
        self.rows.iter().filter(|r|r.exception!=RETIRED).map(|r|
            std::mem::size_of::<Row>()+if r.exception==0 {0} else {std::mem::size_of::<FactLifecycle>()}).sum()
    }
    pub fn bytes(&self)->usize {std::mem::size_of_val(self.rows.as_ref())+self.exceptions.capacity()*std::mem::size_of::<FactLifecycle>()}
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn common_stage_is_inherited_and_divergent_lifecycle_does_not_accumulate_history() {
        let mut facts=Facts::from_rows(vec![(2,Some(OwnedFact::inherited(7,41))),
            (5,Some(OwnedFact::inherited(7,53)))], [7,7].into_iter());
        assert_eq!(facts.inherited(),2);
        assert_eq!(facts.bytes(),32);
        let mut state=facts.view(0..2,7).get(2).unwrap().restore();
        state.hash=99;
        facts.write(0..2,7,2,OwnedFact::checked(&state).unwrap());
        assert_eq!(facts.bytes(),32,"hash writes do not need lifecycle exceptions");
        state.hidden=true;state.epoch=9;
        facts.write(0..2,7,2,OwnedFact::checked(&state).unwrap());
        let bytes=facts.bytes();
        for epoch in 10..110 {
            state.epoch=epoch;
            facts.write(0..2,7,2,OwnedFact::checked(&state).unwrap());
        }
        assert_eq!(facts.bytes(),bytes,"one exception per fact, not one per update");
        let read=facts.view(0..2,7).get(2).unwrap().read();
        assert_eq!((read.born,read.epoch,read.hidden,read.hash),(7,109,true,99));
        assert_eq!(facts.view(0..2,7).get(5).unwrap().read().epoch,7);
        facts.take(0..2,7,2).unwrap();
        assert!(facts.view(0..2,7).get(2).is_none());
        assert_eq!(facts.live(),1);
    }
    #[test]
    fn each_source_slice_keeps_its_own_stage_after_composition() {
        let facts=Facts::from_rows(vec![(0,Some(OwnedFact::inherited(3,1))),
            (0,Some(OwnedFact::inherited(12,2)))], [3,12].into_iter());
        assert_eq!(facts.inherited(),2);
        assert_eq!(facts.view(0..1,3).get(0).unwrap().read().born,3);
        assert_eq!(facts.view(1..2,12).get(0).unwrap().read().born,12);
    }
}
