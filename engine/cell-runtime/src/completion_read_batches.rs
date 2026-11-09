//! Parallel reads across ordered completion tasks. The compiler's complete
//! scalar key footprint supplies a transient read set. A derived union touching
//! either side of a future input class invalidates that suffix, even when its
//! representative number would stay unchanged. No result survives a source Run.
use super::*;
use parallel::add_work;
use rayon::prelude::*;

#[derive(Default, Serialize)]
struct Stats {
    attempts: u64,
    queue_head_visits: u64,
    queue_comparisons: u64,
    queue_successor_reads: u64,
    preflight_checks: u64,
    uncovered_stops: u64,
    short_prefixes: u64,
    preparation_errors: u64,
    dispatches: u64,
    prepared_tasks: u64,
    prepared_candidates: u64,
    pending_probes: u64,
    candidate_fact_lookups: u64,
    read_set_slots: u64,
    read_set_comparisons: u64,
    read_set_queries: u64,
    result_refreshes: u64,
    collected_tasks: u64,
    recorded_answers: u64,
    guard_candidates: u64,
    worker_early_stops: u64,
    selection_checks: u64,
    selection_pending_skips: u64,
    selection_dead_skips: u64,
    order_checks: u64,
    interleaved_stops: u64,
    bridged_tasks: u64,
    conflicting_unions: u64,
    committed_tasks: u64,
    reused_after_union: u64,
    unused_tasks: u64,
    unsubmitted_tasks: u64,
    scratch_allocations: u64,
    scratch_bytes_requested: u64,
    peak_tasks: usize,
}
pub(in super::super) struct Runtime {
    limit: usize,
    stats: Stats,
    worker_tasks: Vec<u64>,
}

struct Answer {
    candidate: Candidate,
    result: Result<()>,
}
type Answers = smallvec::SmallVec<[Answer; 4]>;
struct Prepared {
    fact: FactRef,
    row: Row,
    context: CandidateSet,
    answers: Answers,
    worker: usize,
}
struct Bound<'a> {
    candidate: Candidate,
    target: Option<&'a Stored>,
    condition: Option<&'a composition::conditions::Condition>,
    pending: bool,
    skip: bool,
}
#[derive(Default)]
struct Counts {
    work: guard::Work,
    keys: u64,
    visits: u64,
    operators: u64,
    inactive: u64,
    pending: u64,
    candidates: u64,
    early_stops: u64,
    allocations: u64,
    bytes: u64,
}
struct Task<'a> {
    table: usize,
    component: u32,
    values: &'a [Value],
    inputs: smallvec::SmallVec<[Bound<'a>; 16]>,
    answers: Answers,
    counts: Counts,
    worker: usize,
}
impl Task<'_> {
    fn run(&mut self, view: guard::ReadView<'_>) {
        self.worker = rayon::current_thread_index().unwrap();
        for bound in &self.inputs {
            self.counts.candidates += 1;
            if bound.skip {
                self.counts.pending += 1;
                continue;
            }
            if bound.condition.is_some() {
                self.counts.visits += 1;
            } else {
                self.counts.keys += 1;
            }
            let Some(target) = bound.target else {
                self.counts.inactive += u64::from(bound.condition.is_some());
                continue;
            };
            let result = if let Some(condition) = bound.condition {
                self.counts.operators += 1;
                if target.table != self.table {
                    Ok(false)
                } else {
                    view.condition_matches(
                        self.component,
                        condition,
                        target,
                        self.values,
                        &mut self.counts.work,
                    )
                }
            } else {
                view.key_matches(
                    target,
                    self.table,
                    &self.values[..self.values.len() - 1],
                    &mut self.counts.work,
                )
            };
            let matched = matches!(result, Ok(true));
            if !matches!(result, Ok(false)) {
                let capacity = self.answers.capacity();
                self.answers.push(Answer {
                    candidate: bound.candidate,
                    result: result.map(|_| ()),
                });
                if self.answers.capacity() != capacity {
                    self.counts.allocations += 1;
                    self.counts.bytes +=
                        (self.answers.capacity() * std::mem::size_of::<Answer>()) as u64;
                }
            }
            // A completed matching peer can only become a key task after an
            // input-class change. That change invalidates this cached source
            // before a bridged task could retire the peer.
            if matched && !bound.pending {
                self.counts.early_stops += 1;
                break;
            }
        }
    }
}

