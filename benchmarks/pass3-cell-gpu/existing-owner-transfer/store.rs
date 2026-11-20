impl Cells {
    pub(crate) fn physical_owner(&self, id: u32) -> Option<(usize, usize)> {
        let pos = self.completed_index(id)?;
        let v = self.completed.frame_view(pos);
        Some((v.owner, self.completed.owners[v.owner].frames))
    }
    pub(crate) fn owner_ops(&self, id: u32) -> Vec<u32> {
        self.completed_index(id)
            .map(|i| self.completed.frame_view(i).layout.ops.to_vec())
            .unwrap_or_else(|| {
                self.get(&id)
                    .map(|cell| cell.facts.iter().map(|(op, _)| *op).collect())
                    .unwrap_or_default()
            })
    }
    pub(crate) fn live_owner_charge(&self) -> [usize; 7] {
        let (headers, slots, facts, frames) = self.completed_storage();
        [
            self.completed
                .owners
                .iter()
                .filter(|o| o.frames > 0)
                .count(),
            self.completed.owners.len(),
            frames,
            headers,
            slots,
            facts,
            headers + slots + facts,
        ]
    }
}
