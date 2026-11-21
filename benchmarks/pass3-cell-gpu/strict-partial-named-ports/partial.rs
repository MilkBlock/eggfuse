// Internal children were already bound to signed returned coordinates. Only
// the independent residual enumerator checks which of its rows it still owns.
impl Trial {
    fn emit_strict_partial(
        &mut self,
        g: &Graph,
        rid: usize,
        wm: u64,
        p: &Plan,
        base: [u8; N],
        ordinary: &[SourceHeader],
        signed: &[(Dependency, u64)],
    ) -> Result<(Offered, usize, f32, usize)> {
        if p.pivot != Some(0)
            || p.order.len() != 0
            || self.rows.fixed != Some(4)
            || self.residual
            || !self.rows.batch
            || !self.policy.as_ref().is_some_and(|m| m.certified_inputs)
        {
            return Err("unsupported strict mixed single-source program".into());
        }
        if ordinary.windows(2).any(|w| w[0].source >= w[1].source)
            || signed.windows(2).any(|w| w[0].0 >= w[1].0)
        {
            return Err("unordered strict sources".into());
        }
        let mut ext = Vec::with_capacity(ordinary.len().saturating_sub(signed.len()));
        let mut skipped = 0usize;
        for h in ordinary {
            let w = h
                .source
                .ok_or("strict mixed residual requires a physical row")?;
            if h.version < wm {
                return Err("stale ordinary bank on sole semi-naive pivot".into());
            }
            if let Ok(i) = signed.binary_search_by_key(&w, |r| r.0) {
                if signed[i].1 != h.version {
                    return Err("stale strict residual exclusion".into());
                }
                skipped += 1;
            } else {
                ext.push(*h)
            }
        }
        let trace = self.rows.detailed || self.archive_winners;
        if trace && skipped != signed.len() {
            return Err("independent ordinary bank disagrees with signed eligibility".into());
        }
        let input = RowInput {
            m: self.policy.as_ref().unwrap(),
            rid,
            state: &self.state,
            base,
            epoch: g.epoch,
            watermark: wm,
        };
        let mut scores = vec![0.; ext.len()];
        let (evaluations, workers) = input.execute(&ext, &mut scores, 4, self.rows.pool.as_ref());
        self.rows.stats.evaluations += evaluations;
        self.rows.stats.source_headers += ext.len() as u64;
        self.rows.stats.invocations += 1;
        self.rows.stats.calls[4] += 1;
        self.rows.stats.addressed[4] += ext.len() as u64;
        self.rows.stats.peak_workers = self.rows.stats.peak_workers.max(workers.count_ones());
        let mut signed_score = 0.;
        if trace {
            let headers: Vec<_> = signed
                .iter()
                .map(|&(w, v)| SourceHeader::from_published(w, v, self.initial.contains(&w)))
                .collect();
            let mut oracle = vec![0.; headers.len()];
            input.execute(&headers, &mut oracle, 4, self.rows.pool.as_ref());
            signed_score = oracle[0];
            if signed_score < self.floors[rid]
                || oracle.iter().any(|v| v.to_bits() != signed_score.to_bits())
            {
                return Err("invalid strict score audit".into());
            }
        }
        if scores.iter().any(|s| *s < self.floors[rid]) {
            return Err("ordinary fresh row failed certified floor".into());
        }
        let n = signed.len() + ext.len();
        if n > 16_777_216 {
            return Err("strict recurrent count exceeds exact f32 range".into());
        }
        let mut offers = Vec::with_capacity(ext.len());
        let mut model_ids = Vec::with_capacity(signed.len());
        let mut spans: Vec<(bool, usize)> = vec![];
        let (mut a, mut b) = (0, 0);
        // Both lists enter in source address order. Internal IDs are allocated
        // from the independent signed list even in production with no audit.
        while a < signed.len() || b < ext.len() {
            let internal =
                a < signed.len() && (b == ext.len() || Some(signed[a].0) < ext[b].source);
            self.serial += 1;
            if internal {
                let (w, v) = signed[a];
                if self.rows.detailed {
                    self.rows
                        .observe(self.serial, Some(w), v, rid, signed_score, true)
                }
                model_ids.push(self.serial);
                a += 1
            } else {
                let h = ext[b];
                let score = scores[b];
                if self.rows.detailed {
                    self.rows
                        .observe(self.serial, h.source, h.version, rid, score, true)
                }
                offers.push((
                    Token {
                        recipe: None,
                        id: self.serial,
                        rid,
                        w: h.source,
                        guarded: false,
                        version: h.version,
                        initial: h.initial,
                        score,
                    },
                    base,
                    true,
                ));
                b += 1
            }
            if let Some((kind, len)) = spans.last_mut()
                && *kind == internal
            {
                *len += 1
            } else {
                spans.push((internal, 1))
            }
        }
        let mut wire = Vec::with_capacity(signed.len());
        let mut at = 0;
        let mut blocks = 0;
        for (internal, n) in spans {
            if internal {
                let first = crate::joint_root::internal_serials(n)?;
                wire.extend(first..first + n as u64);
            } else {
                let chunk = &mut offers[at..at + n];
                at += n;
                let args: Vec<_> = chunk.iter().map(|(t, _, _)| (t.w, t.version)).collect();
                let pg = crate::joint_root::single_page(g.epoch, rid, Some(0), &args)
                    .ok_or("missing external strict page")?;
                for (i, (t, _, _)) in chunk.iter_mut().enumerate() {
                    t.recipe = Some(pg.at(i))
                }
                blocks += 1;
            }
        }
        assert_eq!(at, ext.len());
        self.rows.stats.emitted += ext.len() as u64;
        crate::integral_packets::strict_mixed_seal(
            g.epoch,
            rid,
            wm,
            model_ids,
            wire,
            signed_score,
        )?;
        crate::strict_named::record_partition(
            ordinary.len(),
            skipped,
            signed.len(),
            ext.len(),
            blocks,
            trace,
        );
        Ok((offers, n, n as f32, n))
    }
}
