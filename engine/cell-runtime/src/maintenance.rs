//! Observed maintenance work and physical reverse-index occupancy. Logical
//! edge movement is separate from actual insertion/traversal operations.
use super::*;
#[derive(Default, Serialize)]
pub struct Metrics {
    pub subscription_calls: u64,
    pub subscription_value_visits: u64,
    pub canonical_subscription_calls: u64,
    pub subscription_scalar_fields_skipped: u64,
    pub subscription_root_reads_omitted: u64,
    pub subscription_sets_replaced_in_place: u64,
    pub reverse_insert_attempts: u64,
    pub reverse_remove_attempts: u64,
    pub reverse_edges_created: u64,
    pub reverse_edges_removed: u64,
    pub union_frontier_probes: u64,
    pub union_wake_visits: u64,
    pub union_redirected_edges: u64,
    pub reverse_merge_inserts: u64,
    pub reverse_edges_coalesced: u64,
    pub live_reverse_edges: u64,
    pub peak_reverse_edges: u64,
    pub repair_key_probes: u64,
    pub repair_candidate_checks: u64,
}
#[inline]
pub(super) fn insert(uses: &mut HashMap<u64, UseSet>, m: &mut Metrics, id: u64, d: Dependency) {
    m.reverse_insert_attempts += 1;
    let bucket = uses.entry(id).or_default();
    let before = bucket.len();
    bucket.insert(d);
    let added = (bucket.len() - before) as u64;
    m.reverse_edges_created += added;
    m.live_reverse_edges += added;
    m.peak_reverse_edges = m.peak_reverse_edges.max(m.live_reverse_edges);
}
#[inline]
pub(super) fn remove(bucket: &mut UseSet, m: &mut Metrics, d: Dependency) {
    m.reverse_remove_attempts += 1;
    let before = bucket.len();
    bucket.remove(&d);
    let removed = (before - bucket.len()) as u64;
    m.reverse_edges_removed += removed;
    m.live_reverse_edges -= removed;
}
impl Graph {
    pub fn maintenance_report(&self) -> J {
        let observed = self.uses.values().map(|s| s.len() as u64).sum::<u64>();
        assert_eq!(
            observed, self.maintenance.live_reverse_edges,
            "reverse edge accounting"
        );
        json!({"stats":self.maintenance,"reverse_headers":self.uses.len(),
            "dependency_headers":self.dependencies.len(),
            "unit":"actual operations; created/removed/coalesced edges and live/peak occupancy are separate gauges"})
    }
}

#[cfg(feature="sparse-cells")]
pub(super) fn replace_subscriptions(
    uses:&mut HashMap<u64,UseSet>, dependencies:&mut HashMap<Dependency,smallvec::SmallVec<[u64;3]>>,
    metrics:&mut Metrics, parents:&Parents, d:Dependency, mut refs:smallvec::SmallVec<[u64;3]>,
) {
        refs.sort_unstable();
        refs.dedup();
        use std::collections::hash_map::Entry;
        let (mut old, refs) = match dependencies.entry(d) {
            Entry::Vacant(slot) => {
                for &id in &refs {
                    maintenance::insert(uses, metrics, id, d);
                }
                if !refs.is_empty() {
                    slot.insert(refs);
                }
                return;
            }
            Entry::Occupied(slot) if *slot.get() == refs => return,
            Entry::Occupied(slot) if refs.is_empty() => (slot.remove(), &[][..]),
            Entry::Occupied(slot) => {
                // Keep the witness's existing directory slot. Only its Eq
                // footprint changes; removing/reinserting the same witness
                // cannot affect the reverse-edge difference below.
                metrics.subscription_sets_replaced_in_place += 1;
                let stored = slot.into_mut();
                (std::mem::replace(stored, refs), stored.as_slice())
            }
        };
        for id in &mut old {
            *id = root(parents, *id);
        }
        for id in &old {
            if !refs.contains(id)
                && let Some(bucket) = uses.get_mut(id)
            {
                maintenance::remove(bucket, metrics, d);
                if bucket.is_empty() {
                    uses.remove(id);
                }
            }
        }
        for &id in refs {
            if !old.contains(&id) {
                maintenance::insert(uses, metrics, id, d);
            }
        }
}
