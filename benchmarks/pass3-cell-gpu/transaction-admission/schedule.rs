pub fn install_request_schedule(actions: Vec<u8>) -> Result<()> {
    STORE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("missing proposer")?;
        let t = &mut s.transactions;
        if t.width != 8
            || !t.share
            || !t.parent_reads
            || t.tables_only
            || actions.len() != t.eligible.len()
        {
            return Err("incompatible request scheduling contract".into());
        }
        if actions
            .iter()
            .zip(&t.eligible)
            .any(|(&action, &eligible)| action > 2 || action != 0 && !eligible)
        {
            return Err("unproved request scheduling target".into());
        }
        t.learned_schedule = Some(actions);
        Ok(())
    })
}
