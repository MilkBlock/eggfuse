//! Source-scheduled Cell programs. A committed producer supplies the next
//! stage's complete context; the stage consumes it without a structural join.
//! Coverage is proved from functional table keys, not from observed frequency.
use crate::{
    entry_schedule::{Inputs, Seed},
    graph::{Dependency, Graph, Row},
    cell::{Matched, QueryFacts, QueryFrame, Site, bind_query as bind},
    program::*,
    value::{self, Value, canon},
};
use rustc_hash::FxHashMap as HashMap;
use serde::Serialize;
use serde_json::{Value as J, json};
use std::{
    cell::{OnceCell, RefCell},
    collections::{BTreeMap, BTreeSet},
    rc::Rc,
    time::Instant,
};

#[cfg(feature = "spine-shapes")]
#[path = "spine_shapes.rs"]
mod shapes;
#[derive(Clone)]
pub struct Cursor {
    #[cfg(feature = "iterative-bake")]
    state: crate::iterative::State,
    #[cfg(feature = "spine-blocks")]
    via_block: bool,
    #[cfg(feature = "spine-shapes")]
    trace: shapes::Trace,
    root: Rc<Root>,
    pub depth: u32,
    pub producer: usize,
}
#[cfg(feature = "sparse-cells")]
impl Cursor {
    pub(crate) fn uncached_query(&self) -> bool {
        self.root.context.get().is_none() && self.state.history.is_empty()
    }
    /// The selected source constructor already has a compiled result donor.
    /// Keep that existing handoff as its owner instead of probing again on a
    /// worker. This is admission only: no witness is certified here, and stale
    /// history still falls back at the original source operation.
    fn retain_constructor_handoff(&self, catalog: &crate::iterative::Catalog, operation: usize,
        answer: &mut Matched, stats: &mut Stats) {
        stats.preparation_handoff_history_checks += 1;
        if self.state.history.is_empty() { return; }
        stats.preparation_handoff_checks += 1;
        let Some(donor) = catalog.program(&self.state).iter().find(|donor| {
            stats.preparation_handoff_operations += 1;
            donor.op == operation
        }) else { return; };
        stats.preparation_handoff_reads += 1;
        if matches!(self.state.history.get_counted(donor.back,
            donor.port.expect("compiled Cell result port"), &mut stats.preparation_handoff_inherited_reads),
            Some(Dependency::Fact(_))) {
            answer.constructor = crate::cell::constructor_prepare::Prepared::Absent;
            stats.preparation_handoff_skips += 1;
        }
    }
}
#[cfg(feature = "sparse-cells")]
#[derive(Clone)]
enum PublishedBase {
    Root(Rc<Root>, usize),
    Active(Rc<Cursor>),
    #[cfg(feature = "sparse-cells")]
    Solo {
        id: u64,
        epoch: u64,
        stage: usize,
        producer: usize,
        root: OnceCell<Rc<Root>>,
    },
}
#[cfg(feature = "sparse-cells")]
pub(crate) struct Published {
    base: PublishedBase,
    output: usize,
    #[cfg(feature = "spine-shapes")]
    source: crate::graph::FactRef,
}
#[cfg(feature = "sparse-cells")]
impl Published {
    pub(crate) fn output_position(&self) -> usize { self.output }
    pub(crate) fn root_identity(&self) -> u64 { self.root_info().0 }
    pub(crate) fn cell_results(&self) -> (usize, usize, Option<crate::cell::ResultView<'_>>) {
        // A publication knows its logical producer even when it retained no
        // results. Do not expand a root or recover a physical Cell to find it.
        let (producer, results) = match &self.base {
            PublishedBase::Active(c) => (c.producer, c.state.history.current()),
            PublishedBase::Root(_, producer) | PublishedBase::Solo { producer, .. } => (*producer, None),
        };
        (producer, self.output, results)
    }
    fn root_info(&self) -> (u64, Option<&Root>) {
        match &self.base {
            PublishedBase::Root(r, _) => (r.id, Some(r)),
            PublishedBase::Active(c) => (c.root.id, Some(&c.root)),
            #[cfg(feature = "sparse-cells")]
            PublishedBase::Solo { id, root, .. } => (*id, root.get().map(Rc::as_ref)),
        }
    }
    pub(crate) fn expand(&self) -> Cursor {
        let mut c = match &self.base {
            PublishedBase::Root(r, p) => Cursor::fresh(r.clone(), *p),
            PublishedBase::Active(c) => (**c).clone(),
            #[cfg(feature = "sparse-cells")]
            PublishedBase::Solo {
                id,
                epoch,
                stage,
                producer,
                root,
            } => Cursor::fresh(
                root.get_or_init(|| {
                    Rc::new(Root {
                        id: *id,
                        epoch: *epoch,
                        set: *stage,
                        context: OnceCell::new(),
                    })
                })
                .clone(),
                *producer,
            ),
        };
        c.state.output = self.output;
        #[cfg(feature = "spine-shapes")]
        {
            c.trace.source = Some(self.source);
        }
        c
    }
}
#[cfg(not(feature = "sparse-cells"))]
pub(crate) type Published = Cursor;
#[cfg(not(feature = "sparse-cells"))]
impl Cursor {
    #[cfg(feature = "iterative-bake")]
    pub(crate) fn cell_results(&self) -> (usize, usize, Option<crate::cell::ResultView<'_>>) {
        (self.producer, self.state.output, self.state.history.current())
    }
    pub(crate) fn expand(&self) -> Self {
        self.clone()
    }
    fn root_info(&self) -> (u64, Option<&Root>) {
        (self.root.id, Some(&self.root))
    }
}
#[cfg(feature = "sparse-cells")]
impl Cursor {
    fn fresh(root: Rc<Root>, producer: usize) -> Self {
        Self {
            root,
            producer,
            depth: 1,
            state: Default::default(),
            via_block: false,
            #[cfg(feature = "spine-shapes")]
            trace: Default::default(),
        }
    }
}
#[cfg(feature = "sparse-cells")]
type StageTag = usize;
#[cfg(not(feature = "sparse-cells"))]
type StageTag = Rc<str>;
/// Shared by every published anchor of one logical root. The cell stores a
/// pointer so an unused root never reserves space for the full Context.
struct Root {
    id: u64,
    epoch: u64,
    set: StageTag,
    context: OnceCell<Box<RefCell<Context>>>,
}
impl Root {
    fn materialize(&self, stats: &mut Stats) -> &RefCell<Context> {
        self.context.get_or_init(|| {
            stats.contexts_created += 1;
            Box::new(RefCell::new(Context {
                #[cfg(not(feature = "sparse-cells"))]
                sets: BTreeSet::from([self.set.to_string()]),
                #[cfg(feature = "sparse-cells")]
                sets: smallvec::smallvec![self.set],
                last_epoch: self.epoch,
                visits: 1,
                unions: 0,
                facts: BTreeMap::new(),
            }))
        })
    }
}
/// One RHS application. New roots carry identity and source position until a
/// visible anchor wins publication; resumed applications already own a context.
pub(crate) enum Started {
    Root {
        id: u64,
        producer: usize,
        epoch: u64,
        set: StageTag,
    },
    Live(Cursor),
}
/// One completed source Cell owns its continuation until a final Entry needs
/// it. Promotion moves the started state once; other exports share its base.
struct Completion {
    #[cfg(feature = "sparse-cells")]
    phase: CompletionPhase,
    #[cfg(not(feature = "sparse-cells"))]
    started: Started,
    #[cfg(feature = "sparse-cells")]
    ready: Option<std::num::NonZeroUsize>,
    #[cfg(feature = "sparse-cells")]
    delivery: Option<Delivery>,
}
/// Storage of this Cell's outputs. The producer already lives in Completion's
/// phase; port meanings and order come from that shared Cell definition.
#[cfg(feature = "sparse-cells")]
struct Delivery {
    source: OutputSource,
    #[cfg(feature = "spine-shapes")]
    cell: u32,
}
#[cfg(feature = "sparse-cells")]
#[derive(Debug, PartialEq, Eq)]
enum OutputSource {
    Slots(Vec<Option<Dependency>>),
    History(u32),
    Function(u32),
}
#[cfg(feature = "sparse-cells")]
impl Delivery {
    fn new(width: usize, joint: bool, _cell: u32) -> Self {
        Self {
            source: if joint {
                assert!((1..=32).contains(&width));
                OutputSource::History(u32::MAX >> (32 - width))
            } else { OutputSource::Slots(Vec::new()) },
            #[cfg(feature = "spine-shapes")] cell: _cell,
        }
    }
}
#[cfg(feature = "sparse-cells")]
enum CompletionPhase {
    Started(Started),
    Published(PublishedBase),
    Moving,
}
impl Completion {
    #[cfg(feature = "sparse-cells")]
    fn producer(&self) -> usize {
        match &self.phase {
            CompletionPhase::Started(Started::Root { producer, .. }) => *producer,
            CompletionPhase::Started(Started::Live(c)) => c.producer,
            CompletionPhase::Published(PublishedBase::Root(_, producer))
                | CompletionPhase::Published(PublishedBase::Solo { producer, .. }) => *producer,
            CompletionPhase::Published(PublishedBase::Active(c)) => c.producer,
            CompletionPhase::Moving => unreachable!("Cell completion promotion"),
        }
    }
    #[cfg(feature = "sparse-cells")]
    fn results(&self) -> crate::cell::ResultView<'_> {
        let history = match &self.phase {
            CompletionPhase::Started(Started::Live(c)) => &c.state.history,
            CompletionPhase::Published(PublishedBase::Active(c)) => &c.state.history,
            _ => unreachable!("joint results retain their original live Cell continuation"),
        };
        history.current().expect("completed Cell results")
    }
    fn new(started: Started) -> Self {
        Self {
            #[cfg(feature = "sparse-cells")]
            phase: CompletionPhase::Started(started),
            #[cfg(not(feature = "sparse-cells"))]
            started,
            #[cfg(feature = "sparse-cells")]
            ready: None,
            #[cfg(feature = "sparse-cells")]
            delivery: None,
        }
    }
}
impl Started {
    #[cfg(feature = "iterative-bake")]
    pub(crate) fn closed(&self, catalog: &crate::iterative::Catalog) -> bool {
        matches!(self,Self::Live(c) if catalog.closed(&c.state))
    }
    #[cfg(feature = "iterative-bake")]
    pub(crate) fn result_inputs(
        &self,
        catalog: &crate::iterative::Catalog,
        stats: &mut Stats,
    ) -> smallvec::SmallVec<[crate::result_handoff::Input; 4]> {
        let Self::Live(c) = self else {
            return smallvec::SmallVec::new();
        };
        stats.history_result_reads += catalog.program(&c.state).len() as u64;
        catalog
            .program(&c.state)
            .iter()
            .map(|r| crate::result_handoff::Input {
                op: r.op,
                from_history: true,
                back: r.back,
                fact: match c.state.history.get_counted(r.back, r.port.expect("compiled Cell result port"), &mut stats.history_inherited_reads) {
                    Some(Dependency::Fact(f)) => Some(f),
                    _ => None,
                },
                equal_output: r.equal_output,
            })
            .collect()
    }
    #[cfg(feature = "iterative-bake")]
    fn seed_root(
        &mut self,
        cat: &crate::iterative::Catalog,
        rule: usize,
        run: usize,
        collect_pairs: bool,
        stats: &mut Stats,
    ) {
        if matches!(self, Self::Root { .. })
            && let Some(state) = cat.root_state(rule, run, collect_pairs)
        {
            self.cursor(stats);
            let Self::Live(c) = self else {
                unreachable!()
            };
            c.state = state;
            stats.root_completion_seeds += 1;
        }
    }
    #[cfg(feature = "iterative-bake")]
    fn remember(
        &mut self,
        cat: &crate::iterative::Catalog,
        rid: usize,
        read: impl Fn(usize) -> Option<Dependency>,
        effect: impl Fn(usize) -> Option<Dependency>,
        forwarded: u64,
        #[cfg(feature = "sparse-cells")] prepared: Option<crate::cell::Results>,
        stats: &mut Stats,
    ) {
        if let Self::Live(c) = self {
            let (sources, depth, inherit, layout) = cat.capture(&c.state);
            #[cfg(feature = "sparse-cells")]
            let shared = prepared.map(|results| c.state.history.capture_outputs(depth, results));
            #[cfg(not(feature = "sparse-cells"))]
            let shared = None;
            let work = shared.unwrap_or_else(|| c.state.history.capture_layout(
                depth,
                rid,
                sources,
                inherit,
                layout,
                forwarded,
                read,
                effect,
            ));
            stats.history_capture_reads += work.reads as u64;
            stats.history_slots_written += work.slots as u64;
            stats.history_allocations += work.allocations as u64;
            stats.history_empty_slots_written += work.empty_slots as u64;
            stats.history_carried_steps += u64::from(work.carried);
            stats.history_inherited_slots += work.inherited as u64;
            stats.history_heap_frames += work.heap_frames as u64;
            stats.history_shared_slots += work.shared_slots as u64;
        }
    }
    fn cursor(&mut self, stats: &mut Stats) -> &Cursor {
        if let Self::Root {
            id,
            producer,
            epoch,
            set,
        } = self
        {
            *self = Self::Live(Cursor {
                root: Rc::new(Root {
                    id: *id,
                    epoch: *epoch,
                    set: set.clone(),
                    context: OnceCell::new(),
                }),
                #[cfg(feature = "spine-shapes")]
                trace: Default::default(),
                #[cfg(feature = "spine-blocks")]
                via_block: false,
                #[cfg(feature = "iterative-bake")]
                state: Default::default(),
                depth: 1,
                producer: *producer,
            });
            stats.root_handles_created += 1;
        }
        let Self::Live(cursor) = self else {
            unreachable!()
        };
        cursor
    }
}
#[cfg(feature = "sparse-cells")]
type PortKey = smallvec::SmallVec<[Value; 1]>;
#[cfg(not(feature = "sparse-cells"))]
type PortKey = Vec<Value>;
struct Context {
    #[cfg(not(feature = "sparse-cells"))]
    sets: BTreeSet<String>,
    #[cfg(feature = "sparse-cells")]
    sets: smallvec::SmallVec<[usize; 2]>,
    last_epoch: u64,
    visits: u64,
    unions: u64,
    facts: BTreeMap<(usize, PortKey), Dependency>,
}
#[cfg(all(feature = "iterative-bake", feature = "sparse-cells"))]
#[derive(Debug)]
pub(crate) struct DirectOrigin(usize);

