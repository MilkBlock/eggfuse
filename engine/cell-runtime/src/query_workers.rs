//! Execute complete point-query Cell continuations on a borrowed Run view.
//! Entry values stay borrowed; successful bindings move into the original RHS.
use super::*;
use rayon::prelude::*;
use serde::Serialize;

#[derive(Default, Serialize)]
pub(crate) struct Counts {
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
    cell_queries: Vec<CellQuery>,
    rule_facts: Vec<Option<QueryFacts>>,
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
        self.query_workers = Some(Workers { pool, grain,
            cell_plans: CellPlan::compile(&self.graph.program), cell_queries: Vec::new(),
            rule_facts: (0..self.graph.program.rules.len()).map(|_| None).collect(),
            inline_frame: Frame::default(),
            stats: Counts { worker_entries: vec![0; workers], worker_steps: vec![0; workers],
                worker_frame_capacity_bytes: vec![0; workers], ..Default::default() } });
        Ok(())
    }
    pub(super) fn query_worker_report(&self) -> J {
        self.query_workers.as_ref().map_or(json!({"enabled":false}), |w|
            json!({"enabled":true,"workers":w.stats.worker_entries.len(),"grain":w.grain,
                "organization":"cell-run/v3","scope":"source-Run Cell point queries; borrowed slots and constructor domains; ordered RHS unchanged", "stats":w.stats}))
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
                    &mut frame.values, &mut frame.witnesses, &mut frame.constructors, &mut counts)? else { continue };
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
) -> Result<Option<u64>> {
    witnesses.clear();
    witnesses.push((pivot, entry.witness));
    let owner = (entry.epoch, entry.witness);
    let mut epoch = entry.epoch;
    for (pc, step) in query.steps.iter().enumerate() {
        counts.steps += 1;
        let bound = step.bind::<smallvec::SmallVec<[Value; 4]>>(|field|
            field.operand_in(reads.parents, |col| &entry.values[col], values, None));
        let value = bound.evaluate(|args| match &step.call {
            Call::Table(t) => {
                counts.point_reads += 1;
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
    entries: Vec<bool>,
    tables: Box<[usize]>,
}
impl CellPlan {
    fn compile(p: &Program) -> Vec<Option<Self>> {
        let mut local = p.rules.iter().map(|r| vec![false; r.query.len()]).collect::<Vec<_>>();
        for route in p.multi_stage.routes.values() {
            local[route.consumer][route.anchor] |= route.reads.iter().any(|r| r.witness.is_some());
        }
        p.rules.iter().enumerate().map(|(rid, r)| {
            let mut tables = BTreeSet::new();
            let entries = (0..r.query.len()).map(|pivot| {
                if local[rid][pivot] { return false; }
                let Some(points) = p.cell_queries.point_tables(rid, pivot).filter(|p| !p.is_empty()) else { return false };
                tables.extend(points.iter().copied());
                true
            }).collect::<Vec<_>>();
            entries.iter().any(|&v| v).then(|| Self { entries, tables: tables.into_iter().collect() })
        }).collect()
    }
}
struct CellQuery {
    cell: (usize, Dependency),
    rule: usize,
    pivot: usize,
    ordinal: usize,
    watermark: u64,
    row: Rc<Row>,
    cursor: Option<crate::stage_spine::Cursor>,
}
struct QueryRead<'a> {
    query: &'a crate::cell::Query,
    known: &'a QueryFacts,
    pivot: usize,
    watermark: u64,
    entry: Entry<'a>,
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
    pub(crate) fn spine_entry(&mut self, rid: usize, pivot: usize, cursor: &crate::stage_spine::Cursor) -> bool {
        self.stats.entry_mask_checks += 1;
        if !self.cell_plans[rid].as_ref().unwrap().entries[pivot] { return false; }
        self.stats.admission_entry_checks += 1;
        cursor.uncached_query()
    }
    pub(crate) fn enqueue_spine(&mut self, g: &Graph, rid: usize, pivot: usize,
        ordinal: usize, watermark: u64, row: Rc<Row>, cursor: crate::stage_spine::Cursor, known: &QueryFacts) {
        if self.rule_facts[rid].is_none() { self.rule_facts[rid] = Some(known.clone()); }
        // The actual result's physical Cell selects locality; it is never
        // assumed to be (logical producer, effect position). Unknown boundary
        // functions retain their own identity rather than claiming a Cell.
        self.stats.cell_source_reads += 1;
        let actual = g.origin(row.witness).and_then(|f| {
            g.cells.get(&f.cell).map(|c| (c.template, f.cell))
                .or_else(|| g.continuation_context(row.witness)
                    .filter(|c| c.cell == f.cell).map(|c| (c.template, c.cell)))
        });
        let cell = actual.map_or((g.program.table_templates[row.table], row.witness),
            |(template, cell)| (template, Dependency::Fact(FactRef { cell, op: 0 })));
        if self.cell_queries.len() == self.cell_queries.capacity() { self.stats.cell_queue_growths += 1; }
        self.cell_queries.push(CellQuery { cell, rule: rid, pivot, ordinal, watermark, row, cursor: Some(cursor) });
        self.stats.entry_headers += 1;
        self.stats.peak_cell_queue_bytes = self.stats.peak_cell_queue_bytes.max(
            (self.cell_queries.capacity() * std::mem::size_of::<CellQuery>()) as u64);
    }
    pub(crate) fn record_deferred_storage(&mut self, serial: usize) {
        self.stats.deferred_winner_moves += serial as u64;
        self.stats.batch_buffers += 3; // serial ordinals, deferred pairs, restored winners
    }
    pub(crate) fn record_completion(&mut self, comparisons: u64, winners: u64, bindings: u64) {
        self.stats.winner_order_comparisons += comparisons;
        self.stats.deferred_winner_moves += winners;
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
        let mut comparisons = 0;
        let mut order: Vec<_> = (0..self.cell_queries.len()).collect();
        self.stats.task_order_headers += order.len() as u64;
        order.sort_unstable_by(|&a,&b| {
            comparisons += 1;
            self.cell_queries[a].cell.cmp(&self.cell_queries[b].cell).then_with(|| a.cmp(&b))
        });
        self.stats.cell_order_comparisons += comparisons;
        let mut ranges = Vec::new();
        let mut start = 0;
        let mut cell_start = 0;
        for i in 1..=self.cell_queries.len() {
            let end = i == self.cell_queries.len();
            let new_cell = end || self.cell_queries[order[i]].cell != self.cell_queries[order[cell_start]].cell;
            if new_cell {
                self.stats.cell_instances += 1;
                self.stats.multi_entry_cells += u64::from(i - cell_start > 1);
                self.stats.cross_rule_cells += u64::from(order[cell_start..i].iter()
                    .any(|&q| self.cell_queries[q].rule != self.cell_queries[order[cell_start]].rule));
                self.stats.max_entries_per_cell = self.stats.max_entries_per_cell.max((i - cell_start) as u64);
                cell_start = i;
            }
            if end || (new_cell && (i - start >= self.grain
                || self.cell_queries[order[i]].cell.0 != self.cell_queries[order[start]].cell.0)) {
                ranges.push(start..i);
                start = i;
            }
        }
        let headers = order.iter().map(|&i| &self.cell_queries[i]).map(|q| QueryRead {
            query: g.program.cell_queries.get(q.rule, q.pivot).unwrap().as_ref(),
            known: self.rule_facts[q.rule].as_ref().unwrap(), pivot: q.pivot, watermark: q.watermark,
            entry: Entry { values: &q.row.values, epoch: q.row.epoch, witness: q.row.witness },
        }).collect::<Vec<_>>();
        self.stats.borrowed_job_headers += headers.len() as u64;
        self.stats.entry_buffer_bytes += (headers.capacity() * std::mem::size_of::<QueryRead<'_>>()) as u64;
        let key_nodes = g.program.key_nodes();
        let pooled = self.pool.is_some() && headers.len() >= self.grain;
        let run = |range: &std::ops::Range<usize>, frame: &mut Frame| {
            let chunk = &headers[range.clone()];
            let max_slots = chunk.iter().map(|q| q.query.result_slots()).max().unwrap_or(0);
            let max_reads = chunk.iter().map(|q| q.query.steps.len() + 1).max().unwrap_or(0);
            let mut counts = Counts { entries: chunk.len() as u64, chunks: 1, ..Default::default() };
            frame.prepare(max_slots, max_reads, &mut counts);
            let mut answers = Vec::new();
            let mut first_error = None;
            for (&source, q) in order[range.clone()].iter().zip(chunk) {
                let answer = evaluate(q.query, &q.entry, q.pivot, &reads, key_nodes, true,
                    &mut frame.values, &mut frame.witnesses, &mut frame.constructors, &mut counts).map(|epoch| epoch.filter(|&e| e >= q.watermark).map(|epoch| {
                        counts.answers += 1;
                        crate::cell::Matched { direct: None, epoch,
                            values: q.query.inputs.iter().map(|f| f.operand_in(reads.parents,
                                |col| &q.entry.values[col], &frame.values, None).into_owned()).collect(),
                            facts: q.known.with_rows(frame.witnesses.iter().copied()),
                        }
                    }));
                match answer {
                    Ok(Some(answer)) => {
                        // At most one answer per point-query Entry. Allocate
                        // once on the first hit; all-negative tasks allocate
                        // nothing and dense tasks never grow repeatedly.
                        if answers.capacity() == 0 {
                            answers.reserve_exact(chunk.len());
                            counts.answer_buffer_allocations += 1;
                        }
                        answers.push((source, answer));
                    }
                    Ok(None) => {}
                    Err(error) => if first_error.as_ref().is_none_or(|(index, _)| source < *index) {
                        first_error = Some((source, error));
                    },
                }
            }
            counts.completion_headers = answers.len() as u64;
            counts.output_buffer_capacity = answers.capacity() as u64;
            counts.frame_capacity_bytes = frame.bytes();
            (answers, first_error, counts, if pooled { rayon::current_thread_index() } else { None })
        };
        let mut chunks: Vec<_> = if pooled {
            self.pool.as_ref().unwrap().install(|| ranges.par_iter().map(|range| with_worker_frame(|frame| run(range, frame))).collect())
        } else { ranges.iter().map(|range| self.inline_frame.with(|frame| run(range, frame))).collect() };
        self.stats.batches += 1;
        self.stats.batch_buffers += 4; // order, ranges, borrowed headers, chunks
        self.stats.completion_error_checks += chunks.len() as u64;
        // Cell grouping reorders queries. Preserve the first source-order
        // error without materializing a completion slot for every failed match.
        let error = chunks.iter_mut().filter_map(|(_, error, _, _)| error.take()).min_by_key(|(index, _)| *index);
        if let Some((_, error)) = error {
            for q in self.cell_queries.drain(..) { self.rule_facts[q.rule] = None; }
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
                spine.record_worker_answer(q.rule, q.ordinal, answer,
                    q.cursor.take().expect("one positive completion per Cell query"));
            }
        }
        // finish_worker_rule already restores each rule's source ordinals
        // before winner selection. No second, dense reorder is necessary.
        // Drop negative cursors and clear even rules with no positive answers.
        for q in self.cell_queries.drain(..) { self.rule_facts[q.rule] = None; }
        Ok(())
    }
}
