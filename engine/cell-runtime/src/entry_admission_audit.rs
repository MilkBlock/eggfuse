//! Untimed observation of identical, complete Sieve guards on shared Entries.
//! Retains only Run-local batch identities and scalar counts, never row bindings.
use super::{Guard, Stats};
use crate::program::{Call, Program};
use rustc_hash::FxHashMap;
use serde::Serialize;

type BatchKey = (usize, u64, usize);
#[derive(Default, Serialize)]
struct Class {
    driver: usize,
    guards: Vec<(usize, Vec<usize>)>,
    consumers: Vec<(usize, usize)>,
    batches: u64,
    rows: u64,
    probes: u64,
    rejects: u64,
    reused_batches: u64,
    repeated_rows: u64,
    repeated_probes: u64,
    repeated_rejects: u64,
}
#[derive(Default)]
pub(super) struct Audit {
    plans: Vec<Vec<Option<usize>>>,
    classes: Vec<Class>,
    epoch: Option<u64>,
    seen: FxHashMap<BatchKey, (u64, u64, u64)>,
    batches: u64,
    restricted_batches: u64,
    empty_batches: u64,
    peak_run_groups: usize,
    events: Vec<[u64; 7]>,
    dropped_events: usize,
}
pub(crate) struct Probe {
    key: Option<BatchKey>,
    probes: u64,
    rejected: u64,
}
impl Audit {
    pub(super) fn new(p: &Program, rules: &[Vec<Vec<Guard>>]) -> Self {
        let mut audit = Self::default();
        let mut ids = FxHashMap::default();
        for (rid, atoms) in rules.iter().enumerate() {
            let mut plans = vec![];
            for (atom, guards) in atoms.iter().enumerate() {
                let Call::Table(table) = p.rules[rid].query[atom].call else {
                    plans.push(None); continue;
                };
                if guards.is_empty() { plans.push(None); continue; }
                // Preserve guard order so repeated probe counts must agree too.
                let id = *ids.entry((table, guards.clone())).or_insert_with(|| {
                    let id = audit.classes.len();
                    audit.classes.push(Class { driver: table,
                        guards: guards.iter().map(|g| (g.child, g.cols.clone())).collect(),
                        ..Default::default() });
                    id
                });
                audit.classes[id].consumers.push((rid, atom));
                plans.push(Some(id));
            }
            audit.plans.push(plans);
        }
        audit
    }
    pub(super) fn begin(&mut self, epoch: u64, rid: usize, atom: usize, node: usize,
        watermark: u64, stats: &Stats) -> Probe {
        if self.epoch != Some(epoch) {
            self.seen.clear();
            self.epoch = Some(epoch);
        }
        Probe { key: self.plans[rid][atom].map(|id| (node, watermark, id)),
            probes: stats.probes, rejected: stats.rejected }
    }
    pub(super) fn finish(&mut self, probe: Probe, rows: u64, full_delta: bool, stats: &Stats) {
        self.batches += 1;
        if !full_delta { self.restricted_batches += 1; return; }
        if rows == 0 { self.empty_batches += 1; return; }
        let Some(key) = probe.key else { return; };
        let counts = (rows, stats.probes - probe.probes, stats.rejected - probe.rejected);
        // Batch-only evidence for offline dominance tests, with an explicit cap.
        if self.events.len() < 65_536 {
            self.events.push([self.epoch.unwrap(), key.0 as u64, key.1, key.2 as u64,
                              counts.0, counts.1, counts.2]);
        } else { self.dropped_events += 1; }
        let class = &mut self.classes[key.2];
        class.batches += 1;
        class.rows += counts.0;
        class.probes += counts.1;
        class.rejects += counts.2;
        if let Some(prior) = self.seen.insert(key, counts) {
            assert_eq!(prior, counts, "same sealed Entry/guards/watermark must have identical admission counts");
            class.reused_batches += 1;
            class.repeated_rows += counts.0;
            class.repeated_probes += counts.1;
            class.repeated_rejects += counts.2;
        }
        self.peak_run_groups = self.peak_run_groups.max(self.seen.len());
    }
    pub(super) fn report(&self) -> serde_json::Value {
        serde_json::json!({"scope":"untimed batch census; no saved work or speed claim",
            "batches":self.batches,"restricted_batches":self.restricted_batches,"empty_batches":self.empty_batches,
            "peak_run_groups":self.peak_run_groups,"classes":self.classes,
            "event_fields":["epoch","entry_node","watermark","class","rows","probes","rejects"],
            "events":self.events,"dropped_events":self.dropped_events})
    }
}
