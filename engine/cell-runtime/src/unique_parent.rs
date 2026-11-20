//! Instantiate the compiler's exhaustive, zero-expansion stage-entry certificate.
//! Only the identity of the second witness is predicted. Native graph reads are
//! authoritative for visibility, canonical keys, delta legality and completion.
use crate::{
    cell::{Instance, QueryFacts, bind_query, query_operand},
    graph::{Dependency, Graph},
    program::{Arg, Call, Op, Program, Result},
    value::{Value, canon},
};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet, hash_map::DefaultHasher},
    ffi::{CString, c_char, c_void},
    hash::{Hash, Hasher},
    path::Path,
    ptr::NonNull,
    time::Instant,
};

#[derive(Clone)]
struct Plan {
    pivot: usize,
    source: usize,
    target: usize,
    columns: Vec<Arg>,
}

fn plans(p: &Program) -> Vec<Option<Plan>> {
    let mut out = vec![None; p.rules.len()];
    for (rid, pivot, steps) in &p.multi_stage.stage_entries {
        let rule = &p.rules[*rid];
        if rule.query.len() != 2 || steps.as_slice() != [1 - *pivot] || out[*rid].is_some() {
            continue;
        }
        let a = &rule.query[*pivot];
        let b = &rule.query[1 - *pivot];
        let (Call::Table(source), Call::Table(target)) = (&a.call, &b.call) else {
            continue;
        };
        let Some((_, key)) = b.args.split_last() else {
            continue;
        };
        if !key.iter().any(|v| matches!(v, Arg::Slot(_))) {
            continue;
        }
        let cols = key
            .iter()
            .map(|arg| match arg {
                Arg::Slot(_) => a.args.iter().position(|v| v == arg).map(Arg::Slot),
                Arg::Literal(v) => Some(Arg::Literal(v.clone())),
            })
            .collect::<Option<Vec<_>>>();
        if let Some(columns) = cols {
            out[*rid] = Some(Plan {
                pivot: *pivot,
                source: *source,
                target: *target,
                columns,
            });
        }
    }
    out
}

#[derive(Default, Serialize)]
pub struct Counts {
    pub fine_timing: bool,
    pub admitted_rules: usize,
    pub executed_rules: BTreeSet<usize>,
    pub rule_occurrences: u64,
    pub anchors: u64,
    pub proposals: u64,
    pub abstentions: u64,
    pub verified_parent: u64,
    #[cfg(feature = "slot-transfer-audit")]
    pub audited_parent_addresses: u64,
    #[cfg(feature = "slot-transfer-audit")]
    pub ambiguous_present_keys: u64,
    #[cfg(feature = "slot-transfer-audit")]
    pub true_parent_code_mismatch: u64,
    #[cfg(feature = "slot-transfer-audit")]
    pub absent_parent_keys: u64,
    #[cfg(feature = "slot-transfer-audit")]
    pub wrong_identical_code: u64,
    #[cfg(feature = "slot-transfer-audit")]
    pub wrong_primary_only: u64,
    #[cfg(feature = "slot-transfer-audit")]
    pub wrong_other_score: u64,
    pub wrong_parent: u64,
    pub exact_probes: u64,
    pub fallback_probes: u64,
    pub bindings: u64,
    pub from_proposal: u64,
    pub missed_by_abstention: u64,
    pub recovered_wrong_parent: u64,
    pub batches: u64,
    pub dispatches: u64,
    pub scored_positions: u64,
    pub initialized_tables: u64,
    pub seeded_rows: u64,
    pub patched_rows: u64,
    pub port_seconds: f64,
    pub forward_seconds: f64,
    pub device_seconds: f64,
    pub verify_seconds: f64,
    pub fallback_seconds: f64,
    pub direct_seconds: f64,
}
#[derive(Default)]
struct Bank {
    initialized: bool,
    refs: Vec<Dependency>,
    #[cfg(feature = "slot-transfer-audit")]
    codes: Vec<Vec<i32>>,
    ids: BTreeMap<Dependency, usize>,
    changed: BTreeSet<Dependency>,
}

