//! Execute complete point-query Cell continuations on a borrowed Run view.
//! Entry values stay borrowed; successful bindings move into the original RHS.
use super::*;
use rayon::prelude::*;
use serde::Serialize;

#[derive(Default, Serialize)]
pub(crate) struct Counts {
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
            stats: Counts { worker_entries: vec![0; workers], ..Default::default() } });
        Ok(())
    }
    pub(super) fn query_worker_report(&self) -> J {
        self.query_workers.as_ref().map_or(json!({"enabled":false}), |w|
            json!({"enabled":true,"workers":w.stats.worker_entries.len(),"grain":w.grain,
                "scope":"source-Run Cell function-point queries; borrowed slots; ordered RHS unchanged", "stats":w.stats}))
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
        let Some(tables) = &kernel.function_points else { return Ok(false) };
        let Some(reads) = self.graph.query_function_reads(tables, &mut workers.stats.admission_table_checks)
            else { return Ok(false) };
        workers.stats.seed_selection_visits += seeds.len() as u64;
        if seeds.iter().filter(|s| s.atom() == kernel.pivot).count() < workers.grain { return Ok(false); }
        workers.stats.seed_selection_visits += seeds.len() as u64;
        let entries: Vec<_> = seeds.iter().filter(|s| s.atom() == kernel.pivot)
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
        let run = |chunk: &[Entry<'_>]| -> Result<(Vec<Binding>, Counts, usize)> {
            let mut results = vec![Value::Int(0); query.result_slots()];
            let mut witnesses = vec![None; query_width];
            let mut counts = Counts { entries: chunk.len() as u64, chunks: 1,
                frame_allocations: u64::from(!results.is_empty()) + u64::from(!witnesses.is_empty()),
                ..Default::default() };
            let mut answers = Vec::new();
            for entry in chunk {
                let Some(epoch) = evaluate(query, entry, pivot, &reads, key_nodes, false,
                    &mut results, &mut witnesses, &mut counts)? else { continue };
                if answers.len() == answers.capacity() { counts.answer_buffer_allocations += 1; }
                answers.push(Binding {
                    #[cfg(feature="view-consumers")]
                    view_source: None,
                    direct: None,
                    known: known.with_rows(witnesses.iter().enumerate().filter_map(|(a, &w)| w.map(|w| (a,w)))),
                    values: input_slots.iter().zip(&query.inputs).map(|(&slot, field)|
                        (slot, field.operand_in(reads.parents, |col| &entry.values[col], &results, None).into_owned())).collect(),
                    epoch, parent: None, continuation: None, compiled: true,
                });
            }
            counts.answers = answers.len() as u64;
            counts.output_buffer_capacity = answers.capacity() as u64;
            Ok((answers, counts, if pooled { rayon::current_thread_index().unwrap() } else { 0 }))
        };
        // Indexed collection preserves pivot/Entry order, including first-error
        // selection. The borrow ends before any source effect can mutate slots.
        let completed: Vec<_> = if let Some(pool) = &workers.pool {
            pool.install(|| entries.par_chunks(workers.grain).map(run).collect())
        } else { entries.chunks(workers.grain).map(run).collect() };
        workers.stats.batches += 1;
        workers.stats.batch_buffers += 2;
        workers.stats.entry_headers += entries.len() as u64;
        workers.stats.entry_buffer_bytes += (entries.capacity() * std::mem::size_of::<Entry<'_>>()) as u64;
        for result in completed {
            let (mut answers, counts, worker) = result?;
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
    reads: &crate::graph::function_reads::FunctionReads<'_>, key_nodes: &J,
    spine: bool, values: &mut [Value], witnesses: &mut [Option<Dependency>], counts: &mut Counts,
) -> Result<Option<u64>> {
    witnesses[pivot] = Some(entry.witness);
    let owner = (entry.epoch, entry.witness);
    let mut epoch = entry.epoch;
    for (pc, step) in query.steps.iter().enumerate() {
        counts.steps += 1;
        let bound = step.bind::<smallvec::SmallVec<[Value; 4]>>(|field|
            field.operand_in(reads.parents, |col| &entry.values[col], values, None));
        let value = bound.evaluate(|args| match &step.call {
            Call::Table(t) => {
                counts.point_reads += 1;
                let Some((v, stamp, witness)) = reads.point(*t, &args) else { return Ok(None) };
                if !spine && ((stamp, witness) > owner || ((stamp, witness) == owner && step.atom < pivot)) {
                    counts.owner_rejections += 1;
                    return Ok(None);
                }
                epoch = epoch.max(stamp);
                witnesses[step.atom] = Some(witness);
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
    fn absorb(&mut self, c: &Counts, worker: usize) {
        self.stats.worker_entries[worker] += c.entries;
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
    pub(crate) fn should_buffer(&self, entries: usize) -> bool {
        entries >= self.grain && !cfg!(feature="structural-depth")
            && !cfg!(feature="family-overlap") && !cfg!(feature="family-survey")
    }
    pub(crate) fn spine_batch(
        &mut self, g: &mut Graph, queries: &crate::cell::Queries, rid: usize,
        ready: &[(usize, Rc<Row>, crate::stage_spine::Cursor)], capacity: usize, local: &[bool], watermark: u64,
        known: &QueryFacts, stats: &mut crate::stage_spine::Stats,
    ) -> Result<Vec<(usize, Result<Option<crate::cell::Matched>>)>> {
        if ready.is_empty() { return Ok(Vec::new()); }
        // The coordinator's original cursors stay here. Workers borrow only
        // Entry values, immutable instructions and authoritative function slots.
        self.stats.batch_buffers += 1; // buffered source entries
        self.stats.entry_buffer_bytes += (capacity * std::mem::size_of_val(&ready[0])) as u64;
        let Some(reads) = g.query_function_reads(&[], &mut self.stats.admission_table_checks)
            else { return Ok(Vec::new()) };
        let mut admitted = vec![None; g.program.rules[rid].query.len()];
        self.stats.batch_buffers += 1;
        let entries: Vec<_> = ready.iter().enumerate().filter_map(|(ordinal, (pivot, row, cursor))| {
            self.stats.admission_entry_checks += 1;
            let yes = *admitted[*pivot].get_or_insert_with(|| {
                !local[*pivot] && queries.function_points(rid, *pivot).is_some_and(|tables|
                    !tables.is_empty() && g.query_function_reads(tables, &mut self.stats.admission_table_checks).is_some())
            });
            (yes && cursor.uncached_query()).then(|| (ordinal, *pivot,
                queries.get(rid, *pivot).unwrap().as_ref(),
                Entry { values: &*row.values, epoch: row.epoch, witness: row.witness }))
        }).collect();
        self.stats.entry_headers += entries.len() as u64;
        self.stats.batch_buffers += u64::from(entries.capacity() != 0);
        self.stats.entry_buffer_bytes += (entries.capacity() * std::mem::size_of::<(usize,usize,&crate::cell::Query,Entry<'_>)>()) as u64;
        if entries.len() < self.grain { return Ok(Vec::new()); }
        let width = g.program.rules[rid].query.len();
        let key_nodes = g.program.key_nodes();
        let pooled = self.pool.is_some();
        let run = |chunk: &[(usize, usize, &crate::cell::Query, Entry<'_>)]| {
            let max_slots = chunk.iter().map(|(_,_,q,_)| q.result_slots()).max().unwrap_or(0);
            let mut values = vec![Value::Int(0); max_slots];
            let mut witnesses = vec![None; width];
            let mut counts = Counts { entries: chunk.len() as u64, chunks: 1,
                frame_allocations: u64::from(max_slots != 0) + u64::from(width != 0),
                answer_buffer_allocations: 1, ..Default::default() };
            let mut answers = Vec::with_capacity(chunk.len());
            for (ordinal, pivot, query, entry) in chunk {
                let answer = evaluate(query, entry, *pivot, &reads, key_nodes, true,
                    &mut values, &mut witnesses, &mut counts).map(|epoch| epoch.filter(|&e| e >= watermark).map(|epoch| {
                        counts.answers += 1;
                        crate::cell::Matched {
                            direct: None, epoch,
                            values: query.inputs.iter().map(|f| f.operand_in(reads.parents,
                                |col| &entry.values[col], &values, None).into_owned()).collect(),
                            facts: known.with_rows(witnesses.iter().enumerate().filter_map(|(a, &w)| w.map(|w| (a,w)))),
                        }
                    }));
                answers.push((*ordinal, answer));
            }
            counts.output_buffer_capacity = answers.capacity() as u64;
            (answers, counts, if pooled { rayon::current_thread_index().unwrap() } else { 0 })
        };
        let chunks: Vec<_> = if let Some(pool) = &self.pool {
            pool.install(|| entries.par_chunks(self.grain).map(run).collect())
        } else { entries.chunks(self.grain).map(run).collect() };
        self.stats.batches += 1;
        self.stats.batch_buffers += 2; // chunk directory and ordered completion buffer
        let mut completed = Vec::with_capacity(entries.len());
        for (mut answers, counts, worker) in chunks {
            self.stats.spine_entries += counts.entries;
            self.stats.spine_point_reads += counts.point_reads;
            stats.record_query_worker(&counts);
            // Count actual key reads, but no Row decoding/cache path or
            // pre-resume serial read occurred. No logical lookup is "saved".
            g.key_lookup_calls.set(g.key_lookup_calls.get() + counts.point_reads);
            g.stats.key_operations += counts.key_operations;
            self.absorb(&counts, worker);
            completed.append(&mut answers);
        }
        Ok(completed)
    }
}
