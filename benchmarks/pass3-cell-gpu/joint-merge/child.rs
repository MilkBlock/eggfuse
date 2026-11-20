//! Predict a physical child template before its source merge. Its certificate authorizes allocation itself.
use crate::{
    graph::{Dependency, Graph},
    program::{Arg, Call, Op, Program, Result},
    value::{Value, canon},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value as Json, json};
use std::{cell::RefCell, collections::BTreeMap};

#[derive(Deserialize)]
pub struct Config {
    pub program_sha256: String,
    pub weights: [f32; 7],
    pub control: String,
    #[serde(default)]
    pub forbid_fallback: bool,
}
#[derive(Clone)]
struct Route {
    effect: usize,
    function: usize,
    factory: usize,
    candidate_table: usize,
    ctor: usize,
    template: usize,
}
#[derive(Clone, Serialize)]
struct Parent {
    ordinal: usize,
    rule: usize,
    run: u64,
    provider: &'static str,
    token: u64,
}
#[derive(Clone, Serialize)]
struct Token {
    id: usize,
    parent: Parent,
    effect: usize,
    function: usize,
    constructor: usize,
    template: usize,
    old_reference: Option<Dependency>,
    candidate_reference: Dependency,
    candidate_table: usize,
    candidate_site: usize,
    old_key: Vec<Value>,
    candidate_key: Vec<Value>,
    old: Option<Value>,
    new: Value,
    old_epoch: Option<u64>,
    candidate_epoch: u64,
    score: f32,
    selected: bool,
    issued_before_mutation: bool,
    entered_allocator: bool,
    allocated: Option<u32>,
    reused: bool,
    rejected: bool,
}
pub(crate) struct Verified {
    pub id: usize,
    pub table: usize,
    pub template: usize,
    pub arguments: [Value; 2],
}
struct Session {
    routes: BTreeMap<(usize, usize), Route>,
    nested: BTreeMap<usize, usize>,
    forbid: bool,
    weights: [f32; 7],
    control: String,
    parent: Option<Parent>,
    ordinal: usize,
    active: Option<usize>,
    trace: Vec<Token>,
    audit: bool,
    counts: [u64; 6],
    raw_hash: u64,
}
thread_local! {static SESSION:RefCell<Option<Session>>=const{RefCell::new(None)};}
pub fn configure(p: &Program, data: Option<&[u8]>, audit: bool) -> Result<()> {
    let Some(bytes) = data else {
        SESSION.with_borrow_mut(|s| *s = None);
        return Ok(());
    };
    let c: Config = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
    if p.artifact["sha256"] != c.program_sha256
        || c.weights.iter().any(|x| !x.is_finite())
        || !matches!(
            c.control.as_str(),
            "learned" | "null" | "wrong-template" | "wrong-operands" | "stale" | "shadow" | "all"
        )
    {
        return Err("invalid joint merge checkpoint or program".into());
    }
    let mut routes = BTreeMap::new();
    for (rid, r) in p.rules.iter().enumerate() {
        let ops = &p.templates[r.template].ops;
        for (effect, op) in ops.iter().enumerate() {
            let Op::Set(function, _, Arg::Slot(v)) = op else {
                continue;
            };
            let expr = &p.tables[*function].merge;
            if expr["args"] != json!([{"var":"old"},{"var":"new"}]) {
                continue;
            }
            let Some(name) = expr["call"]["table"].as_str() else {
                continue;
            };
            let Some(ctor) = p
                .tables
                .iter()
                .position(|t| t.name == name && t.virtual_fact)
            else {
                continue;
            };
            let Some((factory, candidate_table)) =
                ops[..effect]
                    .iter()
                    .enumerate()
                    .rev()
                    .find_map(|(i, op)| match op {
                        Op::Let(dst, Call::Table(t), _)
                            if dst == v && p.tables[*t].virtual_fact =>
                        {
                            Some((i, *t))
                        }
                        _ => None,
                    })
            else {
                continue;
            };
            if p.tables[ctor].schema.len() != 3 {
                continue;
            }
            routes.insert(
                (rid, effect),
                Route {
                    effect,
                    function: *function,
                    factory,
                    candidate_table,
                    ctor,
                    template: p.table_templates[ctor],
                },
            );
        }
    }
    if routes.is_empty() {
        return Err("no function-constructor merge routes".into());
    }
    let nested = routes.values().map(|r| (r.ctor, r.template)).collect();
    SESSION.with_borrow_mut(|s| {
        *s = Some(Session {
            routes,
            nested,
            forbid: c.forbid_fallback,
            weights: c.weights,
            control: c.control,
            parent: None,
            ordinal: 0,
            active: None,
            trace: Vec::new(),
            audit,
            counts: [0; 6],
            raw_hash: 14695981039346656037,
        })
    });
    Ok(())
}
pub(crate) fn begin(rid: usize, run: u64, single: Option<u64>, multi: usize) {
    SESSION.with_borrow_mut(|state| {
        if let Some(s) = state {
            s.ordinal += 1;
            s.active = None;
            s.parent = match (single, multi) {
                (Some(id), 0) => Some(("single", id)),
                (None, id) if id > 0 => Some(("multi", id as u64)),
                (None, 0) => None,
                _ => panic!("two winning neural providers for one binding"),
            }
            .map(|(provider, token)| Parent {
                ordinal: s.ordinal,
                run,
                rule: rid,
                provider,
                token,
            });
        }
    });
}
pub(crate) fn end() {
    SESSION.with_borrow_mut(|state| {
        if let Some(s) = state {
            s.parent = None;
            s.active = None;
        }
    });
}
pub(crate) fn issue(
    g: &Graph,
    cell: u32,
    op: usize,
    table: usize,
    key: &[Value],
    candidate: &Value,
) -> Result<()> {
    SESSION.with_borrow_mut(|state| {
        let Some(s) = state else { return Ok(()) };
        s.active = None;
        let Some(parent) = s.parent.as_ref() else {
            return Ok(());
        };
        let Some(route) = s
            .routes
            .get(&(parent.rule, op))
            .filter(|r| r.function == table)
        else {
            return Ok(());
        };
        let Op::Let(_, _, args) =
            &g.program.templates[g.program.rules[parent.rule].template].ops[route.factory]
        else {
            unreachable!()
        };
        let typed = g.inline_arguments(cell, args)?;
        let Some(pair) = g
            .lookup(route.candidate_table, &typed)?
            .filter(|r| !r.hidden && r.values.last() == Some(candidate))
        else {
            return Ok(());
        };
        let prior = g.lookup(table, key)?;
        let old = prior.as_ref().and_then(|r| r.values.last()).cloned();
        let integer = typed
            .iter()
            .find_map(|v| {
                if let Value::Int(i) = v {
                    Some(*i)
                } else {
                    None
                }
            })
            .unwrap_or(0);
        let f = [
            1.,
            old.is_some() as u8 as f32,
            (old.as_ref() == Some(candidate)) as u8 as f32,
            (integer as f64).abs().ln_1p().min(40.) as f32 / 40.,
            (parent.run as f32 / 2048.).min(1.),
            (parent.rule % 16) as f32 / 16.,
        ];
        let score = s.weights[6] + f.iter().zip(&s.weights).map(|(a, b)| a * b).sum::<f32>();
        let decision = if s.control == "all" {
            true
        } else if s.control == "null" {
            false
        } else {
            score >= 0.
        };
        if !s.audit {
            s.trace.clear();
        }
        let id = s.trace.len();
        let t = Token {
            id,
            parent: parent.clone(),
            effect: route.effect,
            function: table,
            constructor: route.ctor,
            template: route.template,
            old_reference: prior.as_ref().map(|r| r.witness),
            candidate_reference: pair.witness,
            candidate_table: route.candidate_table,
            candidate_site: route.factory,
            old_key: key.to_vec(),
            candidate_key: typed.to_vec(),
            old,
            new: candidate.clone(),
            old_epoch: prior.map(|r| r.epoch),
            candidate_epoch: pair.epoch,
            score,
            selected: decision,
            issued_before_mutation: true,
            entered_allocator: false,
            allocated: None,
            reused: false,
            rejected: false,
        };
        for word in [
            parent.ordinal as u64,
            parent.run,
            parent.rule as u64,
            parent.token,
            op as u64,
            t.template as u64,
            score.to_bits() as u64,
            decision as u64,
        ] {
            s.raw_hash = (s.raw_hash ^ word).wrapping_mul(1099511628211);
        }
        s.counts[0] += 1;
        s.counts[1] += decision as u64;
        s.trace.push(t);
        if decision {
            s.active = Some(id);
        }
        Ok(())
    })
}
pub(crate) fn finish() {
    SESSION.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.active = None;
        }
    });
}

