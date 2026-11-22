// Typed token memory belongs to the issuer; the receiver still accepts only named packets.
use crate::{
    graph::{Dependency, Graph},
    named_only::{Inbox, Packet},
    program::{Arg, Call, Result},
    value::Value,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    cell::RefCell,
    collections::{BTreeMap, HashMap},
    rc::Rc,
};

#[derive(Deserialize)]
pub struct Model {
    #[serde(default)]
    order: Option<Order>,
    #[serde(default)]
    scalars: BTreeMap<String, [f64; 3]>,
    #[serde(default)]
    wide_scalar: bool,
    #[serde(default)]
    port_distinct: bool,
    left: [bool; 4],
    sender: [[bool; 2]; 4],
    follow: [[bool; 4]; 2],
}
#[derive(Deserialize)]
struct Order {
    weights: [[f32; 8]; 16],
    bias: [f32; 16],
    out: [f32; 16],
}

impl Order {
    fn score(&self, first: &[f32; 4], second: &[f32; 4]) -> f32 {
        self.weights
            .iter()
            .zip(self.bias)
            .zip(self.out)
            .map(|((w, bias), out)| {
                let z = first
                    .iter()
                    .chain(second)
                    .zip(w)
                    .fold(bias, |z, (x, w)| z + x * w);
                out * z.tanh()
            })
            .sum()
    }
}

