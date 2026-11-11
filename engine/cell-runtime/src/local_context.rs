//! Retain a connected prefix and expand its final table at the scheduled Run.
//! Only correlated prefixes survive Run boundaries; terminal answers do not.
use crate::{
    cell::{Field, Matched, Query, QueryFacts, ScopedStep},
    entry_schedule::Scheduler,
    graph::{Dependency, Graph, Row},
    program::*,
    query::{QueryIndexes, ReadStamp},
    value::Value,
};
use rustc_hash::FxHashMap as Map;
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    rc::Rc,
};

#[derive(Debug, Clone)]
pub(crate) struct Plan {
    root: ScopedStep,
    ports: Vec<ScopedStep>,
    witness_slots: usize,
    columns: Vec<usize>,
    read_tables: Vec<usize>,
    identity_literal: bool,
    query: Query,
    inputs: InputSlots,
}
impl Plan {
    fn root(&self) -> usize { self.root.step.atom }
    fn tail(&self) -> usize { self.query.steps[0].atom }
    fn slots(&self) -> usize { self.ports.last().unwrap_or(&self.root).end() }
    fn tables(&self) -> (usize, usize) {
        match (&self.root.step.call, &self.query.steps[0].call) {
            (Call::Table(root), Call::Table(tail)) => (*root, *tail),
            _ => unreachable!("compiled context endpoints"),
        }
    }
    fn versions<'a>(&'a self, g: &'a Graph) -> impl Iterator<Item = u64> + 'a {
        self.read_tables.iter().map(|&t| g.query_versions[t])
    }
    fn witness_atoms(&self) -> impl Iterator<Item = usize> + '_ {
        std::iter::once(&self.root).chain(&self.ports)
            .filter(|s| matches!(s.step.call, Call::Table(_))).map(|s| s.step.atom)
    }
}
#[path = "context_wire.rs"]
mod wire;

fn slots(args: &[Arg]) -> BTreeSet<usize> {
    args.iter()
        .filter_map(|a| match a {
            Arg::Slot(i) => Some(*i),
            _ => None,
        })
        .collect()
}
fn table(a: &Atom) -> usize {
    match a.call {
        Call::Table(t) => t,
        _ => unreachable!("checked context atom"),
    }
}
fn identity(v: &Value) -> bool {
    match v {
        Value::Eq(_) => true,
        Value::Set(s) => s.iter().any(identity),
        _ => false,
    }
}
pub(crate) fn derive(p: &Program, entries: &serde_json::Value) -> Vec<Option<Rc<Plan>>> {
    let spine = entries
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|v| v["rule"].as_u64().map(|r| r as usize))
        .collect::<BTreeSet<_>>();
    p.rules
        .iter()
        .enumerate()
        .map(|(rid, r)| {
            let q = &r.query;
            if !r.seminaive
                || spine.contains(&rid)
                || q.len() < 4
                || q.iter().any(|a| !matches!(a.call, Call::Table(_)))
            {
                return None;
            }
            let mut chosen = None;
            for (root, a) in q.iter().enumerate() {
                if !p.tables[table(a)].constructor {
                    continue;
                }
                let keys = slots(&a.args[..a.args.len() - 1]);
                let anchor = slots(&a.args);
                if keys.len() < 2 {
                    continue;
                }
                for (tail, b) in q.iter().enumerate() {
                    let tail_slots = slots(&b.args);
                    if root == tail || !tail_slots.is_disjoint(&anchor) {
                        continue;
                    }
                    let ports = (0..q.len())
                        .filter(|&i| i != root && i != tail)
                        .collect::<Vec<_>>();
                    let mut used = BTreeSet::<usize>::new();
                    let mut known = anchor.clone();
                    if !ports.iter().all(|&i| {
                        let args = &q[i].args;
                        let k = slots(&args[..args.len() - 1]);
                        let link = k.intersection(&keys).copied().collect::<Vec<_>>();
                        used.extend(link.iter().copied());
                        known.extend(slots(args));
                        !link.is_empty()
                    }) || used.len() < 2
                    {
                        continue;
                    }
                    let tk = slots(&b.args[..b.args.len() - 1]);
                    if tk.is_disjoint(&known) || tk.is_subset(&known) {
                        continue;
                    }
                    if chosen.is_some() {
                        return None;
                    }
                    chosen = Some(project(r, root, ports, tail, vec![])?);
                }
            }
            chosen.map(Rc::new)
        })
        .collect()
}

