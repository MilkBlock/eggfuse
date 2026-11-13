//! Opt-in physical replacement at an idle source Run boundary. Logical
//! components stay independent even when small completed frames share arrays.
use super::*;
impl Graph {
    /// A completed source need not join a multi-frame storage owner to stop
    /// copying bindings already held by its checked component. The component
    /// teardown path restores symbolic slots before retiring their provider.
    pub(in crate::graph) fn delegate_completed_slots(&mut self, cell:u32) {
        let Some(owner)=self.ownership.as_ref() else {return;};
        let Some(frame)=owner.composition.frames.get(&cell) else {return;};
        let component=owner.composition.components[frame.component as usize].as_ref().unwrap();
        let ports=&owner.composition.shapes[component.shape].ports[frame.ordinal];
        let Some(c)=self.cells.get_mut(&cell).filter(|c|c.completed) else {return;};
        let slots=&self.program.cell_ownership.markers[c.template].program.slots;
        let mut checks=0;
        let removed=c.values.retain_owned(|slot,value| {
            let Value::Eq(value)=value else {return true;};
            let Some(local)=slots.get(*slot).copied().flatten() else {return true;};
            let Some(bound)=component.signals[ports[local]] else {return true;};
            checks+=1;
            root(&self.parents,*value)!=root(&self.parents,bound)
        });
        if removed>0 {c.symbolic_slots=true;c.values.compact_capacity();}
        self.stats.completed_symbolic_slot_checks+=checks;
        self.stats.completed_symbolic_slots_elided+=removed as u64;
    }

