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
            ("stats", &["decoded_rows", "repaired_dependencies", "residual_candidates", "key_operations", "handoff_attempts", "constructor_requests", "union_requests", "cells_created", "register_result_writes"]),
            ("stage_spine/stats", &[
                "legacy_entry_writes", "legacy_retirement_checks", "legacy_cursor_probes", "node_cursor_reads",
                "root_handles_created", "contexts_created", "captured_anchors", "capture_reads",
                "origin_key_slots", "origin_map_writes", "origin_map_probes",
                "history_capture_reads", "history_slots_written", "history_allocations",
                "query_receipt_attempts", "context_reads", "port_cache_fills", "guards", "cell_query_result_writes",
                "scoped_anchor_checks", "scoped_direct_checks", "scoped_receipt_checks",
                "local_witness_contexts", "local_witness_route_probes", "local_witness_route_steps", "local_witness_key_fields",
                "local_witness_route_comparisons", "local_witness_read_index_probes",
                "local_witness_receipt_probes", "local_witness_receipt_steps", "local_witness_history_borrows",
                "direct_publication_hash_probes", "fragment_packets", "fragment_receipt_spills",
                // Charge every Cell output, including single/mixed Cells, and
                // the boundary work that a compiled output can replace.
                // Fragment coverage/check counters are subsets, not extra work.
                "cell_output_receipts", "cell_output_slot_reads", "effect_output_copies", "receipt_attempts",
                // Each delivered output still resolves its receipt before
                // Entry selection; skipping visibility checks does not erase it.
                "cell_output_deliveries",
                "completion_boundary_records", "completion_boundary_reads", "completion_order_checks", "completion_cell_visits",
            ]),
            ("entry_schedule/stats", &[
                "entry_publication_writes", "entry_retirement_checks", "predicate_checks", "row_decodes",
                "publication_slot_probes", "publication_pending_pushes", "fragment_pending_writes", "fragment_pending_reads",
            ]),
            // Count dispatch, direct donor access and additional full-key
            // validation. register_result_writes already includes prefix
            // field writes; do not charge its subset again. Primitive guard
            // checks likewise replace the original kernel instructions.
            ("stats/register_prefix", &[
                "context_reads", "plan_comparisons", "row_reads", "key_fields",
                "plan_index_probes", "source_index_probes",
                "publication_probes", "receipt_probes", "receipt_steps", "history_borrows",
            ]),
            ("publication", &["row_reads", "column_rows", "range_rows", "neighbor_rows"]),
            // Hash/index work precedes row decoding, so it is not represented
            // by decoded_rows or key_lookup_calls. Include failed admission,
            // grouping, reverse enumeration and summary maintenance.
            ("free_join", &[
                "entry_rows", "entry_probes", "entry_cache_hits",
                "entry_bucket_rows_examined", "entry_bucket_rows_materialized",
                "cover_rows", "key_groups", "probes", "bucket_rows_examined", "bucket_rows_materialized",
                "reverse_keys", "reverse_refs", "reverse_epoch_bins", "disjoint_key_reads",
            ]),
            ("sieve/stats", &["rule_uses", "build_rows", "update_rows", "dependency_rows", "probes"]),
        ] {
            for field in fields {
                let key = if group.is_empty() { field.to_string() } else { format!("{group}/{field}") };
                let value = report.pointer(&format!("/{key}")).and_then(J::as_u64)
                    .ok_or_else(|| format!("missing measured-work counter {key}"))?;
                work.insert(key, value);
            }
        }
        // Static Cell scopes replace candidate-prefix copies with slot clears.
        // Query-host point reads, result writes and key operations are already
        // in the ordinary counters. Charge only the new preparation/dispatch
        // and buffer work here, never count a worker answer as saved work.
        for field in ["admission_entry_checks", "admission_table_checks", "seed_selection_visits", "entry_headers",
            "chunks", "frame_allocations", "batch_buffers", "answer_buffer_allocations"] {
            let value = if report["query_workers"]["enabled"] == true {
                report["query_workers"]["stats"][field].as_u64()
                    .ok_or_else(|| format!("missing query worker work {field}"))?
            } else { 0 };
            work.insert(format!("query_workers/stats/{field}"), value);
        }
        let cell_tasks = match report["query_workers"].get("organization") {
            None => false, // recorded 13cfd235 Entry-batch host
            Some(J::String(version)) if version == "cell-run/v1" || version == "cell-run/v2" => true,
            _ => return Err("unknown query worker organization".into()),
        };
        for field in ["rule_admissions", "entry_mask_checks", "cell_source_reads",
            "cell_order_comparisons", "cell_queue_growths", "borrowed_job_headers",
            "serial_order_headers", "seed_range_comparisons", "winner_order_comparisons",
            "deferred_winner_moves", "completion_binding_moves"] {
            let value = if cell_tasks {
                report["query_workers"]["stats"][field].as_u64()
                    .ok_or_else(|| format!("missing Cell task work {field}"))?
            } else { 0 };
            work.insert(format!("query_workers/stats/{field}"), value);
        }
        for field in ["task_order_headers", "completion_slot_initializations", "completion_slot_writes"] {
            let value = if report["query_workers"]["organization"] == "cell-run/v2" {
                report["query_workers"]["stats"][field].as_u64()
                    .ok_or_else(|| format!("missing Cell completion work {field}"))?
            } else { 0 };
            work.insert(format!("query_workers/stats/{field}"), value);
        }
        // Domain traversal and exact guards are folded into their existing
        // ownership/stable-port counters below. Only new scratch/metadata work
        // is charged here, once; constructor coverage itself earns no credit.
        for field in ["domain_key_fields", "metadata_reads", "candidate_pushes",
            "candidate_growths", "candidate_sort_comparisons"] {
            let value = if report["query_workers"]["organization"] == "cell-run/v2" {
                report["query_workers"]["stats"]["constructors"][field].as_u64()
                    .ok_or_else(|| format!("missing constructor query work {field}"))?
            } else { 0 };
            work.insert(format!("query_workers/stats/constructors/{field}"), value);
        }
        // Charge both paths, summing rules so changing context admission cannot
        // hide work by adding/removing a per-rule key from the comparison.
        let contexts = report["local_context"]["rules"].as_object()
            .ok_or("missing context work report")?;
        for field in ["prefix_copies", "prefix_slots_copied", "branch_slot_clears",
            "terminal_binding_copies", "terminal_slots_copied", "terminal_scratch_slots", "terminal_result_writes"] {
            let mut total = 0;
            for stats in contexts.values() {
                total += stats[field].as_u64().ok_or_else(|| format!("missing context work {field}"))?;
            }
            work.insert(format!("local_context/{field}"), total);
        }
        // Positive receipt/prefix hits and *_avoided are outcomes, not negative
        // work. Actual lookup savings already lower key_lookup_calls (including
        // PointPorts hits that never queried the graph). Spine donor reads are
        // already included in decoded_rows; local_witness_row_reads is that subset.
        // Entry slot probes cover ordinary and fragment publication equally;
        // fragment_slot_probes/replacements are subsets, not extra lookups.
        // local_witness_route_index_probes is the direct-index subset of
        // local_witness_route_probes, not another dispatch to charge.
        // Free Join membership_only/shared_column_reads are entry_probes
        // subsets. Sieve reused_summaries is a rule_uses subset. Rejections,
        // skips and successful filter outcomes do not earn additional credit.
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
            "signal_binding_reads","signal_root_queries","signal_parent_probes","component_lifetime_updates","component_lifetime_growths","signal_bindings_created","signal_bindings_retired","component_signal_retire_visits","signal_port_attaches","signal_port_detaches","signal_activations","slice_steps",
            "marker_union_requests","domain_planning_calls","domain_planning_signals","domain_planning_slice_steps","domain_signal_visits","domain_slice_steps","domain_route_probes","domain_column_checks","domain_legacy_fact_probes","domain_type_guards","query_class_probes","query_class_range_jumps",
            "components_created","components_retired","composition_entry_reads","composition_missing_sources",
            "composition_transition_probes","composition_unbaked_fallbacks","composition_requests","composition_shape_builds","composition_materializations","composition_shape_steps","composition_frames",
            "dispatch_heap_pushes","dispatch_heap_pops","dispatch_comparisons","dispatch_scratch_growths"] {
            let key=format!("cell_ownership/stats/{field}");
            let value=if report["cell_ownership"]["enabled"]==false {0} else {
                report["cell_ownership"]["stats"][field].as_u64().ok_or_else(||format!("missing ownership work {field}"))?
            };
            work.insert(key,value);
        }
        // Stable fields and equality-guarded keys replace maintenance with
        // reads/guards. Their work must not disappear from Bake's ledger.
        for field in ["rows_installed", "node_retirement_probes", "node_lookups", "ports_installed", "row_views", "port_reads", "root_resolutions", "root_parent_probes",
            "notifications", "notified_columns", "legacy_key_enqueues", "equality_enqueues", "equality_completions",
            "key_candidates", "key_field_comparisons", "pending_candidate_skips", "birth_hint_probes", "port_domain_probes"] {
            let key = format!("stable_ports/stats/{field}");
            let value = if report["stable_ports"]["enabled"] == true {
                report["stable_ports"]["stats"][field].as_u64()
                    .ok_or_else(||format!("missing stable-port work {field}"))?
            } else { 0 };
            work.insert(key, value);
        }
        for field in ["attempts", "boundary_signals", "boundary_sites", "condition_visits",
            "inactive_sites", "pending_sites", "operator_guards", "scalar_guards", "equality_guards", "shared_symbol_guards",
            "anchor_probes", "boundary_uncompiled_steps", "boundary_indexed_steps", "local_candidates", "boundary_candidates",
            "candidate_buffer_growths", "candidate_sort_comparisons"] {
            let key = format!("stable_ports/local_conditions/stats/{field}");
            let conditions = &report["stable_ports"]["local_conditions"];
            let value = if conditions["enabled"] == true {
                conditions["stats"][field].as_u64().ok_or_else(|| format!("missing local condition work {field}"))?
            } else { 0 };
            work.insert(key, value);
        }
        // Actual guards (including speculative reads) are already counted
        // above. Charge their dispatch/collection too, without counting the
        // speculative subset a second time or using worker-dependent loads.
        // Candidate directory lookups are included in stable_ports/node_lookups;
        // the worker and preparation lookup counts are subsets of that total.
        let parallel = &report["stable_ports"]["parallel_guards"];
        for field in ["candidate_batches", "rounds", "chunks", "prepared_candidates",
            "collected_results", "scratch_allocations"] {
            let value = if parallel["enabled"] == true {
                parallel["stats"][field].as_u64().ok_or_else(|| format!("missing parallel guard work {field}"))?
            } else { 0 };
            work.insert(format!("stable_ports/parallel_guards/stats/{field}"), value);
        }
        for field in ["pool_builds", "workers"] {
            let value = if parallel["enabled"] == true {
                parallel[field].as_u64().ok_or_else(|| format!("missing guard pool work {field}"))?
            } else { 0 };
            work.insert(format!("stable_ports/parallel_guards/{field}"), value);
        }
        let batches = &report["stable_ports"]["completion_batches"];
        for field in ["attempts", "queue_head_visits", "queue_comparisons", "queue_successor_reads",
            "preflight_checks", "dispatches", "prepared_tasks", "prepared_candidates", "pending_probes",
            "read_set_slots", "read_set_comparisons", "read_set_queries",
            "result_refreshes", "collected_tasks", "recorded_answers", "selection_checks", "order_checks", "scratch_allocations"] {
            let value = if batches["enabled"] == true {
                batches["stats"][field].as_u64().ok_or_else(|| format!("missing completion batch work {field}"))?
            } else { 0 };
            work.insert(format!("stable_ports/completion_batches/stats/{field}"), value);
        }
        let overlap = &batches["overlap"];
        for field in ["epochs", "base_snapshots", "task_spawns", "projected_tasks", "input_buffer_allocations", "activity_allocations", "reader_activity_updates", "channel_builds", "channel_receives", "slot_publications", "slot_abandons", "slot_collection_reads", "ordered_slot_reads", "row_handle_clones", "result_buffer_allocations"] {
            let value = if overlap["enabled"] == true {
                overlap["stats"][field].as_u64().ok_or_else(|| format!("missing overlap work {field}"))?
            } else { 0 };
            work.insert(format!("stable_ports/completion_batches/overlap/{field}"), value);
        }
        for field in ["writes", "growths", "copied_units", "merged_entries"] {
            let value = if overlap["enabled"] == true {
                overlap["stats"]["overlay"][field].as_u64().ok_or_else(|| format!("missing overlay work {field}"))?
            } else { 0 };
            work.insert(format!("stable_ports/completion_batches/overlay/{field}"), value);
        }
        for field in ["scope_requests", "head_probes", "head_updates", "legacy_frontier_probes", "cause_probes", "cause_comparisons", "cause_growths", "mixed_epoch_inserts", "advanced_task_epochs", "completion_epoch_checks", "completion_epoch_joins"] {
            let key = format!("scoped_completion/stats/{field}");
            let value = if report["scoped_completion"]["enabled"] == true {
                report["scoped_completion"]["stats"][field].as_u64().ok_or_else(||format!("missing scoped completion work {field}"))?
            } else { 0 };
            work.insert(key,value);
        }
        for field in ["table_probes", "shadow_probes", "live_probes", "base_probes", "base_head_reads", "overlay_head_reads", "table_activations", "shadow_insert_attempts", "live_inserts", "live_removes", "base_successor_ranges", "base_successor_steps", "merge_live_probes"] {
            let value = if report["scoped_completion"]["enabled"] == true {
                report["scoped_completion"]["queue_overlay"]["stats"][field].as_u64()
                    .ok_or_else(||format!("missing queue overlay work {field}"))?
            } else { 0 };
            work.insert(format!("scoped_completion/queue_overlay/{field}"), value);
        }
        for field in ["attempts", "pending_checks", "order_checks", "anchor_reads", "signal_visits", "static_steps", "site_checks", "operator_checks", "publications"] {
            let proof = &report["stable_ports"]["unique_publication"];
            let value = if proof["enabled"] == true {
                proof["stats"][field].as_u64().ok_or_else(|| format!("missing unique publication work {field}"))?
            } else { 0 };
            work.insert(format!("stable_ports/unique_publication/stats/{field}"), value);
        }
        for field in ["ruleset_waits", "eager_waits", "readiness_dependency_checks", "publication_table_checks", "rhs_demand_probes", "rhs_demand_growths", "rhs_selected_rules", "bound_rhs_attempts", "bound_rhs_rule_checks", "bound_rhs_ops", "bound_rhs_expression_steps", "bound_rhs_input_reads", "bound_rhs_key_reads", "bound_rhs_value_slots", "bound_rhs_scratch_growths", "bound_rhs_overlay_checks"] {
            let key = format!("scoped_executor/stats/{field}");
            let value = if report["scoped_executor"]["enabled"] == true {
                report["scoped_executor"]["stats"][field].as_u64().ok_or_else(||format!("missing scoped execution work {field}"))?
            } else { 0 };
            work.insert(key,value);
        }
        for field in ["forecasts", "seed_roots", "seed_candidates", "root_visits", "signal_visits", "static_steps", "output_reads", "legacy_boundaries", "membership_checks", "scratch_growths", "pure_epoch_source_steps", "pure_epoch_birth_checks", "pure_epoch_order_checks", "pure_epoch_order_refinements", "pure_epoch_frontier_roots", "pure_epoch_frontier_checks"] {
            let key = format!("port_completion/stats/{field}");
            let value = if report["port_completion"]["enabled"] == true {
                report["port_completion"]["stats"][field].as_u64().ok_or_else(||format!("missing port completion work {field}"))?
            } else { 0 };
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

#[cfg(all(test, feature = "sparse-cells"))]
#[test]
fn query_worker_credit_charges_buffers_and_never_rewards_answer_counts() {
    use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
    let source = include_str!("../tests/fixtures/cell-point-queries.egg");
    let core = eggfuse_bake::device_frontend::core("query-credit", source).unwrap();
    let p = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let mut e = Executor::new(Graph::new_with_local_congruence(p).unwrap(), false);
    e.use_query_workers(1, 16).unwrap();
    e.execute().unwrap();
    let mut report = e.report();
    let work = Work::read(&report).unwrap();
    assert!(work.0["query_workers/stats/frame_allocations"] > 0);
    assert!(work.0["query_workers/stats/chunks"] > 0);
    report["query_workers"]["stats"]["answers"] = u64::MAX.into();
    assert_eq!(Work::read(&report).unwrap().0, work.0);
    report["query_workers"]["stats"].as_object_mut().unwrap().remove("frame_allocations");
    assert!(Work::read(&report).is_err());
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn witness_and_fragment_credit_charges_work_without_counting_outcomes_twice() {
        use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
        let source = r#"
(datatype E (N i64) (A E) (B E) (Edge E i64) (Out E i64))
(ruleset make) (ruleset consume)
(rule ((= x (N n))) ((A x) (B x)) :ruleset make)
(rule ((B x) (= a (A x)) (Edge x n)) ((Out a n)) :ruleset consume)
(Edge (N 0) 1) (Edge (N 0) 2)
(run-schedule (seq (run make) (run consume)))
"#;
        let core = eggfuse_bake::device_frontend::core("prefix-credit", source).unwrap();
        let p = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
        let mut executor = Executor::new(Graph::new(p).unwrap(), false);
        #[cfg(feature = "sparse-cells")]
        executor.use_entry_publications().unwrap();
        executor.execute().unwrap();
        let report = executor.report();
        let baseline = Work::read(&report).unwrap();
        let mut context = report.clone();
        context["local_context"]["rules"]["scope-ledger"] = json!({
            "prefix_copies": 1, "prefix_slots_copied": 8, "branch_slot_clears": 0,
            "terminal_binding_copies": 0, "terminal_slots_copied": 0, "terminal_scratch_slots": 0, "terminal_result_writes": 0,
        });
        let copied = Work::read(&context).unwrap();
        assert_eq!(baseline.savings(&copied).0, -9);
        context["local_context"]["rules"]["scope-ledger"] = json!({
            "prefix_copies": 0, "prefix_slots_copied": 0, "branch_slot_clears": 10,
            "terminal_binding_copies": 0, "terminal_slots_copied": 0, "terminal_scratch_slots": 0, "terminal_result_writes": 0,
        });
        // Replacing a copy with more charged clears must not earn credit.
        assert_eq!(copied.savings(&Work::read(&context).unwrap()).0, -1);
        context["local_context"]["rules"]["scope-ledger"]["terminal_scratch_slots"] = json!(2);
        context["local_context"]["rules"]["scope-ledger"]["terminal_result_writes"] = json!(3);
        assert_eq!(copied.savings(&Work::read(&context).unwrap()).0, -6);
        context["local_context"]["rules"]["scope-ledger"].as_object_mut().unwrap().remove("branch_slot_clears");
        assert!(Work::read(&context).unwrap_err().contains("missing context work branch_slot_clears"));
        // Start from a real complete report, then isolate ledger behavior. This
        // is an accounting regression, not a synthetic performance result.
        let bump = |report: &mut J, key: &str| {
            let value = report.pointer_mut(key).unwrap();
            *value = json!(value.as_u64().unwrap() + 1);
        };
        let charged = [
            "/stats/register_result_writes", "/stage_spine/stats/cell_query_result_writes",
            "/stats/register_prefix/context_reads", "/stats/register_prefix/plan_comparisons",
            "/stats/register_prefix/plan_index_probes", "/stats/register_prefix/source_index_probes",
            "/stats/register_prefix/row_reads", "/stats/register_prefix/key_fields",
            "/stats/register_prefix/publication_probes", "/stats/register_prefix/receipt_probes", "/stats/register_prefix/receipt_steps",
            "/stats/register_prefix/history_borrows", "/stage_spine/stats/local_witness_history_borrows",
            "/stage_spine/stats/local_witness_contexts", "/stage_spine/stats/local_witness_route_probes",
            "/stage_spine/stats/local_witness_route_steps", "/stage_spine/stats/local_witness_key_fields",
            "/stage_spine/stats/local_witness_route_comparisons", "/stage_spine/stats/local_witness_read_index_probes",
            "/stage_spine/stats/local_witness_receipt_probes", "/stage_spine/stats/local_witness_receipt_steps",
            "/stage_spine/stats/direct_publication_hash_probes", "/stage_spine/stats/fragment_packets",
            "/stage_spine/stats/fragment_receipt_spills", "/entry_schedule/stats/publication_slot_probes",
            "/stage_spine/stats/cell_output_receipts", "/stage_spine/stats/cell_output_slot_reads",
            "/stage_spine/stats/effect_output_copies", "/stage_spine/stats/receipt_attempts",
            "/stage_spine/stats/cell_output_deliveries",
            "/stage_spine/stats/completion_boundary_records", "/stage_spine/stats/completion_boundary_reads",
            "/stage_spine/stats/completion_order_checks", "/stage_spine/stats/completion_cell_visits",
            "/entry_schedule/stats/publication_pending_pushes", "/entry_schedule/stats/fragment_pending_writes",
            "/entry_schedule/stats/fragment_pending_reads",
            "/free_join/entry_rows", "/free_join/entry_probes", "/free_join/entry_cache_hits",
            "/free_join/entry_bucket_rows_examined", "/free_join/entry_bucket_rows_materialized",
            "/free_join/cover_rows", "/free_join/key_groups", "/free_join/probes",
            "/free_join/bucket_rows_examined", "/free_join/bucket_rows_materialized",
            "/free_join/reverse_keys", "/free_join/reverse_refs", "/free_join/reverse_epoch_bins", "/free_join/disjoint_key_reads",
            "/sieve/stats/rule_uses", "/sieve/stats/build_rows", "/sieve/stats/update_rows",
            "/sieve/stats/dependency_rows", "/sieve/stats/probes",
        ];
        let mut costs = report.clone();
        for key in charged { bump(&mut costs, key); }
        assert_eq!(baseline.savings(&Work::read(&costs).unwrap()).0, -(charged.len() as i128));
        let mut outcomes = report.clone();
        for key in [
            "/stats/register_prefix/eligible_seeds", "/stats/register_prefix/plan_hits",
            "/stats/register_prefix/donor_hits", "/stats/register_prefix/key_reads_avoided",
            "/stats/register_prefix/receipt_hits", "/stage_spine/stats/local_witness_receipt_hits",
            "/stats/register_prefix/field_writes", "/stats/register_prefix/primitive_checks",
            "/stage_spine/stats/local_witness_hits", "/stage_spine/stats/fragment_direct_inserts_avoided",
            "/stage_spine/stats/local_witness_route_index_probes",
            "/stage_spine/stats/fragment_deliveries", "/entry_schedule/stats/fragment_slot_probes",
            "/stage_spine/stats/fragment_receipts", "/stage_spine/stats/fragment_delivery_checks",
            "/stage_spine/stats/cell_output_checks", "/stage_spine/stats/effect_outputs_reused",
            "/entry_schedule/stats/fragment_slot_replacements", "/entry_schedule/stats/publication_pending_reuses",
            "/free_join/membership_only", "/free_join/shared_column_reads", "/free_join/entry_rejections",
            "/free_join/disjoint_rule_skips", "/sieve/stats/reused_summaries", "/sieve/stats/rejected",
            "/sieve/stats/empty_join_skips",
        ] { bump(&mut outcomes, key); }
        assert_eq!(Work::read(&outcomes).unwrap(), baseline);
        // A Spine donor already increments decoded_rows: charging the donor's
        // subset counter again would count that same row access twice.
        bump(&mut outcomes, "/stage_spine/stats/local_witness_row_reads");
        bump(&mut outcomes, "/stats/decoded_rows");
        assert_eq!(baseline.savings(&Work::read(&outcomes).unwrap()).0, -1);
        // Removing a lookup is a loss when it adds more pre-decode filtering.
        let mut shifted = report.clone();
        shifted["key_lookup_calls"] = json!(report["key_lookup_calls"].as_u64().unwrap().checked_sub(1).unwrap());
        bump(&mut shifted, "/free_join/entry_probes");
        bump(&mut shifted, "/sieve/stats/update_rows");
        assert_eq!(baseline.savings(&Work::read(&shifted).unwrap()).0, -1);
        for (group, field) in [("/free_join", "entry_probes"), ("/sieve/stats", "update_rows"),
            ("/stage_spine/stats", "completion_boundary_reads"), ("/stage_spine/stats", "cell_output_slot_reads")] {
            let mut missing = report.clone();
            missing.pointer_mut(group).unwrap().as_object_mut().unwrap().remove(field);
            assert!(Work::read(&missing).unwrap_err().contains(&format!("{}/{field}", &group[1..])));
        }
        let mut missing = report;
        missing["stats"]["register_prefix"].as_object_mut().unwrap().remove("row_reads");
        assert!(Work::read(&missing).unwrap_err().contains("stats/register_prefix/row_reads"));
    }
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
    #[test]
    fn parallel_guard_dispatch_cannot_hide_preparation_from_bake_credit() {
        use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
        let source = r#"
(datatype E (N i64) (F E i64))
(F (N 0) 0) (F (N 1) 0) (F (N 0) 1) (F (N 1) 1)
(F (N 0) 2) (F (N 1) 2) (F (N 0) 3) (F (N 1) 3)
(ruleset merge)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(run-schedule (run merge))
"#;
        let core = eggfuse_bake::device_frontend::core("guard-credit", source).unwrap();
        let compiled = compiler::compile(core, &Default::default()).unwrap();
        let run = |parallel, batch, overlap| {
            let mut graph = Graph::new_with_local_congruence(Program::parse(compiled.clone()).unwrap()).unwrap();
            if parallel { graph.use_parallel_port_guards(2, 1).unwrap(); }
            if batch { graph.use_completion_read_batches(16).unwrap(); }
            if overlap { graph.use_overlapped_completion().unwrap(); }
            let mut executor = Executor::new(graph, false);
            executor.execute().unwrap();
            (executor.graph.export().unwrap(), executor.report())
        };
        let (before_state, before) = run(false, false, false);
        let (after_state, mut after) = run(true, false, false);
        assert_eq!(before_state, after_state);
        let serial = Work::read(&before).unwrap();
        let route_work = "stable_ports/local_conditions/stats/boundary_indexed_steps";
        assert!(serial.0[route_work] > 0);
        let mut missing_routes = before.clone();
        missing_routes["stable_ports"]["local_conditions"]["stats"].as_object_mut().unwrap().remove("boundary_indexed_steps");
        assert!(Work::read(&missing_routes).unwrap_err().contains("missing local condition work boundary_indexed_steps"));
        let parallel = Work::read(&after).unwrap();
        assert!(parallel.0["stable_ports/parallel_guards/stats/rounds"] > 0);
        assert!(parallel.0["stable_ports/parallel_guards/stats/prepared_candidates"] > 0);
        assert!(serial.savings(&parallel).0 < 0);
        after["stable_ports"]["parallel_guards"]["stats"].as_object_mut().unwrap().remove("prepared_candidates");
        assert!(Work::read(&after).unwrap_err().contains("missing parallel guard work prepared_candidates"));
        let (batch_state, mut batch_report) = run(true, true, false);
        assert_eq!(before_state, batch_state);
        let batch = Work::read(&batch_report).unwrap();
        assert!(batch.0["stable_ports/completion_batches/stats/dispatches"] > 0);
        assert!(serial.savings(&batch).0 < 0);
        batch_report["stable_ports"]["completion_batches"]["stats"].as_object_mut().unwrap().remove("read_set_comparisons");
        assert!(Work::read(&batch_report).unwrap_err().contains("missing completion batch work read_set_comparisons"));
        let (overlap_state, mut overlap_report) = run(true, true, true);
        assert_eq!(before_state, overlap_state);
        let overlap = Work::read(&overlap_report).unwrap();
        assert!(overlap.0["stable_ports/completion_batches/overlap/task_spawns"] > 0);
        assert!(overlap.0["stable_ports/stats/root_parent_probes"] > 0);
        assert!(overlap.0["cell_ownership/stats/signal_parent_probes"] > 0);
        assert_eq!(overlap.0["stable_ports/completion_batches/overlap/channel_builds"], 0);
        assert!(overlap.0["stable_ports/completion_batches/overlap/slot_collection_reads"] > 0);
        assert!(overlap.0["scoped_completion/queue_overlay/shadow_probes"] > 0);
        assert!(serial.savings(&overlap).0 < 0);
        let mut missing_queue = overlap_report.clone();
        missing_queue["scoped_completion"]["queue_overlay"]["stats"].as_object_mut().unwrap().remove("base_successor_steps");
        assert!(Work::read(&missing_queue).unwrap_err().contains("missing queue overlay work base_successor_steps"));
        overlap_report["stable_ports"]["completion_batches"]["overlap"]["stats"]["overlay"].as_object_mut().unwrap().remove("copied_units");
        assert!(Work::read(&overlap_report).unwrap_err().contains("missing overlay work copied_units"));
        after["stable_ports"]["parallel_guards"]["stats"]["prepared_candidates"] = 0.into();
        after["stable_ports"]["stats"].as_object_mut().unwrap().remove("root_parent_probes");
        assert!(Work::read(&after).unwrap_err().contains("missing stable-port work root_parent_probes"));
        let mut missing_delivery = overlap_report;
        missing_delivery["stable_ports"]["completion_batches"]["overlap"]["stats"].as_object_mut().unwrap().remove("slot_publications");
        assert!(Work::read(&missing_delivery).unwrap_err().contains("missing overlap work slot_publications"));
    }
    #[test]
    fn frontier_independence_cannot_hide_its_membership_probes() {
        use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
        let source = r#"
(datatype E (N i64) (F E))
(F (N 0)) (F (N 1)) (F (N 2)) (F (N 3))
(ruleset a) (ruleset b)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (N 2)) (= y (N 3))) ((union x y)) :ruleset b)
(run-schedule (seq (run a) (run b)))
"#;
        let core = eggfuse_bake::device_frontend::core("frontier-credit", source).unwrap();
        let program = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
        let mut executor = Executor::new(Graph::new_with_scoped_completion(program).unwrap(), false);
        executor.use_pure_epochs().unwrap();
        executor.execute().unwrap();
        let mut report = executor.report();
        let work = Work::read(&report).unwrap();
        if report["scoped_executor"]["global_observer"] == false {
            assert!(work.0["port_completion/stats/pure_epoch_frontier_checks"] > 0);
        }
        report["port_completion"]["stats"].as_object_mut().unwrap().remove("pure_epoch_frontier_checks");
        assert!(Work::read(&report).unwrap_err().contains("missing port completion work pure_epoch_frontier_checks"));
    }
}
