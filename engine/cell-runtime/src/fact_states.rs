//! Stable fact identity is independent of the backing Cell record. This is the
//! sole point lookup/mutation boundary; it owns no second index or fact copy.
use super::{FactRef,FactState};
#[path="owned_fact_state.rs"]
mod owned;
pub(crate) use owned::{FactRead,FactWrite};
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
pub(crate) use owned::OwnedFact;
#[cfg(not(feature="sparse-cells"))]
use super::Cell;
pub(crate) trait FactStates {
    fn cell_metadata(&self,cell:u32)->Option<super::CellMetadata>;
    fn fact_state(&self, fact:FactRef)->Option<FactRead<'_>>;
    fn fact_state_mut(&mut self, fact:FactRef)->Option<FactWrite<'_>>;
    fn remove_fact_state(&mut self, fact:FactRef)->Option<FactState>;
    fn insert_fact_state(&mut self, fact:FactRef, state:FactState)->Option<FactState>;
    fn fact_count(&self, cell:u32)->Option<usize>;
    fn fact_states(&self, cell:u32)->impl Iterator<Item=(FactRef,FactRead<'_>)>;
    fn cell_ids(&self)->impl Iterator<Item=u32>;
}
#[cfg(feature="sparse-cells")]
impl FactStates for super::arena::Cells {
    fn cell_ids(&self)->impl Iterator<Item=u32> {
        let active=self.iter().map(|(&id,_)|id);
        #[cfg(feature="storage-metrics")]
        {active.chain(self.completed_ids())}
        #[cfg(not(feature="storage-metrics"))]
        {active}
    }
    fn cell_metadata(&self,cell:u32)->Option<super::CellMetadata> {
        #[cfg(feature="storage-metrics")]
        if let Some(meta)=self.completed_meta(cell) {return Some(meta);}
        self.get(&cell).map(super::CellMetadata::from)
    }
    #[inline]
    fn fact_state(&self, f:FactRef)->Option<FactRead<'_>> {
        #[cfg(feature="storage-metrics")]
        if let Some(facts)=self.completed_facts(f.cell) {
            return facts[facts.binary_search_by_key(&f.op,|p|p.0).ok()?].1.as_ref().map(OwnedFact::read);
        }
        self.get(&f.cell)?.facts.get(&f.op).map(FactRead::from)
    }
    #[inline]
    fn fact_state_mut(&mut self, f:FactRef)->Option<FactWrite<'_>> {
        #[cfg(feature="storage-metrics")]
        if self.completed_index(f.cell).is_some() {
            let facts=self.completed_facts(f.cell)?;
            let state=facts[facts.binary_search_by_key(&f.op,|p|p.0).ok()?].1?.restore();
            return Some(FactWrite::Owned{cells:self,fact:f,state:Some(state)});
        }
        self.get_mut(&f.cell)?.facts.get_mut(&f.op).map(FactWrite::Ordinary)
    }
    fn remove_fact_state(&mut self, f:FactRef)->Option<FactState> {
        #[cfg(feature="storage-metrics")]
        if self.completed_index(f.cell).is_some() {
            let facts=self.completed_facts_mut(f.cell)?;
            return facts[facts.binary_search_by_key(&f.op,|p|p.0).ok()?].1.take().map(OwnedFact::restore);
        }
        self.get_mut(&f.cell)?.facts.remove(&f.op)
    }
    fn insert_fact_state(&mut self, f:FactRef, state:FactState)->Option<FactState> {
        let facts=&mut self.get_mut(&f.cell).expect("registered writable fact owner").facts;
        facts.reserve_first();
        facts.insert(f.op,state)
    }
    fn fact_count(&self, cell:u32)->Option<usize> {
        #[cfg(feature="storage-metrics")]
        if let Some(facts)=self.completed_facts(cell) {return Some(facts.iter().filter(|p|p.1.is_some()).count());}
        Some(self.get(&cell)?.facts.len())
    }
    fn fact_states(&self, cell:u32)->impl Iterator<Item=(FactRef,FactRead<'_>)> {
        let active=self.get(&cell).into_iter().flat_map(move |c|c.facts.iter().map(move |(&op,s)|(FactRef{cell,op},FactRead::from(s))));
        #[cfg(feature="storage-metrics")]
        {active.chain(self.completed_facts(cell).into_iter().flatten().filter_map(move |(op,s)|Some((FactRef{cell,op:*op},s.as_ref()?.read()))))}
        #[cfg(not(feature="storage-metrics"))]
        {active}
    }
}
#[cfg(not(feature="sparse-cells"))]
impl FactStates for rustc_hash::FxHashMap<u32,Cell> {
    fn cell_ids(&self)->impl Iterator<Item=u32> {self.keys().copied()}
    fn cell_metadata(&self,cell:u32)->Option<super::CellMetadata> {self.get(&cell).map(super::CellMetadata::from)}
    #[inline]
    fn fact_state(&self, f:FactRef)->Option<FactRead<'_>> {self.get(&f.cell)?.facts.get(&f.op).map(FactRead::from)}
    #[inline]
    fn fact_state_mut(&mut self, f:FactRef)->Option<FactWrite<'_>> {self.get_mut(&f.cell)?.facts.get_mut(&f.op).map(FactWrite::Ordinary)}
    fn remove_fact_state(&mut self, f:FactRef)->Option<FactState> {self.get_mut(&f.cell)?.facts.remove(&f.op)}
    fn insert_fact_state(&mut self, f:FactRef, state:FactState)->Option<FactState> {
        let facts=&mut self.get_mut(&f.cell).expect("registered fact owner").facts;
        #[cfg(feature="sparse-cells")]
        facts.reserve_first();
        facts.insert(f.op,state)
    }
    fn fact_count(&self, cell:u32)->Option<usize> {Some(self.get(&cell)?.facts.len())}
    fn fact_states(&self, cell:u32)->impl Iterator<Item=(FactRef,FactRead<'_>)> {
        self.get(&cell).into_iter().flat_map(move |c|c.facts.iter().map(move |(&op,s)|(FactRef{cell,op},FactRead::from(s))))
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
        FactState {owned:true,local_union_owned:false,
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
    #[test]
    #[cfg(feature="storage-metrics")]
    fn transferred_fact_addresses_survive_partial_owner_retirement() {
        use crate::slots::ReadSlots;
        use crate::value::Value;
        let mut cells=super::super::arena::Cells::default();
        for id in [10,20] {
            let mut c=cell();c.values.insert(0,Value::Int(id as i64));cells.insert(id,c);
            cells.insert_fact_state(FactRef{cell:id,op:7},state(3));
        }
        assert!(!cells.transfer_completed(&[10,10]));
        assert!(cells.get(&10).is_some());
        assert!(cells.transfer_completed(&[10,20]));
        assert!(cells.get(&10).is_none());
        assert_eq!(cells.completed_slots(20).unwrap().get(&0),Some(&Value::Int(20)));
        cells.remove_fact_state(FactRef{cell:10,op:7}).unwrap();
        assert!(cells.retire_completed(10));
        assert_eq!(cells.fact_state(FactRef{cell:20,op:7}).unwrap().epoch,3);
        assert!(cells.completed_meta(10).is_none());
        cells.remove_fact_state(FactRef{cell:20,op:7}).unwrap();
        cells.retire_completed(20);
        let (_,slots,facts,frames)=cells.completed_storage();
        assert_eq!((slots,facts,frames),(0,0,0));
    }

    #[test]
    #[cfg(feature="storage-metrics")]
    fn later_stage_extends_owner_without_losing_partial_lifecycles() {
        use crate::slots::ReadSlots;
        use crate::value::Value;
        let mut cells=super::super::arena::Cells::default();
        for id in [10,20,30,40,50] {
            let mut c=cell();c.started_epoch=id as u64;c.values.insert(0,Value::Int(id as i64));cells.insert(id,c);
            cells.insert_fact_state(FactRef{cell:id,op:7},state(id as u64));
        }
        assert!(cells.transfer_completed(&[10,20]));
        assert!(cells.transfer_completed(&[30,40]));
        let first=FactRef{cell:10,op:7};
        cells.fact_state_mut(first).unwrap().hidden=true;
        cells.fact_state_mut(first).unwrap().epoch=99;
        cells.remove_fact_state(FactRef{cell:20,op:7}).unwrap();
        // A partial old owner or duplicated source cannot be consumed.
        assert!(cells.extend_completed(&[10,50]).is_none());
        assert!(cells.extend_completed(&[10,20,50,50]).is_none());
        assert!(cells.get(&50).is_some());
        assert_eq!(cells.completed_slots(10).unwrap().get(&0),Some(&Value::Int(10)));
        let (added,merged,slots,facts)=cells.extend_completed(&[10,20,30,40,50]).unwrap();
        assert_eq!((added,merged,slots,facts),(1,1,4,3));
        assert!(cells.get(&50).is_none());
        assert!(cells.extend_completed(&[10,20,30,40,50]).is_none());
        assert!(cells.fact_state(first).unwrap().hidden);
        assert_eq!(cells.fact_state(first).unwrap().epoch,99);
        assert_eq!(cells.fact_state(first).unwrap().born,10);
        assert!(cells.fact_state(FactRef{cell:20,op:7}).is_none());
        for id in [10,20,30,40,50] {
            assert_eq!(cells.completed_meta(id).unwrap().started_epoch,id as u64);
            assert_eq!(cells.completed_slots(id).unwrap().get(&0),Some(&Value::Int(id as i64)));
        }
        let restored=cells.unseal_completed(10).unwrap();
        assert_eq!(restored.values.get(&0),Some(&Value::Int(10)));
        assert_eq!(restored.facts.get(&7).unwrap().epoch,99);
        assert_eq!(cells.completed_slots(50).unwrap().get(&0),Some(&Value::Int(50)));
        let report=cells.completed_profile();
        assert_eq!(report["restoration"]["events"],1);
        assert_eq!(report["restoration"]["slots"],1);
        assert_eq!(report["restoration"]["facts"],1);
        let bytes=restored.values.capacity_bytes()+restored.facts.capacity_bytes();
        assert_eq!(report["restoration"]["capacity_bytes"],bytes);
        assert_eq!(report["restoration"]["max_capacity_bytes"],bytes);
        assert!(cells.unseal_completed(10).is_none());
        assert_eq!(cells.completed_profile()["restoration"],report["restoration"]);
        // A retired fact is not reconstructed, and siblings remain compressed.
        let empty=cells.unseal_completed(20).unwrap();
        assert!(empty.facts.is_empty());
        assert_eq!(cells.completed_profile()["restoration"]["facts"],1);
        assert_eq!(cells.completed_profile()["restoration"]["events"],2);
        assert!(cells.completed_meta(30).is_some());
    }

    #[test]
    #[cfg(feature="storage-metrics")]
    fn owned_lifecycle_updates_stay_shared_and_exceptional_entries_restore_source() {
        let mut cells=super::super::arena::Cells::default();
        for id in [10,20] {cells.insert(id,cell());cells.insert_fact_state(FactRef{cell:id,op:7},state(3));}
        assert!(cells.transfer_completed(&[10,20]));
        let f=FactRef{cell:10,op:7};
        {let mut s=cells.fact_state_mut(f).unwrap();s.epoch=8;s.hash=99;s.hidden=true;}
        assert!(cells.get(&10).is_none(),"ordinary lifecycle writes must not restore a source");
        let s=cells.fact_state(f).unwrap();
        assert_eq!((s.epoch,s.born,s.hash,s.hidden),(8,3,99,true));
        assert_eq!(cells.completed_profile()["representation_fallbacks"],0);
        let alias=FactRef{cell:99,op:2};
        cells.fact_state_mut(f).unwrap().entry=Some(alias);
        assert!(cells.get(&10).is_some(),"specialized contract must not hide a new alias");
        let s=cells.fact_state(f).unwrap();
        assert_eq!((s.entry,s.epoch,s.born,s.hash,s.hidden),(Some(alias),8,3,99,true));
        assert_eq!(cells.completed_profile()["representation_fallbacks"],1);
        assert!(cells.completed_meta(20).is_some(),"other owner slices remain usable");
        assert_eq!(cells.fact_state(FactRef{cell:20,op:7}).unwrap().epoch,3);
        assert!(cells.extend_completed(&[10,20]).is_none(),"uncovered aliases cannot silently compact again");
    }
    #[test]
    #[cfg(feature="storage-metrics")]
    fn owner_transfer_rejects_unproved_fact_representation_atomically() {
        let mut cells=super::super::arena::Cells::default();
        for id in [10,20] {cells.insert(id,cell());cells.insert_fact_state(FactRef{cell:id,op:7},state(3));}
        cells.fact_state_mut(FactRef{cell:10,op:7}).unwrap().owned=false;
        assert!(!cells.transfer_completed(&[10,20]));
        assert!(cells.get(&10).is_some() && cells.get(&20).is_some());
        assert!(!cells.fact_state(FactRef{cell:10,op:7}).unwrap().owned);
    }

}
