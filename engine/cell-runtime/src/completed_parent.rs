//! Discharge a completed instance's parent dependency through its existing
//! composed symbols. Unknown/scalar projections retain the ordinary parent.
use super::*;
impl Graph {
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
