//! Opt-in parallel reads for one ordered completion task. A round borrows plain
//! template/port data, finishes all reads, then selects the first match/error in
//! source candidate order. No Graph, Rc, mutable counter or commit enters the
//! pool. This mode handles one task; completion_read_batches adds certified
//! reads across tasks while retaining the same pool and ordered commits.
use super::*;
use rayon::prelude::*;

#[derive(Default, Serialize)]
struct Stats {
    candidate_batches: u64,
    candidate_sites: u64,
    peak_candidates: usize,
    candidate_histogram: [u64; 9],
    below_grain_batches: u64,
    dispatched_batches: u64,
    rounds: u64,
    chunks: u64,
    prepared_candidates: u64,
    prepared_fact_lookups: u64,
    prepared_live_guards: u64,
    collected_results: u64,
    scratch_allocations: u64,
    scratch_bytes_requested: u64,
    speculative_candidates: u64,
    speculative_pending_sites: u64,
    speculative_local_conditions: u64,
    speculative_key_candidates: u64,
    speculative_guard_work: guard::Work,
}

pub(in super::super) struct Runtime {
    pub(super) pool: std::sync::Arc<rayon::ThreadPool>,
    grain: usize,
    width: usize,
    stats: Stats,
    // Execution distribution is deliberately outside the deterministic counts.
    worker_candidates: Vec<u64>,
}

struct Job<'a> {
    candidate: Candidate,
    pending: bool,
    live: bool,
    condition: Option<&'a composition::conditions::Condition>,
    result: Result<bool>,
    work: guard::Work,
    worker: usize,
}

pub(super) fn add_work(total: &mut guard::Work, work: &guard::Work) {
    total.node_lookups += work.node_lookups;
    total.template_node_projections += work.template_node_projections;
    total.field_layout_reads += work.field_layout_reads;
    total.port_reads += work.port_reads;
    total.parent_probes += work.parent_probes;
    total.key_fields += work.key_fields;
    total.scalar_guards += work.scalar_guards;
    total.equality_guards += work.equality_guards;
    total.shared_symbol_guards += work.shared_symbol_guards;
}

// Borrow field values and resolve candidates on the worker. Sparse Cell lifecycle
// reads are shareable; no prepared node descriptor is retained per job.
fn run_round(
    pool: &rayon::ThreadPool,
    grain: usize,
    jobs: &mut [Job<'_>],
    view: guard::ReadView<'_>,
    component: u32,
    table: usize,
    values: &[Value],
) {
    pool.install(|| {
        jobs.par_chunks_mut(grain).for_each(|chunk| {
            for job in chunk {
                job.evaluate_fields(view, component, table, values);
            }
        });
    });
}

impl Job<'_> {
    fn evaluate_fields(
        &mut self,
        view: guard::ReadView<'_>,
        component: u32,
        table: usize,
        values: &[Value],
    ) {
        self.worker = rayon::current_thread_index().expect("guard runs in its private pool");
        if self.pending {
            return;
        }
        let Some(target) = view.node(self.candidate.fact, &mut self.work) else {return;};
        self.live = true;
        self.result = if let Some(condition) = self.condition {
            if target.table != table {
                Ok(false)
            } else {
                view.condition_matches(component, condition, &target, values, &mut self.work)
            }
        } else {
            view.key_matches(&target, table, &values[..values.len() - 1], &mut self.work)
        };
    }
}

