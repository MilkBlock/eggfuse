//! Complete necessary Cell query conditions on the sealed source-Run view.
//! The only returned data is the original ordered Entry witness selection.
use super::*;
use crate::entry_schedule::Batch;
use rayon::prelude::*;
use std::time::Instant;

#[derive(Default, serde::Serialize)]
pub(super) struct Stats {
    attempts: u64,
    epoch_bins: u64,
    batches: u64,
    rows: u64,
    kept: u64,
    probes: u64,
    chunks: u64,
    candidate_capacity_bytes: u64,
    peak_candidate_bytes: u64,
    prepare_seconds: f64,
    pool_seconds: f64,
    compact_seconds: f64,
    worker_rows: Vec<u64>,
    worker_probes: Vec<u64>,
    // Wall residence in task bodies, not CPU time or a utilization measurement.
    worker_task_seconds: Vec<f64>,
}

impl Sieve {
    pub(crate) fn parallel_entries(&mut self, graph: &Graph, index: &QueryIndexes,
        rid: usize, batch: Batch<'_>, pool: &rayon::ThreadPool, grain: usize,
    ) -> Option<Vec<(Dependency, bool)>> {
        if !self.parallel_enabled || !self.enabled { return None; }
        self.parallel.attempts += 1;
        let guards = &self.rules[rid][batch.atom()];
        if guards.is_empty() { return None; }
        // Amortize one join per source batch; do not send tiny filters to the pool.
        let chunk_size = grain.max(256);
        if !batch.delta_exceeds(chunk_size.saturating_mul(pool.current_num_threads()), &mut self.parallel.epoch_bins) {
            return None;
        }
        let keys = index.current_fingerprints(graph, batch.table)?;
        let states = &self.states;
        let clock = Instant::now();
        let mut rows: Vec<_> = batch.delta().map(|&(_, w)| (w, true)).collect();
        let bytes = (rows.capacity() * std::mem::size_of::<(Dependency, bool)>()) as u64;
        self.parallel.candidate_capacity_bytes += bytes;
        self.parallel.peak_candidate_bytes = self.parallel.peak_candidate_bytes.max(bytes);
        self.parallel.prepare_seconds += clock.elapsed().as_secs_f64();
        let clock = Instant::now();
        let results: Vec<_> = pool.install(|| rows.par_chunks_mut(chunk_size).map(|chunk| {
            let clock = Instant::now();
            let (mut probes, mut rejected) = (0u64, 0u64);
            for (w, keep) in chunk.iter_mut() {
                // Missing fingerprints pass to the exact matcher, as in allow().
                let Some(row) = keys.get(w) else { continue; };
                for guard in guards {
                    probes += 1;
                    if !states[guard.child].allows(row, &guard.cols) {
                        *keep = false;
                        rejected += 1;
                        break;
                    }
                }
            }
            (rayon::current_thread_index().expect("pool task"), chunk.len(), probes, rejected,
                clock.elapsed().as_secs_f64())
        }).collect());
        self.parallel.pool_seconds += clock.elapsed().as_secs_f64();
        self.parallel.worker_rows.resize(pool.current_num_threads(), 0);
        self.parallel.worker_probes.resize(pool.current_num_threads(), 0);
        self.parallel.worker_task_seconds.resize(pool.current_num_threads(), 0.0);
        self.parallel.batches += 1;
        self.parallel.rows += rows.len() as u64;
        self.parallel.chunks += results.len() as u64;
        for (worker, n, probes, rejected, seconds) in results {
            self.parallel.worker_rows[worker] += n as u64;
            self.parallel.worker_probes[worker] += probes;
            self.parallel.worker_task_seconds[worker] += seconds;
            self.parallel.probes += probes;
            self.stats.probes += probes;
            self.stats.rejected += rejected;
            self.stats.per_rule[rid].0 += probes;
            self.stats.per_rule[rid].1 += rejected;
        }
        let clock = Instant::now();
        rows.retain(|(_, keep)| *keep);
        self.parallel.compact_seconds += clock.elapsed().as_secs_f64();
        self.parallel.kept += rows.len() as u64;
        Some(rows)
    }
}
