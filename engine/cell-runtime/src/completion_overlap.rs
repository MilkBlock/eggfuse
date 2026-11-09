//! Pipeline snapshot reads and ordered commits. The certificate and collision
//! path are shared with synchronous batches; only result delivery is different.
use super::*;
use std::sync::{
    Arc,
    atomic::{AtomicUsize, Ordering},
    mpsc,
};

#[derive(Default, Serialize)]
struct Stats {
    epochs: u64,
    base_snapshots: u64,
    task_spawns: u64,
    reader_activity_updates: u64,
    channel_builds: u64,
    channel_receives: u64,
    row_handle_clones: u64,
    result_buffer_allocations: u64,
    result_buffer_bytes: u64,
    overlay: crate::read_epoch::Work,
    layers: guard::EpochWork,
}
#[derive(Default, Serialize)]
struct Observed {
    ordered_receives: u64,
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
        if index == 1 {
            self.state.lock().unwrap().0 = true;
            self.changed.notify_all();
            self.wait(1);
            assert!(!self.panic_after_commit, "injected completion reader panic");
        }
    }
    fn end(&self, index: usize) {
        if index == 0 {
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
            "scope":"immutable epoch bases with coordinator write overlays; ordered per-task result delivery",
            "performance_admission":false})
    }
}

struct Outcome {
    index: usize,
    answers: Answers,
    counts: Counts,
    worker: usize,
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
        allowed: Option<&[bool]>,
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
        let snapshot = self.freeze_completion_reads();
        let active = Arc::new(AtomicUsize::new(0));
        #[cfg(feature = "completion-overlap-probes")]
        let probe = self
            .overlap_runtime()
            .probe
            .as_ref()
            .filter(|p| !p.claimed.swap(true, Ordering::AcqRel))
            .cloned();
        self.overlap_runtime().active = Some(active.clone());
        let (send, receive) = mpsc::sync_channel::<Outcome>(count);
        let mut buffered: Vec<Option<Outcome>> =
            std::iter::repeat_with(|| None).take(count).collect();
        let mut total = Counts::default();
        let mut collected = 0;
        let mut recorded_answers = 0;
        let mut committed = 0;
        let mut end = count;
        let initial_unions = self.stats.unions;
        let mut distribution = vec![0u64; pool.current_num_threads()];
        let mut ordered_receives = 0;
        // Rayon joins spawned tasks even on error/unwind. Restore the writable
        // containers before propagating a panic; never leave a frozen Graph.
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            pool.in_place_scope_fifo(|scope| {
                for (index, source) in prepared.iter().enumerate() {
                    let sender = send.clone();
                    let active = &active;
                    let view = snapshot.reader();
                    let ready = snapshot.ready();
                    // Explicitly project Send borrows; no Rc owner crosses the scope.
                    let (fact, table, component) =
                        (source.fact, source.row.table, source.context.component);
                    let values: &[Value] = &source.row.values;
                    let candidates: &[Candidate] = &source.context.candidates;
                    let plan: &Plan = &source.context.plan;
                    #[cfg(feature = "completion-overlap-probes")]
                    let probe = probe.as_ref();
                    scope.spawn_fifo(move |_| {
                        active.fetch_add(1, Ordering::AcqRel);
                        let active_read = ActiveRead(active);
                        #[cfg(feature = "completion-overlap-probes")]
                        if let Some(probe) = probe {
                            probe.begin(index);
                        }
                        let mut answers = Answers::new();
                        let mut worker = usize::MAX;
                        let mut task = Task {
                            fact,
                            table,
                            component,
                            values,
                            candidates,
                            plan,
                            answers: &mut answers,
                            counts: Counts::default(),
                            worker: &mut worker,
                        };
                        task.run(view, ready);
                        let counts = task.counts;
                        #[cfg(feature = "completion-overlap-probes")]
                        if let Some(probe) = probe {
                            probe.end(index);
                        }
                        drop(active_read);
                        let _ = sender.send(Outcome {
                            index,
                            answers,
                            counts,
                            worker,
                        });
                    });
                }
                drop(send);
                let mut receive_one = |buffered: &mut Vec<Option<Outcome>>| -> Result<()> {
                    let outcome = receive
                        .recv()
                        .map_err(|_| "completion reader disconnected")?;
                    collected += 1;
                    recorded_answers += outcome.answers.len() as u64;
                    collect_counts(&mut total, &outcome.counts);
                    distribution[outcome.worker] += 1;
                    let index = outcome.index;
                    assert!(buffered[index].replace(outcome).is_none());
                    Ok(())
                };
                let result = (|| -> Result<bool> {
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
                        while buffered[index].is_none() {
                            ordered_receives += 1;
                            receive_one(&mut buffered)?;
                        }
                        let outcome = buffered[index].take().unwrap();
                        // This shares immutable canonical inputs with the reader.
                        // The refreshed output travels separately to the commit.
                        self.commit_cached_source(
                            source.fact,
                            source.row.clone(),
                            outcome.answers,
                            initial_unions,
                            next,
                            allowed,
                        )?;
                        committed += 1;
                        self.commit_batch_unions(reads, index + 1, &mut end)?;
                    }
                    Ok(committed != 0)
                })();
                // Charge discarded work too. A full channel holds every job,
                // so early abandonment cannot strand a sender behind a join.
                while let Ok(outcome) = receive.recv() {
                    collected += 1;
                    recorded_answers += outcome.answers.len() as u64;
                    collect_counts(&mut total, &outcome.counts);
                    distribution[outcome.worker] += 1;
                }
                result
            })
        }));
        self.overlap_runtime().active = None;
        drop(snapshot);
        let overlay = self.thaw_completion_reads();
        let runtime = self.overlap_runtime();
        runtime.stats.epochs += 1;
        runtime.stats.base_snapshots += 4;
        runtime.stats.task_spawns += count as u64;
        runtime.stats.reader_activity_updates += 2 * count as u64;
        runtime.stats.channel_builds += 1;
        runtime.stats.channel_receives += collected;
        runtime.stats.row_handle_clones += committed;
        runtime.stats.result_buffer_allocations += 2;
        runtime.stats.result_buffer_bytes +=
            (buffered.capacity() * std::mem::size_of::<Option<Outcome>>()
                + distribution.capacity() * std::mem::size_of::<u64>()) as u64;
        runtime.stats.overlay.add(overlay.total());
        runtime.stats.layers.add(overlay);
        runtime.observed.ordered_receives += ordered_receives;
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
