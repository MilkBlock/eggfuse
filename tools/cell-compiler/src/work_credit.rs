//! Deterministic credit from two complete executions of the same workload.
//! These are equally weighted observed operations, not calibrated nanoseconds.
use serde_json::{Value as J, json};
use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Work(pub BTreeMap<String, u64>);
impl Work {
    pub fn read(report: &J) -> Result<Self, String> {
        let mut work = BTreeMap::new();
        for (group, fields) in [
            ("", &["key_lookup_calls", "fact_decode_calls", "fact_decode_ports"][..]),
            ("stats", &["decoded_rows", "repaired_dependencies", "residual_candidates", "key_operations", "handoff_attempts", "constructor_requests", "union_requests", "cells_created"]),
            ("stage_spine/stats", &[
                "legacy_entry_writes", "legacy_retirement_checks", "legacy_cursor_probes", "node_cursor_reads",
                "root_handles_created", "contexts_created", "captured_anchors", "capture_reads",
                "origin_key_slots", "origin_map_writes", "origin_map_probes",
                "history_capture_reads", "history_slots_written", "history_allocations",
                "query_receipt_attempts", "context_reads", "port_cache_fills", "guards",
            ]),
            ("entry_schedule/stats", &[
                "entry_publication_writes", "entry_retirement_checks", "predicate_checks", "row_decodes",
            ]),
            ("publication", &["row_reads", "column_rows", "range_rows", "neighbor_rows"]),
        ] {
            for field in fields {
                let key = if group.is_empty() { field.to_string() } else { format!("{group}/{field}") };
                let value = report.pointer(&format!("/{key}")).and_then(J::as_u64)
                    .ok_or_else(|| format!("missing measured-work counter {key}"))?;
                work.insert(key, value);
            }
        }
        for field in ["attempts", "steps", "effect_steps", "port_writes", "row_copies"] {
            let key = format!("repair_cells/stats/{field}");
            let stats = &report["repair_cells"]["stats"];
            let value = if report["repair_cells"]["enabled"] == false { 0 }
                else { stats[field].as_u64().ok_or_else(|| format!("missing repair work {field}"))? };
            work.insert(key, value);
        }
        for field in ["attempts", "port_checks", "field_copies"] {
            let key = format!("repair_ports/stats/{field}");
            let value = if report["repair_ports"]["enabled"] == false { 0 }
                else { report["repair_ports"]["stats"][field].as_u64().ok_or_else(|| format!("missing repair port work {field}"))? };
            work.insert(key, value);
        }
        for field in ["subscription_calls", "subscription_value_visits", "reverse_insert_attempts", "reverse_remove_attempts",
            "union_frontier_probes", "union_wake_visits", "reverse_merge_inserts", "repair_key_probes", "repair_candidate_checks"] {
            let key = format!("maintenance/stats/{field}");
            let value = report["maintenance"]["stats"][field].as_u64().ok_or_else(||format!("missing maintenance work {field}"))?;
            work.insert(key, value);
        }
        for field in ["birth_attempts", "prepare_reads", "completion_allocations", "completion_visits", "port_checks", "row_copies", "obligation_checks", "obligation_reads"] {
            let key = format!("local_union_cells/stats/{field}");
            let value = if report["local_union_cells"]["enabled"] == false {0}
                else {report["local_union_cells"]["stats"][field].as_u64().ok_or_else(||format!("missing local completion work {field}"))?};
            work.insert(key, value);
        }
        for field in ["fallback_queries", "fallback_rows"] {
            let key=format!("local_union_cells/{field}");
            work.insert(key,report["local_union_cells"][field].as_u64().ok_or("missing coverage fallback work")?);
        }
        for field in ["marker_entries","marker_anchor_reads","boundary_insert_attempts","boundary_probes",
            "owner_visits","body_visits","port_checks","row_copies","key_completions","boundary_rebuilds","boundary_body_reads",
            "domain_queries","domain_owner_visits","domain_body_visits","domain_legacy_visits","domain_results","unbound_query_calls","unbound_query_rows",
            "signal_binding_reads","signal_bindings_created","signal_bindings_retired","component_signal_retire_visits","signal_port_attaches","signal_port_detaches","signal_activations","slice_steps",
            "marker_union_requests","domain_planning_calls","domain_planning_signals","domain_planning_slice_steps","domain_signal_visits","domain_slice_steps",
            "components_created","components_retired","composition_entry_reads","composition_missing_sources",
            "composition_transition_probes","composition_unbaked_fallbacks","composition_requests","composition_shape_builds","composition_materializations","composition_shape_steps","composition_frames",
            "dispatch_heap_pushes","dispatch_heap_pops","dispatch_comparisons","dispatch_scratch_growths"] {
            let key=format!("cell_ownership/stats/{field}");
            let value=if report["cell_ownership"]["enabled"]==false {0} else {
                report["cell_ownership"]["stats"][field].as_u64().ok_or_else(||format!("missing ownership work {field}"))?
            };
            work.insert(key,value);
        }
        Ok(Self(work))
    }
    pub fn savings(&self, trial: &Self) -> (i128, J) {
        let mut changes = BTreeMap::new();
        let mut net = 0i128;
        for (name, &before) in &self.0 {
            let after = trial.0[name];
            let saved = i128::from(before) - i128::from(after);
            net += saved;
            changes.insert(name, json!({"before":before,"after":after,"saved":saved}));
        }
        (net, json!({"net_saved_operations":net,"counters":changes,
            "unit":"one observed operation per counter; equal weights, not elapsed time",
            "performance_admission":"unvalidated proxy; a positive sum alone does not establish acceleration",
            "scope":"complete inference including failed candidates and unused source captures; excludes compilation and replay cost"}))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn lookup_savings_must_pay_for_unused_capture_and_failed_reads() {
        let old = Work(BTreeMap::from([("lookup".into(), 100), ("capture".into(), 0), ("failed_read".into(), 0)]));
        let mut trial = old.clone();
        trial.0.insert("lookup".into(), 90);
        trial.0.insert("capture".into(), 8);
        trial.0.insert("failed_read".into(), 3);
        assert_eq!(old.savings(&trial).0, -1);
        trial.0.insert("capture".into(), 2);
        assert_eq!(old.savings(&trial).0, 5);
    }
}
