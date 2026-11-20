// Learned buckets identify possible subscriber addresses. Ordered source checks
// still enforce complete key equality, visibility and the original source Run.
type Subscribers = rustc_hash::FxHashMap<u32, Vec<usize>>;

#[derive(Default, Serialize)]
struct WakeStats {
    eligible_calls: u64,
    routed_calls: u64,
    all_roots: u64,
    active_roots: u64,
    fresh_roots: u64,
    fresh_functions: u64,
    fresh_targets: u64,
    point_candidates: u64,
    scanned_points: u64,
    subscriber_visits: u64,
    score_collisions: u64,
    index_build_rows: u64,
    index_hits: u64,
    peak_rows: usize,
    refused: u64,
    direct_receipts: u64,
    audited_receipts: u64,
    suffix_open: u64,
}

#[derive(Default)]
struct Wake {
    mode: u8,
    indexes: rustc_hash::FxHashMap<(usize, usize), (u64, u64, usize, Rc<Subscribers>)>,
    retained: usize,
    stats: WakeStats,
}

pub fn configure_wake(mode: u64) -> Result<()> {
    if !(1..=4).contains(&mode) {
        return Err("invalid request wake mode".into());
    }
    STORE.with_borrow_mut(|s| {
        s.as_mut().ok_or("missing trained source issuer")?.wake.mode = mode as u8;
        Ok(())
    })
}

impl Store {
    fn wake_index(&mut self, c: &Context, step: &StackStep, col: usize) -> Option<Rc<Subscribers>> {
        let key = (step.table, col);
        let stamp = (step.frame.generation, c.graph.stats.unions);
        if let Some((g, u, _, m)) = self.wake.indexes.get(&key)
            && (*g, *u) == stamp
        {
            self.wake.stats.index_hits += 1;
            return Some(m.clone());
        }
        if let Some((_, _, rows, _)) = self.wake.indexes.remove(&key) {
            self.wake.retained -= rows;
        }
        let count = step.frame.rows.len();
        if count > 32768 {
            return None;
        }
        if self.wake.retained + count > 65536 {
            self.wake.indexes.clear();
            self.wake.retained = 0;
        }
        let mut bins = Subscribers::default();
        for (i, row) in step.frame.rows.iter().enumerate() {
            let v = canon(&row.values[col], &c.graph.parents);
            let code = self.code(&v);
            bins.entry(signature(code, false, self.views))
                .or_default()
                .push(i);
        }
        let bins = Rc::new(bins);
        self.wake.retained += count;
        self.wake.stats.peak_rows = self.wake.stats.peak_rows.max(self.wake.retained);
        self.wake.stats.index_build_rows += count as u64;
        self.wake
            .indexes
            .insert(key, (stamp.0, stamp.1, count, bins.clone()));
        Some(bins)
    }

    fn wake_roots(
        &mut self,
        c: &Context,
        src: &StackStep,
        point: &StackStep,
        target: &StackStep,
        key: &[RequestArg],
        tcol: usize,
    ) -> Option<Vec<(usize, Option<usize>)>> {
        let mode = self.wake.mode;
        let [RequestArg::Source(scol)] = key else {
            return None;
        };
        let n = src.frame.rows.len();
        self.wake.stats.eligible_calls += 1;
        let cut = if c.rule.seminaive && c.remaining[3] < c.watermark {
            c.watermark
        } else {
            0
        };
        if cut == 0 {
            self.wake.stats.suffix_open += 1;
            if mode < 4 || point.frame.rows.len() >= n {
                return None;
            }
        }
        let mut roots = Vec::new();
        if cut > 0 {
            let epochs = self.epoch_order(src);
            let start = epochs.partition_point(|(e, _)| *e < cut);
            self.wake.stats.fresh_roots += (n - start) as u64;
            if n > 32 && n - start > n / 2 {
                return None;
            }
            roots.extend(epochs[start..].iter().map(|&(_, i)| (i, None)));
        }
        let mut points = Vec::new();
        if cut == 0 {
            points.extend(0..point.frame.rows.len());
            self.wake.stats.scanned_points += point.frame.rows.len() as u64;
        } else {
            let epochs = self.epoch_order(point);
            let start = epochs.partition_point(|(e, _)| *e < cut);
            self.wake.stats.fresh_functions += (epochs.len() - start) as u64;
            points.extend(epochs[start..].iter().map(|&(_, i)| i));
            if target.frame.max_epoch >= cut {
                if mode == 1 {
                    return None;
                }
                let epochs = self.epoch_order(target);
                let start = epochs.partition_point(|(e, _)| *e < cut);
                let mut codes = rustc_hash::FxHashSet::default();
                for &(_, i) in &epochs[start..] {
                    // The target code must match the frozen shortlist's actual source value.
                    let code = self.code(&target.frame.rows[i].values[tcol]);
                    codes.insert(signature(code, false, self.views));
                }
                self.wake.stats.fresh_targets += (epochs.len() - start) as u64;
                let bins = self.wake_index(c, point, 1)?;
                for code in codes {
                    if let Some(rows) = bins.get(&code) {
                        points.extend_from_slice(rows)
                    }
                    if points.len() > 2 * point.frame.rows.len() + n {
                        self.wake.stats.refused += 1;
                        return None;
                    }
                }
            }
        }
        points.sort_unstable();
        points.dedup();
        self.wake.stats.point_candidates += points.len() as u64;
        if !points.is_empty() {
            let index = self.wake_index(c, src, *scol)?;
            for j in points {
                let mid = &point.frame.rows[j];
                let key = canon(&mid.values[0], &c.graph.parents);
                let code = self.code(&key);
                if let Some(rows) = index.get(&signature(code, true, self.views)) {
                    self.wake.stats.subscriber_visits += rows.len() as u64;
                    for &i in rows {
                        let r = &src.frame.rows[i];
                        if cut > 0 && r.epoch >= cut {
                            continue;
                        }
                        if canon(&r.values[*scol], &c.graph.parents) != key {
                            self.wake.stats.score_collisions += 1;
                            continue;
                        }
                        roots.push((i, Some(j)));
                    }
                }
            }
        }
        roots.sort_unstable_by_key(|&(i, _)| i);
        // A unary source function has a single result. If the physical frame
        // contains ambiguous aliases keep the ordinary direct request.
        if roots.windows(2).any(|w| w[0].0 == w[1].0) {
            self.wake.stats.refused += 1;
            return None;
        }
        self.wake.stats.routed_calls += 1;
        self.wake.stats.all_roots += n as u64;
        self.wake.stats.active_roots += roots.len() as u64;
        Some(roots)
    }
}
