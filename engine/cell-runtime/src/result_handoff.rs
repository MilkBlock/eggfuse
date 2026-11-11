//! Symbolic SSA keys on one finite, witnessed block path. Constructor receipts
//! can also prove result equality. Mutable receipts prove only a row location;
//! a query must read its current result and check visibility and the full key.
use crate::{
    graph::{Dependency, FactRef},
    iterative::Entry,
    cell::{Capture, Definition, ResultFrame, ResultPort, Results, ResultView, Site, SlotLayout},
    program::*,
};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    rc::Rc,
    num::NonZeroUsize,
};

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub(crate) struct Reuse {
    pub equal_output: bool,
    pub op: usize,
    pub back: usize,
    pub rule: usize,
    pub donor: Site,
    #[serde(skip)]
    pub port: Option<ResultPort>,
}
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
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
    pub from_history: bool,
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
    lazy_unions: bool,
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
            let mut actual_result=value;
            if let Some(i) = index.find(&mut symbols, &facts, table, &key) {
                let f = &facts[i];
                let inherited = (lazy_unions && f.stage==stage).then(|| match f.source {
                    Site::Effect(op) => program.iter().find(|r: &&Reuse|r.op==op).cloned(),
                    _ => None,
                }).flatten();
                if (f.stage != stage || inherited.is_some())
                    && stage + 1 == path.len()
                    && !p.known_results.static_skip.get(rid).is_some_and(|s| s[op])
                {
                    let (back,rule,donor) = inherited.map_or((stage-f.stage,f.rule,f.source),
                        |r|(r.back,r.rule,r.donor));
                    program.push(Reuse {
                        equal_output: matches!(ins, Op::Set(..))
                            && symbols.root(value) == symbols.root(f.result),
                        op,
                        back, rule, donor,
                        port: None,
                    });
                }
                if matches!(ins, Op::Set(..)) {
                    unions.push((value, f.result));
                    // A Set on an existing constructor queues equality. Its
                    // current result does not become the requested value until
                    // the Run boundary; later RHS keys must retain that fact.
                    if lazy_unions {actual_result=f.result;}
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
                result: actual_result,
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
pub(crate) enum Trail {
    One(Results),
    // Each entry is empty or One. Reuse an existing One when a later Cell
    // needs a deeper history; do not copy its results into another owner.
    Many(Vec<Option<ResultFrame>>),
}
/// Reporting-only census of result storage reachable from published Entries.
/// Shared owners (including inherited leaves) and layouts are counted once.
/// Bytes include backing capacities and an explicit two-word Rc header estimate,
/// but exclude allocator rounding, cursors, pending work and unrelated graph data.
#[derive(Default, Serialize)]
pub(crate) struct HistoryStorage {
    owners: usize,
    owner_payload_bytes: usize,
    result_array_bytes: usize,
    history_array_bytes: usize,
    layouts: usize,
    layout_bytes: usize,
    rc_header_bytes: usize,
    #[serde(skip)]
    seen: BTreeSet<usize>,
    #[serde(skip)]
    seen_layouts: BTreeSet<usize>,
}
impl HistoryStorage {
    fn layout(&mut self, layout: &Rc<SlotLayout>) {
        if self.seen_layouts.insert(Rc::as_ptr(layout) as usize) {
            self.layouts += 1;
            self.layout_bytes += layout.storage_bytes();
            self.rc_header_bytes += 2 * std::mem::size_of::<usize>();
        }
    }
    fn frame(&mut self, frame: &ResultFrame) {
        if let Some(layout) = &frame.projection { self.layout(layout); }
        self.visit(&frame.owner);
    }
    fn visit(&mut self, owner: &Rc<Trail>) {
        if !self.seen.insert(Rc::as_ptr(owner) as usize) { return; }
        self.owners += 1;
        self.owner_payload_bytes += std::mem::size_of::<Trail>();
        self.rc_header_bytes += 2 * std::mem::size_of::<usize>();
        match owner.as_ref() {
            Trail::One(results) => {
                let (bytes, parent, layout) = results.storage_parts();
                self.result_array_bytes += bytes;
                if let Some(parent) = parent { self.visit(parent); }
                if let Some(layout) = layout { self.layout(layout); }
            }
            Trail::Many(frames) => {
                self.history_array_bytes += frames.capacity() * std::mem::size_of::<Option<ResultFrame>>();
                for frame in frames.iter().flatten() { self.frame(frame); }
            }
        }
    }
}
#[derive(Clone, Debug, Default)]
pub(crate) struct History {
    frames: Option<ResultFrame>,
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
    pub inherited: usize,
    pub heap_frames: usize,
    pub shared_slots: usize,
}
impl History {
    pub(crate) fn count_storage(&self, census: &mut HistoryStorage) {
        if let Some(frame) = &self.frames { census.frame(frame); }
    }
    /// Advance across a Cell with no actual exported results. The existing
    /// immutable frames stay shared; trim only when the compiled lifetime ends.
    fn carry(&mut self, limit: usize, work: &mut CaptureWork) {
        if self.frames.is_none() { return; }
        self.empty += 1;
        let keep = limit.saturating_sub(self.empty);
        if keep == 0 { *self = Self::default(); return; }
        if let Some(Trail::Many(frames)) = self.frames.as_ref().map(|f| f.owner.as_ref()) {
            if frames.len() > keep {
                if keep == 1 {
                    // A nonempty history always ends with its last real frame.
                    self.frames = frames.last().unwrap().clone();
                } else {
                    let retained = frames[frames.len() - keep..].to_vec();
                    work.slots += retained.len();
                    work.allocations += 2;
                    self.frames = Some(ResultFrame { owner: Rc::new(Trail::Many(retained)), projection: None });
                }
            }
        }
        work.carried = true;
    }
    /// One existing frame, excluding empty-stage bookkeeping. Many never
    /// embeds another Many, so retaining a result cannot retain expired history.
    fn snapshot(&self, back: usize) -> Option<ResultFrame> {
        let back = back.checked_sub(self.empty).filter(|&b| b > 0)?;
        match self.frames.as_ref().map(|f| f.owner.as_ref()) {
            Some(Trail::One(_)) if back == 1 => self.frames.clone(),
            Some(Trail::Many(v)) => v.len().checked_sub(back).and_then(|i| v[i].clone()),
            _ => None,
        }
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn is_empty(&self) -> bool { self.frames.is_none() }
    pub(crate) fn current(&self) -> Option<ResultView<'_>> { self.frame(1) }
    /// A newly completed Cell has not published its current frame yet. Repair
    /// may already have coalesced its receipts; update the unique local storage
    /// before Entry/Cursor sharing outlives this Run's forwarding map. Previously
    /// shared owners are deliberately left untouched and never copied or scanned.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn seal_current(&mut self, forward: impl FnMut(Dependency) -> Dependency) -> Option<(usize, usize)> {
        if self.empty != 0 { return Some((0, 0)); }
        let Some(frame) = self.frames.as_mut() else { return Some((0, 0)); };
        if frame.projection.is_some() { return None; }
        let results = match Rc::get_mut(&mut frame.owner)? {
            Trail::One(results) => results,
            Trail::Many(frames) => {
                let Some(frame) = frames.last_mut().and_then(Option::as_mut) else { return Some((0, 0)); };
                if frame.projection.is_some() { return None; }
                let Trail::One(results) = Rc::get_mut(&mut frame.owner)? else { unreachable!("flat Cell history"); };
                results
            },
        };
        Some(results.seal_local(forward))
    }
    pub(crate) fn project_complete(&self,plan:&crate::cell::CompletedPlan,probes:&mut u64) -> Option<Results> {
        Results::project_complete(plan,self.snapshot(plan.back)?,probes)
    }
    pub(crate) fn capture(
        &mut self,
        limit: usize,
        rid: usize,
        wanted: &[Capture],
        read: impl Fn(usize) -> Option<Dependency>,
        effect: impl Fn(usize) -> Option<Dependency>,
    ) -> CaptureWork {
        self.capture_selected(limit, rid, wanted, true, read, effect)
    }
    pub(crate) fn capture_selected(
        &mut self, limit: usize, rid: usize, wanted: &[Capture], inherit: bool,
        read: impl Fn(usize) -> Option<Dependency>, effect: impl Fn(usize) -> Option<Dependency>,
    ) -> CaptureWork {
        self.capture_layout(limit, rid, wanted, inherit, None, 0, read, effect)
    }
    pub(crate) fn capture_layout(&mut self, limit: usize, rid: usize, wanted: &[Capture], inherit: bool,
        layout: Option<&Rc<SlotLayout>>, forwarded: u64,
        read: impl Fn(usize)->Option<Dependency>, effect: impl Fn(usize)->Option<Dependency>) -> CaptureWork {
        if !inherit && limit > 1 && wanted.is_empty() && self.frames.is_some() {
            let stored = match self.frames.as_ref().unwrap().owner.as_ref() { Trail::One(_) => 1, Trail::Many(v) => v.len() };
            let count = (stored + self.empty).min(limit - 1);
            let mut frames = Vec::with_capacity(count + 1);
            frames.extend((1..=count).rev().map(|back| self.snapshot(back)));
            frames.push(None);
            *self = Self { frames:Some(ResultFrame { owner: Rc::new(Trail::Many(frames)), projection: None }), empty:0 };
            return CaptureWork { slots:count+1, allocations:2, ..Default::default() };
        }
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
        // A one-stage replacement can move its existing owner directly. It
        // needs neither a back-address lookup nor an extra owner handle.
        let owner = if inherit && forwarded != 0 && layout.is_some() && limit == 1 && self.empty == 0 {
            self.frames.take()
        } else { None };
        if let Some(owner)=owner { results.prepare(layout.unwrap(),owner,forwarded); }
        let local_width = wanted.last().map_or(0, |c| c.port.slot() + 1) - results.inherited_count();
        let mut empty_slots = 0;
        for capture in wanted {
            if results.inherits(capture.port) { continue; }
            let w = match capture.site {
                Site::Query(i) => read(i),
                Site::Effect(i) => effect(i),
            };
            if let Some(w) = w {
                if results.stored_len() == 0 { results.reserve_local(local_width); }
                empty_slots += results.insert(capture.port, w);
            }
        }
        let work = CaptureWork { reads: wanted.len() - results.inherited_count(), slots: results.stored_len(),
            empty_slots, allocations: 0, carried: false, inherited:results.inherited_count(), heap_frames:usize::from(results.spilled()), shared_slots:0 };
        self.retain_results(limit, results, work)
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn capture_outputs(&mut self, limit: usize, results: Results) -> CaptureWork {
        assert!(limit > 0);
        let shared_slots = results.len();
        self.retain_results(limit, results, CaptureWork { shared_slots, ..Default::default() })
    }
    fn retain_results(&mut self, limit: usize, results: Results, mut work: CaptureWork) -> CaptureWork {
        if results.len() == 0 {
            self.carry(limit, &mut work);
            return work;
        }
        let (frame, allocations) = ResultFrame::retain(results);
        if limit == 1 || self.frames.is_none() || self.empty >= limit - 1 {
            work.allocations = allocations;
            *self = Self { frames: Some(frame), empty: 0 };
            return work;
        }
        let stored = match self.frames.as_ref().map(|f| f.owner.as_ref()) {
            Some(Trail::Many(v)) => v.len(),
            Some(Trail::One(_)) => 1,
            _ => 0,
        };
        let retained = (stored + self.empty).min(limit - 1);
        work.slots += retained + 1;
        work.allocations = 2 + allocations;
        let mut v = Vec::with_capacity(retained + 1);
        v.extend((1..=retained).rev().map(|back| self.snapshot(back)));
        v.push(Some(frame));
        *self = Self { frames: Some(ResultFrame { owner: Rc::new(Trail::Many(v)), projection: None }), empty: 0 };
        work
    }
    pub(crate) fn get_counted(&self, back: usize, port: ResultPort, extra:&mut u64) -> Option<Dependency> {
        self.frame(back)?.get_counted(port, extra)
    }
    pub(crate) fn get(&self, back: usize, port: ResultPort) -> Option<Dependency> {
        self.frame(back)?.get(port)
    }
    fn frame(&self, back: usize) -> Option<ResultView<'_>> {
        let back = back.checked_sub(self.empty).filter(|&b| b > 0)?;
        let frame = self.frames.as_ref()?;
        match frame.owner.as_ref() {
            Trail::One(_) if back == 1 => frame.view(),
            Trail::Many(v) => v.get(v.len().checked_sub(back)?)?.as_ref()?.view(),
            _ => return None,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
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
    derive_stage(p, path, congruence, query_ports, false)
}

#[derive(Clone, Debug, Default)]
pub(crate) struct Switch {
    reuse_results: bool,
    pub(crate) congruence: bool,
    pub(crate) query_ports: bool,
    nodes: Box<[Node]>,
    by_rule: DispatchRows,
    roots: Box<[Option<NonZeroUsize>]>,
    initial: Vec<usize>,
    exports: Rows<Site>,
    completion: bool,
    lazy_unions: bool,
    direct: Box<[Option<Rc<crate::cell::CompletedPlan>>]>,
    pub depth: usize,
}
type DispatchRows = Rows<Option<NonZeroUsize>>;

/// CSR rows preserve slots and direct rule indexing without one allocation
/// and a fat pointer per rule. Empty adjacent rows share the same offset.
#[derive(Clone, Debug)]
struct Rows<T> {
    offsets: Box<[usize]>,
    slots: Box<[T]>,
}
impl<T> Default for Rows<T> {
    fn default() -> Self { Self { offsets: Box::new([]), slots: Box::new([]) } }
}
impl<T> Rows<T> {
    fn compile(rows: Vec<Vec<T>>) -> Self {
        if rows.is_empty() { return Self::default(); }
        let mut offsets = Vec::with_capacity(rows.len()+1);
        let mut slots = Vec::new();
        offsets.push(0);
        for row in rows {
            slots.extend(row);
            offsets.push(slots.len());
        }
        Self { offsets: offsets.into_boxed_slice(), slots: slots.into_boxed_slice() }
    }
    fn get(&self, rule: usize) -> Option<&[T]> {
        let end = *self.offsets.get(rule.checked_add(1)?)?;
        Some(&self.slots[self.offsets[rule]..end])
    }
    fn len(&self) -> usize { self.offsets.len().saturating_sub(1) }
}
type Transition = ((usize, usize), usize);

#[derive(Clone, Debug, Serialize)]
struct Node<C = Rc<[Capture]>, N = Rc<[Transition]>, P = Rc<Terminal>> {
    unit: usize,
    failure: usize,
    program: P,
    next: N,
    supply: C,
    #[serde(skip)]
    keep_history: usize,
    #[serde(skip)]
    layout: Option<Rc<SlotLayout>>,
}

fn share_program(program: Terminal, pool: &mut BTreeSet<Rc<Terminal>>) -> Rc<Terminal> {
    if let Some(existing) = pool.get(&program) { return existing.clone(); }
    let shared = Rc::new(program);
    pool.insert(shared.clone());
    shared
}

fn share_slice<T: Ord>(values: Vec<T>, pool: &mut BTreeSet<Rc<[T]>>) -> Rc<[T]> {
    if let Some(existing) = pool.get(values.as_slice()) { return existing.clone(); }
    let shared: Rc<[T]> = values.into();
    pool.insert(shared.clone());
    shared
}

/// Liveness after this Cell completes. A successor's direct read needs `back`
/// frames; its future retention needs one fewer before it adds its own frame.
/// Include inherited edges and default restarts, not just trie children.
fn retained_depths(nodes: &[Node<Vec<Capture>, Vec<Transition>, Terminal>], initial: &[usize]) -> Vec<usize> {
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
    pub(crate) fn exports(&self, rule: usize) -> &[Site] {
        self.exports.get(rule).unwrap_or(&[])
    }
    pub(crate) fn completion_storage(&self) -> serde_json::Value {
        let mut seen = BTreeSet::new();
        let mut payload = 0;
        for node in &self.nodes {
            if seen.insert(Rc::as_ptr(&node.program) as usize) {
                payload += node.program.reuse.capacity()*std::mem::size_of::<Reuse>()
                    +node.program.queries.capacity()*std::mem::size_of::<QueryReuse>();
            }
        }
        let mut direct_seen = BTreeSet::new();
        let direct_bytes = self.direct.iter().flatten()
            .filter(|p| direct_seen.insert(Rc::as_ptr(p) as usize))
            .map(|p| std::mem::size_of::<crate::cell::CompletedPlan>()+2*std::mem::size_of::<usize>()
                +p.outputs.capacity()*std::mem::size_of::<(Site,usize,usize)>()
                +p.projections.capacity()*std::mem::size_of::<(Rc<SlotLayout>,Rc<SlotLayout>)>()).sum::<usize>();
        let mut union_seen = BTreeSet::new();
        let union_bytes = self.direct.iter().flatten().filter_map(|p|p.unions.as_ref())
            .filter(|p|union_seen.insert(Rc::as_ptr(p) as *const () as usize))
            .map(|p|std::mem::size_of_val(p.as_ref())+2*std::mem::size_of::<usize>()).sum::<usize>();
        serde_json::json!({
            "states":self.nodes.len(),
            "lowered_reads":self.nodes.iter().map(|n| (
                n.program.reuse.iter().map(|r|r.port.map(|p|(p.rule(),p.slot()))).collect::<Vec<_>>(),
                n.program.queries.iter().map(|r|r.port.map(|p|(p.rule(),p.slot()))).collect::<Vec<_>>()
            )).collect::<Vec<_>>(),
            "node_array_bytes":std::mem::size_of_val(self.nodes.as_ref()),
            "program_owner_bytes":seen.len()*(std::mem::size_of::<Terminal>()+2*std::mem::size_of::<usize>()),
            "direct_states":self.direct.iter().flatten().count(),
            "direct_array_bytes":std::mem::size_of_val(self.direct.as_ref()),
            "direct_programs":direct_seen.len(),
            "direct_program_bytes":direct_bytes,
            "lazy_union_states":self.direct.iter().flatten().filter(|p|p.unions.is_some()).count(),
            "lazy_union_programs":union_seen.len(),
            "lazy_union_program_bytes":union_bytes,
            "read_payload_bytes":payload})
    }
    pub(crate) fn transition_storage(&self) -> serde_json::Value {
        let mut seen = BTreeSet::new();
        let mut payload = 0;
        for node in &self.nodes {
            if seen.insert(Rc::as_ptr(&node.next) as *const Transition as usize) {
                payload += std::mem::size_of_val(node.next.as_ref());
            }
        }
        serde_json::json!({
            "states":self.nodes.len(),
            "node_array_bytes":std::mem::size_of_val(self.nodes.as_ref()),
            "transition_payload_bytes":payload,
            "transition_owner_bytes":seen.len()*2*std::mem::size_of::<usize>()})
    }
    pub(crate) fn capture_storage(&self) -> serde_json::Value {
        let mut seen = BTreeSet::new();
        let mut payload = 0;
        for node in &self.nodes {
            if seen.insert(Rc::as_ptr(&node.supply) as *const Capture as usize) {
                payload += node.supply.len()*std::mem::size_of::<Capture>();
            }
        }
        serde_json::json!({
            "states":self.nodes.len(), "node_capacity":self.nodes.len(),
            "captures":self.nodes.iter().map(|n|n.supply.iter().map(|c|(c.site,c.port.rule(),c.port.slot())).collect::<Vec<_>>()).collect::<Vec<_>>(),
            "node_array_bytes":std::mem::size_of_val(self.nodes.as_ref()),
            "capture_payload_bytes":payload,
            "capture_owner_bytes":seen.len()*2*std::mem::size_of::<usize>()})
    }
    pub(crate) fn export_storage(&self) -> serde_json::Value {
        serde_json::json!({
            "interfaces":(0..self.exports.len()).map(|r|(r,self.exports.get(r).unwrap())).filter(|(_,s)|!s.is_empty()).collect::<Vec<_>>(),
            "directory_bytes":std::mem::size_of_val(self.exports.offsets.as_ref()),
            "slot_bytes":std::mem::size_of_val(self.exports.slots.as_ref())})
    }
    pub(crate) fn dispatch_storage(&self) -> serde_json::Value {
        serde_json::json!({"rule_rows":self.by_rule.len(),
            "rule_slots":self.by_rule.slots.len(),
            "root_slots":self.roots.len(),
            "row_directory_bytes":std::mem::size_of_val(self.by_rule.offsets.as_ref()),
            "rule_slot_bytes":std::mem::size_of_val(self.by_rule.slots.as_ref()),
            "root_slot_bytes":std::mem::size_of_val(self.roots.as_ref()),
            "duplicate_lookup_entry_bytes":0})
    }
    /// Lower the validated portable transfer certificate with the Cell's own
    /// alias proofs. Keep one executable completion flag, without changing the
    /// historical wire certificate or relaxing its exact validation.
    pub(crate) fn complete_cells(&mut self, p: &Program, rule: impl Fn(usize) -> usize) {
        for node in self.nodes.iter_mut().skip(1) {
            let rid = rule(node.unit);
            let complete = !node.program.reuse.is_empty()
                && Definition::new(p, rid).expect("validated Cell")
                    .closes_with(&p.known_results.static_skip[rid], self.congruence,
                        |op| node.program.reuse.iter().any(|r| r.op == op));
            if node.program.complete != complete {
                Rc::make_mut(&mut node.program).complete = complete;
            }
        }
        // Re-intern after the authoritative post-certificate lowering. This
        // must not mutate a program shared with another state or catalog clone.
        let mut programs = BTreeSet::<Rc<Terminal>>::new();
        for node in &mut self.nodes {
            if let Some(existing) = programs.get(node.program.as_ref()) {
                node.program = existing.clone();
            } else {
                programs.insert(node.program.clone());
            }
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
        completion: bool,
        lazy_unions: bool,
    ) -> Self {
        let mut prefixes = BTreeMap::new();
        let mut units = BTreeMap::new();
        for (id, path) in paths.enumerate() {
            units.insert(path.to_vec(), id);
            for i in 1..=path.len() {
                prefixes.entry(path[..i].to_vec()).or_insert_with(|| {
                    if reuse_results {
                        derive_stage(p, &path[..i], congruence, query_ports, lazy_unions)
                    } else {
                        Terminal::default()
                    }
                });
            }
        }
        let mut paths = prefixes.into_iter().collect::<Vec<_>>();
        paths.sort_by_key(|(p, _)| p.len());
        let blank = || Node::<Vec<Capture>, Vec<Transition>, Terminal> {
            unit: 0,
            failure: 0,
            program: Default::default(),
            next: vec![],
            supply: vec![],
            keep_history: 0, layout: None,
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
        // Ripsat completion exports the existing donor slots directly. Extend
        // the one authoritative result layout before any ports are lowered.
        let mut direct_back = vec![None; nodes.len()];
        let mut direct_sources = vec![None;nodes.len()];
        if completion {
            for (path,&id) in &ids {
                if path.len()<2 { continue; }
                let rid=path.last().unwrap().1.0;
                let cell=Definition::new(p,rid).unwrap();
                let program=&nodes[id].program;
                let complete = if lazy_unions {
                    !program.reuse.is_empty() && cell.closes_with(&p.known_results.static_skip[rid],true,
                        |op|program.reuse.iter().any(|r|r.op==op))
                } else { program.complete };
                if !complete {continue;}
                // Prior stages may have ordered unions or other effects.
                // Their completed typed receipts prove this inclusion; only
                // positive paths additionally share a normalized structure.
                if cell.template.ops.iter().any(|i|!matches!(i,Op::Copy(..)|Op::Let(_,Call::Table(_),_)|Op::Set(..))
                    && !(lazy_unions && matches!(i,Op::Union(..)))) {continue;}
                let ops=cell.template.ops.iter().enumerate().filter_map(|(op,i)|
                    (matches!(i,Op::Let(..)|Op::Set(..))
                        && (!lazy_unions || !p.known_results.static_skip[rid][op])).then_some(op)).collect::<Vec<_>>();
                if ops.is_empty() || ops.len()>32 { continue; }
                let reads=ops.iter().filter(|&&op|!lazy_unions || !p.known_results.static_skip[rid][op])
                    .map(|op|nodes[id].program.reuse.iter().find(|r|r.op==*op)).collect::<Option<Vec<_>>>();
                let Some(reads)=reads else { continue; };
                if reads.is_empty() {continue;}
                if !lazy_unions && reads.iter().any(|r|matches!(cell.template.ops[r.op],Op::Set(..)) && !r.equal_output) {continue;}
                let first=reads[0];
                if reads.iter().any(|r|(r.back,r.rule)!=(first.back,first.rule)) { continue; }
                let (back,donor_rule)=(first.back,first.rule);
                let wanted=exports[rid].iter().copied().chain(ops.iter().map(|&op|Site::Effect(op))).collect::<BTreeSet<_>>();
                let sources=wanted.iter().map(|&site| {
                    let actual = if lazy_unions { match site {
                        Site::Effect(op) => p.known_results.static_sources[rid][op].unwrap_or(site),
                        Site::Query(_) => site,
                    }} else {site};
                    let source=match actual {
                        Site::Effect(op)=>nodes[id].program.reuse.iter().find(|r|r.op==op).map(|r|(r.back,r.rule,r.donor)),
                        Site::Query(atom) if path.last().unwrap().1.1==Some(atom) && back==1 => {
                            let previous=path[path.len()-2].1.0;
                            let op=path.last().unwrap().0?;
                            let source=p.known_results.static_sources.get(previous).and_then(|s|s[op]).unwrap_or(Site::Effect(op));
                            Some((1,previous,source))
                        },
                        Site::Query(atom)=>nodes[id].program.queries.iter().find(|r|r.atom==atom).map(|r|(r.back,r.rule,r.donor)),
                    }?;
                    ((source.0,source.1)==(back,donor_rule)).then_some((site,source.2))
                }).collect::<Option<BTreeMap<_,_>>>();
                let Some(sources)=sources else{continue};
                // Deletion is a boundary operation. Decline whole-table
                // visibility changes, even when they occur outside this path.
                if wanted.iter().any(|&site| {
                    let table=cell.relation(site).unwrap().table;
                    !p.tables[table].constructor || !p.tables[table].virtual_fact ||
                        p.templates.iter().any(|t|t.ops.iter().any(|i|matches!(i,Op::Hide(t,..) if *t==table)))
                }) { continue; }
                direct_back[id]=Some(back);
                direct_sources[id]=Some((donor_rule,sources.clone()));
                let donor=ids[&path[..path.len()-back]];
                for (&site,&source) in &sources {
                    exports[rid].push(site);
                    nodes[id].supply.push(Capture {site,port:ResultPort::new(rid,0)});
                    exports[donor_rule].push(source);
                    nodes[donor].supply.push(Capture{site:source,port:ResultPort::new(donor_rule,0)});
                }
            }
            for exports in &mut exports {exports.sort_unstable();exports.dedup();}
            for id in 1..nodes.len() {
                let (before,after)=nodes.split_at_mut(id);
                let node=&mut after[0];
                node.supply.extend_from_slice(&before[node.failure].supply);
                node.supply.sort_unstable();node.supply.dedup();
            }
        }
        let keep = retained_depths(&nodes, &initial);
        for (id,(node, keep)) in nodes.iter_mut().zip(keep).enumerate() {
            node.keep_history = keep.max(usize::from(direct_back[id].is_some()));
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
        let mut layouts = BTreeMap::new();
        for node in &mut nodes {
            if node.supply.is_empty() { continue; }
            let width = node.supply.iter().map(|c| c.port.slot()+1).max().unwrap();
            if width > 64 { continue; }
            let mut layout = vec![None; width];
            for capture in &node.supply {
                if let Site::Effect(op) = capture.site {
                    if let Some(reuse) = node.program.reuse.iter().find(|r| r.op == op && r.back == 1) {
                        layout[capture.port.slot()] = reuse.port;
                    }
                }
            }
            if layout.iter().any(Option::is_some) {
                let rule = node.supply[0].port.rule();
                node.layout = layouts.entry((rule,layout.clone()))
                    .or_insert_with(|| SlotLayout::compile(rule,layout)).clone();
            }
        }
        let mut direct=vec![None;nodes.len()];
        for (id,back) in direct_back.into_iter().enumerate() {
            let Some(back)=back else {continue};
            let node=&nodes[id];
            let rule=node.supply[0].port.rule();
            let (donor,mapping)=direct_sources[id].as_ref().unwrap();
            let sources=exports[rule].iter().map(|site|mapping.get(site).map(|&site|port(*donor,site))).collect::<Vec<_>>();
            if sources.len()>64 || sources.iter().any(Option::is_none) {continue;}
            let Some(layout)=layouts.entry((rule,sources.clone()))
                .or_insert_with(||SlotLayout::compile(rule,sources)).clone() else {continue};
            let cell=Definition::new(p,rule).unwrap();
            let outputs=exports[rule].iter().enumerate().map(|(slot,&site)|(site,cell.relation(site).unwrap().table,slot)).collect();
            let required_sources=layout.sources.iter().flatten().fold(0,|mask,p|mask | (1u64<<p.slot()));
            let Some(unions) = crate::cell::compile_unions(p,rule,&exports[rule],
                |op|p.known_results.static_skip[rule][op] || nodes[id].program.reuse.iter().any(|r|r.op==op && r.equal_output)) else {continue};
            direct[id]=Some(Rc::new(crate::cell::CompletedPlan{rule,back,layout,outputs,required_sources,projections:vec![],unions}));
        }
        if completion {crate::cell::compile_projections(&mut direct,layouts.values().flatten().cloned());}
        // Freeze only after every ResultPort has its final rule/slot identity.
        // The pool is compile-local: states share immutable capture programs,
        // while each completed instance retains its own Results and lifetime.
        let mut pool = BTreeSet::<Rc<[Capture]>>::new();
        let mut transitions = BTreeSet::<Rc<[Transition]>>::new();
        let mut programs = BTreeSet::<Rc<Terminal>>::new();
        let mut frozen = Vec::with_capacity(nodes.len());
        for node in nodes {
            let supply = share_slice(node.supply, &mut pool);
            frozen.push(Node { unit: node.unit, failure: node.failure,
                program: share_program(node.program, &mut programs), next: share_slice(node.next, &mut transitions), supply,
                keep_history: node.keep_history, layout: node.layout });
        }
        drop(pool);
        drop(transitions);
        drop(programs);
        let nodes = frozen.into_boxed_slice();
        let mut by_rule = vec![vec![]; p.rules.len()];
        let mut roots = vec![None; p.rules.len()];
        for (&(rid, pivot), &leaf) in leaves {
            let leaf = NonZeroUsize::new(leaf.checked_add(1).expect("Cell leaf address overflow")).unwrap();
            let Some(pivot) = pivot else {
                roots[rid] = Some(leaf);
                continue;
            };
            let entries = &mut by_rule[rid];
            entries.resize(entries.len().max(pivot + 1), None);
            entries[pivot] = Some(leaf);
        }
        // Missing trailing rows and roots are already handled by checked lookup.
        while by_rule.last().is_some_and(Vec::is_empty) { by_rule.pop(); }
        while roots.last() == Some(&None) { roots.pop(); }
        let by_rule = DispatchRows::compile(by_rule);
        let roots = roots.into_boxed_slice();
        while exports.last().is_some_and(Vec::is_empty) { exports.pop(); }
        let exports = Rows::compile(exports);
        Self {
            reuse_results,
            congruence,
            query_ports,
            nodes,
            by_rule,
            roots,
            initial,
            exports,
            completion,
            lazy_unions,
            direct:if completion {direct.into_boxed_slice()}else{Box::new([])},
            depth,
        }
    }
    pub(crate) fn leaf(&self, r: usize, p: usize) -> Option<usize> {
        self.by_rule.get(r)?.get(p).copied().flatten().map(|id| id.get()-1)
    }
    pub(crate) fn unique_root(&self, rule: usize, require_supply: bool) -> Option<usize> {
        if let Some(leaf) = self.roots.get(rule).copied().flatten() {
            let pc = self.initial[leaf.get()-1];
            return (!require_supply || !self.nodes[pc].supply.is_empty()).then_some(pc);
        }
        let mut leaves = self.by_rule.get(rule)?.iter().flatten();
        let leaf = *leaves.next()?;
        if leaves.next().is_some() {
            return None;
        }
        let pc = self.initial[leaf.get()-1];
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
    pub(crate) fn state_contracts(&self, p: &Program, entry: impl Fn(usize) -> Entry) -> serde_json::Value {
        serde_json::Value::Array(self.nodes.iter().enumerate().map(|(id, n)| {
            if id == 0 { return serde_json::json!({"initial":true,"can_inherit":false}); }
            let (rid, pivot) = entry(n.unit);
            let rule = &p.artifact["recipe"]["rules"][rid];
            serde_json::json!({
                "environment":p.artifact["recipe"]["sha256"],
                "interface":{"query":rule["query"],"pivot":pivot,"sorts":p.templates[p.rules[rid].template].sorts},
                "effects":rule["effects"],
                "activation":{"rule":rid,"boundary":"original-source-run","position":"after-rhs-before-publication","union_commit":"source-run-boundary"},
                "completion_program":n.program,"exports":n.supply,"retained_stages":n.keep_history,
                "transitions":n.next,"restart":n.failure,
                "inheritance":{"storage":"existing-results","distance_delta":1,"retain":n.keep_history},
                "slot_layout":n.supply.iter().map(|c| serde_json::json!({"source":c.site,
                    "inherit":n.layout.as_ref().and_then(|l| l.sources.get(c.port.slot())).copied().flatten().map(|port|
                        serde_json::json!({"back":1,"rule":port.rule(),"slot":port.slot()}))})).collect::<Vec<_>>(),
                "can_inherit":(n.supply.is_empty() && n.keep_history > 0) || n.layout.is_some()
            })
        }).collect())
    }
    pub(crate) fn layout_storage(&self) -> (usize,usize) {
        let mut seen=BTreeSet::new();
        let bytes=self.nodes.iter().filter_map(|n|n.layout.as_ref())
            .chain(self.direct.iter().flatten().flat_map(|p|std::iter::once(&p.layout)
                .chain(p.projections.iter().flat_map(|(a,b)|[a,b]))))
            .filter(|l|seen.insert(Rc::as_ptr(l) as usize))
            .map(|l|l.storage_bytes()+2*std::mem::size_of::<usize>()).sum();
        (seen.len(),bytes)
    }
    pub(crate) fn layout(&self, id: usize) -> Option<&Rc<SlotLayout>> {
        self.nodes.get(id)?.layout.as_ref()
    }
    pub(crate) fn capture(&self, id: usize) -> (&[Capture], usize, Option<&Rc<SlotLayout>>) {
        self.nodes.get(id).map_or((&[], 0, None), |n| (n.supply.as_ref(), n.keep_history,n.layout.as_ref()))
    }
    pub(crate) fn program(&self, id: usize) -> Option<&Terminal> {
        self.nodes.get(id).map(|n| n.program.as_ref())
    }
    pub(crate) fn direct(&self,id:usize) -> Option<&Rc<crate::cell::CompletedPlan>> {
        self.direct.get(id)?.as_ref()
    }
    pub(crate) fn completion_enabled(&self) -> bool { self.completion }
    pub(crate) fn artifact(&self) -> serde_json::Value {
        let mut artifact=serde_json::json!({"schema":if self.lazy_unions {"eggfuse-result-switch/v5"} else if self.completion {"eggfuse-result-switch/v4"} else if self.query_ports {"eggfuse-result-switch/v3"} else if self.congruence {"eggfuse-result-switch/v2"} else {"eggfuse-result-switch/v1"},"reuse_results":self.reuse_results,"initial_entries":self.initial,"states":self.nodes,"max_back":self.depth});
        if self.completion { artifact["completion_states"]=serde_json::json!(self.direct.iter().map(|p|p.as_ref().map(|p|p.artifact())).collect::<Vec<_>>()); }
        artifact
    }
    pub(crate) fn enabled(&self) -> bool {
        !self.nodes.is_empty()
    }
    pub(crate) fn replay(&self, path: &[(Option<usize>, Entry)]) -> usize {
        path.iter().fold(0, |s, (op, e)| {
            let leaf = match *e {
                (r, Some(p)) => self.leaf(r, p),
                (r, None) => self.roots.get(r).copied().flatten().map(|id|id.get()-1),
            }.expect("validated Cell path entry");
            self.advance(s, op.unwrap_or(0), leaf)
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
    #[cfg(feature = "sparse-cells")]
    fn publication_seals_only_unique_current_results_without_copying_history() {
        let wanted = [Capture { site: Site::Effect(0), port: ResultPort::new(4, 0) },
            Capture { site: Site::Effect(1), port: ResultPort::new(4, 1) }];
        let mut h = History::default();
        h.capture(2, 4, &wanted, |_| None, |i| Some(Dependency::Function(i)));
        let address = Rc::as_ptr(&h.frames.as_ref().unwrap().owner);
        assert_eq!(h.seal_current(|w| if w == Dependency::Function(0) {
            Dependency::Function(8)
        } else { w }), Some((2, 1)));
        assert_eq!(Rc::as_ptr(&h.frames.as_ref().unwrap().owner), address);
        assert_eq!(h.get(1, wanted[0].port), Some(Dependency::Function(8)));
        let published = h.clone();
        assert_eq!(h.seal_current(|_| panic!("shared history must not be scanned")), None);
        assert_eq!(Rc::as_ptr(&h.frames.as_ref().unwrap().owner), address);
        h.capture(2, 4, &wanted, |_| None, |i| Some(Dependency::Function(i + 10)));
        assert_eq!(h.seal_current(|w| {
            let Dependency::Function(i) = w else { unreachable!() };
            assert!(i >= 10, "do not traverse preceding frames");
            Dependency::Function(i + 10)
        }), Some((2, 2)));
        assert_eq!(h.get(1, wanted[0].port), Some(Dependency::Function(20)));
        assert_eq!(h.get(2, wanted[0].port), Some(Dependency::Function(8)));
        assert_eq!(published.get(1, wanted[0].port), Some(Dependency::Function(8)));
        h.capture(2, 5, &[], |_| None, |_| None);
        assert_eq!(h.seal_current(|_| panic!("empty stage has no new results")), Some((0, 0)));
    }

    #[test]
    fn dispatch_rows_preserve_empty_rows_and_extreme_missing_indices() {
        let rows = DispatchRows::compile(vec![vec![], vec![NonZeroUsize::new(1), None], vec![], vec![]]);
        assert_eq!(rows.len(), 4);
        assert_eq!(rows.offsets.as_ref(), &[0, 0, 2, 2, 2]);
        assert_eq!(rows.get(0), Some([].as_slice()));
        assert_eq!(rows.get(1).unwrap(), &[NonZeroUsize::new(1), None]);
        assert_eq!(rows.get(2), Some([].as_slice()));
        assert_eq!(rows.get(3), Some([].as_slice()));
        assert_eq!(rows.get(4), None);
        assert_eq!(rows.get(usize::MAX), None);
        assert_eq!(DispatchRows::compile(vec![]).get(0), None);
    }
    #[test]
    fn completion_sharing_preserves_lowered_ports_and_copy_on_write() {
        let program = |slot| Terminal {
            reuse: vec![Reuse { equal_output: true, op: 2, back: 1, rule: 4,
                donor: Site::Effect(2), port: Some(ResultPort::new(4, slot)) }],
            queries: vec![QueryReuse { atom: 0, back: 1, rule: 4,
                donor: Site::Query(0), port: Some(ResultPort::new(4, slot)) }],
            complete: false,
        };
        let mut pool = BTreeSet::new();
        let a = share_program(program(0), &mut pool);
        let mut same = share_program(program(0), &mut pool);
        let other = share_program(program(1), &mut pool);
        assert!(Rc::ptr_eq(&a, &same));
        // The portable certificate omits ports; it is not an interning key.
        assert_eq!(serde_json::to_value(&a).unwrap(), serde_json::to_value(&other).unwrap());
        assert!(!Rc::ptr_eq(&a, &other));
        Rc::make_mut(&mut same).complete = true;
        assert!(!a.complete);
        assert!(same.complete);
        assert!(!Rc::ptr_eq(&a, &same));
        let completed = share_program((*same).clone(), &mut pool);
        assert!(!Rc::ptr_eq(&a, &completed));
        drop(pool);
        assert_eq!(a.reuse[0].port, Some(ResultPort::new(4, 0)));
        assert_eq!(other.queries[0].port, Some(ResultPort::new(4, 1)));
    }
    #[test]
    fn transition_pool_preserves_labels_targets_and_fallback() {
        let mut pool = BTreeSet::new();
        let a = share_slice(vec![((7, 2), 1)], &mut pool);
        let same = share_slice(vec![((7, 2), 1)], &mut pool);
        assert!(Rc::ptr_eq(&a, &same));
        for edge in [((8, 2), 1), ((7, 3), 1), ((7, 2), 0)] {
            assert!(!Rc::ptr_eq(&a, &share_slice(vec![edge], &mut pool)));
        }
        drop(pool);
        let mut switch = Switch::default();
        switch.initial = vec![0, 0, 0, 1];
        switch.nodes = [a, same].into_iter().map(|next| Node {
            unit: 0, failure: 0, program: Rc::new(Terminal::default()), next,
            supply: Rc::from([]), keep_history: 0, layout: None,
        }).collect();
        assert_eq!(switch.advance(0, 7, 2), 1);
        assert_eq!(switch.advance(1, 7, 2), 1);
        assert_eq!(switch.advance(0, 8, 2), 0);
        assert_eq!(switch.advance(0, 7, 3), 1);
    }
    #[test]
    fn capture_pool_keys_include_actual_ports_and_outlive_compiler_pool() {
        let mut pool = BTreeSet::new();
        let capture = |rule, slot| Capture { site: Site::Effect(2), port: ResultPort::new(rule, slot) };
        let a = share_slice(vec![capture(4, 0)], &mut pool);
        let b = share_slice(vec![capture(4, 0)], &mut pool);
        let other_rule = share_slice(vec![capture(5, 0)], &mut pool);
        let other_slot = share_slice(vec![capture(4, 1)], &mut pool);
        assert!(Rc::ptr_eq(&a, &b));
        assert!(!Rc::ptr_eq(&a, &other_rule));
        assert!(!Rc::ptr_eq(&a, &other_slot));
        let empty = share_slice(vec![], &mut pool);
        assert!(Rc::ptr_eq(&empty, &share_slice(vec![], &mut pool)));
        drop(pool);
        drop(a);
        assert_eq!(b.as_ref(), &[capture(4, 0)]);
        assert_eq!(Rc::strong_count(&b), 1);
    }
    #[test]
    fn compact_exports_preserve_slot_order_and_missing_rules() {
        let mut switch = Switch::default();
        assert!(switch.exports(0).is_empty());
        switch.exports = Rows::compile(vec![vec![], vec![Site::Query(0), Site::Effect(2)], vec![]]);
        assert!(switch.exports(0).is_empty());
        assert_eq!(switch.exports(1), &[Site::Query(0), Site::Effect(2)]);
        assert_eq!(switch.exports(1).binary_search(&Site::Effect(2)), Ok(1));
        assert!(switch.exports(2).is_empty());
        assert!(switch.exports(3).is_empty());
        assert!(switch.exports(usize::MAX).is_empty());
        let clone = switch.clone();
        drop(switch);
        assert_eq!(clone.exports(1), &[Site::Query(0), Site::Effect(2)]);
    }
    #[test]
    fn packed_dispatch_preserves_holes_roots_and_replay() {
        let address = |id: usize| NonZeroUsize::new(id.checked_add(1).unwrap());
        assert_eq!(address(usize::MAX-1).unwrap().get()-1, usize::MAX-1);
        assert_eq!(std::mem::size_of::<Option<NonZeroUsize>>(), std::mem::size_of::<usize>());
        let mut switch = Switch::default();
        assert_eq!(switch.leaf(0, 0), None);
        assert_eq!(switch.unique_root(0, false), None);
        switch.by_rule = DispatchRows::compile(vec![vec![address(0), None],
            vec![address(1), address(2)]]);
        switch.initial = vec![1, 2, 3];
        switch.nodes = (0..4).map(|unit| Node { unit, failure: 0,
            program: Rc::new(Terminal::default()), next: Rc::from([]), supply: Rc::from([]),
            keep_history: 0, layout: None }).collect();
        assert_eq!(switch.leaf(0, 0), Some(0));
        assert_eq!(switch.leaf(0, 1), None);
        assert_eq!(switch.leaf(0, 2), None);
        assert_eq!(switch.leaf(2, 0), None);
        assert_eq!(switch.unique_root(0, false), Some(1));
        assert_eq!(switch.unique_root(0, true), None);
        assert_eq!(switch.unique_root(1, false), None);
        switch.roots = vec![None, address(0)].into_boxed_slice();
        assert_eq!(switch.unique_root(1, false), Some(1));
        switch.nodes[1].next = Rc::from([((7, 2), 2)]);
        assert_eq!(switch.replay(&[(None, (1, None)), (Some(7), (1, Some(1)))]), 2);
        assert_eq!(switch.replay(&[(None, (0, Some(0)))]), 1);
    }
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
        let owner = Rc::downgrade(&history.frames.as_ref().unwrap().owner);
        let published = history.clone();
        for back in 2..=4 {
            let work = history.capture(4, 8, &[], |_| None, |_| None);
            assert!(work.carried);
            assert_eq!((work.reads, work.slots, work.allocations), (0, 0, 0));
            assert!(Rc::ptr_eq(&history.frames.as_ref().unwrap().owner, &published.frames.as_ref().unwrap().owner));
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
    fn mixed_layout_inherits_validated_slots_and_replaces_missing_or_fresh_results() {
        let old_ports = [ResultPort::new(4,0), ResultPort::new(4,1)];
        let captures = [Capture { site:Site::Effect(1), port:old_ports[0] }, Capture { site:Site::Effect(2), port:old_ports[1] }];
        let mut h = History::default();
        h.capture(1,4,&captures, |_|None, |i|Some(Dependency::Function(i)));
        let published = h.clone();
        let wanted = [Capture { site:Site::Query(0), port:ResultPort::new(5,0) },
            Capture { site:Site::Effect(1), port:ResultPort::new(5,1) },
            Capture { site:Site::Effect(2), port:ResultPort::new(5,2) }];
        let layout=SlotLayout::compile(5,vec![None,Some(old_ports[0]),Some(old_ports[1])]).unwrap();
        let work = h.capture_layout(1,5,&wanted,true,Some(&layout),1<<1,
            |_|Some(Dependency::Function(9)), |i| if i==1 { panic!("inherited receipt must not be read again") } else { Some(Dependency::Function(20)) });
        assert_eq!((work.inherited,work.reads,work.slots),(1,2,2));
        assert_eq!(h.get(1,ResultPort::new(5,0)),Some(Dependency::Function(9)));
        assert_eq!(h.get(1,ResultPort::new(5,1)),Some(Dependency::Function(1)));
        assert_eq!(h.get(1,ResultPort::new(5,2)),Some(Dependency::Function(20)));
        assert_eq!(published.get(1,old_ports[1]),Some(Dependency::Function(2)));
        h.capture_layout(1,5,&wanted,true,Some(&layout),0, |_|None, |_|None);
        assert_eq!(h.get(1,ResultPort::new(5,1)),None);
    }
    #[test]
    fn projected_results_preserve_missing_local_slots_and_bit_63() {
        let captures: Vec<_> = (0..64).map(|slot| Capture {
            site:Site::Effect(slot), port:ResultPort::new(4,slot),
        }).collect();
        let mut h=History::default();
        h.capture(1,4,&captures, |_|None, |i|Some(Dependency::Function(i)));
        let mut sources=vec![None;64];
        sources[1]=Some(captures[1].port);
        sources[63]=Some(captures[63].port);
        let layout=SlotLayout::compile(4,sources).unwrap();
        h.capture_layout(1,4,&captures,true,Some(&layout),(1<<63)|2, |_|None,
            |i| match i { 1|63=>panic!("inherited slot reread"), 3=>Some(Dependency::Function(99)), _=>None });
        for slot in 0..64 {
            let expected=match slot {1|63=>Some(Dependency::Function(slot)),3=>Some(Dependency::Function(99)),_=>None};
            assert_eq!(h.get(1,captures[slot].port),expected,"slot {slot}");
        }
    }
    #[test]
    fn repeated_slot_inheritance_keeps_one_leaf_owner_and_no_chain() {
        let wanted = [Capture { site:Site::Query(0), port:ResultPort::new(4,0) },
            Capture { site:Site::Effect(1), port:ResultPort::new(4,1) },
            Capture { site:Site::Effect(2), port:ResultPort::new(4,2) }];
        let layout=SlotLayout::compile(4,vec![None,Some(wanted[1].port),Some(wanted[2].port)]).unwrap();
        let mut h=History::default();
        h.capture(1,4,&wanted, |_|Some(Dependency::Function(0)), |i|Some(Dependency::Function(i)));
        let owner=h.snapshot(1).unwrap();
        for epoch in 1..=300 {
            let work=h.capture_layout(1,4,&wanted,true,Some(&layout),6,
                |_|Some(Dependency::Function(epoch+10)), |_|panic!("do not reread inherited effects"));
            assert_eq!((work.inherited,work.slots,work.reads,work.heap_frames),(2,1,1,0));
            let Trail::One(current)=h.frames.as_ref().unwrap().owner.as_ref() else { panic!() };
            assert!(Rc::ptr_eq(current.parent_owner().unwrap(),&owner.owner));
            assert_eq!(h.get(1,wanted[0].port),Some(Dependency::Function(epoch+10)));
            assert_eq!(h.get(1,wanted[1].port),Some(Dependency::Function(1)));
        }
        let mut storage=HistoryStorage::default();
        h.count_storage(&mut storage);
        h.clone().count_storage(&mut storage);
        storage.frame(&owner);
        assert_eq!((storage.owners,storage.layouts),(2,1));
        assert_eq!(storage.owner_payload_bytes,2*std::mem::size_of::<Trail>());
        assert_eq!(storage.result_array_bytes,h.frames.as_ref().unwrap().view().map(|_| {
            let Trail::One(r)=owner.owner.as_ref() else { unreachable!() }; r.storage_parts().0
        }).unwrap());
    }
    #[test]
    fn projected_history_keeps_logical_ports_through_empty_stages_and_deeper_retention() {
        let captures = [Capture { site: Site::Effect(0), port: ResultPort::new(4, 0) },
            Capture { site: Site::Effect(1), port: ResultPort::new(4, 1) }];
        let mut h = History::default();
        h.capture(1, 4, &captures, |_| None, |i| Some(Dependency::Function(i + 10)));
        let published = h.clone();
        let owner = Rc::downgrade(&h.frames.as_ref().unwrap().owner);
        let layout = SlotLayout::compile(5, vec![Some(captures[1].port), Some(captures[0].port)]).unwrap();
        let wanted = [Capture { site: Site::Effect(0), port: ResultPort::new(5, 0) },
            Capture { site: Site::Effect(1), port: ResultPort::new(5, 1) }];
        let work = h.capture_layout(1, 5, &wanted, true, Some(&layout), 3,
            |_| panic!("no query recapture"), |_| panic!("no effect recapture"));
        assert_eq!((work.allocations, work.slots, work.reads), (0, 0, 0));
        assert!(Rc::ptr_eq(&h.frames.as_ref().unwrap().owner, &published.frames.as_ref().unwrap().owner));
        assert_eq!(h.get(1, wanted[0].port), Some(Dependency::Function(11)));
        assert_eq!(h.get(1, captures[0].port), None);
        assert_eq!(published.get(1, captures[0].port), Some(Dependency::Function(10)));
        let mut extra = 0;
        assert_eq!(h.get_counted(1, wanted[1].port, &mut extra), Some(Dependency::Function(10)));
        assert_eq!(extra, 1);
        let mut storage = HistoryStorage::default();
        h.count_storage(&mut storage);
        published.count_storage(&mut storage);
        assert_eq!((storage.owners, storage.layouts), (1, 1));
        h.capture(3, 8, &[], |_| None, |_| None);
        h.capture(3, 4, &captures, |_| None, |i| Some(Dependency::Function(i + 20)));
        assert_eq!(h.get(1, captures[0].port), Some(Dependency::Function(20)));
        assert_eq!(h.get(2, wanted[0].port), None);
        assert_eq!(h.get(3, wanted[0].port), Some(Dependency::Function(11)));
        drop(published);
        assert!(owner.upgrade().is_some());
        h.capture(1, 8, &[], |_| None, |_| None);
        assert!(owner.upgrade().is_none());
    }
    #[test]
    fn partial_inheritance_from_a_projected_frame_does_not_reuse_wrong_ports() {
        let captures = [Capture { site: Site::Effect(0), port: ResultPort::new(4, 0) }];
        let mut h = History::default();
        h.capture(1, 4, &captures, |_| None, |_| Some(Dependency::Function(10)));
        let layout = SlotLayout::compile(5, vec![Some(captures[0].port)]).unwrap();
        let wanted = [Capture { site: Site::Effect(0), port: ResultPort::new(5, 0) }];
        h.capture_layout(1, 5, &wanted, true, Some(&layout), 1, |_| None, |_| unreachable!());
        let again = SlotLayout::compile(6, vec![Some(wanted[0].port)]).unwrap();
        // Ordinary inheritance has no baked composed layout for this renamed
        // source. It must read the actual result instead of exposing rule 4 as 5.
        let last = [Capture { site: Site::Effect(0), port: ResultPort::new(6, 0) }];
        let work = h.capture_layout(1, 6, &last, true, Some(&again), 1,
            |_| None, |_| Some(Dependency::Function(20)));
        assert_eq!((work.inherited, work.reads), (0, 1));
        assert_eq!(h.get(1, last[0].port), Some(Dependency::Function(20)));
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
            }] } else { vec![] }, keep_history: 0, layout: None,
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
