//! Symbolic SSA keys on one finite, witnessed block path. Constructor receipts
//! can also prove result equality. Mutable receipts prove only a row location;
//! a query must read its current result and check visibility and the full key.
use crate::{
    graph::{Dependency, FactRef},
    iterative::Entry,
    cell::{Capture, Definition, ResultPort, Results, Site},
    program::*,
};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    rc::Rc,
};

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct Reuse {
    pub equal_output: bool,
    pub op: usize,
    pub back: usize,
    pub rule: usize,
    pub donor: Site,
    #[serde(skip)]
    pub port: Option<ResultPort>,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct QueryReuse {
    pub atom: usize,
    pub back: usize,
    pub rule: usize,
    pub donor: Site,
    #[serde(skip)]
    pub port: Option<ResultPort>,
}
#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) struct Input {
    pub op: usize,
    pub back: usize,
    pub fact: Option<FactRef>,
    pub equal_output: bool,
}
#[derive(Clone)]
struct Fact {
    stage: usize,
    rule: usize,
    source: Site,
    table: usize,
    key: Vec<usize>,
    result: usize,
    constructor: bool,
}
#[derive(Clone, Default)]
struct KeyFootprint {
    indexed_roots: BTreeSet<usize>,
    key_epoch: usize,
    congruence_dirty: bool,
}
impl crate::cell::SymbolObserver for KeyFootprint {
    fn key(&mut self, roots: &[usize]) { self.indexed_roots.extend(roots); }
    fn merged(&mut self, from: usize, _: usize) {
        // Fresh output aliases normally do not change any existing fact key.
        if self.indexed_roots.contains(&from) {
            self.key_epoch += 1;
            self.congruence_dirty = true;
        }
    }
}
type Symbols = crate::cell::Symbols<KeyFootprint>;
impl Symbols {
    #[cfg(test)]
    fn same_key(&self, a: &[usize], b: &[usize]) -> bool {
        a.len() == b.len() && a.iter().zip(b).all(|(&x, &y)| self.root(x) == self.root(y))
    }