impl Graph {
    /// Experimental, default-off worker dispatch. A grain is the minimum
    /// candidates per worker; smaller lists keep the existing serial path.
    pub fn use_parallel_port_guards(&mut self, workers: usize, grain: usize) -> Result<()> {
        if workers < 2 || grain == 0 {
            return Err(
                "parallel port guards require at least two workers and a nonzero grain".into(),
            );
        }
        let width = workers
            .checked_mul(grain)
            .ok_or("guard round size overflow")?;
        if let Some(old) = self.stable_ports.as_ref().and_then(|s| s.parallel.as_ref()) {
            return if old.pool.current_num_threads() == workers && old.grain == grain {
                Ok(())
            } else {
                Err("guard pool is already configured".into())
            };
        }
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(workers)
            .thread_name(|i| format!("cell-guard-{i}"))
            .build()
            .map_err(|e| e.to_string())?;
        self.use_local_port_conditions()?;
        self.stable_ports.as_mut().unwrap().parallel = Some(Runtime {
            pool: std::sync::Arc::new(pool),
            grain,
            width,
            stats: Stats::default(),
            worker_candidates: vec![0; workers],
        });
        Ok(())
    }

    pub(super) fn dispatch_port_guards(&mut self, count: usize) -> bool {
        let Some(runtime) = self.stable_ports.as_mut().unwrap().parallel.as_mut() else {
            return false;
        };
        let stats = &mut runtime.stats;
        stats.candidate_batches += 1;
        stats.candidate_sites += count as u64;
        stats.peak_candidates = stats.peak_candidates.max(count);
        let bin = if count == 0 {
            0
        } else {
            (usize::BITS - count.leading_zeros()).min(8) as usize
        };
        stats.candidate_histogram[bin] += 1;
        if count < runtime.width {
            stats.below_grain_batches += 1;
            false
        } else {
            stats.dispatched_batches += 1;
            true
        }
    }

