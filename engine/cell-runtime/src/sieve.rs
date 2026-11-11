//! Sieve-style semijoin summaries over COMPLETE visible virtual tables.
//! A filter is a necessary condition, never a proof that a binding exists.
//! Interned by table/columns/dependencies, not ruleset or source variable names.
use crate::{
    graph::{Dependency, Graph},
    program::{Call, Program, Result},
    query::QueryIndexes,
};
use rustc_hash::FxHashMap as HashMap;
#[cfg(not(feature = "sparse-cells"))]
use rustc_hash::FxHashSet as HashSet;
use std::collections::VecDeque;
use std::hash::{Hash, Hasher};
#[cfg(feature = "entry-admission-audit")]
#[path = "entry_admission_audit.rs"]
mod entry_audit;
#[cfg(feature = "cell-entry-reverse")]
#[path = "sieve_reverse.rs"]
mod reverse;
#[cfg(feature = "cell-entry-reverse")]
use reverse::Stats as ReverseStats;

#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
struct Guard {
    cols: Vec<usize>,
    child: usize,
}
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct Spec {
    table: usize,
    cols: Vec<usize>,
    guards: Vec<Guard>,
    read_columns: u64,
}
impl Spec {
    fn new(table: usize, cols: Vec<usize>, guards: Vec<Guard>) -> Self {
        let read_columns = cols.iter().chain(guards.iter().flat_map(|g| &g.cols))
            .fold(0, |mask, &c| mask | crate::query::column_bit(c));
        Self { table, cols, guards, read_columns }
    }
    /// Narrow Cell projections use exact inline-width support keys in allows().
    /// Only wider projections (or the legacy representation) read the Bloom.
    fn needs_bloom(&self) -> bool {
        !cfg!(feature = "sparse-cells") || self.cols.len() > 2
    }
}
#[derive(Clone)]
struct Influence {
    columns: u64,
    members: std::ops::Range<usize>,
    // Number of existing Summary::built members, updated only by ensure/reset.
    built: usize,
}
#[derive(Clone, Default)]
struct Dispatch {
    // One flat member array serves both complete and field-selective publication.
    members: Vec<usize>,
    groups: Vec<Influence>,
    built: usize,
}
#[cfg(feature = "sparse-cells")]
#[path = "support_keys.rs"]
mod support_keys;
#[cfg(feature = "sparse-cells")]
type Support = support_keys::Support;
#[cfg(not(feature = "sparse-cells"))]
type Support = HashSet<Vec<u64>>;
#[cfg(feature = "sparse-cells")]
type Projection = smallvec::SmallVec<[u64; 3]>;
#[cfg(not(feature = "sparse-cells"))]
type Projection = Vec<u64>;
#[derive(Default)]
struct Summary {
    built: bool,
    keys: Support,
    bloom: Bloom,
}
impl Summary {
    fn allows(&self, keys: &[u64], cols: &[usize]) -> bool {
        #[cfg(feature = "sparse-cells")]
        match (&self.keys, cols) {
            (Support::Empty, _) => return false,
            (Support::Unit, []) => return true,
            (Support::One(words), &[c]) => return words.contains(&keys[c]),
            (Support::Two(words), &[a,b]) => return words.contains(&[keys[a],keys[b]]),
            _ => (),
        }
        self.bloom.contains_projection(keys, cols)
    }
}
#[derive(Default)]
struct Bloom {
    words: Vec<u64>,
    collide: bool,
}
fn hash(xs: &[u64]) -> u64 {
    hash_projection(xs.iter().copied(), xs.len())
}
fn hash_projection(xs: impl Iterator<Item = u64>, len: usize) -> u64 {
    let mut h = rustc_hash::FxHasher::default();
    len.hash(&mut h);
    for x in xs {
        x.hash(&mut h)
    }
    h.finish()
}
impl Bloom {
    fn location_hash(&self, h: u64) -> (usize, u64) {
        let h = if self.collide { 0 } else { h };
        let mask = (1 << ((h >> 32) & 63)) | (1 << ((h >> 38) & 63)) | (1 << ((h >> 44) & 63));
        ((h as usize) & (self.words.len() - 1), mask)
    }
    #[cfg(test)]
    fn contains(&self, xs: &[u64]) -> bool {
        if self.words.is_empty() {
            return false;
        }
        let (i, m) = self.location_hash(hash(xs));
        self.words[i] & m == m
    }
    fn contains_projection(&self, keys: &[u64], cols: &[usize]) -> bool {
        if self.words.is_empty() {
            return false;
        }
        let (i, m) = self.location_hash(hash_projection(cols.iter().map(|c| keys[*c]), cols.len()));
        self.words[i] & m == m
    }
    fn insert(&mut self, xs: &[u64]) {
        let (i, m) = self.location_hash(hash(xs));
        self.words[i] |= m;
    }
    fn grow(&mut self, keys: &Support, collide: bool) {
        self.collide = collide;
        let size = (keys.len().saturating_mul(16).div_ceil(64))
            .max(1)
            .next_power_of_two();
        if self.words.len() >= size {
            return;
        }
        self.words = vec![0; size];
        for k in keys {
            self.insert(k)
        }
    }
}
#[derive(Default, serde::Serialize)]
pub struct Stats {
    pub builds: u64,
    pub rule_uses: u64,
    pub reused_summaries: u64,
    pub build_rows: u64,
    pub update_rows: u64,
    pub column_checks: u64,
    pub publication_dispatches: u64,
    pub inactive_publications: u64,
    pub unchanged_column_rows: u64,
    pub dependency_rows: u64,
    pub added_keys: u64,
    pub probes: u64,
    pub rejected: u64,
    pub empty_join_skips: u64,
    pub per_rule: Vec<(u64, u64)>,
}
pub struct Sieve {
    #[cfg(feature = "cell-entry-reverse")]
    pub(crate) reverse_enabled: bool,
    #[cfg(feature = "cell-entry-reverse")]
    reverse: ReverseStats,
    #[cfg(feature = "entry-admission-audit")]
    audit: entry_audit::Audit,
    pub enabled: bool,
    specs: Vec<Spec>,
    states: Vec<Summary>,
    by_table: Vec<Dispatch>,
    parents: Vec<Vec<(usize, usize)>>,
    // Incoming necessary conditions for each (rule, atom).
    rules: Vec<Vec<Vec<Guard>>>,
    active: Vec<bool>,
    collide: bool,
    pub stats: Stats,
}
impl Sieve {
    #[cfg(feature = "family-frontiers")]
    pub(crate) fn survey_guards(&self, rule: usize, pivot: usize) -> Vec<(Vec<usize>, usize)> {
        self.rules[rule][pivot]
            .iter()
            .map(|g| (g.cols.clone(), g.child))
            .collect()
    }