impl Graph {
    pub fn use_completion_read_batches(&mut self, limit: usize) -> Result<()> {
        if !(2..=64).contains(&limit) {
            return Err("completion batch task limit must be between 2 and 64".into());
        }
        let workers = self
            .stable_ports
            .as_ref()
            .and_then(|s| s.parallel.as_ref())
            .ok_or("completion batches require a configured guard pool")?
            .pool
            .current_num_threads();
        if let Some(old) = self.stable_ports.as_ref().unwrap().batches.as_ref() {
            return if old.limit == limit {
                Ok(())
            } else {
                Err("completion batch limit already configured".into())
            };
        }
        self.use_scoped_completion()?;
        self.stable_ports.as_mut().unwrap().batches = Some(Runtime {
            limit,
            stats: Stats::default(),
            worker_tasks: vec![0; workers],
        });
        Ok(())
    }
    fn batch_stats(&mut self) -> &mut Stats {
        &mut self
            .stable_ports
            .as_mut()
            .unwrap()
            .batches
            .as_mut()
            .unwrap()
            .stats
    }
    fn batch_source_covered(&self, f: FactRef, table: usize) -> bool {
        if !self.port_keys_enabled(table) {
            return false;
        }
        let Some(state) = self.cells.get(&f.cell).and_then(|c| c.facts.get(&f.op)) else {
            return false;
        };
        if state.ports.is_none() {
            return false;
        }
        let m = self.ownership.as_ref().unwrap();
        let frame = m.composition.frames[&f.cell];
        let Some(component) = &m.composition.components[frame.component as usize] else {
            return false;
        };
        self.program
            .cell_ownership
            .composition
            .conditions
            .get(component.shape)
            .is_some_and(|p| p.complete && p.site(frame.ordinal, f.op).is_some())
    }
    pub(in crate::graph) fn complete_port_read_batch(
        &mut self,
        next: Option<Dependency>,
        allowed: Option<&[bool]>,
    ) -> Result<bool> {
        let Some(runtime) = self.stable_ports.as_ref().and_then(|s| s.batches.as_ref()) else {
            return Ok(false);
        };
        let limit = runtime.limit;
        if self.ownership.as_ref().unwrap().pending.len() < 2 {
            return Ok(false);
        }
        self.batch_stats().attempts += 1;
        let (mut prefix, heads, comparisons, successors, allocations, bytes) = self
            .ownership
            .as_ref()
            .unwrap()
            .pending
            .prefix_before(next, allowed, limit);
        let stats = self.batch_stats();
        stats.queue_head_visits += heads;
        stats.queue_comparisons += comparisons;
        stats.queue_successor_reads += successors;
        stats.scratch_allocations += allocations;
        stats.scratch_bytes_requested += bytes as u64;
        let mut covered = 0;
        for &(fact, table) in &prefix {
            self.batch_stats().preflight_checks += 1;
            if !self.batch_source_covered(fact, table) {
                self.batch_stats().uncovered_stops += 1;
                break;
            }
            covered += 1;
        }
        prefix.truncate(covered);
        if prefix.len() < 2 {
            self.batch_stats().short_prefixes += 1;
            return Ok(false);
        }
        let mut prepared = Vec::with_capacity(prefix.len());
        self.batch_stats().scratch_allocations += 1;
        self.batch_stats().scratch_bytes_requested +=
            (prepared.capacity() * std::mem::size_of::<Prepared>()) as u64;
        for (fact, _) in prefix {
            // An error in an ahead-of-order source must not prevent earlier
            // commits. Stop prefetching; the ordinary path will observe it.
            let row = match self.fact(fact) {
                Ok(Some(row)) => row,
                _ => {
                    self.batch_stats().preparation_errors += 1;
                    break;
                }
            };
            let context = match self.local_port_candidates(fact, &row) {
                Ok(Some(context)) => context,
                _ => {
                    self.batch_stats().preparation_errors += 1;
                    break;
                }
            };
            prepared.push(Prepared {
                fact,
                row,
                context,
                answers: Answers::new(),
                worker: usize::MAX,
            });
        }
        if prepared.len() < 2 {
            self.batch_stats().unsubmitted_tasks += prepared.len() as u64;
            return Ok(false);
        }
        let mut reads = smallvec::SmallVec::<[(u64, usize); 32]>::new();
        let (mut read_allocations, mut read_bytes) = (0, 0);
        for (index, source) in prepared.iter().enumerate() {
            for &column in self.program.repair_ports.key_eq_columns[source.row.table]
                .as_ref()
                .unwrap()
            {
                let Value::Eq(root) = source.row.values[column] else {
                    return Err("typed batch input".into());
                };
                let capacity = reads.capacity();
                reads.push((root, index));
                if reads.capacity() != capacity {
                    read_allocations += 1;
                    read_bytes += (reads.capacity() * std::mem::size_of::<(u64, usize)>()) as u64;
                }
            }
        }
        self.batch_stats().read_set_slots += reads.len() as u64;
        let stats = self.batch_stats();
        stats.scratch_allocations += read_allocations;
        stats.scratch_bytes_requested += read_bytes;
        reads.sort_unstable_by(|a, b| {
            stats.read_set_comparisons += 1;
            a.cmp(b)
        });
        reads.dedup();
        self.evaluate_completion_tasks(&mut prepared)?;
        let count = prepared.len();
        let mut end = count;
        let mut committed = 0;
        let initial_unions = self.stats.unions;
        'tasks: for (index, mut source) in prepared.into_iter().enumerate() {
            if index >= end {
                break;
            }
            let mut next = if index == 0 {
                next
            } else {
                self.next_scoped_dirty(allowed)
            };
            loop {
                if index >= end {
                    break 'tasks;
                }
                self.batch_stats().order_checks += 1;
                let head = self.ownership.as_ref().unwrap().pending.first(allowed);
                if allowed.is_some_and(|mask| self.pending_opaque_completion(mask))
                    || head.is_none()
                    || next.is_some_and(|d| d < Dependency::Fact(head.unwrap().0))
                {
                    self.batch_stats().interleaved_stops += 1;
                    break 'tasks;
                }
                let (head, table) = head.unwrap();
                if (head, table) == (source.fact, source.row.table) {
                    break;
                }
                // A new earlier pure constructor can run in the original
                // order without abandoning unrelated prefetched reads. Legacy
                // effects/births remain a boundary, never a speculative bridge.
                if head >= source.fact || !self.port_keys_enabled(table) {
                    self.batch_stats().interleaved_stops += 1;
                    break 'tasks;
                }
                assert_eq!(self.pop_owned_before(next, allowed), Some(head));
                self.complete_owned_key(head)?;
                self.batch_stats().bridged_tasks += 1;
                self.commit_batch_unions(&reads, index, &mut end)?;
                next = self.next_scoped_dirty(allowed);
            }
            // Input values are certified unchanged. Result, visibility and
            // epoch are current commit-time data, not prefetched metadata.
            let state = &self.cells[&source.fact.cell].facts[&source.fact.op];
            source.row.hidden = state.hidden;
            source.row.epoch = state.epoch;
            if self.stats.unions != initial_unions {
                // During this read/commit window only union can change a
                // result. Its old ID still names the same class; following
                // parents avoids re-reading the component/port directory.
                let Value::Eq(id) = source.row.values.last().unwrap() else {
                    return Err("typed batch result".into());
                };
                let output = Value::Eq(root(&self.parents, *id));
                let stable = self.stable_ports.as_ref().unwrap();
                stable
                    .root_resolutions
                    .set(stable.root_resolutions.get() + 1);
                *Rc::get_mut(&mut source.row.values)
                    .expect("batch owns its row view")
                    .last_mut()
                    .unwrap() = output;
                self.batch_stats().result_refreshes += 1;
            }
            let mut found = None;
            for answer in source.answers {
                self.batch_stats().selection_checks += 1;
                let f = answer.candidate.fact;
                let Some(state) = self.cells.get(&f.cell).and_then(|c| c.facts.get(&f.op)) else {
                    self.batch_stats().selection_dead_skips += 1;
                    continue;
                };
                let Some(stored) = state.ports.as_deref() else {
                    self.batch_stats().selection_dead_skips += 1;
                    continue;
                };
                if self
                    .ownership
                    .as_ref()
                    .unwrap()
                    .pending
                    .contains(stored.table, &f)
                {
                    self.batch_stats().selection_pending_skips += 1;
                    continue;
                }
                answer.result?;
                let row = self.read_stable_fact(f, state, stored)?;
                let cross = self.cells[&source.fact.cell].started_epoch
                    != self.cells[&f.cell].started_epoch;
                let local = self.local_condition_stats();
                if answer.candidate.condition.is_some() {
                    local.completed_conditions += 1;
                    local.cross_stage_conditions += u64::from(cross);
                } else {
                    local.boundary_collisions += 1;
                }
                found = Some(row);
                break;
            }
            assert_eq!(self.pop_owned_before(next, allowed), Some(source.fact));
            self.dirty_facts[source.row.table].remove(&source.fact);
            self.stable_ports.as_mut().unwrap().equality_completions += 1;
            self.batch_stats().reused_after_union += u64::from(self.stats.unions > initial_unions);
            self.commit_port_key(source.fact, source.row, found)?;
            committed += 1;
            self.commit_batch_unions(&reads, index + 1, &mut end)?;
        }
        let stats = self.batch_stats();
        stats.committed_tasks += committed;
        stats.unused_tasks += count as u64 - committed;
        Ok(committed != 0)
    }

    fn commit_batch_unions(
        &mut self,
        reads: &[(u64, usize)],
        first_task: usize,
        end: &mut usize,
    ) -> Result<()> {
        if self.pending_unions.is_empty() {
            return Ok(());
        }
        // Only complete_port_key is allowed here. Its sole pair consists of
        // freshly resolved result roots, and retirement performs no unions.
        debug_assert_eq!(self.pending_unions.len(), 1);
        let pairs = std::mem::take(&mut self.pending_unions);
        for &(a, b) in &pairs {
            if a == b {
                continue;
            }
            let previous_end = *end;
            for root in [a, b] {
                let stats = self.batch_stats();
                stats.read_set_queries += 1;
                let first = reads.partition_point(|&slot| {
                    stats.read_set_comparisons += 1;
                    slot < (root, first_task)
                });
                if let Some(&(read_root, task)) = reads.get(first)
                    && read_root == root
                {
                    *end = (*end).min(task);
                }
            }
            self.batch_stats().conflicting_unions += u64::from(*end < previous_end);
        }
        self.commit_union_batch(pairs)
    }

    fn evaluate_completion_tasks(&mut self, prepared: &mut [Prepared]) -> Result<()> {
        let mut tasks = Vec::with_capacity(prepared.len());
        let mut allocations = 1;
        let mut bytes = (tasks.capacity() * std::mem::size_of::<Task<'_>>()) as u64;
        let mut candidates = 0;
        let mut fact_lookups = 0;
        for source in prepared.iter() {
            let mut inputs = smallvec::SmallVec::<[Bound<'_>; 16]>::with_capacity(
                source.context.candidates.len(),
            );
            if inputs.spilled() {
                allocations += 1;
                bytes += (inputs.capacity() * std::mem::size_of::<Bound<'_>>()) as u64;
            }
            for &candidate in &source.context.candidates {
                candidates += 1;
                let pending = self
                    .dependency_table(Dependency::Fact(candidate.fact))
                    .is_some_and(|t| {
                        self.ownership
                            .as_ref()
                            .unwrap()
                            .pending
                            .contains(t, &candidate.fact)
                    });
                let skip = pending && candidate.fact >= source.fact;
                let target = if skip {
                    None
                } else {
                    fact_lookups += 1;
                    self.cells
                        .get(&candidate.fact.cell)
                        .and_then(|c| c.facts.get(&candidate.fact.op))
                        .and_then(|s| s.ports.as_deref())
                };
                inputs.push(Bound {
                    candidate,
                    target,
                    pending,
                    skip,
                    condition: candidate
                        .condition
                        .map(|i| &source.context.plan.conditions[i]),
                });
            }
            tasks.push(Task {
                table: source.row.table,
                component: source.context.component,
                values: &source.row.values,
                inputs,
                answers: Answers::new(),
                counts: Counts::default(),
                worker: usize::MAX,
            });
        }
        let view = self.stable_port_reader()?;
        self.stable_ports
            .as_ref()
            .unwrap()
            .parallel
            .as_ref()
            .unwrap()
            .pool
            .install(|| {
                tasks.par_iter_mut().for_each(|task| task.run(view));
            });
        let mut total = Counts::default();
        // Detach results from all Graph/template borrows before any mutation.
        let results = tasks
            .into_iter()
            .map(|task| {
                add_work(&mut total.work, &task.counts.work);
                total.keys += task.counts.keys;
                total.visits += task.counts.visits;
                total.operators += task.counts.operators;
                total.inactive += task.counts.inactive;
                total.pending += task.counts.pending;
                total.candidates += task.counts.candidates;
                total.early_stops += task.counts.early_stops;
                allocations += task.counts.allocations;
                bytes += task.counts.bytes;
                (task.answers, task.worker)
            })
            .collect::<smallvec::SmallVec<[_; 16]>>();
        if results.spilled() {
            allocations += 1;
            bytes += (results.capacity() * std::mem::size_of::<(Answers, usize)>()) as u64;
        }
        for (source, (answers, worker)) in prepared.iter_mut().zip(results) {
            source.answers = answers;
            source.worker = worker;
        }
        self.record_guard_reads(&total.work);
        let stable = self.stable_ports.as_mut().unwrap();
        stable
            .key_candidates
            .set(stable.key_candidates.get() + total.keys);
        let local = stable.conditions.as_mut().unwrap();
        local.condition_visits += total.visits;
        local.operator_guards += total.operators;
        local.inactive_sites += total.inactive;
        local.pending_sites += total.pending;
        local.scalar_guards += total.work.scalar_guards;
        local.equality_guards += total.work.equality_guards;
        local.shared_symbol_guards += total.work.shared_symbol_guards;
        let runtime = stable.batches.as_mut().unwrap();
        for source in prepared.iter() {
            runtime.worker_tasks[source.worker] += 1;
        }
        let stats = &mut runtime.stats;
        stats.dispatches += 1;
        stats.prepared_tasks += prepared.len() as u64;
        stats.peak_tasks = stats.peak_tasks.max(prepared.len());
        stats.collected_tasks += prepared.len() as u64;
        stats.prepared_candidates += candidates;
        stats.pending_probes += candidates;
        stats.candidate_fact_lookups += fact_lookups;
        stats.recorded_answers += prepared.iter().map(|s| s.answers.len() as u64).sum::<u64>();
        stats.guard_candidates += total.candidates;
        stats.worker_early_stops += total.early_stops;
        stats.scratch_allocations += allocations;
        stats.scratch_bytes_requested += bytes;
        Ok(())
    }

    pub fn completion_batch_report(&self) -> J {
        let Some(runtime) = self.stable_ports.as_ref().and_then(|s| s.batches.as_ref()) else {
            return json!({"enabled":false});
        };
        json!({"enabled":true,"task_limit":runtime.limit,"stats":runtime.stats,
            "worker_tasks":runtime.worker_tasks,
            "scope":"standalone Cell CPU; batched immutable reads with input-class certificates and ordered commits",
            "proof":"complete compiler key footprint; both union classes checked; live/pending peers and queue order rechecked; invalid suffix discarded",
            "performance_admission":false})
    }
}
