//! Conditional requests owned by an issued parent. Only a real winning publication can arm a child.
use crate::cell::{Instance, QueryFacts};
use crate::graph::{Dependency, Graph, Row};
use crate::program::{Arg, Call, Op, Program, Result};
use crate::slots::Slots;
use crate::value::Value;
use rustc_hash::FxHashMap;
use serde::Deserialize;
use serde_json::{Value as J, json};
use std::cell::RefCell;
use std::collections::BTreeMap;

#[derive(Deserialize)]
struct Family {
    table: String,
    column: usize,
    threshold: i64,
    eq: usize,
    gt: usize,
}
#[derive(Deserialize)]
struct Config {
    family: Family,
    parents: Vec<[usize; 2]>,
    mode: String,
    #[serde(default)]
    recursive: bool,
    #[serde(default)]
    profile: bool,
    #[serde(default)]
    recycle: bool,
}
#[derive(Clone, Copy, Debug)]
pub struct Request {
    serial: u64,
    epoch: u64,
    rid: usize,
    owner: u64,
}
#[derive(Clone, Copy, Debug)]
pub struct Origin {
    ordinal: usize,
    epoch: u64,
    rid: usize,
    effect: usize,
    serial: u64,
    owner: u64,
    admitted: bool,
    inherited: Option<Child>,
}
#[derive(Clone, Copy, Debug)]
pub struct Child {
    pub root: usize,
    pub serial: u64,
    pub owner: u64,
    pub producer: usize,
    pub effect: usize,
    pub issue: u64,
    pub version: u64,
    pub source: Dependency,
    pub value: i64,
    pub branch: u8,
    pub depth: usize,
    generation: u64,
}
#[derive(Clone, Copy)]
pub enum Choice {
    Regular,
    Excluded,
    Selected(Child),
}
#[derive(Clone, Copy, PartialEq)]
enum Mode {
    Flat,
    Dispatch,
    Baked,
    Stale,
    Shadow,
}
#[derive(Clone)]
struct Layout {
    rid: usize,
    columns: Vec<(usize, Option<usize>)>,
    template: usize,
    arity: usize,
}
struct State {
    family: Family,
    table: usize,
    layouts: [Layout; 2],
    parents: Vec<Vec<(usize, Option<i64>)>>,
    mode: Mode,
    recursive: bool,
    profile: bool,
    recycle: bool,
    active: Option<Origin>,
    last_child: Option<(usize, Child)>,
    pending: FxHashMap<Dependency, Child>,
    seen: FxHashMap<Dependency, (Origin, u64)>,
    generation: u64,
    counts: [u64; 24],
    winners: Vec<J>,
    opportunities: BTreeMap<(usize, usize), [u64; 4]>,
    projected: u64,
    issued_bytes: u64,
    peak: usize,
    peak_capacity: usize,
    depth: usize,
    root_ord: usize,
}
thread_local! {static STATE:RefCell<Option<State>>=const{RefCell::new(None)};}

fn checked_layout(p: &Program, f: &Family, t: usize, rid: usize, greater: bool) -> Result<Layout> {
    let r = p.rules.get(rid).ok_or("unknown continuation rule")?;
    if !r.seminaive || r.query.len() != if greater { 2 } else { 1 } {
        return Err("unsupported guard schedule".into());
    }
    let atom = &r.query[0];
    if !matches!(atom.call,Call::Table(id) if id==t) || f.column + 1 >= atom.args.len() {
        return Err("bad continuation source".into());
    }
    let mut vars = BTreeMap::new();
    for (col, arg) in atom.args.iter().enumerate() {
        match arg {
            Arg::Slot(slot) if (greater || col != f.column) && !vars.contains_key(slot) => {
                vars.insert(*slot, Some(col));
            }
            Arg::Literal(Value::Int(k)) if !greater && col == f.column && *k == f.threshold => {}
            _ => return Err("unproved constructor constraint".into()),
        }
    }
    if greater {
        let pred = &r.query[1];
        if !matches!(&pred.call,Call::Primitive(op,ty) if op==">" && ty=="Unit")
            || pred.args.len() != 3
            || pred.args[0] != atom.args[f.column]
            || !matches!(pred.args[1],Arg::Literal(Value::Int(k)) if k==f.threshold)
        {
            return Err("wrong guarded comparison".into());
        }
        let Arg::Slot(slot) = pred.args[2] else {
            return Err("unknown guard output".into());
        };
        if vars.insert(slot, None).is_some() {
            return Err("bound guard output".into());
        }
    }
    let columns = r
        .inputs
        .iter()
        .map(|s| Ok((*s, *vars.get(s).ok_or("unknown projected input")?)))
        .collect::<Result<Vec<_>>>()?;
    Ok(Layout {
        rid,
        columns,
        template: r.template,
        arity: r.query.len(),
    })
}

