//! Discharge a completed instance's parent dependency through its existing
//! composed symbols. Unknown/scalar projections retain the ordinary parent.
use super::*;
fn retire_dead_values(values:&mut crate::slots::FrameSlots,dead:&[usize])->usize {
    let removed=values.retain_owned(|slot,_|dead.binary_search(slot).is_err());
    if removed>0 {values.compact_capacity();}
    removed
}
impl Graph {
    pub(crate) fn retire_completed_writer_inputs(&mut self,cell:u32,rid:usize) {
        let Some(index)=self.writer_dir.get(cell) else {
            self.retire_completed_inputs(cell,rid);return;
        };
        let Some(dead)=self.program.executions[rid].completed_dead_inputs.as_ref() else {return;};
        let Some(writer)=self.functions[index].writer.as_mut().filter(|w|w.completed) else {return;};
        let removed=retire_dead_values(&mut writer.values,dead);
        self.stats.completed_dead_slots_elided+=removed as u64;
        self.stats.completed_dead_frames_compacted+=u64::from(removed>0);
    }
    pub(crate) fn retire_completed_inputs(&mut self, cell:u32, rid:usize) {
        // A frame with no facts or retained users will be dropped immediately.
        // Do not compact a temporary allocation just before destroying it.
        if self.parent_users.get(&cell).copied().unwrap_or(0)==0
            && self.rhs_frame(cell).is_none_or(|c|c.facts.is_empty()) {return;}
        let (plan,_,frame)=self.execution_parts(rid,cell);
        let Some(dead)=plan.completed_dead_inputs.as_ref() else {return;};
        if !frame.completed {return;}
        let removed=retire_dead_values(&mut frame.values,dead);
        if removed>0 {
            self.stats.completed_dead_slots_elided+=removed as u64;
            self.stats.completed_dead_frames_compacted+=1;
        }
    }
    pub(crate) fn complete_parent_handoff(&mut self, cell: u32, rid: usize) -> Result<()> {
        let Some(layout)=self.program.executions[rid].parent_completion.as_ref() else {return Ok(());};
        let Some(c) = self.cells.get(&cell).filter(|c| c.completed) else { return Ok(()); };
        let Some(parent) = c.parent else { return Ok(()); };
        if self.ownership.is_none() { return Ok(()); }
        let template = c.template;
        self.stats.completed_parent_candidates += 1;
        // No partially copied bindings and no second ownership table. All
        // retained parent projections must already be represented by this component.
        for &slot in layout.iter() {
            self.stats.completed_parent_slot_checks += 1;
            let Some(value) = self.inherited_cell_slot(cell, template, slot) else { return Ok(()); };
            if self.slot(cell, slot)? != value { return Ok(()); }
        }
        let c = self.cells.get_mut(&cell).unwrap();
        c.symbolic_slots = true;
        c.parent = None;
        self.stats.completed_parent_detachments += 1;
        self.stats.completed_parent_slots_delegated += layout.len() as u64;
        self.release_reference(parent);
        // Existing source-Run GC retires unused ancestors after pending matches
        // have consumed their bindings. Never collect ancestors mid-Run.
        Ok(())
    }
}

// Diagnostic only: expose whether transient same-key forwarding can discharge
// parent storage. A visible replacement is not sufficient: it can depend on the
// child itself, and other holders can keep the old frame alive.
#[cfg(feature="storage-metrics")]
impl Graph {
    pub(crate) fn trace_forwarded_parents(&self) {
        if !crate::receipt_trace::enabled() || self.receipt_forwards.is_empty() {return;}
        let mut frames=0;let mut parents=0;
        for (&child,c) in self.cells.iter() {
            frames+=1;
            let Some(parent)=c.parent else {continue;};parents+=1;
            let from=Dependency::Fact(parent);
            let to=self.resolve_receipt(from);
            if from==to {continue;}
            let Some(source)=self.cells.get(&parent.cell) else {continue;};
            let visible=self.live_table(to).is_some_and(|table|self.receipt_visible(to,table));
            let mut cycle=false;
            if let Dependency::Fact(target)=to {
                let mut cursor=Some(target.cell);let mut hops=0;
                while let Some(id)=cursor {
                    if id==child || hops>self.next_cell as usize {cycle=true;break;}
                    cursor=self.cells.get(&id).and_then(|c|c.parent).map(|p|p.cell);
                    hops+=1;
                }
            }
            crate::receipt_trace::parent_forward(child,from,to,
                self.parent_users.get(&parent.cell).copied().unwrap_or(0),
                source.facts.len(),source.values.len(),visible,cycle);
        }
        crate::receipt_trace::parent_scan(frames,parents);
    }
}