pub(crate) fn take(g: &Graph, table: usize, key: &[Value]) -> Result<Option<Verified>> {
    SESSION.with_borrow_mut(|state| {
        let Some(s) = state else { return Ok(None) };
        let Some(id) = s.active else { return Ok(None) };
        let t = &mut s.trace[id];
        if table != t.constructor {
            return Ok(None);
        }
        // Test controls corrupt one component AFTER the frozen network has issued its token.
        // The verifier rechecks the dynamic ports against the authoritative graph here.
        s.active = None;
        s.counts[2] += 1;
        let template = if s.control == "wrong-template" {
            (t.template + 1) % g.program.templates.len()
        } else {
            t.template
        };
        let Some(w) = t.old_reference else {
            t.rejected = true;
            return Ok(None);
        };
        let Some(old) = t.old.as_ref() else {
            t.rejected = true;
            return Ok(None);
        };
        let Some(a) = g.row(w)?.filter(|r| !r.hidden && r.table == t.function) else {
            t.rejected = true;
            return Ok(None);
        };
        let Some(b) = g
            .row(t.candidate_reference)?
            .filter(|r| !r.hidden && r.table == t.candidate_table)
        else {
            t.rejected = true;
            return Ok(None);
        };
        let old = canon(old, &g.parents);
        let new = canon(&t.new, &g.parents);
        let args = if s.control == "wrong-operands" {
            [new.clone(), old.clone()]
        } else {
            [old.clone(), new.clone()]
        };
        if s.parent.as_ref().map(|p| p.ordinal) != Some(t.parent.ordinal)
            || g.program.table_templates[table] != template
            || !a.values[..a.values.len() - 1].iter().eq(t
                .old_key
                .iter()
                .map(|v| canon(v, &g.parents))
                .collect::<Vec<_>>()
                .iter())
            || !b.values[..b.values.len() - 1].iter().eq(t
                .candidate_key
                .iter()
                .map(|v| canon(v, &g.parents))
                .collect::<Vec<_>>()
                .iter())
            || a.values.last() != Some(&old)
            || b.values.last() != Some(&new)
            || t.old_epoch != Some(a.epoch)
            || Some(b.epoch)
                != (if s.control == "stale" {
                    t.candidate_epoch.checked_add(1)
                } else {
                    Some(t.candidate_epoch)
                })
            || args.as_slice() != key
        {
            t.rejected = true;
            s.counts[3] += 1;
            return Ok(None);
        }
        if s.control == "shadow" {
            return Ok(None);
        }
        t.entered_allocator = true;
        Ok(Some(Verified {
            id,
            table,
            template,
            arguments: args,
        }))
    })
}
pub(crate) fn allocated(id: usize, cell: Option<u32>) {
    SESSION.with_borrow_mut(|state| {
        let s = state.as_mut().unwrap();
        let t = &mut s.trace[id];
        assert!(t.entered_allocator && t.allocated.is_none() && !t.reused);
        t.allocated = cell;
        t.reused = cell.is_none();
        s.counts[if t.reused { 4 } else { 5 }] += 1;
    });
}
pub fn report() -> Json {
    SESSION.with_borrow(|s|s.as_ref().map_or(Json::Null,|s|json!({"control":s.control,"source_rhs":s.ordinal,
        "score_trajectory":s.raw_hash.to_string(),"counts":s.counts,"issued":if s.audit{json!(s.trace)}else{Json::Null}})))
}

pub(crate) fn allow_default_fresh(table: usize) -> Result<()> {
    SESSION.with_borrow(|state|{
        if let Some(s)=state && s.forbid && let Some(template)=s.nested.get(&table){
            return Err(format!("no verified neural template {template} for fresh dynamic constructor {table} at source ordinal {}",s.ordinal));
        }
        Ok(())
    })
}
