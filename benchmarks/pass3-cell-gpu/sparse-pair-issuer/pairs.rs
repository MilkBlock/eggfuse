#[derive(Default, Serialize)]
struct SparsePairStats {
    unneeded_epoch_sorts: u64,
    considered: u64,
    admitted: u64,
    left_stale: u64,
    mixed: u64,
    right_rows: u64,
    age_tests: u64,
    learned_build_rows: u64,
    learned_probes: u64,
    emits: u64,
    pair_rules: rustc_hash::FxHashMap<usize, [u64; 4]>,
}
#[derive(Default)]
struct SparsePairs {
    mode: u64,
    min_rows: usize,
    ratio: usize,
    stats: SparsePairStats,
}
pub fn enable_sparse_pairs(v: Json) -> Result<()> {
    let mode = v["mode"].as_u64().ok_or("missing sparse pair mode")?;
    if !(1..=3).contains(&mode) {
        return Err("invalid sparse pair mode".into());
    }
    let n = v["min_rows"].as_u64().unwrap_or(32) as usize;
    let ratio = v["ratio"].as_u64().unwrap_or(1) as usize;
    STORE.with_borrow_mut(|state| {
        let s = state.as_mut().ok_or("no active pointer policy")?;
        if s.mode != "learned"
            || !s.packed_lookup
            || !s.seal
            || s.accel != 4
            || s.radius != 0
            || s.pair_mode != 3
        {
            return Err("sparse pairs need the zero-radius sealed pair guard".into());
        }
        s.sparse_pairs.mode = mode;
        s.sparse_pairs.min_rows = n;
        s.sparse_pairs.ratio = ratio;
        Ok(())
    })
}
type PairKey = smallvec::SmallVec<[u32; 3]>;
impl Store {
    fn sparse_values(&mut self, row: &Row, cols: &[(usize, usize)], left: bool) -> PairKey {
        cols.iter()
            .map(|&(l, r)| {
                signature(
                    self.code(&row.values[if left { l } else { r }]),
                    left,
                    self.views,
                )
            })
            .collect()
    }
    fn sparse_delta_pair(
        &mut self,
        c: &Context<'_>,
        steps: &[StackStep],
        cut: u64,
        raw: &mut Vec<Vec<Dependency>>,
    ) -> Result<bool> {
        self.sparse_pairs.stats.considered += 1;
        let (left, right) = (&steps[0], &steps[1]);
        let stale = left.frame.max_epoch < cut;
        if self.sparse_pairs.mode == 1
            || right.frame.max_epoch < cut
            || right.frame.rows.len() < self.sparse_pairs.min_rows
            || left
                .frame
                .rows
                .len()
                .saturating_mul(self.sparse_pairs.ratio)
                > right.frame.rows.len()
            || (!stale && self.sparse_pairs.mode < 3)
            || self
                .equations
                .plans
                .get(self.rule)
                .is_some_and(|p| p.is_some())
        {
            return Ok(false);
        }
        let cols = right
            .shared
            .iter()
            .map(|&(r, slot)| {
                left.publish
                    .iter()
                    .find(|&&(_, s)| s == slot)
                    .map(|&(l, _)| (l, r))
            })
            .collect::<Option<Vec<_>>>()
            .ok_or("unbound sparse pair column")?;
        self.sparse_pairs.stats.admitted += 1;
        self.sparse_pairs.stats.left_stale += u64::from(stale);
        self.sparse_pairs.stats.mixed += u64::from(!stale);
        self.sparse_pairs.stats.right_rows += right.frame.rows.len() as u64;
        // Compile the small set of full-right requests actually issued by fresh left roots.
        let left_keys: Vec<_> = left
            .frame
            .rows
            .iter()
            .map(|row| self.sparse_values(row, &cols, true))
            .collect();
        let wanted = left_keys
            .iter()
            .zip(&left.frame.rows)
            .filter_map(|(key, l)| (l.epoch >= cut).then_some(key))
            .collect::<rustc_hash::FxHashSet<_>>();
        let mut fresh = rustc_hash::FxHashMap::<PairKey, Vec<usize>>::default();
        let mut all = rustc_hash::FxHashMap::<PairKey, Vec<usize>>::default();
        for (i, row) in right.frame.rows.iter().enumerate() {
            let new = row.epoch >= cut;
            self.sparse_pairs.stats.age_tests += 1;
            if !new && wanted.is_empty() {
                continue;
            }
            let code = self.sparse_values(row, &cols, false);
            self.sparse_pairs.stats.learned_build_rows += 1;
            if wanted.contains(&code) {
                all.entry(code.clone()).or_default().push(i);
            }
            if new {
                fresh.entry(code).or_default().push(i);
            }
        }
        let mut path = Vec::with_capacity(2);
        let mut issued = 0;
        for (l, row) in left.frame.rows.iter().enumerate() {
            if self.stop_generation() {
                break;
            }
            if self.atoms.mode > 0 && !self.local_codes_permit(0, l, row) {
                continue;
            }
            let bucket = if row.epoch >= cut { &all } else { &fresh };
            self.sparse_pairs.stats.learned_probes += 1;
            let Some(members) = bucket.get(&left_keys[l]) else {
                continue;
            };
            self.counts.root_offers += 1;
            for &r in members {
                if self.stop_generation() {
                    break;
                }
                let other = &right.frame.rows[r];
                if self.atoms.mode > 0 && !self.local_codes_permit(1, r, other) {
                    continue;
                }
                self.counts.approximate_visits += 1;
                self.counts.learned_pointers += 1;
                self.trial_attempts += 1;
                path.clear();
                path.extend([row.witness, other.witness]);
                self.flat_offsets.clear();
                self.flat_offsets.extend([l as u32, r as u32]);
                self.seal_raw(c, steps, &path, raw);
                issued += 1;
            }
        }
        self.flat_offsets.clear();
        self.sparse_pairs.stats.emits += issued;
        let v = self
            .sparse_pairs
            .stats
            .pair_rules
            .entry(self.rule)
            .or_default();
        v[0] += 1;
        v[1] += left.frame.rows.len() as u64;
        v[2] += right.frame.rows.len() as u64;
        v[3] += issued;
        Ok(true)
    }
}