#[derive(Default, Serialize)]
pub struct Counts {
    reads: u64,
    encoded_fields: u64,
    order_decisions: u64,
    order_swaps: u64,
    candidate_visits: u64,
    first_scores: u64,
    second_scores: u64,
    epoch_reads: u64,
    denied_rules: BTreeMap<usize, u64>,
    route_build_rows: u64,
    route_probes: u64,
    summary_reads: u64,
    scalar_suppressed: BTreeMap<usize, u64>,
    issued: u64,
    abstained: u64,
    denied_budget: u64,
    rule_calls: u64,
}
#[derive(Clone, Copy, PartialEq, Eq)]
enum Payload {
    Int(i64),
    Eq(u64),
    Other,
}
#[derive(Clone, Copy, PartialEq, Eq)]
struct Code([u8; 20], Payload);
impl Code {
    fn of(v: &Value) -> Result<Self> {
        let data = serde_json::to_vec(v).map_err(|e| e.to_string())?;
        let h = Sha256::digest(data);
        let mut b = [0; 20];
        b.copy_from_slice(&h[..20]);
        let scalar = match v {
            Value::Int(n) => Payload::Int(*n),
            Value::Eq(id) => Payload::Eq(*id),
            _ => Payload::Other,
        };
        Ok(Self(b, scalar))
    }
    fn page(self) -> u16 {
        u16::from_le_bytes([self.0[4], self.0[5]]) & 1023
    }
    fn matches(self, b: Self) -> bool {
        self.0[4..] == b.0[4..]
    }
}
struct Token {
    address: Dependency,
    epoch: u64,
    fields: Vec<Code>,
}
struct Read {
    table: usize,
    route_id: usize,
    checks: Vec<(usize, usize)>,
    literals: Vec<(usize, Code)>,
    repeats: Vec<(usize, usize)>,
    exports: Vec<(usize, usize)>,
    index: usize,
}
enum ScalarInput {
    Slot(usize),
    Literal(i64),
}
impl ScalarInput {
    fn read(&self, slots: &[Code]) -> Option<i64> {
        match self {
            Self::Literal(v) => Some(*v),
            Self::Slot(i) => match slots[*i].1 {
                Payload::Int(n) => Some(n),
                _ => None,
            },
        }
    }
}
struct ScalarGate {
    inputs: [ScalarInput; 2],
    expected: Option<ScalarInput>,
    weights: [f64; 3],
    wide: bool,
}
impl ScalarGate {
    fn rejects(&self, slots: &[Code]) -> bool {
        let [Some(a), Some(b)] = self.inputs.each_ref().map(|v| v.read(slots)) else {
            return false;
        };
        let [u, v, bias] = self.weights;
        let score = |x: i64, y: i64| u * (x as f64) + v * (y as f64) + bias;
        let small = |x: i64| (-16..=16).contains(&x);
        if small(a) && small(b) {
            let z = score(a, b);
            return match &self.expected {
                None => z < 0.,
                Some(out) => out
                    .read(slots)
                    .is_some_and(|n| small(n) && (z - n as f64).abs() > 0.5),
            };
        }
        if !self.wide || self.expected.is_some() {
            return false;
        }
        // Signed order is unsigned order after flipping the sign bit. Encode
        // each operand independently, then apply the same certified digit gate.
        let digits = |n: i64| (n as u64) ^ (1u64 << 63);
        for shift in (0..16).rev().map(|plane| plane * 4) {
            let x = ((digits(a) >> shift) & 15) as i64;
            let y = ((digits(b) >> shift) & 15) as i64;
            let xy = score(x, y) >= 0.;
            if shift == 0 || xy != (score(y, x) >= 0.) {
                return !xy;
            }
        }
        unreachable!()
    }
}
struct Layout {
    gates: Vec<ScalarGate>,
    distinct: Vec<(usize, usize)>,
    reads: Vec<Read>,
    slots: usize,
}
fn layout(
    rule: &crate::program::Rule,
    first: Option<usize>,
    model: &Model,
) -> Result<Option<Layout>> {
    let mut atoms = vec![];
    for atom in rule.query.iter() {
        if let Call::Table(t) = atom.call {
            atoms.push((atoms.len(), t, &atom.args));
        }
    }
    // A connecting fact supplies both endpoints before two aliases of the same
    // table are expanded. Shared columns common to both aliases cannot select
    // an endpoint, so require a separate slot for each side.
    let bridge = (atoms.len() == 3)
        .then(|| {
            (0..3).find(|&i| {
                let (_, ta, a) = atoms[(i + 1) % 3];
                let (_, tb, b) = atoms[(i + 2) % 3];
                let (_, tc, c) = atoms[i];
                let contains = |args: &[Arg], slot: usize| {
                    args.iter()
                        .any(|arg| matches!(arg, Arg::Slot(s) if *s == slot))
                };
                let links = |first: &[Arg], second: &[Arg]| {
                    c.iter().any(|arg| {
                        matches!(arg, Arg::Slot(s)
                    if contains(first, *s) && !contains(second, *s))
                    })
                };
                ta == tb && ta != tc && links(a, b) && links(b, a)
            })
        })
        .flatten();
    let mut seen = BTreeMap::new();
    let mut reads = vec![];
    while !atoms.is_empty() {
        let rank = |args: &Vec<Arg>| {
            args.iter()
                .filter(|a| matches!(a,Arg::Slot(s) if seen.contains_key(s)))
                .count()
        };
        let i = if reads.is_empty() {
            first
                .or(bridge)
                .or_else(|| atoms.iter().position(|(_, _, args)| args.len() > 1))
                .unwrap_or(0)
        } else {
            let i = (0..atoms.len())
                .max_by_key(|&i| (rank(atoms[i].2), usize::MAX - i))
                .unwrap();
            if rank(atoms[i].2) != 0 {
                i
            } else if let Some(unit) = atoms.iter().position(|(_, _, args)| args.len() == 1) {
                // A nullary constructor/function has exactly one possible key.
                // The packet still names its actual versioned result.
                unit
            } else {
                return Ok(None);
            }
        };
        let (index, table, args) = atoms.remove(i);
        let mut read = Read {
            table,
            index,
            route_id: 0,
            checks: vec![],
            repeats: vec![],
            literals: vec![],
            exports: vec![],
        };
        let mut local = BTreeMap::new();
        for (col, a) in args.iter().enumerate() {
            match a {
                Arg::Literal(Value::Eq(_)) => return Ok(None), // A changing canonical literal needs a runtime projection.
                Arg::Literal(v) => read.literals.push((col, Code::of(v)?)),
                Arg::Slot(s) => {
                    if let Some(&slot) = seen.get(s) {
                        read.checks.push((col, slot));
                    } else if let Some(&first) = local.get(s) {
                        read.repeats.push((col, first));
                    } else {
                        local.insert(*s, col);
                    }
                }
            }
        }
        for (s, col) in local {
            let n = seen.len();
            seen.insert(s, n);
            read.exports.push((col, n));
        }
        reads.push(read);
    }
    let scalar = |arg: &Arg| match arg {
        Arg::Literal(Value::Int(x)) => Some(ScalarInput::Literal(*x)),
        Arg::Slot(s) => seen.get(s).copied().map(ScalarInput::Slot),
        _ => None,
    };
    let gates = rule
        .query
        .iter()
        .filter_map(|atom| {
            let Call::Primitive(op, ty) = &atom.call else {
                return None;
            };
            let [a, b, out] = atom.args.as_slice() else {
                return None;
            };
            let weights = *model.scalars.get(op)?;
            let expected = match (op.as_str(), ty.as_str()) {
                ("+" | "-", "i64") => Some(scalar(out)?),
                ("<" | ">" | "<=" | ">=", "Unit") => None,
                _ => return None,
            };
            Some(ScalarGate {
                inputs: [scalar(a)?, scalar(b)?],
                expected,
                weights,
                wide: model.wide_scalar,
            })
        })
        .collect();
    let mut distinct = vec![];
    if model.port_distinct {
        for atom in rule.query.iter() {
            if let Call::Primitive(op, ty) = &atom.call
                && op == "!="
                && ty == "Unit"
                && let [Arg::Slot(a), Arg::Slot(b), _] = atom.args.as_slice()
                && let (Some(&i), Some(&j)) = (seen.get(a), seen.get(b))
            {
                distinct.push((i, j));
            }
        }
    }
    Ok(Some(Layout {
        gates,
        distinct,
        reads,
        slots: seen.len(),
    }))
}
struct Issuer {
    model: Model,
    plans: Vec<Option<Layout>>,
    alternatives: Vec<Option<Layout>>,
    bank: BTreeMap<usize, Rc<Vec<Token>>>,
    routes: HashMap<usize, HashMap<u16, Vec<usize>>>,
    pages: bool,
    run: usize,
    counts: Counts,
    cap: u64,
}
thread_local! {static ACTIVE:RefCell<Option<Issuer>>=const{RefCell::new(None)};}
pub fn init(g: &Graph, model: Model, cap: u64, pages: bool) -> Result<()> {
    // Validate the serialized readouts before allowing them to suppress a packet.
    for (op, &[u, v, bias]) in &model.scalars {
        for a in -16..=16 {
            for b in -16..=16 {
                let z = u * f64::from(a) + v * f64::from(b) + bias;
                let valid = match op.as_str() {
                    "+" => (z - f64::from(a + b)).abs() < 0.25,
                    "-" => (z - f64::from(a - b)).abs() < 0.25,
                    "<" => (z >= 0.) == (a < b),
                    "<=" => (z >= 0.) == (a <= b),
                    ">" => (z >= 0.) == (a > b),
                    ">=" => (z >= 0.) == (a >= b),
                    _ => false,
                };
                if !z.is_finite() || !valid {
                    return Err(format!("uncertified scalar readout {op}"));
                }
            }
        }
    }
    let mut plans = g
        .program
        .rules
        .iter()
        .map(|rule| layout(rule, None, &model))
        .collect::<Result<Vec<_>>>()?;
    let mut alternatives = Vec::with_capacity(plans.len());
    for (rule, plan) in g.program.rules.iter().zip(&plans) {
        let alternative = match plan {
            Some(p)
                if model.order.is_some() && p.reads.len() == 2 && !p.reads[1].checks.is_empty() =>
            {
                layout(rule, Some(p.reads[1].index), &model)?
            }
            _ => None,
        };
        alternatives.push(alternative);
    }
    let mut layouts = BTreeMap::new();
    for plan in plans.iter_mut().chain(alternatives.iter_mut()).flatten() {
        for read in &mut plan.reads {
            let columns = read
                .checks
                .iter()
                .map(|x| x.0)
                .chain(read.literals.iter().map(|x| x.0))
                .collect::<Vec<_>>();
            let next = layouts.len();
            read.route_id = *layouts.entry((read.table, columns)).or_insert(next);
        }
    }
    ACTIVE.replace(Some(Issuer {
        model,
        plans,
        alternatives,
        bank: BTreeMap::new(),
        routes: HashMap::new(),
        pages,
        run: 0,
        counts: Counts::default(),
        cap,
    }));
    Ok(())
}
pub fn finish() -> Counts {
    ACTIVE.take().unwrap().counts
}

