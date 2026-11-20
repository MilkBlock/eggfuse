// Row workers can see only immutable source headers and the shared pre-occurrence
// recurrent state. They never access the non-Sync native graph or its verifier.
use rayon::prelude::*;
use serde::Serialize;
use std::sync::Arc;
use std::time::Instant as RowClock;

const ACTIONS: usize = 8;
const INPUT: usize = 5;

#[derive(Clone, Copy)]
struct SourceHeader {
    source: Option<Dependency>,
    version: u64,
    initial: bool,
    dynamics: [u8; 4], // function witness, integer count, contains zero, first integer scale
}

#[derive(Deserialize)]
struct RowModel {
    hidden: Vec<[f32; INPUT]>,
    bias: Vec<f32>,
    decisions: Vec<Vec<f32>>,
    offsets: [f32; ACTIONS],
}
impl RowModel {
    fn valid(&self) -> bool {
        let h = self.hidden.len();
        h == self.bias.len()
            && self.decisions.len() == ACTIONS
            && self.decisions.iter().all(|r| r.len() == h)
            && self
                .hidden
                .iter()
                .flatten()
                .chain(&self.bias)
                .chain(self.decisions.iter().flatten())
                .chain(&self.offsets)
                .all(|x| x.is_finite())
    }
    fn action(&self, x: &[f32; INPUT], max: usize) -> usize {
        let mut q = self.offsets;
        for (i, w) in self.hidden.iter().enumerate() {
            let h = (w.iter().zip(x).fold(self.bias[i], |a, (b, c)| a + b * c)).tanh();
            for (j, score) in q.iter_mut().enumerate() {
                *score += self.decisions[j][i] * h;
            }
        }
        (0..ACTIONS)
            .filter(|&a| width(a) <= max)
            .max_by(|&a, &b| q[a].total_cmp(&q[b]).then(b.cmp(&a)))
            .unwrap()
    }
}

fn width(action: usize) -> usize {
    1 << (action % 4)
}
#[derive(Default, Serialize)]
struct RowStats {
    invocations: u64,
    proof_empty_calls: u64,
    proof_stale_headers: u64,
    proof_block_calls: u64,
    source_headers: u64,
    snapshot_builds: u64,
    snapshot_reuses: u64,
    evaluations: u64,
    emitted: u64,
    stale_proofs: u64,
    real_parallel_calls: u64,
    peak_workers: u32,
    calls: [u64; ACTIONS],
    addressed: [u64; ACTIONS],
}
#[derive(Default)]
struct RowEngine {
    prefilter: usize,
    verify: VerifiedRows,
    active: bool,
    detailed: bool,
    prune: bool,
    profile: bool,
    capture: bool,
    fixed: Option<usize>,
    max_rows: usize,
    workers: usize,
    pool: Option<rayon::ThreadPool>,
    model: Option<RowModel>,
    snapshots: std::collections::HashMap<usize, (u64, Arc<Vec<SourceHeader>>)>,
    stats: RowStats,
    batch: bool,
    raw: u64,
    seed: u64,
    examples: Vec<([f32; INPUT], [u64; ACTIONS])>,
    phase: [u64; 4],
}
impl RowEngine {
    fn observe(
        &mut self,
        serial: u64,
        source: Option<Dependency>,
        epoch: u64,
        rid: usize,
        score: f32,
        issued: bool,
    ) {
        let ptr = source.map(address).unwrap_or([0; 3]);
        for w in [
            serial,
            ptr[0],
            ptr[1],
            ptr[2],
            epoch,
            rid as u64,
            u64::from(score.to_bits()),
            issued as u64,
        ] {
            self.raw = (self.raw ^ w).wrapping_mul(1099511628211);
        }
    }
    fn report(&self) -> J {
        json!({"stats":self.stats,"verification":self.verify.stats,"decision_digest":self.raw.to_string(),"phase_ns":self.phase,"examples":self.examples})
    }

