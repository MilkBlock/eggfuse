// Only raw proposals cross source occurrences. Validation reads the current graph after sealing.
#[derive(Default, Serialize)]
struct RawCacheStats {
    candidates_tested: u64,
    cache_hits: u64,
    cache_misses: u64,
    watermark_regressions: u64,
    reused_tuples: u64,
    stale_tuples: u64,
    skipped_bytes: u64,
    peak_bytes: usize,
    resident_bytes: usize,
}
struct RawBatch {
    generations: Vec<u64>,
    cut: u64,
    epochs: Vec<u64>,
    offsets: Vec<u32>,
}
impl RawBatch {
    fn bytes(&self) -> usize {
        self.generations.capacity() * 8 + self.epochs.capacity() * 8 + self.offsets.capacity() * 4
    }
}
struct RawCache {
    enabled: bool,
    capturing: bool,
    cache: HashMap<usize, Rc<RawBatch>>,
    counts: RawCacheStats,
    epochs: Vec<u64>,
    offsets: Vec<u32>,
    room: usize,
    overflow: bool,
}
impl RawCache {
    const BUDGET: usize = 16 << 20;
    fn new(enabled: bool) -> Self {
        Self {
            enabled,
            capturing: false,
            cache: HashMap::new(),
            counts: Default::default(),
            epochs: vec![],
            offsets: vec![],
            room: 0,
            overflow: false,
        }
    }
    fn save(&mut self, epoch: u64, offsets: &[u32]) {
        if self.overflow {
            return;
        }
        if 8 * (self.epochs.len() + 1) + 4 * (self.offsets.len() + offsets.len()) > self.room {
            self.overflow = true;
            return;
        }
        self.epochs.push(epoch);
        self.offsets.extend_from_slice(offsets);
    }
}
impl Store {
    fn emit_cached(
        &mut self,
        c: &Context<'_>,
        steps: &[StackStep],
        slots: usize,
        raw: &mut Vec<Vec<Dependency>>,
    ) -> Result<()> {
        let cut = if c.rule.seminaive && c.remaining[c.pick_count] < c.watermark {
            c.watermark
        } else {
            0
        };
        let rule = self.rule;
        let mut path = Vec::with_capacity(steps.len());
        if let Some(previous) = self.raw_cache.cache.get(&rule).cloned() {
            let same = steps
                .iter()
                .map(|s| s.frame.generation)
                .eq(previous.generations.iter().copied());
            if same && cut >= previous.cut {
                self.raw_cache.counts.cache_hits += 1;
                for (&epoch, positions) in previous
                    .epochs
                    .iter()
                    .zip(previous.offsets.chunks_exact(steps.len()))
                {
                    self.raw_cache.counts.candidates_tested += 1;
                    if epoch < cut {
                        self.raw_cache.counts.stale_tuples += 1;
                        continue;
                    }
                    path.clear();
                    self.flat_offsets.clear();
                    for (step, &pos) in steps.iter().zip(positions) {
                        path.push(step.frame.rows[pos as usize].witness);
                    }
                    self.flat_offsets.extend_from_slice(positions);
                    self.seal_raw(c, steps, &path, raw);
                    self.raw_cache.counts.reused_tuples += 1;
                }
                self.flat_offsets.clear();
                return Ok(());
            }
            if same {
                self.raw_cache.counts.watermark_regressions += 1;
            }
            self.raw_cache.counts.resident_bytes -= previous.bytes();
            self.raw_cache.cache.remove(&rule);
        }
        self.raw_cache.counts.cache_misses += 1;
        self.raw_cache.epochs.clear();
        self.raw_cache.offsets.clear();
        self.raw_cache.room =
            RawCache::BUDGET.saturating_sub(self.raw_cache.counts.resident_bytes + steps.len() * 8);
        self.raw_cache.capturing = true;
        self.raw_cache.overflow = false;
        let result = self.emit_stack(c, steps, 0, 0, &mut path, &mut vec![None; slots], raw);
        self.raw_cache.capturing = false;
        result?;
        // A capped batch is not evidence of completeness, including when today's tighter
        // watermark could skip the prefix responsible for the previous cap.
        if self.trial_attempts >= self.cap || self.raw_cache.overflow {
            return Ok(());
        }
        let batch = RawBatch {
            generations: steps.iter().map(|s| s.frame.generation).collect(),
            cut,
            epochs: std::mem::take(&mut self.raw_cache.epochs),
            offsets: std::mem::take(&mut self.raw_cache.offsets),
        };
        let bytes = batch.bytes();
        if bytes + self.raw_cache.counts.resident_bytes > RawCache::BUDGET {
            self.raw_cache.counts.skipped_bytes += bytes as u64;
            return Ok(());
        }
        self.raw_cache.counts.resident_bytes += bytes;
        self.raw_cache.counts.peak_bytes = self
            .raw_cache
            .counts
            .peak_bytes
            .max(self.raw_cache.counts.resident_bytes);
        self.raw_cache.cache.insert(rule, Rc::new(batch));
        Ok(())
    }
}

