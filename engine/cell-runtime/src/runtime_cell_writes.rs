//! Worker-owned scalar RHS batches. Source cursors remain on their owner;
//! workers receive the existing instances and write actual destination rows.
use super::*;
use crate::graph::cell_writes::Task as WriteTask;
use rayon::prelude::*;

impl Executor {
    pub(super) fn batch_write_rule(&self, rid: usize, rows: &[Binding]) -> bool {
        rows.len() >= 32
            && self.cell_execution.is_some()
            && self
                .query_workers
                .as_ref()
                .and_then(|w| w.execution_pool())
                .is_some()
            && self.graph.worker_write_supported(rid)
            && self.graph.worker_write_capacity(rows.len())
            && !self.stage_spine.has_pending_origins(rid)
            && !self.graph.needs_ownership_entry(rid)
            && !self.graph.program.iterative.tracks_slots()
            && self.completion.is_none()
            && !self.profile_queries
            && !cfg!(feature = "structural-depth")
            && !cfg!(feature = "family-survey")
            && rows.iter().all(|b| {
                self.graph.worker_write_parent(b.parent)
                    && b.direct.is_none()
                    && b.continuation.is_none()
            })
    }

    pub(super) fn apply_worker_writes(
        &mut self,
        rid: usize,
        mut rows: Vec<Binding>,
    ) -> Result<Option<Vec<Binding>>> {
        let write = self.graph.program.writes[rid].as_ref().unwrap().clone();
        let ports = write.ports.as_ref().unwrap();
        let prefix = write.prefix.last().copied();
        let clock = Instant::now();
        let parents = self.graph.parents.reader();
        let pool = self
            .query_workers
            .as_ref()
            .unwrap()
            .execution_pool()
            .unwrap();
        // Total reads continue directly through mutation in one worker batch.
        // Only unchecked arithmetic needs a speculative preparation barrier.
        let direct = prefix.is_none_or(|op| rows.iter().all(|b| op < b.prepared));
        let prepared: Vec<_> = if direct {
            Vec::new()
        } else {
            pool.install(|| {
                rows.par_iter_mut()
                    .with_min_len(32)
                    .map(|b| {
                        ports.project_read(
                            &b.values,
                            parents,
                            prefix.is_some_and(|op| op < b.prepared),
                        )
                    })
                    .collect()
            })
        };
        let counts = &mut self.cell_execution.as_mut().unwrap().writes;
        counts.preparation_ns += clock.elapsed().as_nanos() as u64;
        counts.worker_candidates += rows.len() as u64;
        counts.temporary_bytes += (prepared.capacity()
            * std::mem::size_of::<Result<(Value, i64, Option<usize>)>>())
            as u64;
        if prepared.iter().any(Result::is_err) {
            counts.fallback_batches += 1;
            return Ok(Some(rows));
        }
        counts.batches += 1;
        counts.direct_batches += u64::from(direct);
        counts.candidates += rows.len() as u64;
        let clock = Instant::now();
        let mut contexts = rows
            .iter()
            .any(|b| !matches!(b.known, QueryFacts::None))
            .then(|| Vec::with_capacity(rows.len()));
        let mut tasks = Vec::with_capacity(rows.len());
        let mut projections = prepared.into_iter();
        let template = self.graph.program.rules[rid].template;
        for (ordinal, b) in rows.into_iter().enumerate() {
            #[cfg(feature = "slot-transfer-audit")]
            crate::transfer_audit::rhs(rid);
            self.continuation_stats.compiled_bindings += u64::from(b.compiled);
            self.graph.stats.prepared_rhs_operations += self.graph.program.executions[rid]
                .prepared_operations(&self.graph.program.templates[template], b.prepared)
                as u64;
            let (key, value, destination) = if direct {
                (
                    ports.project_key(&b.values, self.graph.parents.reader())?,
                    0,
                    None,
                )
            } else {
                projections.next().unwrap().unwrap()
            };
            #[allow(unused_mut)]
            let mut task = WriteTask::new(b.values, key, value, destination, ordinal);
            task.parent = b.parent;
            #[cfg(feature = "slot-transfer-audit")]
            {
                task.source = crate::transfer_audit::suspend_source();
            }
            if let Some(contexts) = &mut contexts {
                contexts.push(b.known);
            }
            tasks.push(task);
        }
        let counts = &mut self.cell_execution.as_mut().unwrap().writes;
        counts.source_completion_ns += clock.elapsed().as_nanos() as u64;
        counts.temporary_bytes += (tasks.capacity() * std::mem::size_of::<WriteTask>()
            + contexts
                .as_ref()
                .map_or(0, |v| v.capacity() * std::mem::size_of::<QueryFacts>()))
            as u64;
        self.graph.write_cells(
            rid,
            &mut tasks,
            pool,
            counts,
            direct.then_some(prefix.is_some()),
        )?;
        let clock = Instant::now();
        // Only source completion/publication remains here. The actual values,
        // decoded rows and final writer slots have already been installed.
        let mut contexts = contexts.into_iter().flatten();
        for task in tasks {
            let known = contexts.next().unwrap_or_default();
            let step = self.stage_spine.begin_root(
                &self.graph.program,
                rid,
                &self.current_stage,
                self.graph.epoch,
            );
            #[cfg(feature = "slot-transfer-audit")]
            task.audit(self.graph.epoch, write.table)?;
            if let Some(step) = step {
                self.stage_spine.effects(0, u64::from(task.changed), 0);
                let step = if !task.changed {
                    let Some(step) = self.stage_spine.complete_absorbed_root(
                        &self.graph,
                        rid,
                        task.cell,
                        step,
                        &write,
                        task.index,
                        &mut self.entry_schedule,
                    )?
                    else {
                        continue;
                    };
                    step
                } else {
                    step
                };
                self.stage_spine.complete(
                    &self.graph,
                    rid,
                    task.cell,
                    step,
                    |i| known.receipt(i),
                    crate::cell::SingleEffect(write.op, Dependency::Function(task.index)),
                    |_| Ok(vec![task.key.clone()]),
                )?;
            }
        }
        self.cell_execution
            .as_mut()
            .unwrap()
            .writes
            .source_completion_ns += clock.elapsed().as_nanos() as u64;
        Ok(None)
    }
}
