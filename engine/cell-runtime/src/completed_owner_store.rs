//! One set of arrays for a completed composed owner. Logical fact/slot numbers
//! stay unchanged; the former per-frame vectors move into bounded slices.
use super::*;
use crate::{slots::ReadSlots,value::Value};
use std::ops::Range;
use std::sync::Arc;
use std::collections::HashSet;
#[path="completed_fact_storage.rs"]
mod fact_storage;
use fact_storage::Facts;
use crate::graph::fact_states::{OwnedFact,RestoreCause};
pub(super) const COMPLETED:u32=1<<31;
use super::super::CellMetadata as Metadata;
pub(super) struct Frame {
    pub id:u32,
    pub owner:usize,
    started_epoch:u64,
    recipe_depth:u32,
    layout:Arc<Layout>,
    slot_start:usize,
    fact_start:usize,
}
/// Sparse operation/slot positions only; no values, Eq proofs or lifecycle.
#[derive(Hash,PartialEq,Eq)]
struct Layout {
    template:usize,
    completed_prefix:usize,
    symbolic_slots:bool,
    slots:Box<[usize]>,
    ops:Box<[u32]>,
}
impl Frame {
    fn meta(&self)->Metadata {
        Metadata{template:self.layout.template,completed_prefix:self.layout.completed_prefix,
            symbolic_slots:self.layout.symbolic_slots,completed:true,
            started_epoch:self.started_epoch,recipe_depth:self.recipe_depth}
    }
    fn slots(&self)->Range<usize> {self.slot_start..self.slot_start+self.layout.slots.len()}
}
pub(super) struct Owner {
    pub frames:usize,
    pub slots:Box<[Value]>,
    facts:Facts,
}
#[derive(Default,serde::Serialize)]
struct Restoration {
    events:u64,
    requested_scalar_slots:u64,
    restored_slots:u64,
    restored_facts:u64,
    restored_array_capacity_bytes:u64,
    max_array_capacity_bytes:usize,
    max_source_template:usize,
    max_source_slots:usize,
    max_source_facts:usize,
}
#[derive(Default)]
pub(super) struct Completed {
    pub frames:Vec<Frame>,
    pub owners:Vec<Owner>,
    pub representation_fallbacks:u64,
    restorations:[Restoration;3],
    layouts:HashSet<Arc<Layout>>,
    layout_checks:u64,
    layout_reuses:u64,
}
impl Completed {
    fn layout(&mut self,meta:Metadata,slots:Vec<usize>,ops:Vec<u32>)->Arc<Layout> {
        self.layout_checks+=1;
        assert!(meta.completed,"only completed sources share stage layouts");
        let layout=Layout{template:meta.template,completed_prefix:meta.completed_prefix,
            symbolic_slots:meta.symbolic_slots,slots:slots.into_boxed_slice(),ops:ops.into_boxed_slice()};
        if let Some(shared)=self.layouts.get(&layout) {self.layout_reuses+=1;return shared.clone();}
        let layout=Arc::new(layout);self.layouts.insert(layout.clone());layout
    }
    fn release_layout(&mut self,layout:Arc<Layout>) {
        if Arc::strong_count(&layout)==2 {self.layouts.remove(&layout);}
    }
    fn layout_bytes(&self)->usize {
        self.layouts.capacity()*std::mem::size_of::<Arc<Layout>>()
            +self.layouts.iter().map(|l|std::mem::size_of::<Layout>()+2*std::mem::size_of::<usize>()
                +std::mem::size_of_val(l.slots.as_ref())+std::mem::size_of_val(l.ops.as_ref())).sum::<usize>()
    }
}
pub(crate) struct Slots<'a> {positions:&'a [usize], values:&'a [Value]}
impl Slots<'_> {
    pub(crate) fn len(&self)->usize {self.values.len()}
    #[cfg(test)]
    pub(crate) fn as_ptr(&self)->*const Value {self.values.as_ptr()}
}
impl ReadSlots for Slots<'_> {
    fn get(&self, slot:&usize)->Option<&Value> {
        self.values.get(self.positions.binary_search(slot).ok()?)
    }
}
// Both directories survive many Runs. Bound unused capacity in either one:
// transferring a few more frames must not double the retained directory cost.
fn reserve_bounded<T>(records:&mut Vec<T>,added:usize) {
    let needed=records.len()+added;
    if needed>records.capacity() {
        let capacity=needed.next_power_of_two().min(needed.div_ceil(128)*128);
        records.reserve_exact(capacity-records.len());
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
        Some(self.completed.frames.get(self.completed_index(id)?)?.meta())
    }
    pub(crate) fn completed_slots(&self,id:u32)->Option<Slots<'_>> {
        let f=self.completed.frames.get(self.completed_index(id)?)?;
        Some(Slots{positions:&f.layout.slots,values:&self.completed.owners[f.owner].slots[f.slots()]})
    }
    pub(crate) fn completed_value(&self,id:u32,slot:usize)->Option<&Value> {
        let f=self.completed.frames.get(self.completed_index(id)?)?;
        let offset=f.layout.slots.binary_search(&slot).ok()?;
        self.completed.owners[f.owner].slots.get(f.slot_start+offset)
    }
    pub(crate) fn completed_facts(&self,id:u32)->Option<fact_storage::View<'_>> {
        let f=self.completed.frames.get(self.completed_index(id)?)?;
        Some(self.completed.owners[f.owner].facts.view(f.fact_start,&f.layout.ops,f.started_epoch))
    }
    pub(crate) fn take_completed_fact(&mut self,f:super::super::FactRef)->Option<OwnedFact> {
        let frame=&self.completed.frames[self.completed_index(f.cell)?];
        self.completed.owners[frame.owner].facts.take(frame.fact_start,&frame.layout.ops,frame.started_epoch,f.op)
    }
    /// Called only for checked completed sources, at an idle Run boundary.
    /// Reject the whole group before moving any source frame.
    pub(crate) fn can_transfer_completed(&self,ids:&[u32])->bool {
        self.can_transfer_segment(ids,1)
    }
    fn can_transfer_segment(&self,ids:&[u32],minimum:usize)->bool {
        if ids.len()<minimum || self.completed.frames.len().saturating_add(ids.len())>=COMPLETED as usize
            || ids.iter().enumerate().any(|(i,id)|ids[..i].contains(id))
            || ids.iter().any(|id| {
            self.get(id).is_none_or(|c| !c.completed || c.parent.is_some() || !c.values.is_unshared()
                    || c.facts.iter().any(|(_,s)|OwnedFact::checked(s).is_none()))
        }) {return false;}
        ids.iter().all(|id|(*id as usize)<self.positions.len())
    }
    pub(crate) fn transfer_completed(&mut self,ids:&[u32])->bool {
        self.transfer_segment(ids,1)
    }
    fn transfer_segment(&mut self,ids:&[u32],minimum:usize)->bool {
        if !self.can_transfer_segment(ids,minimum) {return false;}
        reserve_bounded(&mut self.completed.frames,ids.len());
        reserve_bounded(&mut self.completed.owners,1);
        let slots=ids.iter().map(|id|self.get(id).unwrap().values.len()).sum();
        let facts=ids.iter().map(|id|self.get(id).unwrap().facts.len()).sum();
        let owner=self.completed.owners.len();
        let mut values=Vec::with_capacity(slots);
        let mut states=Facts::builder(facts);
        for &id in ids {
            let c=self.remove(&id).unwrap();
            let meta=Metadata::from(&c);
            let slot_start=values.len();let fact_start=states.len();
            let mut slots=Vec::new();let mut ops=Vec::new();
            for (slot,value) in c.values.into_unshared().unwrap() {slots.push(slot);values.push(value);}
            for (op,state) in c.facts {ops.push(op);states.push(Some(OwnedFact::checked(&state).expect("checked owner fact")),meta.started_epoch);}
            let layout=self.completed.layout(meta,slots,ops);
            let position=u32::try_from(self.completed.frames.len()+1).unwrap();
            assert!(position<COMPLETED);
            self.completed.frames.push(Frame{id,owner,started_epoch:meta.started_epoch,recipe_depth:meta.recipe_depth,layout,slot_start,fact_start});
            self.positions[id as usize]=COMPLETED|position;
        }
        let facts=states.finish();
        self.completed.owners.push(Owner{frames:ids.len(),slots:values.into_boxed_slice(),facts});
        true
    }
    /// A larger completed Cell can retain several existing storage segments.
    /// The authoritative component already names their logical source frames;
    /// no second child directory or copied parent arrays are required.
    pub(crate) fn extend_completed_segments(&mut self,ids:&[u32])->Option<(usize,usize)> {
        let mut owners=Vec::new();let mut added=Vec::new();
        for (i,&id) in ids.iter().enumerate() {
            if ids[..i].contains(&id) {return None;}
            if let Some(index)=self.completed_index(id) {
                let owner=self.completed.frames[index].owner;
                if !owners.contains(&owner) {owners.push(owner);}
            } else {added.push(id);}
        }
        if owners.is_empty() || added.is_empty() {return None;}
        // Only the suffix moves. A single new frame is legal because its
        // surrounding composed Cell already has an admitted completed segment.
        self.transfer_segment(&added,1).then_some((added.len(),owners.len()))
    }
    /// Extend one proved component's storage with later completed stages. All
    /// members of any old owner must participate, so no omitted slice loses its
    /// backing allocation. Logical IDs and metadata are preserved verbatim.
    pub(crate) fn extend_completed(&mut self,ids:&[u32])->Option<(usize,usize,usize,usize)> {
        let mut owners=Vec::<(usize,usize)>::new();
        let mut added=0;
        for (i,&id) in ids.iter().enumerate() {
            if ids[..i].contains(&id) {return None;}
            if let Some(index)=self.completed_index(id) {
                let owner=self.completed.frames[index].owner;
                if let Some((_,count))=owners.iter_mut().find(|(o,_)|*o==owner) {*count+=1;}
                else {owners.push((owner,1));}
            } else {
                let c=self.get(&id)?;
                if !c.completed || c.parent.is_some() || !c.values.is_unshared()
                    || id as usize>=self.positions.len()
                    || c.facts.iter().any(|(_,s)|OwnedFact::checked(s).is_none()) {return None;}
                added+=1;
            }
        }
        if owners.is_empty() || ids.len()<2 || (added==0 && owners.len()==1)
            || owners.iter().any(|&(o,n)|self.completed.owners[o].frames!=n)
            || self.completed.frames.len().saturating_add(added)>=COMPLETED as usize {return None;}
        reserve_bounded(&mut self.completed.frames,added);
        let destination=owners[0].0;
        let mut slot_count=0;let mut fact_count=0;
        for &id in ids {
            if let Some(i)=self.completed_index(id) {
                let f=&self.completed.frames[i];let o=&self.completed.owners[f.owner];
                slot_count+=f.layout.slots.len();
                fact_count+=o.facts.view(f.fact_start,&f.layout.ops,f.started_epoch).iter().count();
            } else {let c=self.get(&id).unwrap();slot_count+=c.values.len();fact_count+=c.facts.len();}
        }
        let mut values=Vec::with_capacity(slot_count);let mut facts=Facts::builder(fact_count);
        let mut moved_slots=0;let mut moved_facts=0;
        for &id in ids {
            let slot_start=values.len();let fact_start=facts.len();
            let mut slots=Vec::new();let mut ops=Vec::new();
            if let Some(i)=self.completed_index(id) {
                let frame=&self.completed.frames[i];
                let meta=frame.meta();
                let owner=&mut self.completed.owners[frame.owner];
                for (slot,value) in frame.layout.slots.iter().zip(&mut owner.slots[frame.slots()]) {
                    slots.push(*slot);values.push(std::mem::replace(value,Value::Int(0)));moved_slots+=1;
                }
                for (offset,op) in frame.layout.ops.iter().enumerate() {
                    if let Some(state)=owner.facts.take_at(frame.fact_start+offset,frame.started_epoch) {
                        ops.push(*op);facts.push(Some(state),frame.started_epoch);moved_facts+=1;
                    }
                }
                let layout=self.completed.layout(meta,slots,ops);
                let frame=&mut self.completed.frames[i];
                let old=std::mem::replace(&mut frame.layout,layout);
                frame.owner=destination;frame.slot_start=slot_start;frame.fact_start=fact_start;
                self.completed.release_layout(old);
            } else {
                let c=self.remove(&id).unwrap();let meta=Metadata::from(&c);
                for (slot,value) in c.values.into_unshared().unwrap() {slots.push(slot);values.push(value);}
                for (op,state) in c.facts {ops.push(op);facts.push(Some(OwnedFact::checked(&state).expect("checked owner fact")),meta.started_epoch);}
                let layout=self.completed.layout(meta,slots,ops);
                let index=self.completed.frames.len();
                self.completed.frames.push(Frame{id,owner:destination,started_epoch:meta.started_epoch,recipe_depth:meta.recipe_depth,layout,slot_start,fact_start});
                self.positions[id as usize]=COMPLETED|(index as u32+1);
            }
        }
        for &(owner,_) in &owners {
            self.completed.owners[owner]=Owner{frames:0,slots:Box::default(),facts:Facts::default()};
        }
        let facts=facts.finish();
        self.completed.owners[destination]=Owner{frames:ids.len(),slots:values.into_boxed_slice(),facts};
        Some((added,owners.len()-1,moved_slots,moved_facts))
    }
    /// Boundary fallback: move the remaining fields/facts back before a
    /// component supplying delegated symbols disappears. Other slices stay put.
    pub(crate) fn unseal_completed(&mut self,id:u32,cause:RestoreCause)->Option<Cell> {
        let index=self.completed_index(id)?;
        let frame=&self.completed.frames[index];
        let meta=frame.meta();
        let owner=&mut self.completed.owners[frame.owner];
        let values=frame.layout.slots.iter().zip(owner.slots[frame.slots()].iter_mut())
            .map(|(s,v)|(*s,std::mem::replace(v,Value::Int(0)))).collect();
        let facts=frame.layout.ops.iter().enumerate().filter_map(|(offset,op)| {
            Some((*op,owner.facts.take_at(frame.fact_start+offset,meta.started_epoch)?.restore()))
        }).collect();
        self.retire_completed(id);
        let cell=Cell{template:meta.template,started_epoch:meta.started_epoch,
            completed_prefix:meta.completed_prefix,recipe_depth:meta.recipe_depth,
            completed:meta.completed,symbolic_slots:meta.symbolic_slots,
            parent:None,values,facts};
        let (kind,requested)=match cause {
            RestoreCause::ScalarProvider{slots}=>(0,slots),
            RestoreCause::ComponentRetirement=>(1,0),RestoreCause::Representation=>(2,0),
        };
        let stats=&mut self.completed.restorations[kind];
        let bytes=cell.values.capacity_bytes()+cell.facts.capacity_bytes();
        stats.events+=1;stats.requested_scalar_slots+=requested as u64;
        stats.restored_slots+=cell.values.len() as u64;stats.restored_facts+=cell.facts.len() as u64;
        stats.restored_array_capacity_bytes+=bytes as u64;
        if stats.events==1 || bytes>stats.max_array_capacity_bytes {
            stats.max_array_capacity_bytes=bytes;stats.max_source_template=meta.template;
            stats.max_source_slots=cell.values.len();stats.max_source_facts=cell.facts.len();
        }
        Some(cell)
    }
    pub(crate) fn write_completed_fact(&mut self,f:super::super::FactRef,state:super::super::FactState) {
        if let Some(compact)=OwnedFact::checked(&state) {
            let frame=&self.completed.frames[self.completed_index(f.cell).expect("live completed writer")];
            self.completed.owners[frame.owner].facts.write(frame.fact_start,&frame.layout.ops,frame.started_epoch,f.op,compact);
        } else {
            let mut cell=self.unseal_completed(f.cell,RestoreCause::Representation).expect("exceptional completed writer");
            *cell.facts.get_mut(&f.op).expect("live completed fact")=state;
            self.insert(f.cell,cell);
            self.completed.representation_fallbacks+=1;
        }
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
        if owner.frames==0 {owner.slots=Box::default();owner.facts=Facts::default();}
        self.completed.release_layout(removed.layout);
        true
    }
    /// Export only: relate logical sources to actual physical segments. Keep
    /// values out of this trace; no region directory is maintained at runtime.
    pub(crate) fn completed_layout_trace(&self)->serde_json::Value {
        use std::collections::{BTreeMap,BTreeSet};
        let key=|f:&Frame| (f.layout.template,f.layout.completed_prefix,f.layout.symbolic_slots,
            f.layout.slots.to_vec(),f.layout.ops.to_vec());
        let keys=self.completed.frames.iter().map(key).collect::<BTreeSet<_>>();
        let ids=keys.iter().enumerate().map(|(id,key)|(key,id)).collect::<BTreeMap<_,_>>();
        let layouts=keys.iter().map(|(template,prefix,symbolic,slots,ops)|serde_json::json!({
            "template":template,"completed_prefix":prefix,"symbolic_slots":symbolic,"slots":slots,"ops":ops
        })).collect::<Vec<_>>();
        let mut frames=self.completed.frames.iter().map(|f|serde_json::json!({
            "cell":f.id,"owner":f.owner,"layout":ids[&key(f)],"started_epoch":f.started_epoch,
            "recipe_depth":f.recipe_depth,"slot_start":f.slot_start,"fact_start":f.fact_start
        })).collect::<Vec<_>>();
        frames.sort_by_key(|f|f["cell"].as_u64().unwrap());
        let owners=self.completed.owners.iter().enumerate().filter(|(_,o)|o.frames>0).map(|(id,o)|
            serde_json::json!({"id":id,"sources":o.frames,"slot_entries":o.slots.len(),
                "fact_entries":o.facts.len(),"live_facts":o.facts.live()})).collect::<Vec<_>>();
        serde_json::json!({"schema":"completed-regions/v1","layouts":layouts,"frames":frames,"owners":owners,
            "source_record_bytes":std::mem::size_of::<Frame>(),"owner_record_bytes":std::mem::size_of::<Owner>(),
            "source_record_capacity":self.completed.frames.capacity(),"owner_record_capacity":self.completed.owners.capacity(),
            "scope":"export-only physical source ranges; layout identity excludes values, epochs and ownership proofs"})
    }
    pub(crate) fn completed_profile(&self)->serde_json::Value {
        use std::collections::{BTreeMap,BTreeSet};
        let mut templates=BTreeMap::<usize,usize>::new();
        let mut epochs=BTreeMap::<usize,BTreeSet<u64>>::new();
        let mut widths=BTreeMap::<usize,usize>::new();
        for f in &self.completed.frames {
            *templates.entry(f.layout.template).or_default()+=1;
            epochs.entry(f.owner).or_default().insert(f.started_epoch);
        }
        for owner in self.completed.owners.iter().filter(|o|o.frames>0) {*widths.entry(owner.frames).or_default()+=1;}
        let slots=self.completed.owners.iter().map(|o|o.slots.len()).sum::<usize>();
        let live_slots=self.completed.frames.iter().map(|f|f.layout.slots.len()).sum::<usize>();
        serde_json::json!({"source_records":self.records.len(),"owned_fact_bytes":std::mem::size_of::<OwnedFact>(),
            "restoration":{"events":self.completed.restorations.iter().map(|s|s.events).sum::<u64>(),
                "slots":self.completed.restorations.iter().map(|s|s.restored_slots).sum::<u64>(),
                "facts":self.completed.restorations.iter().map(|s|s.restored_facts).sum::<u64>(),
                "capacity_bytes":self.completed.restorations.iter().map(|s|s.restored_array_capacity_bytes).sum::<u64>(),
                "max_capacity_bytes":self.completed.restorations.iter().map(|s|s.max_array_capacity_bytes).max().unwrap_or(0),
                "max_template":self.completed.restorations.iter().filter(|s|s.events!=0).max_by_key(|s|s.max_array_capacity_bytes).map(|s|s.max_source_template),
                "scalar_provider":self.completed.restorations[0],
                "component_retirement":self.completed.restorations[1],"representation":self.completed.restorations[2],
                "scope":"restored frame array capacities before caller inserts lost bindings; excludes source arena growth, allocator overhead and Value payloads"},
            "fact_storage_encoding":"shared sparse membership; instance hashes and lifecycle exceptions",
            "source_frame_bytes":std::mem::size_of::<Frame>(),
            "shared_membership_layouts":self.completed.layouts.len(),"layout_checks":self.completed.layout_checks,
            "layout_reuses":self.completed.layout_reuses,"layout_estimated_bytes":self.completed.layout_bytes(),
            "owner_grouping":"physical arrays may span logical components; source frames restore independently",
            "fact_storage_live_bytes":self.completed_live_fact_bytes(),
            "representation_fallbacks":self.completed.representation_fallbacks,"completed_frames":self.completed.frames.len(),
            "owners":epochs.len(),"cross_stage_owners":epochs.values().filter(|e|e.len()>1).count(),
            "owner_widths":widths,"templates":templates,"stored_slot_entries":slots,
            "live_slot_entries":live_slots,"retired_slot_entries":slots-live_slots,
            "stored_fact_entries":self.completed.owners.iter().map(|o|o.facts.len()).sum::<usize>(),
            "live_fact_entries":self.completed.owners.iter().map(|o|o.facts.live()).sum::<usize>(),
            "inherited_fact_lifecycles":self.completed.owners.iter().map(|o|o.facts.inherited()).sum::<usize>(),
            "owner_header_slots":self.completed.owners.len()})
    }
    pub(crate) fn completed_live_fact_bytes(&self)->usize {
        self.completed.owners.iter().map(|o|o.facts.live_bytes()).sum()
    }
    pub(crate) fn completed_storage(&self)->(usize,usize,usize,usize) {
        (self.completed.frames.capacity()*std::mem::size_of::<Frame>()
            +self.completed.owners.capacity()*std::mem::size_of::<Owner>()+self.completed.layout_bytes(),
         self.completed.owners.iter().map(|o|std::mem::size_of_val(o.slots.as_ref())).sum(),
         self.completed.owners.iter().map(|o|o.facts.bytes()).sum(),
         self.completed.frames.len())
    }
}