#[cfg(all(feature = "iterative-bake", not(feature = "sparse-cells")))]
pub(crate) struct DirectOrigin(pub Box<Cursor>);
#[cfg(all(feature = "iterative-bake", not(feature = "sparse-cells")))]
impl std::fmt::Debug for DirectOrigin {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_tuple("DirectOrigin")
            .field(&self.0.producer)
            .finish()
    }
}
/// Exact entry coverage, independently usable from residual query completion.
pub(crate) struct Coverage {
    pub answers: Vec<Matched>,
    pub covered: BTreeSet<(usize, Dependency)>,
    pub claimed: usize,
    pub complete: bool,
}
/// Keep the current source set's counter directly accessible between RHS
/// applications. Serialization includes both the current and settled counts.
#[derive(Default)]
struct SetCounts {
    settled: BTreeMap<String, u64>,
    recent: Option<(String, u64)>,
}
impl SetCounts {
    fn add(&mut self, name: &str) {
        if let Some((current, count)) = &mut self.recent
            && current == name
        {
            *count += 1;
            return;
        }
        if let Some((old, count)) = self.recent.take() {
            self.settled.insert(old, count);
        }
        let (key, count) = self.settled.remove_entry(name).unwrap_or_else(|| (name.to_owned(), 0));
        self.recent = Some((key, count + 1));
    }
}
impl Serialize for SetCounts {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error> {
        serializer.collect_map(
            self.settled.iter().map(|(name, count)| (name.as_str(), count))
                .chain(self.recent.iter().map(|(name, count)| (name.as_str(), count))),
        )
    }
}
#[cfg(test)]
mod set_counts_test {
    use super::*;
    #[cfg(feature = "sparse-cells")]
    #[test]
    fn fused_worker_selection_matches_source_order_then_stable_depth_selection() {
        // Arrival order is independent of source ordinal. Include equal keys,
        // unequal depths, exact depth ties and different prepared output slots.
        let spec = [(5, 9, 1), (0, 7, 2), (4, 7, 5), (2, 9, 3), (3, 7, 5), (1, 8, 1)];
        let mut expected = spec.to_vec();
        expected.sort_unstable_by_key(|&(ordinal, _, _)| ordinal);
        expected.sort_by(|a, b| a.1.cmp(&b.1).then_with(|| b.2.cmp(&a.2)));
        expected.dedup_by_key(|row| row.1);
        for seed in 0..64 {
            let mut state = seed + 1u64;
            let mut arrivals = spec.to_vec();
            for i in (1..arrivals.len()).rev() {
                state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
                arrivals.swap(i, state as usize % (i + 1));
            }
            let mut cursors = Vec::new();
            let mut roots = Vec::new();
            let mut stats = Stats::default();
            let rows = arrivals.into_iter().map(|(ordinal, key, depth)| {
                let root = Rc::new(Root { id: ordinal as u64, epoch: 1, set: 0, context: OnceCell::new() });
                roots.push((ordinal, Rc::downgrade(&root)));
                let mut cursor = Cursor::fresh(root, 0);
                cursor.depth = depth;
                let mut answer = Matched::matched([(1, Value::Int(key))].into_iter().collect(), QueryFacts::None, 1);
                if ordinal % 2 == 0 { answer.values.insert(15, Value::Int(ordinal as i64)); }
                Winner::new(answer, cursor, ordinal, &mut cursors, &mut stats)
            }).collect::<Vec<_>>();
            // Only the owned candidates cross threads. Their original Cursor
            // owners, including Rc roots, stay in this source Run's arena.
            let allocation = rows.as_ptr() as usize;
            let mut rows = std::thread::spawn(move || rows).join().unwrap();
            assert_eq!(rows.as_ptr() as usize, allocation);
            let mut comparisons = 0;
            assert_eq!(select_worker_winners(&mut rows, &[1], &mut comparisons, &mut cursors), 3);
            let actual = rows.iter().map(|winner| {
                let Value::Int(key) = winner.answer.values[&1] else { unreachable!() };
                let cursor = cursors[winner.answer.direct.as_ref().unwrap().0].as_ref().unwrap();
                assert_eq!(cursor.root.id, winner.ordinal as u64);
                (winner.ordinal, key, winner.depth)
            }).collect::<Vec<_>>();
            assert_eq!(actual, expected);
            assert!(comparisons > 0);
            for (ordinal, root) in &roots {
                assert_eq!(root.upgrade().is_some(), expected.iter().any(|r|r.0 == *ordinal));
            }
            for mut winner in rows { drop(take_origin(&mut cursors, winner.answer.direct.take().unwrap())); }
            assert!(cursors.is_empty());
            assert!(roots.iter().all(|(_, root)| root.upgrade().is_none()));
        }
    }
    #[cfg(feature = "sparse-cells")]
    #[test]
    fn deferred_group_removal_and_abort_preserve_live_origin_handles() {
        let g = crate::query::test_projection_graph();
        let mut spine = Programs::new(&g.program);
        spine.direct_sealed_answers = true;
        spine.deferred_slots.resize(8, usize::MAX);
        let mut roots = Vec::new();
        for rule in [3, 6] {
            let root = Rc::new(Root { id: rule as u64, epoch: 1, set: 0, context: OnceCell::new() });
            roots.push(Rc::downgrade(&root));
            let answer = Matched::matched([(0, Value::Int(rule as i64))].into_iter().collect(), QueryFacts::None, 1);
            let winner = Winner::new(answer, Cursor::fresh(root, 0), 0,
                &mut spine.sealed_cursors, &mut spine.stats);
            spine.deferred_slots[rule] = spine.deferred_queries.len();
            spine.deferred_queries.push(DeferredQuery { rule, complete: true, covered: 1, rows: vec![winner] });
        }
        let allocations = spine.deferred_frames().map(|(r, rows)| (r, rows.as_ptr() as usize)).collect::<Vec<_>>();
        let (_, mut first) = spine.finish_worker_rule(3, &[0], &mut 0).unwrap();
        assert!(!spine.deferred(3));
        assert!(spine.deferred(6));
        assert_eq!(spine.deferred_frames().map(|(r, rows)| (r, rows.as_ptr() as usize)).collect::<Vec<_>>(), allocations[1..]);
        assert_eq!(take_origin(&mut spine.sealed_cursors, first[0].direct.take().unwrap()).root.id, 3);
        assert!(roots[0].upgrade().is_none());
        assert!(roots[1].upgrade().is_some());
        // Abort the other query without exposing or committing its candidate.
        spine.discard_query_candidates();
        assert!(!spine.deferred(6));
        assert!(spine.deferred_frames().next().is_none());
        assert!(roots[1].upgrade().is_none());
        assert_eq!(spine.stats.aborted_cursor_releases, 1);
    }
    #[cfg(feature = "sparse-cells")]
    #[test]
    fn joint_delivery_retirement_cannot_turn_a_mask_into_an_arena_offset() {
        for width in [1, 32] {
            let mut delivery = Delivery::new(width, true, 9);
            for position in (0..width).rev() {
                let OutputSource::History(mask) = &mut delivery.source else { panic!("lost history") };
                assert_ne!(*mask & (1 << position), 0);
                *mask &= !(1 << position);
            }
            assert_eq!(delivery.source, OutputSource::History(0));
        }
        let owned = Delivery::new(64, false, 9);
        assert_eq!(owned.source, OutputSource::Slots(Vec::new()));
    }
    #[cfg(feature = "sparse-cells")]
    #[test]
    fn concurrent_effect_owners_move_results_into_delivery_and_abort_independently() {
        use crate::{cell::{CompletedEffects, Output}, program::{Rule, Template}};
        let mut g = crate::query::test_projection_graph();
        let ops = vec![Op::Set(0, vec![Arg::Slot(0), Arg::Slot(0)], Arg::Slot(1)),
            Op::Set(1, vec![Arg::Slot(0), Arg::Slot(0)], Arg::Slot(1))];
        g.program.templates.push(Template { name: "owned-outputs".into(),
            sorts: vec![json!({"kind":"i64"}); 2], defs: Default::default(),
            parent_columns: Default::default(), ops: ops.into() });
        g.program.rules.push(Rule { template: 0, query: Rc::new(vec![]), inputs: vec![0, 1].into(),
            completion: Default::default(), seminaive: false, direct: None });
        g.program.known_results.static_skip.push(Rc::new(vec![false; 2]));
        g.program.known_results.static_sources.push(vec![None; 2]);
        let mut spine = Programs::new(&g.program);
        spine.outputs[0] = vec![Output { operation: 0, table: 0, receipt_source: None },
            Output { operation: 1, table: 1, receipt_source: None }];
        spine.cell_output_widths[0] = 2;
        spine.compiled_commits = true;
        spine.receipts = true;
        let mut first = spine.begin_effects(&g, 0, false, true, None, &QueryFacts::None);
        let mut second = spine.begin_effects(&g, 0, false, true, None, &QueryFacts::None);
        first.record(0, Dependency::Function(10));
        second.record(0, Dependency::Function(20));
        first.record(1, Dependency::Function(11));
        second.record(1, Dependency::Function(21));
        let original = first.slot(0).unwrap() as *mut Option<Dependency> as usize;
        spine.pending_steps.push(Completion::new(Started::Root {
            id: 1, producer: 0, epoch: 0, set: 0,
        }));
        spine.install_delivery(0, 0, 0, false);
        spine.finish_effects_to(first, Some(0));
        spine.abort_effects(second);
        let mut third = spine.begin_effects(&g, 0, false, true, None, &QueryFacts::None);
        assert_eq!(third.get(0), None, "recycled results must not become evidence");
        third.record(0, Dependency::Function(30));
        let OutputSource::Slots(results) = &mut spine.pending_steps[0].delivery.as_mut().unwrap().source else { panic!("owned delivery") };
        assert_eq!(results.as_ptr() as usize, original, "completion moves ownership, not result slots");
        assert_eq!(results, &[Some(Dependency::Function(10)), Some(Dependency::Function(11))]);
        results[1] = None; // One table published; another still waits for completion.
        spine.abort_effects(third);
        let OutputSource::Slots(results) = &spine.pending_steps[0].delivery.as_ref().unwrap().source else { unreachable!() };
        assert_eq!(results, &[Some(Dependency::Function(10)), None]);
        assert_eq!(spine.stats.shared_output_arena_borrows, 0);
        assert_eq!(spine.stats.publication_buffer_moves, 1);
        assert_eq!(spine.stats.effect_buffer_reuses, 1);
    }
    #[test]
    fn serialization_includes_current_set_and_prior_occurrences() {
        let mut counts=SetCounts::default();
        for set in ["b","b","a","b"] { counts.add(set); }
        assert_eq!(json!(counts),json!({"a":1,"b":3}));
    }
}
#[derive(Default, Serialize)]
pub struct Stats {
    candidate_cursor_stores: u64,
    candidate_cursor_growths: u64,
    candidate_cursor_peak_bytes: u64,
    losing_cursor_releases: u64,
    aborted_cursor_releases: u64,
    deferred_group_growths: u64,
    deferred_group_peak_bytes: u64,
    query_fragment_frames: u64,
    query_fragment_slots: u64,
    query_fragment_capacity_bytes: u64,
    query_fragment_sealed_slots: u64,
    query_fragment_sealed_capacity_bytes: u64,
    origin_key_slots: u64,
    origin_map_writes: u64,
    origin_map_probes: u64,
    history_capture_reads: u64,
    history_shared_slots: u64,
    joint_history_checks: u64,
    joint_history_frames: u64,
    joint_scratch_borrows: u64,
    joint_scratch_growths: u64,
    joint_scratch_growth_bytes: u64,
    shared_output_arena_borrows: u64,
    owned_effect_frames: u64,
    effect_buffer_takes: u64,
    effect_buffer_returns: u64,
    effect_buffer_reuses: u64,
    effect_buffer_growths: u64,
    effect_buffer_growth_bytes: u64,
    effect_buffer_pool_growths: u64,
    effect_buffer_pool_growth_bytes: u64,
    prepared_effect_buffer_moves: u64,
    prepared_effect_spares_released: u64,
    prepared_effect_spare_bytes_released: u64,
    prepared_effect_joint_positions: u64,
    prepared_effect_joint_reads: u64,
    prepared_effect_joint_writes: u64,
    publication_buffer_moves: u64,
    joint_history_query_reads: u64,
    joint_history_query_writes: u64,
    joint_output_reads: u64,
    joint_output_mask_checks: u64,
    joint_output_mask_writes: u64,
    ripsat_plan_probes: u64,
    ripsat_layout_checks: u64,
    ripsat_witness_checks: u64,
    ripsat_projection_checks: u64,
    ripsat_boundary_reads: u64,
    ripsat_completed: u64,
    ripsat_union_cells: u64,
    ripsat_union_input_reads: u64,
    ripsat_union_result_reads: u64,
    ripsat_projected_slots: u64,
    ripsat_layout_fallbacks: u64,
    ripsat_boundary_fallbacks: u64,
    ripsat_witness_fallbacks: u64,
    history_slots_written: u64,
    history_seal_checks: u64,
    history_seal_reads: u64,
    history_seal_writes: u64,
    history_seal_shared: u64,
    history_allocations: u64,
    history_empty_slots_written: u64,
    history_carried_steps: u64,
    history_inherited_slots: u64,
    history_inherited_reads: u64,
    history_inheritance_marks: u64,
    history_heap_frames:u64,
    history_result_reads: u64,
    preparation_handoff_rule_checks: u64,
    preparation_handoff_history_checks: u64,
    preparation_handoff_checks: u64,
    preparation_handoff_operations: u64,
    preparation_handoff_reads: u64,
    preparation_handoff_inherited_reads: u64,
    preparation_handoff_skips: u64,
    legacy_entry_writes: u64,
    legacy_retirement_checks: u64,
    pub(crate) legacy_cursor_probes: u64,
    pub(crate) node_cursor_reads: u64,
    root_attempts: u64,
    root_handles_created: u64,
    #[cfg(feature = "sparse-cells")]
    deferred_single_roots: u64,
    #[cfg(feature = "sparse-cells")]
    absorbed_root_completions: u64,
    #[cfg(feature = "sparse-cells")]
    absorbed_root_checks: u64,
    contexts_created: u64,
    captured_contexts: u64,
    capture_reads: u64,
    receipt_attempts: u64,
    receipt_hits: u64,
    receipt_redirects: u64,
    receipt_rejections: u64,
    receipt_missing: u64,
    receipt_decodes: u64,
    receipt_hits_by_source: BTreeMap<String, u64>,
    anchor_publications: u64,
    missing_capture_rows: u64,
    anchors_retired: u64,
    query_attempts: u64,
    routed_spine_seeds: u64,
    sealed_partial_origins: u64,
    routed_matcher_seeds: u64,
    mixed_routed_queries: u64,
    query_takeovers: u64,
    partial_queries: u64,
    pivot_candidates: u64,
    shared_entry_hits: u64,
    entry_parameters_copied: u64,
    shared_entry_cross_rule_hits: u64,
    shared_row_hits: u64,
    peak_cached_entries: usize,
    entry_requests_by_rule: BTreeMap<usize, u64>,
    entry_checks_by_rule: BTreeMap<usize, u64>,
    fallback_pivots: u64,
    missing_context_pivots: u64,
    unsupported_key_pivots: u64,
    uncovered_queries: u64,
    pivots_skipped: u64,
    delta_rows_examined: u64,
    dispatch_headers: u64,
    context_reads: u64,
    captured_anchors: u64,
    #[cfg(feature = "sparse-cells")]
    unmaterialized_anchor_keys: u64,
    alias_query_forwards: u64,
    alias_effect_forwards: u64,
    distinct_anchor_keys: u64,
    context_fact_publications: u64,
    completed_steps: u64,
    root_completion_seeds: u64,
    port_refreshes: u64,
    pre_resume_port_lookups: u64,
    port_cache_fills: u64,
    query_receipt_attempts: u64,
    query_receipt_hits: u64,
    query_receipt_function_hits: u64,
    query_receipt_missing: u64,
    query_receipt_stale: u64,
    local_witness_contexts: u64,
    local_witness_routes: u64,
    local_witness_route_probes: u64,
    local_witness_route_steps: u64,
    local_witness_route_index_probes: u64,
    local_witness_route_comparisons: u64,
    local_witness_read_index_probes: u64,
    local_witness_key_fields: u64,
    local_witness_reads: u64,
    local_witness_hits: u64,
    local_witness_stale: u64,
    local_witness_misses: crate::graph::producer::WitnessMisses,
    local_witness_receipt_probes: u64,
    local_witness_receipt_steps: u64,
    local_witness_receipt_hits: u64,
    local_witness_row_reads: u64,
    local_witness_history_borrows: u64,
    local_witness_slot_reads: u64,
    completion_boundary_records: u64,
    completion_boundary_reads: u64,
    completion_order_checks: u64,
    completion_cell_visits: u64,
    completion_cursor_moves: u64,
    effect_frames: u64,
    effect_slots_initialized: u64,
    effect_slot_probes: u64,
    effect_slot_targets: u64,
    effect_outputs_reused: u64,
    effect_output_copies: u64,
    output_registrations: u64,
    cell_output_registrations: u64,
    cell_output_span_seals: u64,
    cell_output_sealed_receipts: u64,
    output_span_checks: u64,
    output_residual_dispatches: u64,
    effect_aborted_frames: u64,
    cell_output_spans: u64,
    cell_output_slots: u64,
    cell_output_receipts: u64,
    cell_output_slot_reads: u64,
    inline_function_receipts: u64,
    inline_function_reads: u64,
    cell_output_checks: u64,
    cell_output_deliveries: u64,
    peak_cell_output_slots: usize,
    // Removed packet allocation counters remain zero for historical comparison.
    fragment_packets: u64,
    fragment_receipts: u64,
    fragment_receipt_spills: u64,
    fragment_direct_inserts_avoided: u64,
    fragment_delivery_checks: u64,
    fragment_deliveries: u64,
    direct_publication_hash_probes: u64,
    guards: u64,
    cell_query_entries: u64,
    cell_query_steps: u64,
    cell_query_result_writes: u64,
    guard_rejections: u64,
    bindings: u64,
    steps_executed: u64,
    resumed_steps: u64,
    #[cfg(feature = "spine-blocks")]
    block_entries: u64,
    #[cfg(feature = "spine-blocks")]
    block_resumptions: u64,
    cross_stage_steps: u64,
    marker_roots: u64,
    constructor_requests: u64,
    function_updates: u64,
    union_requests: u64,
    max_chain: u32,
    max_sets_per_spine: usize,
    max_stage_visits: u64,
    capture_seconds: f64,
    publication_seconds: f64,
    scoped_anchor_checks: u64,
    scoped_direct_checks: u64,
    scoped_receipt_checks: u64,
    query_seconds: f64,
    by_set: SetCounts,
    resumed_by_set: SetCounts,
    bindings_by_rule: BTreeMap<usize, u64>,
    covered_by_rule: BTreeMap<usize, u64>,
    fallback_by_rule: BTreeMap<usize, u64>,
}
#[derive(Clone, Copy)]
pub(crate) struct Publication {
    #[cfg(feature = "iterative-bake")]
    output: usize,
    slot: usize,
    receipt: Option<Dependency>,
    #[cfg(feature = "spine-shapes")]
    source: crate::graph::FactRef,
}
/// Only boundary-normalized exports use this scratch list. Cell exports
/// already have shared template order and stay in their completion slots.
#[cfg(feature = "sparse-cells")]
#[derive(Clone, Copy)]
struct ReadyPublication {
    table: usize,
    witness: Dependency,
    publication: Publication,
    next: Option<std::num::NonZeroUsize>,
}
pub struct Programs {
    #[cfg(feature = "sparse-cells")]
    pub(crate) direct_sealed_answers: bool,
    #[cfg(feature = "structural-depth")]
    pub(crate) structural: crate::depth_runtime::Depth,
    #[cfg(feature = "structural-depth")]
    pub(crate) track_ports: Vec<usize>,
    #[cfg(feature = "iterative-bake")]
    pub(crate) training: crate::iterative::Training,
    #[cfg(feature = "spine-shapes")]
    shapes: shapes::Profile,
    pub enabled: bool,
    pub partial: bool,
    pub receipts: bool,
    pub audit_receipts: bool,
    shared_entries: bool,
    cache_epoch: u64,
    anchor_shapes: BTreeMap<(usize, usize), (usize, Vec<(usize, usize)>)>,
    entry_cache: HashMap<(usize, Dependency), (bool, usize)>,
    row_cache: HashMap<Dependency, Option<Rc<Row>>>,
    table_readers: Vec<Vec<usize>>,
    // Number of distinct planned input tables with at least one live anchor.
    live_inputs: Vec<usize>,
    queries: Rc<crate::cell::Queries>,
    local_witness_entries: Vec<Vec<bool>>,
    entries: HashMap<Dependency, Published>,
    #[cfg(feature = "sparse-cells")]
    entry_owned_tables: Vec<bool>,
    #[cfg(feature = "sparse-cells")]
    entry_owned_ids: Vec<usize>,
    #[cfg(feature = "sparse-cells")]
    ready_publications: Vec<ReadyPublication>,
    active_tables: Vec<usize>,
    // Anchor-producing operations and their optional proven receipt sources.
    outputs: Vec<Vec<crate::cell::Output>>,
    effect_plans: Vec<OnceCell<Rc<crate::cell::EffectPlan>>>,
    #[cfg(feature = "structural-depth")]
    full_effect_plans: Vec<OnceCell<Rc<crate::cell::EffectPlan>>>,
    alias_query_facts: Vec<QueryFacts>,
    owner_queries: bool,
    // All anchors of one application share this slot, including after key coalescence.
    pending_steps: Vec<Completion>,
    #[cfg(feature = "sparse-cells")]
    publication_base: u64,
    #[cfg(feature = "sparse-cells")]
    pub(crate) compiled_commits: bool,
    #[cfg(feature = "sparse-cells")]
    permanent: Vec<bool>,
    #[cfg(feature = "sparse-cells")]
    direct_publications: HashMap<Dependency, (usize, Publication)>,
    #[cfg(feature = "sparse-cells")]
    cell_output_widths: Vec<usize>,
    #[cfg(feature = "sparse-cells")]
    cell_outputs_pending: usize,
    // Only empty buffers are pooled. Live execution and publication each own
    // their actual results, independently of every other Cell.
    effect_buffers: Vec<Vec<Option<Dependency>>>,
    pending_anchors: Vec<(usize, Vec<Value>, Publication)>,
    marker_root: Vec<bool>,
    root_set: Rc<str>,
    #[cfg(feature = "sparse-cells")]
    stage_names: HashMap<String, usize>,
    #[cfg(feature = "sparse-cells")]
    stage_number: usize,
    capture_unions: Option<u64>,
    origins: Vec<HashMap<Vec<Value>, Cursor>>,
    origin_rules: Vec<usize>,
    retain_matched_origins: bool,
    // Query candidates and sealed bindings use the same move-only origin.
    // The Rc-backed Cursor stays on the coordinator throughout worker access.
    #[cfg(all(feature = "iterative-bake", feature = "sparse-cells"))]
    sealed_cursors: Vec<Option<Cursor>>,
    next_context: u64,

