//! Execute Cell queries on a borrowed Run view: point continuations and, with
//! parallel-residuals, connected residual expansion plus necessary admission.
//! Entry values stay borrowed; successful bindings move into the original RHS.
use super::*;
use rayon::prelude::*;
use serde::Serialize;
#[cfg(feature = "parallel-residuals")]
#[path = "query_expansion_workers.rs"]
mod expansion;
#[cfg(feature = "cell-query-sharing-audit")]
#[path = "query_sharing_audit.rs"]
mod sharing_audit;
#[path = "query_ready_workers.rs"]
mod ready;

#[derive(Default, Serialize)]
pub(crate) struct Counts {
    pub execution: crate::cell::execution::Counts,
    pub worker_local_operations: Vec<u64>,
    pub worker_constructor_lookups: Vec<u64>,
    #[cfg(feature = "cell-query-sharing-audit")]
    pub sharing_audit: sharing_audit::Counts,
    pub fixed_read_probes: u64,
    pub entry_parent_handoffs: u64,
    pub fixed_read_fills: u64,
    pub fixed_read_hits: u64,
    pub fixed_read_clears: u64,
    pub fixed_key_fields: u64,
    pub fixed_rejected_entries: u64,
    pub shared_first_reads: u64,
    pub shared_first_key_fields: u64,
    pub fixed_read_storage_bytes: u64,
    pub cell_task_probes: u64,
    pub cell_task_records: u64,
    pub cell_task_links: u64,
    pub cell_task_emissions: u64,
    pub cell_task_clears: u64,
    pub cell_task_growths: u64,
    pub cell_code_reads: u64,
    pub active_template_visits: u64,
    pub ungrouped_inline_entries: u64,
    pub peak_cell_task_bytes: u64,
    pub compiled_cell_code_bytes: u64,
    pub frame_cache_borrows: u64,
    pub frame_capacity_bytes: u64,
    pub worker_frame_capacity_bytes: Vec<u64>,
    pub coordinator_frame_capacity_bytes: u64,
    pub constructors: crate::graph::query_reads::Work,
    pub task_order_headers: u64,
    pub completion_slot_initializations: u64,
    pub completion_slot_writes: u64,
    pub completion_headers: u64,
    pub completion_error_checks: u64,
    // input-depth-ordinal/v1 counts the fused comparator. Older reports count
    // only the preliminary ordinal sort, omitting their second key sort.
    pub winner_order_comparisons: u64,
    pub deferred_winner_moves: u64,
    pub completion_binding_moves: u64,
    pub serial_order_headers: u64,
    pub rule_admissions: u64,
    pub static_rule_skips: u64,
    pub entry_mask_checks: u64,
    pub cell_source_reads: u64,
    pub cell_order_comparisons: u64,
    pub cell_queue_growths: u64,
    pub peak_cell_queue_bytes: u64,
    pub borrowed_job_headers: u64,
    pub cell_instances: u64,
    pub multi_entry_cells: u64,
    pub cross_rule_cells: u64,
    pub max_entries_per_cell: u64,
    pub coordinator_entries: u64,
    pub seed_range_comparisons: u64,
    pub worker_steps: Vec<u64>,
    pub admission_entry_checks: u64,
    pub spine_entries: u64,
    pub spine_point_reads: u64,
    pub guards: u64,
    pub guard_rejections: u64,
    pub batches: u64,
    pub entries: u64,
    pub answers: u64,
    pub steps: u64,
    pub point_reads: u64,
    pub key_operations: u64,
    pub result_writes: u64,
    pub owner_rejections: u64,
    pub chunks: u64,
    pub entry_buffer_bytes: u64,
    pub frame_allocations: u64,
    pub admission_table_checks: u64,
    pub seed_selection_visits: u64,
    pub entry_headers: u64,
    pub output_buffer_capacity: u64,
    pub batch_buffers: u64,
    pub answer_buffer_allocations: u64,
    pub worker_entries: Vec<u64>,
}
pub(crate) struct Workers {
    // Run-level accounting does not inflate each query chunk's Counts.
    matched: ready::Stats,
    #[cfg(feature = "parallel-residuals")]
    expansion: expansion::Plans,
    pool: Option<rayon::ThreadPool>,
    grain: usize,
    stats: Counts,
    cell_plans: Vec<Option<CellPlan>>,
    cell_codes: Vec<CellCode>,
    first_reads: FirstReads,
    tasks: CellTasks,
    cell_queries: Vec<CellQuery>,
    rule_facts: Vec<Option<RuleRun>>,
    inline_frame: Frame,
}

// Capacities belong to the executor's worker threads (or its inline host).
// Values, witnesses and candidates never survive a chunk, including an error.
// This is scratch reuse, not a query-result cache across source Runs.
#[derive(Default)]
struct Frame {
    values: Vec<Value>,
    witnesses: Vec<(usize, Dependency)>,
    constructors: crate::graph::query_reads::Scratch,
}
struct FrameUse<'a>(&'a mut Frame);
impl Drop for FrameUse<'_> {
    fn drop(&mut self) {
        self.0.values.clear();
        self.0.witnesses.clear();
        self.0.constructors.clear();
    }
}
impl Frame {
    fn with<R>(&mut self, run: impl FnOnce(&mut Self) -> R) -> R {
        let guard = FrameUse(self);
        run(&mut *guard.0)
    }
    fn prepare(&mut self, slots: usize, reads: usize, counts: &mut Counts) {
        debug_assert!(self.values.is_empty() && self.witnesses.is_empty());
        counts.frame_cache_borrows += 1;
        counts.frame_allocations += u64::from(slots > self.values.capacity())
            + u64::from(reads > self.witnesses.capacity());
        self.values.resize(slots, Value::Int(0));
        self.witnesses.reserve(reads);
    }
    fn bytes(&self) -> u64 {
        (self.values.capacity() * std::mem::size_of::<Value>()
            + self.witnesses.capacity() * std::mem::size_of::<(usize, Dependency)>()
            + self.constructors.capacity_bytes()) as u64
    }
}
thread_local! {
    static QUERY_FRAME: std::cell::RefCell<Frame> = std::cell::RefCell::new(Frame::default());
}
fn with_worker_frame<R>(run: impl FnOnce(&mut Frame) -> R) -> R {
    QUERY_FRAME.with_borrow_mut(|frame| frame.with(run))
}

