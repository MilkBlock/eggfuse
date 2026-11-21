// No reverse reader, actual field value, or repair outcome is an input feature.
const LOC_F: usize = 12;
type LocX = [u8; LOC_F];
#[derive(Clone)]
struct PortSite {
    col: usize,
    slot: Option<usize>,
    alias: Option<usize>,
}
#[derive(Clone)]
struct FactSite {
    op: u32,
    table: usize,
    width: usize,
    eq: u64,
    result: Option<usize>,
    sites: Vec<PortSite>,
}
struct LocatorModel {
    weights: [f32; LOC_F],
    bias: f32,
    threshold: f32,
}
impl LocatorModel {
    fn select(&self, x: &LocX) -> bool {
        self.bias
            + self
                .weights
                .iter()
                .zip(x)
                .map(|(w, v)| w * (*v as f32 / 8.))
                .sum::<f32>()
            >= self.threshold
    }
}
#[derive(Default, serde::Serialize)]
struct LocStats {
    issue_ns: u64,
    verify_ns: u64,
    dispatch_patch_ns: u64,
    nonempty_unions: u64,
    shared_program_hits: u64,
    shared_programs: u64,
    unions: u64,
    owner_found: u64,
    model_fields: u64,
    static_fields: u64,
    proposed_fields: u64,
    facts_proposed: u64,
    verified_facts: u64,
    duplicates: u64,
    partial_or_wrong: u64,
    expired: u64,
    unavailable: u64,
    membership_reject: u64,
    applied: u64,
    patched_fields: u64,
    distinct_certificates: u64,
    other_fields_checked: u64,
    spared_field_tests: u64,
    complete_lists: u64,
    direct_notifications: u64,
    total_readers: u64,
    ordinary_notifications: u64,
    true_positions: u64,
    true_owner_positions: u64,
    true_seed_positions: u64,
    function_positions: u64,
    nested_positions: u64,
    true_proposed: u64,
    false_proposed: u64,
    parent_only_hits: u64,
    truth_work: u64,
    proposed_true_work: u64,
    weighted_patch_work: u64,
    exact_patchable_work: u64,
    audits: u64,
}
struct PortTicket {
    hi: u64,
    lo: u64,
    epoch: u64,
    union: u64,
    version: u64,
    table: usize,
    mask: u64,
    payload: std::rc::Weak<Vec<Value>>,
}
#[derive(Default)]
struct Locator {
    profile: bool,
    bake: bool,
    programs: rustc_hash::FxHashMap<
        (
            usize,
            Option<usize>,
            bool,
            bool,
            bool,
            smallvec::SmallVec<[u32; 4]>,
        ),
        Vec<(u32, usize, u64, u64)>,
    >,
    examples: std::collections::BTreeMap<&'static str, J>,
    mode: u8,
    audit: bool,
    parents: bool,
    plans: Vec<Vec<FactSite>>,
    model: Option<LocatorModel>,
    pending: rustc_hash::FxHashMap<FactRef, PortTicket>,
    labels: std::collections::BTreeMap<LocX, [u64; 2]>,
    stats: LocStats,
}
struct Proposal {
    serial: u64,
    issued_epoch: u64,
    f: FactRef,
    table: usize,
    eq: u64,
    mask: u64,
}
impl Graph {
    pub fn use_union_locator(&mut self, spec: &J, audit: bool) -> Result<()> {
        let mode = spec["mode"].as_u64().ok_or("missing union position mode")?;
        if !(1..=6).contains(&mode) {
            return Err("invalid union position mode".into());
        }
        let model = if matches!(mode, 3 | 4 | 6) {
            let weights: [f32; LOC_F] =
                serde_json::from_value(spec["weights"].clone()).map_err(|e| e.to_string())?;
            let bias = spec["bias"].as_f64().ok_or("missing position bias")? as f32;
            let threshold = spec["threshold"]
                .as_f64()
                .ok_or("missing position threshold")? as f32;
            if !weights
                .iter()
                .chain([&bias, &threshold])
                .all(|v| v.is_finite())
            {
                return Err("nonfinite union position parameters".into());
            }
            Some(LocatorModel {
                weights,
                bias,
                threshold,
            })
        } else {
            None
        };
        let mut plans = Vec::new();
        for t in &self.program.templates {
            let mut copy = rustc_hash::FxHashMap::<usize, usize>::default();
            let mut plan = vec![];
            for (op_id, op) in t.ops.iter().enumerate() {
                if let Op::Copy(dst, Arg::Slot(src)) = op {
                    let source = *copy.get(src).unwrap_or(src);
                    copy.insert(*dst, source);
                    continue;
                }
                let (table, args, out) = match op {
                    Op::Let(dst, Call::Table(t), a) => (*t, a, Arg::Slot(*dst)),
                    Op::Set(t, a, v) => (*t, a, v.clone()),
                    _ => continue,
                };
                let schema = &self.program.tables[table].schema;
                if !self.program.tables[table].virtual_fact
                    || schema.len() > 64
                    || schema.len() != args.len() + 1
                    || !schema.iter().all(|v| {
                        matches!(
                            v["kind"].as_str(),
                            Some(
                                "eq" | "i64"
                                    | "f64"
                                    | "String"
                                    | "Unit"
                                    | "bool"
                                    | "structural_key"
                            )
                        )
                    })
                {
                    continue;
                }
                let mut sites = vec![];
                let mut eq = 0;
                for (i, arg) in args.iter().chain(std::iter::once(&out)).enumerate() {
                    if schema[i]["kind"] != "eq" {
                        continue;
                    }
                    let slot = match arg {
                        Arg::Slot(s) => Some(*s),
                        _ => None,
                    };
                    sites.push(PortSite {
                        col: i,
                        slot,
                        alias: slot.map(|s| *copy.get(&s).unwrap_or(&s)),
                    });
                    eq |= 1u64 << i;
                }
                if eq != 0 {
                    plan.push(FactSite {
                        op: op_id as u32,
                        table,
                        width: schema.len(),
                        eq,
                        result: match out {
                            Arg::Slot(s) => Some(s),
                            _ => None,
                        },
                        sites,
                    });
                }
            }
            plans.push(plan);
        }
        self.locator = Locator {
            mode: mode as u8,
            profile: spec["profile"] == true,
            bake: spec["bake"].as_bool() == Some(true),
            parents: spec["parent_ports"].as_bool().unwrap_or(true),
            audit,
            model,
            plans,
            ..Default::default()
        };
        Ok(())
    }
    pub fn union_location_report(&self) -> J {
        json!({"stats":self.locator.stats,"examples":self.locator.examples,"features":self.locator.labels.iter().collect::<Vec<_>>()})
    }
    fn locate_before_union(&mut self, hi: u64, lo: u64) -> Option<Vec<Dependency>> {
        let mut locator = std::mem::take(&mut self.locator);
        let result = locator.issue(self, hi, lo);
        self.locator = locator;
        result
    }
    fn use_located_port(&mut self, d: Dependency, from: u64, to: u64) -> bool {
        let Dependency::Fact(f) = d else { return false };
        let Some(t) = self.locator.pending.remove(&f) else {
            return false;
        };
        let Some(s) = self
            .cells
            .get_mut(&f.cell)
            .and_then(|c| c.facts.get_mut(&f.op))
        else {
            return false;
        };
        let Some((table, fields)) = &mut s.decoded else {
            return false;
        };
        if t.hi != from
            || t.lo != to
            || t.epoch != self.epoch
            || t.union != self.stats.unions
            || s.hidden
            || t.version != s.epoch
            || t.table != *table
            || t.payload.as_ptr() != std::rc::Rc::as_ptr(fields)
        {
            self.locator.stats.expired += 1;
            return false;
        }
        drop(t.payload);
        let values = std::rc::Rc::make_mut(fields);
        let mut mask = t.mask;
        while mask != 0 {
            let i = mask.trailing_zeros() as usize;
            mask &= mask - 1;
            values[i] = Value::Eq(to);
        }
        self.locator.stats.applied += 1;
        self.locator.stats.patched_fields += t.mask.count_ones() as u64;
        self.locator.stats.weighted_patch_work += values.len() as u64;
        if self.locator.audit {
            let c = &self.cells[&f.cell];
            let state = &c.facts[&f.op];
            let native = self
                .decode_fact(f, c, state)
                .expect("source repair comparison");
            assert_eq!(&native.values, &state.decoded.as_ref().unwrap().1);
            self.locator.stats.audits += 1;
        }
        true
    }
}
fn has_nested(v: &Value, hi: u64) -> u64 {
    match v {
        Value::Eq(x) => u64::from(*x == hi),
        Value::Set(xs) => xs.iter().map(|x| has_nested(x, hi)).sum(),
        _ => 0,
    }
}
impl Locator {
    fn issue(&mut self, g: &Graph, hi: u64, lo: u64) -> Option<Vec<Dependency>> {
        let issue_clock = self.profile.then(std::time::Instant::now);
        self.pending.clear();
        self.stats.unions += 1;
        let owner = (hi >> 32) as u32;
        let orig_slot = (hi as u32).checked_sub(1).map(|s| s as usize);
        let parents = if self.parents {
            crate::joint_root::locator_parents()
        } else {
            smallvec::SmallVec::new()
        };
        let mut cells = smallvec::SmallVec::<[u32; 5]>::new();
        if owner != 0 && g.cells.contains_key(&owner) {
            cells.push(owner);
            self.stats.owner_found += 1;
        }
        for d in &parents {
            if let Dependency::Fact(f) = d
                && !cells.contains(&f.cell)
            {
                cells.push(f.cell);
            }
        }
        let capture = self.mode == 1;
        let observe = self.audit || capture;
        let mut examples = vec![];
        let mut proposals = vec![];
        for &id in &cells {
            let Some(c) = g.cells.get(&id) else { continue };
            let losing = owner != 0 && id == owner;
            let key = if self.bake {
                let mut named: smallvec::SmallVec<[u32; 4]> = parents
                    .iter()
                    .filter_map(|d| match d {
                        Dependency::Fact(f) if f.cell == id => Some(f.op),
                        _ => None,
                    })
                    .collect();
                named.sort_unstable();
                named.dedup();
                Some((
                    c.template,
                    if losing { orig_slot } else { None },
                    losing,
                    c.parent.is_some(),
                    c.started_epoch == g.epoch,
                    named,
                ))
            } else {
                None
            };
            if let Some(list) = key.as_ref().and_then(|k| self.programs.get(k)) {
                self.stats.shared_program_hits += 1;
                for &(op, table, eq, mask) in list {
                    self.stats.proposed_fields += mask.count_ones() as u64;
                    self.stats.facts_proposed += 1;
                    proposals.push(Proposal {
                        serial: g.stats.unions,
                        issued_epoch: g.epoch,
                        f: FactRef { cell: id, op },
                        table,
                        eq,
                        mask,
                    });
                }
                continue;
            }
            let start = proposals.len();
            for site in &self.plans[c.template] {
                let f = FactRef {
                    cell: id,
                    op: site.op,
                };
                let seeded = parents
                    .iter()
                    .any(|d| matches!(d,Dependency::Fact(x) if x.cell==id));
                let named = parents.contains(&Dependency::Fact(f));
                let mut mask = 0u64;
                for port in &site.sites {
                    let flag = |b| if b { 8 } else { 0 };
                    let direct = losing
                        && orig_slot.is_some()
                        && (port.slot == orig_slot || port.alias == orig_slot);
                    let x = [
                        flag(losing),
                        flag(seeded),
                        flag(named),
                        flag(direct),
                        flag(losing && site.result.is_some() && site.result == orig_slot),
                        flag(port.col + 1 == site.width),
                        flag(site.eq.count_ones() == 1),
                        site.eq.count_ones().min(8) as u8,
                        port.col.min(8) as u8,
                        (site.op as usize).min(8) as u8,
                        flag(c.parent.is_some()),
                        flag(c.started_epoch == g.epoch),
                    ];
                    self.stats.static_fields += u64::from(direct);
                    let learned = self.model.as_ref().is_some_and(|m| m.select(&x));
                    self.stats.model_fields += u64::from(self.model.is_some());
                    let selected = match self.mode {
                        1 => false,
                        2 => direct,
                        3 => learned,
                        4 | 6 => direct || learned,
                        5 => true,
                        _ => false,
                    };
                    if selected {
                        mask |= 1u64 << port.col;
                    }
                    if capture {
                        examples.push((f, port.col, x));
                    }
                }
                if mask != 0 {
                    self.stats.facts_proposed += 1;
                    self.stats.proposed_fields += mask.count_ones() as u64;
                    proposals.push(Proposal {
                        serial: if self.mode == 6 {
                            g.stats.unions.wrapping_sub(1)
                        } else {
                            g.stats.unions
                        },
                        issued_epoch: g.epoch,
                        f,
                        table: site.table,
                        eq: site.eq,
                        mask,
                    });
                }
            }
            if let Some(k) = key
                && self.programs.len() < 4096
            {
                self.programs.insert(
                    k,
                    proposals[start..]
                        .iter()
                        .map(|p| (p.f.op, p.table, p.eq, p.mask))
                        .collect(),
                );
                self.stats.shared_programs += 1;
            }
        }
        // Only now may the observer consult the independent exact affected set.
        if let Some(t) = issue_clock {
            self.stats.issue_ns += t.elapsed().as_nanos() as u64;
        }
        let count = g.uses.get(&hi).map_or(0, |s| s.len());
        self.stats.total_readers += count as u64;
        self.stats.nonempty_unions += u64::from(count > 0);
        if observe {
            let mut actual = rustc_hash::FxHashMap::<(FactRef, usize), usize>::default();
            if let Some(set) = g.uses.get(&hi) {
                for &d in set {
                    let Some(r) = g.row(d).expect("source union observer") else {
                        continue;
                    };
                    let mut direct = 0;
                    for (i, v) in r.values.iter().enumerate() {
                        if *v == Value::Eq(hi) {
                            direct += 1;
                            self.stats.true_positions += 1;
                            self.stats.truth_work += r.values.len() as u64;
                            match d {
                                Dependency::Fact(f) => {
                                    actual.insert((f, i), r.values.len());
                                    self.stats.true_owner_positions += u64::from(f.cell == owner);
                                    self.stats.true_seed_positions +=
                                        u64::from(cells.contains(&f.cell));
                                }
                                Dependency::Function(_) => self.stats.function_positions += 1,
                            }
                        } else if matches!(v, Value::Set(_)) {
                            self.stats.nested_positions += has_nested(v, hi);
                        }
                    }
                    if let Dependency::Fact(f) = d
                        && direct > 0
                        && !r.hidden
                        && g.stable_node(f).is_none()
                        && g.cells
                            .get(&f.cell)
                            .and_then(|c| c.facts.get(&f.op))
                            .is_some_and(|s| s.decoded.is_some())
                        && g.program.tables[r.table].schema.iter().all(|v| {
                            matches!(
                                v["kind"].as_str(),
                                Some(
                                    "eq" | "i64"
                                        | "f64"
                                        | "String"
                                        | "Unit"
                                        | "bool"
                                        | "structural_key"
                                )
                            )
                        })
                    {
                        self.stats.exact_patchable_work += r.values.len() as u64;
                    }
                }
            }
            for (f, col, x) in examples {
                self.labels.entry(x).or_default()[usize::from(actual.contains_key(&(f, col)))] += 1;
            }
            for p in &proposals {
                let mut mask = p.mask;
                let actual_mask = actual
                    .keys()
                    .filter(|(f, _)| *f == p.f)
                    .fold(0u64, |m, (_, i)| m | (1u64 << i));
                if self.audit {
                    let kind = if actual_mask == p.mask {
                        "field_match"
                    } else {
                        "wrong_or_partial_fields"
                    };
                    self.examples.entry(kind).or_insert_with(||json!({"union_number":g.stats.unions,"run_epoch":g.epoch,"from":hi,"to":lo,"cell":p.f.cell,"op":p.f.op,"table":g.program.tables[p.table].name,"proposed_mask":p.mask,"actual_mask":actual_mask,"all_readers":count,"from_parent_token":p.f.cell!=owner}));
                }
                while mask != 0 {
                    let col = mask.trailing_zeros() as usize;
                    mask &= mask - 1;
                    let w = actual.get(&(p.f, col)).copied();
                    self.stats.true_proposed += u64::from(w.is_some());
                    self.stats.false_proposed += u64::from(w.is_none());
                    self.stats.proposed_true_work += w.unwrap_or(0) as u64;
                    self.stats.parent_only_hits += u64::from(w.is_some() && p.f.cell != owner);
                }
            }
        }
        if capture {
            return None;
        }
        let verify_clock = self.profile.then(std::time::Instant::now);
        let mut valid = Vec::new();
        for p in proposals {
            let Some(state) = g.cells.get(&p.f.cell).and_then(|c| c.facts.get(&p.f.op)) else {
                self.stats.unavailable += 1;
                continue;
            };
            let Some((table, values)) = &state.decoded else {
                self.stats.unavailable += 1;
                continue;
            };
            if state.hidden || *table != p.table || g.stable_node(p.f).is_some() {
                self.stats.unavailable += 1;
                continue;
            }
            let d = Dependency::Fact(p.f);
            let Some(deps) = g.dependencies.get(&d) else {
                self.stats.membership_reject += 1;
                continue;
            };
            if !deps.iter().any(|&id| root(&g.parents, id) == hi) {
                self.stats.membership_reject += 1;
                continue;
            }
            let mut hits = p.mask;
            let mut all_match = true;
            while hits != 0 {
                let i = hits.trailing_zeros() as usize;
                hits &= hits - 1;
                if values.get(i) != Some(&Value::Eq(hi)) {
                    all_match = false;
                    break;
                }
            }
            if !all_match {
                self.stats.partial_or_wrong += 1;
                continue;
            }
            let mut rest = p.eq & !p.mask;
            let unique = p.mask.count_ones() == 1
                && deps.len() == p.eq.count_ones() as usize
                && deps.iter().all(|id| !g.parents.contains_key(id));
            if rest != 0 && unique {
                self.stats.distinct_certificates += 1;
                self.stats.spared_field_tests += rest.count_ones() as u64;
                rest = 0;
            }
            while rest != 0 {
                let i = rest.trailing_zeros() as usize;
                rest &= rest - 1;
                self.stats.other_fields_checked += 1;
                if values.get(i) == Some(&Value::Eq(hi)) {
                    all_match = false;
                    break;
                }
            }
            if !all_match {
                self.stats.partial_or_wrong += 1;
                continue;
            }
            if p.serial != g.stats.unions || p.issued_epoch != g.epoch {
                self.stats.expired += 1;
                continue;
            }
            let t = PortTicket {
                hi,
                lo,
                union: g.stats.unions,
                epoch: g.epoch,
                version: state.epoch,
                table: *table,
                mask: p.mask,
                payload: std::rc::Rc::downgrade(values),
            };
            if self.pending.insert(p.f, t).is_none() {
                valid.push(d);
                self.stats.verified_facts += 1
            } else {
                self.stats.duplicates += 1;
            }
        }
        valid.sort_unstable();
        if let Some(t) = verify_clock {
            self.stats.verify_ns += t.elapsed().as_nanos() as u64;
        }
        if !valid.is_empty() && valid.len() == count {
            if self.audit {
                assert!(g.uses[&hi].iter().copied().eq(valid.iter().copied()));
            }
            self.stats.complete_lists += 1;
            self.stats.direct_notifications += valid.len() as u64;
            Some(valid)
        } else {
            self.stats.ordinary_notifications += count as u64;
            None
        }
    }
}