#[derive(Default, Serialize)]
struct PairStats {
    calls: u64,
    delta_calls: u64,
    clean: u64,
    projected_indexes: u64,
    projected_rows: u64,
    guarded_left: u64,
    guarded_pairs: u64,
    high_directories: u64,
    high_index_rows: u64,
    full_left: u64,
    delta_left: u64,
    fresh_right: u64,
    reverse_row_visits: u64,
    first_candidates: u64,
    published_pairs: u64,
    compiled_columns: u64,
    encoded_rows: u64,
    reverse_index_rows: u64,
    source_row_pairs: u64,
}
#[derive(Default)]
struct NeuralColumns {
    related: FxHashMap<(usize, Vec<usize>), (u64, ProjectedEpochs)>,
    columns: HashMap<(usize, usize), (u64, Rc<Vec<Port>>)>,
    reverse: HashMap<(usize, usize), (u64, Rc<HashMap<u16, Vec<usize>>>)>,
    epochs: HashMap<usize, (u64, Rc<Vec<(u64, usize)>>)>,
    high: HashMap<(usize, usize), (u64, Rc<Vec<u64>>)>,
}
impl Store {
    fn projected_column(&mut self, d: &StackStep, col: usize) -> Rc<Vec<Port>> {
        let key = (d.table, col);
        if let Some((g, values)) = self.neural_columns.columns.get(&key)
            && *g == d.frame.generation
        {
            return values.clone();
        }
        let values = Rc::new(
            d.frame
                .rows
                .iter()
                .map(|r| self.code(&r.values[col]))
                .collect::<Vec<_>>(),
        );
        self.pair_stats.compiled_columns += 1;
        self.pair_stats.encoded_rows += values.len() as u64;
        self.neural_columns
            .columns
            .insert(key, (d.frame.generation, values.clone()));
        values
    }
    fn epoch_order(&mut self, d: &StackStep) -> Rc<Vec<(u64, usize)>> {
        if let Some((generation, epoch)) = self.neural_columns.epochs.get(&d.table)
            && *generation == d.frame.generation
        {
            return epoch.clone();
        }
        let mut values = d
            .frame
            .rows
            .iter()
            .enumerate()
            .map(|(i, r)| (r.epoch, i))
            .collect::<Vec<_>>();
        values.sort_unstable();
        let epoch = Rc::new(values);
        self.neural_columns
            .epochs
            .insert(d.table, (d.frame.generation, epoch.clone()));
        epoch
    }
    fn query_index(
        &mut self,
        d: &StackStep,
        col: usize,
        keys: &[Port],
    ) -> Rc<HashMap<u16, Vec<usize>>> {
        if let Some((version, index)) = self.neural_columns.reverse.get(&(d.table, col))
            && *version == d.frame.generation
        {
            return index.clone();
        }
        let mut map: HashMap<u16, Vec<usize>> = HashMap::new();
        for (i, k) in keys.iter().enumerate() {
            map.entry(k.query).or_default().push(i);
        }
        self.pair_stats.reverse_index_rows += keys.len() as u64;
        let index = Rc::new(map);
        self.neural_columns
            .reverse
            .insert((d.table, col), (d.frame.generation, index.clone()));
        index
    }
    fn emit_two(
        &mut self,
        c: &Context<'_>,
        steps: &[StackStep],
        raw: &mut Vec<Vec<Dependency>>,
    ) -> Result<()> {
        let (left, right) = (&steps[0], &steps[1]);
        let cut = if c.rule.seminaive && c.remaining[2] < c.watermark {
            c.watermark
        } else {
            0
        };
        self.pair_stats.calls += 1;
        if cut > left.frame.max_epoch.max(right.frame.max_epoch) {
            self.pair_stats.clean += 1;
            return Ok(());
        }
        let mut left_cols = Vec::with_capacity(right.shared.len());
        let mut right_cols = Vec::with_capacity(right.shared.len());
        for &(rcol, slot) in &right.shared {
            let lcol = left
                .publish
                .iter()
                .find(|&&(_, s)| s == slot)
                .ok_or("missing proposed parent field")?
                .0;
            left_cols.push((lcol, self.projected_column(left, lcol)));
            right_cols.push((rcol, self.projected_column(right, rcol)));
        }
        let index = if self.signatures.enabled {
            None
        } else {
            Some(self.index(right.table, right_cols[0].0, &right.frame))
        };
        let full_index = if self.signatures.enabled {
            Some(self.full_code_table(&right.frame, right_cols[0].0))
        } else {
            None
        };
        let full_left = left.frame.rows.len();
        let left_epochs = self.epoch_order(left);
        let right_epochs = self.epoch_order(right);
        let lcut = left_epochs.partition_point(|(e, _)| *e < cut);
        let rcut = right_epochs.partition_point(|(e, _)| *e < cut);
        let right_fresh = right_epochs.len() - rcut;
        let radius_bins = match self.radius {
            0 => 1,
            1 => 11,
            2 => 56,
            _ => 1024,
        };
        // A reverse query pays one hash lookup per signature in the Hamming
        // ball. It is attractive when only a small right delta exists.
        let selective = self.pair_mode >= 2
            && cut > 0
            && self.mode == "learned"
            && self.radius <= 2
            && (right_fresh == 0
                || right_fresh.saturating_mul(radius_bins) < lcut.saturating_mul(3));
        self.pair_stats.source_row_pairs += (left.frame.rows.len() * right.frame.rows.len()) as u64;
        let mut active: Vec<usize> = Vec::new();
        let mut back: HashMap<usize, Vec<usize>> = HashMap::new();
        if selective {
            self.pair_stats.delta_calls += 1;
            for &(_, i) in &left_epochs[lcut..] {
                active.push(i);
            }
            self.pair_stats.delta_left += active.len() as u64;
            self.pair_stats.fresh_right += right_fresh as u64;
            if right_fresh > 0 {
                let inv = self.query_index(left, left_cols[0].0, &left_cols[0].1);
                for &(_, r) in &right_epochs[rcut..] {
                    let k = right_cols[0].1[r].key;
                    for &mask in &self.reverse_masks {
                        if let Some(indices) = inv.get(&(k ^ mask)) {
                            for &l in indices {
                                self.pair_stats.reverse_row_visits += 1;
                                if left.frame.rows[l].epoch >= cut {
                                    continue;
                                }
                                if !left_cols
                                    .iter()
                                    .zip(&right_cols)
                                    .all(|((_, lcol), (_, rcol))| self.compatible(lcol[l], rcol[r]))
                                {
                                    continue;
                                }
                                let dest = back.entry(l).or_default();
                                if dest.is_empty() {
                                    active.push(l);
                                }
                                dest.push(r);
                            }
                        }
                    }
                }
                for (&l, rs) in &mut back {
                    let q = left_cols[0].1[l].query;
                    rs.sort_unstable_by_key(|&r| {
                        let k = right_cols[0].1[r].key;
                        let order = if self.radius <= 1 {
                            let d = q ^ k;
                            if d == 0 {
                                0
                            } else {
                                1 + d.trailing_zeros() as u16
                            }
                        } else {
                            k
                        };
                        (order, r)
                    });
                }
            }
            active.sort_unstable();
        } else {
            self.pair_stats.full_left += full_left as u64;
        }
        let (right_guard, suffix_guard) =
            if self.pair_mode == 3 && c.rule.seminaive && c.watermark > 0 {
                self.age_guards(c, steps)?
            } else {
                (vec![], vec![])
            };
        let prune = self.pair_mode == 3 && c.rule.seminaive && c.watermark > 0;
        let corr = self.pair_mode == 4;
        let prefix_guard = if corr {
            self.correlated_guards(c, steps, 1)?
        } else {
            vec![]
        };
        let complete_guard = if corr {
            self.correlated_guards(c, steps, 2)?
        } else {
            vec![]
        };
        let mark = if c.rule.seminaive { c.watermark } else { 0 };
        let mut path = Vec::with_capacity(2);
        let n = if selective { active.len() } else { full_left };
        for pos in 0..n {
            if self.stop_generation() {
                break;
            }
            let l = if selective { active[pos] } else { pos };
            let row = &left.frame.rows[l];
            if cut > row.epoch.max(right.frame.max_epoch) {
                continue;
            }
            if corr && !possible_relation_chain(&prefix_guard, l, 0, row.epoch, mark) {
                self.pair_stats.guarded_left += 1;
                continue;
            }
            if prune
                && row.epoch < c.watermark
                && !could_have_delta(&right_guard, l, None, c.watermark)
                && !could_have_delta(&suffix_guard, l, None, c.watermark)
            {
                self.pair_stats.guarded_left += 1;
                continue;
            }
            self.counts.root_offers += 1;
            self.pair_stats.first_candidates += 1;
            let shortlist;
            let reverse = back.get(&l);
            let entries: &[usize] = if let Some(found) = reverse {
                found
            } else {
                shortlist = if let Some(t) = &full_index {
                    self.full_code_list(t, left_cols[0].1[l])
                } else {
                    self.shortlist(
                        &right.frame,
                        index.as_ref().unwrap(),
                        right_cols[0].0,
                        left_cols[0].1[l],
                    )
                };
                &shortlist
            };
            for &r in entries {
                if self.stop_generation() {
                    break;
                }
                let other = &right.frame.rows[r];
                if row.epoch.max(other.epoch) < cut {
                    continue;
                }
                if corr
                    && !possible_relation_chain(
                        &complete_guard,
                        l,
                        r,
                        row.epoch.max(other.epoch),
                        mark,
                    )
                {
                    self.pair_stats.guarded_pairs += 1;
                    continue;
                }
                if prune
                    && row.epoch.max(other.epoch) < c.watermark
                    && !could_have_delta(&suffix_guard, l, Some(r), c.watermark)
                {
                    self.pair_stats.guarded_pairs += 1;
                    continue;
                }
                if reverse.is_none()
                    && !left_cols
                        .iter()
                        .zip(&right_cols)
                        .skip(1)
                        .all(|((_, lcol), (_, rcol))| self.compatible(lcol[l], rcol[r]))
                {
                    continue;
                }
                self.counts.approximate_visits += 1;
                self.counts.learned_pointers += 1;
                self.trial_attempts += 1;
                path.clear();
                path.push(row.witness);
                path.push(other.witness);
                self.flat_offsets.clear();
                self.flat_offsets.extend_from_slice(&[l as u32, r as u32]);
                self.seal_raw(c, steps, &path, raw);
                self.pair_stats.published_pairs += 1;
            }
        }
        self.flat_offsets.clear();
        Ok(())
    }
}