pub fn configure(p: &Program, data: Option<&[u8]>) -> Result<()> {
    let Some(data) = data else {
        STATE.with_borrow_mut(|s| *s = None);
        return Ok(());
    };
    let c: Config = serde_json::from_slice(data).map_err(|e| e.to_string())?;
    let f = c.family;
    let t = p
        .tables
        .iter()
        .position(|v| v.name == f.table)
        .ok_or("unknown family table")?;
    if !p.tables[t].constructor
        || p.tables[t]
            .schema
            .get(f.column)
            .is_none_or(|s| s["name"] != "i64")
    {
        return Err("mutable or non-integer field".into());
    }
    let layouts = [
        checked_layout(p, &f, t, f.eq, false)?,
        checked_layout(p, &f, t, f.gt, true)?,
    ];
    let mut parents = vec![vec![]; p.rules.len()];
    for [rid, e] in c.parents {
        let r = p.rules.get(rid).ok_or("unknown producer")?;
        let ops = &p.templates[r.template].ops;
        let args = match ops.get(e) {
            Some(Op::Let(_, Call::Table(id), a) | Op::Set(id, a, _)) if *id == t => a,
            _ => return Err("invalid producer effect port".into()),
        };
        if args.len() <= f.column {
            return Err("short producer key".into());
        }
        // A tail may inherit its parent's immutable i64 if the source RHS exactly defines the new port as b - d.
        let mut decrement = None;
        if rid == f.gt {
            if let Arg::Slot(result) = args[f.column] {
                let input = &r.query[0].args[f.column];
                for op in ops[..e].iter().rev() {
                    match op {
                        Op::Let(dst, Call::Primitive(name, ty), operands)
                            if *dst == result
                                && name == "-"
                                && ty == "i64"
                                && operands.len() == 2
                                && operands[0] == *input =>
                        {
                            if let Arg::Literal(Value::Int(d)) = operands[1] {
                                decrement = Some(d);
                            }
                            break;
                        }
                        Op::Let(dst, ..) | Op::Copy(dst, _) if *dst == result => break,
                        _ => (),
                    }
                }
            }
        }
        if parents[rid].iter().any(|(op, _)| *op == e) {
            return Err("duplicate parent interface".into());
        }
        parents[rid].push((e, decrement));
    }
    let mode = match c.mode.as_str() {
        "flat" => Mode::Flat,
        "dispatch" => Mode::Dispatch,
        "baked" => Mode::Baked,
        "stale" => Mode::Stale,
        "shadow" => Mode::Shadow,
        _ => return Err("unknown higher-order mode".into()),
    };
    STATE.with_borrow_mut(|s| {
        *s = Some(State {
            family: f,
            table: t,
            layouts,
            parents,
            mode,
            recursive: c.recursive,
            profile: c.profile,
            recycle: c.recycle,
            active: None,
            last_child: None,
            pending: Default::default(),
            seen: Default::default(),
            generation: 0,
            counts: [0; 24],
            winners: vec![],
            opportunities: Default::default(),
            projected: 0,
            issued_bytes: 0,
            peak: 0,
            peak_capacity: 0,
            depth: 0,
            root_ord: 0,
        })
    });
    Ok(())
}

