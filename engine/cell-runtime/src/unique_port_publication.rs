//! A complete input domain can prove a changed constructor has no peer before
//! it enters the completion queue. The domain is the existing native/boundary
//! port directory; its input routes are shared template code. Pending peers are
//! included. No key comparison, sorted candidate buffer or reverse list is built.
use super::*;

const MAX_VISITS: u64 = 64;
#[derive(Default, Serialize)]
pub(super) struct Counts {
    #[serde(skip)]
    remaining_unions: usize,
    #[serde(skip)]
    legacy_inflight: bool,
    attempts: u64,
    pending_checks: u64,
    pending_skips: u64,
    order_checks: u64,
    batch_skips: u64,
    legacy_skips: u64,
    predecessor_skips: u64,
    anchor_reads: u64,
    signal_visits: u64,
    static_steps: u64,
    site_checks: u64,
    operator_checks: u64,
    peer_rejections: u64,
    incomplete_rejections: u64,
    budget_rejections: u64,
    accepted: u64,
    pub(super) publications: u64,
    peak_visits: u64,
}
fn visits(c: &Counts) -> u64 {
    c.anchor_reads + c.signal_visits + c.static_steps
}
impl Graph {
    /// Connectivity commits precede key tasks. Publishing midway through a
    /// source batch could change the survivor chosen by its later equalities.
    pub(in crate::graph) fn commit_union_batch(&mut self, pairs: Vec<(u64, u64)>) -> Result<()> {
        let count = pairs.len();
        for (index, (a, b)) in pairs.into_iter().enumerate() {
            if let Some(c) = self.stable_ports.as_mut().and_then(|s| s.unique.as_mut()) {
                c.remaining_unions = count - index - 1;
            }
            let result = self.union(a, b);
            if let Some(c) = self.stable_ports.as_mut().and_then(|s| s.unique.as_mut()) {
                c.remaining_unions = 0;
                c.legacy_inflight = false;
            }
            result?;
        }
        Ok(())
    }
    pub(in crate::graph) fn unique_union_frontier(&mut self, from: u64) {
        if let Some(c) = self.stable_ports.as_mut().and_then(|s| s.unique.as_mut()) {
            // These legacy tasks are marked only after owned-port dispatch.
            c.legacy_inflight = self.uses.get(&from).is_some_and(|s| !s.is_empty());
        }
    }
    pub fn use_unique_port_publication(&mut self) -> Result<()> {
        self.use_local_port_conditions()?;
        if !self.ownership_settled() || !self.pending_unions.is_empty() {
            return Err("enable unique port publication at a settled boundary".into());
        }
        self.stable_ports
            .as_mut()
            .unwrap()
            .unique
            .get_or_insert_with(Counts::default);
        Ok(())
    }
    pub(super) fn unique_port_input(&mut self, f: FactRef, changed: &[usize]) -> bool {
        let Some(mut counts) = self.stable_ports.as_mut().unwrap().unique.take() else {
            return false;
        };
        counts.attempts += 1;
        let before = visits(&counts);
        let outcome = self.prove_unique_input(f, changed, &mut counts, before);
        counts.peak_visits = counts.peak_visits.max(visits(&counts) - before);
        let accepted = match outcome {
            Some(yes) => yes,
            None => {
                counts.budget_rejections += 1;
                false
            }
        };
        counts.accepted += u64::from(accepted);
        self.stable_ports.as_mut().unwrap().unique = Some(counts);
        accepted
    }
    fn prove_unique_input(
        &self,
        f: FactRef,
        changed: &[usize],
        counts: &mut Counts,
        before: u64,
    ) -> Option<bool> {
        let owner = self.ownership.as_ref().unwrap();
        let stored = self.stable_node(f)?;
        let table = stored.table;
        counts.pending_checks += 1;
        if owner.pending.contains(table, &f) {
            counts.pending_skips += 1;
            return Some(false);
        }
        counts.order_checks += 1;
        if counts.remaining_unions != 0 || !self.pending_unions.is_empty() {
            counts.batch_skips += 1;
            return Some(false);
        }
        if counts.legacy_inflight || !self.dirty.is_empty() || !self.dirty_markers.is_empty() {
            counts.legacy_skips += 1;
            return Some(false);
        }
        if owner
            .pending
            .first(None)
            .is_some_and(|(first, _)| first < f)
        {
            counts.predecessor_skips += 1;
            return Some(false);
        }
        let columns = self.program.repair_ports.key_eq_columns[table].as_ref()?;
        let mut best = None;
        for &column in columns {
            if visits(counts) - before >= MAX_VISITS {
                return None;
            }
            counts.anchor_reads += 1;
            let Ok(Value::Eq(id)) = self.read_stable_column(stored, column) else {
                counts.incomplete_rejections += 1;
                return Some(false);
            };
            let size = owner.boundaries.get(&id).map_or(0, |s| s.len())
                + usize::from(self.native_signal(id).is_some());
            // Prefer an unchanged input when domain sizes tie. Either domain
            // is complete: union moves all signal bindings before dispatch.
            let rank = (size, changed.contains(&column));
            if best.is_none_or(|(_, _, old)| rank < old) {
                best = Some((column, id, rank));
            }
        }
        let Some((column, id, _)) = best else {
            counts.incomplete_rejections += 1;
            return Some(false);
        };
        let mut source_seen = false;
        for signal in owner
            .boundaries
            .get(&id)
            .into_iter()
            .flat_map(|s| s.iter().copied())
            .chain(self.native_signal(id))
        {
            if visits(counts) - before >= MAX_VISITS {
                return None;
            }
            counts.signal_visits += 1;
            let Ok(uses) = self.cell_field_uses(signal, column) else {
                counts.incomplete_rejections += 1;
                return Some(false);
            };
            for position in 0..uses.len() {
                if visits(counts) - before >= MAX_VISITS {
                    return None;
                }
                counts.static_steps += 1;
                let Some(fact) = uses.fact(position, true) else { continue; };
                if self.unique_input_site(fact, f, table, counts, &mut source_seen) {
                    return Some(false);
                }
            }
        }
        if !source_seen {
            counts.incomplete_rejections += 1;
        }
        Some(source_seen)
    }
    // True means a live peer exists. Source-order pending status is irrelevant
    // to uniqueness: an unprocessed peer must forbid direct publication too.
    fn unique_input_site(
        &self,
        fact: FactRef,
        source: FactRef,
        table: usize,
        counts: &mut Counts,
        source_seen: &mut bool,
    ) -> bool {
        counts.site_checks += 1;
        let Some(stored) = self.stable_node(fact) else {
            return false;
        };
        counts.operator_checks += 1;
        if stored.table != table {
            return false;
        }
        if fact == source {
            *source_seen = true;
            return false;
        }
        counts.peer_rejections += 1;
        true
    }
    pub(super) fn unique_publication_report(&self) -> J {
        match self.stable_ports.as_ref().and_then(|s| s.unique.as_ref()) {
            Some(counts) => json!({"enabled":true,"stats":counts,"visit_budget":MAX_VISITS,
                "scope":"complete live input-domain uniqueness; shared wiring, no per-instance consumer index"}),
            None => json!({"enabled":false}),
        }
    }
}