#[cfg(test)]
#[test]
fn scratch_keeps_capacity_but_releases_values_on_error_and_unwind() {
    use std::sync::Arc;
    let mut frame = Frame::default();
    for unwind in [false, true] {
        let value = Arc::new("value from a completed Run".to_owned());
        let weak = Arc::downgrade(&value);
        let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            frame.with(|frame| -> Result<()> {
                frame.prepare(3, 2, &mut Counts::default());
                frame.values[0] = Value::Text(value);
                frame.witnesses.push((0, Dependency::Fact(FactRef { cell: 7, op: 1 })));
                if unwind { panic!("query failure") }
                Err("query failure".into())
            })
        }));
        assert!(if unwind { outcome.is_err() } else { outcome.unwrap().is_err() });
        assert!(weak.upgrade().is_none(), "scratch must not retain a query value");
        assert!(frame.values.is_empty() && frame.witnesses.is_empty());
        assert!(frame.values.capacity() >= 3 && frame.witnesses.capacity() >= 2);
    }
}
// Borrow through the Entry's Rc on the coordinator, sharing only its immutable
// values and lifecycle stamp. No Rc operations happen on worker threads.
struct Entry<'a> {
    values: &'a [Value],
    epoch: u64,
    witness: Dependency,
}
impl Executor {
    pub fn use_cell_execution(&mut self, grain: usize) -> Result<()> {
        if grain == 0 || self.query_workers.is_none() {
            return Err("Cell execution requires query workers and positive grain".into());
        }
        if !self.steps.is_empty() || self.cell_execution.is_some() {
            return Err("configure Cell execution once before the first Run".into());
        }
        self.cell_execution = Some(crate::cell::execution::runtime::State {
            grain, counts: Default::default(),
        });
        for rule in 0..self.graph.program.rules.len() {
            let mut constructor = crate::cell::constructor_prepare::Plan::derive(&self.graph.program, rule);
            if let Some(plan) = &mut constructor {
                plan.compile_prefix(&self.graph.program,rule,self.stage_spine.permanent_tables());
            }
            self.graph.program.executions[rule].constructor = constructor;
            self.graph.program.executions[rule].births = crate::graph::cell_births::Plan::derive(&self.graph.program,rule).map(std::sync::Arc::new);
        }
        self.refresh_cell_execution_layouts();
        Ok(())
    }
    /// All layout mutation is configuration, before the first Run. Refresh
    /// static wiring there instead of checking its identity on every instance.
    pub(super) fn refresh_cell_execution_layouts(&mut self) {
        for rule in 0..self.graph.program.rules.len() {
            if self.graph.program.executions[rule].constructor.as_ref().is_some_and(|p|p.prefix_width()!=0) {
                let layout=self.stage_spine.preparation_layout(&self.graph.program,rule);
                self.graph.program.executions[rule].constructor.as_mut().unwrap().result_layout=layout;
            }
        }
    }
    #[cfg(feature = "parallel-entry-filters")]
    pub fn use_parallel_entry_filters(&mut self) -> Result<()> {
        if !self.steps.is_empty() { return Err("configure Entry filters before execution".into()); }
        if self.query_workers.as_ref().is_none_or(|w| w.pool.is_none()) {
            return Err("parallel Entry filters require at least two query workers".into());
        }
        self.sieve.parallel_enabled = true;
        Ok(())
    }
    pub fn use_query_workers(&mut self, workers: usize, grain: usize) -> Result<()> {
        if workers == 0 || grain == 0 { return Err("query workers and grain must be positive".into()); }
        if self.query_workers.is_some() { return Err("query workers already configured".into()); }
        let pool = if workers == 1 { None } else {
            Some(rayon::ThreadPoolBuilder::new().num_threads(workers)
                .thread_name(|i| format!("cell-query-{i}")).build().map_err(|e| e.to_string())?)
        };
        let (cell_plans, mut cell_codes) = CellPlan::compile(&self.graph.program,self.stage_spine.permanent_tables());
        let first_reads = FirstReads::compile(&mut cell_codes);
        let fixed_read_storage_bytes = first_reads.bytes();
        #[cfg(feature = "cell-query-sharing-audit")]
        let sharing_audit = sharing_audit::Counts {
            compiled_prefixes: cell_codes.iter().flat_map(|c| c.audit_prefixes.iter()).copied().max().unwrap_or(0) as u64,
            compiled_prefix_bytes: cell_codes.iter().map(|c| c.audit_prefixes.capacity() * std::mem::size_of::<usize>()).sum::<usize>() as u64,
            ..Default::default()
        };
        let compiled_cell_code_bytes = (cell_codes.capacity() * std::mem::size_of::<CellCode>()
            + cell_plans.capacity() * std::mem::size_of::<Option<CellPlan>>()
            + cell_plans.iter().flatten().map(|p| p.entries.capacity() * std::mem::size_of::<Option<usize>>()
                + p.tables.len() * std::mem::size_of::<usize>()).sum::<usize>()) as u64;
        self.query_workers = Some(Workers { pool, grain, matched: Default::default(),
            #[cfg(feature = "parallel-residuals")]
            expansion: Default::default(),
            cell_plans, cell_codes, first_reads, tasks: CellTasks::new(self.graph.program.templates.len()), cell_queries: Vec::new(),
            rule_facts: (0..self.graph.program.rules.len()).map(|_| None).collect(),
            inline_frame: Frame::default(),
            stats: Counts { compiled_cell_code_bytes, fixed_read_storage_bytes, worker_entries: vec![0; workers], worker_local_operations:vec![0; workers], worker_constructor_lookups:vec![0;workers], worker_steps: vec![0; workers],
                #[cfg(feature = "cell-query-sharing-audit")]
                sharing_audit,
                worker_frame_capacity_bytes: vec![0; workers], ..Default::default() } });
        Ok(())
    }
    pub(super) fn query_worker_report(&self) -> J {
        self.query_workers.as_ref().map_or(json!({"enabled":false}), |w|
            json!({"enabled":true,"workers":w.stats.worker_entries.len(),"grain":w.grain,
                "organization":"cell-run/v5","winner_ordering":"input-depth-ordinal/v1",
                "instance_header_bytes":std::mem::size_of::<Binding>(),
                "matched":w.matched,
                "constructor_access":"canonical-or-stable/v1", "first_read_sharing":"literal-run/v1",
                "rule_run_capacity_bytes":w.rule_facts.capacity()*std::mem::size_of::<Option<RuleRun>>(),
                "scope":"source-Run Cell queries and owned matched slots; optional residual expansion; source-ordered shared effects", "stats":w.stats,
                "residual_expansion":w.expansion_report()}))
    }
    pub(super) fn query_worker_batch(
        &mut self, rid: usize, rule: &Rule, kernel: &crate::row_kernel::Kernel,
        seeds: &[crate::entry_schedule::Seed], covered: &BTreeSet<(usize, Dependency)>,
        early_sieve: bool, known: &QueryFacts, out: &mut Vec<Binding>,
    ) -> Result<bool> {
        let Some(workers) = &mut self.query_workers else { return Ok(false) };
        // Existing producer-prefix hosts keep their ownership. Point-only
        // neighbor queries transfer here; enumeration stays in its current host.
        // Shape surveys/audits with additional per-read effects use those hosts too.
        if kernel.routes.is_some() || cfg!(feature="structural-depth")
            || cfg!(feature="family-overlap") || cfg!(feature="family-survey") {
            return Ok(false);
        }
        let Some(tables) = &kernel.point_tables else { return Ok(false) };
        let Some(reads) = self.graph.query_reads(tables, &mut workers.stats.admission_table_checks)
            else { return Ok(false) };
        let seeds = crate::entry_schedule::Seed::for_atom(seeds, kernel.pivot,
            &mut workers.stats.seed_range_comparisons);
        if seeds.len() < workers.grain { return Ok(false); }
        workers.stats.seed_selection_visits += seeds.len() as u64;
        let entries: Vec<_> = seeds.iter()
            .filter(|s| !covered.contains(&(kernel.pivot, s.packet.row.witness)))
            .filter(|s| early_sieve || self.sieve.allow(rid, kernel.pivot, s.packet.row.table,
                s.packet.row.witness, &self.query_indexes))
            .map(|s| Entry { values: &*s.packet.row.values, epoch: s.packet.row.epoch,
                witness: s.packet.row.witness }).collect();
        if entries.is_empty() { return Ok(true); }
        // Once selected this host owns the whole pivot, including rejected seeds.
        // Even a small filtered batch is completed here, never queried twice.
        let query = kernel.query.as_ref();
        let pivot = kernel.pivot;
        let input_slots = rule.inputs.as_slice();
        let query_width = rule.query.len();
        let key_nodes = self.graph.program.key_nodes();
        let local=&self.graph.program.executions[rid];
        let template=&self.graph.program.templates[rule.template];
        let pooled = workers.pool.is_some();
        let run = |chunk: &[Entry<'_>], frame: &mut Frame| -> Result<(Vec<Binding>, Counts, Option<usize>)> {
            let mut counts = Counts { entries: chunk.len() as u64, chunks: 1,
                ..Default::default() };
            frame.prepare(query.result_slots(), query_width, &mut counts);
            let mut answers = Vec::new();
            for entry in chunk {
                let Some(epoch) = evaluate(query, entry, pivot, &reads, key_nodes, false, None,
                    &mut frame.values, &mut frame.witnesses, &mut frame.constructors, &mut counts,
                    #[cfg(feature = "cell-query-sharing-audit")] None,
                )? else { continue };
                if answers.len() == answers.capacity() { counts.answer_buffer_allocations += 1; }
                let mut answer=Binding {
                    #[cfg(feature="sparse-cells")]
                    prepared: 0,
                    #[cfg(feature="sparse-cells")]
                    constructor: Default::default(),
                    #[cfg(feature="sparse-cells")]
                    preparation_attempted: false,
                    #[cfg(feature="view-consumers")]
                    view_source: None,
                    direct: None,
                    known: known.with_rows(frame.witnesses.iter().copied()),
                    values: local.slots(input_slots.iter().zip(&query.inputs).map(|(&slot, field)|
                        (slot, field.operand_in(reads.parents, |col| &entry.values[col], &frame.values, None).into_owned())),&mut counts.execution),
                    epoch, parent: None, continuation: None, compiled: true,
                };
                local.prepare(template,&mut answer,&mut counts.execution);
                if let Some(plan) = &local.constructor {
                    plan.prepare(&mut answer,Some(&reads),&mut frame.constructors,
                        &mut counts.constructors,&mut counts.execution.constructor);
                }
                answers.push(answer);
            }
            counts.answers = answers.len() as u64;
            counts.output_buffer_capacity = answers.capacity() as u64;
            counts.frame_capacity_bytes = frame.bytes();
            Ok((answers, counts, if pooled { rayon::current_thread_index() } else { None }))
        };
        // Indexed collection preserves pivot/Entry order, including first-error
        // selection. The borrow ends before any source effect can mutate slots.
        let completed: Vec<_> = if let Some(pool) = &workers.pool {
            pool.install(|| entries.par_chunks(workers.grain).map(|chunk| with_worker_frame(|frame| run(chunk, frame))).collect())
        } else { entries.chunks(workers.grain).map(|chunk| workers.inline_frame.with(|frame| run(chunk, frame))).collect() };
        workers.stats.batches += 1;
        workers.stats.batch_buffers += 2;
        workers.stats.entry_headers += entries.len() as u64;
        workers.stats.entry_buffer_bytes += (entries.capacity() * std::mem::size_of::<Entry<'_>>()) as u64;
        for result in completed {
            let (mut answers, counts, worker) = result?;
            self.graph.record_constructor_query_work(&counts.constructors);
            workers.absorb(&counts, worker);
            self.graph.stats.register_seeds += counts.entries;
            self.graph.stats.register_answers += counts.answers;
            self.graph.stats.register_result_writes += counts.result_writes;
            self.graph.stats.key_operations += counts.key_operations;
            self.graph.stats.residual_candidates += counts.point_reads;
            self.graph.key_lookup_calls.set(self.graph.key_lookup_calls.get() + counts.point_reads + counts.execution.constructor.lookups);
            out.append(&mut answers);
        }
        Ok(true)
    }
}

// The ordinary Cell instructions remain the sole query semantics. These two
// hosts differ only in delta ownership and how completed frames are projected.
fn evaluate(
    query: &crate::cell::Query, entry: &Entry<'_>, pivot: usize,
    reads: &crate::graph::query_reads::QueryReads<'_>, key_nodes: &J,
    spine: bool, first: Option<&PointResult>, values: &mut [Value], witnesses: &mut Vec<(usize, Dependency)>,
    scratch: &mut crate::graph::query_reads::Scratch, counts: &mut Counts,
    #[cfg(feature = "cell-query-sharing-audit")] mut audit: Option<(&mut sharing_audit::Probe, &[usize])>,
) -> Result<Option<u64>> {
    witnesses.clear();
    witnesses.push((pivot, entry.witness));
    let owner = (entry.epoch, entry.witness);
    let mut epoch = entry.epoch;
    for (pc, step) in query.steps.iter().enumerate() {
        counts.steps += 1;
        #[cfg(feature = "cell-query-sharing-audit")]
        if let Some((probe, prefixes)) = &mut audit {
            probe.prefix(prefixes[pc], entry.values, entry.witness, matches!(step.call, Call::Table(_)));
        }
        let value = if let Some(first) = first.filter(|_| pc == 0) {
            debug_assert!(spine, "shared first reads currently belong to Cell continuations");
            counts.shared_first_reads += 1;
            counts.shared_first_key_fields += step.key.len() as u64;
            let bound = step.bind_result(|field|
                field.operand_in(reads.parents, |col| &entry.values[col], values, None));
            bound.evaluate(|()| {
                let Some((v, stamp, witness)) = first.as_ref().map_err(Clone::clone)? else { return Ok(None) };
                epoch = epoch.max(*stamp);
                witnesses.push((step.atom, *witness));
                Ok(Some(v.clone()))
            })?
        } else {
            let bound = step.bind::<smallvec::SmallVec<[Value; 4]>>(|field|
                field.operand_in(reads.parents, |col| &entry.values[col], values, None));
            bound.evaluate(|args| match &step.call {
                Call::Table(t) => {
                    counts.point_reads += 1;
                    #[cfg(feature = "cell-query-sharing-audit")]
                    if let Some((probe, _)) = &mut audit { probe.read(*t, &args); }
                    let Some((v, stamp, witness)) = reads.point(*t, &args, scratch, &mut counts.constructors)? else { return Ok(None) };
                    if !spine && ((stamp, witness) > owner || ((stamp, witness) == owner && step.atom < pivot)) {
                        counts.owner_rejections += 1;
                        return Ok(None);
                    }
                    epoch = epoch.max(stamp);
                    witnesses.push((step.atom, witness));
                    Ok(Some(v))
                }
                Call::Primitive(name, sort) => {
                    counts.guards += 1;
                    counts.key_operations += u64::from(name.starts_with("cell-key-"));
                    value::primitive(name, &args, sort, key_nodes)
                }
            })?
        };
        let Some(value) = value else {
            counts.guard_rejections += u64::from(matches!(step.call, Call::Primitive(..)));
            return Ok(None);
        };
        if if spine { pc < query.result_slots() } else { step.check_result.is_none() } {
            values[pc] = value;
            counts.result_writes += 1;
        }
    }
    Ok(Some(epoch))
}

impl Workers {
    pub(crate) fn execution_pool(&self) -> Option<&rayon::ThreadPool> { self.pool.as_ref() }
    #[cfg(feature = "parallel-publication")]
    pub(crate) fn publication_pool(&self)->(Option<&rayon::ThreadPool>,usize) { (self.pool.as_ref(),self.grain) }
    fn expansion_report(&self) -> J {
        #[cfg(feature = "parallel-residuals")]
        { self.expansion.report() }
        #[cfg(not(feature = "parallel-residuals"))]
        { json!({"enabled":false}) }
    }
    #[cfg(feature = "parallel-entry-filters")]
    pub(crate) fn filter_pool(&self) -> Option<(&rayon::ThreadPool, usize)> {
        self.pool.as_ref().map(|p| (p, self.grain))
    }
    fn absorb(&mut self, c: &Counts, worker: Option<usize>) {
        #[cfg(feature = "cell-query-sharing-audit")]
        self.stats.sharing_audit.add(&c.sharing_audit);
        self.stats.constructors.add(&c.constructors);
        self.stats.execution.add(&c.execution);
        if let Some(worker) = worker {
            self.stats.worker_entries[worker] += c.entries;
            self.stats.worker_local_operations[worker] += c.execution.operations;
            self.stats.worker_constructor_lookups[worker] += c.execution.constructor.lookups;
            self.stats.worker_steps[worker] += c.steps;
            self.stats.worker_frame_capacity_bytes[worker] = self.stats.worker_frame_capacity_bytes[worker].max(c.frame_capacity_bytes);
        } else {
            self.stats.coordinator_entries += c.entries;
            self.stats.coordinator_frame_capacity_bytes = self.stats.coordinator_frame_capacity_bytes.max(c.frame_capacity_bytes);
        }
        self.stats.frame_cache_borrows += c.frame_cache_borrows;
        self.stats.frame_capacity_bytes = self.stats.frame_capacity_bytes.max(c.frame_capacity_bytes);
        self.stats.entries += c.entries;
        self.stats.answers += c.answers;
        self.stats.steps += c.steps;
        self.stats.shared_first_reads += c.shared_first_reads;
        self.stats.shared_first_key_fields += c.shared_first_key_fields;
        self.stats.point_reads += c.point_reads;
        self.stats.key_operations += c.key_operations;
        self.stats.result_writes += c.result_writes;
        self.stats.owner_rejections += c.owner_rejections;
        self.stats.guards += c.guards;
        self.stats.guard_rejections += c.guard_rejections;
        self.stats.chunks += c.chunks;
        self.stats.frame_allocations += c.frame_allocations;
        self.stats.answer_buffer_allocations += c.answer_buffer_allocations;
        self.stats.output_buffer_capacity += c.output_buffer_capacity;
    }
}

// This is derived from the existing Cell queries. It selects code, never live
// facts or a producer's subscriber list.
struct CellPlan {
    entries: Vec<Option<usize>>,
    tables: Box<[usize]>,
}
struct CellCode {
    #[cfg(feature = "parallel-residuals")]
    expansion: bool,
    first_read: Option<usize>,
    query: crate::cell::SharedQuery,
    inputs: InputSlots,
    rule: usize,
    template: usize,
    pivot: usize,
    inherits_entry: bool,
    slots: usize,
    reads: usize,
    #[cfg(feature = "cell-query-sharing-audit")]
    audit_prefixes: Vec<usize>,
}
// A finite compiler-selected read layout, not a dynamic key cache. Values and
// misses live only until this source Run joins; no cross-Run invalidation index.
type PointResult = Result<Option<(Value, u64, Dependency)>>;
#[derive(Default)]
struct FirstReads {
    keys: Vec<(usize, Vec<Value>)>,
    results: Vec<Option<PointResult>>,
    touched: Vec<usize>,
    work: crate::graph::query_reads::Work,
    rejected: u64,
}
impl FirstReads {
    fn compile(codes: &mut [CellCode]) -> Self {
        let mut reads = Self::default();
        let mut index = BTreeMap::new();
        for code in codes {
            // The explicit sharing audit observes the original reads so it can
            // discover opportunities; its instrumented build is never timed.
            if cfg!(feature = "cell-query-sharing-audit") { continue; }
            if let Some(key) = code.query.first_literal_read() {
                let id = *index.entry(key.clone()).or_insert_with(|| {
                    let id = reads.keys.len();
                    reads.keys.push(key);
                    reads.results.push(None);
                    id
                });
                code.first_read = Some(id);
            }
        }
        reads.touched = Vec::with_capacity(reads.keys.len());
        reads
    }
    fn bytes(&self) -> u64 {
        (self.keys.capacity() * std::mem::size_of::<(usize, Vec<Value>)>()
            + self.keys.iter().map(|(_, k)| k.capacity() * std::mem::size_of::<Value>()).sum::<usize>()
            + self.results.capacity() * std::mem::size_of::<Option<PointResult>>()
            + self.touched.capacity() * std::mem::size_of::<usize>()) as u64
    }
}
struct RuleRun {
    facts: QueryFacts, watermark: u64,
    #[cfg(feature="parallel-residuals")]
    first_source:usize,
}
impl CellPlan {
    fn compile(p: &Program, permanent:&[bool]) -> (Vec<Option<Self>>, Vec<CellCode>) {
        let mut local = p.rules.iter().map(|r| vec![false; r.query.len()]).collect::<Vec<_>>();
        for route in p.multi_stage.routes.values() {
            local[route.consumer][route.anchor] |= route.reads.iter().any(|r| r.witness.is_some());
        }
        let mut codes = Vec::new();
        #[cfg(feature = "cell-query-sharing-audit")]
        let mut prefixes = sharing_audit::Prefixes::default();
        let plans = p.rules.iter().enumerate().map(|(rid, r)| {
            let mut tables = BTreeSet::new();
            let entries = (0..r.query.len()).map(|pivot| {
                if local[rid][pivot] { return None; }
                let points = p.cell_queries.point_tables(rid, pivot).filter(|p| !p.is_empty())?;
                tables.extend(points.iter().copied());
                let query = p.cell_queries.get(rid, pivot).unwrap().clone();
                let code = codes.len();
                codes.push(CellCode {
                    #[cfg(feature = "parallel-residuals")] expansion:false,
                    first_read: None, rule: rid, template:r.template, pivot, inherits_entry:crate::cell::inherits_entry(p,rid,pivot,permanent), slots: query.result_slots(), reads: query.steps.len() + 1,
                    #[cfg(feature = "cell-query-sharing-audit")]
                    audit_prefixes: prefixes.compile(&query),
                    inputs: r.inputs.clone(), query });
                Some(code)
            }).collect::<Vec<_>>();
            entries.iter().any(Option::is_some).then(|| Self { entries, tables: tables.into_iter().collect() })
        }).collect();
        (plans, codes)
    }
}
struct CellQuery {
    #[cfg(feature = "parallel-residuals")]
    filter: bool,
    code: usize,
    next: usize,
    ordinal: usize,
    row: Rc<Row>,
    cursor: Option<crate::stage_spine::Cursor>,
}
struct QueryRead<'a> {
    #[cfg(feature = "parallel-residuals")]
    expansion: usize,
    #[cfg(feature = "parallel-residuals")]
    filter: bool,
    source: usize,
    code: &'a CellCode,
    row: &'a Row,
    #[cfg(feature = "cell-query-sharing-audit")]
    audit_cell: (usize, Dependency),
}
fn query_error_order(q:&QueryRead<'_>,known:&RuleRun)->(usize,bool,usize) {
    #[cfg(feature="parallel-residuals")]
    { (known.first_source,q.code.expansion,q.source) }
    #[cfg(not(feature="parallel-residuals"))]
    { let _=known;(q.source,false,0) }
}
struct Chunk {
    entries: std::ops::Range<usize>,
    slots: usize,
    reads: usize,
}
fn append_query<'a>(source: usize, queries: &'a [CellQuery], codes: &'a [CellCode],
    headers: &mut Vec<QueryRead<'a>>, chunk: &mut Chunk, counts: &mut Counts,
    #[cfg(feature = "parallel-residuals")] positions: &[usize],
    #[cfg(feature = "cell-query-sharing-audit")] g: &Graph) {
    let q = &queries[source];
    let code = &codes[q.code];
    counts.cell_code_reads += 1;
    chunk.slots = chunk.slots.max(code.slots);
    chunk.reads = chunk.reads.max(code.reads);
    headers.push(QueryRead { source, code,
        #[cfg(feature = "parallel-residuals")] expansion:if code.expansion {positions[q.code]} else {0},
        #[cfg(feature = "parallel-residuals")] filter:q.filter,
        #[cfg(feature = "cell-query-sharing-audit")]
        audit_cell: physical_cell(g, &q.row),
        row: &q.row });
}
#[inline]
fn physical_cell(g: &Graph, row: &Row) -> (usize, Dependency) {
    // Use the actual result's Cell, including foreign constructor reuse.
    let actual = g.origin(row.witness).and_then(|f| {
        g.cells.cell_metadata(f.cell).map(|c| (c.template, f.cell))
            .or_else(|| g.continuation_context(row.witness)
                .filter(|c| c.cell == f.cell).map(|c| (c.template, c.cell)))
    });
    actual.map_or((g.program.table_templates[row.table], row.witness),
        |(template, cell)| (template, Dependency::Fact(FactRef { cell, op: 0 })))
}
// Transient work, not subscriptions: each Run links only its already activated
// Entries. The shared template buckets contain no facts or later consumers.
// One flat arena avoids allocating a Vec for every physical Cell.
struct CellTask {
    first: usize,
    last: usize,
    count: usize,
    first_rule: usize,
    cross_rule: bool,
    next: usize,
}
struct CellTasks {
    by_cell: rustc_hash::FxHashMap<(usize, Dependency), usize>,
    cells: Vec<CellTask>,
    templates: Vec<(usize, usize)>, // task index + 1; zero is empty
    active: Vec<usize>,
}
impl CellTasks {
    fn new(templates: usize) -> Self {
        Self { by_cell: Default::default(), cells: Vec::new(), templates: vec![(0, 0); templates], active: Vec::new() }
    }
    fn push(&mut self, cell: (usize, Dependency), source: usize, rule: usize, queries: &mut [CellQuery], counts: &mut Counts) {
        counts.cell_task_probes += 1;
        let capacity = self.by_cell.capacity();
        match self.by_cell.entry(cell) {
            std::collections::hash_map::Entry::Occupied(index) => {
                let task = &mut self.cells[*index.get()];
                queries[task.last].next = source;
                task.last = source;
                task.count += 1;
                task.cross_rule |= task.first_rule != rule;
                counts.cell_task_links += 1;
            }
            std::collections::hash_map::Entry::Vacant(index) => {
                let id = self.cells.len();
                index.insert(id);
                counts.cell_task_growths += u64::from(self.cells.len() == self.cells.capacity());
                self.cells.push(CellTask { first: source, last: source, count: 1, first_rule: rule, cross_rule: false, next: 0 });
                let (first, last) = &mut self.templates[cell.0];
                if *last == 0 {
                    counts.cell_task_growths += u64::from(self.active.len() == self.active.capacity());
                    self.active.push(cell.0);
                    *first = id + 1;
                } else {
                    self.cells[*last - 1].next = id + 1;
                    counts.cell_task_links += 1;
                }
                *last = id + 1;
                counts.cell_task_records += 1;
            }
        }
        counts.cell_task_growths += u64::from(self.by_cell.capacity() != capacity);
    }
    fn bytes(&self) -> u64 {
        // Hash-map entry capacity excludes its private control bytes.
        (self.by_cell.capacity() * std::mem::size_of::<((usize, Dependency), usize)>()
            + self.cells.capacity() * std::mem::size_of::<CellTask>()
            + self.templates.capacity() * std::mem::size_of::<(usize, usize)>()
            + self.active.capacity() * std::mem::size_of::<usize>()) as u64
    }
    fn clear(&mut self, counts: &mut Counts) {
        counts.cell_task_clears += self.cells.len() as u64;
        self.by_cell.clear();
        self.cells.clear();
        for template in self.active.drain(..) { self.templates[template] = (0, 0); }
    }
}
impl Workers {
    pub(crate) fn admit_spine_rule(&mut self, g: &Graph, rid: usize) -> bool {
        self.stats.rule_admissions += 1;
        if cfg!(feature="structural-depth") || cfg!(feature="family-overlap") || cfg!(feature="family-survey") { return false; }
        let Some(plan) = &self.cell_plans[rid] else {
            self.stats.static_rule_skips += 1;
            return false;
        };
        g.query_reads(&plan.tables, &mut self.stats.admission_table_checks).is_some()
    }
    pub(crate) fn spine_entry(&mut self, rid: usize, pivot: usize, cursor: &crate::stage_spine::Cursor) -> Option<usize> {
        self.stats.entry_mask_checks += 1;
        let code = self.cell_plans[rid].as_ref().unwrap().entries[pivot]?;
        self.stats.admission_entry_checks += 1;
        cursor.uncached_query().then_some(code)
    }
    pub(crate) fn enqueue_spine(&mut self, g: &Graph, code: usize,
        ordinal: usize, watermark: u64, row: Rc<Row>, cursor: crate::stage_spine::Cursor, known: &QueryFacts) {
        if let Some(id) = self.cell_codes[code].first_read {
            self.stats.fixed_read_probes += 1;
            if self.first_reads.results[id].is_none() {
                let (table, literals) = &self.first_reads.keys[id];
                let key = literals.iter().map(|v| value::canon(v, &g.parents))
                    .collect::<smallvec::SmallVec<[Value; 4]>>();
                self.stats.fixed_key_fields += key.len() as u64;
                // Admission already checked this table. Cache errors too, but
                // deliver them through source-ordered worker error selection.
                let result = g.query_reads(&[], &mut self.stats.admission_table_checks)
                    .ok_or_else(|| "Cell query Run snapshot changed before completion".to_owned())
                    .and_then(|reads| reads.point(*table, &key, &mut self.inline_frame.constructors, &mut self.first_reads.work));
                self.first_reads.results[id] = Some(result);
                self.first_reads.touched.push(id);
                self.stats.fixed_read_fills += 1;
                self.stats.point_reads += 1;
                self.stats.spine_point_reads += 1;
                g.key_lookup_calls.set(g.key_lookup_calls.get() + 1);
            } else { self.stats.fixed_read_hits += 1; }
            if matches!(self.first_reads.results[id], Some(Ok(None))) {
                self.stats.fixed_rejected_entries += 1;
                self.first_reads.rejected += 1;
                return;
            }
        }
        self.enqueue_query(g,code,ordinal,watermark,row,Some(cursor),known,
            #[cfg(feature="parallel-residuals")] false);
    }
    fn enqueue_query(&mut self,g:&Graph,code:usize,ordinal:usize,watermark:u64,row:Rc<Row>,
        cursor:Option<crate::stage_spine::Cursor>,known:&QueryFacts,
        #[cfg(feature="parallel-residuals")] filter:bool) {
        let rid = self.cell_codes[code].rule;
        if self.rule_facts[rid].is_none() { self.rule_facts[rid] = Some(RuleRun { facts: known.clone(), watermark,
            #[cfg(feature="parallel-residuals")] first_source:self.cell_queries.len(), }); }
        debug_assert_eq!(self.rule_facts[rid].as_ref().unwrap().watermark, watermark);
        if self.cell_queries.len() == self.cell_queries.capacity() { self.stats.cell_queue_growths += 1; }
        self.cell_queries.push(CellQuery { code, next: usize::MAX, ordinal, row, cursor,
            #[cfg(feature="parallel-residuals")] filter, });
        // A small Run is one inline task: all of its Cells already stay on one
        // host, so it needs no grouping index. If it grows, activate the queued
        // prefix once, then append each later Entry directly to its Cell task.
        if self.cell_queries.len() == self.grain {
            for source in 0..self.cell_queries.len() { self.group_source(g, source); }
        } else if self.cell_queries.len() > self.grain {
            self.group_source(g, self.cell_queries.len() - 1);
        }
        self.stats.entry_headers += 1;
        self.stats.peak_cell_queue_bytes = self.stats.peak_cell_queue_bytes.max(
            (self.cell_queries.capacity() * std::mem::size_of::<CellQuery>()) as u64);
    }
    fn group_source(&mut self, g: &Graph, source: usize) {
        let q = &self.cell_queries[source];
        let row = &q.row;
        let rid = self.cell_codes[q.code].rule;
        // The actual result's physical Cell selects locality; it is never
        // assumed to be (logical producer, effect position). Unknown boundary
        // functions retain their own identity rather than claiming a Cell.
        self.stats.cell_source_reads += 1;
        let cell = physical_cell(g, row);
        self.tasks.push(cell, source, rid, &mut self.cell_queries, &mut self.stats);
    }
    pub(crate) fn record_completion(&mut self, comparisons: u64, bindings: u64) {
        self.stats.winner_order_comparisons += comparisons;
        self.stats.completion_binding_moves += bindings;
    }
    pub(crate) fn pending_rule(&self, rid: usize) -> bool { self.rule_facts[rid].is_some() }
    pub(crate) fn discard_queries(&mut self, g: &mut Graph, spine: &mut crate::stage_spine::Programs) {
        self.tasks.clear(&mut self.stats);
        for q in self.cell_queries.drain(..) { self.rule_facts[self.cell_codes[q.code].rule] = None; }
        #[cfg(feature="parallel-residuals")]
        self.expansion.discard();
        self.finish_read_accounting(g, spine);
    }
    pub(crate) fn finish_run(&mut self, g: &mut Graph, spine: &mut crate::stage_spine::Programs,
        matches: &mut [(usize, Vec<Binding>)],
        #[cfg(feature="parallel-residuals")] indexes:&crate::query::QueryIndexes,
        #[cfg(feature="parallel-residuals")] sieve:&mut crate::sieve::Sieve,
        #[cfg(feature="parallel-residuals")] entries:&crate::entry_join::Plan) -> Result<()> {
        let outcome = self.finish_queries(g, spine, matches,
            #[cfg(feature="parallel-residuals")] indexes,
            #[cfg(feature="parallel-residuals")] sieve,
            #[cfg(feature="parallel-residuals")] entries);
        if outcome.is_err() {
            self.discard_queries(g, spine);
            spine.discard_query_candidates();
        } else { self.finish_read_accounting(g, spine); }
        outcome
    }
    fn finish_read_accounting(&mut self, g: &mut Graph, spine: &mut crate::stage_spine::Programs) {
        // Also clear an all-negative Run and error paths. A later mutable write,
        // new constructor, visibility change or union must be read anew.
        g.record_constructor_query_work(&self.first_reads.work);
        self.stats.constructors.add(&self.first_reads.work);
        self.first_reads.work = Default::default();
        spine.stats.record_query_worker(&Counts { entries: self.first_reads.rejected,
            steps: self.first_reads.rejected, ..Default::default() });
        self.first_reads.rejected = 0;
        for id in self.first_reads.touched.drain(..) {
            self.first_reads.results[id] = None;
            self.stats.fixed_read_clears += 1;
        }
    }
    fn finish_queries(&mut self, g: &mut Graph, spine: &mut crate::stage_spine::Programs,
        matches: &mut [(usize, Vec<Binding>)],
        #[cfg(feature="parallel-residuals")] indexes:&crate::query::QueryIndexes,
        #[cfg(feature="parallel-residuals")] sieve:&mut crate::sieve::Sieve,
        #[cfg(feature="parallel-residuals")] entries:&crate::entry_join::Plan) -> Result<()> {
        let constructor_groups = self.matched.constructor_groups;
        let mut ready = ready::borrow(g, matches, spine, &mut self.matched);
        if self.cell_queries.is_empty() && ready.is_empty() { return Ok(()); }
        #[cfg(feature="parallel-residuals")]
        let prepared=self.expansion.prepare(indexes,sieve,entries);
        #[cfg(feature="parallel-residuals")]
        let residual_active=!prepared.is_empty();
        #[cfg(not(feature="parallel-residuals"))]
        let residual_active=false;
        let reads = if self.cell_queries.is_empty() && constructor_groups == self.matched.constructor_groups { None }
            else { g.query_reads(&[], &mut self.stats.admission_table_checks) };
        if !self.cell_queries.is_empty() && reads.is_none() {
            return Err("Cell query Run snapshot changed before completion".into());
        }
        // The move-only coordinator records retain the original Entry and
        // cursor. Only small borrowed headers cross the thread boundary.
        let mut ranges = Vec::new();
        let mut headers = Vec::with_capacity(self.cell_queries.len());
        if self.tasks.cells.is_empty() {
            debug_assert!(self.cell_queries.len() < self.grain);
            self.stats.ungrouped_inline_entries += self.cell_queries.len() as u64;
            let mut chunk = Chunk { entries: 0..self.cell_queries.len(), slots: 0, reads: 0 };
            for source in 0..self.cell_queries.len() {
                append_query(source, &self.cell_queries, &self.cell_codes, &mut headers, &mut chunk, &mut self.stats,
                    #[cfg(feature="parallel-residuals")] &self.expansion.ready,
                    #[cfg(feature = "cell-query-sharing-audit")] g);
            }
            if !chunk.entries.is_empty() { ranges.push(chunk); }
        }
        for &template in &self.tasks.active {
            self.stats.active_template_visits += 1;
            let mut chunk = Chunk { entries: headers.len()..headers.len(), slots: 0, reads: 0 };
            let mut task = self.tasks.templates[template].0;
            while task != 0 {
                let cell = &self.tasks.cells[task - 1];
                self.stats.cell_task_emissions += 1;
                self.stats.cell_instances += 1;
                self.stats.multi_entry_cells += u64::from(cell.count > 1);
                self.stats.cross_rule_cells += u64::from(cell.cross_rule);
                self.stats.max_entries_per_cell = self.stats.max_entries_per_cell.max(cell.count as u64);
                let mut source = cell.first;
                while source != usize::MAX {
                    append_query(source, &self.cell_queries, &self.cell_codes, &mut headers, &mut chunk, &mut self.stats,
                        #[cfg(feature="parallel-residuals")] &self.expansion.ready,
                    #[cfg(feature = "cell-query-sharing-audit")] g);
                    source = self.cell_queries[source].next;
                }
                task = cell.next;
                chunk.entries.end = headers.len();
                if chunk.entries.len() >= self.grain || task == 0 {
                    ranges.push(chunk);
                    chunk = Chunk { entries: headers.len()..headers.len(), slots: 0, reads: 0 };
                }
            }
        }
        debug_assert_eq!(headers.len(), self.cell_queries.len());
        // Source indices now live in the borrowed header, not a second vector.
        self.stats.task_order_headers += headers.len() as u64;
        self.stats.borrowed_job_headers += headers.len() as u64;
        self.stats.entry_buffer_bytes += (headers.capacity() * std::mem::size_of::<QueryRead<'_>>()) as u64;
        self.stats.peak_cell_task_bytes = self.stats.peak_cell_task_bytes.max(self.tasks.bytes());
        let key_nodes = g.program.key_nodes();
        let pooled = self.pool.is_some() && headers.len() + ready::instances(&ready) >= self.grain;
        let local=&g.program.executions;
        let templates=&g.program.templates;
        let rule_facts = &self.rule_facts;
        let first_reads = &self.first_reads.results;
        let run = |range: &Chunk, frame: &mut Frame| {
            let reads = reads.as_ref().expect("nonempty query chunk has a Run read view");
            let chunk = &headers[range.entries.clone()];
            let mut counts = Counts { chunks: 1, ..Default::default() };
            frame.prepare(range.slots, range.reads, &mut counts);
            let clock=residual_active.then(Instant::now);
            #[cfg(feature="parallel-residuals")]
            let mut residual=expansion::ChunkWork::default();
            let mut answers = Vec::new();
            let mut first_error = None;
            #[cfg(feature = "cell-query-sharing-audit")]
            let mut probe = sharing_audit::Probe::default();
            for q in chunk {
                let code = q.code;
                let known = rule_facts[code.rule].as_ref().unwrap();
                #[cfg(feature="parallel-residuals")]
                if code.expansion {
                    if let Err(error)=prepared[q.expansion].evaluate(q,&reads,key_nodes,known,frame,&mut residual,&mut answers,&local[code.rule],&templates[code.template]) {
                        let order=query_error_order(q,known);
                        if first_error.as_ref().is_none_or(|(old,_)|order<*old) {first_error=Some((order,error));}
                    }
                    continue;
                }
                counts.entries+=1;
                let entry=Entry {values:&q.row.values,epoch:q.row.epoch,witness:q.row.witness};
                #[cfg(feature = "cell-query-sharing-audit")]
                probe.start(q.audit_cell, q.source, code.rule, code.pivot);
                let answer = evaluate(&code.query, &entry, code.pivot, &reads, key_nodes, true,
                    code.first_read.map(|id| first_reads[id].as_ref().expect("activated first read")),
                    &mut frame.values, &mut frame.witnesses, &mut frame.constructors, &mut counts,
                    #[cfg(feature = "cell-query-sharing-audit")] Some((&mut probe, &code.audit_prefixes)),
                ).map(|epoch| epoch.filter(|&e| e >= known.watermark).map(|epoch| {
                        counts.answers += 1;
                        crate::cell::Matched::matched(
                            local[code.rule].slots(code.inputs.iter().zip(&code.query.inputs).map(|(&slot, f)|
                                (slot, f.operand_in(reads.parents,
                                    |col| &entry.values[col], &frame.values, None).into_owned())),&mut counts.execution),
                            known.facts.with_rows(frame.witnesses.iter().copied()), epoch)
                    }));
                #[cfg(feature = "cell-query-sharing-audit")]
                probe.end(matches!(answer, Ok(Some(_))), answer.is_err());
                match answer {
                    Ok(Some(mut answer)) => {
                        local[code.rule].prepare(&templates[code.template],&mut answer,&mut counts.execution);
                        if let Some(plan) = &local[code.rule].constructor {
                            plan.prepare(&mut answer,Some(&reads),&mut frame.constructors,
                                &mut counts.constructors,&mut counts.execution.constructor);
                        }
                        // Point-only tasks reserve once. Mixed expansions may
                        // return more rows, so also charge subsequent growth.
                        if answers.len() == answers.capacity() {
                            if answers.is_empty() { answers.reserve_exact(chunk.len()); }
                            counts.answer_buffer_allocations += 1;
                        }
                        answers.push((q.source, answer));
                    }
                    Ok(None) => {}
                    Err(error) => {
                        let order=query_error_order(q,known);
                        if first_error.as_ref().is_none_or(|(old,_)|order<*old) {first_error=Some((order,error));}
                    }
                }
            }
            counts.completion_headers = answers.len() as u64;
            #[cfg(feature="parallel-residuals")]
            { residual.counts.frame_capacity_bytes=frame.bytes(); }
            counts.output_buffer_capacity = answers.capacity() as u64;
            counts.frame_capacity_bytes = frame.bytes();
            #[cfg(feature = "cell-query-sharing-audit")]
            { counts.sharing_audit = probe.finish(); }
            (answers, first_error, counts, if pooled { rayon::current_thread_index() } else { None },
                #[cfg(feature="parallel-residuals")] residual,
                clock.map_or(0.0,|clock|clock.elapsed().as_secs_f64()))
        };
        let execution=residual_active.then(Instant::now);
        let grain = self.grain;
        if !ready.is_empty() {
            if headers.is_empty() { self.matched.matched_only_invocations += 1; }
            else { self.matched.mixed_invocations += 1; }
        }
        let (mut chunks, completed): (Vec<_>, _) = if pooled {
            self.pool.as_ref().unwrap().install(|| {
                let queries = || ranges.par_iter().map(|range| with_worker_frame(|frame| run(range, frame))).collect();
                if ready.is_empty() { (queries(), ready::Work::default()) }
                else if ranges.is_empty() { (Vec::new(), ready::parallel(&mut ready, grain, reads.as_ref())) }
                else { rayon::join(queries, || ready::parallel(&mut ready, grain, reads.as_ref())) }
            })
        } else {
            (ranges.iter().map(|range| self.inline_frame.with(|frame| run(range, frame))).collect(),
                ready::inline(&mut ready, grain, reads.as_ref()))
        };
        drop(ready);
        drop(reads);
        g.record_constructor_query_work(&completed.constructors);
        g.key_lookup_calls.set(g.key_lookup_calls.get() + completed.execution.constructor.lookups);
        self.stats.constructors.add(&completed.constructors);
        self.stats.execution.add(&completed.execution);
        self.matched.execution.add(&completed.execution);
        self.matched.instances += completed.instances;
        self.matched.deferred_instances += completed.deferred_instances;
        self.matched.deferred_operations += completed.deferred_operations;
        self.matched.chunks += completed.chunks;
        self.matched.empty_chunks += completed.empty_chunks;
        self.matched.histogram_growths += completed.histogram_growths;
        self.matched.histogram_capacity_bytes += completed.histogram_capacity_bytes;
        let worker_operations = completed.workers.iter().sum::<u64>();
        self.matched.worker_operations += worker_operations;
        self.matched.inline_operations += completed.execution.operations - worker_operations;
        for (worker, operations) in completed.workers.into_iter().enumerate() {
            self.stats.worker_local_operations[worker] += operations;
        }
        for (worker, lookups) in completed.constructor_workers.into_iter().enumerate() {
            self.stats.worker_constructor_lookups[worker] += lookups;
        }
        let elapsed=execution.map_or(0.0,|clock|clock.elapsed().as_secs_f64());
        let header_capacity=headers.capacity();
        drop(headers);
        #[cfg(feature="parallel-residuals")]
        { drop(prepared); self.record_expansion_run(elapsed,pooled,header_capacity); }
        #[cfg(not(feature="parallel-residuals"))]
        let _=(elapsed,header_capacity);
        self.stats.batches += 1;
        // Matched-only work borrows existing rows and has none of these query
        // allocations. Its group headers are charged in matched statistics.
        self.stats.batch_buffers += 3 * u64::from(header_capacity != 0);
        self.stats.completion_error_checks += chunks.len() as u64;
        // Cell grouping reorders queries. Preserve the first source-order
        // error without materializing a completion slot for every failed match.
        let error = chunks.iter_mut().filter_map(|chunk| chunk.1.take()).min_by_key(|(index, _)| *index);
        self.tasks.clear(&mut self.stats);
        if let Some((_, error)) = error {
            for q in self.cell_queries.drain(..) { self.rule_facts[self.cell_codes[q.code].rule] = None; }
            return Err(error);
        }
        for chunk in chunks {
            #[cfg(feature="parallel-residuals")]
            let (answers,_,counts,worker,residual,_seconds)=chunk;
            #[cfg(not(feature="parallel-residuals"))]
            let (answers,_,counts,worker,_seconds)=chunk;
            g.record_constructor_query_work(&counts.constructors);
            self.stats.spine_entries += counts.entries;
            self.stats.spine_point_reads += counts.point_reads;
            spine.stats.record_query_worker(&counts);
            g.key_lookup_calls.set(g.key_lookup_calls.get() + counts.point_reads + counts.execution.constructor.lookups);
            g.stats.key_operations += counts.key_operations;
            self.absorb(&counts, worker);
            self.stats.completion_headers += counts.completion_headers;
            #[cfg(feature="parallel-residuals")]
            self.record_expansion_chunk(g,sieve,residual,worker,_seconds,answers.capacity());
            for (source, mut answer) in answers {
                #[cfg(feature="parallel-residuals")]
                if self.cell_codes[self.cell_queries[source].code].expansion {
                    let q=&self.cell_queries[source];let code=&self.cell_codes[q.code];
                    let (rid,position)=(code.rule,self.expansion_position(code.rule,code.pivot,q.ordinal));
                    self.record_expansion_answer(rid,position,source,answer);
                    continue;
                }
                let q = &mut self.cell_queries[source];
                if self.cell_codes[q.code].inherits_entry && !g.has_visibility_changes(q.row.table)
                    && let Dependency::Fact(parent)=q.row.witness {
                    answer.parent=Some(parent);
                    self.stats.entry_parent_handoffs+=1;
                    spine.stats.record_entry_parent();
                }
                spine.record_worker_answer(self.cell_codes[q.code].rule, q.ordinal, answer,
                    q.cursor.take().expect("one positive completion per Cell query"));
            }
        }
        #[cfg(feature="parallel-residuals")] self.expansion.finished();
        // finish_worker_rule selects by input, depth and original ordinal in
        // one pass. Completion order need not be restored separately.
        // Drop negative cursors and clear even rules with no positive answers.
        for q in self.cell_queries.drain(..) { self.rule_facts[self.cell_codes[q.code].rule] = None; }
        Ok(())
    }
}