    fn snapshot(
        &mut self,
        g: &Graph,
        table: usize,
        initial: &BTreeSet<Dependency>,
        cert: bool,
    ) -> Result<Arc<Vec<SourceHeader>>> {
        let version = g.query_versions[table];
        if let Some((v, rows)) = self.snapshots.get(&table)
            && *v == version
        {
            self.stats.snapshot_reuses += 1;
            return Ok(rows.clone());
        }
        let mut records = Vec::new();
        for w in g.witnesses(table) {
            let (epoch, dynamics) = if cert {
                let Some(e) = g.visible_epoch(w) else {
                    continue;
                };
                (e, [0; 4])
            } else {
                let Some(row) = g.row(w)? else { continue };
                if row.hidden {
                    continue;
                }
                (
                    row.epoch,
                    [
                        u8::from(matches!(w, Dependency::Function(_))) * 32,
                        row.values
                            .iter()
                            .filter(|v| matches!(v, Value::Int(_)))
                            .count()
                            .min(32) as u8,
                        u8::from(row.values.iter().any(|v| matches!(v, Value::Int(0)))) * 32,
                        row.values
                            .iter()
                            .find_map(|v| {
                                if let Value::Int(i) = v {
                                    Some(i.unsigned_abs().min(31) as u8)
                                } else {
                                    None
                                }
                            })
                            .unwrap_or(32),
                    ],
                )
            };
            records.push(SourceHeader {
                source: Some(w),
                version: epoch,
                initial: initial.contains(&w),
                dynamics,
            });
        }
        self.stats.snapshot_builds += 1;
        let rows = Arc::new(records);
        self.snapshots.insert(table, (version, rows.clone()));
        Ok(rows)
    }
}

struct RowInput<'a> {
    m: &'a Model,
    rid: usize,
    state: &'a [f32; H],
    base: [u8; N],
    epoch: u64,
    watermark: u64,
}
impl RowInput<'_> {
    fn feature(&self, h: &SourceHeader) -> [u8; N] {
        let mut v = self.base;
        if h.source.is_some() {
            v[5] = 32 * u8::from(h.version >= self.watermark);
            if !self.m.certified_inputs {
                v[6] = self.epoch.saturating_sub(h.version).min(32) as u8;
                v[7] = 32 * u8::from(h.initial);
                v[8] = h.dynamics[0];
                v[10] = h.dynamics[1];
                v[11] = h.dynamics[2];
                v[12] = h.dynamics[3];
            }
        }
        v
    }
    fn score_batch(&self, sources: &[SourceHeader], out: &mut [f32], memo: bool) -> u64 {
        let mut evaluations = 0;
        if memo && self.m.certified_inputs {
            let mut saved = [None, None];
            for (h, v) in sources.iter().zip(out) {
                let group = usize::from(h.source.is_some() && h.version >= self.watermark);
                *v = *saved[group].get_or_insert_with(|| {
                    evaluations += 1;
                    self.m.score(&self.feature(h), self.rid, self.state)
                });
            }
        } else if memo {
            let mut saved = rustc_hash::FxHashMap::default();
            for (h, v) in sources.iter().zip(out) {
                let f = self.feature(h);
                *v = *saved.entry(f).or_insert_with(|| {
                    evaluations += 1;
                    self.m.score(&f, self.rid, self.state)
                });
            }
        } else {
            for (h, v) in sources.iter().zip(out) {
                *v = self.m.score(&self.feature(h), self.rid, self.state);
            }
            evaluations = sources.len() as u64;
        }
        evaluations
    }

    fn execute(
        &self,
        sources: &[SourceHeader],
        out: &mut [f32],
        action: usize,
        pool: Option<&rayon::ThreadPool>,
    ) -> (u64, u64) {
        if sources.is_empty() {
            return (0, 0);
        }
        let lanes = width(action).min(sources.len());
        let memo = action >= 4;
        if lanes == 1 {
            return (self.score_batch(sources, out, memo), 1);
        }
        let block = sources.len().div_ceil(lanes);
        if let Some(workers) = pool {
            workers.install(|| {
                out.par_chunks_mut(block)
                    .zip(sources.par_chunks(block))
                    .map(|(target, subset)| {
                        let id = rayon::current_thread_index().unwrap_or(0);
                        (self.score_batch(subset, target, memo), 1u64 << id)
                    })
                    .reduce(|| (0, 0), |(a, b), (c, d)| (a + c, b | d))
            })
        } else {
            (
                out.chunks_mut(block)
                    .zip(sources.chunks(block))
                    .map(|(target, subset)| self.score_batch(subset, target, memo))
                    .sum(),
                1,
            )
        }
    }
}
impl Trial {
    pub(crate) fn configure_rows(&mut self, spec: &J, audit: bool) -> Result<()> {
        self.rows.detailed = audit;
        if spec.is_null() {
            return Ok(());
        }
        let max = spec["max_rows"].as_u64().unwrap_or(1) as usize;
        let workers = spec["workers"].as_u64().unwrap_or(1) as usize;
        if ![1, 2, 4, 8].contains(&max) || !(1..=8).contains(&workers) {
            return Err("row configuration out of range".into());
        }
        let fixed = spec["action"].as_u64().map(|v| v as usize);
        if fixed.is_some_and(|a| a >= ACTIONS || width(a) > max) {
            return Err("fixed width exceeds max rows".into());
        }
        let model = spec
            .get("policy")
            .map(|v| serde_json::from_value::<RowModel>(v.clone()))
            .transpose()
            .map_err(|e| e.to_string())?;
        if model.as_ref().is_some_and(|m| !m.valid()) {
            return Err("incompatible row policy weights".into());
        }
        self.rows.prefilter = spec["prefilter"].as_u64().unwrap_or(0) as usize;
        if self.rows.prefilter > 2 {
            return Err("unknown pre-issuance proof".into());
        }
        self.rows.verify.mode = spec["verify"].as_u64().unwrap_or(0) as usize;
        if self.rows.verify.mode > 4 {
            return Err("unknown verifier specialization".into());
        }
        self.rows.batch = spec["batch"].as_bool() == Some(true);
        self.rows.active = true;
        self.rows.max_rows = max;
        self.rows.workers = workers;
        self.rows.fixed = fixed;
        self.rows.model = model;
        self.rows.capture = spec["capture"].as_bool() == Some(true);
        self.rows.profile = spec["profile"].as_bool() == Some(true);
        self.rows.prune = spec["prune"].as_bool() != Some(false);
        self.rows.seed = spec["seed"].as_u64().unwrap_or(19);
        if workers > 1 {
            self.rows.pool = Some(
                rayon::ThreadPoolBuilder::new()
                    .num_threads(workers)
                    .build()
                    .map_err(|e| e.to_string())?,
            )
        }
        Ok(())
    }

