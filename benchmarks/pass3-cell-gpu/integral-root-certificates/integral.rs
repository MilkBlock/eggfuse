// Independently verify obligations on original Run releases. Source arbitration
// remains authoritative. Only a matching owner and complete binding can take over.
use crate::cell::{bind_query, query_operand};
use crate::{
    cell::QueryFacts,
    graph::{Dependency, Graph, Row},
    program::{Arg, Call, Result, Rule},
    slots::Slots,
    value::Value,
};
use rustc_hash::FxHashMap as Map;
use serde::Serialize;
use serde_json::{Value as J, json};
use std::{cell::RefCell, collections::BTreeMap};

#[derive(Default, Serialize)]
pub(crate) struct Metrics {
    pub(crate) external_seeds: u64,
    pub(crate) baseline_commits: u64,
    pub(crate) resumed: u64,
    pub(crate) deep_resumes: u64,
    pub(crate) active_rule_releases: u64,
    pub(crate) delta_ports: u64,
    pub(crate) without_cursor: u64,
    pub(crate) deep_ports: u64,
    pub(crate) owner_missing: u64,
    pub(crate) stage_guard: u64,
    pub(crate) unsupported: u64,
    pub(crate) anchor_reads: u64,
    pub(crate) point_reads: u64,
    pub(crate) primitives: u64,
    pub(crate) negative: u64,
    pub(crate) offers: u64,
    pub(crate) credited: u64,
    pub(crate) swapped: u64,
    pub(crate) wrong_owner: u64,
    pub(crate) no_proposal: u64,
    pub(crate) wrong_witness: u64,
    pub(crate) wrong_anchor: u64,
    pub(crate) complete_receipts: u64,
    pub(crate) reconstructed_receipts: u64,
    pub(crate) implicit_anchor: u64,
    pub(crate) implicit_suffix: u64,
    pub(crate) duplicate_or_unconsumed: u64,
    pub(crate) root_outputs: [u64; 5],
    pub(crate) child_outputs: [u64; 5],
    pub(crate) total_outputs: [u64; 5],
    pub(crate) points_at_credit: u64,
}
pub(crate) struct Owner {
    pub run: usize,
    pub rule: usize,
    serial: u64,
    children: usize,
    first_child: Option<[usize; 4]>,
    work: [u64; 5],
}
struct Offer {
    version: u64,
    owner: u64,
    pivot: usize,
    inputs: Slots,
    refs: Vec<(usize, Dependency)>,
    producer: usize,
    op: usize,
}
pub(crate) struct Candidate {
    pub values: Slots,
    pub refs: Vec<(usize, Dependency)>,
}
pub(crate) struct State {
    pub m: Metrics,
    pub roots: Map<u64, Owner>,
    pending: Map<(usize, Vec<Value>), Vec<Offer>>,
    current: Option<(u64, bool)>,
    run: usize,
    swap: bool,
    fault: bool,
    examples: Vec<J>,
    branches: Vec<J>,
    routes: BTreeMap<(usize, usize, usize, usize), u64>,
    pub grams: Map<(usize, usize), Option<Vec<usize>>>,
}
thread_local! {static STORE:RefCell<Option<State>>=const{RefCell::new(None)};}
pub fn configure(mode: &str) -> Result<()> {
    if !["off", "verify", "apply", "wrong-owner"].contains(&mode) {
        return Err("invalid integral verifier mode".into());
    }
    STORE.with_borrow_mut(|v| {
        *v = (mode != "off").then(|| State {
            m: Default::default(),
            roots: Default::default(),
            pending: Default::default(),
            run: 0,
            current: None,
            swap: mode == "apply" || mode == "wrong-owner",
            fault: mode == "wrong-owner",
            examples: vec![],
            branches: vec![],
            routes: Default::default(),
            grams: Default::default(),
        })
    });
    Ok(())
}
#[inline]
pub(crate) fn enabled() -> bool {
    STORE.with_borrow(|s| s.is_some())
}
pub(crate) fn with<T>(f: impl FnOnce(&mut State) -> T) -> T {
    STORE.with_borrow_mut(|s| f(s.as_mut().unwrap()))
}

