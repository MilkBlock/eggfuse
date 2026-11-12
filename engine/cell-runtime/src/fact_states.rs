//! Stable fact identity is independent of the backing Cell record. This is the
//! sole point lookup/mutation boundary; it owns no second index or fact copy.
use super::{FactRef,FactState};
#[cfg(not(feature="sparse-cells"))]
use super::Cell;
pub(crate) trait FactStates {
    fn fact_state(&self, fact:FactRef)->Option<&FactState>;
    fn fact_state_mut(&mut self, fact:FactRef)->Option<&mut FactState>;
    fn remove_fact_state(&mut self, fact:FactRef)->Option<FactState>;
    fn insert_fact_state(&mut self, fact:FactRef, state:FactState)->Option<FactState>;
    fn fact_count(&self, cell:u32)->Option<usize>;
    fn fact_states(&self, cell:u32)->impl Iterator<Item=(FactRef,&FactState)>;
}
#[cfg(feature="sparse-cells")]
impl FactStates for super::arena::Cells {
    #[inline]
    fn fact_state(&self, f:FactRef)->Option<&FactState> {self.get(&f.cell)?.facts.get(&f.op)}
    #[inline]
    fn fact_state_mut(&mut self, f:FactRef)->Option<&mut FactState> {self.get_mut(&f.cell)?.facts.get_mut(&f.op)}
    fn remove_fact_state(&mut self, f:FactRef)->Option<FactState> {self.get_mut(&f.cell)?.facts.remove(&f.op)}
    fn insert_fact_state(&mut self, f:FactRef, state:FactState)->Option<FactState> {
        let facts=&mut self.get_mut(&f.cell).expect("registered fact owner").facts;
        #[cfg(feature="sparse-cells")]
        facts.reserve_first();
        facts.insert(f.op,state)
    }
    fn fact_count(&self, cell:u32)->Option<usize> {Some(self.get(&cell)?.facts.len())}
    fn fact_states(&self, cell:u32)->impl Iterator<Item=(FactRef,&FactState)> {
        self.get(&cell).into_iter().flat_map(move |c|c.facts.iter().map(move |(&op,s)|(FactRef{cell,op},s)))
    }
}
#[cfg(not(feature="sparse-cells"))]
impl FactStates for rustc_hash::FxHashMap<u32,Cell> {
    #[inline]
    fn fact_state(&self, f:FactRef)->Option<&FactState> {self.get(&f.cell)?.facts.get(&f.op)}
    #[inline]
    fn fact_state_mut(&mut self, f:FactRef)->Option<&mut FactState> {self.get_mut(&f.cell)?.facts.get_mut(&f.op)}
    fn remove_fact_state(&mut self, f:FactRef)->Option<FactState> {self.get_mut(&f.cell)?.facts.remove(&f.op)}
    fn insert_fact_state(&mut self, f:FactRef, state:FactState)->Option<FactState> {
        let facts=&mut self.get_mut(&f.cell).expect("registered fact owner").facts;
        #[cfg(feature="sparse-cells")]
        facts.reserve_first();
        facts.insert(f.op,state)
    }
    fn fact_count(&self, cell:u32)->Option<usize> {Some(self.get(&cell)?.facts.len())}
    fn fact_states(&self, cell:u32)->impl Iterator<Item=(FactRef,&FactState)> {
        self.get(&cell).into_iter().flat_map(move |c|c.facts.iter().map(move |(&op,s)|(FactRef{cell,op},s)))
    }
}

#[cfg(all(test,feature="sparse-cells"))]
mod tests {
    use super::*;
    fn cell()->super::super::Cell {
        super::super::Cell {symbolic_slots:false,completed_prefix:0,started_epoch:3,completed:true,
            template:0,parent:None,values:Default::default(),facts:Default::default(),recipe_depth:0}
    }
    fn state(epoch:u64)->FactState {
        FactState {owned:false,local_union_owned:false,
            #[cfg(feature="receipt-slots")] port_slot:0,
            decoded:None,entry:None,hidden:false,epoch,born:epoch,hash:9}
    }
    #[test]
    fn stable_fact_access_survives_owner_relocation_and_retirement() {
        let mut cells=super::super::arena::Cells::default();
        cells.insert(10,cell());cells.insert(20,cell());
        let f=FactRef{cell:20,op:7};
        assert!(cells.insert_fact_state(f,state(3)).is_none());
        cells.remove(&10); // Dense relocation must not change logical facts.
        assert_eq!(cells.fact_state(f).unwrap().born,3);
        cells.fact_state_mut(f).unwrap().hidden=true;
        cells.fact_state_mut(f).unwrap().epoch=5;
        assert_eq!(cells.fact_states(20).map(|(id,s)|(id,s.hidden,s.epoch)).collect::<Vec<_>>(),vec![(f,true,5)]);
        assert_eq!(cells.fact_count(20),Some(1));
        assert_eq!(cells.remove_fact_state(f).unwrap().born,3);
        assert_eq!(cells.fact_count(20),Some(0));
        assert!(cells.fact_state(f).is_none());
        cells.remove(&20);
        assert_eq!(cells.fact_count(20),None);
        assert!(cells.fact_states(20).next().is_none());
    }
}