    fn generate_rows(
        &mut self,
        g: &Graph,
        rid: usize,
        wm: u64,
        p: &Plan,
    ) -> Result<(Vec<(Token, [u8; N], bool)>, usize, f32, usize)> {
        let r = &g.program.rules[rid];
        let phase = self.rows.profile.then(RowClock::now);
        let mut base = self.features(g, r, p, None, wm);
        if let Some(pivot) = p.pivot {
            base[9] = r.query[pivot].args.len().min(32) as u8;
            base[13] = r.query[pivot]
                .args
                .iter()
                .filter(|a| matches!(a, Arg::Literal(_)))
                .count()
                .min(32) as u8;
        }
        let model = self
            .policy
            .as_ref()
            .ok_or("adaptive rows require trained weights")?;
        if self.mode != "learned" {
            return Err("adaptive rows need a real selection head".into());
        }
        let nullary = [SourceHeader {
            source: None,
            version: 0,
            initial: false,
            dynamics: [0; 4],
        }];
        let keep;
        if self.rows.prefilter != 0
            && r.query
                .iter()
                .any(|a| matches!(a.call,Call::Table(t) if g.witness_count(t)==0))
        {
            self.rows.stats.proof_empty_calls += 1;
            return Ok((vec![], 0, 0., 0));
        }
        let sources: &[SourceHeader] = if let Some(pivot) = p.pivot {
            let Call::Table(t) = r.query[pivot].call else {
                return Err("unexpected non-table pivot".into());
            };
            keep = self
                .rows
                .snapshot(g, t, &self.initial, model.certified_inputs)?;
            &keep
        } else {
            &nullary
        };
        let filtered: Vec<SourceHeader>;
        // If no other table can meet the watermark, every valid source binding requires
        // a fresh pivot. Filter the input address bank BEFORE feature scoring or issue.
        let can_prefilter = self.rows.prefilter == 2
            && r.seminaive
            && p.pivot.is_some()
            && wm != 0
            && p.order.iter().all(|&index| match r.query[index].call {
                Call::Table(t) => self.rows.verify.frontier(g, t) < wm,
                _ => true,
            });
        let sources = if can_prefilter {
            filtered = sources
                .iter()
                .copied()
                .filter(|v| v.version >= wm)
                .collect();
            self.rows.stats.proof_stale_headers += (sources.len() - filtered.len()) as u64;
            self.rows.stats.proof_block_calls += 1;
            filtered.as_slice()
        } else {
            sources
        };
        let n = sources.len();
        let input = RowInput {
            m: model,
            rid,
            state: &self.state,
            base,
            epoch: g.epoch,
            watermark: wm,
        };
        let x = [
            (1. + n as f32).log2() / 12.,
            base[1] as f32 / 16.,
            base[2] as f32 / 16.,
            u8::from(model.certified_inputs) as f32,
            self.state[0],
        ];
        let action = if let Some(f) = self.rows.fixed {
            f
        } else if let Some(policy) = &self.rows.model {
            policy.action(&x, self.rows.max_rows)
        } else if n > 128 {
            4
        } else {
            0
        };
        if let Some(t) = phase {
            self.rows.phase[0] += t.elapsed().as_nanos() as u64;
        }
        let t = self.rows.profile.then(RowClock::now);
        let mut scores = vec![0.; n];
        let (evals, participants) =
            input.execute(sources, &mut scores, action, self.rows.pool.as_ref());
        // Offline timing labels. Every treatment reads exactly the same causal feature bank and
        // preceding neural state. Off-policy oracle trials never contribute emitted proposals.
        if self.rows.capture
            && n != 0
            && (self
                .rows
                .stats
                .invocations
                .wrapping_mul(6364136223846793005)
                .wrapping_add(self.rows.seed)
                >> 60)
                < 2
        {
            let mut costs = [0u64; ACTIONS];
            let rotation = (self.rows.stats.invocations as usize) % ACTIONS;
            let mut scratch = vec![0.; n];
            for k in 0..ACTIONS {
                let a = (rotation + k) % ACTIONS;
                let start = RowClock::now();
                input.execute(sources, &mut scratch, a, self.rows.pool.as_ref());
                costs[a] = start.elapsed().as_nanos() as u64;
                if scratch != scores {
                    return Err("row partition changed candidate logits".into());
                }
            }
            self.rows.examples.push((x, costs));
        }
        if let Some(t) = t {
            self.rows.phase[1] += t.elapsed().as_nanos() as u64;
        }
        self.rows.stats.invocations += 1;
        self.rows.stats.source_headers += n as u64;
        self.rows.stats.calls[action] += 1;
        self.rows.stats.addressed[action] += n as u64;
        self.rows.stats.evaluations += evals;
        let workers = participants.count_ones();
        self.rows.stats.peak_workers = self.rows.stats.peak_workers.max(workers);
        self.rows.stats.real_parallel_calls += u64::from(workers > 1);
        let t = self.rows.profile.then(RowClock::now);
        let sole = r.seminaive
            && p.pivot.is_some()
            && p.order
                .iter()
                .all(|&a| matches!(r.query[a].call, Call::Primitive(..)));
        let mut result = Vec::new();
        let mut emitted = 0;
        let mut fresh_total = 0.;
        for (h, score) in sources.iter().zip(scores) {
            let fresh = h.source.is_some() && h.version >= wm;
            fresh_total += u8::from(fresh) as f32;
            let send = score >= self.floors[rid];
            if !send && model.certified_inputs {
                if !sole || fresh {
                    return Err("row policy violated certified score bound".into());
                }
                self.guard_counts[0] += 1;
            }
            self.serial += 1;
            if self.rows.detailed {
                self.rows
                    .observe(self.serial, h.source, h.version, rid, score, send);
            }
            if !send && !self.residual {
                continue;
            }
            let recipe = if send && !self.rows.batch {
                crate::joint_root::issue(
                    "single",
                    g.epoch,
                    rid,
                    h.source
                        .zip(p.pivot)
                        .map(|(row, atom)| crate::joint_root::Ref {
                            atom,
                            row,
                            version: h.version,
                        })
                        .into_iter(),
                )
            } else {
                None
            };
            let token = Token {
                recipe,
                id: self.serial,
                rid,
                w: h.source,
                version: h.version,
                initial: h.initial,
                score,
                guarded: false,
            };
            result.push((token, base, send));
            emitted += usize::from(send);
        }
        if self.rows.batch && !result.is_empty() {
            let block = result.len().div_ceil(width(action));
            for shard in result.chunks_mut(block) {
                let frozen: Vec<_> = shard
                    .iter()
                    .filter(|(_, _, send)| *send)
                    .map(|(t, _, _)| (t.w, t.version))
                    .collect();
                if let Some(page) = crate::joint_root::single_page(g.epoch, rid, p.pivot, &frozen) {
                    for (i, (t, _, _)) in shard.iter_mut().filter(|(_, _, send)| *send).enumerate()
                    {
                        t.recipe = Some(page.at(i));
                    }
                }
            }
        }
        self.rows.stats.emitted += emitted as u64;
        if let Some(t) = t {
            self.rows.phase[2] += t.elapsed().as_nanos() as u64
        }
        Ok((result, emitted, fresh_total, n))
    }
}
