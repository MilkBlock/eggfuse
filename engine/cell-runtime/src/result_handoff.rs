//! Symbolic SSA keys on one finite, witnessed block path. Constructor receipts
//! can also prove result equality. Mutable receipts prove only a row location;
//! a query must read its current result and check visibility and the full key.
use crate::{
    graph::{Dependency, FactRef},
    iterative::Entry,
    cell::{Definition, Site},
    program::*,
    value::Value,
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
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct QueryReuse {
    pub atom: usize,
    pub back: usize,
    pub rule: usize,
    pub donor: Site,
}
#[derive(Clone, Copy)]
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
struct Symbols {
    parents: Vec<usize>,
    literals: BTreeMap<Value, usize>,
    indexed_roots: BTreeSet<usize>,
    key_epoch: usize,
    congruence_dirty: bool,
}
impl Symbols {
    fn fresh(&mut self) -> usize {
        let i = self.parents.len();
        self.parents.push(i);
        i
    }
    fn root(&self, mut i: usize) -> usize {
        while self.parents[i] != i {
            i = self.parents[i]
        }
        i
    }
    fn equal(&mut self, a: usize, b: usize) {
        let a = self.root(a);
        let b = self.root(b);
        // Fresh output aliases normally do not change any existing fact key.
        if a != b && self.indexed_roots.contains(&a.max(b)) {
            self.key_epoch += 1;
            self.congruence_dirty = true;
        }
        self.parents[a.max(b)] = a.min(b);
    }
    fn arg(&mut self, a: &Arg, slots: &[usize]) -> usize {
        match a {
            Arg::Slot(s) => slots[*s],
            Arg::Literal(v) => {
                if let Some(&i) = self.literals.get(v) {
                    return i;
                }
                let i = self.fresh();
                self.literals.insert(v.clone(), i);
                i
            }
        }
    }
    #[cfg(test)]
    fn same_key(&self, a: &[usize], b: &[usize]) -> bool {
        a.len() == b.len() && a.iter().zip(b).all(|(&x, &y)| self.root(x) == self.root(y))
    }

    /// Compile-time closure over the surviving, witnessed constructor facts.
    /// Call only at a source boundary or after collecting the complete LHS;
    /// queued RHS unions must not become visible to earlier RHS instructions.
    fn close(&mut self, facts: &[Fact]) {
        if self.congruence_dirty {
            self.close_full(facts);
        }
    }
    fn close_full(&mut self, facts: &[Fact]) {
        loop {
            let mut keys = BTreeMap::new();
            let mut changed = false;
            for f in facts {
                if !f.constructor {
                    continue;
                }
                let key = (
                    f.table,
                    f.key.iter().map(|&i| self.root(i)).collect::<Vec<_>>(),
                );
                self.indexed_roots.extend(&key.1);
                if let Some(other) = keys.insert(key, f.result)
                    && self.root(other) != self.root(f.result)
                {
                    self.equal(other, f.result);
                    changed = true;
                }
            }
            if !changed {
                break;
            }
        }
        self.congruence_dirty = false;
    }
}
/// Exact canonical keys, retaining the most recent donor like the reverse scan.
/// This is a compiler lookup index, not another equality solver.
#[derive(Default)]
struct FactIndex {
    keys: BTreeMap<(usize, Vec<usize>), usize>,
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
        if self.epoch != symbols.key_epoch {
            self.clear(symbols);
        }
        for (i, f) in facts.iter().enumerate().skip(self.indexed) {
            let key = f.key.iter().map(|&s| symbols.root(s)).collect::<Vec<_>>();
            symbols.indexed_roots.extend(&key);
            self.keys.insert((f.table, key), i);
        }
        self.indexed = facts.len();
        self.epoch = symbols.key_epoch;
        let key = key.iter().map(|&s| symbols.root(s)).collect::<Vec<_>>();
        // Register the pending fact too, before its source-boundary unions.
        symbols.indexed_roots.extend(&key);
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
                let into = symbols.arg(arg, &slots);
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
            let result = symbols.arg(&relation.result, &slots);
            let key = relation.keys
                .iter()
                .map(|a| symbols.arg(a, &slots))
                .collect::<Vec<_>>();
            if let Some(i) = index.find(&mut symbols, &facts, table, &key) {
                let f = &facts[i];
                if query_ordered && Some(atom) != pivot && f.stage != stage {
                    queries.push(QueryReuse {
                        atom,
                        back: stage - f.stage,
                        rule: f.rule,
                        donor: f.source,
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
                    slots[*dst] = symbols.arg(a, &slots);
                    continue;
                }
                Op::Union(a, b) => {
                    unions.push((symbols.arg(a, &slots), symbols.arg(b, &slots)));
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
                .map(|a| symbols.arg(a, &slots))
                .collect::<Vec<_>>();
            let value = symbols.arg(&relation.result, &slots);
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
#[derive(Clone, Debug)]
struct Exports {
    rule: usize,
    rows: smallvec::SmallVec<[(Site, Dependency); 2]>,
}
/// Shared by copied/published cursors. Empty stages maintain real offsets;
/// trimming at the largest compiled distance bounds the history.
#[derive(Debug)]
enum Trail {
    One(Exports),
    Many(Vec<Option<Rc<Exports>>>),
}
#[derive(Clone, Debug, Default)]
pub(crate) struct History(Option<Rc<Trail>>);
#[derive(Default)]
pub(crate) struct CaptureWork {
    pub reads: usize,
    pub slots: usize,
    pub allocations: usize,
}
impl History {
    pub(crate) fn current_source(&self, rule: usize, source: Site, steps: &mut u64) -> Option<Dependency> {
        let e = match self.0.as_deref()? {
            Trail::One(e) => e,
            Trail::Many(v) => v.last()?.as_deref()?,
        };
        if e.rule != rule { return None; }
        e.rows.iter().find(|x| { *steps += 1; x.0 == source }).map(|x| x.1)
    }
    pub(crate) fn capture(
        &mut self,
        limit: usize,
        rid: usize,
        wanted: &[Site],
        read: impl Fn(usize) -> Option<Dependency>,
        effect: impl Fn(usize) -> Option<Dependency>,
    ) -> CaptureWork {
        if limit == 0 || (wanted.is_empty() && self.0.is_none()) {
            return CaptureWork::default();
        }
        let mut rows = smallvec::SmallVec::new();
        for &d in wanted {
            let w = match d {
                Site::Query(i) => read(i),
                Site::Effect(i) => effect(i),
            };
            if let Some(w) = w {
                rows.push((d, w));
            }
        }
        let mut work = CaptureWork { reads: wanted.len(), slots: rows.len(), allocations: 0 };
        let frame = (!rows.is_empty()).then_some(Exports { rule: rid, rows });
        if limit == 1 {
            work.allocations = usize::from(frame.is_some());
            self.0 = frame.map(|f| Rc::new(Trail::One(f)));
            return work;
        }
        let prev = match self.0.as_deref() {
            Some(Trail::Many(v)) => v.as_slice(),
            _ => &[],
        };
        let prev = &prev[prev.len().saturating_sub(limit - 1)..];
        if frame.is_none() && !prev.iter().any(Option::is_some) {
            self.0 = None;
            return work;
        }
        work.slots += prev.len() + 1;
        work.allocations = 2 + usize::from(frame.is_some());
        let mut v = Vec::with_capacity(prev.len() + 1);
        v.extend_from_slice(prev);
        v.push(frame.map(Rc::new));
        self.0 = Some(Rc::new(Trail::Many(v)));
        work
    }
    pub(crate) fn get(&self, r: &Reuse) -> Option<FactRef> {
        match self.get_donor(r.back, r.rule, r.donor)? {
            Dependency::Fact(f) => Some(f),
            _ => None,
        }
    }
    pub(crate) fn get_query(&self, r: &QueryReuse) -> Option<Dependency> {
        self.get_donor(r.back, r.rule, r.donor)
    }
    fn get_donor(&self, back: usize, rule: usize, donor: Site) -> Option<Dependency> {
        let e = match self.0.as_deref()? {
            Trail::One(e) if back == 1 => e,
            Trail::Many(v) => v.get(v.len().checked_sub(back)?)?.as_deref()?,
            _ => return None,
        };
        (e.rule == rule)
            .then(|| e.rows.iter().find(|x| x.0 == donor).map(|x| x.1))
            .flatten()
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
    supply: Vec<Site>,
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
                nodes[donor].supply.push(source);
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
    pub(crate) fn supply(&self, id: usize) -> &[Site] {
        self.nodes.get(id).map_or(&[], |n| n.supply.as_slice())
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
        && p.templates[p.rules[r].template]
            .ops
            .iter()
            .enumerate()
            .all(|(i, o)| {
                matches!(o, Op::Copy(..))
                    || (congruence && matches!(o, Op::Union(..)))
                    || reuse.iter().any(|x| x.op == i)
            })
}

#[cfg(test)]
mod tests {
    use super::*;
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
                for i in 0..symbols.parents.len() {
                    assert_eq!(
                        symbols.root(i),
                        reference.root(i),
                        "step={step}, symbol={i}"
                    );
                }
                assert!(!symbols.congruence_dirty);
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
