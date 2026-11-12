//! Opt-in physical replacement at an idle source Run boundary. Only frames in
//! the same already checked composed component can share a backing owner.
use super::*;
impl Graph {
    /// Matched diagnostic control: reclaim only the source record arena's spare
    /// capacity, without removing fields, facts, or parent links.
    pub fn compact_source_record_capacity(&mut self) {self.cells.release_source_capacity();}
    pub fn transfer_completed_owners(&mut self)->Result<usize> {
        if self.active_rhs.is_some() || !self.ownership_settled() || !self.pending_unions.is_empty() || !self.dirty.is_empty() {
            return Err("completed owner transfer requires a settled Run boundary".into());
        }
        let Some(m)=self.ownership.as_ref() else {return Ok(0);};
        let groups=m.composition.components.iter().flatten().map(|component| {
            component.frames.iter().copied().filter(|id| {
                self.parent_users.get(id).copied().unwrap_or(0)==0
                    && self.cells.get(id).is_some_and(|c| c.completed && c.parent.is_none()
                        && !c.facts.is_empty() && c.values.is_unshared()
                        && c.facts.iter().all(|(&op,s)|s.owned && self.stable_node(FactRef{cell:*id,op}).is_some()))
            }).collect::<Vec<_>>()
        }).filter(|g|g.len()>1).collect::<Vec<_>>();
        let mut count=0;
        for ids in groups {
            if !self.cells.can_transfer_completed(&ids) {continue;}
            // A completed parent handoff has already proved symbolic reads.
            // Reuse that storage contract instead of excluding inherited frames.
            let inherited=ids.iter().filter(|id|self.cells.get(id).unwrap().symbolic_slots).count();
            for &id in &ids {
                let m=self.ownership.as_ref().unwrap();
                let frame=m.composition.frames[&id];
                let component=m.composition.components[frame.component as usize].as_ref().unwrap();
                let ports=&m.composition.shapes[component.shape].as_ref().unwrap().ports[frame.ordinal];
                let c=self.cells.get_mut(&id).unwrap();
                let slots=&self.program.cell_ownership.markers[c.template].program.slots;
                let removed=c.values.retain_owned(|slot,value| {
                    let Value::Eq(value)=value else {return true;};
                    let Some(local)=slots.get(*slot).copied().flatten() else {return true;};
                    let Some(bound)=component.signals[ports[local]] else {return true;};
                    root(&self.parents,*value)!=root(&self.parents,bound)
                });
                if removed>0 {c.symbolic_slots=true;}
                self.stats.shared_owner_slots_delegated+=removed as u64;
            }
            if self.cells.transfer_completed(&ids) {
                count+=ids.len();
                self.stats.shared_owner_inherited_frames+=inherited as u64;
            }
        }
        if count>0 {self.cells.release_source_capacity();}
        Ok(count)
    }
}

// Read-only, bounded caller-side observation. Do not retain any of these frame
// addresses or component memberships as execution proofs across a source Run.
impl Graph {
    pub(crate) fn trace_rhs_owner_links(&self, cell:u32, rule:usize, donor:Dependency, known:&crate::cell::QueryFacts)->J {
        let Some(m)=self.ownership.as_ref() else {return J::Null;};
        let locate=|id:u32| -> J {
            let Some(frame)=m.composition.frames.get(&id) else {return J::Null;};
            let Some(component)=m.composition.components.get(frame.component as usize).and_then(Option::as_ref) else {return J::Null;};
            json!({"cell":id,"component":frame.component,"ordinal":frame.ordinal,
                "shape":component.shape,"frames":component.frames.len()})
        };
        let dependency=|receipt:Dependency| -> J {match receipt {
            Dependency::Fact(f)=>locate(f.cell),Dependency::Function(_)=>J::Null,
        }};
        let entry=m.composition.entry.as_ref().filter(|entry|entry.rule==rule);
        let anchors=entry.map(|entry|entry.anchors.iter().enumerate().filter_map(|(atom,receipt)| {
            let receipt=(*receipt)?;
            Some(json!({"atom":atom,"receipt":receipt,"location":dependency(receipt)}))
        }).collect::<Vec<_>>()).unwrap_or_default();
        let parent=self.rhs_frame(cell).and_then(|frame|frame.parent);
        let query=self.program.rules[rule].query.iter().enumerate().filter_map(|(atom,_)| {
            let receipt=known.receipt(atom)?;
            Some(json!({"atom":atom,"receipt":receipt,"location":dependency(receipt)}))
        }).collect::<Vec<_>>();
        json!({"receiver":locate(cell),"donor":dependency(donor),
            "entry_present":entry.is_some(),"anchors":anchors,"query":query,
            "query_atoms":self.program.rules[rule].query.len(),
            "parent":parent.map(|fact|json!({"receipt":Dependency::Fact(fact),"location":locate(fact.cell)}))})
    }
}
