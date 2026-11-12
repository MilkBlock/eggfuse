//! One set of arrays for a completed composed owner. Logical fact/slot numbers
//! stay unchanged; the former per-frame vectors move into bounded slices.
use super::*;
use crate::{slots::ReadSlots,value::Value};
use std::ops::Range;
pub(super) const COMPLETED:u32=1<<31;
use super::super::CellMetadata as Metadata;
pub(super) struct Frame {
    pub id:u32,
    pub owner:usize,
    pub meta:Metadata,
    pub slots:Range<usize>,
    pub facts:Range<usize>,
}
pub(super) struct Owner {
    pub frames:usize,
    pub slots:Box<[(usize,Value)]>,
    pub facts:Box<[(u32,Option<super::super::FactState>)]>,
}
#[derive(Default)]
pub(super) struct Completed {
    pub frames:Vec<Frame>,
    pub owners:Vec<Owner>,
}
pub(crate) struct Slots<'a>(pub &'a [(usize,Value)]);
impl ReadSlots for Slots<'_> {
    fn get(&self, slot:&usize)->Option<&Value> {
        Some(&self.0[self.0.binary_search_by_key(slot,|p|p.0).ok()?].1)
    }
}
impl Cells {
    pub(crate) fn completed_ids(&self)->impl Iterator<Item=u32> {self.completed.frames.iter().map(|f|f.id)}
    pub(crate) fn release_source_capacity(&mut self) {self.records.shrink_to_fit();}
    pub(crate) fn completed_index(&self,id:u32)->Option<usize> {
        let address=self.positions.get(id as usize).copied().unwrap_or(0);
        (address & COMPLETED != 0).then_some((address & !COMPLETED).wrapping_sub(1) as usize)
    }
    pub(crate) fn completed_meta(&self,id:u32)->Option<Metadata> {
        Some(self.completed.frames.get(self.completed_index(id)?)?.meta)
    }
    pub(crate) fn completed_slots(&self,id:u32)->Option<Slots<'_>> {
        let f=self.completed.frames.get(self.completed_index(id)?)?;
        Some(Slots(&self.completed.owners[f.owner].slots[f.slots.clone()]))
    }
    pub(crate) fn completed_facts(&self,id:u32)->Option<&[(u32,Option<super::super::FactState>)]> {
        let f=self.completed.frames.get(self.completed_index(id)?)?;
        Some(&self.completed.owners[f.owner].facts[f.facts.clone()])
    }
    pub(crate) fn completed_facts_mut(&mut self,id:u32)->Option<&mut [(u32,Option<super::super::FactState>)]> {
        let f=self.completed.frames.get(self.completed_index(id)?)?;
        Some(&mut self.completed.owners[f.owner].facts[f.facts.clone()])
    }
    /// Called only for a checked completed component, at an idle Run boundary.
    /// Reject the whole group before moving any source frame.
    pub(crate) fn can_transfer_completed(&self,ids:&[u32])->bool {
        if ids.len()<2 || self.completed.frames.len().saturating_add(ids.len())>=COMPLETED as usize
            || ids.iter().enumerate().any(|(i,id)|ids[..i].contains(id))
            || ids.iter().any(|id| {
            self.get(id).is_none_or(|c| !c.completed || c.parent.is_some() || !c.values.is_unshared())
        }) {return false;}
        ids.iter().all(|id|(*id as usize)<self.positions.len())
    }
    pub(crate) fn transfer_completed(&mut self,ids:&[u32])->bool {
        if !self.can_transfer_completed(ids) {return false;}
        let slots=ids.iter().map(|id|self.get(id).unwrap().values.len()).sum();
        let facts=ids.iter().map(|id|self.get(id).unwrap().facts.len()).sum();
        let owner=self.completed.owners.len();
        let mut values=Vec::with_capacity(slots);
        let mut states=Vec::with_capacity(facts);
        for &id in ids {
            let c=self.remove(&id).unwrap();
            let meta=Metadata::from(&c);
            let start=values.len();values.extend(c.values.into_unshared().unwrap());
            let first=states.len();states.extend(c.facts.into_iter().map(|(op,s)|(op,Some(s))));
            let position=u32::try_from(self.completed.frames.len()+1).unwrap();
            assert!(position<COMPLETED);
            self.completed.frames.push(Frame{id,owner,meta,slots:start..values.len(),facts:first..states.len()});
            self.positions[id as usize]=COMPLETED|position;
        }
        self.completed.owners.push(Owner{frames:ids.len(),slots:values.into_boxed_slice(),facts:states.into_boxed_slice()});
        true
    }
    /// Boundary fallback: move the remaining fields/facts back before a
    /// component supplying delegated symbols disappears. Other slices stay put.
    pub(crate) fn unseal_completed(&mut self,id:u32)->Option<Cell> {
        let index=self.completed_index(id)?;
        let frame=&self.completed.frames[index];
        let meta=frame.meta;
        let owner=&mut self.completed.owners[frame.owner];
        let values=owner.slots[frame.slots.clone()].iter_mut()
            .map(|(s,v)|(*s,std::mem::replace(v,Value::Int(0)))).collect();
        let facts=owner.facts[frame.facts.clone()].iter_mut()
            .filter_map(|(op,s)|Some((*op,s.take()?))).collect();
        self.retire_completed(id);
        Some(Cell{template:meta.template,started_epoch:meta.started_epoch,
            completed_prefix:meta.completed_prefix,recipe_depth:meta.recipe_depth,
            completed:meta.completed,symbolic_slots:meta.symbolic_slots,
            parent:None,values,facts})
    }
    pub(crate) fn retire_completed(&mut self,id:u32)->bool {
        let Some(index)=self.completed_index(id) else {return false;};
        let removed=self.completed.frames.swap_remove(index);
        self.positions[id as usize]=0;
        if let Some(moved)=self.completed.frames.get(index) {
            self.positions[moved.id as usize]=COMPLETED|u32::try_from(index+1).unwrap();
        }
        let owner=&mut self.completed.owners[removed.owner];
        owner.frames-=1;
        if owner.frames==0 {owner.slots=Box::default();owner.facts=Box::default();}
        true
    }
    pub(crate) fn completed_profile(&self)->serde_json::Value {
        use std::collections::{BTreeMap,BTreeSet};
        let mut templates=BTreeMap::<usize,usize>::new();
        let mut epochs=BTreeMap::<usize,BTreeSet<u64>>::new();
        let mut widths=BTreeMap::<usize,usize>::new();
        for f in &self.completed.frames {
            *templates.entry(f.meta.template).or_default()+=1;
            epochs.entry(f.owner).or_default().insert(f.meta.started_epoch);
        }
        for owner in self.completed.owners.iter().filter(|o|o.frames>0) {*widths.entry(owner.frames).or_default()+=1;}
        let slots=self.completed.owners.iter().map(|o|o.slots.len()).sum::<usize>();
        let live_slots=self.completed.frames.iter().map(|f|f.slots.len()).sum::<usize>();
        serde_json::json!({"source_records":self.records.len(),"completed_frames":self.completed.frames.len(),
            "owners":epochs.len(),"cross_stage_owners":epochs.values().filter(|e|e.len()>1).count(),
            "owner_widths":widths,"templates":templates,"stored_slot_entries":slots,
            "live_slot_entries":live_slots,"retired_slot_entries":slots-live_slots,
            "stored_fact_entries":self.completed.owners.iter().map(|o|o.facts.len()).sum::<usize>(),
            "live_fact_entries":self.completed.owners.iter().flat_map(|o|o.facts.iter()).filter(|p|p.1.is_some()).count(),
            "owner_header_slots":self.completed.owners.len()})
    }
    pub(crate) fn completed_storage(&self)->(usize,usize,usize,usize) {
        (self.completed.frames.capacity()*std::mem::size_of::<Frame>()
            +self.completed.owners.capacity()*std::mem::size_of::<Owner>(),
         self.completed.owners.iter().map(|o|std::mem::size_of_val(o.slots.as_ref())).sum(),
         self.completed.owners.iter().map(|o|std::mem::size_of_val(o.facts.as_ref())).sum(),
         self.completed.frames.len())
    }
}
