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
    pub subscription_rows_reused: u64,
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
            "dependency_headers":self.forward_dependency_size().0,
            "unit":"actual operations; created/removed/coalesced edges and live/peak occupancy are separate gauges"})
    }
}

/// A new Cell operation / reserved Function address has no old incidences.
/// Its fields were canonicalized in the same sealed, union-free epoch. The
/// ordinary replacement path remains authoritative for every existing row.
#[cfg(feature="sparse-cells")]
pub(super) fn subscribe_fresh(
    uses:&mut HashMap<u64,UseSet>,
    metrics:&mut Metrics,d:Dependency,values:&[Value],columns:Option<&[usize]>,
) {
    let mut refs=smallvec::SmallVec::<[u64;3]>::new();
    metrics.subscription_calls+=1;
    if let Some(columns)=columns {
        for column in columns.iter().copied().chain(std::iter::once(values.len()-1)) {
            let Value::Eq(id)=values[column] else {panic!("typed constructor Eq port")};refs.push(id);
        }
        metrics.canonical_subscription_calls+=1;
        metrics.subscription_value_visits+=refs.len() as u64;
        metrics.subscription_scalar_fields_skipped+=(values.len()-refs.len()) as u64;
    } else {
        fn collect(v:&Value,refs:&mut smallvec::SmallVec<[u64;3]>,visits:&mut u64) {
            *visits+=1;
            match v {Value::Eq(id)=>refs.push(*id),Value::Set(xs)=>for x in xs.iter() {collect(x,refs,visits);},_=>()}
        }
        for v in values {collect(v,&mut refs,&mut metrics.subscription_value_visits);}
    }
    metrics.subscription_root_reads_omitted+=refs.len() as u64;
    refs.sort_unstable();refs.dedup();
    for &id in &refs {insert(uses,metrics,id,d);}

}