fn project(
    r: &Rule,
    root: usize,
    ports: Vec<usize>,
    tail: usize,
    post: Vec<usize>,
) -> Option<Plan> {
    let q = &r.query;
    let (known, mut steps) = Query::scoped_prefix(r, root, &ports)?;
    let read_tables = steps.iter()
        .filter_map(|s| match s.step.call {
            Call::Table(t) => Some(t),
            _ => None,
        })
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let identity_literal = q.iter().any(|a| {
        a.args
            .iter()
            .any(|v| matches!(v,Arg::Literal(v) if identity(v)))
    });
    let query = Query::continuation(r, std::iter::once(root).chain(ports.iter().copied()),
        known, tail, &post)?;
    let columns = query.steps[0].expansion.as_ref()?.bound.iter().filter_map(|(col, field)|
        matches!(field, Field::Anchor(_)).then_some(*col)).collect();
    Some(Plan {
        witness_slots: steps.iter().filter(|s| matches!(s.step.call, Call::Table(_))).count(),
        root: steps.remove(0),
        ports: steps,
        columns,
        read_tables,
        identity_literal,
        query,
        inputs: r.inputs.clone(),
    })
}

#[path = "context_cuts.rs"]
mod cuts;
pub(crate) use cuts::{Cuts, Selections, compile as compile_cuts, select as select_cuts};