pub fn submit(
    g: &Graph,
    run: usize,
    rid: usize,
    wm: u64,
    inbox: &mut Inbox,
    family: Option<usize>,
) -> Result<bool> {
    ACTIVE.with_borrow_mut(|active| {
        let a = active.as_mut().ok_or("missing issuer")?;
        a.counts.rule_calls += 1;
        if a.run != run {
            a.bank.clear();
            a.routes.clear();
            a.run = run;
        }
        let Some(plan) = &a.plans[rid] else {
            a.counts.abstained += 1;
            return Ok(false);
        };
        let mut memory = vec![];
        for read in &plan.reads {
            if !a.bank.contains_key(&read.table) {
                let mut tokens = vec![];
                for address in g.witnesses(read.table) {
                    a.counts.reads += 1;
                    if let Some(row) = g.row(address)?
                        && !row.hidden
                    {
                        let fields = row
                            .values
                            .iter()
                            .map(Code::of)
                            .collect::<Result<Vec<_>>>()?;
                        a.counts.encoded_fields += fields.len() as u64;
                        tokens.push(Token {
                            address,
                            epoch: row.epoch,
                            fields,
                        });
                    }
                }
                a.bank.insert(read.table, Rc::new(tokens));
            }
            memory.push(a.bank[&read.table].clone());
        }
        if memory.iter().any(|m| m.is_empty()) {
            return Ok(true);
        }
        let semi = g.program.rules[rid].seminaive && !memory.is_empty();
        let mut later_fresh = vec![false; memory.len() + 1];
        let mut fresh_rows = vec![vec![]; memory.len()];
        if semi && a.pages {
            for i in (0..memory.len()).rev() {
                a.counts.epoch_reads += memory[i].len() as u64;
                fresh_rows[i].extend(
                    memory[i]
                        .iter()
                        .enumerate()
                        .filter_map(|(j, r)| (r.epoch >= wm).then_some(j)),
                );
                later_fresh[i] = later_fresh[i + 1] || !fresh_rows[i].is_empty();
            }
            if !later_fresh[0] {
                return Ok(true);
            }
        }
        let mut plan = plan;
        if a.pages
            && let (Some(order), Some(alternative)) = (&a.model.order, &a.alternatives[rid])
        {
            let features = |i: usize| {
                let rows = memory[i].len();
                let fresh = if semi { fresh_rows[i].len() } else { rows };
                [
                    (rows as f32).ln_1p(),
                    (fresh as f32).ln_1p(),
                    (fresh == 0) as u8 as f32,
                    (rows < 16) as u8 as f32,
                ]
            };
            let (left, right) = (features(0), features(1));
            a.counts.order_decisions += 1;
            if order.score(&right, &left) > order.score(&left, &right) {
                plan = alternative;
                memory.swap(0, 1);
                fresh_rows.swap(0, 1);
                later_fresh[1] = !fresh_rows[1].is_empty();
                a.counts.order_swaps += 1;
            }
        }
        let mut summary = [[[false; 2]; 32]; 4];
        let shared = if memory.len() >= 2 && !plan.reads[1].checks.is_empty() {
            let (col, slot) = plan.reads[1].checks[0];
            let first = plan.reads[0]
                .exports
                .iter()
                .find(|(_, s)| *s == slot)
                .unwrap()
                .0;
            a.counts.summary_reads += memory[1].len() as u64;
            for row in memory[1].iter() {
                let fresh = usize::from(
                    !g.program.rules[rid].seminaive || row.epoch >= wm || memory.len() > 2,
                );
                let code = row.fields[col];
                for (k, plane) in summary.iter_mut().enumerate() {
                    let entry = &mut plane[usize::from(code.0[k] % 32)];
                    for (v, learned) in entry.iter_mut().zip(a.model.sender[2 + fresh]) {
                        *v |= learned;
                    }
                }
            }
            Some(first)
        } else {
            None
        };
        // Partial-code dispatch can prune only ports rejected by the frozen follower.
        let mut stack = vec![(
            Vec::<(usize, Dependency, u64)>::new(),
            vec![Code([0; 20], Payload::Other); plan.slots],
            false,
        )];
        let mut budget = a.cap;
        while let Some((parents, slots, fresh)) = stack.pop() {
            let step = parents.len();
            if step == memory.len() {
                if fresh || parents.is_empty() || !g.program.rules[rid].seminaive {
                    if plan.gates.iter().any(|gate| gate.rejects(&slots))
                        || plan
                            .distinct
                            .iter()
                            .any(|&(a, b)| slots[a].1 != Payload::Other && slots[a].1 == slots[b].1)
                    {
                        *a.counts.scalar_suppressed.entry(rid).or_default() += 1;
                        continue;
                    }
                    let mut ordered = parents;
                    ordered.sort_unstable_by_key(|p| p.0);
                    inbox.submit(Packet::issue(
                        family,
                        run,
                        rid,
                        ordered.into_iter().map(|(_, w, e)| (w, e)).collect(),
                    ));
                    a.counts.issued += 1;
                }
                continue;
            }
            let read = &plan.reads[step];
            let fold = |hash: u16, code: Code| (hash.wrapping_mul(31) ^ code.page()) & 1023;
            let mut shortlist = if a.pages
                && memory[step].len() >= 16
                && !(read.checks.is_empty() && read.literals.is_empty())
            {
                a.counts.route_probes += 1;
                let idx = a.routes.entry(read.route_id).or_insert_with(|| {
                    let mut map: HashMap<u16, Vec<usize>> = HashMap::new();
                    for (i, row) in memory[step].iter().enumerate() {
                        let page = read
                            .checks
                            .iter()
                            .map(|x| row.fields[x.0])
                            .chain(read.literals.iter().map(|x| row.fields[x.0]))
                            .fold(0, fold);
                        map.entry(page).or_default().push(i);
                    }
                    a.counts.route_build_rows += memory[step].len() as u64;
                    map
                });
                let page = read
                    .checks
                    .iter()
                    .map(|x| slots[x.1])
                    .chain(read.literals.iter().map(|x| x.1))
                    .fold(0, fold);
                Some(idx.get(&page).map(Vec::as_slice).unwrap_or(&[]))
            } else {
                None
            };
            let need_fresh = semi && a.pages && !fresh && !later_fresh[step + 1];
            if need_fresh
                && fresh_rows[step].len() < shortlist.map_or(memory[step].len(), <[usize]>::len)
            {
                shortlist = Some(&fresh_rows[step]);
            }
            let size = shortlist.map_or(memory[step].len(), <[usize]>::len);
            for i in (0..size).rev() {
                let row = &memory[step][shortlist.map_or(i, |list| list[i])];
                if budget == 0 {
                    a.counts.denied_budget += 1;
                    *a.counts.denied_rules.entry(rid).or_default() += 1;
                    return Ok(false);
                }
                budget -= 1;
                a.counts.candidate_visits += 1;
                let current = usize::from(!g.program.rules[rid].seminaive || row.epoch >= wm);
                if need_fresh && current == 0 {
                    continue;
                }
                if step == 0 {
                    a.counts.first_scores += 1;
                    if !a.model.left[current] {
                        continue;
                    }
                    if let Some(col) = shared {
                        let ch = usize::from(current == 0 && memory.len() == 2);
                        if !summary
                            .iter()
                            .enumerate()
                            .all(|(k, p)| p[usize::from(row.fields[col].0[k] % 32)][ch])
                        {
                            continue;
                        }
                    }
                } else {
                    a.counts.second_scores += 1;
                    let intermediate = step + 1 < memory.len();
                    if !a.model.follow[usize::from(fresh || intermediate)][2 + current]
                        || read
                            .checks
                            .iter()
                            .any(|&(col, slot)| !row.fields[col].matches(slots[slot]))
                    {
                        continue;
                    }
                }
                if read
                    .literals
                    .iter()
                    .any(|&(c, v)| !row.fields[c].matches(v))
                    || read
                        .repeats
                        .iter()
                        .any(|&(c, b)| !row.fields[c].matches(row.fields[b]))
                {
                    continue;
                }
                let mut next = parents.clone();
                next.push((read.index, row.address, row.epoch));
                let mut bound = slots.clone();
                for &(c, s) in &read.exports {
                    bound[s] = row.fields[c];
                }
                stack.push((next, bound, fresh || current == 1));
            }
        }
        Ok(true)
    })
}