    /// Matched diagnostic control: reclaim only the source record arena's spare
    /// capacity, without removing fields, facts, or parent links.
    pub fn compact_source_record_capacity(&mut self) {self.cells.release_source_capacity();}
    /// Completed singleton components use the same inherited fact storage.
    /// A multi-frame history is not a prerequisite for compact lifecycle state.
    pub fn transfer_completed_owners(&mut self)->Result<usize> {
        self.transfer_completed_storage::<true>(false, true)
    }
    /// Experimental reuse of existing child storage inside a larger component.
    pub fn transfer_completed_owner_segments(&mut self)->Result<usize> {
        self.transfer_completed_storage::<false>(true, true)
    }
    /// Diagnostic ablation of singleton admission; all other storage logic is shared.
    pub fn transfer_completed_multi_owners(&mut self)->Result<usize> {
        self.transfer_completed_storage::<false>(false, false)
    }
    /// Same lifecycle admission, without sharing small singleton backing arrays.
    pub fn transfer_completed_unpooled_owners(&mut self)->Result<usize> {
        self.transfer_completed_storage::<false>(false, true)
    }
    fn transfer_completed_storage<const POOL:bool>(&mut self,reuse_segments:bool,singletons:bool)->Result<usize> {
        if self.active_rhs.is_some() || !self.ownership_settled() || !self.pending_unions.is_empty() || !self.dirty.is_empty() {
            return Err("completed owner transfer requires a settled Run boundary".into());
        }
        let Some(m)=self.ownership.as_ref() else {return Ok(0);};
        // Ordinary source records are the authoritative not-yet-transferred
        // inventory. Completed storage/restored sources already enter/leave it;
        // do not scan every historical component to rediscover that inventory.
        let mut candidates=Vec::new();
        for (&id,_) in self.cells.iter() {
            self.stats.shared_owner_admission_source_probes+=1;
            if let Some(frame)=m.composition.frames.get(&id) {candidates.push(frame.component);}
        }
        // Preserve the original component order, including physical pooling.
        candidates.sort_unstable();candidates.dedup();
        let mut groups=Vec::new();let mut pending=Vec::new();let mut bytes=0;
        for id in candidates {
            let Some(component)=m.composition.components.get(id as usize).and_then(Option::as_ref) else {continue;};
            let mut ids=component.frames.iter().copied().filter(|id| {
                self.cells.completed_meta(*id).is_some()
                    || self.cells.get(id).is_some_and(|c| c.completed && c.parent.is_none()
                        && !c.facts.is_empty() && c.values.is_unshared()
                        && c.facts.iter().all(|(&op,s)|s.owned && self.stable_node(FactRef{cell:*id,op}).is_some()))
            }).collect::<Vec<_>>();
            if ids.is_empty() || (!singletons && ids.len()==1) {continue;}
            if POOL && self.cells.completed_owner_has_external_sources(&ids) {
                // Keep shared prefix slices in place. Batch only the new
                // sources, instead of allocating a separate owner per suffix.
                // Logical component wiring and stable source IDs do not move.
                ids.retain(|id|self.cells.completed_meta(*id).is_none());
                if ids.is_empty() {continue;}
            }
            if POOL && ids.len()<=16 && ids.iter().all(|id|self.cells.completed_meta(*id).is_none()) {
                // Bound source count and estimated array payload while collecting
                // groups once. Sources retain independent restoration slices.
                // Logical composition is not a reason to allocate a separate
                // physical slab. Pool newly completed short components too;
                // complete unshared prefixes keep the extension path below.
                let size=ids.iter().map(|id| {
                    let c=self.cells.get(id).unwrap();
                    c.values.len()*std::mem::size_of::<(usize,Value)>()
                        +c.facts.len()*std::mem::size_of::<crate::graph::fact_states::OwnedFact>()
                }).sum::<usize>();
                if !pending.is_empty() && (pending.len()+ids.len()>16 || bytes+size>4096) {
                    groups.push(std::mem::take(&mut pending));bytes=0;
                }
                pending.extend(ids);bytes+=size;
            } else {groups.push(ids);}
        }
        if !pending.is_empty() {groups.push(pending);}
        let mut count=0;
        for ids in groups {
            let extending=ids.iter().any(|id|self.cells.completed_meta(*id).is_some());
            if !extending && !self.cells.can_transfer_completed(&ids) {continue;}
            // An already consolidated component has no new takeover work.
            if extending && ids.iter().all(|id|self.cells.completed_meta(*id).is_some()) {continue;}
            // A completed parent handoff has already proved symbolic reads.
            // Reuse that storage contract instead of excluding inherited frames.
            // External readers retain logical IDs, not ordinary Cell addresses.
            // Shared storage already preserves recipe reads and retirement fallback.
            let referenced=ids.iter().filter(|id|self.cells.get(id).is_some()
                && self.parent_users.get(id).copied().unwrap_or(0)>0).count();
            let inherited=ids.iter().filter(|id|self.cells.get(id).is_some_and(|c|c.symbolic_slots)).count();
            for &id in &ids {
                if self.cells.completed_meta(id).is_some() {continue;}
                let m=self.ownership.as_ref().unwrap();
                let frame=m.composition.frames[&id];
                let component=m.composition.components[frame.component as usize].as_ref().unwrap();
                let ports=&m.composition.shapes[component.shape].ports[frame.ordinal];
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
            if extending {
                let flat=if reuse_segments {None} else {self.cells.extend_completed(&ids)};
                // A physical slab may also contain unrelated live components.
                // Never copy those siblings to grow this logical component.
                let extension=flat.or_else(||self.cells.extend_completed_segments(&ids).map(|(added,reused)| {
                    self.stats.shared_owner_segment_extensions+=1;
                    self.stats.shared_owner_segments_reused+=reused as u64;
                    (added,0,0,0)
                }));
                if let Some((added,merged,slots,facts))=extension {
                    count+=added;
                    self.stats.shared_owner_referenced_frames+=referenced as u64;
                    self.stats.shared_owner_extensions+=1;
                    self.stats.shared_owner_extension_frames+=added as u64;
                    self.stats.shared_owner_merged_owners+=merged as u64;
                    self.stats.shared_owner_slot_entries_moved+=slots as u64;
                    self.stats.shared_owner_fact_entries_moved+=facts as u64;
                    self.stats.shared_owner_inherited_frames+=inherited as u64;
                }
            } else if self.cells.transfer_completed(&ids) {
                count+=ids.len();
                self.stats.shared_owner_referenced_frames+=referenced as u64;
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
        let anchors=entry.map(|entry|entry.anchors.iter().enumerate().filter_map(|(index,receipt)| {
            let receipt=(*receipt)?;
            Some(json!({"entry":index,"atom":self.program.cell_ownership.entries[rule][index],
                "receipt":receipt,"location":dependency(receipt)}))
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