const ROOT_LIMIT: usize = 256;
const PREFIX_LIMIT: usize = 4096;
#[derive(Clone)]
struct Prefix {
    values: Vec<Option<Value>>,
    // Dense in the shared prefix instruction order; scalar and terminal atoms
    // have no slots. Every retained prefix has completed all of these reads.
    witnesses: Vec<Dependency>,
    epoch: u64,
}
struct Root {
    epoch: u64,
    leases: Vec<ReadStamp>,
    outputs: Vec<Rc<Prefix>>,
}
#[derive(Default)]
struct Group {
    rows: Vec<Rc<Prefix>>,
}
#[derive(Default)]
struct Context {
    plan: Option<Rc<Plan>>,
    versions: Vec<u64>,
    unions: u64,
    roots: Map<Dependency, Root>,
    groups: Map<Vec<Value>, Group>,
    blocked: bool,
    oversized_at: Vec<usize>,
}
#[derive(Default, Serialize)]
pub(crate) struct Stats {
    calls: u64,
    orientations: BTreeMap<usize, u64>,
    spine_deferrals: u64,
    fallbacks: u64,
    root_rows: u64,
    root_rebuilds: u64,
    root_reuses: u64,
    port_probes: u64,
    port_candidates: u64,
    prefix_copies: u64,
    prefix_slots_copied: u64,
    branch_slot_clears: u64,
    terminal_binding_copies: u64,
    terminal_slots_copied: u64,
    terminal_scratch_slots: u64,
    terminal_result_writes: u64,
    terminal_input_slots: u64,
    terminal_input_capacity_bytes: u64,
    full_terminal_rows: u64,
    delta_terminal_rows: u64,
    reverse_reads: u64,
    reverse_groups: u64,
    bindings: u64,
    terminal_pairs: u64,
    peak_roots: usize,
    peak_prefix_rows: usize,
}
#[derive(Default)]
pub(crate) struct Contexts {
    enabled: bool,
    general: bool,
    states: Map<usize, Context>,
    stats: BTreeMap<usize, Stats>,
}
impl Contexts {
    pub fn new(program: &Program) -> Self {
        Self {
            enabled: true,
            general: program.artifact.get("context_admission").is_some(),
            ..Default::default()
        }
    }
    pub fn general(&self) -> bool {
        self.general
    }
    pub fn enabled(&self) -> bool {
        self.enabled
    }
    pub fn accepts(&self, p: &Program, rid: usize) -> bool {
        self.enabled()
            && (p.local_contexts[rid].is_some() || self.general && !p.context_cuts[rid].is_empty())
    }
    pub fn report(&self, program: &Program) -> serde_json::Value {
        let (cut_rules, cut_orientations) = program.context_cut_counts();
        let plans = program.local_contexts.iter().enumerate().filter_map(|(rid,p)| p.as_ref().map(|p| serde_json::json!({"rule":rid,"root":p.root(),"ports":p.ports.iter().map(|s| s.step.atom).collect::<Vec<_>>(),"terminal":p.tail()}))).collect::<Vec<_>>();
        serde_json::json!({"enabled":self.enabled,"root_limit":ROOT_LIMIT,"prefix_limit":PREFIX_LIMIT,"plans":plans,"general":self.general,"cut_rules":cut_rules,"cut_orientations":cut_orientations,"rules":self.stats})
    }
    pub fn matches(
        &mut self,
        rid: usize,
        watermark: u64,
        facts: &QueryFacts,
        spine_active: bool,
        g: &mut Graph,
        ix: &mut QueryIndexes,
        entries: &mut Scheduler,
    ) -> Result<Option<Vec<Matched>>> {
        let stats = self.stats.entry(rid).or_default();
        if spine_active {
            stats.spine_deferrals += 1;
            return Ok(None);
        }
        let plan = if !self.general || g.program.context_cuts[rid].is_empty() {
            let p = g.program.local_contexts[rid].as_ref().unwrap();
            p.clone()
        } else {
            let best = g.program.context_cuts[rid]
                .iter()
                .filter_map(|p| {
                    let (root, tail) = p.tables();
                    let roots = g.witness_count(root);
                    let tails = g.witness_count(tail);
                    (roots <= ROOT_LIMIT && roots <= tails)
                        .then_some(((roots, std::cmp::Reverse(tails), p.root()), p))
                })
                .min_by_key(|(score, _)| *score);
            let Some((_, p)) = best else {
                self.states.remove(&rid);
                stats.fallbacks += 1;
                return Ok(None);
            };
            p.clone()
        };
        let (root_table, terminal) = plan.tables();
        let tail = &plan.query.steps[0];
        let expansion = tail.expansion.as_ref().expect("terminal expansion");
        let roots = g.witness_count(root_table);
        if roots > ROOT_LIMIT || roots > g.witness_count(terminal) {
            self.states.remove(&rid);
            stats.fallbacks += 1;
            return Ok(None);
        }
        let c = self.states.entry(rid).or_default();
        if c.plan.as_ref().is_none_or(|old| !Rc::ptr_eq(old, &plan)) {
            *c = Context {
                plan: Some(plan.clone()),
                ..Default::default()
            };
        }
        // An oversized cut is a performance miss, never a negative query answer.
        // Probe it again only after a prefix table shrinks. Original search
        // still observes same-size replacements while this cut is deferred.
        if self.general
            && c.blocked
            && !plan
                .read_tables
                .iter()
                .zip(&c.oversized_at)
                .any(|(&t, &old)| g.witness_count(t) < old)
        {
            stats.fallbacks += 1;
            return Ok(None);
        }
        if !c.versions.iter().copied().eq(plan.versions(g))
            || (plan.identity_literal && c.unions != g.stats.unions)
        {
            let reset = plan.identity_literal && c.unions != g.stats.unions;
            c.versions.clear();
            c.versions.extend(plan.versions(g));
            c.unions = g.stats.unions;
            c.blocked = false;
            let mut changed = reset;
            let mut previous = std::mem::take(&mut c.roots);
            let mut size = 0;
            let mut work_left = if self.general {
                PREFIX_LIMIT
            } else {
                usize::MAX
            };
            for w in g.witnesses(root_table) {
                let Some(epoch) = g.visible_epoch(w) else {
                    continue;
                };
                let cached = previous.remove(&w);
                let root = if let Some(old) = cached.filter(|r| {
                    !reset && r.epoch == epoch && r.leases.iter().all(|s| ix.valid_read(g, s))
                }) {
                    stats.root_reuses += 1;
                    old
                } else {
                    changed = true;
                    stats.root_rows += 1;
                    g.stats.residual_candidates += 1;
                    let row = g.row(w)?.ok_or("missing visible root")?;
                    let mut witnesses = Vec::with_capacity(plan.witness_slots);
                    witnesses.push(w);
                    let mut p = Prefix {
                        values: vec![None; plan.slots()],
                        witnesses,
                        epoch,
                    };
                    let mut root = Root {
                        epoch,
                        leases: vec![],
                        outputs: vec![],
                    };
                    if plan.root.bind_row(g, &row, p.values.as_mut_slice()) {
                        stats.root_rebuilds += 1;
                        let complete = if plan.witness_slots > 1 {
                            extend(g, ix, &plan.ports, &mut p,
                                &mut root, size, &mut work_left, stats)?
                        } else if size + root.leases.len() + root.outputs.len() >= PREFIX_LIMIT {
                            false
                        } else {
                            // With no enumerated prefix table there are no
                            // siblings: keep the original move into the cache.
                            let mut matched = true;
                            for step in &plan.ports {
                                if !scalar(g, step, &mut p.values)? { matched = false; break; }
                            }
                            if matched {
                                root.outputs.push(Rc::new(p));
                            }
                            true
                        };
                        if !complete {
                            c.blocked = true;
                            break;
                        }
                    }
                    root
                };
                size += root.outputs.len() + root.leases.len();
                if size > PREFIX_LIMIT {
                    c.blocked = true;
                    break;
                }
                c.roots.insert(w, root);
            }
            if c.blocked {
                c.oversized_at = plan.read_tables.iter().map(|&t| g.witness_count(t)).collect();
                c.roots.clear();
                c.groups.clear();
            } else if changed || !previous.is_empty() {
                c.groups.clear();
                for p in c.roots.values().flat_map(|r| &r.outputs) {
                    let key = expansion.bound.iter().filter_map(|(_, field)|
                        matches!(field, Field::Anchor(_)).then(||
                            field.read(g, |slot| p.values[slot].as_ref().unwrap(), &[], None))).collect();
                    let group = c.groups.entry(key).or_default();
                    group.rows.push(p.clone());
                }
                for group in c.groups.values_mut() {
                    group.rows.sort_unstable_by_key(|p| p.epoch);
                }
                stats.peak_roots = stats.peak_roots.max(c.roots.len());
                stats.peak_prefix_rows = stats
                    .peak_prefix_rows
                    .max(c.groups.values().map(|g| g.rows.len()).sum());
            }
        }
        if c.blocked {
            stats.fallbacks += 1;
            return Ok(None);
        }
        stats.calls += 1;
        *stats.orientations.entry(plan.root()).or_default() += 1;
        let mut answers = Vec::new();
        let pairs_before = stats.terminal_pairs;
        // New prefix facts can match old terminal rows. Stable prefixes only
        // see the current terminal delta. Every answer has at least one new row.
        for group in c
            .groups
            .values()
            .filter(|b| b.rows.last().unwrap().epoch >= watermark)
        {
            let fresh = group.rows.partition_point(|p| p.epoch < watermark);
            let bound = expansion.bind::<Vec<_>>(|field| field.read(g,
                |slot| group.rows[0].values[slot].as_ref().unwrap(), &[], None));
            for &w in ix.candidates(g, terminal, &bound)?.iter() {
                stats.full_terminal_rows += 1;
                g.stats.residual_candidates += 1;
                if let Some(row) = g.row(w)?
                    && !row.hidden
                {
                    stats.terminal_pairs += emit(
                        g,
                        &plan,
                        if row.epoch >= watermark {
                            &group.rows
                        } else {
                            &group.rows[fresh..]
                        },
                        &row,
                        facts,
                        &mut answers,
                        stats,
                    )?;
                }
            }
        }
        if c.groups
            .values()
            .any(|b| b.rows.last().unwrap().epoch < watermark)
        {
            let before = stats.delta_terminal_rows;
            let batch = entries.terminal_batch(g, rid, plan.tail(), watermark)?;
            let budget = self
                .general
                .then(|| batch.delta_len())
                .flatten()
                .unwrap_or(0);
            let mut cost = c.groups.len();
            let mut domains = vec![];
            if cost < budget {
                for group in c
                    .groups
                    .values()
                    .filter(|b| b.rows.last().unwrap().epoch < watermark)
                {
                    let bound = expansion.bind::<Vec<_>>(|field| field.read(g,
                        |slot| group.rows[0].values[slot].as_ref().unwrap(), &[], None));
                    stats.reverse_groups += 1;
                    cost = cost.saturating_add(ix.count(g, terminal, &bound)?);
                    if cost >= budget {
                        break;
                    }
                    domains.push((group, bound));
                }
            }
            if cost < budget {
                stats.reverse_reads += 1;
                for (group, bound) in domains {
                    for &w in ix.candidates(g, terminal, &bound)?.iter() {
                        stats.delta_terminal_rows += 1;
                        if let Some(packet) = batch.entry(w) {
                            stats.terminal_pairs += emit(
                                g,
                                &plan,
                                &group.rows,
                                &packet.row,
                                facts,
                                &mut answers,
                                stats,
                            )?;
                        }
                    }
                }
            } else {
                for &(_, w) in batch.delta() {
                    let row = &batch.entry(w).unwrap().row;
                    stats.delta_terminal_rows += 1;
                    let key = plan
                        .columns
                        .iter()
                        .map(|&col| row.values[col].clone())
                        .collect::<Vec<_>>();
                    if let Some(group) = c.groups.get(&key)
                        && group.rows.last().unwrap().epoch < watermark
                    {
                        stats.terminal_pairs += emit(
                            g,
                            &plan,
                            &group.rows,
                            row,
                            facts,
                            &mut answers,
                            stats,
                        )?;
                    }
                }
            }
            g.stats.residual_candidates += stats.delta_terminal_rows - before;
        }
        g.stats.residual_candidates += stats.terminal_pairs - pairs_before;
        answers.sort_by(|a, b| a.values.cmp(&b.values));
        answers.dedup_by(|a, b| a.values == b.values);
        stats.bindings += answers.len() as u64;
        Ok(Some(answers))
    }
}
fn extend(
    g: &mut Graph,
    ix: &mut QueryIndexes,
    ports: &[ScopedStep],
    p: &mut Prefix,
    root: &mut Root,
    size: usize,
    work_left: &mut usize,
    stats: &mut Stats,
) -> Result<bool> {
    if size + root.leases.len() + root.outputs.len() >= PREFIX_LIMIT {
        return Ok(false);
    }
    let Some((scoped, rest)) = ports.split_first() else {
        // Only retained successful prefixes need independent storage.
        stats.prefix_copies += 1;
        stats.prefix_slots_copied += (p.values.len() + p.witnesses.len()) as u64;
        root.outputs.push(Rc::new(p.clone()));
        return Ok(true);
    };
    let step = &scoped.step;
    if matches!(step.call, Call::Primitive(..)) {
        let result = (|| {
            if !scalar(g, scoped, &mut p.values)? { return Ok(true); }
            extend(g, ix, rest, p, root, size, work_left, stats)
        })();
        clear_scope(p, scoped, stats);
        return result;
    }
    let Call::Table(t) = step.call else { unreachable!() };
    let expansion = step.expansion.as_ref().expect("prefix expansion");
    let bound = expansion.bind::<Vec<_>>(|field|
        field.read(g, |slot| p.values[slot].as_ref().unwrap(), &[], None));
    let Some((candidates, lease)) = ix.leased_candidates(g, t, &bound, PREFIX_LIMIT)? else {
        return Ok(false);
    };
    root.leases.push(lease);
    stats.port_probes += 1;
    for &w in candidates.iter() {
        if *work_left == 0 {
            return Ok(false);
        }
        *work_left -= 1;
        stats.port_candidates += 1;
        g.stats.residual_candidates += 1;
        if let Some(row) = g.row(w)? {
            let epoch = p.epoch;
            let result = if scoped.bind_row(g, &row, p.values.as_mut_slice()) {
                p.witnesses.push(w);
                p.epoch = p.epoch.max(row.epoch);
                let result = extend(g, ix, rest, p, root, size, work_left, stats);
                p.witnesses.pop();
                result
            } else { Ok(true) };
            clear_scope(p, scoped, stats);
            p.epoch = epoch;
            if !result? { return Ok(false); }
        }
    }
    Ok(true)
}
#[inline]
fn clear_scope(p: &mut Prefix, step: &ScopedStep, stats: &mut Stats) {
    // Some fields may not have been assigned before a predicate failed. Clear
    // the compiled scope anyway; it never contains a parent/sibling binding.
    stats.branch_slot_clears += step.bindings.len() as u64;
    p.values[step.base..step.end()].fill(None);
}
fn emit(
    g: &mut Graph,
    plan: &Plan,
    prefixes: &[Rc<Prefix>],
    row: &Row,
    facts: &QueryFacts,
    out: &mut Vec<Matched>,
    stats: &mut Stats,
) -> Result<u64> {
    let query = &plan.query;
    let expansion = query.steps[0].expansion.as_ref().expect("terminal expansion");
    let expanded = Some((0, row));
    if row.hidden
        || !expansion.checks
            .iter()
            .all(|(col, f)| f.agrees(&row.values[*col], g,
                |slot| prefixes[0].values[slot].as_ref().unwrap(), &[], expanded))
    {
        return Ok(0);
    }
    // The terminal row and prefix slots stay borrowed. Only scalar results
    // need storage; reuse this scratch for the whole correlated group.
    let mut results = smallvec::SmallVec::<[Value; 4]>::new();
    if query.result_slots() != 0 {
        results.resize(query.result_slots(), Value::Int(0));
        stats.terminal_scratch_slots += results.len() as u64;
    }
    'prefix: for p in prefixes {
        let epoch = p.epoch.max(row.epoch);
        for (position, step) in query.steps.iter().enumerate().skip(1) {
            let bound = step.bind::<smallvec::SmallVec<[Value; 4]>>(|f| f.operand(g,
                |slot| p.values[slot].as_ref().unwrap(), &results, expanded));
            let result = bound.evaluate(|args| {
                let Call::Primitive(name, sort) = &step.call else { unreachable!("scalar suffix") };
                if name.starts_with("cell-key-") { g.stats.key_operations += 1; }
                g.primitive(name, &args, sort)
            })?;
            let Some(value) = result else { continue 'prefix; };
            if step.check_result.is_none() {
                results[position] = value;
                stats.terminal_result_writes += 1;
            }
        }
        let values: crate::slots::Slots = plan.inputs.iter().zip(&query.inputs).map(|(&slot, f)| (slot, f.read(g,
            |slot| p.values[slot].as_ref().unwrap(), &results, expanded))).collect();
        debug_assert_eq!(p.witnesses.len(), plan.witness_slots);
        let facts = facts.with_rows(plan.witness_atoms().zip(p.witnesses.iter().copied())
            .chain(std::iter::once((plan.tail(), row.witness))));
        stats.terminal_input_slots += values.len() as u64;
        stats.terminal_input_capacity_bytes += values.capacity_bytes() as u64;
        out.push(Matched::matched(values, facts, epoch));
    }
    Ok(prefixes.len() as u64)
}

fn scalar(g: &mut Graph, scoped: &ScopedStep, values: &mut [Option<Value>]) -> Result<bool> {
    let step = &scoped.step;
    let bound = step.bind::<smallvec::SmallVec<[Value; 4]>>(|field|
        field.operand(g, |slot| values[slot].as_ref().unwrap(), &[], None));
    let result = bound.evaluate(|args| {
        let Call::Primitive(name, sort) = &step.call else { unreachable!("scalar prefix") };
        if name.starts_with("cell-key-") { g.stats.key_operations += 1; }
        g.primitive(name, &args, sort)
    })?;
    let Some(value) = result else { return Ok(false); };
    if scoped.bindings.len() == 1 {
        // Newly produced values move into the original prefix. Bound results
        // have already been checked by the shared instruction and need no write.
        values[scoped.base] = Some(value);
    }
    Ok(true)
}