#[derive(Default, Serialize)]
struct DeltaStats {
    batches: u64,
    changed_addresses: u64,
    applied: u64,
    rebuilt: u64,
    inherited_rows: u64,
    decoded_rows: u64,
    removed_rows: u64,
    audit_comparisons: u64,
}
#[derive(Default)]
struct DeltaFrame {
    generation: u64,
    changed: std::collections::BTreeSet<Dependency>,
}

// Called at the same post-rebuild barrier which publishes the native table indexes.
// The journal is retained only for snapshots that have actually been requested.
pub(crate) fn changed_frame_rows(graph: &Graph) {
    STORE.with_borrow_mut(|store| {
        let Some(s) = store.as_mut() else { return };
        if !s.frame_delta {
            return;
        }
        for (table, changes) in graph.changes.tables() {
            if !s.frames.contains_key(&table) {
                continue;
            }
            let pending = s.frame_changes.entry(table).or_default();
            pending.generation = graph.query_versions[table];
            pending.changed.extend(changes.keys().copied());
            s.delta_stats.batches += 1;
            s.delta_stats.changed_addresses += changes.len() as u64;
        }
    });
}

impl Store {
    fn update_frame(
        &mut self,
        graph: &Graph,
        table: usize,
        generation: u64,
    ) -> Result<Option<Rc<Frame>>> {
        let Some(change) = self.frame_changes.remove(&table) else {
            return Ok(None);
        };
        if change.generation != generation {
            return Ok(None);
        }
        let Some(old) = self.frames.get(&table) else {
            return Ok(None);
        };
        let mut prior = old.rows.iter().peekable();
        let mut rows = Vec::with_capacity(old.rows.len() + change.changed.len());
        for w in change.changed {
            while prior.peek().is_some_and(|r| r.witness < w) {
                rows.push(prior.next().unwrap().clone());
                self.delta_stats.inherited_rows += 1;
            }
            if prior.peek().is_some_and(|r| r.witness == w) {
                prior.next();
            }
            if let Some(r) = graph.row(w)?.filter(|r| !r.hidden && r.table == table) {
                rows.push(r);
                self.delta_stats.decoded_rows += 1;
            } else {
                self.delta_stats.removed_rows += 1;
            }
        }
        self.delta_stats.inherited_rows += prior.len() as u64;
        rows.extend(prior.cloned());
        if self.detailed {
            let mut i = 0;
            for w in graph.witnesses(table) {
                if let Some(r) = graph.row(w)?.filter(|r| !r.hidden) {
                    let candidate = rows.get(i).ok_or("delta snapshot missed source row")?;
                    if candidate.witness != r.witness
                        || candidate.epoch != r.epoch
                        || candidate.values != r.values
                    {
                        return Err(format!(
                            "stale proposed snapshot: table {table} source {w:?}, epoch {}",
                            graph.epoch
                        ));
                    }
                    i += 1;
                    self.delta_stats.audit_comparisons += 1;
                }
            }
            if i != rows.len() {
                return Err("extra row in incremental source snapshot".into());
            }
        }
        let max_epoch = rows.iter().map(|r| r.epoch).max().unwrap_or(0);
        let frame = Rc::new(Frame {
            table,
            generation,
            rows,
            max_epoch,
        });
        self.frames.insert(table, frame.clone());
        self.delta_stats.applied += 1;
        Ok(Some(frame))
    }
}

