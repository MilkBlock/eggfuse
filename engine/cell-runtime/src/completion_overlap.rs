//! Pipeline snapshot reads and ordered commits. The certificate and collision
//! path are shared with synchronous batches; only result delivery is different.
use super::*;
use std::sync::{
    Arc, OnceLock,
    atomic::{AtomicUsize, Ordering},
};

#[derive(Default, Serialize)]
struct Stats {
    epochs: u64,
    projection_candidates: u64,
    projection_records: u64,
    projection_scalar_values: u64,
    projection_scalar_bytes_total: u64,
    projection_comparisons: u64,
    projection_insertion_moves: u64,
    projection_capacity_bytes_total: u64,
    projection_capacity_bytes_peak: usize,
    base_snapshots: u64,
    task_spawns: u64,
    projected_tasks: u64,
    input_buffer_allocations: u64,
    input_buffer_bytes: u64,
    activity_allocations: u64,
    reader_activity_updates: u64,
    channel_builds: u64,
    channel_receives: u64,
    slot_publications: u64,
    slot_abandons: u64,
    slot_collection_reads: u64,
    ordered_slot_reads: u64,
    row_handle_clones: u64,
    result_buffer_allocations: u64,
    result_buffer_bytes: u64,
    overlay: crate::read_epoch::Work,
    layers: guard::EpochWork,
}
#[derive(Default, Serialize)]
struct Observed {
    effective_unions_with_active_readers: u64,
}
#[derive(Default)]
pub(super) struct Runtime {
    pub enabled: bool,
    stats: Stats,
    observed: Observed,
    active: Option<Arc<AtomicUsize>>,
    #[cfg(feature = "completion-overlap-probes")]
    probe: Option<Arc<Probe>>,
}
#[cfg(feature = "completion-overlap-probes")]
#[derive(Default)]
struct Probe {
    claimed: std::sync::atomic::AtomicBool,
    state: std::sync::Mutex<(bool, bool)>,
    changed: std::sync::Condvar,
    panic_after_commit: bool,
    panic_first: bool,
}
#[cfg(feature = "completion-overlap-probes")]
impl Probe {
    fn wait(&self, field: usize) {
        let state = self.state.lock().unwrap();
        let (state, timeout) = self
            .changed
            .wait_timeout_while(state, std::time::Duration::from_secs(5), |s| {
                if field == 0 { !s.0 } else { !s.1 }
            })
            .unwrap();
        assert!(!timeout.timed_out(), "overlap probe timed out: {state:?}");
    }
    fn begin(&self, index: usize) {
        if self.panic_first {
            assert!(index != 0, "injected first completion reader panic");
            return;
        }
        if index == 1 {
            self.state.lock().unwrap().0 = true;
            self.changed.notify_all();
            self.wait(1);
            assert!(!self.panic_after_commit, "injected completion reader panic");
        }
    }
    fn end(&self, index: usize) {
        if index == 0 && !self.panic_first {
            self.wait(0);
        }
    }
    fn committed(&self) {
        self.state.lock().unwrap().1 = true;
        self.changed.notify_all();
    }
}
impl Runtime {
    pub fn report(&self) -> J {
        if !self.enabled {
            return json!({"enabled":false});
        }
        json!({"enabled":true,"stats":self.stats,"observed":self.observed,
            "scope":"immutable epoch bases with coordinator write overlays; grouped readers publish directly to ordered result slots",
            "performance_admission":false})
    }
}