    #[cfg(feature = "sparse-cells")]
    answer_scratch: Winners,
    #[cfg(feature = "sparse-cells")]
    deferred_queries: Vec<DeferredQuery>,
    #[cfg(feature = "sparse-cells")]
    deferred_slots: Vec<usize>,
    pub stats: Stats,
}
// One owned execution fragment. Its inputs are also the winner key; there is
// no empty answer shell plus a separately moved binding vector.
#[cfg(not(feature = "sparse-cells"))]
struct Winner { answer: Matched, cursor: Cursor }
#[cfg(feature = "sparse-cells")]
pub(crate) struct Winner {
    pub(crate) answer: Matched,
    ordinal: usize,
    depth: u32,
}
#[cfg(feature = "sparse-cells")]
struct DeferredQuery { rule: usize, complete: bool, covered: usize, rows: Vec<Winner> }
#[cfg(feature = "sparse-cells")]
impl Winner {
    fn new(mut answer: Matched, cursor: Cursor, ordinal: usize,
        cursors: &mut Vec<Option<Cursor>>, stats: &mut Stats) -> Self {
        debug_assert!(answer.direct.is_none());
        let depth = cursor.depth;
        answer.direct = Some(DirectOrigin(cursors.len()));
        stats.candidate_cursor_stores += 1;
        stats.candidate_cursor_growths += u64::from(cursors.len() == cursors.capacity());
        cursors.push(Some(cursor));
        stats.candidate_cursor_peak_bytes = stats.candidate_cursor_peak_bytes.max(
            (cursors.capacity() * std::mem::size_of::<Option<Cursor>>()) as u64);
        Self { answer, ordinal, depth }
    }
}
#[cfg(feature = "sparse-cells")]
fn take_origin(cursors: &mut Vec<Option<Cursor>>, token: DirectOrigin) -> Cursor {
    let cursor = cursors[token.0].take().expect("owned Spine cursor");
    // Only vacant trailing slots are reused. Every remaining token keeps its
    // address; the consumed move-only token cannot refer to a later occupant.
    while cursors.last().is_some_and(Option::is_none) { cursors.pop(); }
    cursor
}
#[cfg(feature = "sparse-cells")]
fn select_worker_winners(results: &mut Vec<Winner>, inputs: &[usize], comparisons: &mut u64,
    cursors: &mut Vec<Option<Cursor>>) -> usize {
    // A total source ordinal preserves the old stable key/depth selection
    // without restoring source order first or stripping a temporary vector.
    results.sort_unstable_by(|a, b| {
        *comparisons += 1;
        a.answer.compare_inputs(&b.answer, inputs)
            .then_with(|| b.depth.cmp(&a.depth))
            .then_with(|| a.ordinal.cmp(&b.ordinal))
    });
    let before = results.len();
    results.dedup_by(|a, b| {
        if a.answer.compare_inputs(&b.answer, inputs).is_eq() {
            drop(take_origin(cursors, a.answer.direct.take().expect("candidate origin")));
            true
        } else { false }
    });
    before - results.len()
}
#[cfg(feature = "sparse-cells")]
type Winners = Vec<Winner>;
#[cfg(not(feature = "sparse-cells"))]
type Winners = BTreeMap<crate::slots::Slots, Winner>;
#[cfg(not(feature = "sparse-cells"))]
fn record_answer(
    results: &mut Winners,
    values: crate::slots::Slots,
    facts: QueryFacts,
    epoch: u64,

    cursor: Cursor,
) {
    let candidate = Winner {
        answer: Matched::matched(values, facts, epoch),
        cursor,
    };
    #[cfg(feature = "sparse-cells")]
    results.push(candidate);
    #[cfg(not(feature = "sparse-cells"))]
    {
        let mut candidate = candidate;
        let values = std::mem::take(&mut candidate.answer.values);
        match results.entry(values) {
            std::collections::btree_map::Entry::Vacant(e) => {
                e.insert(candidate);
            }
            std::collections::btree_map::Entry::Occupied(mut e) => {
                if candidate.cursor.depth > e.get().cursor.depth {
                    e.insert(candidate);
                }
            }
        }
    }
}
struct LocalWitness {
    producer: crate::cell::Producer,
    route: Rc<crate::multistage::Continuation>,
}
fn read_port(
    g: &mut Graph,
    cursor: &Cursor,
    _atom: usize,
    table: usize,
    args: PortKey,
    stats: &mut Stats,
    local: Option<&mut LocalWitness>,
    #[cfg(feature = "iterative-bake")] local_results: Option<crate::cell::ResultView<'_>>,
    #[cfg(feature = "structural-depth")] structural: (&mut crate::depth_runtime::Depth, Dependency),
) -> Result<Option<Row>> {
    let key = (table, args);
    let good = |r: &Row| {
        r.table == table && !r.hidden && r.values[..key.1.len()] == key.1[..]
    };
    #[cfg(feature = "iterative-bake")]
    if let Some(proof) = g.program.iterative.query_receipt(&cursor.state, _atom) {
        stats.query_receipt_attempts += 1;
        stats.history_result_reads += 1;
        if let Some(w) = cursor.state.history.get_counted(proof.back, proof.port.expect("compiled Cell result port"), &mut stats.history_inherited_reads) {
            g.stats.decoded_rows += 1;
            if let Some(row) = g.row(w)?.filter(good) {
                stats.query_receipt_hits += 1;
                stats.query_receipt_function_hits += u64::from(matches!(w, Dependency::Function(_)));
                return Ok(Some(row));
            }
            stats.query_receipt_stale += 1;
        } else {
            stats.query_receipt_missing += 1;
        }
    }
    // A candidate may fail a later port or guard, or lose
    // binding deduplication. Only an applied origin promotes the root.
    let cache = cursor.root.context.get();
    let witness = cache.and_then(|context| {
        let mut context = context.borrow_mut();
        context.canonicalize(g);
        context.facts.get(&key).copied()
    });
    let mut row = if let Some(w) = witness {
        stats.context_reads += 1;
        g.stats.decoded_rows += 1;
        g.row(w)?.filter(good)
    } else {
        None
    };
    if row.is_none() {
        if let Some(local) = local
            && let Some(source) = {
                stats.local_witness_read_index_probes += 1;
                local.route.witness(_atom)
            }
        {
            stats.local_witness_reads += 1;
            // This is a current positive witness, never a cached value or a
            // negative lookup proof. Missing or retired receipts fall back.
            #[cfg(feature = "iterative-bake")]
            let receipt = if let Some(port) = source.port {
                stats.local_witness_receipt_probes += 1;
                stats.local_witness_slot_reads += 1;
                stats.history_result_reads += 1;
                local_results.and_then(|results| results.get_counted(port, &mut stats.history_inherited_reads))
            } else { None };
            #[cfg(not(feature = "iterative-bake"))]
            let receipt = None;
            stats.local_witness_receipt_hits += u64::from(receipt.is_some());
            let mut reads = 0;
            row = local.producer.row(g, source.source, receipt, table, key.1.len() + 1,
                &mut stats.local_witness_misses, &mut stats.local_witness_contexts, &mut reads)?.filter(|r| {
                let equal = r.values.iter().zip(key.1.iter()).all(|(actual, expected)| {
                        stats.local_witness_key_fields += 1;
                        actual == expected
                    });
                stats.local_witness_misses.key += u64::from(!equal);
                equal
            });
            stats.local_witness_row_reads += reads;
            g.stats.decoded_rows += reads;
            if row.is_some() {
                stats.local_witness_hits += 1;
            } else {
                stats.local_witness_stale += 1;
            }
        }
    }
    if row.is_none() {
        stats.port_refreshes += 1;
        #[cfg(feature = "structural-depth")]
        let forwarded = structural.0.spine_read(g, structural.1, table, &key.1)?;
        #[cfg(not(feature = "structural-depth"))]
        let forwarded: Option<Row> = None;
        let probed = forwarded.is_none();
        row = match forwarded {
            Some(row) => Some(row),
            None => g.lookup_canonical(table, &key.1)?,
        };
        if let Some(context) = cache {
            let mut context = context.borrow_mut();
            if let Some(r) = row.as_ref().filter(|r| !r.hidden) {
                context.facts.insert(key, r.witness);
                stats.port_cache_fills += 1;
            } else {
                context.facts.remove(&key);
            }
        } else if probed {
            stats.pre_resume_port_lookups += 1;
        }
    }
    Ok(row.filter(|r| !r.hidden))
}
pub fn compile_entries(p: &Program) -> J {
    let mut entries = vec![];
    for (rid, r) in p.rules.iter().enumerate() {
        if r.seminaive {
            for (pivot, a) in r.query.iter().enumerate() {
                if let Call::Table(t) = a.call {
                    if let Some(order) = crate::cell::query_order(r, pivot, 0) {
                        let atoms = order.iter().map(|(i, _)| *i).collect::<Vec<_>>();
                        entries.push(json!({"rule":rid,"anchor":pivot,"table":p.tables[t].name,"atoms":atoms}));
                    }
                }
            }
        }
    }
    J::Array(entries)
}
impl Context {
    fn canonicalize(&mut self, g: &Graph) {
        if self.unions == g.stats.unions {
            return;
        }
        self.facts = std::mem::take(&mut self.facts)
            .into_iter()
            .map(|((t, key), w)| ((t, key.iter().map(|v| canon(v, &g.parents)).collect()), w))
            .collect();
        self.unions = g.stats.unions;
    }
}
impl Publication {
    /// Captures append one completed source Cell at a time; its effects retain
    /// source order. Deferred scopes keep these slots until all outputs drain.
    #[cfg(feature = "sparse-cells")]
    fn order(&self) -> (usize, usize) { (self.slot, self.output) }
}
impl Programs {
    #[cfg(feature = "iterative-bake")]
    pub(crate) fn cell_results<'a>(&'a self, entries: &'a crate::entry_schedule::Scheduler,
        seed: &Seed) -> Option<(usize, usize, Option<crate::cell::ResultView<'a>>)> {
        #[cfg(feature = "sparse-cells")]
        if self.entry_owned_tables[seed.packet.row.table] {
            return entries.publication(seed).map(Published::cell_results);
        }
        #[cfg(not(feature = "sparse-cells"))]
        let _ = entries;
        self.entries.get(&seed.packet.row.witness).map(Published::cell_results)
    }
    pub fn new(p: &Program) -> Self {
        let enabled = true;
        #[cfg(feature = "sparse-cells")]
        let permanent = {
            let mut v = vec![true; p.tables.len()];
            for t in &p.templates {
                for op in t.ops.iter() {
                    if let Op::Hide(table, ..) = op {
                        v[*table] = false;
                    }
                }
            }
            for init in &p.initial {
                if init["subsumed"].as_bool() == Some(true)
                    && let Some(t) = p.tables.iter().position(|t| init["table"] == t.name)
                {
                    v[t] = false;
                }
            }
            v
        };
        let mut s = Self {
            #[cfg(feature = "sparse-cells")]
            direct_sealed_answers: false,
            enabled,
            receipts: true,
            audit_receipts: false,
            partial: false,
            shared_entries: false,
            cache_epoch: u64::MAX,
            anchor_shapes: BTreeMap::new(),
            entry_cache: HashMap::default(),
            row_cache: HashMap::default(),
            table_readers: vec![Vec::new(); p.tables.len()],
            live_inputs: vec![0; p.rules.len()],
            queries: if enabled { p.cell_queries.clone() } else { Default::default() },
            local_witness_entries: {
                let mut entries = p.rules.iter().map(|r| vec![false; r.query.len()]).collect::<Vec<_>>();
                for route in p.multi_stage.routes.values() {
                    entries[route.consumer][route.anchor] |= route.reads.iter().any(|read| read.witness.is_some());
                }
                entries
            },
            entries: HashMap::default(),
            #[cfg(feature = "sparse-cells")]
            entry_owned_tables: vec![false; p.tables.len()],
            #[cfg(feature = "sparse-cells")]
            entry_owned_ids: vec![],
            #[cfg(feature = "sparse-cells")]
            ready_publications: vec![],
            active_tables: vec![0; p.tables.len()],
            #[cfg(feature = "spine-shapes")]
            shapes: Default::default(),
            #[cfg(feature = "iterative-bake")]
            training: Default::default(),
            outputs: vec![],
            effect_plans: vec![OnceCell::new(); p.rules.len()],
            #[cfg(feature = "structural-depth")]
            full_effect_plans: vec![OnceCell::new(); p.rules.len()],
            alias_query_facts: vec![],
            owner_queries: false,
            pending_steps: vec![],
            #[cfg(feature = "sparse-cells")]
            publication_base: 0,
            pending_anchors: vec![],
            #[cfg(feature = "sparse-cells")]
            compiled_commits: false,
            #[cfg(feature = "sparse-cells")]
            permanent,
            #[cfg(feature = "sparse-cells")]
            direct_publications: Default::default(),
            #[cfg(feature = "sparse-cells")]
            cell_output_widths: vec![0; p.rules.len()],
            #[cfg(feature = "sparse-cells")]
            cell_outputs_pending: 0,
            effect_buffers: vec![],
            marker_root: p.rules.iter().map(|r| p.templates[r.template].ops.iter().any(|op| match op {
                Op::Set(t, _, _) | Op::Let(_, Call::Table(t), _) => p.marker_tables.contains(t),
                _ => false,
            })).collect(),
            root_set: Rc::from(""),
            #[cfg(feature = "sparse-cells")]
            stage_names: Default::default(),
            #[cfg(feature = "sparse-cells")]
            stage_number: usize::MAX,
            capture_unions: None,
            #[cfg(feature = "structural-depth")]
            structural: crate::depth_runtime::Depth::new(p),
            #[cfg(feature = "structural-depth")]
            track_ports: vec![0; p.rules.len()],
            origins: vec![HashMap::default(); p.rules.len()],
            origin_rules: Vec::new(),
            retain_matched_origins: false,
            #[cfg(all(feature = "iterative-bake", feature = "sparse-cells"))]
            sealed_cursors: Vec::new(),
            next_context: 0,

            #[cfg(feature = "sparse-cells")]
            answer_scratch: vec![],
            #[cfg(feature = "sparse-cells")]
            deferred_queries: Vec::new(),
            #[cfg(feature = "sparse-cells")]
            deferred_slots: vec![usize::MAX; p.rules.len()],
            stats: Stats::default(),
        };
        if !enabled {
            return s;
        }
        let mut anchor_tables = BTreeSet::new();
        for (rid, pivot, _) in &p.multi_stage.stage_entries {
            let Call::Table(t) = p.rules[*rid].query[*pivot].call else {
                unreachable!()
            };
            anchor_tables.insert(t);
            if !s.table_readers[t].contains(rid) {
                s.table_readers[t].push(*rid);
            }
        }

        // Store one cursor per committed anchor. Consumer programs attach only
        // on their own Run, rather than preparing the entire fanout at publish.
        for (rid, r) in p.rules.iter().enumerate() {
            let outputs = crate::cell::Definition::new(p, rid).expect("typed Cell")
                .outputs(&anchor_tables, p.known_results.static_sources.get(rid).map(Vec::as_slice).unwrap_or(&[]));
            let mut query_facts = QueryFacts::None;
            for output in &outputs {
                if let Some(Site::Query(atom)) = output.receipt_source {
                    match query_facts {
                        QueryFacts::None => query_facts = QueryFacts::One(atom, None),
                        QueryFacts::One(first, _) if first != atom => {
                            query_facts = QueryFacts::All(vec![None; r.query.len()])
                        }
                        _ => {}
                    }
                }
            }
            s.outputs.push(outputs);
            #[cfg(feature = "iterative-bake")]
            for src in p.iterative.exports(rid) {
                if let crate::cell::Site::Query(i) = *src {
                    if matches!(r.query[i].call, Call::Table(t) if !p.tables[t].constructor) {
                        query_facts = QueryFacts::Ports(vec![None; r.query.len()]);
                        continue;
                    }
                    match query_facts {
                        QueryFacts::None => query_facts = QueryFacts::One(i, None),
                        QueryFacts::One(j, _) if i != j => {
                            query_facts = QueryFacts::All(vec![None; r.query.len()])
                        }
                        _ => {}
                    }
                }
            }
            s.alias_query_facts.push(query_facts);
        }
        #[cfg(feature = "spine-shapes")]
        s.shapes.catalog(p, &s.outputs);
        s
    }
    pub fn begin(
        &mut self,
        p: &Program,
        rid: usize,
        values: &crate::slots::Slots,
        set: &str,
        epoch: u64,
    ) -> Option<Cursor> {
        let mut step = self.begin_step(
            p,
            rid,
            values,
            set,
            epoch,
            #[cfg(feature = "iterative-bake")]
            None,
        )?;
        let cursor = step.cursor(&mut self.stats).clone();
        cursor.root.materialize(&mut self.stats);
        Some(cursor)
    }
    pub(crate) fn completed_step_count(&self) -> u64 { self.stats.completed_steps }
    /// Stored completions have odd positions; roots staged between them have
    /// the preceding even position and use their existing monotone root IDs
    /// to break ties. This needs no per-Completion order field. The base only
    /// advances when the complete pending arena is drained, including scopes.
    #[cfg(feature = "sparse-cells")]
    fn publication_order(&self, slot: usize, between: bool) -> u64 {
        self.publication_base.checked_add(slot as u64).and_then(|n| n.checked_mul(2))
            .and_then(|n| n.checked_add(u64::from(!between))).expect("Cell publication order exhausted")
    }

    #[cfg(feature="sparse-cells")]
    pub(crate) fn has_pending_origins(&self,rid:usize)->bool {
        self.enabled && !self.origins[rid].is_empty()
    }

    pub(crate) fn begin_step(
        &mut self,
        p: &Program,
        rid: usize,
        values: &crate::slots::Slots,
        set: &str,
        epoch: u64,
        #[cfg(feature = "iterative-bake")] direct: Option<DirectOrigin>,
    ) -> Option<Started> {
        if !self.enabled {
            return None;
        }
        #[cfg(all(feature = "iterative-bake", feature = "sparse-cells"))]
        let supplied = direct.map(|token| take_origin(&mut self.sealed_cursors, token));
        #[cfg(all(feature = "iterative-bake", not(feature = "sparse-cells")))]
        let supplied = direct.map(|d| *d.0);
        #[cfg(not(feature = "iterative-bake"))]
        let supplied: Option<Cursor> = None;
        let previous = supplied.or_else(|| {
            let bucket = &mut self.origins[rid];
            if bucket.is_empty() {
                return None;
            }
            self.stats.origin_key_slots += p.rules[rid].inputs.len() as u64;
            self.stats.origin_map_probes += 1;
            let key: smallvec::SmallVec<[Value; 6]> = p.rules[rid]
                .inputs
                .iter()
                .map(|i| values[i].clone())
                .collect();
            bucket.remove(key.as_slice())
        });
        if previous.is_none() && self.outputs.get(rid).is_none_or(Vec::is_empty) {
            return None;
        }
        #[cfg(feature = "sparse-cells")]
        if self.root_set.as_ref() != set || self.stage_number == usize::MAX {
            self.root_set = Rc::from(set);
            self.stage_number = if let Some(&n) = self.stage_names.get(set) {
                n
            } else {
                let n = self.stage_names.len();
                self.stage_names.insert(set.into(), n);
                n
            };
        }
        self.stats.steps_executed += 1;
        self.stats.by_set.add(set);
        if let Some(mut cursor) = previous {
            self.stats.resumed_steps += 1;
            #[cfg(feature = "slot-transfer-audit")]
            crate::transfer_audit::resume(cursor.root.id, cursor.producer, rid, cursor.depth);
            #[cfg(feature = "spine-blocks")]
            {
                self.stats.block_resumptions += u64::from(cursor.via_block);
            }
            self.stats.resumed_by_set.add(set);
            cursor.depth = cursor
                .depth
                .checked_add(1)
                .expect("stage recipe depth exhausted");
            #[cfg(feature = "spine-shapes")]
            self.shapes.resume(&mut cursor.trace, cursor.producer, rid);
            cursor.producer = rid;
            let mut c = cursor.root.materialize(&mut self.stats).borrow_mut();
            #[cfg(not(feature = "sparse-cells"))]
            if !c.sets.contains(set) {
                self.stats.cross_stage_steps += 1;
                c.sets.insert(set.into());
            }
            #[cfg(feature = "sparse-cells")]
            if !c.sets.contains(&self.stage_number) {
                self.stats.cross_stage_steps += 1;
                c.sets.push(self.stage_number);
            }
            if c.last_epoch != epoch {
                c.visits += 1;
                c.last_epoch = epoch;
            }
            self.stats.max_chain = self.stats.max_chain.max(cursor.depth);
            self.stats.max_sets_per_spine = self.stats.max_sets_per_spine.max(c.sets.len());
            self.stats.max_stage_visits = self.stats.max_stage_visits.max(c.visits);
            drop(c);
            Some(Started::Live(cursor))
        } else {
            let id = self.next_context;
            self.next_context += 1;
            self.stats.root_attempts += 1;
            self.stats.marker_roots += u64::from(self.marker_root[rid]);
            self.stats.max_chain = self.stats.max_chain.max(1);
            self.stats.max_sets_per_spine = self.stats.max_sets_per_spine.max(1);
            self.stats.max_stage_visits = self.stats.max_stage_visits.max(1);
            #[cfg(not(feature = "sparse-cells"))]
            if self.root_set.as_ref() != set {
                self.root_set = Rc::from(set);
            }
            Some(Started::Root {
                id,
                producer: rid,
                epoch,
                #[cfg(not(feature = "sparse-cells"))]
                set: self.root_set.clone(),
                #[cfg(feature = "sparse-cells")]
                set: self.stage_number,
            })
        }
    }
    #[cfg(all(feature = "rhs-work-audit", feature = "rhs-locals"))]
    pub(crate) fn anchor_at(&self, r: usize, op: usize) -> bool {
        self.outputs[r].iter().any(|o| o.operation == op)
    }
    pub fn capture_receipts(&self, rid: usize) -> bool {
        self.enabled && self.receipts && self.outputs.get(rid).is_some_and(|ops| !ops.is_empty())
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn permanent_tables(&self) -> &[bool] { &self.permanent }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn preparation_layout(&self, p: &Program, rid: usize) -> Option<std::sync::Arc<crate::cell::EffectLayout>> {
        if !self.capture_receipts(rid) { return None; }
        let plan = self.effect_plans[rid].get_or_init(|| Rc::new(crate::cell::EffectPlan::compile(
            p, rid, &self.outputs[rid], self.cell_output_widths[rid], false)));
        Some(plan.layout.clone())
    }
    pub(crate) fn alias_query_facts(&self, g: &Graph, rid: usize) -> QueryFacts {
        // Only an admitted continuation (or explicit fragment training) reads
        // the ownership Entry receipts. Keep the original Spine alias plan
        // intact: unrelated rules must not clone a full query-width packet.
        // Check at consumption, since training can start after Executor::new.
        let base = if self.owner_queries && g.needs_ownership_entry(rid) {
            QueryFacts::Ports(vec![None; g.program.rules[rid].query.len()])
        } else if self.receipts || self.owner_queries {
            self.alias_query_facts.get(rid).cloned().unwrap_or_default()
        } else {
            QueryFacts::None
        };
        #[cfg(feature = "structural-depth")]
        if self.track_ports[rid] > 0 {
            return QueryFacts::Tracked(Box::new(base), vec![None; self.track_ports[rid]], 0);
        }
        base
    }
    pub(crate) fn enable_owner_queries(&mut self) {
        // Enabling ownership never overwrites the independent static alias
        // requirements; repeated configuration cannot broaden their scope.
        self.owner_queries = true;
    }
    /// Begin the source owner's existing result layout. Prepared worker results
    /// may transfer the same allocation; no unrelated publication is borrowed.
    pub(crate) fn begin_effects(&mut self, g: &Graph, rid: usize, full: bool, force: bool,
        _step: Option<&Started>, _facts: &QueryFacts) -> crate::cell::Effects {
        self.begin_effects_with_results(g, rid, full, force, _step, _facts, None)
    }
    pub(crate) fn begin_effects_with_results(&mut self, g: &Graph, rid: usize, full: bool, force: bool,
        _step: Option<&Started>, _facts: &QueryFacts,
        prepared: Option<Vec<Option<Dependency>>>) -> crate::cell::Effects {
        if !force && !full && !self.capture_receipts(rid) {
            debug_assert!(prepared.as_ref().is_none_or(Vec::is_empty));
            return Default::default();
        }
        let outputs = self.outputs.get(rid).map_or(&[][..], Vec::as_slice);
        #[cfg(feature = "sparse-cells")]
        let published = self.cell_output_widths[rid];
        #[cfg(not(feature = "sparse-cells"))]
        let published = 0;
        let plans = &self.effect_plans;
        #[cfg(feature = "structural-depth")]
        let plans = if full { &self.full_effect_plans } else { plans };
        let plan = plans[rid].get_or_init(|| Rc::new(crate::cell::EffectPlan::compile(&g.program, rid, outputs, published, full))).clone();
        #[cfg(feature = "sparse-cells")]
        debug_assert!(prepared.as_ref().is_none_or(|_| g.program.executions[rid].constructor.as_ref()
            .and_then(|p|p.result_layout.as_ref()).is_some_and(|layout|std::sync::Arc::ptr_eq(layout,&plan.layout))),
            "configuration freezes one worker/source result layout before execution");
        #[cfg(feature = "sparse-cells")]
        let keep = self.compiled_commits && self.receipts && !self.audit_receipts
            && published != 0 && outputs[..published].iter().all(|o| !g.has_visibility_changes(o.table));
        #[cfg(not(feature = "sparse-cells"))]
        let keep = false;
        let prepared = prepared.filter(|b| !b.is_empty());
        let buffer = self.borrow_effect_buffer();
        let before = buffer.capacity() * std::mem::size_of::<Option<Dependency>>();
        self.stats.owned_effect_frames += 1;
        #[cfg(feature = "sparse-cells")]
        if keep && !full && !g.program.iterative.tracks_slots() && let Some(width) = plan.joint_width() {
            self.stats.joint_history_checks += 1;
            if let Some(Started::Live(cursor)) = _step {
                let (sources, depth, _, _) = g.program.iterative.capture(&cursor.state);
                // Supply is a checked subset of this rule's exports. Equal
                // width proves complete coverage without per-instance maps.
                if depth != 0 && sources.len() == width {
                    let (mut frame, queries) = crate::cell::Effects::begin_joint(plan, buffer, _facts);
                    let growth = frame.scratch_capacity_bytes().saturating_sub(before);
                    self.stats.joint_scratch_borrows += 1;
                    self.stats.joint_scratch_growths += u64::from(growth != 0);
                    self.stats.joint_scratch_growth_bytes += growth as u64;
                    self.stats.effect_buffer_growths += u64::from(growth != 0);
                    self.stats.effect_buffer_growth_bytes += growth as u64;
                    self.stats.joint_history_frames += 1;
                    self.stats.joint_history_query_reads += queries as u64;
                    self.stats.joint_history_query_writes += queries as u64;
                    if let Some(prepared) = prepared {
                        let (positions, reads, writes) = frame.import_prepared(&prepared);
                        self.stats.prepared_effect_joint_positions += positions as u64;
                        self.stats.prepared_effect_joint_reads += reads as u64;
                        self.stats.prepared_effect_joint_writes += writes as u64;
                        // This execution already borrowed its ordinary spare
                        // for joint scratch. Recycling a second incoming array
                        // would grow the idle pool on every such handoff.
                        self.stats.prepared_effect_spares_released += 1;
                        self.stats.prepared_effect_spare_bytes_released +=
                            (prepared.capacity()*std::mem::size_of::<Option<Dependency>>()) as u64;
                        drop(prepared);
                    }
                    return frame;
                }
            }
        }
        #[cfg(feature = "sparse-cells")]
        if let Some(prepared) = prepared {
            self.stats.prepared_effect_buffer_moves += 1;
            // The incoming frame replaces the spare this execution would have
            // borrowed. Otherwise every prepared publication adds another
            // permanent cache entry, even when the live working set is stable.
            self.stats.prepared_effect_spares_released += u64::from(buffer.capacity()!=0);
            self.stats.prepared_effect_spare_bytes_released += before as u64;
            drop(buffer);
            return crate::cell::Effects::adopt(plan, prepared, keep);
        }
        let frame = crate::cell::Effects::begin(plan, buffer, keep);
        let growth = frame.scratch_capacity_bytes().saturating_sub(before);
        self.stats.effect_buffer_growths += u64::from(growth != 0);
        self.stats.effect_buffer_growth_bytes += growth as u64;
        frame
    }
    fn borrow_effect_buffer(&mut self) -> Vec<Option<Dependency>> {
        self.stats.effect_buffer_takes += 1;
        let buffer = self.effect_buffers.pop().unwrap_or_default();
        self.stats.effect_buffer_reuses += u64::from(buffer.capacity() != 0);
        debug_assert!(buffer.is_empty());
        buffer
    }
    fn recycle_effect_buffer(&mut self, mut buffer: Vec<Option<Dependency>>) {
        buffer.clear();
        if buffer.capacity() == 0 { return; }
        self.stats.effect_buffer_returns += 1;
        let before = self.effect_buffers.capacity();
        self.effect_buffers.push(buffer);
        let growth = self.effect_buffers.capacity() - before;
        self.stats.effect_buffer_pool_growths += u64::from(growth != 0);
        self.stats.effect_buffer_pool_growth_bytes += (growth * std::mem::size_of::<Vec<Option<Dependency>>>()) as u64;
    }
    pub(crate) fn finish_effects(&mut self, effects: impl crate::cell::CompletedEffects) {
        self.finish_effects_to(effects, None);
    }
    fn finish_effects_to(&mut self, effects: impl crate::cell::CompletedEffects, output: Option<usize>) {
        if let Some((buffer, slots, probes, targets)) = effects.finish(output.is_some()) {
            self.stats.effect_frames += 1;
            self.stats.effect_slots_initialized += slots as u64;
            self.stats.effect_slot_probes += probes;
            self.stats.effect_slot_targets += targets;
            #[cfg(feature = "sparse-cells")]
            if let Some(slot) = output
                && let Some(Delivery { source: OutputSource::Slots(results), .. }) = &mut self.pending_steps[slot].delivery {
                debug_assert!(results.is_empty());
                *results = buffer;
                self.stats.publication_buffer_moves += 1;
                return;
            }
            debug_assert!(buffer.is_empty());
            self.recycle_effect_buffer(buffer);
        }
    }
    pub(crate) fn abort_effects(&mut self, effects: crate::cell::Effects) {
        self.stats.effect_aborted_frames += 1;
        self.finish_effects(effects);
    }
    /// Exact dispatch selects a prechecked constructor completion. Inputs and
    /// the published anchor were already matched; the pure monotone template
    /// proves the full keys. Only actual receipt lifetime remains to validate.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn prepare_direct_completion(&mut self,g:&Graph,rid:usize,step:&Started)
        -> Option<(crate::cell::Results, Option<crate::cell::LazyUnions>)> {
        if !g.program.iterative.completion_enabled() {return None;}
        let Started::Live(cursor)=step else {return None};
        self.stats.ripsat_plan_probes+=1;
        let plan=g.program.iterative.direct_completion(&cursor.state)?;
        debug_assert_eq!(plan.rule,rid);
        let outputs=&self.outputs[rid];
        let width=self.cell_output_widths[rid];
        self.stats.ripsat_layout_checks+=1;
        if !outputs.is_empty() && (!self.compiled_commits || !self.receipts || self.audit_receipts
            || width>32
            || outputs.iter().any(|o|!self.permanent[o.table] || g.has_visibility_changes(o.table))) {
            self.stats.ripsat_boundary_fallbacks+=1; return None;
        }
        if !outputs.is_empty() {
            let effect=self.effect_plans[rid].get_or_init(||Rc::new(crate::cell::EffectPlan::compile(
                &g.program,rid,outputs,width,false)));
            if width!=0 && effect.joint_width()!=Some(plan.layout.sources.len()) {
                self.stats.ripsat_layout_fallbacks+=1; return None;
            }
        }
        let Some(results)=cursor.state.history.project_complete(plan,&mut self.stats.ripsat_projection_checks) else {
            self.stats.ripsat_layout_fallbacks+=1; return None;
        };
        for &(_,table,slot) in &plan.outputs {
            self.stats.ripsat_witness_checks+=1;
            let port=crate::cell::ResultPort::new(rid,slot);
            let Some(w)=results.get(port) else {self.stats.ripsat_witness_fallbacks+=1;return None};
            if !g.receipt_visible(g.resolve_receipt(w),table) {
                self.stats.ripsat_witness_fallbacks+=1; return None;
            }
        }
        Some((results,plan.unions.clone()))
    }
    /// All constructor results were validated before any union is enqueued.
    /// Read the actual matched input or retained result, without a temporary
    /// RHS frame, result assignment, or replay of the constructor instructions.
    /// Only the ordinary source-Run completion may commit these equalities.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn enqueue_direct_unions(&mut self, g: &mut Graph, rid: usize,
        inputs: &crate::slots::Slots, results: &crate::cell::Results,
        program: &crate::cell::LazyUnions) -> Result<()> {
        use crate::cell::UnionPort;
        self.stats.ripsat_union_cells += 1;
        for effect in program.iter() {
            let (crate::cell::UnionEffect::Source(pair) | crate::cell::UnionEffect::Constructor(pair)) = effect;
            let mut read = |port| -> Result<Value> {
                let value = match port {
                    UnionPort::Input(slot) => {
                        self.stats.ripsat_union_input_reads += 1;
                        inputs.get(&slot).cloned().ok_or("missing completed union input")?
                    },
                    UnionPort::Result(slot) => {
                        self.stats.ripsat_union_result_reads += 1;
                        let witness=results.get(crate::cell::ResultPort::new(rid,slot))
                            .ok_or("missing completed union result")?;
                        let row=g.row(g.resolve_receipt(witness))?.ok_or("retired completed union result")?;
                        row.values.last().cloned().ok_or("empty completed union result")?
                    },
                };
                Ok(crate::value::canon(&value,&g.parents))
            };
            let a=read(pair[0])?;
            let b=read(pair[1])?;
            match effect {
                crate::cell::UnionEffect::Source(_) => g.enqueue_source_union(a,b)?,
                crate::cell::UnionEffect::Constructor(_) => g.enqueue_union(a,b)?,
            }
        }
        self.effects(0,0,program.len() as u64);
        Ok(())
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn complete_direct(&mut self,g:&Graph,rid:usize,cell:u32,step:Started,
        results:crate::cell::Results,query_fact:impl Fn(usize)->Option<Dependency>) -> Result<()> {
        self.stats.ripsat_completed+=1;
        self.stats.ripsat_projected_slots+=results.len() as u64;
        self.stats.ripsat_boundary_reads+=self.outputs[rid].len().saturating_sub(self.cell_output_widths[rid]) as u64;
        let effects=crate::cell::ProjectedEffects {
            results:Some(results), plan:self.effect_plans[rid].get().cloned(),
            published:self.cell_output_widths[rid],
        };
        self.complete(g,rid,cell,step,query_fact,effects,
            |_|Err("specialized Cell escaped its validated publication boundary".into()))
    }
    pub(crate) fn complete<E: crate::cell::CompletedEffects>(
        &mut self,
        g: &Graph,
        rid: usize,
        _cell: u32,
        mut step: Started,
        query_fact: impl Fn(usize) -> Option<Dependency>,
        effects: E,
        mut key: impl FnMut(&[Arg]) -> Result<Vec<Value>>,
    ) -> Result<()> {
        #[cfg(feature = "sparse-cells")]
        let mut effects = effects;
        self.stats.completed_steps += 1;
        // A selected query continuation is not an applied rule. Record its
        // bounded provenance only after every source RHS operation succeeded.
        // Queued unions still retain their original publication boundary.
        #[cfg(feature = "iterative-bake")]
        if let Started::Live(cursor) = &mut step {
            self.training.applied(&g.program.iterative, &mut cursor.state,
                g.program.rules[rid].inputs.len());
        }
        self.stats.history_inheritance_marks += effects.forwarded().count_ones() as u64;
        if self.outputs.get(rid).is_none_or(Vec::is_empty) {
            self.finish_effects(effects);
            return Ok(());
        }
        let clock = E::DEFERRED_KEYS.then(Instant::now);
        let rule = &g.program.rules[rid];
        let template = &g.program.templates[rule.template];
        self.capture_unions.get_or_insert(g.stats.unions);
        let slot = self.pending_steps.len();
        #[cfg(feature = "sparse-cells")]
        let joint = effects.has_joint_results();
        #[cfg(feature = "sparse-cells")]
        let sealed = if joint || effects.output_frame().is_some() {
            self.stats.output_span_checks += 1;
            effects.sealed_outputs()
        } else { None };
        #[cfg(not(feature = "sparse-cells"))]
        let joint = false;
        #[cfg(feature = "iterative-bake")]
        let step = {
            let mut s = step;
            let root = matches!(s, Started::Root { .. });
            s.seed_root(
                &g.program.iterative,
                rid,
                self.training.run,
                self.training.collect_pairs,
                &mut self.stats,
            );
            if root && let Started::Live(cursor) = &mut s {
                self.training.trace_root(&g.program.iterative, &mut cursor.state);
            }
            if !joint {
                s.remember(&g.program.iterative, rid,
                    &query_fact, |i| effects.get(i), effects.forwarded(),
                    #[cfg(feature = "sparse-cells")] None, &mut self.stats);
            }
            s
        };
        self.pending_steps.push(Completion::new(step));
        #[cfg(feature = "sparse-cells")]
        if let Some((count, aliases, _)) = sealed {
            // begin_effects admitted only permanent Entry-owned tables without
            // visibility loss. No source Hide can target such a table; union
            // forwarding and final Entry selection still run at publication.
            self.install_delivery(rid, slot, _cell, joint);
            self.stats.cell_output_span_seals += 1;
            self.stats.cell_output_sealed_receipts += count as u64;
            self.stats.effect_outputs_reused += count as u64;
            self.stats.alias_effect_forwards += aliases as u64;
            self.stats.unmaterialized_anchor_keys += count as u64;
            self.stats.captured_anchors += count as u64;
            self.count_output_receipts(rid, count);
        }
        #[cfg(feature = "sparse-cells")]
        let remaining = self.outputs[rid].len() - sealed.map_or(0, |(count, _, _)| count);
        #[cfg(not(feature = "sparse-cells"))]
        let remaining = self.outputs[rid].len();
        for position in 0..remaining {
            #[cfg(feature = "sparse-cells")]
            let position = if let Some((_, _, aliases)) = sealed {
                if position < aliases {
                    self.stats.output_residual_dispatches += 1;
                    effects.output_frame().unwrap().query_output(position)
                } else {
                    // Boundaries already occupy a contiguous suffix. They
                    // need no per-output dispatch index or template lookup.
                    self.cell_output_widths[rid] + position - aliases
                }
            } else { position };
            self.stats.output_registrations += 1;
            let output = self.outputs[rid][position];
            let (i, table, source) = (output.operation, output.table, output.receipt_source);
            let receipt = if self.receipts { output.receipt(&query_fact, |op| effects.get(op)) } else { None };
            if receipt.is_some() {
                match source {
                    Some(Site::Query(_)) => self.stats.alias_query_forwards += 1,
                    Some(Site::Effect(_)) => self.stats.alias_effect_forwards += 1,
                    None => (),
                }
            }
            let publication = Publication {
                slot,
                receipt,
                #[cfg(feature = "iterative-bake")]
                output: i,
                #[cfg(feature = "spine-shapes")]
                source: crate::graph::FactRef {
                    cell: _cell,
                    op: i as u32,
                },
            };
            #[cfg(feature = "sparse-cells")]
            if self.compiled_commits
                && self.permanent[table]
                && !g.has_visibility_changes(table)
                && self.receipts
                && !self.audit_receipts
                && let Some(w) = receipt
            {
                self.capture_receipt(rid, slot, _cell, position, table, publication, w, effects.output_frame());
                // Single writes already evaluated their write key; only deferred
                // frame keys count as materialization avoided here.
                self.stats.unmaterialized_anchor_keys += u64::from(E::DEFERRED_KEYS);
                self.stats.captured_anchors += 1;
                continue;
            }
            let args = match &template.ops[i] {
                Op::Let(_, Call::Table(_), args) | Op::Set(_, args, _) => args,
                _ => unreachable!("validated Cell output"),
            };
            self.pending_anchors
                .push((table, key(args)?, publication));
            self.stats.captured_anchors += 1;
        }
        #[cfg(feature = "sparse-cells")]
        if joint {
            // Individual boundaries only read this frame. The permanent
            // prefix has no query aliases to fill, so raw RHS evidence remains
            // unchanged. Move it once after boundary registration is done.
            let prepared = effects.take_results(rid).unwrap();
            let CompletionPhase::Started(step) = &mut self.pending_steps[slot].phase else { unreachable!() };
            step.remember(&g.program.iterative, rid, |_| unreachable!(), |_| unreachable!(),
                effects.forwarded(), Some(prepared), &mut self.stats);
        }
        #[cfg(feature = "sparse-cells")]
        let publish = self.pending_steps[slot].delivery.is_some();
        #[cfg(not(feature = "sparse-cells"))]
        let publish = false;
        self.finish_effects_to(effects, publish.then_some(slot));
        self.stats.captured_contexts += 1;
        if let Some(clock) = clock { self.stats.capture_seconds += clock.elapsed().as_secs_f64(); }
        Ok(())
    }
    pub(crate) fn write_needs_key(
        &self,
        _table: usize,
        #[cfg(feature = "sparse-cells")] visibility_changed: bool,
    ) -> bool {
        #[cfg(feature = "sparse-cells")]
        { !(self.compiled_commits && self.permanent[_table] && !visibility_changed
            && self.receipts && !self.audit_receipts) }
        #[cfg(not(feature = "sparse-cells"))]
        { true }
    }
    /// A completed, unchanged single write can put its root source directly
    /// in the final Entry slot while the executor exclusively owns the RHS
    /// phase. No query may observe these slots until repair and source-order
    /// resolution finish. Live histories retain ordinary Cell completion.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn complete_absorbed_root(&mut self, g: &Graph, rid: usize, cell: u32,
        step: Started, write: &crate::row_kernel::Write, index: usize,
        entries: &mut crate::entry_schedule::Scheduler) -> Result<Option<Started>> {
        self.stats.absorbed_root_checks += 1;
        if !matches!(step, Started::Root { .. }) || !self.compiled_commits || !self.receipts
            || self.audit_receipts || !self.permanent[write.table]
            || g.has_visibility_changes(write.table) || !self.entry_owned_tables[write.table]
            || self.outputs[rid].len() != 1 || self.cell_output_widths[rid] != 1
            || self.outputs[rid][0].operation != write.op
            || self.outputs[rid][0].receipt_source.is_some()
            || g.program.iterative.root_has_state(rid, self.training.collect_pairs) {
            return Ok(Some(step));
        }
        let Started::Root { id, producer, epoch, set } = step else { unreachable!() };
        debug_assert_eq!(producer, rid);
        self.stats.completed_steps += 1;
        let published = Published {
            base: PublishedBase::Solo { id, producer, epoch, stage: set, root: OnceCell::new() },
            output: write.op,
            #[cfg(feature = "spine-shapes")]
            source: crate::graph::FactRef { cell, op: write.op as u32 },
        };
        #[cfg(not(feature = "spine-shapes"))]
        let _ = cell;
        entries.stage_absorbed_root(write.table, index, self.publication_order(self.pending_steps.len(), true), published)?;
        self.stats.absorbed_root_completions += 1;
        self.stats.captured_anchors += 1;
        Ok(None)
    }
    #[cfg(feature = "sparse-cells")]
    fn capture_receipt(&mut self, rid: usize, slot: usize, _cell: u32, position: usize,
        table: usize, publication: Publication, receipt: Dependency, mut effects: Option<&mut crate::cell::Effects>,
    ) {
        // Only the retained prefix belongs to final Entry delivery. A mixed
        // Cell's boundary outputs must not force its other results through the
        // receipt hash table. A frame which could not reserve that prefix still
        // uses exact boundary publication (including dynamic visibility loss).
        let width = self.cell_output_widths[rid];
        if position >= width || effects.as_ref().is_some_and(|e| !e.keeps_outputs()) {
            self.stats.direct_publication_hash_probes += 1;
            self.direct_publications.insert(receipt, (table, publication));
            return;
        }
        self.stats.cell_output_registrations += 1;
        // A lone actual function result needs no arena location. Its operation
        // and table are already fixed by the Cell output, and the Completion
        // retains its original producer, history and source order. Publication
        // still forwards and validates the receipt after repair.
        if width == 1 && effects.is_none()
            && let Dependency::Function(index) = receipt
            && let Ok(index) = u32::try_from(index)
        {
            debug_assert!(self.pending_steps[slot].delivery.is_none());
            self.pending_steps[slot].delivery = Some(Delivery {
                source: OutputSource::Function(index),
                #[cfg(feature = "spine-shapes")] cell: _cell,
            });
            self.stats.cell_output_spans += 1;
            self.stats.inline_function_receipts += 1;
            self.count_output_receipts(rid, 1);
            return;
        }
        if self.pending_steps[slot].delivery.is_none() {
            self.install_delivery(rid, slot, _cell, false);
            if effects.is_none() {
                let mut buffer = self.borrow_effect_buffer();
                let before = buffer.capacity();
                buffer.resize(width, None);
                let growth = buffer.capacity() - before;
                self.stats.effect_buffer_growths += u64::from(growth != 0);
                self.stats.effect_buffer_growth_bytes += (growth * std::mem::size_of::<Option<Dependency>>()) as u64;
                let OutputSource::Slots(results) = &mut self.pending_steps[slot].delivery.as_mut().unwrap().source else { unreachable!() };
                *results = buffer;
            }
        }
        if let Some(effects) = effects.as_mut() {
            if effects.retain_output(position, receipt) { self.stats.effect_output_copies += 1; }
            else { self.stats.effect_outputs_reused += 1; }
        } else {
            let OutputSource::Slots(results) = &mut self.pending_steps[slot].delivery.as_mut().unwrap().source else { unreachable!("owned Cell outputs") };
            results[position] = Some(receipt);
            self.stats.effect_output_copies += 1;
        }
        self.count_output_receipts(rid, 1);
    }
    #[cfg(feature = "sparse-cells")]
    fn install_delivery(&mut self, rid: usize, slot: usize, _cell: u32, joint: bool) {
        debug_assert!(self.pending_steps[slot].delivery.is_none());
        let width = self.cell_output_widths[rid];
        self.stats.cell_output_spans += 1;
        self.stats.cell_output_slots += width as u64;
        if !joint {
            self.stats.peak_cell_output_slots = self.stats.peak_cell_output_slots.max(self.cell_outputs_pending + width);
        }
        self.stats.joint_output_mask_writes += u64::from(joint);
        let delivery = Delivery::new(width, joint, _cell);
        self.pending_steps[slot].delivery = Some(delivery);
    }
    #[cfg(feature = "sparse-cells")]
    fn count_output_receipts(&mut self, rid: usize, count: usize) {
        self.cell_outputs_pending += count;
        self.stats.cell_output_receipts += count as u64;
        // Preserve the historical multi-output coverage metric as a subset of
        // common Cell output delivery, without maintaining a fragment packet.
        if self.outputs[rid].len() >= 2 {
            self.stats.fragment_receipts += count as u64;
            self.stats.fragment_direct_inserts_avoided += count as u64;
        }
    }
    fn materialize_publication(&mut self, _g: &Graph, publication: Publication) -> Published {
        let slot = publication.slot;
        #[cfg(feature = "sparse-cells")]
        let cursor = {
            let phase = &mut self.pending_steps[slot].phase;
            if !matches!(phase, CompletionPhase::Published(_)) {
                let CompletionPhase::Started(started) = std::mem::replace(phase, CompletionPhase::Moving) else {
                    unreachable!("Cell completion promotion");
                };
                let base = match started {
                    Started::Root { id, producer, epoch, set } if self.outputs[producer].len() == 1 => {
                        self.stats.deferred_single_roots += 1;
                        PublishedBase::Solo { id, producer, epoch, stage: set, root: OnceCell::new() }
                    }
                    Started::Root { id, producer, epoch, set } => {
                        self.stats.root_handles_created += 1;
                        PublishedBase::Root(Rc::new(Root { id, epoch, set, context: OnceCell::new() }), producer)
                    }
                    Started::Live(mut c) => {
                        if !c.state.history.is_empty() && !_g.receipt_forwards.is_empty() {
                            self.stats.history_seal_checks += 1;
                            if let Some((reads, writes)) = c.state.history.seal_current(|w| _g.resolve_receipt(w)) {
                                self.stats.history_seal_reads += reads as u64;
                                self.stats.history_seal_writes += writes as u64;
                            } else { self.stats.history_seal_shared += 1; }
                        }
                        self.stats.completion_cursor_moves += 1;
                        PublishedBase::Active(Rc::new(c))
                    }
                };
                *phase = CompletionPhase::Published(base);
            }
            let CompletionPhase::Published(base) = phase else { unreachable!() };
            Published {
                base: base.clone(),
                output: publication.output,
                #[cfg(feature = "spine-shapes")]
                source: publication.source,
            }
        };
        #[cfg(not(feature = "sparse-cells"))]
        let cursor = {
            let cursor = self.pending_steps[slot].started.cursor(&mut self.stats).clone();
            #[cfg(feature = "spine-shapes")]
            let cursor = {
                let mut cursor = cursor;
                cursor.trace.source = Some(publication.source);
                cursor
            };
            #[cfg(feature = "iterative-bake")]
            let cursor = {
                let mut c = cursor;
                c.state.output = publication.output;
                c
            };
            cursor
        };
        self.stats.anchor_publications += 1;
        cursor
    }
    fn install_anchor(&mut self, g: &Graph, w: Dependency, table: usize, publication: Publication) {
        #[cfg(feature = "sparse-cells")]
        if self.entry_owned_tables[table] {
            // Link normalized boundary exports to their source Cell. The short
            // list orders only this Cell's own outputs, never its consumers.
            let slot = publication.slot;
            let mut previous = None;
            let mut next = self.pending_steps[slot].ready;
            while let Some(i) = next {
                self.stats.completion_order_checks += 1;
                if self.ready_publications[i.get() - 1].publication.order() <= publication.order() { break; }
                previous = Some(i);
                next = self.ready_publications[i.get() - 1].next;
            }
            let id = std::num::NonZeroUsize::new(self.ready_publications.len() + 1).expect("Cell export index");
            self.ready_publications.push(ReadyPublication { table, witness: w, publication, next });
            if let Some(i) = previous { self.ready_publications[i.get() - 1].next = Some(id); }
            else { self.pending_steps[slot].ready = Some(id); }
            self.stats.completion_boundary_records += 1;
            return;
        }
        let cursor = self.materialize_publication(g, publication);
        self.stats.legacy_entry_writes += 1;
        if self.entries.insert(w, cursor).is_none() {
            if self.active_tables[table] == 0 {
                for &rid in &self.table_readers[table] { self.live_inputs[rid] += 1; }
            }
            self.active_tables[table] += 1;
        }
    }
    #[cfg(feature = "sparse-cells")]
    fn finish_boundary(&mut self, g: &Graph, slot: usize, entries: &mut crate::entry_schedule::Scheduler) -> Result<()> {
        let id = self.pending_steps[slot].ready.expect("ready Cell export");
        let record = self.ready_publications[id.get() - 1];
        self.pending_steps[slot].ready = record.next;
        self.stats.completion_boundary_reads += 1;
        if entries.install_publication(record.table, record.witness, self.publication_order(slot, false),
            0, record.publication.output, || Ok(self.materialize_publication(g, record.publication)))?.is_none() {
            // Normalized boundary keys were counted before their receipts were
            // resolved. A later fragment can already own this same final key.
            self.stats.distinct_anchor_keys -= 1;
        }
        Ok(())
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn settled(&self)->bool {
        self.pending_steps.is_empty() && self.pending_anchors.is_empty()
            && self.ready_publications.is_empty() && self.direct_publications.is_empty()
            && self.cell_outputs_pending == 0
            && self.sealed_cursors.is_empty() && self.origin_rules.is_empty()
            && self.capture_unions.is_none() && self.entry_cache.is_empty() && self.row_cache.is_empty()
    }
    pub fn publish(&mut self, g: &mut Graph) -> Result<()> {
        self.publish_impl(g, #[cfg(feature = "sparse-cells")] None, None)
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn publish_to_entries(&mut self, g: &mut Graph, entries: &mut crate::entry_schedule::Scheduler) -> Result<()> {
        self.publish_impl(g, Some(entries), None)
    }
    pub(crate) fn pending_publication_counts(&self) -> (usize, usize) {
        let anchors = self.pending_anchors.len();
        #[cfg(feature = "sparse-cells")]
        let anchors = anchors + self.direct_publications.len() + self.cell_outputs_pending;
        (anchors, self.pending_steps.len())
    }
    pub(crate) fn publish_selected(&mut self, g: &mut Graph,
        #[cfg(feature = "sparse-cells")] entries: &mut crate::entry_schedule::Scheduler,
        ready: &[bool],
    ) -> Result<()> {
        self.publish_impl(g, #[cfg(feature = "sparse-cells")] Some(entries), Some(ready))
    }
    fn publish_impl(&mut self, g: &mut Graph,
        #[cfg(feature = "sparse-cells")] mut entries: Option<&mut crate::entry_schedule::Scheduler>,
        ready: Option<&[bool]>,
    ) -> Result<()> {
        if !self.enabled {
            return Ok(());
        };
        let clock = Instant::now();
        #[cfg(feature = "sparse-cells")]
        if let Some(entries) = entries.as_deref_mut() {
            entries.resolve_staged_roots(g)?;
        }
        // Removed/coalesced anchors are not reusable. Other stale ports are
        // refreshed by exact keys when their legal consumer stage arrives.
        for (t, changes) in g.changes.tables() {
            #[cfg(feature = "sparse-cells")]
            if self.entry_owned_tables[t] { continue; }
            if self.active_tables[t] == 0 { continue; }
            for w in changes.keys() {
                self.stats.legacy_retirement_checks += 1;
                let live = match *w {
                    Dependency::Fact(f) => g
                        .cells
                        .get(&f.cell)
                        .and_then(|c| c.facts.get(&f.op))
                        .is_some_and(|f| !f.hidden),
                    Dependency::Function(i) => g.functions.get(i).is_some_and(|f| f.live),
                };
                if live {
                    continue;
                }
                if self.entries.remove(w).is_some() {
                    self.stats.anchors_retired += 1;
                    let n = &mut self.active_tables[t];
                    *n -= 1;
                    if *n == 0 {
                        for &rid in &self.table_readers[t] {
                            self.live_inputs[rid] -= 1;
                        }
                        break;
                    }
                }
            }
        }
        // Unions can merge different keys after capture. Preserve the last
        // producer in original RHS order at the post-repair canonical key.
        let mut anchors = HashMap::default();
        let recanonicalize = self
            .capture_unions
            .is_some_and(|before| before != g.stats.unions);
        if ready.is_some() { self.stats.scoped_anchor_checks += self.pending_anchors.len() as u64; }
        for (table, mut key, publication) in self.pending_anchors.extract_if(.., |(t, _, _)| ready.is_none_or(|r| r[*t])) {
            if recanonicalize {
                for value in &mut key {
                    *value = canon(value, &g.parents);
                }
            }
            anchors.insert((table, key), publication);
        }
        self.stats.distinct_anchor_keys += anchors.len() as u64;
        #[cfg(feature = "sparse-cells")]
        if !self.direct_publications.is_empty() {
            for &old in g.receipt_forwards.keys() {
                if let Some(ready) = ready {
                    self.stats.scoped_receipt_checks += 1;
                    self.stats.direct_publication_hash_probes += 1;
                    if self.direct_publications.get(&old).is_some_and(|(t, _)| !ready[*t]) { continue; }
                }
                self.stats.direct_publication_hash_probes += 1;
                if let Some(incoming) = self.direct_publications.remove(&old) {
                    let target = g.resolve_receipt(old);
                    self.stats.direct_publication_hash_probes += 1;
                    match self.direct_publications.entry(target) {
                        std::collections::hash_map::Entry::Vacant(e) => {
                            e.insert(incoming);
                        }
                        std::collections::hash_map::Entry::Occupied(mut e) => {
                            if incoming.1.order() > e.get().1.order() {
                                e.insert(incoming);
                            }
                        }
                    }
                }
            }
        }
        #[cfg(feature = "sparse-cells")]
        {
            self.stats.distinct_anchor_keys += if let Some(ready) = ready {
                self.stats.scoped_direct_checks += self.direct_publications.len() as u64;
                self.direct_publications.values().filter(|(t, _)| ready[*t]).count()
            } else { self.direct_publications.len() } as u64;
        }
        let hits_before = self.stats.receipt_hits;
        for ((table, key), publication) in anchors {
            let receipt = publication.receipt;
            let mut witness = None;
            if self.receipts {
                if let Some(old) = receipt {
                    self.stats.receipt_attempts += 1;
                    let w = g.resolve_receipt(old);
                    self.stats.receipt_redirects += u64::from(w != old);
                    if g.receipt_visible(w, table) {
                        if self.audit_receipts {
                            self.stats.receipt_decodes += 1;
                            if g.row(w)?.is_none_or(|r| {
                                r.hidden || r.table != table || r.values[..key.len()] != key
                            }) {
                                return Err(
                                    "commit receipt does not preserve its source key".into()
                                );
                            }
                        }
                        self.stats.receipt_hits += 1;
                        witness = Some(w);
                    } else {
                        self.stats.receipt_rejections += 1;
                    }
                } else {
                    self.stats.receipt_missing += 1;
                }
            }
            if witness.is_none() {
                self.stats.capture_reads += 1;
                witness = g
                    .lookup(table, &key)?
                    .filter(|r| !r.hidden)
                    .map(|r| r.witness);
            }
            if let Some(w) = witness {
                #[cfg(feature = "sparse-cells")]
                if !self.direct_publications.is_empty() {
                    self.stats.direct_publication_hash_probes += 1;
                    if let Some((_, direct)) = self.direct_publications.get(&w) {
                        self.stats.distinct_anchor_keys -= 1;
                        if direct.order() > publication.order() {
                            continue;
                        }
                        self.stats.direct_publication_hash_probes += 1;
                        self.direct_publications.remove(&w);
                    }
                }
                self.install_anchor(g, w, table, publication);
            } else {
                self.stats.missing_capture_rows += 1;
            }
        }
        #[cfg(feature = "sparse-cells")]
        {
            let mut resolved = std::mem::take(&mut self.direct_publications);
            if ready.is_some() { self.stats.scoped_direct_checks += resolved.len() as u64; }
            for (w, (table, p)) in resolved.extract_if(|_, (t, _)| ready.is_none_or(|r| r[*t])) {
                // All subsume/delete producers and initially hidden rows were
                // excluded. Only same-key repair forwarding can move a receipt.
                if !g.receipt_visible(w, table) {
                    return Err("permanent producer receipt lost visibility".into());
                }
                self.stats.receipt_attempts += 1;
                self.stats.receipt_hits += 1;
                self.stats.receipt_redirects += u64::from(p.receipt != Some(w));
                self.install_anchor(g, w, table, p);
            }
            self.direct_publications = resolved;
        }
        #[cfg(feature = "sparse-cells")]
        if let Some(entries) = entries.as_deref_mut() {
            if !self.ready_publications.is_empty() || self.cell_outputs_pending != 0 {
                // Source Cells and their shared output positions are in capture
                // order. Reverse traversal sees the final Entry winner first.
                for slot in (0..self.pending_steps.len()).rev() {
                    self.stats.completion_cell_visits += 1;
                    if let Some(mut delivery) = self.pending_steps[slot].delivery.take() {
                        let mut pending = false;
                        let rule = self.pending_steps[slot].producer();
                        let width = self.cell_output_widths[rule];
                        let fragment = self.outputs[rule].len() >= 2;
                        for position in (0..width).rev() {
                            let old = match &delivery.source {
                                OutputSource::History(mask) => {
                                    self.stats.cell_output_slot_reads += 1;
                                    self.stats.joint_output_mask_checks += 1;
                                    if *mask & (1 << position) == 0 { continue; }
                                    self.stats.joint_output_reads += 1;
                                    let port = self.effect_plans[rule].get().unwrap().history_output(position);
                                    self.pending_steps[slot].results().output(port)
                                }
                                OutputSource::Slots(results) => {
                                    self.stats.cell_output_slot_reads += 1;
                                    results[position]
                                }
                                OutputSource::Function(index) => {
                                    debug_assert_eq!(width, 1);
                                    self.stats.inline_function_reads += 1;
                                    Some(Dependency::Function(*index as usize))
                                }
                            };
                            let Some(old) = old else { continue };
                            let output = self.outputs[rule][position];
                            let table = output.table;
                            self.stats.cell_output_checks += 1;
                            if fragment { self.stats.fragment_delivery_checks += 1; }
                            if ready.is_some_and(|r| !r[table]) { pending = true; continue; }
                            while self.pending_steps[slot].ready.is_some_and(|i| self.ready_publications[i.get() - 1].publication.output > output.operation) {
                                self.finish_boundary(g, slot, entries)?;
                            }
                            let w = g.resolve_receipt(old);
                            let publication = Publication {
                                slot, receipt: Some(old), output: output.operation,
                                #[cfg(feature = "spine-shapes")]
                                source: crate::graph::FactRef { cell: delivery.cell, op: output.operation as u32 },
                            };
                            let installed = entries.install_publication(table, w, self.publication_order(slot, false),
                                0, output.operation, || {
                                self.stats.receipt_attempts += 1;
                                if !g.receipt_visible(w, table) {
                                    return Err("permanent Cell output lost visibility".into());
                                }
                                self.stats.receipt_hits += 1;
                                Ok(self.materialize_publication(g, publication))
                            })?.is_some();
                            self.stats.distinct_anchor_keys += u64::from(installed);
                            self.stats.cell_output_deliveries += 1;
                            if fragment { self.stats.fragment_deliveries += 1; }
                            // Resolution still runs for every delivered output,
                            // even when its final Entry already has a winner.
                            self.stats.receipt_redirects += u64::from(w != old);
                            match &mut delivery.source {
                                OutputSource::History(mask) => {
                                    *mask &= !(1 << position);
                                    self.stats.joint_output_mask_writes += 1;
                                }
                                OutputSource::Slots(results) => results[position] = None,
                                OutputSource::Function(_) => (),
                            }
                            self.cell_outputs_pending -= 1;
                        }
                        if pending { self.pending_steps[slot].delivery = Some(delivery); }
                        else if let OutputSource::Slots(results) = delivery.source { self.recycle_effect_buffer(results); }
                    }
                    while self.pending_steps[slot].ready.is_some() { self.finish_boundary(g, slot, entries)?; }
                }
                self.ready_publications.clear();
            }
            let winners = entries.finish_staged_roots();
            self.stats.anchor_publications += winners;
            self.stats.deferred_single_roots += winners;
            self.stats.receipt_attempts += winners;
            self.stats.receipt_hits += winners;
            self.stats.distinct_anchor_keys += winners;
        }
        let hits = self.stats.receipt_hits - hits_before;
        if hits > 0 {
            *self
                .stats
                .receipt_hits_by_source
                .entry("effect".into())
                .or_default() += hits;
        }
        // A deferred publication retains its own results. New source Runs append
        // contexts without borrowing or relocating those live buffers.
        if self.pending_publication_counts().0 == 0 {
            #[cfg(feature = "sparse-cells")]
            { self.publication_base = self.publication_base.checked_add(self.pending_steps.len() as u64)
                .expect("Cell publication order exhausted"); }
            self.pending_steps.clear();
            self.capture_unions = None;
        }
        if !self.retain_matched_origins {
            #[cfg(all(feature = "iterative-bake", feature = "sparse-cells"))]
            self.sealed_cursors.clear();
            for rid in self.origin_rules.drain(..) {
                self.origins[rid].clear();
            }
        }
        self.entry_cache.clear();
        self.row_cache.clear();
        self.stats.publication_seconds += clock.elapsed().as_secs_f64();
        Ok(())
    }
    /// Bindings already returned by matching still own these cursors while an
    /// independent old region completes before their RHS starts.
    pub(crate) fn retain_matched_origins(&mut self, retain: bool) {
        self.retain_matched_origins = retain;
    }
    pub(crate) fn matched_origin_slots(&self) -> usize {
        let n = self.origin_rules.iter().map(|&r|self.origins[r].len()).sum::<usize>();
        #[cfg(all(feature = "iterative-bake", feature = "sparse-cells"))]
        let n = n + self.sealed_cursors.len();
        n
    }
    pub(crate) fn answers(
        &mut self,
        g: &mut Graph,
        rid: usize,
        pending: &BTreeSet<Dependency>,
        watermark: u64,
        facts: &QueryFacts,
        #[cfg(feature = "sparse-cells")] workers: Option<&mut crate::executor::query_workers::Workers>,
    ) -> Result<Option<Coverage>> {
        if !self.active_for_rule(rid) {
            return Ok(None);
        }
        let clock = Instant::now();
        let result = self.answers_inner(g, rid, pending, watermark, facts,
            #[cfg(feature = "sparse-cells")] workers);
        self.stats.query_seconds += clock.elapsed().as_secs_f64();
        result
    }
    fn answers_inner(
        &mut self,
        g: &mut Graph,
        rid: usize,
        pending: &BTreeSet<Dependency>,
        watermark: u64,
        facts: &QueryFacts,
        #[cfg(feature = "sparse-cells")] workers: Option<&mut crate::executor::query_workers::Workers>,
    ) -> Result<Option<Coverage>> {
        self.stats.query_attempts += 1;
        self.prepare_epoch(g.epoch);
        let shared = self.shared();
        let rule = g.program.rules[rid].clone();
        let mut ready = vec![];
        let mut covered = BTreeSet::new();
        let mut complete = true;
        for &w in pending {
            // Partial dispatch uses witness identity/table headers, not a second
            // candidate decode for every entry that ordinary matching must read.
            let mut eligible = BTreeSet::new();
            if self.partial {
                self.stats.dispatch_headers += 1;
                let Some(t) = g.live_table(w) else { continue };
                for (pivot, a) in rule.query.iter().enumerate() {
                    if !matches!(a.call, Call::Table(table) if table == t) {
                        continue;
                    }
                    if self.entries.contains_key(&w) && self.queries.get(rid, pivot).is_some() {
                        eligible.insert(pivot);
                    } else {
                        self.record_fallbacks(rid, pivot, 1);
                        if complete {
                            self.stats.uncovered_queries += 1;
                        }
                        complete = false;
                    }
                }
                if eligible.is_empty() {
                    continue;
                }
            }
            let row = if shared {
                self.seed_row(g, w)?
            } else {
                self.stats.delta_rows_examined += 1;
                g.stats.decoded_rows += 1;
                g.row(w)?.map(Rc::new)
            };
            let Some(row) = row else { continue };
            if row.hidden || row.epoch < watermark {
                continue;
            }
            for (pivot, a) in rule.query.iter().enumerate() {
                if !matches!(a.call,Call::Table(t) if t==row.table)
                    || (self.partial && !eligible.contains(&pivot))
                {
                    continue;
                }
                let mut input = Inputs::owned(g.program.templates[rule.template].sorts.len());
                // A failed literal/alias bind proves this exact entry empty too.
                // Only partial mode needs to mark it for residual dispatch.
                if self.partial {
                    covered.insert((pivot, w));
                }
                let live = if shared {
                    self.bind_seed(g, rid, pivot, &row, input.owned_mut())
                } else {
                    self.stats.pivot_candidates += 1;
                    a.args
                        .iter()
                        .zip(row.values.iter())
                        .all(|(a, v)| bind(a, v, &mut input, g))
                };
                if !live {
                    continue;
                }
                let Some(cursor) = self
                    .entries
                    .get(&w)
                    .filter(|_| self.queries.get(rid, pivot).is_some())
                    .map(Published::expand)
                else {
                    self.record_fallbacks(rid, pivot, 1);
                    self.stats.uncovered_queries += 1;
                    return Ok(None);
                };
                ready.push((pivot, row.clone(), cursor));
                covered.insert((pivot, w));
            }
        }
        let covered_count = if complete { ready.len() } else { covered.len() };
        self.finish_answers(
            g,
            rid,
            ready.into_iter(),
            covered,
            covered_count,
            complete,
            watermark,
            facts,
            #[cfg(feature = "sparse-cells")] workers,
        )
    }
    #[cfg(feature = "family-survey")]
    pub(crate) fn survey_resumed(&self) -> u64 {
        self.stats.resumed_steps
    }
    pub(crate) fn active_for_rule(&self, rid: usize) -> bool {
        self.enabled && self.live_inputs[rid] != 0
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn configure_entry_owners(&mut self, scheduler: &mut crate::entry_schedule::Scheduler, excluded: impl Fn(usize) -> bool) {
        self.entry_owned_tables = scheduler.own_publications(|t| self.enabled && !self.table_readers[t].is_empty() && !excluded(t));
        self.entry_owned_ids = self.entry_owned_tables.iter().enumerate().filter_map(|(t, &owned)| owned.then_some(t)).collect();
        for (rid, outputs) in self.outputs.iter_mut().enumerate() {
            self.cell_output_widths[rid] = crate::cell::Output::prepare(outputs,
                |table| self.permanent[table] && self.entry_owned_tables[table]);
            self.effect_plans[rid].take();
            #[cfg(feature = "structural-depth")]
            self.full_effect_plans[rid].take();
        }
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn refresh_entry_owners(&mut self, scheduler: &crate::entry_schedule::Scheduler) {
        for &table in &self.entry_owned_ids {
                let count = scheduler.publication_count(table);
                if (count != 0) != (self.active_tables[table] != 0) {
                    for &rid in &self.table_readers[table] {
                        if count == 0 { self.live_inputs[rid] -= 1; }
                        else { self.live_inputs[rid] += 1; }
                    }
                }
                self.active_tables[table] = count;
        }
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn entry_owns(&self, rid: usize, pivot: usize, table: usize) -> bool {
        self.enabled && self.entry_owned_tables[table] && self.queries.get(rid, pivot).is_some()
    }

    /// A live cursor only owns this pivot if the compiler supplied an exhaustive
    /// functional-key order for it. Other witnesses of the same table can fall back.
    pub(crate) fn scheduled_cursors(
        &self,
        rid: usize,
        pivot: usize,
        table: usize,
    ) -> Option<&HashMap<Dependency, Published>> {
        (self.enabled
            && {
                #[cfg(feature = "sparse-cells")]
                { !self.entry_owned_tables[table] }
                #[cfg(not(feature = "sparse-cells"))]
                { true }
            }
            && self.active_tables[table] != 0
            && self.queries.get(rid, pivot).is_some())
        .then_some(&self.entries)
    }

    pub(crate) fn answers_routed(
        &mut self,
        g: &mut Graph,
        rid: usize,
        scheduled_count: usize,
        mut routes: Vec<(usize, Rc<Row>, Cursor)>,
        watermark: u64,
        facts: &QueryFacts,
        #[cfg(feature = "sparse-cells")] workers: Option<&mut crate::executor::query_workers::Workers>,
    ) -> Result<Option<Coverage>> {
        let detached = crate::entry_schedule::DETACH_CELL_ENTRIES;
        let residual_count = if detached { scheduled_count } else { scheduled_count - routes.len() };
        self.stats.routed_spine_seeds += routes.len() as u64;
        self.stats.routed_matcher_seeds += residual_count as u64;
        if !self.active_for_rule(rid) {
            if detached && !routes.is_empty() { return Err("detached Cell Entry lost its query owner".into()); }
            return Ok(None);
        }
        self.stats.query_attempts += 1;
        if routes.is_empty() {
            self.stats.uncovered_queries += u64::from(residual_count != 0);
            return Ok(None);
        }
        let clock = Instant::now();
        let complete = residual_count == 0;
        if !complete {
            self.stats.mixed_routed_queries += 1;
            self.stats.uncovered_queries += 1;
        }
        // Equal-depth continuations retain the original witness/atom tie break.
        routes.sort_unstable_by_key(|(pivot, row, _)| (row.witness, *pivot));
        let mut covered = BTreeSet::new();
        // Partitioned inputs cannot enumerate these Entries again. Only a
        // survey's retained full Seed stream needs a coverage exclusion set.
        if !complete && !detached {
            covered.extend(routes.iter().map(|(pivot, row, _)| (*pivot, row.witness)));
        }
        let covered_count = routes.len();
        let result = self.finish_answers(g, rid, routes.into_iter(), covered, covered_count, complete, watermark, facts,
            #[cfg(feature = "sparse-cells")] workers);
        self.stats.query_seconds += clock.elapsed().as_secs_f64();
        result
    }
    fn finish_answers(
        &mut self,
        g: &mut Graph,
        rid: usize,
        ready: impl ExactSizeIterator<Item = (usize, Rc<Row>, Cursor)>,
        covered: BTreeSet<(usize, Dependency)>,
        covered_count: usize,
        complete: bool,
        watermark: u64,
        facts: &QueryFacts,
        #[cfg(feature = "sparse-cells")] workers: Option<&mut crate::executor::query_workers::Workers>,
    ) -> Result<Option<Coverage>> {
        if !complete && covered_count == 0 {
            return Ok(None);
        }
        #[cfg(feature = "sparse-cells")]
        let mut results = std::mem::take(&mut self.answer_scratch);
        #[cfg(not(feature = "sparse-cells"))]
        let mut results = Winners::new();
        #[cfg(feature = "sparse-cells")]
        let mut workers = workers.and_then(|w| if w.admit_spine_rule(g, rid) { Some(w) } else { None });
        #[cfg(feature = "sparse-cells")]
        let preparation_operation = {
            self.stats.preparation_handoff_rule_checks += 1;
            g.program.executions[rid].constructor.as_ref()
                .filter(|plan| plan.handoff).map(|plan| plan.operation)
        };
        'answer: for (_ordinal, (pivot, row, cursor)) in ready.into_iter().enumerate() {
            let mut epoch = row.epoch;
            let mut local = if self.local_witness_entries[rid][pivot] {
                #[cfg(feature = "iterative-bake")]
                let published = Some((g.program.rules[cursor.producer].template, cursor.state.output));
                #[cfg(not(feature = "iterative-bake"))]
                let published: Option<(usize, usize)> = None;
                let mut producer = crate::cell::Producer::new(row.witness, published);
                producer.address(g, &mut self.stats.local_witness_contexts).and_then(|(template, output)| {
                    self.stats.local_witness_route_probes += 1;
                    let (route, indexed, comparisons) = g.program.multi_stage.routes
                        .lookup(&(template, output, rid, pivot));
                    self.stats.local_witness_route_index_probes += indexed;
                    self.stats.local_witness_route_comparisons += comparisons;
                    let route = route?.clone();
                    self.stats.local_witness_routes += 1;
                    Some(LocalWitness {
                        producer,
                        route,
                    })
                })
            } else { None };
            #[cfg(feature = "spine-shapes")]
            let cursor = {
                let mut c = cursor;
                c.trace.pivot = pivot;
                c.trace.same_fact = c.trace.source.map(Dependency::Fact) == Some(row.witness);
                c
            };
            #[cfg(feature = "spine-blocks")]
            let mut cursor = cursor;
            #[cfg(feature = "iterative-bake")]
            let mut displaced_history = crate::result_handoff::History::default();
            #[cfg(feature = "spine-blocks")]
            {
                #[cfg(feature = "iterative-bake")]
                let selected = if g.program.iterative.enabled() {
                    cursor.state.collect_pairs = self.training.collect_pairs;
                    let (selected, previous) = g.program.iterative.dispatch(
                        &mut cursor.state, rid, pivot, complete, row.witness);
                    // No local witness consumer: release the old history at
                    // dispatch as before, without extending its lifetime.
                    if local.is_some() { displaced_history = previous; }
                    selected
                } else { g.program.spine_blocks.contains(rid, pivot) };
                #[cfg(not(feature = "iterative-bake"))]
                let selected = g.program.spine_blocks.contains(rid, pivot);
                // Selection credits retain their original meaning. Compilation
                // alone does not authorize a composed cross-stage continuation.
                cursor.via_block = selected;
                self.stats.block_entries += u64::from(selected);
            }
            #[cfg(feature = "iterative-bake")]
            let local_results = if local.is_some() {
                // Dispatch keeps admitted history in the cursor, or moves it
                // here on reset. Either way, borrow its original result slots.
                displaced_history.current().or_else(|| cursor.state.history.current())
            } else { None };
            #[cfg(feature = "sparse-cells")]
            if let Some(workers) = workers.as_deref_mut()
                && let Some(code) = workers.spine_entry(rid, pivot, &cursor) {
                workers.enqueue_spine(g, code, _ordinal, watermark, row, cursor, facts);
                continue;
            }
            let query = self.queries.get(rid, pivot).expect("certified Cell Entry");
            self.stats.cell_query_entries += 1;
            let mut values = smallvec::SmallVec::<[Value; 4]>::new();
            // Keep rejected queries off the heap in the common short case. Only
            // successful matches materialize the requested Cell fact projection.
            let mut found_witnesses = smallvec::SmallVec::<[(usize, Dependency); 4]>::new();
            for (position, step) in query.steps.iter().enumerate() {
                self.stats.cell_query_steps += 1;
                let bound = step.bind::<PortKey>(|v| v.operand(g, |col| &row.values[col], &values, None));
                let result = bound.evaluate(|args| match &step.call {
                    Call::Table(table) => {
                        let Some(found) = read_port(
                            g, &cursor, step.atom, *table, args, &mut self.stats, local.as_mut(),
                            #[cfg(feature = "iterative-bake")]
                            local_results,
                            #[cfg(feature = "structural-depth")]
                            (&mut self.structural, row.witness),
                        )? else { return Ok(None); };
                        epoch = epoch.max(found.epoch);
                        found_witnesses.push((step.atom, found.witness));
                        Ok(Some(found.values.last().unwrap().clone()))
                    }
                    Call::Primitive(name, output) => {
                        self.stats.guards += 1;
                        if name.starts_with("cell-key-") { g.stats.key_operations += 1; }
                        value::primitive(name, &args, output, g.program.key_nodes())
                    }
                })?;
                let Some(result) = result else {
                    if matches!(step.call, Call::Primitive(..)) { self.stats.guard_rejections += 1; }
                    continue 'answer;
                };
                // Keep instruction-position addresses for any later output.
                // Trailing checks cannot introduce a StepResult and need no
                // storage; they still execute and reject exactly as before.
                if position < query.result_slots() {
                    self.stats.cell_query_result_writes += 1;
                    values.push(result);
                }
            }
            if epoch >= watermark {
                let inputs: crate::slots::Slots = g.program.rules[rid].inputs.iter().zip(&query.inputs)
                    .map(|(&slot, v)| (slot, v.read(g, |col| &row.values[col], &values, None))).collect();
                let facts = facts.with_rows(std::iter::once((pivot, row.witness))
                    .chain(found_witnesses));
                #[cfg(feature = "iterative-bake")]
                if cursor.via_block && cursor.state.direct {
                    self.training.seal_moves += query.inputs.len() as u64;
                }
                self.stats.query_fragment_frames += 1;
                self.stats.query_fragment_slots += inputs.len() as u64;
                self.stats.query_fragment_capacity_bytes += inputs.capacity_bytes() as u64;
                #[cfg(feature = "sparse-cells")]
                {
                    let mut answer = Matched::matched(inputs, facts, epoch);
                    if let Some(operation) = preparation_operation {
                        cursor.retain_constructor_handoff(&g.program.iterative, operation, &mut answer, &mut self.stats);
                    }
                    results.push(Winner::new(answer, cursor, _ordinal,
                        &mut self.sealed_cursors, &mut self.stats));
                }
                #[cfg(not(feature = "sparse-cells"))]
                record_answer(&mut results, inputs, facts, epoch, cursor);
            }
        }
        #[cfg(feature = "sparse-cells")]
        if workers.as_ref().is_some_and(|w| w.pending_rule(rid)) {
            // Keep each original winner/cursor once until every Cell in this
            // read-only Run has completed. No intermediate binding is sealed.
            debug_assert_eq!(self.deferred_slots[rid], usize::MAX);
            self.deferred_slots[rid] = self.deferred_queries.len();
            self.stats.deferred_group_growths += u64::from(self.deferred_queries.len() == self.deferred_queries.capacity());
            self.deferred_queries.push(DeferredQuery { rule: rid, complete, covered: covered_count, rows: results });
            self.stats.deferred_group_peak_bytes = self.stats.deferred_group_peak_bytes.max(
                (self.deferred_queries.capacity() * std::mem::size_of::<DeferredQuery>()) as u64);
            return Ok(Some(Coverage { complete, covered, claimed: covered_count, answers: Vec::new() }));
        }
        let answers = self.seal_answers(rid, &g.program.rules[rid].inputs, complete, covered_count, results);
        Ok(Some(Coverage {
            complete,
            covered,
            claimed: covered_count,
            answers,
        }))
    }
    fn seal_answers(&mut self, rid: usize, inputs: &[usize], complete: bool, covered_count: usize,
        mut results: Winners) -> Vec<Matched> {
        #[cfg(feature = "sparse-cells")]
        {
            self.stats.losing_cursor_releases += select_worker_winners(&mut results, inputs,
                &mut 0, &mut self.sealed_cursors) as u64;
        }
        #[cfg(feature = "sparse-cells")]
        let rows = results.drain(..);
        #[cfg(not(feature = "sparse-cells"))]
        let rows = results.into_iter().map(|(values, mut winner)| {
            winner.answer.values = values;
            winner
        });
        let answers = self.seal_winners(rid, inputs, complete, covered_count, rows);
        #[cfg(feature = "sparse-cells")]
        { self.answer_scratch = results; }
        answers
    }
    fn seal_winners(&mut self, rid: usize, inputs: &[usize], complete: bool, covered_count: usize,
        rows: impl ExactSizeIterator<Item = Winner>) -> Vec<Matched> {
        if complete { self.stats.query_takeovers += 1; }
        else { self.stats.partial_queries += 1; }
        self.stats.pivots_skipped += covered_count as u64;
        *self.stats.covered_by_rule.entry(rid).or_default() += covered_count as u64;
        self.stats.bindings += rows.len() as u64;
        *self.stats.bindings_by_rule.entry(rid).or_default() += rows.len() as u64;
        rows
            .map(|winner| {
                let mut answer = winner.answer;
                #[cfg(feature = "sparse-cells")]
                let cursor = self.sealed_cursors[answer.direct.as_ref().expect("candidate origin").0]
                    .as_ref().expect("retained candidate cursor");
                #[cfg(not(feature = "sparse-cells"))]
                let cursor = winner.cursor;
                self.stats.query_fragment_sealed_slots += answer.values.len() as u64;
                self.stats.query_fragment_sealed_capacity_bytes += answer.values.capacity_bytes() as u64;
                #[cfg(feature = "iterative-bake")]
                if cursor.state.direct || {
                    #[cfg(feature = "sparse-cells")]
                    { self.direct_sealed_answers }
                    #[cfg(not(feature = "sparse-cells"))]
                    { false }
                } {
                    // The executor appends residual matches after these winners.
                    // Stable sealing keeps the Spine binding on an equal RHS key.
                    // Unsealed continuations still resolve by key.
                    self.stats.sealed_partial_origins += u64::from(!complete);
                    #[cfg(not(feature = "sparse-cells"))]
                    { answer.direct = Some(DirectOrigin(Box::new(cursor))); }
                    return answer;
                }
                #[cfg(feature = "sparse-cells")]
                let cursor = take_origin(&mut self.sealed_cursors, answer.direct.take().unwrap());
                if self.origins[rid].is_empty() {
                    self.origin_rules.push(rid);
                }
                self.stats.origin_map_writes += 1;
                // Unsealed legacy origins still need an independently owned
                // lookup key. It does not replace the fragment's slot storage.
                self.origins[rid].insert(answer.input_values(inputs).cloned().collect(), cursor);
                answer
            })
            .collect()
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn deferred(&self, rid: usize) -> bool { self.deferred_slots[rid] != usize::MAX }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn deferred_frames(&mut self) -> impl Iterator<Item = (usize, &mut [Winner])> {
        self.deferred_queries.iter_mut().map(|q| (q.rule, q.rows.as_mut_slice()))
    }
    /// A failed source query cannot commit any of its accepted candidates.
    /// Release their origins as well as the candidate arrays, including roots
    /// already sealed by an earlier rule in this same read-only Run.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn discard_query_candidates(&mut self) {
        for q in self.deferred_queries.drain(..) { self.deferred_slots[q.rule] = usize::MAX; }
        self.stats.aborted_cursor_releases += self.sealed_cursors.iter().filter(|c|c.is_some()).count() as u64;
        self.sealed_cursors.clear();
        for rid in self.origin_rules.drain(..) { self.origins[rid].clear(); }
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn record_worker_answer(&mut self, rid: usize, ordinal: usize,
        answer: Matched, cursor: Cursor) {
        if cursor.via_block && cursor.state.direct {
            self.training.seal_moves += answer.values.len() as u64;
        }
        self.stats.query_fragment_frames += 1;
        self.stats.query_fragment_slots += answer.values.len() as u64;
        self.stats.query_fragment_capacity_bytes += answer.values.capacity_bytes() as u64;
        let winner = Winner::new(answer, cursor, ordinal, &mut self.sealed_cursors, &mut self.stats);
        self.deferred_queries[self.deferred_slots[rid]].rows.push(winner);
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn finish_worker_rule(&mut self, rid: usize, inputs: &[usize], order_comparisons: &mut u64) -> Option<(bool, Vec<Matched>)> {
        let slot = std::mem::replace(&mut self.deferred_slots[rid], usize::MAX);
        if slot == usize::MAX { return None; }
        let DeferredQuery { rule, complete, covered, mut rows } = self.deferred_queries.swap_remove(slot);
        debug_assert_eq!(rule, rid);
        if let Some(moved) = self.deferred_queries.get(slot) { self.deferred_slots[moved.rule] = slot; }
        self.stats.losing_cursor_releases += select_worker_winners(&mut rows, inputs,
            order_comparisons, &mut self.sealed_cursors) as u64;
        Some((complete, self.seal_winners(rid, inputs, complete, covered, rows.into_iter())))
    }
    pub fn shared(&self) -> bool {
        self.enabled && self.partial && self.shared_entries
    }
    fn prepare_epoch(&mut self, epoch: u64) {
        if self.cache_epoch != epoch {
            self.entry_cache.clear();
            self.row_cache.clear();
            self.cache_epoch = epoch;
        }
    }
    /// All source queries share one immutable LHS snapshot within this Run.
    pub fn seed_row(&mut self, g: &mut Graph, w: Dependency) -> Result<Option<Rc<Row>>> {
        self.prepare_epoch(g.epoch);
        if let Some(row) = self.row_cache.get(&w) {
            self.stats.shared_row_hits += 1;
            return Ok(row.clone());
        }
        self.stats.delta_rows_examined += 1;
        g.stats.decoded_rows += 1;
        let row = g.row(w)?.map(Rc::new);
        self.row_cache.insert(w, row.clone());
        Ok(row)
    }
    /// Exact alpha-equivalent anchor predicates can feed different residual
    /// recipes too. Reuse their checked fields, never an observed full answer.
    pub fn bind_seed(
        &mut self,
        g: &Graph,
        rid: usize,
        pivot: usize,
        row: &Row,
        input: &mut [Option<Value>],
    ) -> bool {
        self.prepare_epoch(g.epoch);
        *self.stats.entry_requests_by_rule.entry(rid).or_default() += 1;
        let (shape, projection) = &self.anchor_shapes[&(rid, pivot)];
        let key = (*shape, row.witness);
        if let Some((valid, last_rule)) = self.entry_cache.get_mut(&key) {
            self.stats.shared_entry_hits += 1;
            self.stats.shared_entry_cross_rule_hits += u64::from(*last_rule != rid);
            *last_rule = rid;
            if *valid {
                self.stats.entry_parameters_copied += projection.len() as u64;
                for &(slot, col) in projection {
                    input[slot] = Some(row.values[col].clone());
                }
            }
            *valid
        } else {
            self.stats.pivot_candidates += 1;
            *self.stats.entry_checks_by_rule.entry(rid).or_default() += 1;
            struct SeedInputs<'a> {
                values: &'a mut [Option<Value>],
                copied: &'a mut u64,
            }
            impl QueryFrame for SeedInputs<'_> {
                #[inline]
                fn slot(&self, slot: usize) -> Option<&Value> { self.values[slot].as_ref() }
                #[inline]
                fn bind_slot(&mut self, slot: usize, value: Value) {
                    *self.copied += 1;
                    self.values[slot] = Some(value);
                }
            }
            let mut frame = SeedInputs { values: input, copied: &mut self.stats.entry_parameters_copied };
            let valid = g.program.rules[rid].query[pivot]
                .args
                .iter()
                .zip(row.values.iter())
                .all(|(a, v)| bind(a, v, &mut frame, g));
            self.entry_cache.insert(key, (valid, rid));
            self.stats.peak_cached_entries =
                self.stats.peak_cached_entries.max(self.entry_cache.len());
            valid
        }
    }
    pub(crate) fn record_fallbacks(&mut self, rid: usize, pivot: usize, count: u64) {
        if count == 0 {
            return;
        }
        self.stats.fallback_pivots += count;
        *self.stats.fallback_by_rule.entry(rid).or_default() += count;
        if self.queries.get(rid, pivot).is_some() {
            self.stats.missing_context_pivots += count;
        } else {
            self.stats.unsupported_key_pivots += count;
        }
    }
    pub fn effects(&mut self, constructors: u64, updates: u64, unions: u64) {
        self.stats.constructor_requests += constructors;
        self.stats.function_updates += updates;
        self.stats.union_requests += unions;
    }
    #[cfg(feature = "spine-shapes")]
    pub fn shape_report(&self) -> J {
        self.shapes.report()
    }
    pub fn report(&self) -> J {
        self.report_with(std::iter::empty())
    }
    pub(crate) fn report_with<'a>(&'a self, extra: impl Iterator<Item = &'a Published>) -> J {
        let extra: Vec<_> = extra.collect();
        let contexts = self
            .entries
            .values()
            .chain(extra.iter().copied())
            .map(Published::root_info)
            .collect::<BTreeMap<_, _>>();
        let materialized = contexts
            .values()
            .filter_map(|root| root.and_then(|r| r.context.get()));
        let live_materialized = materialized.clone().count();
        let facts: usize = materialized.map(|c| c.borrow().facts.len()).sum();
        let effect_plan_cache_bytes = self.effect_plans.capacity() * std::mem::size_of::<OnceCell<Rc<crate::cell::EffectPlan>>>();
        #[cfg(feature = "structural-depth")]
        let effect_plan_cache_bytes = effect_plan_cache_bytes
            + self.full_effect_plans.capacity() * std::mem::size_of::<OnceCell<Rc<crate::cell::EffectPlan>>>();
        #[cfg(feature = "sparse-cells")]
        let candidate_storage = json!({"layout":"owned-origin/v2",
            "rule_slot_bytes":self.deferred_slots.capacity()*std::mem::size_of::<usize>(),
            "deferred_group_bytes":self.deferred_queries.capacity()*std::mem::size_of::<DeferredQuery>(),
            "cursor_capacity_bytes":self.sealed_cursors.capacity()*std::mem::size_of::<Option<Cursor>>(),
            "pending_groups":self.deferred_queries.len(),
            "pending_cursor_slots":self.sealed_cursors.len()});
        #[cfg(not(feature = "sparse-cells"))]
        let candidate_storage = J::Null;
        #[cfg(feature = "sparse-cells")]
        let pending_result_bytes = self.pending_steps.iter().filter_map(|c| match &c.delivery {
            Some(Delivery { source: OutputSource::Slots(results), .. }) => Some(results.capacity()),
            _ => None,
        }).sum::<usize>() * std::mem::size_of::<Option<Dependency>>();
        #[cfg(not(feature = "sparse-cells"))]
        let pending_result_bytes = 0;
        let report = json!({"output_registration":"owned-cell-outputs/v2",
            "owned_output_storage":{
                "pooled_buffers":self.effect_buffers.len(),
                "pool_header_bytes":self.effect_buffers.capacity()*std::mem::size_of::<Vec<Option<Dependency>>>(),
                "pooled_capacity_bytes":self.effect_buffers.iter().map(|b|b.capacity()).sum::<usize>()*std::mem::size_of::<Option<Dependency>>(),
                "pending_capacity_bytes":pending_result_bytes,
                "completion_capacity_bytes":self.pending_steps.capacity()*std::mem::size_of::<Completion>()},
            "query_candidate_storage":candidate_storage,
            "joint_result_storage":"cell-results/v1",
            "union_completion":"cell-union-ports/v1",
            "history_sealing":"unique-cell-results/v1",
            "completion_record_bytes":std::mem::size_of::<Completion>(),
            "joint_result_plan_bytes":self.effect_plans.iter().filter_map(|p|p.get()).map(|p|p.joint_bytes()).sum::<usize>(),
            "effect_plan_registration_bytes":self.effect_plans.iter().filter_map(|p|p.get()).map(|p|p.registration_bytes()).sum::<usize>(),
            "query_fragment_layout":"owned-instance/v1","query_winner_bytes":std::mem::size_of::<Winner>(),
            "query_fragment_header_bytes":std::mem::size_of::<Matched>(),
            "query_fragment_slot_bytes":std::mem::size_of::<(usize, Value)>(),
            "query_value_bytes":std::mem::size_of::<Value>(),
            "enabled":self.enabled,"receipts_enabled":self.receipts,"partial_enabled":self.partial,"shared_entries_enabled":self.shared_entries,"stats":self.stats,"producer_rules":self.outputs.iter().filter(|ops| !ops.is_empty()).count(),
            "effect_plan_slot_bytes":self.effect_plans.iter().filter_map(|p|p.get()).map(|p|p.slot_bytes()).sum::<usize>(),"effect_plan_cache_bytes":effect_plan_cache_bytes,"keyed_entries":self.queries.len(),"shared_query_plans":self.queries.shared(),"live_spines":contexts.len(),"live_materialized_contexts":live_materialized,
            "effect_plan_layout_bytes":self.effect_plans.iter().filter(|p|p.get().is_some()).count()
                * (std::mem::size_of::<crate::cell::EffectLayout>() + 2*std::mem::size_of::<usize>()),
            "entry_references":self.entries.len() + extra.len(),"legacy_entry_references":self.entries.len(),"node_entry_references":extra.len(),"context_fact_references":facts,
            "scope":"source-scheduled RHS continuation from committed producer contexts; exhaustive functional-key entries; unknown delta entries use ordinary matching; no early effect visibility"});
        #[cfg(feature = "iterative-bake")]
        let report = {
            let mut r = report;
            let mut storage = crate::result_handoff::HistoryStorage::default();
            let mut discovery = crate::iterative::DiscoveryStorage::default();
            for publication in self.entries.values().chain(extra.iter().copied()) {
                #[cfg(feature = "sparse-cells")]
                if let PublishedBase::Active(cursor) = &publication.base {
                    cursor.state.history.count_storage(&mut storage);
                    cursor.state.count_discovery(&mut discovery);
                }
                #[cfg(not(feature = "sparse-cells"))]
                {
                    publication.state.history.count_storage(&mut storage);
                    publication.state.count_discovery(&mut discovery);
                }
            }
            r["published_history_storage"] = serde_json::to_value(storage).unwrap();
            r["history_result_frame_bytes"] = std::mem::size_of::<crate::cell::Results>().into();
            r["history_handle_bytes"] = std::mem::size_of::<crate::result_handoff::History>().into();
            r["execution_state_bytes"] = std::mem::size_of::<crate::iterative::State>().into();
            r["published_discovery_storage"] = serde_json::to_value(discovery).unwrap();
            r["iterative_bake"] = self.training.report();
            r
        };
        report
    }
}

#[cfg(feature = "sparse-cells")]
impl Stats {
    pub(crate) fn record_query_worker(&mut self, counts: &crate::executor::query_workers::Counts) {
        self.cell_query_entries += counts.entries;
        self.cell_query_steps += counts.steps;
        self.cell_query_result_writes += counts.result_writes;
        self.guards += counts.guards;
        self.guard_rejections += counts.guard_rejections;
    }
}
