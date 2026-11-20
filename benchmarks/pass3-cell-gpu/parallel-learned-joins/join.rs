use rayon::prelude::*;
use std::time::Instant;

#[derive(Default, Serialize)]
struct WorkerStats {
    calls: u64,
    roots: u64,
    selected: u64,
    attempts: u64,
    speculative: u64,
    raw: u64,
    guard_rows: u64,
    column_refusals: u64,
    small: u64,
    cheap: u64,
    all_stale: u64,
    groups: u64,
    dir_keys: u64,
    epoch_hits: u64,
    bucket_hits: u64,
    epoch_installs: u64,
    bucket_installs: u64,
    budget_refusals: u64,
    peak_retained: usize,
    longest_lane_ns: u64,
    peak_workers: usize,
    peak_overlap: usize,
    multicore_calls: u64,
    worker_span_ns: u64,
    preparation_ns: u64,
    pool_start_ns: u64,
    dispatch_ns: u64,
    blocked_ns: u64,
    worker_ns: u64,
    merge_ns: u64,
    by_rule: BTreeMap<usize, [u64; 5]>,
}
#[derive(Default)]
struct Workers {
    n: usize,
    fault: u8,
    min_roots: usize,
    pool: Option<rayon::ThreadPool>,
    columns: WorkerColumns,
    grain: usize,
    local: bool,
    min_cost: u64,
    cost: FxHashMap<usize, u64>,
    stats: WorkerStats,
}
pub fn set_join_workers(
    n: usize,
    minimum: usize,
    fault: u8,
    budget: usize,
    grain: usize,
    local: bool,
    min_cost: u64,
) -> Result<()> {
    if !matches!(n, 1 | 2 | 4)
        || minimum == 0
        || fault > 2
        || !(1..=16).contains(&grain)
        || (local && n != 1)
    {
        return Err("unsupported learned worker partition".into());
    }
    STORE.with_borrow_mut(|s| {
        let s = s.as_mut().ok_or("missing learned worker producer")?;
        if !s.seal
            || s.accel != 4
            || s.mode != "learned"
            || s.radius != 0
            || !s.tier.materialize
            || !s.packed_lookup
        {
            return Err("workers require a sealed tied, typed-column producer".into());
        }
        s.workers.n = n;
        s.workers.columns.budget = budget;
        s.workers.grain = grain;
        s.workers.local = local;
        s.workers.min_cost = min_cost;
        s.workers.fault = fault;
        s.workers.min_roots = minimum;
        Ok(())
    })
}
struct TestView<'a> {
    rows: &'a FxHashMap<u64, u64>,
    key: &'a [PortSource],
    newly: bool,
}
struct WorkerStep<'a> {
    epochs: EpochColumn,
    permit: Option<Vec<bool>>,
    shared: Option<(usize, BucketColumn<'a>)>,
    extra: Vec<(usize, &'a [u32])>,
    publish: Vec<(usize, &'a [u32])>,
    tests: Vec<TestView<'a>>,
    unkeyed: u64,
}
struct Search<'a> {
    steps: Vec<WorkerStep<'a>>,
    remaining: &'a [u64],
    semi: bool,
    watermark: u64,
    cap: usize,
    present: bool,
    fresh: bool,
    bits: usize,
    slots: usize,
    forward: bool,
}
#[derive(Default)]
struct Lane {
    // Offsets are issuer output only. No graph rows, truth bindings or source proposals cross threads.
    flat: Vec<u32>,
    marks: Vec<usize>,
    attempts: usize,
    roots: u64,
    visits: u64,
    probes: u64,
    stale: u64,
    prefixes: u64,
    absence: u64,
    old: u64,
    published: u64,
    lookups: u64,
    start: u64,
    end: u64,
    worker: usize,
}
impl Search<'_> {
    fn visit(
        &self,
        depth: usize,
        epoch: u64,
        path: &mut Vec<u32>,
        ports: &mut [u32],
        range: std::ops::Range<usize>,
        out: &mut Lane,
    ) {
        if depth == self.steps.len() {
            out.flat.extend_from_slice(path);
            out.marks.push(out.attempts);
            return;
        }
        if out.attempts >= self.cap {
            return;
        }
        if self.semi && epoch.max(self.remaining[depth]) < self.watermark {
            out.stale += 1;
            return;
        }
        let s = &self.steps[depth];
        let members = if let Some((slot, groups)) = &s.shared {
            out.lookups += 1;
            match groups.get(&ports[*slot]) {
                Some(v) => Some(v),
                None => return,
            }
        } else {
            None
        };
        let (start, end) = if depth == 0 {
            (range.start, range.end)
        } else {
            (0, members.map_or(s.epochs.len(), |m| m.len()))
        };
        for i in start..end {
            if out.attempts >= self.cap {
                break;
            }
            let j = members.map_or(i, |xs| xs[i]);
            let now = epoch.max(s.epochs[j]);
            if self.semi && now.max(self.remaining[depth + 1]) < self.watermark {
                continue;
            }
            if depth == 0 {
                out.roots += 1;
            } else {
                out.visits += 1;
                if s.extra.iter().any(|(slot, col)| ports[*slot] != col[j]) {
                    continue;
                }
                out.attempts += 1;
            }
            if s.permit.as_ref().is_some_and(|p| !p[j]) {
                continue;
            }
            for &(slot, col) in &s.publish {
                ports[slot] = col[j];
                out.published += 1;
            }
            if self.forward {
                out.prefixes += 1;
                let mut upper = now.max(s.unkeyed);
                let mut rejected = false;
                for test in &s.tests {
                    let need = self.present && test.newly;
                    if !need && (!self.fresh || !self.semi || upper >= self.watermark) {
                        continue;
                    }
                    out.probes += 1;
                    let mask = (1u32 << self.bits) - 1;
                    let mut key = 0u64;
                    for spec in test.key {
                        let code = match *spec {
                            PortSource::Literal(v) => v,
                            PortSource::Slot(k) => ports[k] & mask,
                        };
                        key = (key << self.bits) | u64::from(code);
                    }
                    if let Some(&v) = test.rows.get(&key) {
                        upper = upper.max(v);
                    } else if need {
                        out.absence += 1;
                        rejected = true;
                        break;
                    }
                }
                if rejected {
                    continue;
                }
                if self.fresh && self.semi && upper < self.watermark {
                    out.old += 1;
                    continue;
                }
            }
            path.push(j as u32);
            self.visit(depth + 1, now, path, ports, range.clone(), out);
            path.pop();
        }
    }
}
impl Store {
    fn parallel_issue(
        &mut self,
        c: &Context<'_>,
        steps: &[StackStep],
        slots: usize,
        raw: &mut Vec<Vec<Dependency>>,
    ) -> Result<bool> {
        let workers = self.workers.n;
        if workers == 0
            || steps.len() < 3
            || !self.page
            || !steps[0].shared.is_empty()
            || steps[1..].iter().any(|d| d.shared.is_empty())
        {
            return Ok(false);
        }
        if self.workers.min_cost > 0 && c.rule.seminaive && c.remaining[0] < c.watermark {
            self.workers.stats.all_stale += 1;
            return Ok(false);
        }
        if self.workers.min_cost > 0
            && self.workers.cost.get(&self.rule).copied().unwrap_or(0) < self.workers.min_cost
        {
            self.workers.stats.cheap += 1;
            return Ok(false);
        }
        let roots = steps[0].frame.rows.len();
        self.workers.stats.selected += 1;
        if roots < self.workers.min_roots {
            self.workers.stats.small += 1;
            return Ok(false);
        }
        if steps.iter().any(|d| {
            d.frame.rows.len() > u32::MAX as usize || d.tier.as_ref().is_none_or(|t| !t.complete)
        }) {
            self.workers.stats.column_refusals += 1;
            return Ok(false);
        }
        if self
            .forward
            .config
            .as_ref()
            .is_some_and(|f| f.stale_control)
        {
            return Ok(false);
        }
        for (j, d) in steps.iter().enumerate() {
            let generation = if self.workers.fault == 1 && j == 0 {
                d.frame.generation.wrapping_sub(1)
            } else {
                d.frame.generation
            };
            if generation != c.graph.query_versions[d.table] {
                return Err("invalid learned worker frame generation".into());
            }
        }
        let prep = Instant::now();
        let mut views = Vec::with_capacity(steps.len());
        // Evaluate any exact owner guard in the original immutable source view, before crossing
        // the Send boundary. Workers receive only the resulting allowed-row bit, never a Graph.
        let mut masks = Vec::with_capacity(steps.len());
        for (i, d) in steps.iter().enumerate() {
            let local = self.atoms.mode != 0 && !self.atoms.stages[i].tests.is_empty();
            let early = self
                .early
                .active
                .as_ref()
                .is_some_and(|x| !x.by_owner[i].is_empty());
            if local || early {
                let mut allowed = Vec::with_capacity(d.frame.rows.len());
                for (j, r) in d.frame.rows.iter().enumerate() {
                    let ok = (!local || self.local_codes_permit(i, j, r))
                        && (!early || self.early.permits(c, i, j, r)?);
                    allowed.push(ok);
                }
                self.workers.stats.guard_rows += allowed.len() as u64;
                masks.push(Some(allowed));
            } else {
                masks.push(None);
            }
        }
        for ((i, d), permit) in steps.iter().enumerate().zip(masks) {
            let t = d.tier.as_ref().unwrap();
            let shared = if let Some(&(column, slot)) = d.shared.first() {
                let index = t
                    .index
                    .as_ref()
                    .and_then(|x| x.packed.as_ref())
                    .ok_or("missing learned buckets")?;
                self.workers.stats.groups += index.len() as u64;
                Some((
                    slot,
                    self.workers
                        .columns
                        .groups(&d.frame, column, index, &mut self.workers.stats),
                ))
            } else {
                None
            };
            let forward = self.forward.active.get(i);
            self.workers.stats.dir_keys += forward.map_or(0, |s| s.tests.len()) as u64;
            let tests = forward
                .map(|s| {
                    s.tests
                        .iter()
                        .map(|q| TestView {
                            rows: &q.dir.rows,
                            key: q.key.as_slice(),
                            newly: q.newly_bound,
                        })
                        .collect()
                })
                .unwrap_or_default();
            views.push(WorkerStep {
                epochs: self
                    .workers
                    .columns
                    .epochs(&d.frame, &mut self.workers.stats),
                shared,
                permit,
                extra: d
                    .shared
                    .iter()
                    .skip(1)
                    .map(|(col, slot)| (*slot, t.extra[col].as_slice()))
                    .collect(),
                publish: t
                    .publish
                    .iter()
                    .map(|(slot, v)| (*slot, v.as_slice()))
                    .collect(),
                tests,
                unkeyed: forward.map_or(0, |f| f.unkeyed_max),
            });
        }
        let cfg = self.forward.config.as_ref();
        let request = Search {
            steps: views,
            remaining: &c.remaining,
            semi: c.rule.seminaive,
            watermark: c.watermark,
            cap: self.cap,
            slots,
            present: cfg.is_some_and(|f| f.existence),
            fresh: cfg.is_some_and(|f| f.freshness),
            bits: (1 + self.forward.extra_views) * B,
            forward: !self.forward.active.is_empty(),
        };
        self.workers.stats.preparation_ns += prep.elapsed().as_nanos() as u64;
        if !self.workers.local && self.workers.pool.is_none() {
            let start = Instant::now();
            self.workers.pool = Some(
                rayon::ThreadPoolBuilder::new()
                    .num_threads(workers)
                    .build()
                    .map_err(|e| e.to_string())?,
            );
            self.workers.stats.pool_start_ns += start.elapsed().as_nanos() as u64;
        }
        let start = Instant::now();
        let chunks = (workers * self.workers.grain).min(roots);
        let search_lane = |lane: usize| {
            let range = roots * lane / chunks..roots * (lane + 1) / chunks;
            let mut out = Lane {
                start: start.elapsed().as_nanos() as u64,
                worker: rayon::current_thread_index().unwrap_or(usize::MAX),
                ..Default::default()
            };
            request.visit(
                0,
                0,
                &mut Vec::with_capacity(request.steps.len()),
                &mut vec![u32::MAX; request.slots],
                range,
                &mut out,
            );
            out.end = start.elapsed().as_nanos() as u64;
            out
        };
        let outputs: Vec<_> = if self.workers.local {
            (0..chunks).map(search_lane).collect()
        } else {
            self.workers
                .pool
                .as_ref()
                .unwrap()
                .install(|| (0..chunks).into_par_iter().map(search_lane).collect())
        };
        self.workers.stats.blocked_ns += start.elapsed().as_nanos() as u64;
        self.workers.stats.dispatch_ns += outputs.iter().map(|o| o.start).min().unwrap();
        let merge = Instant::now();
        let mut events = Vec::new();
        let mut participants = std::collections::BTreeSet::new();
        let mut positions = Vec::with_capacity(steps.len());
        let mut raw_count = 0;
        let mut visited = 0;
        let mut worker_ns = 0;
        let mut longest = 0;
        for out in outputs {
            if out.visits > 0 || out.roots > 0 {
                participants.insert(out.worker);
                events.push((out.start, 1i32));
                events.push((out.end, -1));
            }
            worker_ns += out.end - out.start;
            longest = longest.max(out.end - out.start);
            self.counts.root_offers += out.roots;
            self.counts.approximate_visits += out.visits;
            self.counts.learned_pointers += out.attempts as u64;
            self.counts.stale_candidates += out.stale;
            self.counts.score_bucket_reads += out.lookups;
            self.memo_counts.emitted_port_codes += out.published;
            self.forward.stats.prefixes += out.prefixes;
            self.forward.stats.probes += out.probes;
            self.forward.stats.rejected_absent += out.absence;
            self.forward.stats.rejected_old += out.old;
            let left = self.cap.saturating_sub(self.trial_attempts);
            for (path, &at) in out.flat.chunks_exact(steps.len()).zip(&out.marks) {
                if at > left || left == 0 {
                    self.workers.stats.speculative += 1;
                    continue;
                }
                positions.clear();
                for (column, (d, &j)) in steps.iter().zip(path).enumerate() {
                    let j = if self.workers.fault == 2 && column == 0 {
                        d.frame.rows.len()
                    } else {
                        j as usize
                    };
                    let row = d
                        .frame
                        .rows
                        .get(j)
                        .ok_or("invalid learned worker result offset")?;
                    positions.push(row.witness);
                }
                self.seal_raw(c, steps, &positions, raw);
                raw_count += 1;
            }
            self.trial_attempts += left.min(out.attempts);
            visited += out.attempts as u64;
        }
        let span = events.iter().map(|e| e.0).max().unwrap_or(0)
            - events.iter().map(|e| e.0).min().unwrap_or(0);
        events.sort_unstable();
        let mut live = 0i32;
        let mut peak = 0;
        for (_, d) in events {
            live += d;
            peak = peak.max(live);
        }
        let s = &mut self.workers.stats;
        s.calls += 1;
        s.roots += roots as u64;
        s.attempts += visited;
        s.raw += raw_count;
        s.worker_ns += worker_ns;
        s.longest_lane_ns += longest;
        s.peak_workers = s.peak_workers.max(participants.len());
        s.peak_overlap = s.peak_overlap.max(peak as usize);
        s.multicore_calls += u64::from(peak >= 2);
        s.worker_span_ns += span;
        let r = s.by_rule.entry(self.rule).or_default();
        r[0] += 1;
        r[1] += roots as u64;
        r[2] += visited;
        r[3] += raw_count;
        r[4] += worker_ns;
        s.merge_ns += merge.elapsed().as_nanos() as u64;
        Ok(true)
    }
}