struct Outcome {
    answers: Answers,
    counts: Counts,
    worker: usize,
}
/// Plain projected borrows only; Prepared owns Rc values and never crosses
/// into the worker pool. One input per task, no per-candidate descriptors.
#[derive(Clone, Copy)]
struct Input<'a> {
    fact: FactRef,
    table: usize,
    component: u32,
    values: &'a [Value],
    candidates: &'a [Candidate],
    plan: &'a Plan,
}
impl Input<'_> {
    fn run(self, view: guard::ReadView<'_>, ready: ready::ReadView<'_>) -> Outcome {
        let mut answers = Answers::new();
        let mut worker = usize::MAX;
        let mut task = Task {
            fact: self.fact,
            table: self.table,
            component: self.component,
            values: self.values,
            candidates: self.candidates,
            plan: self.plan,
            answers: &mut answers,
            counts: Counts::default(),
            worker: &mut worker,
        };
        task.run(view, ready);
        let counts = task.counts;
        Outcome {
            answers,
            counts,
            worker,
        }
    }
}
type Slot = OnceLock<Option<Outcome>>;
/// Each lane owns distinct positions. If it unwinds, publish abandonment to
/// every unfilled position so the coordinator cannot wait for a lost result.
struct Lane<'a> {
    slots: &'a [Slot],
    next: usize,
    stride: usize,
}
impl Lane<'_> {
    fn publish(&mut self, outcome: Outcome) {
        assert!(self.slots[self.next].set(Some(outcome)).is_ok());
        self.next += self.stride;
    }
}
impl Drop for Lane<'_> {
    fn drop(&mut self) {
        for index in (self.next..self.slots.len()).step_by(self.stride) {
            let _ = self.slots[index].set(None);
        }
    }
}
struct ActiveRead<'a>(&'a AtomicUsize);
impl Drop for ActiveRead<'_> {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}
fn collect_counts(total: &mut Counts, count: &Counts) {
    add_work(&mut total.work, &count.work);
    total.keys += count.keys;
    total.visits += count.visits;
    total.operators += count.operators;
    total.inactive += count.inactive;
    total.pending += count.pending;
    total.candidates += count.candidates;
    total.pending_probes += count.pending_probes;
    total.early_stops += count.early_stops;
    total.allocations += count.allocations;
    total.bytes += count.bytes;
}