pub(crate) fn grammar(r: &Rule, p: usize) -> Option<Vec<usize>> {
    if !r.seminaive || !matches!(r.query[p].call, Call::Table(_)) {
        return None;
    }
    let mut bound = std::collections::BTreeSet::new();
    for a in &r.query[p].args {
        if let Arg::Slot(s) = a {
            bound.insert(*s);
        }
    }
    let mut done = vec![false; r.query.len()];
    done[p] = true;
    let mut order = Vec::new();
    while done.iter().any(|x| !*x) {
        let i = (0..done.len()).find(|&i| {
            !done[i]
                && r.query[i].args.split_last().is_some_and(|(_, args)| {
                    args.iter().all(|a| {
                        matches!(a, Arg::Literal(_))
                            || matches!(a,Arg::Slot(s) if bound.contains(s))
                    })
                })
        })?;
        if let Call::Primitive(op, ty) = &r.query[i].call
            && !(ty == "i64" && matches!(op.as_str(), "+" | "-" | "*" | "/" | "%" | "min" | "max"))
        {
            return None;
        }
        for a in &r.query[i].args {
            if let Arg::Slot(s) = a {
                bound.insert(*s);
            }
        }
        done[i] = true;
        order.push(i);
    }
    Some(order)
}
pub(crate) fn execute(
    g: &Graph,
    r: &Rule,
    p: usize,
    order: &[usize],
    row: &Row,
    wm: u64,
    m: &mut Metrics,
) -> Result<Option<Candidate>> {
    if row.hidden || row.epoch < wm || !matches!(r.query[p].call,Call::Table(t) if t==row.table) {
        return Ok(None);
    }
    let mut frame = BTreeMap::new();
    let mut refs = vec![(p, row.witness)];
    if row.values.len() != r.query[p].args.len()
        || !r.query[p]
            .args
            .iter()
            .zip(row.values.iter())
            .all(|(a, v)| bind_query(a, v, &mut frame, g))
    {
        return Ok(None);
    }
    for &i in order {
        let atom = &r.query[i];
        let (out, key) = atom.args.split_last().ok_or("empty causal query")?;
        let key = key
            .iter()
            .map(|a| {
                query_operand(a, &frame, g).ok_or_else(|| "missing integral input".to_string())
            })
            .collect::<Result<smallvec::SmallVec<[Value; 3]>>>()?;
        let value = match &atom.call {
            Call::Table(t) => {
                m.point_reads += 1;
                let Some(v) = g.lookup(*t, &key)?.filter(|r| !r.hidden) else {
                    return Ok(None);
                };
                refs.push((i, v.witness));
                v.values.last().cloned()
            }
            Call::Primitive(op, ty) => {
                m.primitives += 1;
                g.primitive(op, &key, ty)?
            }
        };
        let Some(v) = value else { return Ok(None) };
        if !bind_query(out, &v, &mut frame, g) {
            return Ok(None);
        }
    }
    let mut values = Slots::default();
    for &s in r.inputs.iter() {
        values.insert(s, frame.get(&s).ok_or("missing causal RHS slot")?.clone());
    }
    Ok(Some(Candidate { values, refs }))
}
impl State {
    pub fn begin_run(&mut self, run: usize) {
        if run != self.run {
            self.m.duplicate_or_unconsumed +=
                self.pending.values().map(Vec::len).sum::<usize>() as u64;
            self.pending.clear();
            self.run = run;
        }
    }
    pub fn offer(
        &mut self,
        rid: usize,
        pivot: usize,
        root: u64,
        producer: usize,
        op: usize,
        version: u64,
        answer: Candidate,
    ) {
        self.m.offers += 1;
        let inputs = answer.values;
        let key = (rid, inputs.values().cloned().collect());
        self.pending.entry(key).or_default().push(Offer {
            owner: root,
            version,
            pivot,
            inputs,
            refs: answer.refs,
            producer,
            op,
        });
    }
}
pub(crate) enum Apply {
    External(u64),
    Live(u64, u32, Option<(usize, Dependency, u64, usize)>),
    Other,
}
pub(crate) fn commit(
    tag: Apply,
    run: usize,
    rid: usize,
    serial: u64,
    v: &mut Slots,
    known: &QueryFacts,
) -> Result<()> {
    with(|s| {
        s.begin_run(run);
        s.m.baseline_commits += 1;
        s.current = None;
        match tag {
            Apply::External(root) => {
                if s.roots
                    .insert(
                        root,
                        Owner {
                            run,
                            rule: rid,
                            serial,
                            children: 0,
                            first_child: None,
                            work: [0; 5],
                        },
                    )
                    .is_some()
                {
                    return Err("duplicate integral root".into());
                }
                s.m.external_seeds += 1;
                s.current = Some((root, false));
            }
            Apply::Live(root, depth, anchor) => {
                s.m.resumed += 1;
                if depth != 2 {
                    s.m.deep_resumes += 1;
                    return Ok(());
                }
                let key = (rid, v.values().cloned().collect());
                let Some(offers) = s.pending.get_mut(&key) else {
                    s.m.no_proposal += 1;
                    return Ok(());
                };
                if !offers.iter().any(|o| o.owner == root) {
                    s.m.wrong_owner += 1;
                    return Ok(());
                }
                let same_anchor = |o: &Offer| {
                    anchor == Some((o.pivot, o.refs[0].1, o.version, o.op)) && o.owner == root
                };
                if !offers.iter().any(same_anchor) {
                    s.m.wrong_anchor += 1;
                    return Ok(());
                }
                let Some(i) = offers.iter().position(|o| {
                    same_anchor(o)
                        && o.refs
                            .iter()
                            .all(|&(a, w)| known.receipt(a).is_none_or(|actual| actual == w))
                }) else {
                    s.m.wrong_witness += 1;
                    return Ok(());
                };
                let mut o = offers.swap_remove(i);
                let owner = s
                    .roots
                    .get_mut(&root)
                    .ok_or("missing integral external seal")?;
                if s.fault {
                    o.owner ^= 1
                }
                if o.owner != root || owner.rule != o.producer || owner.run >= run || o.inputs != *v
                {
                    return Err("integral certificate owner, Run or binding mismatch".into());
                }
                if s.swap {
                    *v = o.inputs;
                    s.m.swapped += 1
                }
                let child = [run, rid, o.op, o.pivot];
                if let Some(first) = owner.first_child {
                    if owner.children == 1 && s.branches.len() < 12 {
                        s.branches.push(json!([
                            root,
                            owner.serial,
                            owner.run,
                            owner.rule,
                            first,
                            child
                        ]));
                    }
                } else {
                    owner.first_child = Some(child)
                }
                let mut complete = true;
                for &(a, _) in &o.refs {
                    if known.receipt(a).is_none() {
                        complete = false;
                        if a == o.pivot {
                            s.m.implicit_anchor += 1
                        } else {
                            s.m.implicit_suffix += 1
                        }
                    }
                }
                if complete {
                    s.m.complete_receipts += 1
                } else {
                    s.m.reconstructed_receipts += 1
                }
                owner.children += 1;
                s.m.credited += 1;
                s.m.points_at_credit += o.refs.len().saturating_sub(1) as u64;
                s.current = Some((root, true));
                *s.routes
                    .entry((owner.rule, o.op, rid, o.pivot))
                    .or_default() += 1;
                if s.examples.len() < 8 {
                    s.examples.push(json!([
                        root,
                        owner.serial,
                        owner.run,
                        owner.rule,
                        o.op,
                        run,
                        rid,
                        o.pivot,
                        o.refs.len()
                    ]));
                }
            }
            Apply::Other => {}
        };
        Ok(())
    })
}
pub(crate) fn counters(g: &Graph) -> [u64; 5] {
    [
        g.stats.logical_facts_created,
        g.stats.cells_created,
        g.stats.function_updates,
        g.stats.unions,
        g.stats.integral_constructor_births,
    ]
}
pub(crate) fn effects(before: [u64; 5], after: [u64; 5]) {
    with(|s| {
        for i in 0..5 {
            let d = after[i] - before[i];
            s.m.total_outputs[i] += d;
            if let Some((id, child)) = s.current {
                if child {
                    s.m.child_outputs[i] += d
                } else {
                    s.m.root_outputs[i] += d
                }
                s.roots.get_mut(&id).unwrap().work[i] += d;
            }
        }
        s.current = None;
    })
}
pub fn report() -> J {
    STORE.with_borrow(|s|s.as_ref().map_or(J::Null,|s|{
    let mut fanout=BTreeMap::new();let mut used=[0u64;5];
    for r in s.roots.values(){*fanout.entry(r.children).or_insert(0u64)+=1;if r.children>0{for i in 0..5{used[i]+=r.work[i]}}}
    json!({"counts":s.m,"fanout":fanout,"used_root_outputs":used,"uncounted_last_run_offers":s.pending.values().map(Vec::len).sum::<usize>(),"examples":s.examples,"branches":s.branches,
           "routes":s.routes.iter().map(|(&(p,o,c,i),&n)|[p,o,c,i,n as usize]).collect::<Vec<_>>()})
}))
}