unsafe extern "C" {
    fn cell_ports_open(source: *const c_char, weights: *const f32, n: usize) -> *mut c_void;
    fn cell_gpu_close(ptr: *mut c_void);
    fn cell_ports_patch(
        ptr: *mut c_void,
        t: i32,
        width: i32,
        cap: i32,
        slots: *const i32,
        rows: *const i32,
        n: i32,
    ) -> i32;
    fn cell_ports_predict(
        ptr: *mut c_void,
        desc: *const i32,
        n: i32,
        cols: *const i32,
        count: i32,
        out: *mut i32,
        gpu: *mut f64,
    ) -> i32;
}

#[derive(Clone, Copy, Default, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Signal {
    #[default]
    Single,
    DoubleHash,
    SourceRole,
}
impl Signal {
    fn books(self) -> usize {
        if self == Self::Single { 1 } else { 2 }
    }

    fn encode(self, g: &Graph, v: &Value) -> i32 {
        let mut h = DefaultHasher::new();
        v.hash(&mut h);
        let hash = h.finish();
        let second = match self {
            Self::Single => 0,
            Self::DoubleHash => {
                let mut second = DefaultHasher::new();
                0x7072_6f76_656e_616eu64.hash(&mut second);
                v.hash(&mut second);
                (second.finish() & 127) as i32
            }
            Self::SourceRole => self.role(g, v),
        };
        (hash as i32 & 127) | (second << 7)
    }

    // A dynamic constructor output carries its originating frame and SSA slot.
    // Imported roots and released frames have an explicit unknown role.
    fn role(self, g: &Graph, v: &Value) -> i32 {
        let Value::Eq(id) = v else { return 0 };
        let cell = (id >> 32) as u32;
        let slot = (*id as u32).checked_sub(1);
        if cell == 0 {
            return 0;
        }
        let Some(frame) = g.cells.get(&cell) else {
            return 0;
        };
        let template = &g.program.templates[frame.template];
        let Some(op) = slot.and_then(|s| template.defs.get(&(s as usize))) else {
            return 0;
        };
        let Op::Let(_, Call::Table(t), _) = &template.ops[*op] else {
            return 0;
        };
        let mut h = DefaultHasher::new();
        g.program.tables[*t].name.hash(&mut h);
        (h.finish() % 127 + 1) as i32
    }
}