#[cfg(test)]
mod stage_layout_tests {
    use super::*;
    #[test]
    fn shared_stage_preserves_source_epochs_depths_and_independent_restoration() {
        let mut cells=Cells::default();
        for (id,template,prefix,symbolic) in [(1,4,7,true),(2,4,7,true),(3,5,7,true),(4,4,8,true),(5,4,7,false)] {
            cells.insert(id,Cell{template,completed_prefix:prefix,symbolic_slots:symbolic,
                started_epoch:id as u64*10,recipe_depth:id,completed:true,parent:None,
                values:[(0,Value::Int(id as i64))].into_iter().collect(),facts:Default::default()});
        }
        assert!(cells.transfer_completed(&[1,2,3,4,5]));
        assert_eq!(cells.completed.layouts.len(),4,"only identical stages share metadata");
        let first=&cells.completed.frames[cells.completed_index(1).unwrap()];
        let second=&cells.completed.frames[cells.completed_index(2).unwrap()];
        assert!(Arc::ptr_eq(&first.layout,&second.layout));
        let before=cells.completed_layout_trace();
        assert_eq!(before["layouts"].as_array().unwrap().len(),4);
        assert_eq!(before["owners"].as_array().unwrap().len(),1);
        assert_eq!(before["owners"][0]["sources"],5);
        assert_eq!(before["frames"][0]["layout"],before["frames"][1]["layout"]);
        let sibling=cells.completed_slots(2).unwrap().as_ptr();
        let restored=cells.unseal_completed(1,RestoreCause::ComponentRetirement).unwrap();
        assert_eq!((restored.template,restored.completed_prefix,restored.started_epoch,restored.recipe_depth),(4,7,10,1));
        assert!(restored.completed && restored.symbolic_slots);
        assert_eq!(cells.completed_slots(2).unwrap().as_ptr(),sibling);
        let remaining=cells.completed_meta(2).unwrap();
        assert_eq!((remaining.started_epoch,remaining.recipe_depth),(20,2));
        assert_eq!(cells.completed.layouts.len(),4,"sibling still owns shared stage");
        let after=cells.completed_layout_trace();
        assert_eq!(after["owners"][0]["slot_entries"],5,"export preserves holes left by a restored source");
        assert_eq!(after["owners"][0]["sources"],4);
        assert_eq!(after["frames"][0]["cell"],2);
        assert_eq!(after["frames"][0]["slot_start"],1,"sibling did not move");
        assert_eq!(after["frames"][0]["started_epoch"],20);
        cells.retire_completed(2);
        assert_eq!(cells.completed.layouts.len(),3,"last source releases stage layout");
    }
}