enum BoundPort {
    Left(Rc<Vec<Port>>),
    Right(Rc<Vec<Port>>),
    Literal(u16),
}
struct FreshColumn {
    bound: BoundPort,
    // max epoch per lossy learned K signature, initialized with zero for an empty bin
    high: Rc<Vec<u64>>,
}
type AgeGuard = Vec<Vec<FreshColumn>>;
fn could_have_delta(guard: &AgeGuard, left: usize, right: Option<usize>, wm: u64) -> bool {
    guard.iter().any(|cols| {
        cols.iter().all(|x| {
            let code = match &x.bound {
                BoundPort::Left(c) => c[left].key,
                BoundPort::Right(c) => {
                    let Some(i) = right else {
                        return true;
                    };
                    c[i].key
                }
                BoundPort::Literal(code) => *code,
            };
            x.high[code as usize] >= wm
        })
    })
}
impl Store {
    fn high_by_code(&mut self, frame: &Rc<Frame>, table: usize, col: usize) -> Rc<Vec<u64>> {
        let key = (table, col);
        if let Some((version, high)) = self.neural_columns.high.get(&key)
            && *version == frame.generation
        {
            return high.clone();
        }
        let mut high = vec![0; 1 << B];
        for row in &frame.rows {
            let code = self.code(&row.values[col]).key as usize;
            high[code] = high[code].max(row.epoch);
        }
        self.pair_stats.high_directories += 1;
        self.pair_stats.high_index_rows += frame.rows.len() as u64;
        let high = Rc::new(high);
        self.neural_columns
            .high
            .insert(key, (frame.generation, high.clone()));
        high
    }
    fn age_guards(&mut self, c: &Context<'_>, steps: &[StackStep]) -> Result<(AgeGuard, AgeGuard)> {
        let mut known = BTreeMap::new();
        for (i, step) in steps.iter().enumerate() {
            for (col, arg) in c.rule.query[step.atom].args.iter().enumerate() {
                if let Arg::Slot(s) = arg {
                    known.entry(*s).or_insert((i, col));
                }
            }
        }
        let mut right = vec![];
        let mut suffix = vec![];
        for (n, (id, _, _)) in c.inst.iter().enumerate().skip(1) {
            let a = &c.rule.query[*id];
            let Call::Table(table) = a.call else { continue };
            let frame = self.frame(c.graph, table)?;
            if frame.max_epoch < c.watermark {
                continue;
            }
            let mut cols = vec![];
            for (col, arg) in a.args.iter().enumerate() {
                let source = match arg {
                    Arg::Literal(v) => {
                        BoundPort::Literal(self.code(&canon(v, &c.graph.parents)).key)
                    }
                    Arg::Slot(s) => match known.get(s) {
                        Some(&(i, p)) if i < n && i == 0 => {
                            BoundPort::Left(self.projected_column(&steps[0], p))
                        }
                        Some(&(i, p)) if i < n && i == 1 => {
                            BoundPort::Right(self.projected_column(&steps[1], p))
                        }
                        _ => continue,
                    },
                };
                cols.push(FreshColumn {
                    bound: source,
                    high: self.high_by_code(&frame, table, col),
                });
            }
            if n == 1 {
                right.push(cols);
            } else {
                suffix.push(cols);
            }
        }
        Ok((right, suffix))
    }
}

