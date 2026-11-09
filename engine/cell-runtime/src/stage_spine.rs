//! Source-scheduled Cell programs. A committed producer supplies the next
//! stage's complete context; the stage consumes it without a structural join.
//! Coverage is proved from functional table keys, not from observed frequency.
use crate::{
    entry_schedule::{Inputs, Seed},
    graph::{Dependency, Graph, Row},
    cell::Site,
    known_results::QueryFacts,
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
    pub(crate) fn cell_results(&self) -> Option<(usize, usize, Option<&crate::cell::Results>)> {
        let PublishedBase::Active(c) = &self.base else { return None };
        Some((c.producer, self.output, c.state.history.current()))
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
    pub(crate) fn cell_results(&self) -> Option<(usize, usize, Option<&crate::cell::Results>)> {
        Some((self.producer, self.state.output, self.state.history.current()))
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
/// Address of this Cell's output slots in the pending arena. Port meanings and
/// order come from the shared Cell definition, including for single outputs.
#[cfg(feature = "sparse-cells")]
#[derive(Clone, Copy)]
struct Delivery {
    rule: std::num::NonZeroU32,
    first: u32,
    #[cfg(feature = "spine-shapes")]
    cell: u32,
}
#[cfg(feature = "sparse-cells")]
enum CompletionPhase {
    Started(Started),
    Published(PublishedBase),
    Moving,
}
impl Completion {
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
                back: r.back,
                fact: match c.state.history.get(r.back, r.port.expect("compiled Cell result port")) {
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
        stats: &mut Stats,
    ) {
        if cat.history_depth() == 0 {
            return;
        }
        if let Self::Live(c) = self {
            let work = c.state.history.capture(
                cat.history_depth(),
                rid,
                cat.capture_sources(&c.state),
                read,
                effect,
            );
            stats.history_capture_reads += work.reads as u64;
            stats.history_slots_written += work.slots as u64;
            stats.history_allocations += work.allocations as u64;
            stats.history_empty_slots_written += work.empty_slots as u64;
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
pub struct Answer {
    #[cfg(feature = "iterative-bake")]
    pub(crate) direct: Option<DirectOrigin>,

    pub values: Vec<Value>,
    pub witnesses: Vec<Option<Dependency>>,
    pub epoch: u64,
}
/// Exact entry coverage, independently usable from residual query completion.
pub struct Coverage {
    pub answers: Vec<Answer>,
    pub covered: BTreeSet<(usize, Dependency)>,
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
    #[test]
    fn serialization_includes_current_set_and_prior_occurrences() {
        let mut counts=SetCounts::default();
        for set in ["b","b","a","b"] { counts.add(set); }
        assert_eq!(json!(counts),json!({"a":1,"b":3}));
    }
}
#[derive(Default, Serialize)]
pub struct Stats {
    origin_key_slots: u64,
    origin_map_writes: u64,
    origin_map_probes: u64,
    history_capture_reads: u64,
    history_slots_written: u64,
    history_allocations: u64,
    history_empty_slots_written: u64,
    history_result_reads: u64,
    legacy_entry_writes: u64,
    legacy_retirement_checks: u64,
    pub(crate) legacy_cursor_probes: u64,
    pub(crate) node_cursor_reads: u64,
    root_attempts: u64,
    root_handles_created: u64,
    #[cfg(feature = "sparse-cells")]
    deferred_single_roots: u64,
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
    effect_aborted_frames: u64,
    cell_output_spans: u64,
    cell_output_slots: u64,
    cell_output_receipts: u64,
    cell_output_slot_reads: u64,
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
    pub(crate) compiled_commits: bool,
    #[cfg(feature = "sparse-cells")]
    permanent: Vec<bool>,
    #[cfg(feature = "sparse-cells")]
    direct_publications: HashMap<Dependency, (usize, Publication)>,
    #[cfg(feature = "sparse-cells")]
    cell_output_rules: Vec<bool>,
    #[cfg(feature = "sparse-cells")]
    cell_outputs_pending: usize,
    cell_outputs: Vec<Option<Dependency>>,
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
    // Sealed bindings own move-only indices into this Run's winning cursors.
    #[cfg(all(feature = "iterative-bake", feature = "sparse-cells"))]
    sealed_cursors: Vec<Option<Cursor>>,
    next_context: u64,

    #[cfg(feature = "sparse-cells")]
    answer_scratch: Winners,
    pub stats: Stats,
}
fn bind(a: &Arg, v: &Value, input: &mut Inputs, g: &Graph) -> bool {
    match a {
        Arg::Literal(x) => canon(x, &g.parents) == *v,
        Arg::Slot(i) => match input.get(*i) {
            Some(x) => x == v,
            None => {
                input.set(*i, Some(v.clone()));
                true
            }
        },
    }
}
#[cfg(feature = "sparse-cells")]
type Winners = Vec<(Vec<Value>, (Answer, Cursor))>;
#[cfg(not(feature = "sparse-cells"))]
type Winners = BTreeMap<Vec<Value>, (Answer, Cursor)>;
fn record_answer(
    results: &mut Winners,
    values: Vec<Value>,
    witnesses: Vec<Option<Dependency>>,
    epoch: u64,

    cursor: Cursor,
) {
    #[cfg(feature = "iterative-bake")]
    let direct = cursor.state.direct;
    #[cfg(not(feature = "iterative-bake"))]
    let direct = false;
    let candidate = (
        Answer {
            #[cfg(feature = "iterative-bake")]
            direct: None,

            values: if direct || cfg!(feature = "sparse-cells") {
                Vec::new()
            } else {
                values.clone()
            },
            witnesses,
            epoch,
        },
        cursor,
    );
    #[cfg(feature = "sparse-cells")]
    results.push((values, candidate));
    #[cfg(not(feature = "sparse-cells"))]
    match results.entry(values) {
        std::collections::btree_map::Entry::Vacant(e) => {
            e.insert(candidate);
        }
        std::collections::btree_map::Entry::Occupied(mut e) => {
            if candidate.1.depth > e.get().1.depth {
                e.insert(candidate);
            }
        }
    }
}
struct LocalWitness {
    context: Option<crate::graph::producer::Context>,
    route: Rc<crate::multistage::Continuation>,
    #[cfg(feature = "iterative-bake")]
    history: crate::result_handoff::History,
}
fn read_port(
    g: &mut Graph,
    cursor: &Cursor,
    _atom: usize,
    table: usize,
    args: PortKey,
    stats: &mut Stats,
    local: Option<&LocalWitness>,
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
        if let Some(w) = cursor.state.history.get(proof.back, proof.port.expect("compiled Cell result port")) {
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
            && let Some(source) = local.route.reads.iter().find(|read| {
                stats.local_witness_route_steps += 1;
                read.atom == _atom
            }).and_then(|r| r.witness)
        {
            stats.local_witness_reads += 1;
            // This is a current positive witness, never a cached value or a
            // negative lookup proof. Missing or retired receipts fall back.
            #[cfg(feature = "iterative-bake")]
            let receipt = if let Some(port) = source.port {
                stats.local_witness_receipt_probes += 1;
                stats.local_witness_slot_reads += 1;
                stats.history_result_reads += 1;
                local.history.get(1, port)
            } else { None };
            #[cfg(not(feature = "iterative-bake"))]
            let receipt = None;
            stats.local_witness_receipt_hits += u64::from(receipt.is_some());
            let mut reads = 0;
            row = g.context_witness_row(local.context, source.source, receipt, table, key.1.len() + 1,
                &mut stats.local_witness_misses, &mut reads)?.filter(|r| {
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
        seed: &Seed) -> Option<(usize, usize, Option<&'a crate::cell::Results>)> {
        #[cfg(feature = "sparse-cells")]
        if self.entry_owned_tables[seed.packet.row.table] {
            return entries.publication(seed)?.cell_results();
        }
        #[cfg(not(feature = "sparse-cells"))]
        let _ = entries;
        self.entries.get(&seed.packet.row.witness)?.cell_results()
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
                for (&(.., rid, pivot), route) in &p.multi_stage.routes {
                    entries[rid][pivot] |= route.reads.iter().any(|read| read.witness.is_some());
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
            pending_anchors: vec![],
            #[cfg(feature = "sparse-cells")]
            compiled_commits: false,
            #[cfg(feature = "sparse-cells")]
            permanent,
            #[cfg(feature = "sparse-cells")]
            direct_publications: Default::default(),
            #[cfg(feature = "sparse-cells")]
            cell_output_rules: vec![false; p.rules.len()],
            #[cfg(feature = "sparse-cells")]
            cell_outputs_pending: 0,
            cell_outputs: vec![],
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
        let supplied = direct.map(|token| self.sealed_cursors[token.0].take().expect("sealed Spine cursor"));
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
            #[cfg(feature = "iterative-bake")]
            self.training
                .applied(&p.iterative, &mut cursor.state, p.rules[rid].inputs.len());
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
    /// Lend the pending arena to one source RHS. Its suffix is private until
    /// complete seals it; matching and publication never run during this loan.
    pub(crate) fn begin_effects(&mut self, g: &Graph, rid: usize, full: bool, force: bool) -> crate::cell::Effects {
        if !force && !full && !self.capture_receipts(rid) { return Default::default(); }
        let outputs = self.outputs.get(rid).map_or(&[][..], Vec::as_slice);
        let plans = &self.effect_plans;
        #[cfg(feature = "structural-depth")]
        let plans = if full { &self.full_effect_plans } else { plans };
        let plan = plans[rid].get_or_init(|| Rc::new(crate::cell::EffectPlan::compile(&g.program, rid, outputs, full))).clone();
        #[cfg(feature = "sparse-cells")]
        let keep = self.compiled_commits && self.receipts && !self.audit_receipts
            && self.cell_output_rules[rid] && outputs.iter().all(|o| !g.has_visibility_changes(o.table));
        #[cfg(not(feature = "sparse-cells"))]
        let keep = false;
        crate::cell::Effects::begin(plan, std::mem::take(&mut self.cell_outputs), keep)
    }
    pub(crate) fn finish_effects(&mut self, effects: impl crate::cell::CompletedEffects, publish: bool) {
        if let Some((buffer, slots, probes, targets)) = effects.finish(publish) {
            debug_assert!(self.cell_outputs.is_empty(), "one executing Cell owns the output arena");
            self.cell_outputs = buffer;
            self.stats.effect_frames += 1;
            self.stats.effect_slots_initialized += slots as u64;
            self.stats.effect_slot_probes += probes;
            self.stats.effect_slot_targets += targets;
        }
    }
    pub(crate) fn abort_effects(&mut self, effects: crate::cell::Effects) {
        self.stats.effect_aborted_frames += 1;
        self.finish_effects(effects, false);
    }
    pub(crate) fn complete<E: crate::cell::CompletedEffects>(
        &mut self,
        g: &Graph,
        rid: usize,
        _cell: u32,
        step: Started,
        query_fact: impl Fn(usize) -> Option<Dependency>,
        effects: E,
        mut key: impl FnMut(&[Arg]) -> Result<Vec<Value>>,
    ) -> Result<()> {
        #[cfg(feature = "sparse-cells")]
        let mut effects = effects;
        self.stats.completed_steps += 1;
        if self.outputs.get(rid).is_none_or(Vec::is_empty) {
            self.finish_effects(effects, false);
            return Ok(());
        }
        let clock = E::DEFERRED_KEYS.then(Instant::now);
        let rule = &g.program.rules[rid];
        let template = &g.program.templates[rule.template];
        self.capture_unions.get_or_insert(g.stats.unions);
        let slot = self.pending_steps.len();
        #[cfg(feature = "iterative-bake")]
        let step = {
            let mut s = step;
            s.seed_root(
                &g.program.iterative,
                rid,
                self.training.run,
                self.training.collect_pairs,
                &mut self.stats,
            );
            s.remember(&g.program.iterative, rid,
                &query_fact, |i| effects.get(i), &mut self.stats);
            s
        };
        self.pending_steps.push(Completion::new(step));
        for position in 0..self.outputs[rid].len() {
            let output = self.outputs[rid][position];
            let (i, table, source) = (output.operation, output.table, output.receipt_source);
            let receipt = if self.receipts { effects.get(i).or_else(|| {
                match source? {
                    Site::Query(atom) => {
                        let w = query_fact(atom)?;
                        self.stats.alias_query_forwards += 1;
                        Some(w)
                    }
                    Site::Effect(op) => {
                        let w = effects.get(op)?;
                        self.stats.alias_effect_forwards += 1;
                        Some(w)
                    }
                }
            }) } else { None };
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
        let publish = self.pending_steps[slot].delivery.is_some();
        #[cfg(not(feature = "sparse-cells"))]
        let publish = false;
        self.finish_effects(effects, publish);
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
    #[cfg(feature = "sparse-cells")]
    fn capture_receipt(&mut self, rid: usize, slot: usize, _cell: u32, position: usize,
        table: usize, publication: Publication, receipt: Dependency, mut effects: Option<&mut crate::cell::Effects>,
    ) {
        if !self.cell_output_rules[rid] {
            self.stats.direct_publication_hash_probes += 1;
            self.direct_publications.insert(receipt, (table, publication));
            return;
        }
        let width = self.outputs[rid].len();
        let delivery = self.pending_steps[slot].delivery.get_or_insert_with(|| {
            let first = if let Some(effects) = &effects { effects.output_first() } else {
                let first = self.cell_outputs.len();
                self.cell_outputs.resize(first + width, None);
                first
            };
            self.stats.cell_output_spans += 1;
            self.stats.cell_output_slots += width as u64;
            self.stats.peak_cell_output_slots = self.stats.peak_cell_output_slots.max(first + width);
            Delivery {
                rule: u32::try_from(rid).ok().and_then(|r| r.checked_add(1))
                    .and_then(std::num::NonZeroU32::new).expect("Cell rule index exhausted"),
                first: u32::try_from(first).expect("Cell output arena exhausted"),
                #[cfg(feature = "spine-shapes")]
                cell: _cell,
            }
        });
        if let Some(effects) = effects.as_mut() {
            if effects.retain_output(position, receipt) { self.stats.effect_output_copies += 1; }
            else { self.stats.effect_outputs_reused += 1; }
        } else {
            self.cell_outputs[delivery.first as usize + position] = Some(receipt);
            self.stats.effect_output_copies += 1;
        }
        self.cell_outputs_pending += 1;
        self.stats.cell_output_receipts += 1;
        // Preserve the historical multi-output coverage metric as a subset of
        // common Cell output delivery, without maintaining a fragment packet.
        if width >= 2 {
            self.stats.fragment_receipts += 1;
            self.stats.fragment_direct_inserts_avoided += 1;
        }
    }
    fn materialize_publication(&mut self, publication: Publication) -> Published {
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
                    Started::Live(c) => {
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
    fn install_anchor(&mut self, w: Dependency, table: usize, publication: Publication) {
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
        let cursor = self.materialize_publication(publication);
        self.stats.legacy_entry_writes += 1;
        if self.entries.insert(w, cursor).is_none() {
            if self.active_tables[table] == 0 {
                for &rid in &self.table_readers[table] { self.live_inputs[rid] += 1; }
            }
            self.active_tables[table] += 1;
        }
    }
    #[cfg(feature = "sparse-cells")]
    fn finish_boundary(&mut self, slot: usize, entries: &mut crate::entry_schedule::Scheduler) {
        let id = self.pending_steps[slot].ready.expect("ready Cell export");
        let record = self.ready_publications[id.get() - 1];
        self.pending_steps[slot].ready = record.next;
        self.stats.completion_boundary_reads += 1;
        if !entries.install_publication(record.table, record.witness,
            || self.materialize_publication(record.publication)) {
            // Normalized boundary keys were counted before their receipts were
            // resolved. A later fragment can already own this same final key.
            self.stats.distinct_anchor_keys -= 1;
        }
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn settled(&self)->bool {
        self.pending_steps.is_empty() && self.pending_anchors.is_empty()
            && self.ready_publications.is_empty() && self.direct_publications.is_empty()
            && self.cell_outputs.is_empty()
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
                {
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
                self.install_anchor(w, table, publication);
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
                self.install_anchor(w, table, p);
            }
            self.direct_publications = resolved;
        }
        #[cfg(feature = "sparse-cells")]
        if let Some(entries) = entries.as_deref_mut() {
            if !self.ready_publications.is_empty() || self.cell_outputs_pending != 0 {
                entries.begin_publication();
                // Source Cells and their shared output positions are in capture
                // order. Reverse traversal sees the final Entry winner first.
                for slot in (0..self.pending_steps.len()).rev() {
                    self.stats.completion_cell_visits += 1;
                    if let Some(delivery) = self.pending_steps[slot].delivery {
                        let mut pending = false;
                        let rule = delivery.rule.get() as usize - 1;
                        let width = self.outputs[rule].len();
                        for position in (0..width).rev() {
                            self.stats.cell_output_slot_reads += 1;
                            let index = delivery.first as usize + position;
                            let Some(old) = self.cell_outputs[index] else { continue };
                            let output = self.outputs[rule][position];
                            let table = output.table;
                            self.stats.cell_output_checks += 1;
                            if width >= 2 { self.stats.fragment_delivery_checks += 1; }
                            if ready.is_some_and(|r| !r[table]) { pending = true; continue; }
                            while self.pending_steps[slot].ready.is_some_and(|i| self.ready_publications[i.get() - 1].publication.output > output.operation) {
                                self.finish_boundary(slot, entries);
                            }
                            let w = g.resolve_receipt(old);
                            if !g.receipt_visible(w, table) {
                                return Err("permanent Cell output lost visibility".into());
                            }
                            let publication = Publication {
                                slot, receipt: Some(old), output: output.operation,
                                #[cfg(feature = "spine-shapes")]
                                source: crate::graph::FactRef { cell: delivery.cell, op: output.operation as u32 },
                            };
                            let installed = entries.install_publication(table, w, || self.materialize_publication(publication));
                            self.stats.distinct_anchor_keys += u64::from(installed);
                            self.stats.cell_output_deliveries += 1;
                            if width >= 2 { self.stats.fragment_deliveries += 1; }
                            self.stats.receipt_attempts += 1;
                            self.stats.receipt_hits += 1;
                            self.stats.receipt_redirects += u64::from(w != old);
                            self.cell_outputs[index] = None;
                            self.cell_outputs_pending -= 1;
                        }
                        self.pending_steps[slot].delivery = pending.then_some(delivery);
                    }
                    while self.pending_steps[slot].ready.is_some() { self.finish_boundary(slot, entries); }
                }
                self.ready_publications.clear();
            }
        }
        let hits = self.stats.receipt_hits - hits_before;
        if hits > 0 {
            *self
                .stats
                .receipt_hits_by_source
                .entry("effect".into())
                .or_default() += hits;
        }
        // A deferred publication still addresses its original shared slot.
        // New source Runs append contexts; release the arena only when drained.
        if self.pending_publication_counts().0 == 0 {
            self.pending_steps.clear();
            #[cfg(feature = "sparse-cells")]
            self.cell_outputs.clear();
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
    pub fn answers(
        &mut self,
        g: &mut Graph,
        rid: usize,
        pending: &BTreeSet<Dependency>,
        watermark: u64,
    ) -> Result<Option<Coverage>> {
        if !self.active_for_rule(rid) {
            return Ok(None);
        }
        let clock = Instant::now();
        let result = self.answers_inner(g, rid, pending, watermark);
        self.stats.query_seconds += clock.elapsed().as_secs_f64();
        result
    }
    fn answers_inner(
        &mut self,
        g: &mut Graph,
        rid: usize,
        pending: &BTreeSet<Dependency>,
        watermark: u64,
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
        self.finish_answers(
            g,
            rid,
            ready.into_iter(),
            covered,
            complete,
            watermark,
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
        for (rid, outputs) in self.outputs.iter().enumerate() {
            self.cell_output_rules[rid] = !outputs.is_empty()
                && outputs.iter().all(|o| self.permanent[o.table] && self.entry_owned_tables[o.table]);
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

    pub fn answers_scheduled(
        &mut self,
        g: &mut Graph,
        rid: usize,
        seeds: &[Seed],
        watermark: u64,
    ) -> Result<Option<Coverage>> {
        if !self.active_for_rule(rid) {
            return Ok(None);
        }
        // This API also certifies an externally supplied empty domain. The
        // scheduler's routed API only reports takeovers for delivered seeds.
        if seeds.is_empty() {
            self.stats.query_attempts += 1;
            return self.finish_answers(
                g,
                rid,
                std::iter::empty::<(usize, Rc<Row>, Cursor)>(),
                BTreeSet::new(),
                true,
                watermark,
            );
        }
        let mut routes = Vec::new();
        for (i, seed) in seeds.iter().enumerate() {
            let row = &seed.packet.row;
            if let Some(cursor) = self
                .scheduled_cursors(rid, seed.atom(), row.table)
                .and_then(|c| c.get(&row.witness))
            {
                routes.push((i, cursor.expand()));
            } else {
                self.record_fallbacks(rid, seed.atom(), 1);
            }
        }
        self.answers_routed(g, rid, seeds, routes, watermark)
    }

    pub(crate) fn answers_routed(
        &mut self,
        g: &mut Graph,
        rid: usize,
        seeds: &[Seed],
        mut routes: Vec<(usize, Cursor)>,
        watermark: u64,
    ) -> Result<Option<Coverage>> {
        self.stats.routed_spine_seeds += routes.len() as u64;
        self.stats.routed_matcher_seeds += (seeds.len() - routes.len()) as u64;
        if !self.active_for_rule(rid) {
            return Ok(None);
        }
        self.stats.query_attempts += 1;
        if routes.is_empty() {
            self.stats.uncovered_queries += u64::from(!seeds.is_empty());
            return Ok(None);
        }
        let clock = Instant::now();
        let complete = routes.len() == seeds.len();
        if !complete {
            self.stats.mixed_routed_queries += 1;
            self.stats.uncovered_queries += 1;
        }
        // Equal-depth continuations retain the original witness/atom tie break.
        routes.sort_unstable_by_key(|(i, _)| (seeds[*i].packet.row.witness, seeds[*i].atom()));
        let mut covered = BTreeSet::new();
        // A complete takeover has no residual consumer for the coverage set.
        // Stream each validated Entry directly into its Cell query program.
        if !complete {
            covered.extend(
                routes
                    .iter()
                    .map(|(i, _)| (seeds[*i].atom(), seeds[*i].packet.row.witness)),
            );
        }
        let ready = routes.into_iter().map(|(i, cursor)| {
            let seed = &seeds[i];
            (
                seed.atom(),
                seed.packet.row.clone(),
                cursor,
            )
        });
        let result = self.finish_answers(g, rid, ready, covered, complete, watermark);
        self.stats.query_seconds += clock.elapsed().as_secs_f64();
        result
    }
    fn finish_answers(
        &mut self,
        g: &mut Graph,
        rid: usize,
        ready: impl ExactSizeIterator<Item = (usize, Rc<Row>, Cursor)>,
        covered: BTreeSet<(usize, Dependency)>,
        complete: bool,
        watermark: u64,
    ) -> Result<Option<Coverage>> {
        if !complete && covered.is_empty() {
            return Ok(None);
        }
        let rule = g.program.rules[rid].clone();
        #[cfg(feature = "sparse-cells")]
        let mut results = std::mem::take(&mut self.answer_scratch);
        #[cfg(not(feature = "sparse-cells"))]
        let mut results = Winners::new();
        let covered_count = if complete { ready.len() } else { covered.len() };
        'answer: for (pivot, row, cursor) in ready {
            let mut epoch = row.epoch;
            let local = if self.local_witness_entries[rid][pivot] {
                self.stats.local_witness_contexts += 1;
                let context = g.continuation_context(row.witness);
                #[cfg(feature = "iterative-bake")]
                let published = Some((g.program.rules[cursor.producer].template, cursor.state.output));
                #[cfg(not(feature = "iterative-bake"))]
                let published: Option<(usize, usize)> = None;
                published.or_else(|| context.map(|c| (c.template, c.op))).and_then(|(template, output)| {
                    self.stats.local_witness_route_probes += 1;
                    let route = g.program.multi_stage.routes
                        .get(&(template, output, rid, pivot))?.clone();
                    self.stats.local_witness_routes += 1;
                    #[cfg(feature = "iterative-bake")]
                    { self.stats.local_witness_history_borrows += 1; }
                    Some(LocalWitness {
                        context: context.filter(|c| (c.template, c.op) == (template, output)),
                        route,
                        // A consumer absent from the iterative catalog resets
                        // its state during dispatch. The current producer's
                        // already retained receipts still serve this match.
                        #[cfg(feature = "iterative-bake")]
                        history: cursor.state.history.clone(),
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
            #[cfg(feature = "spine-blocks")]
            {
                #[cfg(feature = "iterative-bake")]
                let selected = if g.program.iterative.enabled() {
                    cursor.state.collect_pairs = self.training.collect_pairs;
                    g.program.iterative.dispatch(&mut cursor.state, rid, pivot, complete, row.witness)
                } else { g.program.spine_blocks.contains(rid, pivot) };
                #[cfg(not(feature = "iterative-bake"))]
                let selected = g.program.spine_blocks.contains(rid, pivot);
                // Selection credits retain their original meaning. Compilation
                // alone does not authorize a composed cross-stage continuation.
                cursor.via_block = selected;
                self.stats.block_entries += u64::from(selected);
            }
            let query = self.queries.get(rid, pivot).expect("certified Cell Entry");
            self.stats.cell_query_entries += 1;
            let mut values = smallvec::SmallVec::<[Value; 4]>::new();
            // Keep rejected queries off the heap in the common short case. Only
            // successful matches materialize the externally required witness map.
            let mut found_witnesses = smallvec::SmallVec::<[(usize, Dependency); 4]>::new();
            for step in &query.steps {
                self.stats.cell_query_steps += 1;
                let bound = step.bind::<PortKey>(|v| v.operand(g, &row, &values, None));
                let result = bound.evaluate(|args| match &step.call {
                    Call::Table(table) => {
                        let Some(found) = read_port(
                            g, &cursor, step.atom, *table, args, &mut self.stats, local.as_ref(),
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
                self.stats.cell_query_result_writes += 1;
                values.push(result);
            }
            if epoch >= watermark {
                let inputs = query.inputs.iter().map(|v| v.read(g, &row, &values, None)).collect();
                let mut witnesses = vec![None; rule.query.len()];
                witnesses[pivot] = Some(row.witness);
                for (atom, witness) in found_witnesses { witnesses[atom] = Some(witness); }
                #[cfg(feature = "iterative-bake")]
                if cursor.via_block && cursor.state.direct {
                    self.training.seal_moves += query.inputs.len() as u64;
                }
                record_answer(&mut results, inputs, witnesses, epoch, cursor);
            }
        }
        #[cfg(feature = "sparse-cells")]
        {
            // Stable ordering retains the first producer when duplicate
            // bindings have the same depth, as in the ordered-map route.
            results.sort_by(|(ka, (_, ca)), (kb, (_, cb))| {
                ka.cmp(kb).then_with(|| cb.depth.cmp(&ca.depth))
            });
            results.dedup_by(|a, b| a.0 == b.0);
        }
        if complete {
            self.stats.query_takeovers += 1;
        } else {
            self.stats.partial_queries += 1;
        }
        self.stats.pivots_skipped += covered_count as u64;
        *self.stats.covered_by_rule.entry(rid).or_default() += covered_count as u64;
        self.stats.bindings += results.len() as u64;
        *self.stats.bindings_by_rule.entry(rid).or_default() += results.len() as u64;
        #[cfg(feature = "sparse-cells")]
        let rows = results.drain(..);
        #[cfg(not(feature = "sparse-cells"))]
        let rows = results.into_iter();
        let answers = rows
            .map(|(key, (answer, cursor))| {
                #[cfg(feature = "iterative-bake")]
                if cursor.state.direct || {
                    #[cfg(feature = "sparse-cells")]
                    { self.direct_sealed_answers }
                    #[cfg(not(feature = "sparse-cells"))]
                    { false }
                } {
                    // The executor appends residual matches after these winners.
                    // Stable sealing keeps the Spine binding on an equal RHS key.
                    // The public standalone Programs route still resolves by key.
                    self.stats.sealed_partial_origins += u64::from(!complete);
                    let mut answer = answer;
                    answer.values = key;
                    #[cfg(feature = "sparse-cells")]
                    {
                        answer.direct = Some(DirectOrigin(self.sealed_cursors.len()));
                        self.sealed_cursors.push(Some(cursor));
                    }
                    #[cfg(not(feature = "sparse-cells"))]
                    { answer.direct = Some(DirectOrigin(Box::new(cursor))); }
                    return answer;
                }
                if self.origins[rid].is_empty() {
                    self.origin_rules.push(rid);
                }
                #[cfg(feature = "sparse-cells")]
                let answer = {
                    let mut a = answer;
                    a.values = key.clone();
                    a
                };
                self.stats.origin_map_writes += 1;
                self.origins[rid].insert(key, cursor);
                answer
            })
            .collect();
        #[cfg(feature = "sparse-cells")]
        {
            self.answer_scratch = results;
        }
        Ok(Some(Coverage {
            complete,
            covered,
            answers,
        }))
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
            let valid = g.program.rules[rid].query[pivot]
                .args
                .iter()
                .zip(row.values.iter())
                .all(|(a, v)| match a {
                    Arg::Literal(l) => canon(l, &g.parents) == *v,
                    Arg::Slot(i) => match &input[*i] {
                        Some(old) => old == v,
                        None => {
                            self.stats.entry_parameters_copied += 1;

                            input[*i] = Some(v.clone());
                            true
                        }
                    },
                });
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
        let report = json!({"enabled":self.enabled,"receipts_enabled":self.receipts,"partial_enabled":self.partial,"shared_entries_enabled":self.shared_entries,"stats":self.stats,"producer_rules":self.outputs.iter().filter(|ops| !ops.is_empty()).count(),
            "effect_plan_cache_bytes":effect_plan_cache_bytes,"keyed_entries":self.queries.len(),"shared_query_plans":self.queries.shared(),"live_spines":contexts.len(),"live_materialized_contexts":live_materialized,
            "entry_references":self.entries.len() + extra.len(),"legacy_entry_references":self.entries.len(),"node_entry_references":extra.len(),"context_fact_references":facts,
            "scope":"source-scheduled RHS continuation from committed producer contexts; exhaustive functional-key entries; unknown delta entries use ordinary matching; no early effect visibility"});
        #[cfg(feature = "iterative-bake")]
        let report = {
            let mut r = report;
            r["iterative_bake"] = self.training.report();
            r
        };
        report
    }
}
