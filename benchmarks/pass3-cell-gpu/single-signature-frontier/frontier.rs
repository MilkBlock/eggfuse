use crate::single_witness::SourceHeader;
type EpochKey = (usize, usize);
const DIR_BYTES: usize = (1 << B) * std::mem::size_of::<u64>();
#[derive(Clone)]
enum KeyPart {
    Port(usize),
    Constant(Value),
}
#[derive(Clone)]
struct EpochAtom {
    table: usize,
    fields: Vec<(usize, KeyPart)>,
}
#[derive(Default, Clone, Serialize)]
struct FrontierCounts {
    calls: u64,
    sources: u64,
    old: u64,
    unrestricted: u64,
    admitted: u64,
    all_old: u64,
    exact: u64,
    hashed: u64,
    existing: u64,
    existing_frame: u64,
    groups: u64,
    dead_groups: u64,
    dead_calls: u64,
    native_columns: u64,
    private_columns: u64,
    fresh_suffix_rows: u64,
    suffix_rows: u64,
    build_rows: u64,
    broadcasts: u64,
    group_hits: u64,
    source_reads: u64,
    frame_hits: u64,
    probes: u64,
    pruned: u64,
    peak_payload_bytes: usize,
}
#[derive(Default)]
struct SingleEpochs {
    enabled: bool,
    oracle: bool,
    budget: usize,
    min_old: usize,
    density: usize,
    scan_ratio: usize,
    plans: HashMap<usize, Rc<Vec<EpochAtom>>>,
    counts: BTreeMap<usize, FrontierCounts>,
    private: HashMap<EpochKey, (u64, u64, Rc<Vec<u64>>)>,
    native_marks: HashMap<EpochKey, (u64, u64)>,
}
impl SingleEpochs {
    fn report(&self) -> Json {
        json!({"rules":self.counts,"max_bytes":self.budget})
    }
}
pub fn configure_single_epochs(spec: &serde_json::Map<String, Json>) -> Result<()> {
    STORE.with(|cell| {
        let mut st = cell.borrow_mut();
        let s = &mut st.as_mut().ok_or("missing multi model")?.single_epochs;
        s.enabled = true;
        s.oracle = spec.get("oracle").and_then(Json::as_bool).unwrap_or(false);
        s.budget = spec.get("bytes").and_then(Json::as_u64).unwrap_or(0) as usize;
        s.min_old = spec.get("min_old").and_then(Json::as_u64).unwrap_or(1) as usize;
        s.density = spec.get("density").and_then(Json::as_u64).unwrap_or(0) as usize;
        s.scan_ratio = spec.get("scan_ratio").and_then(Json::as_u64).unwrap_or(2) as usize;
        Ok(())
    })
}
fn epoch_plan(r: &Rule, pivot: usize, order: &[usize]) -> Vec<EpochAtom> {
    let piv = &r.query[pivot].args;
    order
        .iter()
        .filter_map(|&id| {
            let atom = &r.query[id];
            let Call::Table(table) = atom.call else {
                return None;
            };
            let fields = atom
                .args
                .iter()
                .enumerate()
                .filter_map(|(col, arg)| {
                    let src = match arg {
                        Arg::Slot(s) => KeyPart::Port(
                            piv.iter().position(|a| matches!(a,Arg::Slot(x) if x==s))?,
                        ),
                        Arg::Literal(v) => KeyPart::Constant(v.clone()),
                    };
                    Some((col, src))
                })
                .collect();
            Some(EpochAtom { table, fields })
        })
        .collect()
}
struct ProofAtom {
    parts: Vec<KeyPart>,
    cols: Vec<(bool, Option<Rc<Vec<u64>>>)>,
    exact: std::collections::HashSet<Vec<Value>>,
}
#[inline]
fn input<'a>(part: &'a KeyPart, row: &'a Row) -> &'a Value {
    match part {
        KeyPart::Port(i) => &row.values[*i],
        KeyPart::Constant(v) => v,
    }
}