// A stored epoch is an upper bound over one projected signature tuple, never a
// proof of an exact suffix match. Once two independent source rows are issued,
// normal source unification and all point reads/guards are still necessary.
type ProjectedEpochs = Rc<FxHashMap<u64, u64>>;
struct ProjectedRelation {
    table_high: u64,
    fields: Vec<BoundPort>,
    bins: Option<ProjectedEpochs>,
}
impl ProjectedRelation {
    fn upper(&self, left: usize, right: usize) -> Option<u64> {
        let Some(index) = &self.bins else {
            return Some(self.table_high);
        };
        let mut key = 0;
        for value in &self.fields {
            let bits = match value {
                BoundPort::Left(c) => c[left].key,
                BoundPort::Right(c) => c[right].key,
                BoundPort::Literal(k) => *k,
            };
            key = add_projected(key, bits)
        }
        index.get(&key).copied()
    }
}
#[inline]
fn add_projected(key: u64, bits: u16) -> u64 {
    key.wrapping_mul(1_099_511_628_211) ^ (bits as u64)
}
fn possible_relation_chain(
    guard: &[ProjectedRelation],
    l: usize,
    r: usize,
    mut upper: u64,
    wm: u64,
) -> bool {
    for atom in guard {
        let Some(next) = atom.upper(l, r) else {
            return false;
        };
        upper = upper.max(next);
    }
    upper >= wm
}
impl Store {
    fn projected_epochs(&mut self, table: usize, cols: &[usize], frame: &Frame) -> ProjectedEpochs {
        let key = (table, cols.to_vec());
        if let Some((version, epochs)) = self.neural_columns.related.get(&key)
            && *version == frame.generation
        {
            return epochs.clone();
        }
        let mut epochs: FxHashMap<u64, u64> = FxHashMap::default();
        for row in &frame.rows {
            let mut signature = 0;
            for &col in cols {
                signature = add_projected(signature, self.code(&row.values[col]).key);
            }
            let high = epochs.entry(signature).or_default();
            *high = (*high).max(row.epoch);
        }
        self.pair_stats.projected_indexes += 1;
        self.pair_stats.projected_rows += frame.rows.len() as u64;
        let index = Rc::new(epochs);
        self.neural_columns
            .related
            .insert(key, (frame.generation, index.clone()));
        index
    }
    fn correlated_guards(
        &mut self,
        c: &Context<'_>,
        steps: &[StackStep],
        depth: usize,
    ) -> Result<Vec<ProjectedRelation>> {
        let mut owner = BTreeMap::new();
        for (i, step) in steps[..depth].iter().enumerate() {
            for (col, arg) in c.rule.query[step.atom].args.iter().enumerate() {
                if let Arg::Slot(s) = arg {
                    owner.entry(*s).or_insert((i, col));
                }
            }
        }
        let mut guards = vec![];
        for (id, _, _) in &c.inst[depth..] {
            let atom = &c.rule.query[*id];
            let Call::Table(table) = atom.call else {
                continue;
            };
            let frame = self.frame(c.graph, table)?;
            let mut fields = vec![];
            let mut cols = vec![];
            for (col, arg) in atom.args.iter().enumerate() {
                let source = match arg {
                    Arg::Literal(v) => {
                        BoundPort::Literal(self.code(&canon(v, &c.graph.parents)).key)
                    }
                    Arg::Slot(s) => match owner.get(s) {
                        Some(&(i, k)) if i == 0 => {
                            BoundPort::Left(self.projected_column(&steps[0], k))
                        }
                        Some(&(_, k)) => BoundPort::Right(self.projected_column(&steps[1], k)),
                        None => continue,
                    },
                };
                cols.push(col);
                fields.push(source);
            }
            let bins = if cols.is_empty() {
                None
            } else {
                Some(self.projected_epochs(table, &cols, &frame))
            };
            guards.push(ProjectedRelation {
                table_high: frame.max_epoch,
                fields,
                bins,
            });
        }
        Ok(guards)
    }
}

#[derive(Default, Clone, Serialize)]
struct RuleProfile {
    calls: u64,
    picks: usize,
    frame_ms: f64,
    issuance_ms: f64,
    validation_ms: f64,
    raw: u64,
    root_visits: u64,
    signature_visits: u64,
    checks: u64,
}
