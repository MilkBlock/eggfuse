// The frozen opportunity stream supplies only an original candidate. Recompute
// component, owner and model legality in this graph before any physical change.
impl Graph {
    pub fn lifetime_action(
        &mut self,
        offer: &JV,
        policy: Option<&OwnerPolicy>,
        forced: bool,
        audit: bool,
        counter: fn(bool) -> [usize; 4],
    ) -> Result<(bool, usize, usize)> {
        let ids: Vec<u32> =
            serde_json::from_value(offer["ids"].clone()).map_err(|e| e.to_string())?;
        let owners: Vec<(u32, usize)> =
            serde_json::from_value(offer["owners"].clone()).map_err(|e| e.to_string())?;
        let births: Vec<u64> =
            serde_json::from_value(offer["birth_epochs"].clone()).map_err(|e| e.to_string())?;
        let shape = offer["shape"].as_u64().ok_or("missing candidate shape")? as usize;
        if self.active_rhs.is_some()
            || !self.ownership_settled()
            || !self.pending_unions.is_empty()
            || !self.dirty.is_empty()
            || offer["epoch"].as_u64() != Some(self.epoch)
            || ids.len() < 2
            || owners.len() != ids.len()
            || births.len() != ids.len()
        {
            return Err("incorrect placement boundary or member list".into());
        }
        if !self
            .ownership
            .as_ref()
            .ok_or("no ownership program")?
            .composition
            .components
            .iter()
            .flatten()
            .any(|c| c.shape == shape && c.frames.as_slice() == ids.as_slice())
        {
            return Err("compiler component unavailable".into());
        }
        let unique: TrialSet<_> = owners.iter().map(|&(_, o)| o).collect();
        if unique.len() != 2 {
            return Err("requires two existing owners".into());
        }
        for ((&id, &(claimed, o)), &birth) in ids.iter().zip(&owners).zip(&births) {
            if claimed != id
                || self.cells.physical_owner(id)
                    != Some((o, owners.iter().filter(|(_, x)| *x == o).count()))
                || self.cells.completed_meta(id).map(|m| m.started_epoch) != Some(birth)
            {
                return Err("stale or partial old owner".into());
            }
        }
        let f = self.cells.owner_features(&ids, owners[0].1);
        if json!(f) != offer["features"] {
            return Err("physical gate features changed".into());
        }
        let selected = policy
            .map(|p| p.score(&f))
            .transpose()?
            .map_or(forced, |s| s > 0.);
        if Some(selected) != offer["selected"].as_bool() {
            return Err("native gate chose another action".into());
        }
        let initial = if audit {
            Some(self.existing_owner_read(&ids)?)
        } else {
            None
        };
        if let Some(old) = &initial
            && (old["external_readers"].as_array().map(Vec::len)
                != offer["reader_count"].as_u64().map(|n| n as usize)
                || crate::checksum::artifact_digest(old)
                    != offer["old_refs"]
                        .as_str()
                        .ok_or("missing old read digest")?)
        {
            return Err("reader identity mismatch".into());
        }
        let before = counter(false);
        if selected {
            let (added, moved, _, _) = self
                .cells
                .extend_completed(&ids)
                .ok_or("physical transfer failed")?;
            if (added, moved) != (0, 1) {
                return Err("did not consolidate two prior owners".into());
            }
        }
        let after = counter(false);
        if let Some(old) = initial
            && self.existing_owner_read(&ids)? != old
        {
            return Err("old source became unreadable".into());
        }
        Ok((selected, after[1] - before[1], after[2] - before[2]))
    }
}