pub(crate) fn single_epoch_filter(
    g: &Graph,
    rid: usize,
    pivot: usize,
    order: &[usize],
    live: &[bool],
    wm: u64,
    bank: &[SourceHeader],
) -> Result<Option<Vec<SourceHeader>>> {
    STORE.with(|cell| {
        let mut st = cell.borrow_mut();
        let s = st.as_mut().ok_or("missing generator")?;
        let state = &mut s.single_epochs;
        if !state.enabled {
            return Ok(None);
        }
        let counts = state.counts.entry(rid).or_default();
        counts.calls += 1;
        counts.sources += bank.len() as u64;
        let old = bank.iter().filter(|x| x.version < wm).count();
        counts.old += old as u64;
        if old == 0 {
            return Ok(None);
        }
        if old == bank.len() {
            counts.all_old += 1
        }
        if !state.oracle && (old < state.min_old || old * 100 < bank.len() * state.density) {
            return Ok(None);
        }
        let r = &g.program.rules[rid];
        let plan = state
            .plans
            .entry(rid)
            .or_insert_with(|| Rc::new(epoch_plan(r, pivot, order)))
            .clone();
        let Some(codes) = s.baked_codes.as_ref() else {
            return Err("epoch projections require pinned baked weights".into());
        };
        let code = |v: &Value| codes.port(v, s.views).key as usize;
        let Call::Table(owner) = r.query[pivot].call else {
            return Ok(None);
        };
        let jun = g.stats.unions;
        state
            .private
            .retain(|(t, _), (v, u, _)| *v == g.query_versions[*t] && *u == jun);
        let cached = |t: usize| {
            s.frames
                .get(&t)
                .filter(|f| f.generation == g.query_versions[t] && f.born_at_union == jun)
        };
        let mut proofs = vec![];
        let mut scanned = 0usize;
        for (atom, &fresh) in plan.iter().zip(live) {
            if !fresh {
                continue;
            }
            let t = atom.table;
            let generation = g.query_versions[t];
            let f = cached(t);
            // Do not decode a cold table merely to rule it globally old in the production policy.
            let global = f.map(|f| f.max_epoch);
            if global.is_some_and(|x| x < wm) {
                continue;
            }
            let mut field_keys = vec![];
            let mut cols = vec![];
            let mut needs_rows = state.oracle;
            for (col, part) in &atom.fields {
                let k = (t, *col);
                let natural = s
                    .neural_columns
                    .high
                    .get(&k)
                    .filter(|(v, _)| {
                        *v == generation && state.native_marks.get(&k) == Some(&(generation, jun))
                    })
                    .map(|(_, rc)| rc.clone());
                let local = state.private.get(&k).map(|(_, _, rc)| rc.clone());
                if natural.is_some() {
                    counts.native_columns += 1
                } else if local.is_some() {
                    counts.private_columns += 1
                }
                let native = natural.is_some();
                let available = natural.or(local);
                if available.is_none()
                    && state.budget / DIR_BYTES > state.private.len()
                    && g.witness_count(t)
                        <= old.saturating_mul(state.scan_ratio).saturating_sub(scanned)
                {
                    needs_rows = true
                }
                field_keys.push(match part {
                    KeyPart::Port(i) => KeyPart::Port(*i),
                    KeyPart::Constant(v) => KeyPart::Constant(canon(v, &g.parents)),
                });
                cols.push((native, available));
            }
            let mut exact = std::collections::HashSet::new();
            if needs_rows {
                let cold;
                let rows = if let Some(f) = f {
                    &f.rows
                } else {
                    cold = g
                        .witnesses(t)
                        .into_iter()
                        .map(|w| g.row(w))
                        .collect::<Result<Vec<_>>>()?
                        .into_iter()
                        .flatten()
                        .filter(|row| !row.hidden)
                        .collect();
                    &cold
                };
                scanned += rows.len();
                counts.build_rows += rows.len() as u64;
                if rows.iter().all(|r| r.epoch < wm) {
                    continue;
                }
                if state.oracle {
                    counts.suffix_rows += rows.len() as u64;
                    for row in rows.iter().filter(|r| r.epoch >= wm) {
                        counts.fresh_suffix_rows += 1;
                        exact.insert(
                            atom.fields
                                .iter()
                                .map(|(j, _)| row.values[*j].clone())
                                .collect(),
                        );
                    }
                }
                for ((col, _), (_, dir)) in atom.fields.iter().zip(cols.iter_mut()) {
                    if dir.is_some() {
                        continue;
                    }
                    if !state.oracle && state.private.len() >= state.budget / DIR_BYTES {
                        continue;
                    }
                    let mut a = vec![0; 1 << B];
                    for row in rows {
                        let j = code(&row.values[*col]);
                        a[j] = a[j].max(row.epoch)
                    }
                    let a = Rc::new(a);
                    if !state.oracle {
                        state
                            .private
                            .insert((t, *col), (generation, jun, a.clone()));
                    }
                    *dir = Some(a);
                }
            }
            if field_keys.is_empty() || (!state.oracle && cols.iter().all(|v| v.1.is_none())) {
                counts.unrestricted += 1;
                return Ok(None);
            }
            proofs.push(ProofAtom {
                parts: field_keys,
                cols,
                exact,
            });
        }
        if proofs.is_empty() {
            return Ok(None);
        }
        counts.admitted += 1;
        counts.peak_payload_bytes = counts
            .peak_payload_bytes
            .max(state.private.len() * DIR_BYTES);
        let frame = cached(owner);
        let mut keep = Vec::new();
        let mut all = 0;
        let mut pivot_columns = std::collections::BTreeSet::new();
        if !state.oracle {
            for atom in &proofs {
                for (part, (_, dir)) in atom.parts.iter().zip(&atom.cols) {
                    if dir.is_some()
                        && let KeyPart::Port(col) = part
                    {
                        pivot_columns.insert(*col);
                    }
                }
            }
        }
        let shared =
            (!state.oracle && pivot_columns.len() == 1).then(|| *pivot_columns.first().unwrap());
        let mut verdicts = [0u8; 1 << B];

        let mut groups = std::collections::HashSet::new();
        let mut dead_groups = std::collections::HashSet::new();
        for (i, h) in bank.iter().enumerate() {
            if h.version >= wm {
                if !state.oracle {
                    keep.push(*h)
                }
                continue;
            }
            let src = h.source.ok_or("missing pivot address")?;
            let fallback;
            let row = if let Some(r) = frame
                .and_then(|f| f.rows.get(i))
                .filter(|r| r.witness == src && r.epoch == h.version)
            {
                counts.frame_hits += 1;
                r
            } else {
                counts.source_reads += 1;
                fallback = g.row(src)?.ok_or("missing signed pivot")?;
                &fallback
            };
            if let Some(col) = shared {
                let key = code(&row.values[col]);
                let mut decision = verdicts[key];
                if decision == 0 {
                    counts.broadcasts += 1;
                    let mut possible = false;
                    for atom in &proofs {
                        let mut reachable = true;
                        for (part, (_, dir)) in atom.parts.iter().zip(&atom.cols) {
                            if let Some(hi) = dir {
                                counts.probes += 1;
                                let sub = match part {
                                    KeyPart::Port(_) => key,
                                    KeyPart::Constant(v) => code(v),
                                };
                                if hi[sub] < wm {
                                    reachable = false;
                                    break;
                                }
                            }
                        }
                        if reachable {
                            possible = true;
                            break;
                        }
                    }
                    decision = if possible { 1 } else { 2 };
                    verdicts[key] = decision;
                } else {
                    counts.group_hits += 1
                }
                if decision == 1 {
                    keep.push(*h)
                } else {
                    counts.hashed += 1;
                    all += 1
                }
                continue;
            }
            let mut any_exact = false;
            let mut any_hash = false;
            let mut any_native = false;
            let mut group = Vec::new();
            for atom in &proofs {
                let mut hash = true;
                let mut cached_hash = true;
                let mut raw = Vec::new();
                for (part, (natural, dir)) in atom.parts.iter().zip(&atom.cols) {
                    let v = input(part, row);
                    let key = code(v);
                    if state.oracle {
                        group.push(key as u16);
                        raw.push(v.clone())
                    }
                    if let Some(hi) = dir {
                        counts.probes += 1;
                        if hi[key] < wm {
                            hash = false;
                            if *natural {
                                cached_hash = false
                            }
                            if !state.oracle {
                                break;
                            }
                        }
                    }
                }
                if state.oracle && atom.exact.contains(&raw) {
                    any_exact = true
                }
                any_hash |= hash;
                any_native |= cached_hash;
                if !state.oracle && hash {
                    break;
                }
            }
            if state.oracle {
                if !any_exact {
                    counts.exact += 1
                }
                if !any_native {
                    counts.existing += 1;
                    if frame.is_some() {
                        counts.existing_frame += 1
                    }
                }
                groups.insert(group.clone());
                if !any_hash {
                    dead_groups.insert(group);
                }
                if !any_hash && any_exact {
                    return Err("unsafe epoch bucket negative".into());
                }
            }
            if !any_hash {
                counts.hashed += 1;
                all += 1
            } else if !state.oracle {
                keep.push(*h)
            }
        }
        counts.groups += groups.len() as u64;
        counts.dead_groups += dead_groups.len() as u64;
        if all == bank.len() {
            counts.dead_calls += 1
        }
        if !state.oracle && all > 0 {
            counts.pruned += all as u64;
            Ok(Some(keep))
        } else {
            Ok(None)
        }
    })
}
