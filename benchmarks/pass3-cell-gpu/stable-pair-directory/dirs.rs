type StableFields = smallvec::SmallVec<[usize; 3]>;
type StableKey = smallvec::SmallVec<[u32; 3]>;
#[derive(Default)]
struct Posting {
    epochs: BTreeMap<Dependency, u64>,
    high: u64, // Conservative after a retirement; individual visible epochs remain authoritative.
}
#[derive(Default)]
struct LearnedDirectory {
    keys: rustc_hash::FxHashMap<Dependency, StableKey>,
    postings: rustc_hash::FxHashMap<StableKey, Posting>,
}
impl LearnedDirectory {
    fn put(&mut self, row: &Row, code: StableKey) {
        let target = self.postings.entry(code.clone()).or_default();
        target.high = target.high.max(row.epoch);
        target.epochs.insert(row.witness, row.epoch);
        self.keys.insert(row.witness, code);
    }
    fn remove(&mut self, address: Dependency) {
        if let Some(code) = self.keys.remove(&address)
            && let Some(bucket) = self.postings.get_mut(&code)
        {
            bucket.epochs.remove(&address);
            if bucket.epochs.is_empty() {
                self.postings.remove(&code);
            }
        }
    }
}
struct DirectoryVersion {
    generation: u64,
    union: u64,
    through: u64,
    valid_journal: bool,
    charge: usize,
    pending: std::collections::BTreeSet<Dependency>,
    data: Rc<LearnedDirectory>,
}
#[derive(Default, Serialize)]
struct DirectoryStats {
    calls: u64,
    activations: u64,
    builds: u64,
    build_rows: u64,
    reuses: u64,
    patches: u64,
    patch_addresses: u64,
    gaps: u64,
    union_rebuilds: u64,
    cross_union_patches: u64,
    frame_transitions: u64,
    budget_fallbacks: u64,
    peak_charge: usize,
    journal_updates: u64,
    left_probes: u64,
    old_buckets: u64,
    emits: u64,
    audit_rows: u64,
}
#[derive(Default)]
struct StableDirs {
    mode: u64,
    min_rows: usize,
    ratio: usize,
    budget: usize,
    charged: usize,
    stores: rustc_hash::FxHashMap<(usize, StableFields), DirectoryVersion>,
    stats: DirectoryStats,
}
impl StableDirs {
    // A successful Frame update copies or transfers every source row outside this exact delta.
    // Chain that snapshot transition, including across updates to unrelated equivalence classes.
    fn frame_transition(&mut self, t: usize, from: u64, to: u64, changed: &[Dependency]) {
        for ((table, _), state) in &mut self.stores {
            if *table != t {
                continue;
            }
            self.stats.frame_transitions += 1;
            if state.through != from || state.pending.len() > state.data.keys.len().max(32) {
                self.stats.gaps += 1;
                state.valid_journal = false;
                state.pending.clear();
            }
            if state.valid_journal {
                state.pending.extend(changed.iter().copied());
                self.stats.journal_updates += changed.len() as u64;
            }
            state.through = to;
        }
    }
    fn note<I: Iterator<Item = Dependency> + Clone>(
        &mut self,
        table: usize,
        new_gen: u64,
        n: usize,
        changes: I,
    ) {
        for ((owner, _), s) in &mut self.stores {
            if *owner != table || s.through == new_gen {
                continue;
            }
            if new_gen <= s.through
                || new_gen - s.through > n as u64
                || s.pending.len() > s.data.keys.len().max(32)
            {
                s.valid_journal = false;
                s.pending.clear();
                self.stats.gaps += 1;
            }
            if s.valid_journal {
                s.pending.extend(changes.clone());
                self.stats.journal_updates += n as u64;
            }
            s.through = new_gen;
        }
    }
}
pub fn enable_stable_dirs(v: Json) -> Result<()> {
    let mode = v["mode"].as_u64().ok_or("missing stable directory mode")?;
    if !(1..=3).contains(&mode) {
        return Err("invalid directory mode".into());
    }
    STORE.with_borrow_mut(|state| {
        let s = state.as_mut().ok_or("missing source proposer")?;
        if !s.frame_delta
            || !s.packed_lookup
            || !s.seal
            || s.accel != 4
            || s.radius != 0
            || s.pair_mode != 3
            || s.raw_cache.enabled
            || !s.page
            || s.mode != "learned"
        {
            return Err(
                "directory only supports sealed zero-radius, current learned source pages".into(),
            );
        }
        s.stable_dirs.mode = mode;
        s.stable_dirs.min_rows = v["min_rows"].as_u64().unwrap_or(64) as usize;
        s.stable_dirs.ratio = v["ratio"].as_u64().unwrap_or(1) as usize;
        s.stable_dirs.budget = v["bytes"].as_u64().unwrap_or(8 << 20) as usize;
        Ok(())
    })
}
impl Store {
    fn stable_key(&mut self, row: &Row, fields: &StableFields, query: bool) -> StableKey {
        fields
            .iter()
            .map(|&i| signature(self.code(&row.values[i]), query, self.views))
            .collect()
    }
    fn stable_directory(
        &mut self,
        f: &Rc<Frame>,
        fields: StableFields,
    ) -> Result<Option<Rc<LearnedDirectory>>> {
        let key = (f.table, fields);
        let stamp = (f.generation, f.born_at_union);
        if let Some(old) = self.stable_dirs.stores.get(&key)
            && (old.generation, old.union) == stamp
        {
            self.stable_dirs.stats.reuses += 1;
            return Ok(Some(old.data.clone()));
        }
        let prior = self.stable_dirs.stores.remove(&key);
        if let Some(old) = &prior {
            self.stable_dirs.charged -= old.charge;
        }
        // A storage charge, not a peak RSS measurement.
        let charge = 256 + 192 * f.rows.len();
        if self.stable_dirs.charged.saturating_add(charge) > self.stable_dirs.budget {
            self.stable_dirs.stats.budget_fallbacks += 1;
            return Ok(None);
        }
        let mut built = None;
        if self.stable_dirs.mode >= 2
            && let Some(mut old) = prior
        {
            if self.stable_dirs.mode == 2 && old.union != f.born_at_union {
                self.stable_dirs.stats.union_rebuilds += 1;
            } else if old.valid_journal
                && old.through == f.generation
                && let Some(map) = Rc::get_mut(&mut old.data)
            {
                for w in old.pending {
                    map.remove(w);
                    if let Ok(i) = f.rows.binary_search_by_key(&w, |r| r.witness) {
                        let r = &f.rows[i];
                        let code = self.stable_key(r, &key.1, false);
                        map.put(r, code);
                    }
                    self.stable_dirs.stats.patch_addresses += 1;
                }
                self.stable_dirs.stats.cross_union_patches +=
                    u64::from(old.union != f.born_at_union);
                self.stable_dirs.stats.patches += 1;
                built = Some(old.data);
            }
        }
        let data = if let Some(map) = built {
            map
        } else {
            let mut map = LearnedDirectory::default();
            for r in &f.rows {
                let code = self.stable_key(r, &key.1, false);
                map.put(r, code);
            }
            self.stable_dirs.stats.builds += 1;
            self.stable_dirs.stats.build_rows += f.rows.len() as u64;
            Rc::new(map)
        };
        if self.detailed {
            if data.keys.len() != f.rows.len()
                || data
                    .postings
                    .values()
                    .map(|v| v.epochs.len())
                    .sum::<usize>()
                    != f.rows.len()
            {
                return Err("incomplete learned source directory".into());
            }
            for row in &f.rows {
                let code = self.stable_key(row, &key.1, false);
                if data.keys.get(&row.witness) != Some(&code)
                    || data.postings[&code].epochs.get(&row.witness) != Some(&row.epoch)
                {
                    return Err("stale learned source posting".into());
                }
            }
            self.stable_dirs.stats.audit_rows += f.rows.len() as u64;
        }
        self.stable_dirs.charged += charge;
        self.stable_dirs.stats.peak_charge = self
            .stable_dirs
            .stats
            .peak_charge
            .max(self.stable_dirs.charged);
        self.stable_dirs.stores.insert(
            key,
            DirectoryVersion {
                generation: stamp.0,
                union: stamp.1,
                through: stamp.0,
                valid_journal: true,
                charge,
                pending: Default::default(),
                data: data.clone(),
            },
        );
        Ok(Some(data))
    }
    fn stable_pair(
        &mut self,
        c: &Context<'_>,
        steps: &[StackStep],
        cut: u64,
        raw: &mut Vec<Vec<Dependency>>,
    ) -> Result<bool> {
        self.stable_dirs.stats.calls += 1;
        let (left, right) = (&steps[0], &steps[1]);
        if right.frame.rows.len() < self.stable_dirs.min_rows
            || left.frame.rows.len().saturating_mul(self.stable_dirs.ratio) > right.frame.rows.len()
            || self
                .equations
                .plans
                .get(self.rule)
                .is_some_and(|p| p.is_some())
        {
            return Ok(false);
        }
        let mut lcols = StableFields::new();
        let mut rcols = StableFields::new();
        for &(r, slot) in &right.shared {
            let col = left
                .publish
                .iter()
                .find(|(_, s)| *s == slot)
                .ok_or("missing emitted port column")?
                .0;
            lcols.push(col);
            rcols.push(r);
        }
        let Some(dir) = self.stable_directory(&right.frame, rcols)? else {
            return Ok(false);
        };
        self.stable_dirs.stats.activations += 1;
        let right_local = self.atoms.mode > 0 && !self.atoms.stages[1].tests.is_empty();
        let mut path = Vec::with_capacity(2);
        for (l, row) in left.frame.rows.iter().enumerate() {
            if self.stop_generation() {
                break;
            }
            if self.atoms.mode > 0 && !self.local_codes_permit(0, l, row) {
                continue;
            }
            self.stable_dirs.stats.left_probes += 1;
            let code = self.stable_key(row, &lcols, true);
            let Some(b) = dir.postings.get(&code) else {
                continue;
            };
            if row.epoch.max(b.high) < cut {
                self.stable_dirs.stats.old_buckets += 1;
                continue;
            }
            self.counts.root_offers += 1;
            for (&right_address, &epoch) in &b.epochs {
                if self.stop_generation() {
                    break;
                }
                if row.epoch.max(epoch) < cut {
                    continue;
                }
                if right_local {
                    let pos = right
                        .frame
                        .rows
                        .binary_search_by_key(&right_address, |r| r.witness)
                        .map_err(|_| "absent indexed parent")?;
                    if !self.local_codes_permit(1, pos, &right.frame.rows[pos]) {
                        continue;
                    }
                }
                self.counts.approximate_visits += 1;
                self.counts.learned_pointers += 1;
                self.trial_attempts += 1;
                path.clear();
                path.extend([row.witness, right_address]);
                self.seal_raw(c, steps, &path, raw);
                self.stable_dirs.stats.emits += 1;
            }
        }
        Ok(true)
    }
}