pub fn issue(run: u64, rid: usize, serial: u64) -> Option<Request> {
    STATE.with_borrow_mut(|state| {
        let s = state.as_mut()?;
        if s.parents[rid].is_empty() {
            return None;
        }
        s.counts[0] += 1;
        // Each standalone flat child needs its own (parent handle, port); the shared request names both branches through its template.
        s.issued_bytes += if s.mode == Mode::Flat { 32 } else { 16 };
        Some(Request {
            serial,
            epoch: run,
            rid,
            owner: serial,
        })
    })
}
pub fn inherit(run: u64, rid: usize, serial: u64, parent: Child) -> Option<Request> {
    let inherited = STATE.with_borrow_mut(|state| {
        let s = state.as_mut()?;
        if !s.recursive
            || s.parents[rid].is_empty()
            || !s.parents[rid].iter().any(|(_, d)| d.is_some())
        {
            return None;
        }
        s.counts[13] += 1;
        Some(Request {
            serial,
            epoch: run,
            rid,
            owner: parent.owner,
        })
    });
    inherited.or_else(|| issue(run, rid, serial))
}
pub fn activate(
    serial: u64,
    request: Option<Request>,
    ordinal: usize,
    run: u64,
    rid: usize,
) -> Result<()> {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state.as_mut() else {
            return Ok(());
        };
        if let Some(req) = request
            && (req.serial != serial || req.rid != rid || req.epoch != run)
        {
            return Err("foreign forward request".into());
        }
        let inherited = s
            .last_child
            .take()
            .and_then(|(o, c)| (s.recursive && o == ordinal).then_some(c));
        s.root_ord = ordinal;
        s.active = Some(Origin {
            ordinal,
            epoch: run,
            rid,
            effect: usize::MAX,
            serial,
            owner: request.map_or(serial, |r| r.owner),
            admitted: request.is_some(),
            inherited,
        });
        Ok(())
    })
}
pub fn end() {
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.active = None;
            s.last_child = None;
        }
    });
}
pub fn stage(rid: usize, effect: usize, table: usize) -> Option<Origin> {
    STATE.with_borrow(|state| {
        let s = state.as_ref()?;
        if table != s.table {
            return None;
        }
        let mut o = s.active.filter(|o| o.rid == rid)?;
        o.effect = effect;
        o.admitted &= s.parents[rid].iter().any(|(e, _)| *e == effect);
        if !o.admitted && !s.profile {
            return None;
        }
        Some(o)
    })
}
pub fn publish(
    g: &Graph,
    w: Dependency,
    table: usize,
    key: &[Value],
    origin: Option<Origin>,
) -> Result<()> {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state.as_mut() else {
            return Ok(());
        };
        if table != s.table {
            return Ok(());
        }
        if s.pending.remove(&w).is_some() {
            s.counts[8] += 1;
        }
        if s.profile {
            s.seen.remove(&w);
        }
        let Some(o) = origin else { return Ok(()) };
        let version = g.visible_epoch(w).ok_or("missing published owner")?;
        if s.profile {
            s.seen.insert(w, (o, version));
        }
        if !o.admitted {
            return Ok(());
        }
        let value = match key.get(s.family.column) {
            Some(Value::Int(v)) => *v,
            _ => return Err("invalid published integer".into()),
        };
        let mut depth = 1;
        let inherited = o.inherited.and_then(|prior| {
            let dec = s.parents[o.rid]
                .iter()
                .find(|(idx, _)| *idx == o.effect)?
                .1?;
            Some((prior, prior.value.wrapping_sub(dec)))
        });
        if let Some((prior, expected)) = inherited {
            if expected != value {
                return Err("inherited port disagrees with actual source return".into());
            }
            depth = prior.depth + 1;
            s.counts[10] += 1;
            // Only the greater branch can emit this checked subtraction, and its successful
            // source Run has already advanced that consumer watermark to o.epoch. An immutable
            // older constructor generation can no longer enable either exclusive branch.
            if s.recycle
                && prior.version < o.epoch
                && s.pending
                    .get(&prior.source)
                    .is_some_and(|v| v.generation == prior.generation)
            {
                s.pending.remove(&prior.source);
                s.counts[14] += 1;
            }
        }
        s.generation += 1;
        s.counts[1] += 1;
        s.counts[2
            + usize::from(value >= s.family.threshold)
            + usize::from(value > s.family.threshold)] += 1;
        let c = Child {
            root: o.ordinal,
            serial: o.serial,
            owner: o.owner,
            producer: o.rid,
            effect: o.effect,
            issue: o.epoch,
            version,
            source: w,
            value,
            branch: if value == s.family.threshold {
                1
            } else if value > s.family.threshold {
                2
            } else {
                0
            },
            depth,
            generation: s.generation,
        };
        s.pending.insert(w, c);
        s.peak = s.peak.max(s.pending.len());
        s.peak_capacity = s.peak_capacity.max(s.pending.capacity());
        s.depth = s.depth.max(depth);
        Ok(())
    })
}
pub fn handles(rid: usize) -> bool {
    STATE.with_borrow(|s| {
        s.as_ref()
            .is_some_and(|s| rid == s.family.eq || rid == s.family.gt)
    })
}
pub fn tracking(table: usize) -> bool {
    STATE.with_borrow(|s| s.as_ref().is_some_and(|s| s.table == table))
}
pub fn choose(rid: usize, row: &Row, wm: u64) -> Choice {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state.as_mut() else {
            return Choice::Regular;
        };
        let is_gt = rid == s.family.gt;
        if !is_gt && rid != s.family.eq {
            return Choice::Regular;
        }
        let Some(c) = s.pending.get(&row.witness).copied() else {
            return Choice::Regular;
        };
        if s.mode == Mode::Shadow {
            return Choice::Regular;
        }
        if c.version != row.epoch || s.mode == Mode::Stale || row.hidden {
            s.counts[9] += 1;
            return Choice::Regular;
        }
        if c.version < wm {
            s.counts[7] += 1;
            return Choice::Excluded;
        }
        let branch = if s.mode == Mode::Baked {
            c.branch == if is_gt { 2 } else { 1 }
        } else if is_gt {
            c.value > s.family.threshold
        } else {
            c.value == s.family.threshold
        };
        if s.mode != Mode::Flat && !branch {
            s.counts[6] += 1;
            return Choice::Excluded;
        }
        s.counts[5] += 1;
        Choice::Selected(c)
    })
}
pub fn projection(g: &Graph, rid: usize, c: &Child) -> Result<Option<Instance>> {
    STATE.with_borrow_mut(|state| {
        let s = state.as_mut().ok_or("missing higher-order verifier")?;
        let layout = &s.layouts[usize::from(rid == s.family.gt)];
        if layout.rid != rid
            || g.program.rules[rid].template != layout.template
            || g.epoch <= c.issue
            || s.pending
                .get(&c.source)
                .is_none_or(|now| now.generation != c.generation)
        {
            return Err("stale continuation source".into());
        }
        let Some(row) = g.row(c.source)? else {
            return Ok(None);
        };
        if row.hidden || row.epoch != c.version || row.table != s.table {
            return Ok(None);
        }
        let mut values = Slots::default();
        for &(slot, from) in &layout.columns {
            values.insert(
                slot,
                from.map_or(Value::Int(0), |col| row.values[col].clone()),
            );
        }
        let mut refs = vec![None; layout.arity];
        refs[0] = Some(c.source);
        s.projected += 1;
        Ok(Some(Instance::matched(
            values,
            QueryFacts::Ports(refs),
            row.epoch,
        )))
    })
}
pub fn logical_offer(rid: usize, c: Child) -> bool {
    STATE.with_borrow(|s| {
        s.as_ref()
            .is_some_and(|s| c.branch == if rid == s.family.gt { 2 } else { 1 })
    })
}
pub fn baked() -> bool {
    STATE.with_borrow(|s| s.as_ref().is_some_and(|s| s.mode == Mode::Baked))
}
pub fn commit(rid: usize, run: u64, ordinal: usize, w: Option<Dependency>, c: Option<Child>) {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state.as_mut() else { return };
        let Some(w) = w else { return };
        if rid == s.family.eq || rid == s.family.gt {
            if let Some((o, _)) = s.seen.get(&w) {
                let branch = usize::from(rid == s.family.gt);
                let counts = s.opportunities.entry((o.rid, o.effect)).or_default();
                counts[branch] += 1;
                if c.is_some() {
                    counts[2 + branch] += 1;
                }
            }
        }
        if let Some(c) = c {
            s.counts[11 + usize::from(rid == s.family.gt)] += 1;
            s.last_child = Some((ordinal, c));
            if s.profile {
                s.winners.push(json!([
                    ordinal,
                    run,
                    rid,
                    w,
                    c.root,
                    c.serial,
                    c.producer,
                    c.effect,
                    c.issue,
                    c.version,
                    c.generation,
                    c.depth,
                    c.value
                ]));
            }
        }
    })
}
pub fn report() -> J {
    STATE.with_borrow(|state|state.as_ref().map_or(J::Null,|s|json!({
    "counts":s.counts,"retired":s.counts[14],"peak_payload_bytes":s.peak*std::mem::size_of::<(Dependency,Child)>(),"peak_hash_capacity":s.peak_capacity,"final_pending":s.pending.len(),"projected":s.projected,"peak_pending":s.peak,"max_chain":s.depth,"request_logical_bytes":s.issued_bytes,
    "winners":s.winners,"observed":s.opportunities.iter().map(|(&(rid,e),counts)|json!([rid,e,counts])).collect::<Vec<_>>()
})))
}
