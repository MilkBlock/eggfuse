//! Discharge a completed instance's parent dependency through its existing
//! composed symbols, immutable scalar operands and only the residual actual
//! values. An unreadable projection leaves the ordinary parent intact.
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
        let Some(dead)=self.program.executions[rid].completed_dead_slots.as_ref() else {return;};
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
        let Some(dead)=plan.completed_dead_slots.as_ref() else {return;};
        if !frame.completed {return;}
        let removed=retire_dead_values(&mut frame.values,dead);
        if removed>0 {
            self.stats.completed_dead_slots_elided+=removed as u64;
            self.stats.completed_dead_frames_compacted+=1;
        }
        self.delegate_completed_slots(cell);
        self.delegate_completed_scalars(cell);
    }
    pub(crate) fn complete_parent_handoff(&mut self, cell: u32, rid: usize) -> Result<()> {
        let Some(layout)=self.program.executions[rid].parent_completion.as_ref() else {return Ok(());};
        let Some(c) = self.cells.get(&cell).filter(|c| c.completed) else { return Ok(()); };
        let Some(parent) = c.parent else { return Ok(()); };
        if self.ownership.is_none() { return Ok(()); }
        let template = c.template;
        self.stats.completed_parent_candidates += 1;
        // Build the residual before changing ownership. A failed read leaves
        // the original parent and every binding untouched. The existing frame
        // owns the residual; there is no second binding store.
        let mut residual=smallvec::SmallVec::<[(usize,Value);4]>::new();
        let mut delegated=0;
        for &slot in layout.iter() {
            self.stats.completed_parent_slot_checks += 1;
            if self.cells.get(&cell).unwrap().values.get(&slot).is_some() {continue;}
            let Ok(actual)=self.slot(cell,slot) else {return Ok(());};
            let provider=self.inherited_cell_slot(cell, template, slot)
                .or_else(||self.completed_scalar_slot(cell,template,slot,None));
            if provider.as_ref()==Some(&actual) {delegated+=1;} else {residual.push((slot,actual));}
        }
        let c = self.cells.get_mut(&cell).unwrap();
        let capacity=c.values.capacity_bytes();
        self.stats.completed_parent_residual_slots+=residual.len() as u64;
        for (slot,value) in residual {c.values.insert(slot,value);}
        self.stats.completed_parent_residual_capacity_bytes+=c.values.capacity_bytes().saturating_sub(capacity) as u64;
        c.symbolic_slots = true;
        c.parent = None;
        self.stats.completed_parent_detachments += 1;
        self.stats.completed_parent_slots_delegated += delegated;
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

impl Graph {
    fn scalar_plan(&self,template:usize)->&[(usize,u32,usize)] {
        if self.program.rules.get(template).is_none_or(|r|r.template!=template) {return &[];}
        self.program.executions[template].completed_scalar_slots.as_deref().unwrap_or(&[])
    }
    pub(super) fn completed_scalar_slot(&self,cell:u32,template:usize,slot:usize,excluding:Option<u32>)->Option<Value> {
        let plan=self.scalar_plan(template);
        let start=plan.partition_point(|p|p.0<slot);
        plan[start..].iter().take_while(|p|p.0==slot).find_map(|&(_,op,col)| {
            if excluding==Some(op) {return None;}
            let value=self.read_stable_column(self.stable_node(FactRef{cell,op})?,col).ok()?;
            matches!(value,Value::Int(_)|Value::Float(_)|Value::Text(_)).then_some(value)
        })
    }
    fn delegate_completed_scalars(&mut self,cell:u32) {
        let Some(c)=self.cells.get(&cell).filter(|c|c.completed) else {return;};
        let mut slots=self.scalar_plan(c.template).iter().filter_map(|&(slot,_,_)| {
            let value=c.values.get(&slot)?;
            (self.completed_scalar_slot(cell,c.template,slot,None).as_ref()==Some(value)).then_some(slot)
        }).collect::<Vec<_>>();
        slots.dedup();
        if slots.is_empty() {return;}
        let c=self.cells.get_mut(&cell).unwrap();
        let removed=c.values.retain_owned(|slot,_|!slots.contains(slot));
        if removed>0 {c.symbolic_slots=true;c.values.compact_capacity();}
        self.stats.completed_scalar_slots_elided+=removed as u64;
    }
    /// Restore only bindings losing their last provider, before either stable
    /// fields or the composed owner are retired. Fact identity stays unchanged.
    pub(super) fn preserve_completed_scalars(&mut self,f:FactRef) {
        use crate::slots::ReadSlots;
        let Some(meta)=self.cells.cell_metadata(f.cell).filter(|m|m.symbolic_slots) else {return;};
        let mut restore=Vec::new();
        for &(slot,op,col) in self.scalar_plan(meta.template) {
            if op!=f.op {continue;}
            let present=if let Some(c)=self.cells.get(&f.cell) {c.values.get(&slot).is_some()}
                else {self.cells.completed_slots(f.cell).is_some_and(|s|s.get(&slot).is_some())};
            if present || self.completed_scalar_slot(f.cell,meta.template,slot,Some(op)).is_some() {continue;}
            if let Some(value)=self.stable_node(f).and_then(|s|self.read_stable_column(s,col).ok()) {
                if !restore.iter().any(|(s,_)|*s==slot) {restore.push((slot,value));}
            }
        }
        if restore.is_empty() {return;}
        if let Some(c)=self.cells.unseal_completed(f.cell) {
            self.cells.insert(f.cell,c);self.stats.shared_owner_frames_restored+=1;
        }
        let c=self.cells.get_mut(&f.cell).expect("live scalar provider has a source frame");
        self.stats.completed_scalar_slots_restored+=restore.len() as u64;
        for (slot,value) in restore {c.values.insert(slot,value);}
    }
}
