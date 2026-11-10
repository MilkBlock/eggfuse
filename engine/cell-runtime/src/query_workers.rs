//! Execute complete point-query Cell continuations on a borrowed Run view.
//! Entry values stay borrowed; successful bindings move into the original RHS.
use super::*;
use rayon::prelude::*;
use serde::Serialize;
#[cfg(feature = "cell-query-sharing-audit")]
#[path = "query_sharing_audit.rs"]
mod sharing_audit;

#[derive(Default, Serialize)]
pub(crate) struct Counts {
    #[cfg(feature = "cell-query-sharing-audit")]
    pub sharing_audit: sharing_audit::Counts,
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
    pool: Option<rayon::ThreadPool>,
    grain: usize,
    stats: Counts,
    cell_plans: Vec<Option<CellPlan>>,
    cell_codes: Vec<CellCode>,
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
    pub fn use_query_workers(&mut self, workers: usize, grain: usize) -> Result<()> {
        if workers == 0 || grain == 0 { return Err("query workers and grain must be positive".into()); }
        if self.query_workers.is_some() { return Err("query workers already configured".into()); }
        let pool = if workers == 1 { None } else {
            Some(rayon::ThreadPoolBuilder::new().num_threads(workers)
                .thread_name(|i| format!("cell-query-{i}")).build().map_err(|e| e.to_string())?)
        };
        let (cell_plans, cell_codes) = CellPlan::compile(&self.graph.program);
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
        self.query_workers = Some(Workers { pool, grain,
            cell_plans, cell_codes, tasks: CellTasks::new(self.graph.program.templates.len()), cell_queries: Vec::new(),
            rule_facts: (0..self.graph.program.rules.len()).map(|_| None).collect(),
            inline_frame: Frame::default(),
            stats: Counts { compiled_cell_code_bytes, worker_entries: vec![0; workers], worker_steps: vec![0; workers],
                #[cfg(feature = "cell-query-sharing-audit")]
                sharing_audit,
                worker_frame_capacity_bytes: vec![0; workers], ..Default::default() } });
        Ok(())
    }
    pub(super) fn query_worker_report(&self) -> J {
        self.query_workers.as_ref().map_or(json!({"enabled":false}), |w|
            json!({"enabled":true,"workers":w.stats.worker_entries.len(),"grain":w.grain,
                "organization":"cell-run/v4","winner_ordering":"input-depth-ordinal/v1",
                "scope":"source-Run Cell point queries; borrowed slots and constructor domains; ordered RHS unchanged", "stats":w.stats}))
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
        let pooled = workers.pool.is_some();
        let run = |chunk: &[Entry<'_>], frame: &mut Frame| -> Result<(Vec<Binding>, Counts, Option<usize>)> {
            let mut counts = Counts { entries: chunk.len() as u64, chunks: 1,
                ..Default::default() };
            frame.prepare(query.result_slots(), query_width, &mut counts);
            let mut answers = Vec::new();
            for entry in chunk {
                let Some(epoch) = evaluate(query, entry, pivot, &reads, key_nodes, false,
                    &mut frame.values, &mut frame.witnesses, &mut frame.constructors, &mut counts,
                    #[cfg(feature = "cell-query-sharing-audit")] None,
                )? else { continue };
                if answers.len() == answers.capacity() { counts.answer_buffer_allocations += 1; }
                answers.push(Binding {
                    #[cfg(feature="view-consumers")]
                    view_source: None,
                    direct: None,
                    known: known.with_rows(frame.witnesses.iter().copied()),
                    values: input_slots.iter().zip(&query.inputs).map(|(&slot, field)|
                        (slot, field.operand_in(reads.parents, |col| &entry.values[col], &frame.values, None).into_owned())).collect(),
                    epoch, parent: None, continuation: None, compiled: true,
                });
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
            self.graph.key_lookup_calls.set(self.graph.key_lookup_calls.get() + counts.point_reads);
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
    spine: bool, values: &mut [Value], witnesses: &mut Vec<(usize, Dependency)>,
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
        let bound = step.bind::<smallvec::SmallVec<[Value; 4]>>(|field|
            field.operand_in(reads.parents, |col| &entry.values[col], values, None));
        let value = bound.evaluate(|args| match &step.call {
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
        })?;
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
    fn absorb(&mut self, c: &Counts, worker: Option<usize>) {
        #[cfg(feature = "cell-query-sharing-audit")]
        self.stats.sharing_audit.add(&c.sharing_audit);
        self.stats.constructors.add(&c.constructors);
        if let Some(worker) = worker {
            self.stats.worker_entries[worker] += c.entries;
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
    query: crate::cell::SharedQuery,
    inputs: InputSlots,
    rule: usize,
    pivot: usize,
    slots: usize,
    reads: usize,
    #[cfg(feature = "cell-query-sharing-audit")]
    audit_prefixes: Vec<usize>,
}
struct RuleRun { facts: QueryFacts, watermark: u64 }
impl CellPlan {
    fn compile(p: &Program) -> (Vec<Option<Self>>, Vec<CellCode>) {
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
                codes.push(CellCode { rule: rid, pivot, slots: query.result_slots(), reads: query.steps.len() + 1,
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
    code: usize,
    next: usize,
    ordinal: usize,
    row: Rc<Row>,
    cursor: Option<crate::stage_spine::Cursor>,
}
struct QueryRead<'a> {
    source: usize,
    code: &'a CellCode,
    entry: Entry<'a>,
    #[cfg(feature = "cell-query-sharing-audit")]
    audit_cell: (usize, Dependency),
}
struct Chunk {
    entries: std::ops::Range<usize>,
    slots: usize,
    reads: usize,
}
fn append_query<'a>(source: usize, queries: &'a [CellQuery], codes: &'a [CellCode],
    headers: &mut Vec<QueryRead<'a>>, chunk: &mut Chunk, counts: &mut Counts,
    #[cfg(feature = "cell-query-sharing-audit")] g: &Graph) {
    let q = &queries[source];
    let code = &codes[q.code];
    counts.cell_code_reads += 1;
    chunk.slots = chunk.slots.max(code.slots);
    chunk.reads = chunk.reads.max(code.reads);
    headers.push(QueryRead { source, code,
        #[cfg(feature = "cell-query-sharing-audit")]
        audit_cell: physical_cell(g, &q.row),
        entry: Entry { values: &q.row.values, epoch: q.row.epoch, witness: q.row.witness } });
}
#[inline]
fn physical_cell(g: &Graph, row: &Row) -> (usize, Dependency) {
    // Use the actual result's Cell, including foreign constructor reuse.
    let actual = g.origin(row.witness).and_then(|f| {
        g.cells.get(&f.cell).map(|c| (c.template, f.cell))
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
        let rid = self.cell_codes[code].rule;
        if self.rule_facts[rid].is_none() { self.rule_facts[rid] = Some(RuleRun { facts: known.clone(), watermark }); }
        debug_assert_eq!(self.rule_facts[rid].as_ref().unwrap().watermark, watermark);
        if self.cell_queries.len() == self.cell_queries.capacity() { self.stats.cell_queue_growths += 1; }
        self.cell_queries.push(CellQuery { code, next: usize::MAX, ordinal, row, cursor: Some(cursor) });
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
    pub(crate) fn record_deferred_storage(&mut self, serial: usize) {
        self.stats.deferred_winner_moves += serial as u64;
        self.stats.batch_buffers += 2; // serial ordinals and deferred pairs
    }
    pub(crate) fn record_completion(&mut self, comparisons: u64, bindings: u64) {
        self.stats.winner_order_comparisons += comparisons;
        self.stats.completion_binding_moves += bindings;
    }
    pub(crate) fn record_serial_order(&mut self) { self.stats.serial_order_headers += 1; }
    pub(crate) fn pending_rule(&self, rid: usize) -> bool { self.rule_facts[rid].is_some() }
    pub(crate) fn finish_run(&mut self, g: &mut Graph, spine: &mut crate::stage_spine::Programs) -> Result<()> {
        if self.cell_queries.is_empty() { return Ok(()); }
        let reads = g.query_reads(&[], &mut self.stats.admission_table_checks)
            .ok_or("Cell query Run snapshot changed before completion")?;
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
                    #[cfg(feature = "cell-query-sharing-audit")] g);
            }
            ranges.push(chunk);
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
        let pooled = self.pool.is_some() && headers.len() >= self.grain;
        let rule_facts = &self.rule_facts;
        let run = |range: &Chunk, frame: &mut Frame| {
            let chunk = &headers[range.entries.clone()];
            let mut counts = Counts { entries: chunk.len() as u64, chunks: 1, ..Default::default() };
            frame.prepare(range.slots, range.reads, &mut counts);
            let mut answers = Vec::new();
            let mut first_error = None;
            #[cfg(feature = "cell-query-sharing-audit")]
            let mut probe = sharing_audit::Probe::default();
            for q in chunk {
                let code = q.code;
                let known = rule_facts[code.rule].as_ref().unwrap();
                #[cfg(feature = "cell-query-sharing-audit")]
                probe.start(q.audit_cell, q.source, code.rule, code.pivot);
                let answer = evaluate(&code.query, &q.entry, code.pivot, &reads, key_nodes, true,
                    &mut frame.values, &mut frame.witnesses, &mut frame.constructors, &mut counts,
                    #[cfg(feature = "cell-query-sharing-audit")] Some((&mut probe, &code.audit_prefixes)),
                ).map(|epoch| epoch.filter(|&e| e >= known.watermark).map(|epoch| {
                        counts.answers += 1;
                        crate::cell::Matched::matched(
                            code.inputs.iter().zip(&code.query.inputs).map(|(&slot, f)|
                                (slot, f.operand_in(reads.parents,
                                    |col| &q.entry.values[col], &frame.values, None).into_owned())).collect(),
                            known.facts.with_rows(frame.witnesses.iter().copied()), epoch)
                    }));
                #[cfg(feature = "cell-query-sharing-audit")]
                probe.end(matches!(answer, Ok(Some(_))), answer.is_err());
                match answer {
                    Ok(Some(answer)) => {
                        // At most one answer per point-query Entry. Allocate
                        // once on the first hit; all-negative tasks allocate
                        // nothing and dense tasks never grow repeatedly.
                        if answers.capacity() == 0 {
                            answers.reserve_exact(chunk.len());
                            counts.answer_buffer_allocations += 1;
                        }
                        answers.push((q.source, answer));
                    }
                    Ok(None) => {}
                    Err(error) => if first_error.as_ref().is_none_or(|(index, _)| q.source < *index) {
                        first_error = Some((q.source, error));
                    },
                }
            }
            counts.completion_headers = answers.len() as u64;
            counts.output_buffer_capacity = answers.capacity() as u64;
            counts.frame_capacity_bytes = frame.bytes();
            #[cfg(feature = "cell-query-sharing-audit")]
            { counts.sharing_audit = probe.finish(); }
            (answers, first_error, counts, if pooled { rayon::current_thread_index() } else { None })
        };
        let mut chunks: Vec<_> = if pooled {
            self.pool.as_ref().unwrap().install(|| ranges.par_iter().map(|range| with_worker_frame(|frame| run(range, frame))).collect())
        } else { ranges.iter().map(|range| self.inline_frame.with(|frame| run(range, frame))).collect() };
        self.stats.batches += 1;
        self.stats.batch_buffers += 3; // ranges, borrowed headers, chunks
        self.stats.completion_error_checks += chunks.len() as u64;
        // Cell grouping reorders queries. Preserve the first source-order
        // error without materializing a completion slot for every failed match.
        let error = chunks.iter_mut().filter_map(|(_, error, _, _)| error.take()).min_by_key(|(index, _)| *index);
        self.tasks.clear(&mut self.stats);
        if let Some((_, error)) = error {
            for q in self.cell_queries.drain(..) { self.rule_facts[self.cell_codes[q.code].rule] = None; }
            return Err(error);
        }
        for (answers, _, counts, worker) in chunks {
            g.record_constructor_query_work(&counts.constructors);
            self.stats.spine_entries += counts.entries;
            self.stats.spine_point_reads += counts.point_reads;
            spine.stats.record_query_worker(&counts);
            g.key_lookup_calls.set(g.key_lookup_calls.get() + counts.point_reads);
            g.stats.key_operations += counts.key_operations;
            self.absorb(&counts, worker);
            self.stats.completion_headers += counts.completion_headers;
            for (source, answer) in answers {
                let q = &mut self.cell_queries[source];
                spine.record_worker_answer(self.cell_codes[q.code].rule, q.ordinal, answer,
                    q.cursor.take().expect("one positive completion per Cell query"));
            }
        }
        // finish_worker_rule selects by input, depth and original ordinal in
        // one pass. Completion order need not be restored separately.
        // Drop negative cursors and clear even rules with no positive answers.
        for q in self.cell_queries.drain(..) { self.rule_facts[self.cell_codes[q.code].rule] = None; }
        Ok(())
    }
}
