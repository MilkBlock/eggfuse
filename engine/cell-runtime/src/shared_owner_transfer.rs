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
                    && self.cells.get(id).is_some_and(|c| c.completed && !c.symbolic_slots && c.parent.is_none()
                        && !c.facts.is_empty() && c.values.is_unshared()
                        && c.facts.iter().all(|(&op,s)|s.owned && self.stable_node(FactRef{cell:*id,op}).is_some()))
            }).collect::<Vec<_>>()
        }).filter(|g|g.len()>1).collect::<Vec<_>>();
        let mut count=0;
        for ids in groups {
            if !self.cells.can_transfer_completed(&ids) {continue;}
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
            if self.cells.transfer_completed(&ids) {count+=ids.len();}
        }
        if count>0 {self.cells.release_source_capacity();}
        Ok(count)
    }
}
