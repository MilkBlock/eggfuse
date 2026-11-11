//! A Cell's existing joined support can drive a smaller current Entry domain.
//! No new index, subscription, cached frontier or retained binding is created.
use super::*;
use crate::entry_schedule::Batch;

#[derive(Default, serde::Serialize)]
pub(super) struct Stats {
    attempts: u64,
    guards_considered: u64,
    size_skips: u64,
    epoch_bins: u64,
    unavailable: u64,
    over_budget: u64,
    key_probes: u64,
    copied_refs: u64,
    candidate_capacity_bytes: u64,
    selected_batches: u64,
    selected_rows: u64,
    empty_batches: u64,
    sort_comparisons: u64,
    pub(super) probes_omitted: u64,
}
pub(crate) struct Selection {
    pub(crate) guard: usize,
    pub(crate) rows: Vec<(u64, Dependency)>,
}
impl Sieve {
    pub(crate) fn select_entries(&mut self, g: &Graph, index: &QueryIndexes,
        rid: usize, batch: Batch<'_>) -> Option<Selection> {
        if !self.reverse_enabled { return None; }
        self.reverse.attempts += 1;
        let mut best = None;
        for (position, guard) in self.rules[rid][batch.atom()].iter().enumerate() {
            self.reverse.guards_considered += 1;
            let [column] = guard.cols.as_slice() else { continue; };
            let state = &self.states[guard.child];
            let Support::One(keys) = &state.keys else { continue; };
            if state.built && best.is_none_or(|(_, _, prior): (_, _, &rustc_hash::FxHashSet<u64>)| keys.len() < prior.len()) {
                best = Some((position, *column, keys));
            }
        }
        let (guard, column, keys) = best?;
        let budget = keys.len().saturating_mul(4).max(8);
        if keys.len() > 4096 || budget >= batch.len() {
            self.reverse.size_skips += 1;
            return None;
        }
        if !batch.delta_exceeds(budget, &mut self.reverse.epoch_bins) { return None; }
        let mut rows = match index.current_support_rows(g, batch.table, column, keys.iter(), budget,
            &mut self.reverse.key_probes, &mut self.reverse.copied_refs, &mut self.reverse.candidate_capacity_bytes) {
            None => { self.reverse.unavailable += 1; return None; }
            Some(Err(())) => { self.reverse.over_budget += 1; return None; }
            Some(Ok(rows)) => rows,
        };
        // The shared Entry proves its own predicate/visibility and watermark.
        // Restore the original (epoch, witness) order before any consumer runs.
        rows.retain_mut(|(epoch,w)| {
            let Some(entry) = batch.entry(*w) else { return false; };
            *epoch = entry.row.epoch;
            true
        });
        rows.sort_unstable_by(|a,b| {
            self.reverse.sort_comparisons += 1;
            a.cmp(b)
        });
        self.reverse.selected_batches += 1;
        self.reverse.selected_rows += rows.len() as u64;
        self.reverse.empty_batches += u64::from(rows.is_empty());
        Some(Selection { guard, rows })
    }
}