    pub(super) fn parallel_port_collision(
        &mut self,
        source: FactRef,
        row: &Row,
        plan: &Plan,
        component: u32,
        candidates: &[Candidate],
    ) -> Result<Option<Option<Row>>> {
        let width = self
            .stable_ports
            .as_ref()
            .unwrap()
            .parallel
            .as_ref()
            .unwrap()
            .width;
        for round in candidates.chunks(width) {
            // One bounded descriptor allocation at most. No persistent binding/
            // subscriber list, cloned row, Rc/Arc increment or canonical port copy.
            let mut jobs = smallvec::SmallVec::<[Job<'_>; 32]>::with_capacity(round.len());
            for &candidate in round {
                let pending = self
                    .dependency_table(Dependency::Fact(candidate.fact))
                    .is_some_and(|t| {
                        self.ownership
                            .as_ref()
                            .unwrap()
                            .pending
                            .contains(t, &candidate.fact)
                    });
                jobs.push(Job {
                    candidate,
                    pending,
                    live: false,
                    condition: candidate.condition.map(|id| plan.conditions[id].as_ref()),
                    result: Ok(false),
                    work: guard::Work::default(),
                    worker: usize::MAX,
                });
            }
            let runtime = self
                .stable_ports
                .as_ref()
                .unwrap()
                .parallel
                .as_ref()
                .unwrap();
            run_round(
                &runtime.pool,
                runtime.grain,
                &mut jobs,
                self.stable_port_reader()?,
                component,
                row.table,
                &row.values,
            );
            // Fold all actual work, including results after the ordered winner.
            // A speculative error after a winner was never observable serially.
            let mut selected: Option<Result<Candidate>> = None;
            let mut work = guard::Work::default();
            let mut speculative_work = guard::Work::default();
            let mut speculative = 0;
            let mut speculative_pending = 0;
            let mut speculative_local = 0;
            let mut speculative_keys = 0;
            let mut live = 0;
            let mut pending = 0;
            let mut visits = 0;
            let mut inactive = 0;
            let mut operators = 0;
            let mut keys = 0;
            let spilled = jobs.spilled();
            let mut allocated = if spilled {
                jobs.capacity() * std::mem::size_of::<Job<'_>>()
            } else {
                0
            };
            // Drop the borrowed descriptors before recording any Graph state.
            let mut loads = smallvec::SmallVec::<[u64; 8]>::new();
            // Counts have one slot per configured worker, no per-candidate heap.
            loads.resize(runtime.pool.current_num_threads(), 0);
            let load_spill = loads.spilled();
            if load_spill {
                allocated += loads.capacity() * std::mem::size_of::<u64>();
            }
            for job in jobs {
                loads[job.worker] += 1;
                add_work(&mut work, &job.work);
                if selected.is_some() {
                    speculative += 1;
                    add_work(&mut speculative_work, &job.work);
                    if job.pending {
                        speculative_pending += 1;
                    } else if job.condition.is_some() {
                        speculative_local += 1;
                    } else {
                        speculative_keys += 1;
                    }
                }
                live += u64::from(!job.pending && job.live);
                if job.pending {
                    pending += 1;
                } else if job.condition.is_some() {
                    visits += 1;
                    if !job.live {
                        inactive += 1;
                    } else {
                        operators += 1;
                    }
                } else {
                    keys += 1;
                }
                if selected.is_none() {
                    match job.result {
                        Ok(true) => selected = Some(Ok(job.candidate)),
                        Err(error) => selected = Some(Err(error)),
                        Ok(false) => {}
                    }
                }
            }
            self.record_guard_reads(&work);
            let stable = self.stable_ports.as_mut().unwrap();
            stable
                .key_candidates
                .set(stable.key_candidates.get() + keys);
            let local = stable.conditions.as_mut().unwrap();
            local.pending_sites += pending;
            local.condition_visits += visits;
            local.inactive_sites += inactive;
            local.operator_guards += operators;
            local.scalar_guards += work.scalar_guards;
            local.equality_guards += work.equality_guards;
            local.shared_symbol_guards += work.shared_symbol_guards;
            let runtime = stable.parallel.as_mut().unwrap();
            for (total, n) in runtime.worker_candidates.iter_mut().zip(loads) {
                *total += n;
            }
            let stats = &mut runtime.stats;
            stats.rounds += 1;
            stats.chunks += round.len().div_ceil(runtime.grain) as u64;
            stats.prepared_candidates += round.len() as u64;
            // Candidate fields are resolved by the worker; no prepared node handle.
            stats.prepared_live_guards += live;
            stats.collected_results += round.len() as u64;
            stats.scratch_allocations += u64::from(spilled) + u64::from(load_spill);
            stats.scratch_bytes_requested += allocated as u64;
            stats.speculative_candidates += speculative;
            stats.speculative_pending_sites += speculative_pending;
            stats.speculative_local_conditions += speculative_local;
            stats.speculative_key_candidates += speculative_keys;
            add_work(&mut stats.speculative_guard_work, &speculative_work);
            if let Some(selected) = selected {
                let candidate = selected?;
                let target = candidate.fact;
                let cross_stage = self.cells.cell_metadata(source.cell).unwrap().started_epoch
                    != self.cells.cell_metadata(target.cell).unwrap().started_epoch;
                let local = self.local_condition_stats();
                if candidate.condition.is_some() {
                    local.completed_conditions += 1;
                    local.cross_stage_conditions += u64::from(cross_stage);
                } else {
                    local.boundary_collisions += 1;
                }
                let state = self.cells.fact_state(target).unwrap();
                return self
                    .read_stable_fact(target, state, &self.stable_node(target).unwrap())
                    .map(|row| Some(Some(row)));
            }
        }
        Ok(Some(None))
    }

    pub fn parallel_guard_report(&self) -> J {
        let Some(runtime) = self.stable_ports.as_ref().and_then(|s| s.parallel.as_ref()) else {
            return json!({"enabled": false});
        };
        json!({"enabled": true, "scope": "standalone Cell CPU; parallel candidate reads, ordered serial commits",
            "workers": runtime.pool.current_num_threads(), "grain": runtime.grain,
            "round_width": runtime.width, "pool_builds": 1, "stats": runtime.stats,
            "candidate_histogram_bins": ["0", "1", "2-3", "4-7", "8-15", "16-31", "32-63", "64-127", "128+"],
            "worker_candidates": runtime.worker_candidates,
            "limits": "No overlapping Graph mutation; counts exclude allocator-internal and thread-pool allocations. No speedup admission."})
    }
}