impl Graph {
    /// Deterministic diagnostic: hold the second reader until a real union is
    /// committed. This hook is absent from production/audit builds.
    #[cfg(feature = "completion-overlap-probes")]
    pub fn use_completion_overlap_probe(&mut self) -> Result<()> {
        self.use_overlapped_completion()?;
        self.overlap_runtime().probe = Some(Arc::new(Probe::default()));
        Ok(())
    }
    #[cfg(feature = "completion-overlap-probes")]
    pub fn use_completion_overlap_panic_probe(&mut self) -> Result<()> {
        self.use_overlapped_completion()?;
        self.overlap_runtime().probe = Some(Arc::new(Probe {
            panic_after_commit: true,
            ..Probe::default()
        }));
        Ok(())
    }
    #[cfg(feature = "completion-overlap-probes")]
    pub fn use_completion_overlap_early_panic_probe(&mut self) -> Result<()> {
        self.use_overlapped_completion()?;
        self.overlap_runtime().probe = Some(Arc::new(Probe {
            panic_first: true,
            ..Probe::default()
        }));
        Ok(())
    }
    pub fn use_overlapped_completion(&mut self) -> Result<()> {
        let batch = self
            .stable_ports
            .as_mut()
            .and_then(|s| s.batches.as_mut())
            .ok_or("overlapped completion requires configured completion batches")?;
        batch.overlap.enabled = true;
        Ok(())
    }
    fn overlap_runtime(&mut self) -> &mut Runtime {
        &mut self
            .stable_ports
            .as_mut()
            .unwrap()
            .batches
            .as_mut()
            .unwrap()
            .overlap
    }
    pub(super) fn commit_epoch_unions(&mut self, pairs: Vec<(u64, u64)>) -> Result<()> {
        let active = self
            .overlap_runtime()
            .active
            .as_ref()
            .is_some_and(|n| n.load(Ordering::Acquire) != 0);
        let before = self.stats.unions;
        let result = self.commit_union_batch(pairs);
        if active {
            self.overlap_runtime()
                .observed
                .effective_unions_with_active_readers += self.stats.unions - before;
        }
        #[cfg(feature = "completion-overlap-probes")]
        if self.stats.unions > before
            && let Some(probe) = &self.overlap_runtime().probe
        {
            probe.committed();
        }
        result
    }
    pub(super) fn overlap_completion_tasks(
        &mut self,
        prepared: Vec<Prepared>,
        reads: &[(u64, usize)],
        next: Option<Dependency>,
        allowed: Option<crate::table_mask::Selection<'_>>,
    ) -> Result<bool> {
        let count = prepared.len();
        let pool = self
            .stable_ports
            .as_ref()
            .unwrap()
            .parallel
            .as_ref()
            .unwrap()
            .pool
            .clone();
        let snapshot = self.freeze_completion_reads(prepared.iter()
            .flat_map(|p|p.context.candidates.iter().map(|c|c.fact)));
        let projection_work = snapshot.projection_work;
        let runtime = self.overlap_runtime();
        let activity_allocations = u64::from(runtime.active.is_none());
        let active = runtime
            .active
            .get_or_insert_with(|| Arc::new(AtomicUsize::new(0)))
            .clone();
        debug_assert_eq!(active.load(Ordering::Acquire), 0);
        #[cfg(feature = "completion-overlap-probes")]
        let probe = self
            .overlap_runtime()
            .probe
            .as_ref()
            .filter(|p| !p.claimed.swap(true, Ordering::AcqRel))
            .cloned();
        let inputs: Vec<_> = prepared
            .iter()
            .map(|source| Input {
                fact: source.fact,
                table: source.row.table,
                component: source.context.component,
                values: &source.row.values,
                candidates: &source.context.candidates,
                plan: &source.context.plan,
            })
            .collect();
        let slots: Vec<Slot> = std::iter::repeat_with(OnceLock::new).take(count).collect();
        let lanes = count.min(pool.current_num_threads());
        let mut total = Counts::default();
        let mut collected = 0;
        let mut recorded_answers = 0;
        let mut committed = 0;
        let mut end = count;
        let initial_unions = self.stats.unions;
        let mut distribution = vec![0u64; pool.current_num_threads()];
        let mut ordered_slot_reads = 0;
        // Rayon joins spawned lanes even on error/unwind. A lane's Drop fills
        // missing slots before its panic propagates, releasing ordered waiters.
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            pool.in_place_scope_fifo(|scope| {
                for first in 0..lanes {
                    let inputs = &inputs;
                    let mut lane = Lane {
                        slots: &slots,
                        next: first,
                        stride: lanes,
                    };
                    let active = &active;
                    let view = snapshot.reader();
                    let ready = snapshot.ready();
                    #[cfg(feature = "completion-overlap-probes")]
                    let probe = probe.as_ref();
                    scope.spawn_fifo(move |_| {
                        active.fetch_add(1, Ordering::AcqRel);
                        let _active_read = ActiveRead(active);
                        while lane.next < lane.slots.len() {
                            let index = lane.next;
                            #[cfg(feature = "completion-overlap-probes")]
                            if let Some(probe) = probe {
                                probe.begin(index);
                            }
                            let outcome = inputs[index].run(view, ready);
                            #[cfg(feature = "completion-overlap-probes")]
                            if let Some(probe) = probe {
                                probe.end(index);
                            }
                            lane.publish(outcome);
                        }
                    });
                }
                for (index, source) in prepared.iter().enumerate() {
                    if index >= end {
                        break;
                    }
                    let next = if index == 0 {
                        next
                    } else {
                        self.next_scoped_dirty(allowed)
                    };
                    let Some(next) = self.advance_cached_source(
                        index,
                        source.fact,
                        source.row.table,
                        reads,
                        &mut end,
                        next,
                        allowed,
                    )?
                    else {
                        break;
                    };
                    ordered_slot_reads += 1;
                    let outcome = slots[index]
                        .wait()
                        .as_ref()
                        .ok_or("completion reader abandoned its lane")?;
                    // Borrow the published answer in place. Refreshed output
                    // travels separately from the immutable canonical inputs.
                    self.commit_cached_source(
                        source.fact,
                        source.row.clone(),
                        &outcome.answers,
                        initial_unions,
                        next,
                        allowed,
                    )?;
                    committed += 1;
                    self.commit_batch_unions(reads, index + 1, &mut end)?;
                }
                Ok(committed != 0)
            })
        }));
        debug_assert_eq!(active.load(Ordering::Acquire), 0);
        drop(snapshot);
        let overlay = self.thaw_completion_reads();
        // Joining happens before collection, not before commits. Discarded
        // answers are charged too, with no receive queue or result reshuffling.
        for slot in &slots {
            if let Some(outcome) = slot
                .get()
                .expect("every lane publishes or abandons its slots")
            {
                collected += 1;
                recorded_answers += outcome.answers.len() as u64;
                collect_counts(&mut total, &outcome.counts);
                distribution[outcome.worker] += 1;
            }
        }
        let runtime = self.overlap_runtime();
        runtime.stats.epochs += 1;
        runtime.stats.projection_candidates += projection_work.candidates;
        runtime.stats.projection_records += projection_work.records;
        runtime.stats.projection_scalar_values += projection_work.scalar_values;
        runtime.stats.projection_scalar_bytes_total += projection_work.scalar_capacity_bytes as u64;
        runtime.stats.projection_comparisons += projection_work.comparisons;
        runtime.stats.projection_insertion_moves += projection_work.insertion_moves;
        runtime.stats.projection_capacity_bytes_total += (projection_work.capacity_bytes+projection_work.scalar_capacity_bytes) as u64;
        runtime.stats.projection_capacity_bytes_peak = runtime.stats.projection_capacity_bytes_peak.max(projection_work.capacity_bytes+projection_work.scalar_capacity_bytes);
        runtime.stats.base_snapshots += 4;
        runtime.stats.task_spawns += lanes as u64;
        runtime.stats.projected_tasks += count as u64;
        runtime.stats.input_buffer_allocations += 1;
        runtime.stats.input_buffer_bytes +=
            (inputs.capacity() * std::mem::size_of::<Input<'_>>()) as u64;
        runtime.stats.activity_allocations += activity_allocations;
        runtime.stats.reader_activity_updates += 2 * lanes as u64;
        runtime.stats.slot_publications += collected;
        runtime.stats.slot_abandons += count as u64 - collected;
        runtime.stats.slot_collection_reads += count as u64;
        runtime.stats.ordered_slot_reads += ordered_slot_reads;
        runtime.stats.row_handle_clones += committed;
        runtime.stats.result_buffer_allocations += 2;
        runtime.stats.result_buffer_bytes += (slots.capacity() * std::mem::size_of::<Slot>()
            + distribution.capacity() * std::mem::size_of::<u64>())
            as u64;
        runtime.stats.overlay.add(overlay.total());
        runtime.stats.layers.add(overlay);
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
        let batch = stable.batches.as_mut().unwrap();
        for (worker, tasks) in distribution.into_iter().enumerate() {
            batch.worker_tasks[worker] += tasks;
        }
        let stats = &mut batch.stats;
        stats.dispatches += 1;
        stats.prepared_tasks += count as u64;
        stats.peak_tasks = stats.peak_tasks.max(count);
        stats.collected_tasks += collected;
        stats.candidate_positions += prepared
            .iter()
            .map(|s| s.context.candidates.len() as u64)
            .sum::<u64>();
        stats.pending_probes += total.pending_probes;
        stats.candidate_fact_lookups += total.work.node_lookups;
        stats.recorded_answers += recorded_answers;
        stats.guard_candidates += total.candidates;
        stats.worker_early_stops += total.early_stops;
        stats.scratch_allocations += total.allocations;
        stats.scratch_bytes_requested += total.bytes;
        stats.committed_tasks += committed;
        stats.unused_tasks += count as u64 - committed;
        match result {
            Ok(result) => result,
            Err(panic) => std::panic::resume_unwind(panic),
        }
    }
}
