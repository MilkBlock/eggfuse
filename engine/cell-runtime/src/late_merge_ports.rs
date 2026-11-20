//! Verified dynamic merge outputs of a previously proposed and committed parent binding.
//! The model issues a child envelope before the planned Set executes. Both actual
//! constructor references must be supplied by the real source mutation.
use crate::{
    cell::{Matched, QueryFacts, bind_query},
    graph::{Dependency, Graph},
    program::{Arg, Call, Op, Program, Result},
    slots::Slots,
    value::{Value, canon},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value as J, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
};
#[derive(Deserialize)]
pub(crate) struct Config {
    pub digest: String,
    pub routes: Vec<[usize; 8]>,
    pub weights: Vec<f32>,
    pub mode: String,
    pub relax: bool,
    pub only_consumer: bool,
    pub corrupt: bool,
    #[serde(default)]
    pub repeat: bool,
    #[serde(default)]
    pub drop_issued: bool,
}
#[derive(Serialize)]
struct Record {
    root: Option<usize>,
    source: usize,
    run: u64,
    rid: usize,
    route: usize,
    features: [f32; 6],
    selected: bool,
    old: Option<Value>,
    new: Value,
    candidate_pair: Option<Dependency>,
    merged: Option<Dependency>,
    out: Option<Value>,
    merge_epoch: u64,
    pair_epoch: u64,
    checks: u64,
    resolved: usize,
    consumer_run: u64,
    union_revalidated: bool,
    wins: Vec<(usize, u64, bool)>,
    forwarded: bool,
    #[serde(skip)]
    last_version: Option<(u64, u64, Vec<Value>, Vec<Value>)>,
    #[serde(skip)]
    old_pair: Vec<Value>,
    #[serde(skip)]
    old_merge: Vec<Value>,
}
struct State {
    cfg: Config,
    source: usize,
    rid: usize,
    run: u64,
    root: Option<usize>,
    active: Vec<usize>,
    seen_call: bool,
    records: Vec<Record>,
    ready: Vec<usize>,
    consumers: BTreeSet<usize>,
    await_commit: BTreeMap<(usize, Vec<Value>), usize>,
    redundant: u64,
}
thread_local! {static STATE:RefCell<Option<State>>=const{RefCell::new(None)};}
pub(crate) fn configure(p: &Program, c: Config, digest: &str) -> Result<()> {
    if c.digest != digest
        || c.weights.len() != 7
        || c.weights.iter().any(|x| !x.is_finite())
        || !matches!(
            c.mode.as_str(),
            "observe" | "neural" | "all-neural" | "null"
        )
    {
        return Err("invalid late merge model".into());
    }
    let mut consumers = BTreeSet::new();
    for &[parent, effect, t, site, ctor, merge, child, pivot] in &c.routes {
        let r = p.rules.get(parent).ok_or("invalid merge producer")?;
        let ops = &p.templates[r.template].ops;
        let Some(Op::Set(target, _, Arg::Slot(slot))) = ops.get(effect) else {
            return Err("expected set for a merge".into());
        };
        if *target != t
            || !matches!(ops.get(site),Some(Op::Let(dst,Call::Table(k),_)) if dst==slot&&*k==ctor)
            || site >= effect
        {
            return Err("bad candidate wiring".into());
        }
        let desc = &p.tables[t].merge;
        if desc["call"]["table"] != p.tables[merge].name
            || desc["args"] != json!([{"var":"old"},{"var":"new"}])
        {
            return Err("merge expression mismatch".into());
        }
        let q = &p.rules.get(child).ok_or("invalid merge consumer")?.query;
        if q.len() != 2
            || pivot >= 2
            || !matches!(q[pivot].call,Call::Table(k) if k==merge)
            || !matches!(q[1-pivot].call,Call::Table(k) if k==ctor)
            || q[pivot].args.len() != 3
            || Some(&q[pivot].args[1]) != q[1 - pivot].args.last()
        {
            return Err("invalid merge consumer wiring".into());
        }
        consumers.insert(child);
    }
    STATE.with_borrow_mut(|v| {
        *v = Some(State {
            cfg: c,
            source: 0,
            rid: 0,
            run: 0,
            root: None,
            active: vec![],
            seen_call: false,
            records: vec![],
            ready: vec![],
            consumers,
            await_commit: BTreeMap::new(),
            redundant: 0,
        })
    });
    Ok(())
}
pub(crate) fn begin_rhs(rid: usize, epoch: u64, values: &Slots, inputs: &[usize]) {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state else { return };
        s.source += 1;
        s.rid = rid;
        s.run = epoch;
        s.root = None;
        s.active.clear();
        s.seen_call = false;
        if !s.await_commit.is_empty() && s.consumers.contains(&rid) {
            let key = (rid, inputs.iter().map(|i| values[i].clone()).collect());
            if let Some(id) = s.await_commit.remove(&key) {
                s.records[id].resolved = s.source;
                s.records[id].consumer_run = epoch;
                let relaxed = s.records[id].union_revalidated;
                s.records[id].wins.push((s.source, epoch, relaxed));
            }
        }
    });
}
pub(crate) fn neural_root(id: usize) {
    STATE.with_borrow_mut(|state| {
        if let Some(s) = state {
            s.root = Some(id);
        }
    });
}
pub(crate) fn enter(
    g: &Graph,
    cell: u32,
    op: usize,
    t: usize,
    key: &[Value],
    candidate: &Value,
) -> Result<()> {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state else { return Ok(()) };
        s.active.clear();
        s.seen_call = false;
        if s.cfg.mode != "observe" && s.root.is_none() {
            return Ok(());
        }
        for (k, &[rid, effect, target, site, ctor, _merge, _child, _pivot]) in
            s.cfg.routes.iter().enumerate()
        {
            if (rid, effect, target) != (s.rid, op, t) {
                continue;
            }
            let Op::Let(_, _, args) = &g.program.templates[g.program.rules[rid].template].ops[site]
            else {
                unreachable!()
            };
            let fields = g.inline_arguments(cell, args)?;
            let Some(pair) = g
                .lookup(ctor, &fields)?
                .filter(|r| !r.hidden && r.values.last() == Some(candidate))
            else {
                continue;
            };
            let old = g.lookup(t, key)?.and_then(|r| r.values.last().cloned());
            let numer = fields
                .iter()
                .find_map(|v| {
                    if let Value::Int(i) = v {
                        Some(*i)
                    } else {
                        None
                    }
                })
                .unwrap_or(0);
            let input = [
                1.,
                old.is_some() as u8 as f32,
                (old.as_ref() == Some(candidate)) as u8 as f32,
                (numer as f64).abs().ln_1p().min(40.) as f32 / 40.,
                (s.run as f32 / 2048.).min(1.),
                (rid % 16) as f32 / 16.,
            ];
            let score = s.cfg.weights[6]
                + input
                    .iter()
                    .zip(&s.cfg.weights)
                    .map(|(a, b)| a * b)
                    .sum::<f32>();
            let select = match s.cfg.mode.as_str() {
                "observe" | "all-neural" => true,
                "null" => false,
                _ => score >= 0.,
            };
            let id = s.records.len();
            s.records.push(Record {
                root: s.root,
                source: s.source,
                run: s.run,
                rid,
                route: k,
                features: input,
                selected: select,
                old,
                new: candidate.clone(),
                candidate_pair: Some(pair.witness),
                merged: None,
                out: None,
                merge_epoch: 0,
                pair_epoch: pair.epoch,
                checks: 0,
                resolved: 0,
                consumer_run: 0,
                union_revalidated: false,
                wins: vec![],
                forwarded: false,
                last_version: None,
                old_pair: pair.values.to_vec(),
                old_merge: vec![],
            });
            if select {
                s.active.push(id);
            }
        }
        Ok(())
    })
}
pub(crate) fn constructing(t: usize, args: &[Value]) {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state else { return };
        if args.len() != 2 {
            return;
        }
        if s.active.iter().any(|id| {
            let p = &s.records[*id];
            s.cfg.routes[p.route][5] == t && p.old.as_ref() == Some(&args[0]) && p.new == args[1]
        }) {
            s.seen_call = true;
        }
    });
}
pub(crate) fn finish(g: &Graph, index: usize) -> Result<()> {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state else { return Ok(()) };
        let ids = std::mem::take(&mut s.active);
        if !s.seen_call {
            return Ok(());
        }
        for id in ids {
            let p = &mut s.records[id];
            let Some(old) = &p.old else { continue };
            let dst = s.cfg.routes[p.route][5];
            let args = if s.cfg.corrupt {
                [p.new.clone(), old.clone()]
            } else {
                [old.clone(), p.new.clone()]
            };
            let Some(merged) = g.lookup(dst, &args)?.filter(|r| !r.hidden) else {
                continue;
            };
            let Some(visible) = g.row(Dependency::Function(index))? else {
                continue;
            };
            if visible.values.last() != merged.values.last()
                || merged.values[..2] != [old.clone(), p.new.clone()]
            {
                continue;
            }
            p.merged = Some(merged.witness);
            p.merge_epoch = merged.epoch;
            p.old_merge = merged.values.to_vec();
            p.out = merged.values.last().cloned();
            s.ready.push(id);
        }
        Ok(())
    })
}
pub(crate) fn verify(
    g: &Graph,
    rid: usize,
    watermark: u64,
    facts: &QueryFacts,
) -> Result<(bool, Vec<Matched>)> {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state else {
            return Ok((false, vec![]));
        };
        if !s.consumers.contains(&rid) {
            return Ok((false, vec![]));
        }
        let mut rows = Vec::new();
        let rule = &g.program.rules[rid];
        for &id in &s.ready {
            let p = &mut s.records[id];
            let [_, _, _, _, _, _, child, pivot] = s.cfg.routes[p.route];
            if child != rid || (!s.cfg.repeat && p.resolved != 0) || p.run >= g.epoch {
                continue;
            }
            let resolve = |w: Dependency,
                           table: usize,
                           values: &[Value]|
             -> Result<Option<crate::graph::Row>> {
                if let Some(r) = g.row(w)?.filter(|r| {
                    !r.hidden
                        && values
                            .iter()
                            .map(|x| canon(x, &g.parents))
                            .eq(r.values.iter().cloned())
                }) {
                    return Ok(Some(r));
                }
                if !s.cfg.relax {
                    return Ok(None);
                }
                let key = values[..values.len() - 1]
                    .iter()
                    .map(|x| canon(x, &g.parents))
                    .collect::<Vec<_>>();
                Ok(g.lookup(table, &key)?.filter(|r| {
                    !r.hidden
                        && values
                            .iter()
                            .map(|x| canon(x, &g.parents))
                            .eq(r.values.iter().cloned())
                }))
            };
            let Some(merged) = resolve(p.merged.unwrap(), s.cfg.routes[p.route][5], &p.old_merge)?
            else {
                continue;
            };
            let Some(pair) = resolve(
                p.candidate_pair.unwrap(),
                s.cfg.routes[p.route][4],
                &p.old_pair,
            )?
            else {
                continue;
            };
            let forwarded =
                p.merged != Some(merged.witness) || p.candidate_pair != Some(pair.witness);
            let version = (
                merged.epoch,
                pair.epoch,
                merged.values.to_vec(),
                pair.values.to_vec(),
            );
            if p.resolved != 0 && p.last_version.as_ref() == Some(&version) {
                continue;
            }
            if merged.hidden || pair.hidden || merged.epoch.max(pair.epoch) < watermark {
                continue;
            }
            let relaxed = forwarded
                || merged.epoch != p.merge_epoch
                || pair.epoch != p.pair_epoch
                || merged.values.as_slice() != p.old_merge
                || pair.values.as_slice() != p.old_pair;
            if relaxed && !s.cfg.relax {
                continue;
            }
            if !p
                .old_merge
                .iter()
                .map(|x| canon(x, &g.parents))
                .eq(merged.values.iter().cloned())
                || !p
                    .old_pair
                    .iter()
                    .map(|x| canon(x, &g.parents))
                    .eq(pair.values.iter().cloned())
            {
                continue;
            }
            let mut env = BTreeMap::new();
            let mut known = Vec::new();
            let mut ok = true;
            for (pos, row) in [(pivot, &merged), (1 - pivot, &pair)] {
                let a = &rule.query[pos];
                ok &= matches!(a.call,Call::Table(t) if t==row.table)
                    && a.args
                        .iter()
                        .zip(row.values.iter())
                        .all(|(a, v)| bind_query(a, v, &mut env, g));
                known.push((pos, row.witness));
            }
            if !ok {
                continue;
            }
            let key: Vec<_> = rule.inputs.iter().map(|i| env[i].clone()).collect();
            if s.await_commit.contains_key(&(rid, key.clone())) {
                continue;
            }
            p.checks += 1;
            p.union_revalidated = relaxed;
            p.forwarded = forwarded;
            p.last_version = Some(version);
            s.await_commit.insert((rid, key), id);
            let values = rule.inputs.iter().map(|i| (*i, env[i].clone())).collect();
            rows.push(Matched::matched(
                values,
                facts.with_rows(known),
                merged.epoch.max(pair.epoch),
            ));
        }
        Ok((s.cfg.only_consumer, rows))
    })
}
pub(crate) fn report() -> Option<J> {
    STATE.with_borrow(|state|state.as_ref().map(|s|json!({"mode":s.cfg.mode,"records":s.records,"routes":s.cfg.routes,
        "outstanding":s.await_commit.len(),"rhs":s.source,"residual_disabled_for_consumer":s.cfg.only_consumer,"extra_overlaps":s.redundant})))
}
pub(crate) fn replace_overlaps(
    rid: usize,
    generated: &mut Vec<Matched>,
    ordinary: &mut Vec<Matched>,
    inputs: &[usize],
) {
    STATE.with_borrow_mut(|state| {
        if let Some(s) = state {
            let before = ordinary.len();
            ordinary.retain(|o| {
                !generated
                    .iter()
                    .any(|b| inputs.iter().all(|i| b.values.get(i) == o.values.get(i)))
            });
            s.redundant += (before - ordinary.len()) as u64;
            if s.cfg.drop_issued {
                for b in generated.iter() {
                    s.await_commit
                        .remove(&(rid, inputs.iter().map(|i| b.values[i].clone()).collect()));
                }
                generated.clear();
            }
        }
    });
}
