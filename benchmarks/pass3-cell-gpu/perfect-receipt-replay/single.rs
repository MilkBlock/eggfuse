impl Trial {
    fn replay_single(
        &self,
        g: &Graph,
        rid: usize,
        p: &Plan,
        b: &crate::receipt_tape::Singles,
        only: bool,
    ) -> Result<(Vec<(Token, [u8; N], bool)>, usize, f32, usize)> {
        if !self.rows.batch || self.residual {
            return Err("oracle requires sealed complete single pages".into());
        }
        let mut v: Vec<_> = b
            .rows
            .iter()
            .filter(|r| !only || b.yes.contains(&r.id))
            .map(|r| {
                (
                    Token {
                        recipe: None,
                        id: r.id,
                        rid,
                        w: r.w,
                        version: r.epoch,
                        initial: r.initial,
                        score: r.score,
                        guarded: r.guarded,
                    },
                    r.features,
                    r.send,
                )
            })
            .collect();
        let selected: Vec<_> = v
            .iter()
            .filter(|(_, _, send)| *send)
            .map(|(t, _, _)| (t.w, t.version))
            .collect();
        if !selected.is_empty()
            && let Some(page) = crate::joint_root::single_page(g.epoch, rid, p.pivot, &selected)
        {
            for (i, (t, _, _)) in v.iter_mut().filter(|(_, _, send)| *send).enumerate() {
                t.recipe = Some(page.at(i));
            }
        }
        // Replay the donor's scalar telemetry for the recurrent update. No
        // reconstructed graph fields or accepted RHS are fed into that update.
        Ok((v, selected.len(), b.total, b.n))
    }
}