    /// Compile-time closure over the surviving, witnessed constructor facts.
    /// Call only at a source boundary or after collecting the complete LHS;
    /// queued RHS unions must not become visible to earlier RHS instructions.
    fn close(&mut self, facts: &[Fact]) {
        if self.observer.congruence_dirty {
            self.close_full(facts);
        }
    }
    fn close_full(&mut self, facts: &[Fact]) {
        self.close_constructors(facts.iter().filter(|f| f.constructor)
            .map(|f| (f.table, f.key.as_slice(), f.result)));
        self.observer.congruence_dirty = false;
    }
}
/// Exact canonical keys, retaining the most recent donor like the reverse scan.
/// This is a compiler lookup index, not another equality solver.
#[derive(Default)]
struct FactIndex {
    keys: BTreeMap<(usize, crate::cell::SymbolKey), usize>,
    indexed: usize,
    epoch: usize,
}
impl FactIndex {
    fn clear(&mut self, _symbols: &mut Symbols) {
        self.keys.clear();
        self.indexed = 0;
        // Keep the conservative footprint: a Hide may clear this lookup index
        // before queued unions affect other surviving constructor keys.
    }
    fn find(
        &mut self,
        symbols: &mut Symbols,
        facts: &[Fact],
        table: usize,
        key: &[usize],
    ) -> Option<usize> {
        if self.epoch != symbols.observer.key_epoch {
            self.clear(symbols);
        }
        for (i, f) in facts.iter().enumerate().skip(self.indexed) {
            let key = symbols.key(&f.key);
            symbols.observer.indexed_roots.extend(&key);
            self.keys.insert((f.table, key), i);
        }
        self.indexed = facts.len();
        self.epoch = symbols.observer.key_epoch;
        let key = symbols.key(key);
        // Register the pending fact too, before its source-boundary unions.
        symbols.observer.indexed_roots.extend(&key);
        self.keys.get(&(table, key)).copied()
    }
}
fn derive_stage(
    p: &Program,
    path: &[(Option<usize>, Entry)],
    congruence: bool,
    query_ports: bool,
) -> Terminal {
    if path.len() < 2 {
        return Terminal::default();
    }
    let mut symbols = Symbols::default();
    let mut facts = Vec::<Fact>::new();
    let mut index = FactIndex::default();
    let mut published = Vec::new();
    let mut program = vec![];
    let mut queries = vec![];
    for (stage, &(_, (rid, pivot))) in path.iter().enumerate() {
        let cell = Definition::new(p, rid).expect("validated Cell path");
        let r = cell.rule;
        let t = cell.template;
        let mut slots = (0..t.sorts.len())
            .map(|_| symbols.fresh())
            .collect::<Vec<_>>();
        if let Some(pivot) = pivot {
            for (arg, col) in r.query[pivot].args.iter().zip(published.drain(..)) {
                let into = symbols.arg(arg, |i| slots[i]);
                symbols.equal(into, col);
            }
        } else {
            debug_assert!(stage == 0 && published.is_empty());
        }
        // A query receipt may use only the pivot and earlier completed ports.
        // Full-LHS equalities are valid for RHS proofs, but using them here
        // could make a later query constraint justify an earlier lookup.
        let order = if query_ports && stage + 1 == path.len() {
            pivot.and_then(|pivot| {
                p.multi_stage
                    .stage_entries
                    .iter()
                    .find(|(rule, anchor, _)| (*rule, *anchor) == (rid, pivot))
                    .map(|(_, _, rest)| {
                        std::iter::once(pivot)
                            .chain(rest.iter().copied())
                            .collect::<Vec<_>>()
                    })
            })
        } else {
            None
        };
        let query_ordered = order.is_some();
        for atom in order.unwrap_or_else(|| (0..r.query.len()).collect()) {
            let Some(relation) = cell.relation(Site::Query(atom)) else { continue };
            let table = relation.table;
            let constructor = p.tables[table].constructor;
            if !constructor && !query_ports {
                continue;
            }
            let result = symbols.arg(&relation.result, |i| slots[i]);
            let key = relation.keys
                .iter()
                .map(|a| symbols.arg(a, |i| slots[i]))
                .collect::<Vec<_>>();
            if let Some(i) = index.find(&mut symbols, &facts, table, &key) {
                let f = &facts[i];
                if query_ordered && Some(atom) != pivot && f.stage != stage {
                    queries.push(QueryReuse {
                        atom,
                        back: stage - f.stage,
                        rule: f.rule,
                        donor: f.source,
                        port: None,
                    });
                }
                // A mutable row's location may survive while its result changes.
                // Only constructor functionality proves a result equality.
                if constructor {
                    symbols.equal(result, f.result);
                }
            }
            facts.push(Fact {
                stage,
                rule: rid,
                source: Site::Query(atom),
                table,
                key,
                result,
                constructor,
            });
        }
        if congruence {
            symbols.close(&facts);
        }
        let publication = path.get(stage + 1).and_then(|s| s.0);
        let mut unions = vec![];
        for (op, ins) in t.ops.iter().enumerate() {
            match ins {
                Op::Copy(dst, a) => {
                    slots[*dst] = symbols.arg(a, |i| slots[i]);
                    continue;
                }
                Op::Union(a, b) => {
                    unions.push((symbols.arg(a, |i| slots[i]), symbols.arg(b, |i| slots[i])));
                    continue;
                }
                Op::Hide(t, ..) => {
                    facts.retain(|f| f.table != *t);
                    index.clear(&mut symbols);
                    continue;
                }
                _ => (),
            }
            let Some(relation) = cell.relation(Site::Effect(op)) else { continue };
            let table = relation.table;
            let key = relation.keys
                .iter()
                .map(|a| symbols.arg(a, |i| slots[i]))
                .collect::<Vec<_>>();
            let value = symbols.arg(&relation.result, |i| slots[i]);
            if Some(op) == publication {
                published = key.clone();
                // A mutable function's published result can change by the next Run.
                if p.tables[table].virtual_fact {
                    published.push(value);
                }
            }
            if !p.tables[table].constructor || !p.tables[table].virtual_fact {
                if query_ports {
                    facts.push(Fact {
                        stage,
                        rule: rid,
                        source: Site::Effect(op),
                        table,
                        key,
                        result: value,
                        constructor: false,
                    });
                }
                continue;
            }
            if let Some(i) = index.find(&mut symbols, &facts, table, &key) {
                let f = &facts[i];
                if f.stage != stage
                    && stage + 1 == path.len()
                    && !p.known_results.static_skip.get(rid).is_some_and(|s| s[op])
                {
                    program.push(Reuse {
                        equal_output: matches!(ins, Op::Set(..))
                            && symbols.root(value) == symbols.root(f.result),
                        op,
                        back: stage - f.stage,
                        rule: f.rule,
                        donor: f.source,
                        port: None,
                    });
                }
                if matches!(ins, Op::Set(..)) {
                    unions.push((value, f.result));
                } else {
                    symbols.equal(value, f.result);
                }
            }
            let source = p.known_results.static_sources.get(rid).and_then(|s| s[op])
                .unwrap_or(Site::Effect(op));
            facts.push(Fact {
                stage,
                rule: rid,
                source,
                table,
                key,
                result: value,
                constructor: true,
            });
        }
        for (a, b) in unions {
            symbols.equal(a, b);
        }
        if congruence {
            symbols.close(&facts);
        }
    }
    let complete = is_complete(p, path.last().unwrap().1.0, &program, congruence);
    Terminal {
        reuse: program,
        queries,
        complete,
    }
}
/// Shared by copied/published cursors. Empty stages maintain real offsets;
/// trimming at the largest compiled distance bounds the history.
#[derive(Debug)]
enum Trail {
    One(Results),
    // Each entry is empty or One. Reuse an existing One when a later Cell
    // needs a deeper history; do not copy its results into another owner.
    Many(Vec<Option<Rc<Trail>>>),
}
#[derive(Clone, Debug, Default)]
pub(crate) struct History {
    frames: Option<Rc<Trail>>,
    // Empty intermediate Cells advance source-stage positions without
    // republishing the same results into another history container.
    empty: usize,
}
#[derive(Default)]
pub(crate) struct CaptureWork {
    pub reads: usize,
    pub slots: usize,
    pub allocations: usize,
    pub empty_slots: usize,
    pub carried: bool,
}
impl History {
    fn one(results: Option<Results>) -> Self {
        Self { frames: results.map(|r| Rc::new(Trail::One(r))), empty: 0 }
    }
    /// Advance across a Cell with no actual exported results. The existing
    /// immutable frames stay shared; trim only when the compiled lifetime ends.
    fn carry(&mut self, limit: usize, work: &mut CaptureWork) {
        if self.frames.is_none() { return; }
        self.empty += 1;
        let keep = limit.saturating_sub(self.empty);
        if keep == 0 { *self = Self::default(); return; }
        if let Some(Trail::Many(frames)) = self.frames.as_deref() {
            if frames.len() > keep {
                if keep == 1 {
                    // A nonempty history always ends with its last real frame.
                    self.frames = frames.last().unwrap().clone();
                } else {
                    let retained = frames[frames.len() - keep..].to_vec();
                    work.slots += retained.len();
                    work.allocations += 2;
                    self.frames = Some(Rc::new(Trail::Many(retained)));
                }
            }
        }
        work.carried = true;
    }
    /// One existing frame, excluding empty-stage bookkeeping. Many never
    /// embeds another Many, so retaining a result cannot retain expired history.
    fn snapshot(&self, back: usize) -> Option<Rc<Trail>> {
        let back = back.checked_sub(self.empty).filter(|&b| b > 0)?;
        match self.frames.as_deref() {
            Some(Trail::One(_)) if back == 1 => self.frames.clone(),
            Some(Trail::Many(v)) => v.len().checked_sub(back).and_then(|i| v[i].clone()),
            _ => None,
        }
    }
    pub(crate) fn current(&self) -> Option<&Results> { self.frame(1) }
    pub(crate) fn capture(
        &mut self,
        limit: usize,
        rid: usize,
        wanted: &[Capture],
        read: impl Fn(usize) -> Option<Dependency>,
        effect: impl Fn(usize) -> Option<Dependency>,
    ) -> CaptureWork {
        if limit == 0 {
            *self = Self::default();
            return CaptureWork::default();
        }
        if wanted.is_empty() {
            let mut work = CaptureWork::default();
            self.carry(limit, &mut work);
            return work;
        }
        let mut results = Results::new(rid);
        let mut empty_slots = 0;
        for capture in wanted {
            let w = match capture.site {
                Site::Query(i) => read(i),
                Site::Effect(i) => effect(i),
            };
            if let Some(w) = w {
                empty_slots += results.insert(capture.port, w);
            }
        }
        let mut work = CaptureWork { reads: wanted.len(), slots: results.len(),
            empty_slots, allocations: 0, carried: false };
        let frame = (results.len() != 0).then_some(results);
        if frame.is_none() {
            self.carry(limit, &mut work);
            return work;
        }
        if limit == 1 || self.frames.is_none() || self.empty >= limit - 1 {
            work.allocations = usize::from(frame.is_some());
            *self = Self::one(frame);
            return work;
        }
        let stored = match self.frames.as_deref() {
            Some(Trail::Many(v)) => v.len(),
            Some(Trail::One(_)) => 1,
            _ => 0,
        };
        let retained = (stored + self.empty).min(limit - 1);
        work.slots += retained + 1;
        work.allocations = 3;
        let mut v = Vec::with_capacity(retained + 1);
        v.extend((1..=retained).rev().map(|back| self.snapshot(back)));
        v.push(Self::one(frame).frames);
        *self = Self { frames: Some(Rc::new(Trail::Many(v))), empty: 0 };
        work
    }
    pub(crate) fn get(&self, back: usize, port: ResultPort) -> Option<Dependency> {
        self.frame(back)?.get(port)
    }
    fn frame(&self, back: usize) -> Option<&Results> {
        let back = back.checked_sub(self.empty).filter(|&b| b > 0)?;
        match self.frames.as_deref()? {
            Trail::One(e) if back == 1 => Some(e),
            Trail::Many(v) => match v.get(v.len().checked_sub(back)?)?.as_deref()? {
                Trail::One(result) => Some(result),
                Trail::Many(_) => unreachable!("Cell history entries contain one completed frame"),
            },
            _ => return None,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct Terminal {
    pub reuse: Vec<Reuse>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub queries: Vec<QueryReuse>,
    pub complete: bool,
}
pub(crate) fn terminal(
    p: &Program,
    path: &[(Option<usize>, Entry)],
    congruence: bool,
    query_ports: bool,
) -> Terminal {
    derive_stage(p, path, congruence, query_ports)
}

#[derive(Clone, Debug, Default)]
pub(crate) struct Switch {
    reuse_results: bool,
    pub(crate) congruence: bool,
    pub(crate) query_ports: bool,
    nodes: Vec<Node>,
    by_rule: Vec<Vec<Option<usize>>>,
    roots: Vec<Option<usize>>,
    initial: Vec<usize>,
    leaves: BTreeMap<Entry, usize>,
    pub exports: Vec<Vec<Site>>,
    pub depth: usize,
}
#[derive(Clone, Debug, Serialize)]
struct Node {
    unit: usize,
    failure: usize,
    program: Terminal,
    next: Vec<((usize, usize), usize)>,
    supply: Vec<Capture>,
    #[serde(skip)]
    keep_history: usize,
}

/// Liveness after this Cell completes. A successor's direct read needs `back`
/// frames; its future retention needs one fewer before it adds its own frame.
/// Include inherited edges and default restarts, not just trie children.
fn retained_depths(nodes: &[Node], initial: &[usize]) -> Vec<usize> {
    let reads = nodes.iter().map(|n| n.program.reuse.iter().map(|r| r.back)
        .chain(n.program.queries.iter().map(|r| r.back)).max().unwrap_or(0)).collect::<Vec<_>>();
    let mut keep = nodes.iter().map(|n| usize::from(!n.supply.is_empty())).collect::<Vec<_>>();
    loop {
        let fallback = initial.iter().map(|&j| reads[j].max(keep[j].saturating_sub(1))).max().unwrap_or(0);
        let mut changed = false;
        for (i, node) in nodes.iter().enumerate() {
            let need = node.next.iter().map(|&(_, j)| reads[j].max(keep[j].saturating_sub(1)))
                .max().unwrap_or(0).max(fallback);
            if need > keep[i] { keep[i] = need; changed = true; }
        }
        if !changed { return keep; }
    }
}
impl Default for Terminal {
    fn default() -> Self {
        Self {
            reuse: vec![],
            queries: vec![],
            complete: false,
        }
    }
}
impl Switch {
    /// Lower the validated portable transfer certificate with the Cell's own
    /// alias proofs. Keep one executable completion flag, without changing the
    /// historical wire certificate or relaxing its exact validation.
    pub(crate) fn complete_cells(&mut self, p: &Program, rule: impl Fn(usize) -> usize) {
        for node in self.nodes.iter_mut().skip(1) {
            let rid = rule(node.unit);
            node.program.complete = !node.program.reuse.is_empty()
                && Definition::new(p, rid).expect("validated Cell")
                    .closes_with(&p.known_results.static_skip[rid], self.congruence,
                        |op| node.program.reuse.iter().any(|r| r.op == op));
        }
    }

    /// Retain only prefixes which can supply a terminal operation. Compile
    /// inherited suffix jumps once, so a cold entry is a direct leaf reset.
    pub(crate) fn build<'a>(
        p: &Program,
        paths: impl Iterator<Item = &'a [(Option<usize>, Entry)]>,
        leaves: &BTreeMap<Entry, usize>,
        reuse_results: bool,
        congruence: bool,
        query_ports: bool,
    ) -> Self {
        let mut prefixes = BTreeMap::new();
        let mut units = BTreeMap::new();
        for (id, path) in paths.enumerate() {
            units.insert(path.to_vec(), id);
            for i in 1..=path.len() {
                prefixes.entry(path[..i].to_vec()).or_insert_with(|| {
                    if reuse_results {
                        terminal(p, &path[..i], congruence, query_ports)
                    } else {
                        Terminal::default()
                    }
                });
            }
        }
        let mut paths = prefixes.into_iter().collect::<Vec<_>>();
        paths.sort_by_key(|(p, _)| p.len());
        let blank = || Node {
            unit: 0,
            failure: 0,
            program: Default::default(),
            next: vec![],
            supply: vec![],
            keep_history: 0,
        };
        let mut nodes = vec![blank()];
        let mut ids = BTreeMap::new();
        let mut initial = vec![0; leaves.len()];
        let mut exports = vec![vec![]; p.rules.len()];
        let mut depth = 0;
        for (path, mut program) in paths {
            let id = nodes.len();
            let &(op, entry) = path.last().unwrap();
            let leaf = leaves[&entry];
            let failure = if path.len() == 1 {
                initial[leaf] = id;
                0
            } else {
                let parent: usize = ids[&path[..path.len() - 1]];
                nodes[parent].next.push(((op.unwrap(), leaf), id));
                (1..path.len())
                    .find_map(|i| {
                        let mut suffix = path[i..].to_vec();
                        suffix[0].0 = None;
                        ids.get(&suffix).copied()
                    })
                    .unwrap_or(0)
            };
            for rule in &nodes[failure].program.reuse {
                if !program.reuse.iter().any(|r| r.op == rule.op) {
                    program.reuse.push(rule.clone());
                }
            }
            program.reuse.sort_by_key(|r| r.op);
            for rule in &nodes[failure].program.queries {
                if !program.queries.iter().any(|r| r.atom == rule.atom) {
                    program.queries.push(rule.clone());
                }
            }
            program.queries.sort_by_key(|r| r.atom);
            program.complete = is_complete(p, entry.0, &program.reuse, congruence);
            for (back, rule, source) in program
                .reuse
                .iter()
                .map(|r| (r.back, r.rule, r.donor))
                .chain(program.queries.iter().map(|r| (r.back, r.rule, r.donor)))
            {
                let donor: usize = ids[&path[..path.len() - back]];
                nodes[donor].supply.push(Capture {
                    site: source, port: ResultPort::new(rule, 0),
                });
                exports[rule].push(source);
                depth = depth.max(back);
            }
            let unit = units.get(&path).copied().unwrap_or(nodes[failure].unit);
            ids.insert(path, id);
            nodes.push(Node {
                unit,
                failure,
                program,
                ..blank()
            });
        }
        for id in 1..nodes.len() {
            let (earlier, rest) = nodes.split_at_mut(id);
            let n = &mut rest[0];
            let inherited = &earlier[n.failure];
            for &(edge, next) in &inherited.next {
                if !n.next.iter().any(|&(e, _)| e == edge) {
                    n.next.push((edge, next));
                }
            }
            n.supply.extend_from_slice(&inherited.supply);
            n.supply.sort_unstable();
            n.supply.dedup();
            n.next.sort_unstable_by_key(|x| x.0);
        }
        for s in &mut exports {
            s.sort_unstable();
            s.dedup();
        }
        let keep = retained_depths(&nodes, &initial);
        for (node, keep) in nodes.iter_mut().zip(keep) {
            node.keep_history = keep;
        }
        // Every reader and writer uses this one Cell result layout. Runtime
        // frames no longer repeat Site tags or search them on each access.
        let port = |rule: usize, site: Site| ResultPort::new(rule,
            exports[rule].binary_search(&site).expect("compiled Cell export"));
        for node in &mut nodes {
            for capture in &mut node.supply {
                capture.port = port(capture.port.rule(), capture.site);
            }
            for read in &mut node.program.reuse {
                read.port = Some(port(read.rule, read.donor));
            }
            for read in &mut node.program.queries {
                read.port = Some(port(read.rule, read.donor));
            }
        }
        let mut by_rule = vec![vec![]; p.rules.len()];
        let mut roots = vec![None; p.rules.len()];
        for (&(rid, pivot), &leaf) in leaves {
            let Some(pivot) = pivot else {
                roots[rid] = Some(leaf);
                continue;
            };
            let entries = &mut by_rule[rid];
            entries.resize(entries.len().max(pivot + 1), None);
            entries[pivot] = Some(leaf);
        }
        Self {
            reuse_results,
            congruence,
            query_ports,
            nodes,
            by_rule,
            roots,
            initial,
            leaves: leaves.clone(),
            exports,
            depth,
        }
    }
    pub(crate) fn leaf(&self, r: usize, p: usize) -> Option<usize> {
        self.by_rule.get(r)?.get(p).copied().flatten()
    }
    pub(crate) fn unique_root(&self, rule: usize, require_supply: bool) -> Option<usize> {
        if let Some(leaf) = self.roots.get(rule).copied().flatten() {
            let pc = self.initial[leaf];
            return (!require_supply || !self.nodes[pc].supply.is_empty()).then_some(pc);
        }
        let mut leaves = self.by_rule.get(rule)?.iter().flatten();
        let leaf = *leaves.next()?;
        if leaves.next().is_some() {
            return None;
        }
        let pc = self.initial[leaf];
        (!require_supply || !self.nodes[pc].supply.is_empty()).then_some(pc)
    }
    pub(crate) fn active(&self, pc: usize) -> usize {
        self.nodes[pc].unit
    }
    pub(crate) fn advance(&self, state: usize, op: usize, leaf: usize) -> usize {
        let jumps = &self.nodes[state].next;
        jumps
            .iter()
            .find(|(k, _)| *k == (op, leaf))
            .map_or(self.initial[leaf], |x| x.1)
    }
    pub(crate) fn capture(&self, id: usize) -> (&[Capture], usize) {
        self.nodes.get(id).map_or((&[], 0), |n| (n.supply.as_slice(), n.keep_history))
    }
    pub(crate) fn program(&self, id: usize) -> Option<&Terminal> {
        self.nodes.get(id).map(|n| &n.program)
    }
    pub(crate) fn artifact(&self) -> serde_json::Value {
        serde_json::json!({"schema":if self.query_ports {"eggfuse-result-switch/v3"} else if self.congruence {"eggfuse-result-switch/v2"} else {"eggfuse-result-switch/v1"},"reuse_results":self.reuse_results,"initial_entries":self.initial,"states":self.nodes,"max_back":self.depth})
    }
    pub(crate) fn enabled(&self) -> bool {
        !self.nodes.is_empty()
    }
    pub(crate) fn replay(&self, path: &[(Option<usize>, Entry)]) -> usize {
        path.iter().fold(0, |s, (op, e)| {
            self.advance(s, op.unwrap_or(0), self.leaves[e])
        })
    }
}

fn is_complete(p: &Program, r: usize, reuse: &[Reuse], congruence: bool) -> bool {
    !reuse.is_empty()
        && Definition::new(p, r).expect("validated Cell")
            .closes_with(&[], congruence, |op| reuse.iter().any(|r| r.op == op))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn compiled_result_ports_preserve_holes_and_real_returned_addresses() {
        let first = ResultPort::new(4, 0);
        let last = ResultPort::new(4, 2);
        let captures = [Capture { site: Site::Query(1), port: first },
            Capture { site: Site::Effect(7), port: last }];
        // The effect reused another Cell's constructor. Its result address
        // cannot be derived from either its local op or its result slot.
        let reused = Dependency::Fact(FactRef { cell: 91, op: 3 });
        let mut history = History::default();
        let work = history.capture(1, 4, &captures, |_| None, |_| Some(reused));
        assert_eq!(work.reads, 2);
        assert_eq!(work.slots, 3);
        assert_eq!(work.empty_slots, 2);
        assert_eq!(history.get(1, last), Some(reused));
        assert_eq!(history.get(1, first), None);
        assert_eq!(history.get(1, ResultPort::new(5, 2)), None);
        assert_eq!(history.get(0, last), None);
        assert_eq!(history.get(2, last), None);
        // An absent source on the next execution never inherits the old value.
        history.capture(1, 4, &captures, |_| None, |_| None);
        assert_eq!(history.get(1, last), None);
    }
    #[test]
    fn result_ports_keep_empty_stage_offsets_and_trim_old_instances() {
        let port = ResultPort::new(4, 0);
        let capture = [Capture { site: Site::Effect(2), port }];
        let old = Dependency::Function(9);
        let new = Dependency::Function(12);
        let mut history = History::default();
        history.capture(3, 4, &capture, |_| None, |_| Some(old));
        history.capture(3, 8, &[], |_| None, |_| None);
        assert_eq!(history.get(1, port), None);
        assert_eq!(history.get(2, port), Some(old));
        history.capture(3, 4, &capture, |_| None, |_| Some(new));
        assert_eq!(history.get(1, port), Some(new));
        assert_eq!(history.get(3, port), Some(old));
        history.capture(3, 8, &[], |_| None, |_| None);
        assert_eq!(history.get(2, port), Some(new));
        assert_eq!(history.get(4, port), None);
    }
    #[test]
    fn changing_cell_retention_preserves_shared_frames_and_empty_stages() {
        let port = ResultPort::new(4, 0);
        let capture = [Capture { site: Site::Effect(2), port }];
        let old = Dependency::Function(9);
        let new = Dependency::Function(12);
        let mut history = History::default();
        assert_eq!(history.capture(1, 4, &capture, |_| None, |_| Some(old)).allocations, 1);
        let published = history.clone();
        assert_eq!(history.capture(2, 8, &[], |_| None, |_| None).allocations, 0);
        assert_eq!(history.get(1, port), None);
        assert_eq!(history.get(2, port), Some(old));
        history.capture(1, 4, &capture, |_| None, |_| Some(new));
        assert_eq!(history.get(1, port), Some(new));
        assert_eq!(history.get(2, port), None);
        history.capture(3, 8, &[], |_| None, |_| None);
        history.capture(3, 8, &[], |_| None, |_| None);
        assert_eq!(history.get(3, port), Some(new));
        history.capture(0, 8, &[], |_| None, |_| None);
        assert!(history.frames.is_none());
        assert_eq!(published.get(1, port), Some(old));
    }
    #[test]
    fn empty_completion_keeps_the_original_owner_and_releases_expired_frames() {
        let port = ResultPort::new(4, 0);
        let capture = [Capture { site: Site::Effect(2), port }];
        let mut history = History::default();
        history.capture(4, 4, &capture, |_| None, |_| Some(Dependency::Function(9)));
        let owner = Rc::downgrade(history.frames.as_ref().unwrap());
        let published = history.clone();
        for back in 2..=4 {
            let work = history.capture(4, 8, &[], |_| None, |_| None);
            assert!(work.carried);
            assert_eq!((work.reads, work.slots, work.allocations), (0, 0, 0));
            assert!(Rc::ptr_eq(history.frames.as_ref().unwrap(), published.frames.as_ref().unwrap()));
            assert_eq!(history.get(back, port), Some(Dependency::Function(9)));
            assert_eq!(history.current().map(|r| r.get(port)), None);
        }
        history.capture(4, 8, &[], |_| None, |_| None);
        assert!(history.frames.is_none());
        assert_eq!(published.get(1, port), Some(Dependency::Function(9)));
        drop(published);
        assert!(owner.upgrade().is_none());
    }
    #[test]
    fn carried_cells_match_a_dense_stage_history_through_missing_results_and_resets() {
        let captures = [Capture { site: Site::Query(0), port: ResultPort::new(4, 0) },
            Capture { site: Site::Effect(2), port: ResultPort::new(4, 2) }];
        let mut history = History::default();
        let mut dense = Vec::<[Option<Dependency>; 3]>::new();
        let mut published = vec![];
        let mut random = 17u64;
        for step in 0..300 {
            random = random.wrapping_mul(6364136223846793005).wrapping_add(1);
            let limit = (random >> 32) as usize % 6;
            let empty = random & 3 == 0;
            let a = (!empty && random & 4 != 0).then_some(Dependency::Function(step * 2));
            let b = (!empty && random & 8 != 0).then_some(Dependency::Function(step * 2 + 1));
            history.capture(limit, 4, if empty { &[] } else { &captures }, |_| a, |_| b);
            dense.push([a, None, b]);
            dense.drain(..dense.len().saturating_sub(limit));
            if step % 11 == 0 { published.push((history.clone(), dense.clone())); }
            for (h, d) in std::iter::once((&history, &dense)).chain(published.iter().map(|(h, d)| (h, d))) {
                for back in 0usize..=7 {
                    for slot in 0..3 {
                        let expected = back.checked_sub(1).and_then(|b| d.len().checked_sub(b + 1)).and_then(|i| d[i][slot]);
                        assert_eq!(h.get(back, ResultPort::new(4, slot)), expected, "step {step}, back {back}, slot {slot}");
                        assert_eq!(h.get(back, ResultPort::new(5, slot)), None);
                    }
                }
            }
        }
    }
    #[test]
    fn completed_cells_retain_only_reachable_future_reads() {
        let node = |supply: bool, back, next| Node {
            unit: 0, failure: 0,
            program: Terminal {
                reuse: if back == 0 { vec![] } else { vec![Reuse {
                    equal_output: true, op: 0, back, rule: 4,
                    donor: Site::Effect(2), port: None,
                }] }, ..Default::default()
            },
            next, supply: if supply { vec![Capture {
                site: Site::Effect(2), port: ResultPort::new(4, 0),
            }] } else { vec![] }, keep_history: 0,
        };
        let nodes = [node(false, 0, vec![]),
            node(true, 0, vec![((0, 0), 2)]),
            node(false, 0, vec![((0, 0), 3)]),
            node(false, 2, vec![((0, 0), 1)]),
            node(false, 0, vec![])];
        // A saves one current result, AB carries it through an empty stage,
        // ABC consumes it and can release history, including on restart.
        assert_eq!(retained_depths(&nodes, &[1, 4]), vec![0, 1, 2, 0, 0]);
    }
    #[test]
    fn conditional_closure_matches_full_scan_through_hides_and_pending_unions() {
        let mut symbols = Symbols::default();
        let mut index = FactIndex::default();
        let mut facts = vec![];
        for _ in 0..90 {
            symbols.fresh();
        }
        let mut seed = 193u64;
        for step in 0..800 {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            let table = (seed >> 32) as usize % 7;
            let key = vec![(seed as usize >> 8) % 90, (seed as usize >> 18) % 90];
            let result = symbols.fresh();
            if let Some(i) = index.find(&mut symbols, &facts, table, &key) {
                symbols.equal(result, facts[i].result);
            }
            facts.push(Fact {
                stage: step,
                rule: 0,
                source: Site::Effect(step),
                table,
                key,
                result,
                constructor: true,
            });
            if step % 13 == 0 {
                facts.retain(|f| f.table != (table + 1) % 7);
                index.clear(&mut symbols);
            }
            // Includes changes to the most recently appended, unindexed key.
            if step % 5 == 0 {
                symbols.equal((seed as usize >> 8) % 90, (step * 11) % 90);
            }
            if step % 3 == 0 {
                let mut reference = symbols.clone();
                reference.close_full(&facts);
                symbols.close(&facts);
                for i in 0..symbols.len() {
                    assert_eq!(
                        symbols.root(i),
                        reference.root(i),
                        "step={step}, symbol={i}"
                    );
                }
                assert!(!symbols.observer.congruence_dirty);
            }
        }
    }
    #[test]
    fn indexed_donors_match_reverse_scan_after_unions_appends_and_deletions() {
        let mut symbols = Symbols::default();
        for _ in 0..64 {
            symbols.fresh();
        }
        let mut facts = vec![];
        let mut index = FactIndex::default();
        let mut state = 7u64;
        let mut next = || {
            state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
            (state >> 32) as usize
        };
        for turn in 0..600 {
            let table = next() % 5;
            let key = vec![next() % 64, next() % 64];
            if turn % 7 == 0 {
                symbols.equal(next() % 64, next() % 64);
            }
            if turn % 23 == 0 {
                facts.retain(|f: &Fact| f.table != table);
                index.clear(&mut symbols);
            }
            if turn % 3 != 0 {
                facts.push(Fact {
                    stage: turn,
                    rule: 0,
                    source: Site::Effect(turn),
                    table,
                    key: key.clone(),
                    result: next() % 64,
                    constructor: true,
                });
            }
            // Appended facts may be unindexed when a subsequent union arrives.
            if turn % 11 == 0 {
                symbols.equal(next() % 64, next() % 64);
            }
            let found = index.find(&mut symbols, &facts, table, &key);
            let expected = facts
                .iter()
                .rposition(|f| f.table == table && symbols.same_key(&f.key, &key));
            assert_eq!(found, expected, "turn {turn}");
            for f in &facts {
                let found = index.find(&mut symbols, &facts, f.table, &f.key);
                assert_eq!(
                    found,
                    facts
                        .iter()
                        .rposition(|g| g.table == f.table && symbols.same_key(&g.key, &f.key))
                );
            }
        }
    }
}
