// Private fields ensure that only this source verifier can mint a checked lane.
// The references are valid for the immutable graph borrow of the current search.
pub(crate) struct CheckedBlock<'a> {
    graph: &'a Graph,
    rule: usize,
    page: &'a MultiPage,
    slot: usize,
    known: &'a [Option<Dependency>],
    values: &'a Slots,
}
impl<'a> CheckedBlock<'a> {
    pub(crate) fn parts(
        self,
    ) -> (
        &'a Graph,
        usize,
        &'a MultiPage,
        usize,
        &'a [Option<Dependency>],
        &'a Slots,
    ) {
        (
            self.graph,
            self.rule,
            self.page,
            self.slot,
            self.known,
            self.values,
        )
    }
}
pub(crate) fn allow_block_handoff() -> Result<()> {
    STORE.with_borrow_mut(|x| {
        let s = x.as_mut().ok_or("missing source verifier")?;
        if s.word_verifier.mode == 0 {
            return Err("checked handoff requires dictionary verification".into());
        }
        s.block_handoff = true;
        Ok(())
    })
}