    pub fn new(program: &Program) -> Self {
        let enabled = true;
        let mut s = Self {
            #[cfg(feature = "cell-entry-reverse")]
            reverse_enabled: false,
            #[cfg(feature = "cell-entry-reverse")]
            reverse: Default::default(),
            #[cfg(feature = "entry-admission-audit")]
            audit: Default::default(),
            enabled,
            specs: vec![],
            states: vec![],
            by_table: vec![Dispatch::default(); program.tables.len()],
            parents: vec![],
            rules: vec![],
            active: vec![],
            collide: std::env::var("CELL_CPU_SIEVE_COLLISIONS").as_deref() == Ok("1"),
            stats: Stats {
                per_rule: vec![(0, 0); program.rules.len()],
                ..Stats::default()
            },
        };
        let mut intern = HashMap::default();
        for (rid, rule) in program.rules.iter().enumerate() {
            let q = &rule.query;
            let links = &program.cell_links[rid];
            let mut targets = vec![vec![]; q.len()];
            if enabled {
                // One deterministic spanning forest; never enumerate paths or
                // combinations. O(atoms^2) planning, <=2*(atoms-1) messages.
                let mut edges = vec![];
                for a in 0..q.len() {
                    for link in links.from(a).iter().filter(|link| link.atom > a) {
                        edges.push((std::cmp::Reverse(link.distinct().count()), a, link.atom));
                    }
                }
                edges.sort();
                let mut groups = (0..q.len()).collect::<Vec<_>>();
                let mut tree = vec![vec![]; q.len()];
                for (_, a, b) in edges {
                    if groups[a] != groups[b] {
                        let (old, new) = (groups[b], groups[a]);
                        for g in &mut groups {
                            if *g == old {
                                *g = new
                            }
                        }
                        tree[a].push(b);
                        tree[b].push(a);
                    }
                }
                fn message(
                    s: &mut Sieve,
                    intern: &mut HashMap<Spec, usize>,
                    q: &[crate::program::Atom],
                    links: &crate::cell::QueryLinks,
                    tree: &[Vec<usize>],
                    from: usize,
                    to: usize,
                    memo: &mut HashMap<(usize, usize), (usize, Vec<usize>)>,
                ) -> (usize, Vec<usize>) {
                    if let Some(v) = memo.get(&(from, to)) {
                        return v.clone();
                    }
                    // Order by sender columns, independent of slot numbering.
                    let mut shared = links.between(from, to).expect("connected Cell atoms").distinct()
                        .map(|(to, from)| (from, to)).collect::<Vec<_>>();
                    shared.sort();
                    let cols = shared.iter().map(|(c, _)| *c).collect();
                    let receiver = shared.iter().map(|(_, d)| *d).collect::<Vec<_>>();
                    let mut guards = tree[from]
                        .iter()
                        .filter(|n| **n != to)
                        .map(|n| {
                            let (child, cols) = message(s, intern, q, links, tree, *n, from, memo);
                            Guard { cols, child }
                        })
                        .collect::<Vec<_>>();
                    guards.sort();
                    guards.dedup();
                    let Call::Table(table) = q[from].call else {
                        unreachable!()
                    };
                    let spec = Spec::new(table, cols, guards);
                    let id = if let Some(id) = intern.get(&spec) {
                        *id
                    } else {
                        let id = s.specs.len();
                        intern.insert(spec.clone(), id);
                        s.specs.push(spec);
                        s.states.push(Summary::default());
                        s.parents.push(vec![]);
                        id
                    };
                    memo.insert((from, to), (id, receiver.clone()));
                    (id, receiver)
                }
                let mut memo = HashMap::default();
                for to in 0..q.len() {
                    for from in &tree[to] {
                        let (child, cols) =
                            message(&mut s, &mut intern, q, links, &tree, *from, to, &mut memo);
                        // A bare table membership is ordinary index filtering, not
                        // new fragment reuse. Only install genuinely joined summaries.
                        if !s.specs[child].guards.is_empty() {
                            targets[to].push(Guard { cols, child })
                        }
                    }
                }
            }
            s.rules.push(targets);
        }
        s.compile_influence();
        for (p, spec) in s.specs.iter().enumerate() {
            for (g, guard) in spec.guards.iter().enumerate() {
                s.parents[guard.child].push((p, g));
            }
        }
        s.active = vec![false; s.rules.len()];
        #[cfg(feature = "entry-admission-audit")]
        { s.audit = entry_audit::Audit::new(program, &s.rules); }
        s
    }
    fn compile_influence(&mut self) {
        let mut tables = vec![Vec::<(u64,Vec<usize>)>::new(); self.by_table.len()];
        for (id, spec) in self.specs.iter().enumerate() {
            let groups = &mut tables[spec.table];
            if let Some((_,members)) = groups.iter_mut().find(|(columns,_)| *columns == spec.read_columns) {
                members.push(id);
            } else {
                groups.push((spec.read_columns,vec![id]));
            }
        }
        for (dispatch,groups) in self.by_table.iter_mut().zip(tables) {
            dispatch.members.clear(); dispatch.groups.clear();
            dispatch.built = 0;
            for (columns,members) in groups {
                let start = dispatch.members.len();
                let built = members.iter().filter(|&&id|self.states[id].built).count();
                dispatch.built += built;
                dispatch.members.extend(members);
                dispatch.groups.push(Influence { columns, members:start..dispatch.members.len(), built });
            }
        }
    }
    #[cfg(feature = "entry-admission-audit")]
    pub(crate) fn begin_entry_audit(&mut self, epoch: u64, rid: usize, atom: usize,
        node: usize, watermark: u64) -> entry_audit::Probe {
        self.audit.begin(epoch, rid, atom, node, watermark, &self.stats)
    }
    #[cfg(feature = "entry-admission-audit")]
    pub(crate) fn finish_entry_audit(&mut self, probe: entry_audit::Probe, visits: u64, full_delta: bool) {
        self.audit.finish(probe, visits, full_delta, &self.stats)
    }
    fn admit(&mut self, id: usize, keys: &[u64]) -> Option<Projection> {
        self.admit_into::<false>(id, keys)
    }
    fn admit_into<const COLD: bool>(&mut self, id: usize, keys: &[u64]) -> Option<Projection> {
        let spec = &self.specs[id];
        for g in &spec.guards {
            if !self.states[g.child].allows(keys, &g.cols)
            {
                return None;
            }
        }
        let k: Projection = spec.cols.iter().map(|c| keys[*c]).collect();
        let state = &mut self.states[id];
        // Must track keys, NOT whether OR changed any Bloom bit. A new key can
        // collide with old bits and STILL needs upstream propagation.
        #[cfg(feature = "sparse-cells")]
        let fresh = state.keys.insert(&k);
        #[cfg(not(feature = "sparse-cells"))]
        let fresh = state.keys.insert(k.clone());
        if !fresh {
            return None;
        }
        if !COLD && spec.needs_bloom() {
            state.bloom.grow(&state.keys, self.collide);
            state.bloom.insert(&k);
        }
        self.stats.added_keys += 1;
        Some(k)
    }
    fn ensure(&mut self, id: usize, g: &Graph, index: &mut QueryIndexes) -> Result<()> {
        if self.states[id].built {
            self.stats.reused_summaries += 1;
            return Ok(());
        }
        // Cell-derived wiring is immutable during preparation. Copy just the
        // next child address across recursion, not the spec and its vectors.
        for position in 0..self.specs[id].guards.len() {
            let child = self.specs[id].guards[position].child;
            self.ensure(child, g, index)?
        }
        let table = self.specs[id].table;
        index.ensure(g, table)?;
        // Child summaries are already complete. Building a support union
        // depends only on the set of row projections, not on witness order.
        for hashes in index.fingerprints(table) {
            self.stats.build_rows += 1;
            self.admit_into::<true>(id, hashes);
        }
        // No parent consumes this summary until its complete initial support
        // is installed. Size and populate its Bloom filter just once.
        let state = &mut self.states[id];
        if self.specs[id].needs_bloom() && !state.keys.is_empty() {
            state.bloom.grow(&state.keys, self.collide);
        }
        state.built = true;
        self.by_table[table].built += 1;
        self.by_table[table].groups.iter_mut().find(|group| group.columns == self.specs[id].read_columns)
            .expect("compiled summary influence").built += 1;
        self.stats.builds += 1;
        Ok(())
    }
    pub fn prepare(&mut self, rid: usize, g: &Graph, index: &mut QueryIndexes) -> Result<()> {
        if !self.enabled {
            return Ok(());
        }
        self.stats.rule_uses += 1;
        if self.active[rid] {
            self.stats.reused_summaries += 1;
            return Ok(());
        }
        for atom in 0..self.rules[rid].len() {
            for position in 0..self.rules[rid][atom].len() {
                let child = self.rules[rid][atom][position].child;
                self.ensure(child, g, index)?
            }
        }
        // A receiver may not otherwise be indexed (e.g. delta root). Ensure it
        // has canonical column hashes before using its filters.
        for (atom, guards) in self.rules[rid].iter().enumerate() {
            if !guards.is_empty() {
                if let Call::Table(t) = g.program.rules[rid].query[atom].call {
                    index.ensure(g, t)?
                }
            }
        }
        self.active[rid] = true;
        Ok(())
    }
    /// Each incoming guard is necessary for the whole conjunctive query.
    /// An empty, built summary refutes every pivot in this snapshot. The next
    /// scheduled Run checks again after publication has propagated new keys.
    pub(crate) fn empty_join(&mut self, rid: usize) -> bool {
        let empty = self.rules[rid].iter().flatten().any(|guard| {
            let summary = &self.states[guard.child];
            summary.built && summary.keys.is_empty()
        });
        self.stats.empty_join_skips += u64::from(empty);
        empty
    }
    pub fn allow(
        &mut self,
        rid: usize,
        atom: usize,
        table: usize,
        w: Dependency,
        index: &QueryIndexes,
    ) -> bool {
        self.allow_inner::<false>(rid, atom, table, w, index, 0)
    }
    #[cfg(feature = "cell-entry-reverse")]
    pub(crate) fn allow_selected(&mut self, rid: usize, atom: usize, table: usize,
        w: Dependency, index: &QueryIndexes, proven: usize) -> bool {
        self.allow_inner::<true>(rid, atom, table, w, index, proven)
    }
    fn allow_inner<const SELECTED: bool>(&mut self, rid: usize, atom: usize, table: usize,
        w: Dependency, index: &QueryIndexes, _proven: usize) -> bool {
        if !self.enabled {
            return true;
        }
        let guards = &self.rules[rid][atom];
        if guards.is_empty() {
            return true;
        }
        let Some(keys) = index.hashes(table, w) else {
            return true;
        }; // exact matcher handles hidden/stale rows
        for (_position, guard) in guards.iter().enumerate() {
            #[cfg(feature = "cell-entry-reverse")]
            if SELECTED && _position == _proven {
                self.reverse.probes_omitted += 1;
                continue;
            }
            self.stats.probes += 1;
            self.stats.per_rule[rid].0 += 1;
            if !self.states[guard.child].allows(keys, &guard.cols)
            {
                self.stats.rejected += 1;
                self.stats.per_rule[rid].1 += 1;
                return false;
            }
        }
        true
    }
    fn publish_member(&mut self, id: usize, keys: &[u64], queue: &mut VecDeque<(usize,Projection)>) {
        if self.states[id].built {
            self.stats.update_rows += 1;
            if let Some(k) = self.admit(id, keys) { queue.push_back((id,k)); }
        }
    }
    pub fn publish(&mut self, index: &mut QueryIndexes) {
        let mut changes = std::mem::take(&mut index.changes);
        changes.sort_unstable();
        if !self.enabled {
            changes.clear();
            index.changes = changes;
            return;
        }
        let mut queue = VecDeque::new();
        for &(w, table, fields) in &changes {
            self.stats.publication_dispatches += 1;
            if self.by_table[table].built == 0 {
                // No built consumer can use this notification. A later ensure
                // still constructs its full support from the ordinary index.
                self.stats.inactive_publications += 1;
                continue;
            }
            if let Some(keys) = index.hashes(table, w) {
                if fields == u64::MAX {
                    // Initial membership must visit every built summary; its
                    // complete flat route needs no group or field tests.
                    for i in 0..self.by_table[table].members.len() {
                        let id = self.by_table[table].members[i];
                        self.publish_member(id,keys,&mut queue);
                    }
                    continue;
                }
                for i in 0..self.by_table[table].groups.len() {
                    let group = &self.by_table[table].groups[i];
                    if group.built == 0 { continue; }
                    // One test skips every built member without visiting its state.
                    // Changed child support still enters through static parent wiring.
                    self.stats.column_checks += 1;
                    if fields & group.columns == 0 {
                        self.stats.unchanged_column_rows += group.built as u64;
                        continue;
                    }
                    for j in group.members.clone() {
                        let id = self.by_table[table].members[j];
                        self.publish_member(id,keys,&mut queue);
                    }
                }
            }
        }
        while let Some((child, keys)) = queue.pop_front() {
            for i in 0..self.parents[child].len() {
                let (parent, gid) = self.parents[child][i];
                if self.states[parent].built {
                    let spec = &self.specs[parent];
                    let table = spec.table;
                    let rows = index.hash_candidates(table, &spec.guards[gid].cols, &keys);
                    for w in rows {
                        self.stats.dependency_rows += 1;
                        if let Some(k) = self.admit(parent, index.hashes(table, w).unwrap()) {
                            queue.push_back((parent, k))
                        }
                    }
                }
            }
        }
        // This is the index's original publication buffer, not retained facts.
        // Empty it at the boundary and return its allocation to its owner.
        changes.clear();
        index.changes = changes;
    }
    pub fn invalidate(&mut self) {
        for state in &mut self.states {
            *state = Summary::default()
        }
        self.active.fill(false);
        for dispatch in &mut self.by_table {
            dispatch.built = 0;
            for group in &mut dispatch.groups { group.built = 0; }
        }
    }
    pub fn report(&self) -> serde_json::Value {
        #[allow(unused_mut)]
        let mut report = serde_json::json!({"enabled":self.enabled,"specifications":self.specs.len(),"active_summaries":self.states.iter().filter(|s|s.built).count(),"stored_keys":self.states.iter().map(|s|s.keys.len()).sum::<usize>(),"bloom_bytes":self.states.iter().map(|s|s.bloom.words.len()*8).sum::<usize>(),"key_payload_bytes":self.states.iter().flat_map(|s|s.keys.iter()).map(|k|k.len()*8).sum::<usize>(),"stats":self.stats,"scope":"complete visible-table semijoin summaries; not Cell-only proof credit"});
        report["column_influence"] = "cell-fields/v2".into();
        report["influence_groups"] = self.by_table.iter().map(|d|d.groups.len()).sum::<usize>().into();
        report["influence_payload_bytes"] = (self.specs.len()*8
            + self.by_table.len()*(std::mem::size_of::<Dispatch>()-std::mem::size_of::<Vec<usize>>())
            + self.by_table.iter().map(|d| d.groups.len()*std::mem::size_of::<Influence>()).sum::<usize>()).into();
        #[cfg(feature = "entry-admission-audit")]
        {
            report["entry_admission_audit"] = self.audit.report();
            report["entry_admission_audit"]["specs"] = self.specs.iter().map(|s|
                serde_json::json!({"table":s.table,"cols":s.cols,
                    "guards":s.guards.iter().map(|g| (&g.child,&g.cols)).collect::<Vec<_>>()})
            ).collect::<Vec<_>>().into();
        }
        #[cfg(feature = "cell-entry-reverse")]
        { report["reverse"] = serde_json::json!({"enabled":self.reverse_enabled,"stats":self.reverse}); }
        report
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn projection_and_guard_columns_both_contribute_to_influence() {
        let spec = Spec::new(0, vec![0, 70], vec![Guard { cols:vec![2, 65], child:0 }]);
        assert_eq!(spec.read_columns, 1 | 4 | (1 << 63));
        assert_eq!(spec.read_columns & crate::query::column_bit(1), 0);
        assert_ne!(spec.read_columns & crate::query::column_bit(130), 0,
            "wide-column collisions conservatively retain maintenance");
    }
    #[cfg(feature = "sparse-cells")]
    #[test]
    fn field_updates_match_full_publication_and_late_children_still_propagate() {
        use crate::value::Value;
        fn fixture(g: &Graph, index: &mut QueryIndexes) -> Sieve {
            let mut s = Sieve::new(&g.program);
            s.specs = vec![
                Spec::new(1, vec![0], vec![]),
                Spec::new(0, vec![0], vec![Guard { cols:vec![1], child:0 }]),
                Spec::new(0, vec![2], vec![]),
                Spec::new(0, vec![], vec![]),
                Spec::new(1, vec![], vec![]),
            ];
            s.states = (0..5).map(|_| Summary::default()).collect();
            s.compile_influence();
            s.parents = vec![vec![(1,0)],vec![],vec![],vec![],vec![]];
            for id in 0..5 { s.ensure(id,g,index).unwrap(); }
            s
        }
        let mut graph = crate::query::test_projection_graph();
        let mut index = crate::query::test_projection_indexes(64);
        index.track_changes = true;
        let mut selected = fixture(&graph,&mut index);
        let mut full = fixture(&graph,&mut index);
        for (stage,(table,a,b,value)) in [(0,5,10,7),(0,5,10,9),(1,10,0,100),
            (0,6,20,8),(0,5,10,11),(1,20,0,100)].into_iter().enumerate() {
            graph.set_function(table,vec![Value::Int(a),Value::Int(b)],Value::Int(value)).unwrap();
            index.update(&mut graph).unwrap();
            if stage == 1 || stage == 4 {
                assert!(index.changes.iter().all(|(_,_,fields)| *fields == crate::query::column_bit(2)));
            } else {
                assert!(index.changes.iter().all(|(_,_,fields)| *fields == u64::MAX));
            }
            let changes = index.changes.clone();
            let column_checks = selected.stats.column_checks;
            selected.publish(&mut index);
            if stage != 1 && stage != 4 {
                assert_eq!(selected.stats.column_checks,column_checks,"full publication does not inspect field groups");
            }
            index.changes = changes.into_iter().map(|(w,t,_)| (w,t,u64::MAX)).collect();
            full.publish(&mut index);
            for (a,b) in selected.states.iter().zip(&full.states) {
                let keys = |s:&Summary| { let mut keys=s.keys.iter().map(<[u64]>::to_vec).collect::<Vec<_>>(); keys.sort(); keys };
                assert_eq!(keys(a),keys(b),"stage {stage}");
            }
            assert_eq!(selected.stats.added_keys,full.stats.added_keys);
            assert_eq!(selected.stats.dependency_rows,full.stats.dependency_rows);
            for dispatch in &selected.by_table {
                assert_eq!(dispatch.built,dispatch.groups.iter().map(|g|g.built).sum::<usize>());
                for group in &dispatch.groups {
                    assert_eq!(group.built,dispatch.members[group.members.clone()].iter().filter(|&&id|selected.states[id].built).count());
                }
            }
            if stage == 1 { assert!(selected.states[1].keys.is_empty()); }
            if stage == 2 { assert!(!selected.states[1].keys.is_empty(),"late child wakes unchanged parent rows"); }
            graph.changes.clear();
        }
        assert!(selected.stats.unchanged_column_rows > 0);
        assert_eq!(full.stats.column_checks,0);
        assert_eq!(selected.stats.publication_dispatches,full.stats.publication_dispatches);
        assert_eq!(selected.stats.update_rows + selected.stats.unchanged_column_rows,full.stats.update_rows);
        assert_eq!(selected.states[1].keys.len(),2);
        assert_eq!(selected.states[4].keys.len(),1,"new rows establish empty projections");
        selected.invalidate();
        assert!(selected.by_table.iter().all(|d|d.built==0));
        assert!(selected.by_table.iter().flat_map(|d| &d.groups).all(|group|group.built==0));
        graph.set_function(0,vec![Value::Int(7),Value::Int(30)],Value::Int(12)).unwrap();
        index.update(&mut graph).unwrap();
        selected.publish(&mut index);
        assert!(selected.stats.inactive_publications>0);
        for id in 0..5 { selected.ensure(id,&graph,&mut index).unwrap(); }
        assert!(selected.by_table.iter().flat_map(|d| &d.groups).all(|group|group.built==group.members.len()));
        assert!(selected.states[2].allows(&[0,0,index.fingerprint(&Value::Int(12))],&[2]),
            "a later prepare sees rows published while all summaries were inactive");
    }
    #[test]
    fn bloom_growth_never_loses_insertions() {
        let mut bloom = Bloom::default();
        let mut keys = Support::default();
        for i in 0..200 {
            let k = vec![i, i * 17];
            #[cfg(feature = "sparse-cells")]
            keys.insert(&k);
            #[cfg(not(feature = "sparse-cells"))]
            keys.insert(k.clone());
            bloom.grow(&keys, false);
            bloom.insert(&k);
            for old in &keys {
                assert!(bloom.contains(old));
                assert!(bloom.contains_projection(&[999, old[1], old[0]], &[2, 1]));
            }
        }
    }
    #[test]
    fn new_key_propagates_even_if_or_did_not_change_bits() {
        let mut s = Sieve {
            #[cfg(feature = "cell-entry-reverse")]
            reverse_enabled: false,
            #[cfg(feature = "cell-entry-reverse")]
            reverse: Default::default(),
            #[cfg(feature = "entry-admission-audit")]
            audit: Default::default(),
            enabled: true,
            specs: vec![Spec::new(0, vec![0, 1, 2], vec![])],
            states: vec![Summary::default()],
            by_table: vec![Dispatch { members:vec![0], groups:vec![Influence { columns:7, members:0..1, built:0 }], built:0 }],
            parents: vec![vec![]],
            rules: vec![],
            active: vec![],
            collide: true,
            stats: Stats::default(),
        };
        assert_eq!(s.admit(0, &[7, 70, 700]).as_deref(), Some(&[7, 70, 700][..]));
        let bits = s.states[0].bloom.words.clone();
        assert!(!bits.is_empty(), "wide projection still exercises Bloom collisions");
        assert_eq!(s.admit(0, &[8, 80, 800]).as_deref(), Some(&[8, 80, 800][..]));
        assert_eq!(bits, s.states[0].bloom.words);
        assert_eq!(s.admit(0, &[8, 80, 800]), None);
        #[cfg(feature = "sparse-cells")]
        for width in 0..=2 {
            s.specs[0].cols = (0..width).collect();
            s.invalidate();
            let first = [7,70];
            assert!(s.admit(0, &first).is_some());
            assert!(s.states[0].bloom.words.is_empty(), "exact support has no Bloom to maintain");
            assert!(s.states[0].allows(&first, &s.specs[0].cols));
            if width != 0 {
                let next = [8,80];
                assert!(!s.states[0].allows(&next, &s.specs[0].cols));
                assert!(s.admit(0, &next).is_some(), "new narrow support still propagates");
                assert!(s.states[0].allows(&next, &s.specs[0].cols));
            }
            assert!(s.states[0].bloom.words.is_empty());
        }
    }
}
