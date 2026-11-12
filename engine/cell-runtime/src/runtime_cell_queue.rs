//! Bounded ready batches for proven independent constructor tails. Source seeds
//! retain their original Cell IDs. A key referring to an unfinished Cell parks
//! the consumer until that earlier tail is registered. No worker waits on it.
use super::*;
use crate::graph::{
    cell_births::{Done, Job},
    rhs_ownership::Suspended,
};
use rayon::prelude::*;

struct Parked {
    execution: owned_cell::Execution,
    context: Suspended,
    job: Option<Job>,
}
const READY_LIMIT: usize = 64;

impl Executor {
    pub(super) fn batch_cell_rule(&self, rid: usize, rows: usize) -> bool {
        rows > 1
            && self.cell_execution.is_some()
            && self
                .query_workers
                .as_ref()
                .and_then(|w| w.execution_pool())
                .is_some()
            && self.graph.local_jobs_supported()
            && self.graph.program.executions[rid]
                .births
                .as_ref()
                .is_some_and(|p| p.batch_rule())
            && !self.stage_spine.has_pending_origins(rid)
            && !self.profile_queries
            && !cfg!(feature = "structural-depth")
            && !cfg!(feature = "family-survey")
    }
    fn finish_attached_cell(&mut self, mut execution: owned_cell::Execution) -> Result<()> {
        loop {
            match self.advance_cell(&mut execution)? {
                owned_cell::Frontier::Boundary(op) => {
                    self.resolve_cell_boundary(&mut execution, op)?
                }
                owned_cell::Frontier::Complete | owned_cell::Frontier::Stopped => {
                    return self.finish_cell(execution);
                }
            }
        }
    }
    fn drain_cell_queue(&mut self, queue: &mut Vec<Parked>, pending: &mut Vec<u32>) -> Result<()> {
        if queue.is_empty() {
            return Ok(());
        }
        let count = queue.iter().filter(|p| p.job.is_some()).count();
        let mut completed = if count != 0 {
            let parents = self.graph.parents.freeze();
            let tasks: Vec<_> = queue
                .iter_mut()
                .filter_map(|p| p.job.take().map(|job| (job, p.execution.effects.writer())))
                .collect();
            let bytes =
                tasks.capacity() * std::mem::size_of::<(Job, crate::cell::EffectWriter<'_>)>();
            let grain = self.cell_execution.as_ref().unwrap().grain;
            let stats = &mut self.cell_execution.as_mut().unwrap().counts;
            stats.births.root_snapshots += 1;
            stats.scheduler.queue_growths += 1;
            stats.scheduler.queue_bytes += bytes as u64;
            stats.scheduler.batches += 1;
            stats.scheduler.jobs += count as u64;
            stats.scheduler.max_ready = stats.scheduler.max_ready.max(count);
            let parallel = tasks.iter().map(|(job, _)| job.operations()).sum::<usize>() >= grain;
            let clock = Instant::now();
            let pool = self
                .query_workers
                .as_ref()
                .unwrap()
                .execution_pool()
                .unwrap();
            let run = |(job, mut effects): (Job, crate::cell::EffectWriter<'_>)| {
                job.run(
                    crate::value::parent_epoch::Read {
                        base: &parents,
                        delta: None,
                    },
                    &mut effects,
                )
            };
            let done: Vec<Done> = if parallel {
                pool.install(|| tasks.into_par_iter().with_min_len(4).map(run).collect())
            } else {
                tasks.into_iter().map(run).collect()
            };
            let elapsed = clock.elapsed().as_nanos() as u64;
            stats.scheduler.wait_ns += elapsed;
            if parallel {
                stats.births.worker_batches += 1;
                stats.births.worker_wait_ns += elapsed;
            }
            stats.scheduler.queue_growths += 1;
            stats.scheduler.queue_bytes += (done.capacity() * std::mem::size_of::<Done>()) as u64;
            drop(parents);
            let work = self.graph.parents.thaw();
            stats.births.root_writes += work.writes;
            stats.births.root_growths += work.growths;
            stats.births.root_merges += work.merged_entries;
            done.into_iter().peekable()
        } else {
            Vec::new().into_iter().peekable()
        };
        for parked in queue.drain(..) {
            let mut execution = parked.execution;
            self.graph.restore_rhs(parked.context);
            if completed
                .peek()
                .is_some_and(|done| done.cell() == execution.cell)
            {
                let done = completed.next().unwrap();
                if let Some(worker) = done.worker {
                    let stats = &mut self.cell_execution.as_mut().unwrap().counts.scheduler;
                    if stats.worker_jobs.len() <= worker {
                        let before = stats.worker_jobs.capacity();
                        stats.worker_jobs.resize(worker + 1, 0);
                        stats.queue_growths += u64::from(before != stats.worker_jobs.capacity());
                        stats.queue_bytes += ((stats.worker_jobs.capacity() - before)
                            * std::mem::size_of::<u64>())
                            as u64;
                    }
                    stats.worker_jobs[worker] += 1;
                }
                let worker = done.worker.is_some();
                let mut counts = self.graph.commit_local_job(done)?;
                execution.work.facts += counts.committed_rows;
                execution.work.constructors += counts.local_births + counts.local_reuses;
                if worker {
                    counts.worker_operations += counts.local_births + counts.local_reuses;
                }
                self.cell_execution
                    .as_mut()
                    .unwrap()
                    .counts
                    .births
                    .add(counts);
            }
            self.finish_attached_cell(execution)?;
            self.graph.sealed_input_cell = None;
            self.graph.sealed_generation = None;
        }
        debug_assert!(completed.next().is_none());
        pending.clear();
        Ok(())
    }
    pub(super) fn apply_cell_batch(
        &mut self,
        rid: usize,
        rows: Vec<Binding>,
        generation: u64,
    ) -> Result<()> {
        self.cell_execution
            .as_mut()
            .unwrap()
            .counts
            .scheduler
            .rule_groups += 1;
        let mut queue: Vec<Parked> = Vec::new();
        let mut pending = Vec::new();
        let result = (|| {
            for binding in rows {
                // Existing inherited histories keep their direct source path. They
                // are not replaced with speculative completion or a duplicate log.
                if binding.direct.is_some() || binding.continuation.is_some() {
                    self.drain_cell_queue(&mut queue, &mut pending)?;
                    self.graph.sealed_generation = Some(generation);
                    self.apply(
                        rid,
                        binding,
                        #[cfg(feature = "structural-depth")]
                        None,
                    )?;
                    self.graph.sealed_input_cell = None;
                    self.graph.sealed_generation = None;
                    continue;
                }
                self.graph.sealed_generation = Some(generation);
                let started = self.start_cell_execution(
                    rid,
                    binding,
                    &pending,
                    #[cfg(feature = "structural-depth")]
                    None,
                )?;
                let Some(mut execution) = started else {
                    self.graph.sealed_input_cell = None;
                    self.graph.sealed_generation = None;
                    continue;
                };
                self.cell_execution
                    .as_mut()
                    .unwrap()
                    .counts
                    .scheduler
                    .instances += 1;
                loop {
                    let position = self
                        .graph
                        .rhs_frame(execution.cell)
                        .unwrap()
                        .completed_prefix;
                    if position == execution.ops.len() {
                        if queue.is_empty() {
                            self.finish_attached_cell(execution)?;
                        } else {
                            self.park_cell(&mut queue, execution, None);
                        }
                        break;
                    }
                    if execution.births.is_some() {
                        let stop = execution.transfers[execution.transfer..]
                            .iter()
                            .find(|t| t.op >= position)
                            .map_or(execution.ops.len(), |t| t.op);
                        let (counts, job) = self.graph.take_local_job(
                            rid,
                            execution.cell,
                            &mut execution.births,
                            stop,
                            true,
                        )?;
                        self.cell_execution
                            .as_mut()
                            .unwrap()
                            .counts
                            .births
                            .add(counts);
                        if let Some(job) = job {
                            let before = pending.capacity();
                            pending.push(execution.cell);
                            let stats = &mut self.cell_execution.as_mut().unwrap().counts.scheduler;
                            stats.queue_growths += u64::from(before != pending.capacity());
                            stats.queue_bytes +=
                                ((pending.capacity() - before) * std::mem::size_of::<u32>()) as u64;
                            self.park_cell(&mut queue, execution, Some(job));
                            break;
                        }
                        if matches!(&execution.ops[position], Op::Let(_, Call::Table(_), _))
                            && !execution.aliases.as_ref().is_some_and(|a| a[position])
                        {
                            // Retain the ordinary local-dedup path when isolation is
                            // unproved. It can still reuse equal dynamic keys inside
                            // this one Cell; the queue must not replace it with replays.
                            if !queue.is_empty() {
                                let state = self.graph.suspend_rhs(execution.cell);
                                self.drain_cell_queue(&mut queue, &mut pending)?;
                                self.graph.restore_rhs(state);
                                if let Some(window) = &mut execution.births {
                                    window.after_isolated_batch(&self.graph);
                                    self.cell_execution
                                        .as_mut()
                                        .unwrap()
                                        .counts
                                        .scheduler
                                        .revalidations += 1;
                                }
                            }
                            self.finish_attached_cell(execution)?;
                            break;
                        }
                    }
                    if !pending.is_empty()
                        && let Op::Let(_, Call::Table(_), args) = &execution.ops[position]
                    {
                        let key = self.graph.inline_arguments(execution.cell, args)?;
                        self.cell_execution
                            .as_mut()
                            .unwrap()
                            .counts
                            .scheduler
                            .operand_reads += key.len() as u64;
                        if key.spilled() {
                            let stats = &mut self.cell_execution.as_mut().unwrap().counts.scheduler;
                            stats.queue_growths += 1;
                            stats.queue_bytes +=
                                (key.capacity() * std::mem::size_of::<Value>()) as u64;
                        }
                        let (probes, blocked) = crate::graph::cell_births::blocked(&key, &pending);
                        self.graph.stats.rhs_pending_probes += probes;
                        if blocked {
                            self.graph.stats.rhs_pending_stops += 1;
                            self.cell_execution
                                .as_mut()
                                .unwrap()
                                .counts
                                .scheduler
                                .dependency_flushes += 1;
                            let state = self.graph.suspend_rhs(execution.cell);
                            self.drain_cell_queue(&mut queue, &mut pending)?;
                            self.graph.restore_rhs(state);
                        }
                    }
                    if !pending.is_empty()
                        && matches!(&execution.ops[position], Op::Set(..) | Op::Union(..))
                    {
                        self.cell_execution
                            .as_mut()
                            .unwrap()
                            .counts
                            .scheduler
                            .effect_flushes += 1;
                        let state = self.graph.suspend_rhs(execution.cell);
                        self.drain_cell_queue(&mut queue, &mut pending)?;
                        self.graph.restore_rhs(state);
                    }
                    execution.phase = owned_cell::Phase::Boundary;
                    self.resolve_cell_boundary(&mut execution, position)?;
                }
                if queue.len() >= READY_LIMIT {
                    self.drain_cell_queue(&mut queue, &mut pending)?;
                }
                self.graph.sealed_input_cell = None;
                self.graph.sealed_generation = None;
            }
            Ok(())
        })();
        // Earlier infallible tails must finish even when admission of a later
        // source instance fails (for example, exhausted Cell identities).
        if result.is_err() {
            self.graph.promote_active();
        }
        self.drain_cell_queue(&mut queue, &mut pending)?;
        result
    }
    fn park_cell(
        &mut self,
        queue: &mut Vec<Parked>,
        execution: owned_cell::Execution,
        job: Option<Job>,
    ) {
        let context = self.graph.suspend_rhs(execution.cell);
        let before = queue.capacity();
        queue.push(Parked {
            execution,
            context,
            job,
        });
        let stats = &mut self.cell_execution.as_mut().unwrap().counts.scheduler;
        stats.queue_growths += u64::from(before != queue.capacity());
        stats.queue_bytes += ((queue.capacity() - before) * std::mem::size_of::<Parked>()) as u64;
    }
}