#[derive(Deserialize)]
struct Weights {
    schema: String,
    #[serde(default)]
    signal: Signal,
    dim: usize,
    buckets: usize,
    embedding: Vec<Vec<f32>>,
    null: f32,
}
struct Model {
    signal: Signal,
    device: NonNull<c_void>,
    banks: Vec<Bank>,
}
impl Drop for Model {
    fn drop(&mut self) {
        unsafe { cell_gpu_close(self.device.as_ptr()) }
    }
}
fn addr(n: usize) -> Result<i32> {
    i32::try_from(n).map_err(|_| "resident port address overflow".into())
}
impl Model {
    fn open(path: &Path, tables: usize) -> Result<Self> {
        let weights: Weights =
            serde_json::from_slice(&std::fs::read(path).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
        let books = weights.signal.books();
        let supported = match weights.schema.as_str() {
            "port-pointer/v1" => weights.signal == Signal::Single && weights.dim == 8,
            "port-pointer/v2" => matches!((books, weights.dim), (1, 8 | 16) | (2, 8)),
            _ => false,
        };
        if !supported
            || weights.buckets != 128
            || weights.embedding.len() != 128 * books
            || !weights.null.is_finite()
            || !weights
                .embedding
                .iter()
                .all(|v| v.len() == weights.dim && v.iter().all(|x| x.is_finite()))
        {
            return Err("invalid parent pointer weights".into());
        }
        let mut values: Vec<_> = weights.embedding.into_iter().flatten().collect();
        values.push(weights.null);
        let code = CString::new(format!(
            "#define PORT_DIM {}\n#define PORT_BOOKS {}\n{}",
            weights.dim,
            books,
            include_str!("parent_pointer.metal")
        ))
        .unwrap();
        let device =
            NonNull::new(unsafe { cell_ports_open(code.as_ptr(), values.as_ptr(), values.len()) })
                .ok_or("cannot initialize resident parent model")?;
        Ok(Self {
            signal: weights.signal,
            device,
            banks: (0..tables).map(|_| Bank::default()).collect(),
        })
    }
    fn sync(&mut self, g: &Graph, t: usize, c: &mut Counts) -> Result<()> {
        let bank = &mut self.banks[t];
        if bank.initialized && bank.changed.is_empty() {
            return Ok(());
        }
        let first = !bank.initialized;
        let pending = if first {
            g.witnesses(t)
        } else {
            std::mem::take(&mut bank.changed).into_iter().collect()
        };
        let width = g.program.tables[t].schema.len() + 1;
        let mut slots = Vec::new();
        let mut data = Vec::new();
        for w in pending {
            let row = g.row(w)?.filter(|r| r.table == t && !r.hidden);
            let slot = if let Some(&i) = bank.ids.get(&w) {
                i
            } else if row.is_some() {
                let i = bank.refs.len();
                bank.refs.push(w);
                bank.ids.insert(w, i);
                i
            } else {
                continue;
            };
            slots.push(addr(slot)?);
            if let Some(row) = row {
                if row.values.len() + 1 != width {
                    return Err("resident port schema mismatch".into());
                }
                data.push(1);
                data.extend(row.values.iter().map(|v| self.signal.encode(g, v)));
            } else {
                data.resize(data.len() + width, 0);
            }
            #[cfg(feature = "slot-transfer-audit")]
            {
                if bank.codes.len() <= slot {
                    bank.codes.resize_with(slot + 1, Vec::new);
                }
                bank.codes[slot] = data[data.len() - width..].to_vec();
            }
        }
        if unsafe {
            cell_ports_patch(
                self.device.as_ptr(),
                addr(t)?,
                addr(width)?,
                addr(bank.refs.len())?,
                slots.as_ptr(),
                data.as_ptr(),
                addr(slots.len())?,
            )
        } != 0
        {
            return Err("resident Metal port update failed".into());
        }
        if first {
            c.initialized_tables += 1;
            c.seeded_rows += slots.len() as u64;
        } else {
            c.patched_rows += slots.len() as u64;
        }
        bank.initialized = true;
        Ok(())
    }
    fn predict(
        &mut self,
        g: &Graph,
        jobs: &[(usize, u64, QueryFacts)],
        plans: &[Option<Plan>],
        c: &mut Counts,
    ) -> Result<Vec<Vec<i32>>> {
        let prep = Instant::now();
        let mut desc = Vec::new();
        let mut cols = Vec::new();
        let mut sizes = Vec::new();
        let mut total = 0;
        for (rid, _, _) in jobs {
            let p = plans[*rid].as_ref().unwrap();
            self.sync(g, p.source, c)?;
            self.sync(g, p.target, c)?;
            let a = self.banks[p.source].refs.len();
            let b = self.banks[p.target].refs.len();
            let key = p.columns.len();
            if key > 1024 {
                return Err("key exceeds inline Metal descriptor capacity".into());
            }
            desc.extend([
                addr(p.source)?,
                addr(p.target)?,
                addr(a)?,
                addr(g.program.tables[p.source].schema.len() + 1)?,
                addr(g.program.tables[p.target].schema.len() + 1)?,
                addr(b)?,
                addr(key)?,
                addr(cols.len())?,
            ]);
            for op in &p.columns {
                cols.push(match op {
                    Arg::Slot(i) => addr(*i)?,
                    Arg::Literal(v) => -1 - self.signal.encode(g, &canon(v, &g.parents)),
                });
            }
            sizes.push(a);
            total += a;
            c.scored_positions += a as u64 * b as u64;
        }
        let mut result = vec![-1; total];
        c.port_seconds += prep.elapsed().as_secs_f64();
        let now = Instant::now();
        let mut gpu = 0.0;
        if unsafe {
            cell_ports_predict(
                self.device.as_ptr(),
                desc.as_ptr(),
                addr(jobs.len())?,
                cols.as_ptr(),
                addr(total)?,
                result.as_mut_ptr(),
                &mut gpu,
            )
        } != 0
        {
            return Err("resident GPU proposal failed".into());
        }
        c.forward_seconds += now.elapsed().as_secs_f64();
        c.device_seconds += gpu;
        c.batches += 1;
        c.dispatches += sizes.iter().filter(|s| **s > 0).count() as u64;
        let mut it = result.into_iter();
        Ok(sizes
            .into_iter()
            .map(|n| it.by_ref().take(n).collect())
            .collect())
    }
}

pub(super) struct Trial {
    plans: Vec<Option<Plan>>,
    model: Option<Model>,
    pub counts: Counts,
}
impl Trial {
    pub fn new(p: &Program, weights: Option<&Path>) -> Result<Self> {
        let plans = plans(p);
        let counts = Counts {
            admitted_rules: plans.iter().flatten().count(),
            fine_timing: std::env::var_os("EGGFUSE_PARENT_FINE_TIMING").is_some(),
            ..Counts::default()
        };
        Ok(Self {
            plans,
            counts,
            model: weights
                .map(|w| Model::open(w, p.tables.len()))
                .transpose()?,
        })
    }
    pub fn models_parents(&self) -> bool {
        self.model.is_some()
    }
    pub fn eligible(&self) -> Vec<bool> {
        self.plans.iter().map(Option::is_some).collect()
    }
    pub fn publish(&mut self, g: &Graph) {
        if let Some(model) = &mut self.model {
            let start = Instant::now();
            for (t, delta) in g.changes.tables() {
                let b = &mut model.banks[t];
                if b.initialized {
                    b.changed.extend(delta.keys().copied());
                }
            }
            self.counts.port_seconds += start.elapsed().as_secs_f64();
        }
    }
    pub fn run(
        &mut self,
        g: &Graph,
        jobs: Vec<(usize, u64, QueryFacts)>,
        out: &mut BTreeMap<usize, Vec<Instance>>,
    ) -> Result<u64> {
        let mut predictions = if let Some(m) = &mut self.model {
            m.predict(g, &jobs, &self.plans, &mut self.counts)?
                .into_iter()
        } else {
            Vec::new().into_iter()
        };
        let before = self.counts.bindings;
        for (rid, watermark, facts) in jobs {
            let p = self.plans[rid].as_ref().unwrap();
            let rule = &g.program.rules[rid];
            let pivot = p.pivot;
            let a = &rule.query[pivot];
            let b = &rule.query[1 - pivot];
            let key_width = b.args.len() - 1;
            let result = predictions.next();
            let mut bindings = Vec::new();
            let c = &mut self.counts;
            c.executed_rules.insert(rid);
            c.rule_occurrences += 1;
            // Enumerate the authoritative anchor domain, including old anchors:
            // an update on the uniquely keyed target may make the join fresh.
            for source in g.witnesses(p.source) {
                let Some(anchor) = g.row(source)? else {
                    continue;
                };
                if anchor.hidden {
                    continue;
                }
                let mut slots = BTreeMap::new();
                if !a
                    .args
                    .iter()
                    .zip(anchor.values.iter())
                    .all(|(arg, v)| bind_query(arg, v, &mut slots, g))
                {
                    continue;
                }
                let key = b.args[..key_width]
                    .iter()
                    .map(|v| {
                        query_operand(v, &slots, g)
                            .ok_or_else(|| "incomplete compiler key".to_owned())
                    })
                    .collect::<Result<Vec<_>>>()?;
                c.anchors += 1;
                let mut proposed = false;
                let mut accepted = false;
                let row = if let Some(model) = &self.model {
                    let start = c.fine_timing.then(Instant::now);
                    let hint = model.banks[p.source]
                        .ids
                        .get(&source)
                        .and_then(|i| result.as_ref()?.get(*i))
                        .copied()
                        .unwrap_or(-1);
                    #[cfg(feature = "slot-transfer-audit")]
                    let audit_codes = {
                        let src = &model.banks[p.source];
                        let target = &model.banks[p.target];
                        let input = &src.codes[*src
                            .ids
                            .get(&source)
                            .ok_or("missing audited resident anchor")?];
                        let query = p
                            .columns
                            .iter()
                            .map(|a| match a {
                                Arg::Slot(col) => input[1 + col],
                                Arg::Literal(v) => model.signal.encode(g, &canon(v, &g.parents)),
                            })
                            .collect::<Vec<_>>();
                        let truth = g.lookup_canonical(p.target, &key)?.filter(|r| !r.hidden);
                        if let Some(ref parent) = truth {
                            let exact_slot = target
                                .ids
                                .get(&parent.witness)
                                .ok_or("live truth missing from resident bank")?;
                            let exact_code = &target.codes[*exact_slot][1..1 + key_width];
                            if exact_code != query.as_slice() {
                                c.true_parent_code_mismatch += 1;
                            } else if target.codes.iter().enumerate().any(|(i, row)| {
                                i != *exact_slot && row[0] != 0 && row[1..1 + key_width] == query
                            }) {
                                c.ambiguous_present_keys += 1;
                            }
                        } else {
                            c.absent_parent_keys += 1;
                        }
                        (truth, query)
                    };
                    let checked = if hint >= 0 {
                        proposed = true;
                        c.proposals += 1;
                        let w = model.banks[p.target]
                            .refs
                            .get(hint as usize)
                            .ok_or("invalid GPU parent address")?;
                        let current = g.row(*w)?.filter(|r| {
                            r.table == p.target && !r.hidden && r.values[..key_width] == key
                        });
                        // In audit builds only, cross-check the *physical witness*
                        // against a separate directory read. Never select its row.
                        #[cfg(feature = "slot-transfer-audit")]
                        {
                            let (reference, query) = &audit_codes;
                            let same = reference.as_ref().is_some_and(|r| r.witness == *w);
                            if same != current.is_some() {
                                return Err(
                                    "verified parent identity differs from directory".into()
                                );
                            }
                            if !same {
                                let candidate =
                                    &model.banks[p.target].codes[hint as usize][1..1 + key_width];
                                if candidate == query.as_slice() {
                                    c.wrong_identical_code += 1;
                                } else if candidate
                                    .iter()
                                    .zip(query)
                                    .all(|(a, b)| (a & 127) == (b & 127))
                                {
                                    c.wrong_primary_only += 1;
                                } else {
                                    c.wrong_other_score += 1;
                                }
                            }
                            c.audited_parent_addresses += 1;
                        }
                        current
                    } else {
                        c.abstentions += 1;
                        None
                    };
                    if let Some(clock) = start {
                        c.verify_seconds += clock.elapsed().as_secs_f64();
                    }
                    if checked.is_some() {
                        accepted = true;
                        c.verified_parent += 1;
                        checked
                    } else {
                        c.wrong_parent += u64::from(proposed);
                        c.fallback_probes += 1;
                        let start = c.fine_timing.then(Instant::now);
                        let r = g.lookup_canonical(p.target, &key)?;
                        if let Some(clock) = start {
                            c.fallback_seconds += clock.elapsed().as_secs_f64();
                        }
                        r
                    }
                } else {
                    let start = c.fine_timing.then(Instant::now);
                    let r = g.lookup_canonical(p.target, &key)?;
                    if let Some(clock) = start {
                        c.direct_seconds += clock.elapsed().as_secs_f64();
                    }
                    c.exact_probes += 1;
                    r
                };
                let Some(parent) = row else {
                    continue;
                };
                let epoch = anchor.epoch.max(parent.epoch);
                if parent.hidden
                    || (rule.seminaive && epoch < watermark)
                    || !b
                        .args
                        .iter()
                        .zip(parent.values.iter())
                        .all(|(arg, v)| bind_query(arg, v, &mut slots, g))
                {
                    continue;
                }
                if self.model.is_some() {
                    if accepted {
                        c.from_proposal += 1;
                    } else if proposed {
                        c.recovered_wrong_parent += 1;
                    } else {
                        c.missed_by_abstention += 1;
                    }
                }
                let known = facts.with_rows([(pivot, source), (1 - pivot, parent.witness)]);
                bindings.push(Instance::matched(slots.into_iter().collect(), known, epoch));
            }
            c.bindings += bindings.len() as u64;
            out.insert(rid, bindings);
        }
        Ok(self.counts.bindings - before)
    }
}
