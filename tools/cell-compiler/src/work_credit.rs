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
                "root_handles_created", "contexts_created", "capture_reads",
                "origin_key_slots", "origin_map_writes", "origin_map_probes",
                "history_capture_reads", "history_slots_written", "history_allocations",
                "ripsat_plan_probes", "ripsat_layout_checks", "ripsat_witness_checks", "ripsat_projection_checks", "ripsat_boundary_reads",
                "history_inherited_reads", "history_inheritance_marks", "history_heap_frames", "effect_slots_initialized",
                "query_receipt_attempts", "context_reads", "port_cache_fills", "guards", "cell_query_result_writes",
                "scoped_anchor_checks", "scoped_direct_checks", "scoped_receipt_checks",
                "local_witness_contexts", "local_witness_route_probes", "local_witness_route_steps", "local_witness_key_fields",
                "local_witness_route_comparisons", "local_witness_read_index_probes",
                "local_witness_receipt_probes", "local_witness_receipt_steps", "local_witness_history_borrows",
                "direct_publication_hash_probes", "fragment_packets", "fragment_receipt_spills",
                // Charge every Cell output, including single/mixed Cells, and
                // the boundary work that a compiled output can replace.
                // Fragment coverage/check counters are subsets, not extra work.
                "cell_output_slot_reads", "effect_output_copies", "receipt_attempts",
                // Each delivered output still resolves its receipt before
                // Entry selection; skipping visibility checks does not erase it.
                "cell_output_deliveries",
                "completion_boundary_records", "completion_boundary_reads", "completion_order_checks", "completion_cell_visits",
            ]),
            ("entry_schedule/stats", &[
                // Seed construction is a distinct intermediate handoff before
                // worker/task headers. This existing counter covers old reports
                // too; direct Cell Entries do not manufacture a Seed to skip it.
                "consumer_seed_deliveries",
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
        // Suspending is ownership work, not a saved source effect. Promotions
        // already enter cells_created; private/public splits and invalidations
        // are outcomes. Each lifecycle hold also pays for its later release.
        for field in ["rhs_context_suspends", "rhs_context_resumes", "rhs_suspend_holds", "rhs_suspend_releases"] {
            let value = match report["cell_execution"]["suspension"].get("schema") {
                None => 0,
                Some(J::String(v)) if v == "owned-rhs-context/v1" => report["stats"][field].as_u64()
                    .ok_or_else(|| format!("missing Cell suspension work {field}"))?,
                _ => return Err("unknown Cell suspension accounting".into()),
            };
            work.insert(format!("stats/{field}"), value);
        }
        // Constructor preparation replaces a source lookup only after checked
        // evidence. All speculative lookups already enter key_lookup_calls;
        // any required decoding remains in fact_decode_calls. Cached-row
        // validation pays its check and field counters. Outcomes earn no credit.
        let constructor_preparation = match report["cell_execution"]["constructor_preparation"].get("schema") {
            None => 0,
            Some(J::String(v)) if v == "cell-constructor-preparation/v1" => 1,
            Some(J::String(v)) if v == "cell-constructor-preparation/v2" => 2,
            Some(J::String(v)) if v == "cell-constructor-preparation/v3" => 3,
            Some(J::String(v)) if v == "cell-constructor-preparation/v4" => 4,
            Some(J::String(v)) if v == "cell-constructor-preparation/v5" => 5,
            Some(J::String(v)) if v == "cell-constructor-preparation/v6" => 6,
            _ => return Err("unknown Cell constructor preparation accounting".into()),
        };
        for (group, fields) in [
            ("stats", &["constructor_prepared_checks", "constructor_prepared_fields"][..]),
            ("query_workers/stats/execution/constructor", &["attempts", "key_fields", "key_spills", "result_writes"]),
        ] {
            for field in fields {
                let key = format!("{group}/{field}");
                let enabled = constructor_preparation > 0 && (group == "stats" || report["query_workers"]["enabled"] == true);
                let value = if enabled {
                    report.pointer(&format!("/{key}")).and_then(J::as_u64)
                        .ok_or_else(||format!("missing constructor preparation work {key}"))?
                } else { 0 };
                work.insert(key, value);
            }
        }
        // Charge certificate and lifetime probes, and the new result-only read.
        // Sealed hits and omitted key fields are outcomes, not extra credit.
        for field in ["constructor_prepared_certificates", "constructor_prepared_liveness_checks", "constructor_prepared_result_reads"] {
            let key = format!("stats/{field}");
            let value = if constructor_preparation >= 2 {
                report["stats"][field].as_u64().ok_or_else(||format!("missing constructor preparation work {key}"))?
            } else { 0 };
            work.insert(key, value);
        }
        // Admission borrows a compiled handoff and its existing result slot.
        // Skipped probes earn no separate credit: they disappear from the
        // ordinary lookup, preparation, dispatch and storage counters.
        for field in ["preparation_handoff_rule_checks", "preparation_handoff_history_checks",
            "preparation_handoff_checks", "preparation_handoff_operations",
            "preparation_handoff_reads", "preparation_handoff_inherited_reads"] {
            let key = format!("stage_spine/stats/{field}");
            let value = if constructor_preparation >= 3 {
                report.pointer(&format!("/{key}")).and_then(J::as_u64)
                    .ok_or_else(||format!("missing constructor preparation work {key}"))?
            } else { 0 };
            work.insert(key, value);
        }
        for (group, fields) in [
            ("stats", &["constructor_prefix_checks", "constructor_prefix_table_checks",
                "constructor_prefix_discarded_slots", "constructor_prefix_receipt_writes"][..]),
            ("query_workers/stats/execution/constructor", &["prefix_slot_writes", "prefix_slot_growths",
                "prefix_witness_growths"]),
        ] {
            for field in fields {
                let key = format!("{group}/{field}");
                let enabled = constructor_preparation >= 4 && (group == "stats" || report["query_workers"]["enabled"] == true);
                let value = if enabled {
                    report.pointer(&format!("/{key}")).and_then(J::as_u64)
                        .ok_or_else(||format!("missing constructor preparation work {key}"))?
                } else { 0 };
                work.insert(key,value);
            }
        }
        // Union requests are already charged above. Charge only the new direct
        // operand acquisition here, including actual result-row access; neither
        // covered Cells nor queued unions earn a second saved-operation credit.
        for (group, fields) in [
            ("query_workers/stats/execution/constructor", &["prefix_layout_checks",
                "prefix_result_initializations", "prefix_progress_writes"][..]),
            ("stage_spine/stats", &["prepared_effect_buffer_moves",
                "prepared_effect_spares_released", "prepared_effect_joint_positions",
                "prepared_effect_joint_reads", "prepared_effect_joint_writes"]),
        ] {
            for field in fields {
                let key = format!("{group}/{field}");
                let enabled = constructor_preparation >= 5 && (group != "query_workers/stats/execution/constructor"
                    || report["query_workers"]["enabled"] == true);
                let value = if enabled {
                    report.pointer(&format!("/{key}")).and_then(J::as_u64)
                        .ok_or_else(||format!("missing constructor preparation work {key}"))?
                } else { 0 };
                work.insert(key,value);
            }
        }
        let key = "query_workers/stats/execution/constructor/prefix_scalar_checks";
        let value = if constructor_preparation >= 6 && report["query_workers"]["enabled"] == true {
            report.pointer(&format!("/{key}")).and_then(J::as_u64)
                .ok_or_else(||format!("missing constructor preparation work {key}"))?
        } else { 0 };
        work.insert(key.into(),value);
        let local_births=match report["cell_execution"].get("local_construction") {
            None=>0,
            Some(v) if v["schema"]=="cell-local-births/v1"=>1,
            Some(v) if v["schema"]=="cell-local-births/v2"=>2,
            Some(v) if v["schema"]=="cell-local-births/v3"=>3,
            _=>return Err("unknown Cell local construction accounting".into()),
        };
        for field in ["plan_checks","resume_checks","window_checks","attempts","anchor_checks","source_operand_reads","operand_reads",
            "candidate_ranges","candidate_probes","field_checks","identity_checks","hashes","row_fields",
            "pending_growths","value_writes","slot_growths","worker_batches"] {
            let key=format!("cell_execution/runtime/stats/births/{field}");
            let value=if local_births>0 {
                report.pointer(&format!("/{key}")).and_then(J::as_u64)
                    .ok_or_else(||format!("missing local construction work {key}"))?
            } else {0};
            work.insert(key,value);
        }
        for field in ["prefix_reads","prefix_handles","prefix_growths","slot_seals","slot_leases","slot_reattachments","root_snapshots","root_writes","root_growths","root_merges","plan_handles","captured_reads","captured_writes"] {
            let key=format!("cell_execution/runtime/stats/births/{field}");
            let value=if local_births>=2 {
                report.pointer(&format!("/{key}")).and_then(J::as_u64)
                    .ok_or_else(||format!("missing local construction work {key}"))?
            } else {0};
            work.insert(key,value);
        }
        for field in ["shared_growths","result_reads","evaluations","bloom_checks","bloom_writes","result_handles","frame_handles","dependency_proofs","key_screens","directory_checks"] {
            let key=format!("cell_execution/runtime/stats/births/{field}");
            let value=if local_births>=3 {
                report.pointer(&format!("/{key}")).and_then(J::as_u64)
                    .ok_or_else(||format!("missing local construction work {key}"))?
            } else {0};
            work.insert(key,value);
        }
        let scheduler=match report["cell_execution"].get("scheduler") {
            None=>false,
            Some(v) if v["schema"]=="cell-ready-batches/v1" || v["schema"]=="cell-ready-batches/v2"=>true,
            _=>return Err("unknown Cell scheduler accounting".into()),
        };
        for key in ["stats/rhs_pending_probes", "stats/rhs_pending_key_spills", "cell_execution/runtime/stats/scheduler/rule_groups",
            "cell_execution/runtime/stats/scheduler/instances", "cell_execution/runtime/stats/scheduler/jobs",
            "cell_execution/runtime/stats/scheduler/batches", "cell_execution/runtime/stats/scheduler/queue_growths",
            "cell_execution/runtime/stats/scheduler/operand_reads", "cell_execution/runtime/stats/scheduler/revalidations"] {
            let value=if scheduler {report.pointer(&format!("/{key}")).and_then(J::as_u64)
                .ok_or_else(||format!("missing Cell scheduler work {key}"))?} else {0};
            work.insert(key.into(),value);
        }
        let budget="cell_execution/runtime/stats/scheduler/budget_checks";
        work.insert(budget.into(),if report["cell_execution"]["scheduler"]["schema"]=="cell-ready-batches/v2" {
            report.pointer(&format!("/{budget}")).and_then(J::as_u64)
                .ok_or_else(||format!("missing Cell scheduler work {budget}"))?
        } else {0});
        for field in ["ripsat_union_input_reads", "ripsat_union_result_reads"] {
            let value = match report["stage_spine"].get("union_completion") {
                None => 0,
                Some(J::String(v)) if v == "cell-union-ports/v1" =>
                    report["stage_spine"]["stats"][field].as_u64()
                        .ok_or_else(||format!("missing Cell union work {field}"))?,
                _ => return Err("unknown Cell union completion".into()),
            };
            work.insert(format!("stage_spine/stats/{field}"),value);
        }
        // Sealing uses the existing Run forwarding map; every visited slot and
        // actual update is new work. A repaired receipt itself earns no credit.
        for field in ["history_seal_checks", "history_seal_reads", "history_seal_writes"] {
            let value = match report["stage_spine"].get("history_sealing") {
                None => 0,
                Some(J::String(v)) if v == "unique-cell-results/v1" =>
                    report["stage_spine"]["stats"][field].as_u64()
                        .ok_or_else(||format!("missing Cell history sealing work {field}"))?,
                _ => return Err("unknown Cell history sealing".into()),
            };
            work.insert(format!("stage_spine/stats/{field}"),value);
        }
        // Member proofs may fail even when a sibling was absorbed. Charge
        // dispatch, eligibility and every actual output probe; coverage is not
        // an independent saving over the omitted bindings/RHS/publications.
        let absorption = &report["neighbor_context"]["absorption"];
        for field in ["mixed_candidates", "mixed_checks", "mixed_output_probes"] {
            let value = match absorption.get("row_completion") {
                None => 0,
                Some(J::String(v)) if v == "cell-min-row/v1" => absorption["stats"][field].as_u64()
                    .ok_or_else(||format!("missing Cell member completion work {field}"))?,
                _ => return Err("unknown Cell member completion".into()),
            };
            work.insert(format!("neighbor_context/absorption/stats/{field}"), value);
        }
        // Candidate-shape dispatch is paid on every present single-column
        // bucket, including shared domains. Inline deliveries earn no credit
        // separate from the existing materialization/allocation observations.
        let shapes = match report["query_domain_transport"].get("schema") {
            None => 0,
            Some(J::String(v)) if v == "cell-witness-domain/v1" => report["free_join"]["projection_shape_checks"].as_u64()
                .ok_or("missing Cell domain shape work")?,
            _ => return Err("unknown Cell domain transport".into()),
        };
        work.insert("free_join/projection_shape_checks".into(), shapes);
        // A field test is new work even when it prevents a whole summary update.
        // Historical reports have no such test; missing new counters are errors.
        let column_checks = match report["sieve"].get("column_influence") {
            None => 0,
            Some(J::String(version)) if version == "cell-fields/v1" || version == "cell-fields/v2" =>
                report["sieve"]["stats"]["column_checks"].as_u64()
                    .ok_or("missing Sieve column_checks")?,
            _ => return Err("unknown Sieve column influence".into()),
        };
        work.insert("sieve/stats/column_checks".into(), column_checks);
        let dispatches = if report["sieve"]["column_influence"] == "cell-fields/v2" {
            report["sieve"]["stats"]["publication_dispatches"].as_u64()
                .ok_or("missing Sieve publication_dispatches")?
        } else { 0 };
        work.insert("sieve/stats/publication_dispatches".into(), dispatches);
        // Charge both attempted plan preparation and every support probe,
        // including unavailable columns. Rejections are outcomes; their saved
        // queries/dispatch are already absent from the original counters.
        for field in ["point_support_plans", "point_support_checks"] {
            let value = match report.get("point_support_accounting") {
                None => 0,
                Some(J::String(v)) if v == "current-column/v1" => report["free_join"][field].as_u64()
                    .ok_or_else(|| format!("missing point support work {field}"))?,
                _ => return Err("unknown point support accounting".into()),
            };
            work.insert(format!("free_join/{field}"), value);
        }
        // Before span sealing each captured anchor and retained receipt had an
        // individual registration. New reports count the remaining operations
        // explicitly: output coverage is no longer proportional to this work.
        let sealed = match report["stage_spine"].get("output_registration") {
            None => false,
            Some(J::String(version)) if version == "cell-span/v1" || version == "owned-cell-outputs/v2" => true,
            _ => return Err("unknown Cell output registration".into()),
        };
        for (field, old) in [("output_registrations", "captured_anchors"),
            ("cell_output_registrations", "cell_output_receipts")] {
            let source = if sealed { field } else { old };
            let value = report["stage_spine"]["stats"][source].as_u64()
                .ok_or_else(|| format!("missing Cell registration work {source}"))?;
            work.insert(format!("stage_spine/stats/{field}"), value);
        }
        for field in ["cell_output_span_seals", "output_span_checks", "output_residual_dispatches"] {
            let value = if sealed { report["stage_spine"]["stats"][field].as_u64()
                .ok_or_else(|| format!("missing Cell registration work {field}"))? } else { 0 };
            work.insert(format!("stage_spine/stats/{field}"), value);
        }
        // Independent result owners pay for the pool and ownership transfers.
        // Reuse/coverage counters overlap these operations; capacity bytes are
        // reported separately rather than adding bytes to an operation score.
        for field in ["effect_buffer_takes", "effect_buffer_returns", "effect_buffer_growths",
            "effect_buffer_pool_growths", "publication_buffer_moves"] {
            let value = if report["stage_spine"]["output_registration"] == "owned-cell-outputs/v2" {
                report["stage_spine"]["stats"][field].as_u64()
                    .ok_or_else(|| format!("missing owned Cell output work {field}"))?
            } else { 0 };
            work.insert(format!("stage_spine/stats/{field}"), value);
        }
        let joint = match report["stage_spine"].get("joint_result_storage") {
            None => false,
            Some(J::String(version)) if version == "cell-results/v1" => true,
            _ => return Err("unknown joint Cell result storage".into()),
        };
        // Shared owners replace the old history heap arrays. Query captures
        // move earlier; they still cost reads and writes. Output availability
        // and retirement are already in cell_output_slot_reads/deliveries;
        // charge the additional lookup through the shared owner separately.
        for field in ["joint_history_checks", "joint_history_frames", "joint_history_query_reads",
            "joint_history_query_writes", "joint_output_reads"] {
            let value = if joint { report["stage_spine"]["stats"][field].as_u64()
                .ok_or_else(|| format!("missing joint Cell result work {field}"))? } else { 0 };
            work.insert(format!("stage_spine/stats/{field}"), value);
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
        for field in ["fixed_read_probes", "fixed_read_fills", "fixed_read_clears",
            "fixed_key_fields", "shared_first_reads"] {
            let value = if report["query_workers"]["first_read_sharing"] == "literal-run/v1" {
                report["query_workers"]["stats"][field].as_u64()
                    .ok_or_else(|| format!("missing shared first read work {field}"))?
            } else { 0 };
            // Physical table reads already enter key_lookup_calls. Hits and
            // rejected Entries are outcomes, not an extra saved-work credit.
            work.insert(format!("query_workers/stats/{field}"), value);
        }
        let cell_tasks = match report["query_workers"].get("organization") {
            None => false, // recorded 13cfd235 Entry-batch host
            Some(J::String(version)) if matches!(version.as_str(), "cell-run/v1" | "cell-run/v2" | "cell-run/v3" | "cell-run/v4" | "cell-run/v5") => true,
            _ => return Err("unknown query worker organization".into()),
        };
        let indexed_tasks = matches!(report["query_workers"]["organization"].as_str(), Some("cell-run/v2" | "cell-run/v3" | "cell-run/v4" | "cell-run/v5"));
        for field in ["cell_task_probes", "cell_task_records", "cell_task_links", "cell_task_emissions",
            "cell_task_clears", "cell_task_growths", "cell_code_reads", "active_template_visits"] {
            let value = if matches!(report["query_workers"]["organization"].as_str(), Some("cell-run/v4" | "cell-run/v5")) {
                report["query_workers"]["stats"][field].as_u64()
                    .ok_or_else(|| format!("missing Cell activation task work {field}"))?
            } else { 0 };
            work.insert(format!("query_workers/stats/{field}"), value);
        }
        for field in ["frame_cache_borrows", "completion_headers", "completion_error_checks"] {
            let value = if matches!(report["query_workers"]["organization"].as_str(), Some("cell-run/v3" | "cell-run/v4" | "cell-run/v5")) {
                report["query_workers"]["stats"][field].as_u64()
                    .ok_or_else(|| format!("missing sparse completion work {field}"))?
            } else { 0 };
            work.insert(format!("query_workers/stats/{field}"), value);
        }
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
            let value = if indexed_tasks {
                report["query_workers"]["stats"][field].as_u64()
                    .ok_or_else(|| format!("missing Cell completion work {field}"))?
            } else { 0 };
            work.insert(format!("query_workers/stats/{field}"), value);
        }
        // v5 borrows matched/deferred instances into the same invocation.
        // Charge actual admission, scratch and preparation, including work on
        // discarded candidates. Matched/deferred operation counts are subsets
        // of stats/execution and must not be charged a second time.
        for (group, fields) in [
            ("matched", &["rule_checks", "admission_instances", "groups", "header_growths",
                "chunks", "histogram_growths"][..]),
            ("stats/execution", &["instances", "operations", "slot_writes", "frame_growths"]),
        ] {
            for field in fields {
                let key = format!("query_workers/{group}/{field}");
                let value = if report["query_workers"]["organization"] == "cell-run/v5" {
                    report.pointer(&format!("/{key}")).and_then(J::as_u64)
                        .ok_or_else(|| format!("missing Cell preparation work {key}"))?
                } else { 0 };
                work.insert(key, value);
            }
        }
        // Domain traversal and exact guards are folded into their existing
        // ownership/stable-port counters below. Only new scratch/metadata work
        // is charged here, once; constructor coverage itself earns no credit.
        for field in ["domain_key_fields", "metadata_reads", "candidate_pushes",
            "candidate_growths", "candidate_sort_comparisons"] {
            let value = if indexed_tasks {
                report["query_workers"]["stats"]["constructors"][field].as_u64()
                    .ok_or_else(|| format!("missing constructor query work {field}"))?
            } else { 0 };
            work.insert(format!("query_workers/stats/constructors/{field}"), value);
        }
        // Canonical reads use the original index/fields, without a new domain.
        // The point lookup is already charged by key_lookup_calls. Expose and
        // charge the candidate/field work once; coverage itself earns no credit.
        // Earlier serial reports did not itemize these operations, so this
        // conservative accounting is not a latency estimate for that baseline.
        for field in ["canonical_candidates", "canonical_field_checks", "canonical_result_reads"] {
            let value = if report["query_workers"]["constructor_access"] == "canonical-or-stable/v1" {
                report["query_workers"]["stats"]["constructors"][field].as_u64()
                    .ok_or_else(|| format!("missing canonical query work {field}"))?
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
        for field in ["ruleset_waits", "eager_waits", "readiness_dependency_checks", "publication_table_checks", "rhs_demand_probes", "rhs_group_checks", "rhs_demand_growths", "rhs_selected_rules", "bound_rhs_attempts", "bound_rhs_rule_checks", "bound_rhs_ops", "bound_rhs_expression_steps", "bound_rhs_input_reads", "bound_rhs_key_reads", "bound_rhs_value_slots", "bound_rhs_scratch_growths", "bound_rhs_overlay_checks"] {
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
    e.use_cell_execution(1).unwrap();
    e.execute().unwrap();
    let mut report = e.report();
    let work = Work::read(&report).unwrap();
    assert_eq!(report["query_workers"]["organization"], "cell-run/v5");
    for key in ["stats/constructor_prepared_checks", "stats/constructor_prepared_fields",
        "stats/constructor_prepared_certificates", "stats/constructor_prepared_liveness_checks", "stats/constructor_prepared_result_reads",
        "stage_spine/stats/preparation_handoff_checks", "stage_spine/stats/preparation_handoff_operations",
        "stage_spine/stats/preparation_handoff_rule_checks", "stage_spine/stats/preparation_handoff_history_checks",
        "stage_spine/stats/preparation_handoff_reads", "stage_spine/stats/preparation_handoff_inherited_reads",
        "stats/constructor_prefix_checks", "stats/constructor_prefix_table_checks",
        "stats/constructor_prefix_discarded_slots", "stats/constructor_prefix_receipt_writes",
        "query_workers/stats/execution/constructor/prefix_slot_writes",
        "query_workers/stats/execution/constructor/prefix_slot_growths",
        "query_workers/stats/execution/constructor/prefix_witness_growths",
        "query_workers/stats/execution/constructor/prefix_layout_checks",
        "query_workers/stats/execution/constructor/prefix_result_initializations",
        "query_workers/stats/execution/constructor/prefix_progress_writes",
        "query_workers/stats/execution/constructor/prefix_scalar_checks",
        "cell_execution/runtime/stats/births/plan_checks",
        "cell_execution/runtime/stats/births/resume_checks",
        "cell_execution/runtime/stats/births/window_checks",
        "cell_execution/runtime/stats/births/attempts",
        "cell_execution/runtime/stats/births/anchor_checks",
        "cell_execution/runtime/stats/births/source_operand_reads",
        "cell_execution/runtime/stats/births/operand_reads",
        "cell_execution/runtime/stats/births/candidate_ranges",
        "cell_execution/runtime/stats/births/candidate_probes",
        "cell_execution/runtime/stats/births/field_checks",
        "cell_execution/runtime/stats/births/identity_checks",
        "cell_execution/runtime/stats/births/hashes",
        "cell_execution/runtime/stats/births/row_fields",
        "cell_execution/runtime/stats/births/pending_growths",
        "cell_execution/runtime/stats/births/value_writes",
        "cell_execution/runtime/stats/births/slot_growths",
        "cell_execution/runtime/stats/births/worker_batches",
        "cell_execution/runtime/stats/births/prefix_reads",
        "cell_execution/runtime/stats/births/prefix_handles",
        "cell_execution/runtime/stats/births/prefix_growths",
        "cell_execution/runtime/stats/births/slot_seals",
        "cell_execution/runtime/stats/births/slot_leases",
        "cell_execution/runtime/stats/births/slot_reattachments",
        "cell_execution/runtime/stats/births/root_snapshots",
        "cell_execution/runtime/stats/births/root_writes",
        "cell_execution/runtime/stats/births/root_growths",
        "cell_execution/runtime/stats/births/root_merges",
        "cell_execution/runtime/stats/births/plan_handles",
        "cell_execution/runtime/stats/births/result_reads",
        "cell_execution/runtime/stats/births/evaluations",
        "cell_execution/runtime/stats/births/bloom_checks",
        "cell_execution/runtime/stats/births/result_handles",

        "stage_spine/stats/prepared_effect_buffer_moves",
        "stage_spine/stats/prepared_effect_spares_released",
        "stage_spine/stats/prepared_effect_joint_positions", "stage_spine/stats/prepared_effect_joint_reads",
        "stage_spine/stats/prepared_effect_joint_writes",
        "query_workers/stats/execution/constructor/attempts", "query_workers/stats/execution/constructor/key_fields",
        "query_workers/stats/execution/constructor/key_spills", "query_workers/stats/execution/constructor/result_writes"] {
        let mut changed = report.clone();
        let value = changed.pointer_mut(&format!("/{key}")).unwrap();
        *value = json!(value.as_u64().unwrap() + 1);
        assert_eq!(work.savings(&Work::read(&changed).unwrap()).0, -1);
        *changed.pointer_mut(&format!("/{key}")).unwrap() = J::Null;
        let category=if key.starts_with("cell_execution/runtime/stats/births/") {
            "local construction work"
        } else {"constructor preparation work"};
        assert!(Work::read(&changed).unwrap_err().contains(category));
    }
    for field in ["rhs_context_suspends", "rhs_context_resumes", "rhs_suspend_holds", "rhs_suspend_releases"] {
        let mut changed = report.clone();
        changed["stats"][field] = json!(report["stats"][field].as_u64().unwrap() + 1);
        assert_eq!(work.savings(&Work::read(&changed).unwrap()).0, -1);
        changed["stats"].as_object_mut().unwrap().remove(field);
        assert!(Work::read(&changed).unwrap_err().contains("suspension work"));
    }
    for key in ["query_workers/matched/rule_checks", "query_workers/matched/header_growths",
        "query_workers/stats/execution/operations", "query_workers/stats/execution/slot_writes"] {
        let mut changed = report.clone();
        let value = changed.pointer_mut(&format!("/{key}")).unwrap();
        *value = json!(value.as_u64().unwrap() + 1);
        assert_eq!(work.savings(&Work::read(&changed).unwrap()).0, -1);
        *changed.pointer_mut(&format!("/{key}")).unwrap() = J::Null;
        assert!(Work::read(&changed).unwrap_err().contains("preparation work"));
    }
    let mut coverage = report.clone();
    coverage["query_workers"]["matched"]["deferred_operations"] = u64::MAX.into();
    coverage["query_workers"]["matched"]["execution"]["operations"] = u64::MAX.into();
    coverage["query_workers"]["stats"]["execution"]["later_operations"] = u64::MAX.into();
    assert_eq!(Work::read(&coverage).unwrap(), work, "subsets do not earn or charge work twice");
    for field in ["local_births", "local_reuses", "committed_rows", "worker_operations", "shared_slots", "result_hits", "duplicate_evaluations", "bloom_skips"] {
        coverage["cell_execution"]["runtime"]["stats"]["births"][field]=u64::MAX.into();
    }
    assert_eq!(Work::read(&coverage).unwrap(),work,"local outcomes do not earn credit twice");
    let mut missing_scheduler=report.clone();
    missing_scheduler["cell_execution"]["runtime"]["stats"]["scheduler"]["jobs"]=J::Null;
    assert!(Work::read(&missing_scheduler).unwrap_err().contains("Cell scheduler work"));
    let mut unknown_scheduler=report.clone();
    unknown_scheduler["cell_execution"]["scheduler"]["schema"]="unknown".into();
    assert!(Work::read(&unknown_scheduler).unwrap_err().contains("unknown Cell scheduler"));
    coverage["cell_execution"]["local_construction"]["schema"]="unknown".into();
    assert!(Work::read(&coverage).unwrap_err().contains("unknown Cell local construction"));
    let mut domains = report.clone();
    domains["free_join"]["projection_shape_checks"] = 9.into();
    domains["free_join"]["inline_domain_deliveries"] = u64::MAX.into();
    assert_eq!(Work::read(&domains).unwrap().0["free_join/projection_shape_checks"], 9);
    domains["free_join"].as_object_mut().unwrap().remove("projection_shape_checks");
    assert!(Work::read(&domains).unwrap_err().contains("domain shape"));
    domains.as_object_mut().unwrap().remove("query_domain_transport");
    assert_eq!(Work::read(&domains).unwrap().0["free_join/projection_shape_checks"], 0);
    domains["query_domain_transport"] = serde_json::json!({"schema":"unknown"});
    assert!(Work::read(&domains).is_err());
    #[cfg(feature = "cell-absorption")]
    {
        let mut member_report = report.clone();
        member_report["neighbor_context"]["absorption"]["stats"]["mixed_output_probes"] = 9.into();
        assert_eq!(Work::read(&member_report).unwrap().0["neighbor_context/absorption/stats/mixed_output_probes"], 9);
        member_report["neighbor_context"]["absorption"]["stats"]["mixed_absorbed"] = u64::MAX.into();
        assert_eq!(Work::read(&member_report).unwrap().0["neighbor_context/absorption/stats/mixed_output_probes"], 9);
        member_report["neighbor_context"]["absorption"]["stats"].as_object_mut().unwrap().remove("mixed_checks");
        assert!(Work::read(&member_report).unwrap_err().contains("missing Cell member completion"));
        member_report["neighbor_context"]["absorption"].as_object_mut().unwrap().remove("row_completion");
        assert_eq!(Work::read(&member_report).unwrap().0["neighbor_context/absorption/stats/mixed_output_probes"], 0);
        member_report["neighbor_context"]["absorption"]["row_completion"] = "unknown".into();
        assert!(Work::read(&member_report).is_err());
    }
    let mut sealed_report = report.clone();
    sealed_report["stage_spine"]["stats"]["history_seal_reads"] = 7.into();
    assert_eq!(Work::read(&sealed_report).unwrap().0["stage_spine/stats/history_seal_reads"], 7);
    sealed_report["stage_spine"]["stats"].as_object_mut().unwrap().remove("history_seal_writes");
    assert!(Work::read(&sealed_report).unwrap_err().contains("missing Cell history sealing"));
    sealed_report["stage_spine"].as_object_mut().unwrap().remove("history_sealing");
    assert_eq!(Work::read(&sealed_report).unwrap().0["stage_spine/stats/history_seal_reads"], 0);
    sealed_report["stage_spine"]["history_sealing"] = "unknown".into();
    assert!(Work::read(&sealed_report).is_err());
    let mut union_report=report.clone();
    union_report["stage_spine"]["stats"]["ripsat_union_cells"]=u64::MAX.into();
    assert_eq!(Work::read(&union_report).unwrap(),work,"coverage earns no credit");
    union_report["stage_spine"]["stats"]["ripsat_union_result_reads"]=5.into();
    assert_eq!(Work::read(&union_report).unwrap().0["stage_spine/stats/ripsat_union_result_reads"],5);
    union_report["stage_spine"]["stats"].as_object_mut().unwrap().remove("ripsat_union_input_reads");
    assert!(Work::read(&union_report).unwrap_err().contains("missing Cell union work"));
    union_report["stage_spine"].as_object_mut().unwrap().remove("union_completion");
    assert_eq!(Work::read(&union_report).unwrap().0["stage_spine/stats/ripsat_union_result_reads"],0);
    union_report["stage_spine"]["union_completion"]="unknown".into();
    assert!(Work::read(&union_report).is_err());
    assert!(work.0["query_workers/stats/frame_allocations"] > 0);
    assert!(work.0["query_workers/stats/chunks"] > 0);
    report["query_workers"]["stats"]["answers"] = u64::MAX.into();
    assert_eq!(Work::read(&report).unwrap().0, work.0);
    report["query_workers"]["stats"]["fixed_read_hits"] = u64::MAX.into();
    report["query_workers"]["stats"]["fixed_rejected_entries"] = u64::MAX.into();
    assert_eq!(Work::read(&report).unwrap().0, work.0);
    let mut missing = report.clone();
    missing["query_workers"]["stats"].as_object_mut().unwrap().remove("fixed_read_probes");
    assert!(Work::read(&missing).is_err());
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
            "/stage_spine/stats/output_registrations", "/stage_spine/stats/cell_output_registrations",
            "/stage_spine/stats/cell_output_span_seals", "/stage_spine/stats/cell_output_slot_reads",
            "/stage_spine/stats/output_span_checks", "/stage_spine/stats/output_residual_dispatches",
            "/stage_spine/stats/effect_buffer_takes", "/stage_spine/stats/effect_buffer_returns",
            "/stage_spine/stats/effect_buffer_growths", "/stage_spine/stats/effect_buffer_pool_growths",
            "/stage_spine/stats/publication_buffer_moves",
            "/stage_spine/stats/joint_history_checks", "/stage_spine/stats/joint_history_frames",
            "/stage_spine/stats/joint_history_query_reads", "/stage_spine/stats/joint_history_query_writes",
            "/stage_spine/stats/joint_output_reads", "/stage_spine/stats/effect_slots_initialized",
            "/stage_spine/stats/effect_output_copies", "/stage_spine/stats/receipt_attempts",
            "/stage_spine/stats/cell_output_deliveries",
            "/stage_spine/stats/completion_boundary_records", "/stage_spine/stats/completion_boundary_reads",
            "/stage_spine/stats/completion_order_checks", "/stage_spine/stats/completion_cell_visits",
            "/entry_schedule/stats/publication_pending_pushes", "/entry_schedule/stats/fragment_pending_writes",
            "/entry_schedule/stats/fragment_pending_reads",
            "/free_join/point_support_plans", "/free_join/point_support_checks",
            "/free_join/entry_rows", "/free_join/entry_probes", "/free_join/entry_cache_hits",
            "/free_join/entry_bucket_rows_examined", "/free_join/entry_bucket_rows_materialized",
            "/free_join/cover_rows", "/free_join/key_groups", "/free_join/probes",
            "/free_join/bucket_rows_examined", "/free_join/bucket_rows_materialized",
            "/free_join/reverse_keys", "/free_join/reverse_refs", "/free_join/reverse_epoch_bins", "/free_join/disjoint_key_reads",
            "/sieve/stats/rule_uses", "/sieve/stats/build_rows", "/sieve/stats/update_rows",
            "/sieve/stats/dependency_rows", "/sieve/stats/probes",
            "/sieve/stats/column_checks",
            "/sieve/stats/publication_dispatches",
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
            "/stage_spine/stats/captured_anchors", "/stage_spine/stats/cell_output_receipts",
            "/stage_spine/stats/cell_output_sealed_receipts",
            "/stage_spine/stats/owned_effect_frames", "/stage_spine/stats/effect_buffer_reuses",
            "/stage_spine/stats/effect_buffer_growth_bytes", "/stage_spine/stats/effect_buffer_pool_growth_bytes",
            "/stage_spine/stats/history_shared_slots", "/stage_spine/stats/joint_output_mask_checks",
            "/stage_spine/stats/joint_output_mask_writes",
            "/entry_schedule/stats/fragment_slot_replacements", "/entry_schedule/stats/publication_pending_reuses",
            "/free_join/point_support_rejected", "/free_join/point_support_unavailable",
            "/free_join/membership_only", "/free_join/shared_column_reads", "/free_join/entry_rejections",
            "/free_join/disjoint_rule_skips", "/sieve/stats/reused_summaries", "/sieve/stats/rejected",
            "/sieve/stats/empty_join_skips",
            "/sieve/stats/unchanged_column_rows",
            "/sieve/stats/inactive_publications",
        ] { bump(&mut outcomes, key); }
        assert_eq!(Work::read(&outcomes).unwrap(), baseline);
        let mut legacy_columns = report.clone();
        legacy_columns["sieve"].as_object_mut().unwrap().remove("column_influence");
        assert_eq!(Work::read(&legacy_columns).unwrap().0["sieve/stats/column_checks"], 0);
        assert_eq!(Work::read(&legacy_columns).unwrap().0["sieve/stats/publication_dispatches"], 0);
        let mut v1 = report.clone();
        v1["sieve"]["column_influence"] = "cell-fields/v1".into();
        v1["sieve"]["stats"].as_object_mut().unwrap().remove("publication_dispatches");
        assert_eq!(Work::read(&v1).unwrap().0["sieve/stats/publication_dispatches"], 0);
        v1["sieve"]["column_influence"] = "cell-fields/v2".into();
        assert!(Work::read(&v1).unwrap_err().contains("publication_dispatches"));
        let mut missing_columns = report.clone();
        missing_columns["sieve"]["stats"].as_object_mut().unwrap().remove("column_checks");
        assert!(Work::read(&missing_columns).unwrap_err().contains("column_checks"));
        missing_columns["sieve"]["column_influence"] = "unknown".into();
        assert!(Work::read(&missing_columns).unwrap_err().contains("unknown Sieve"));
        // Historical reports used one registration per captured output. Keep
        // those costs, while rejecting new reports missing their actual work.
        let mut legacy = report.clone();
        legacy["stage_spine"].as_object_mut().unwrap().remove("output_registration");
        let legacy_work = Work::read(&legacy).unwrap();
        assert_eq!(legacy_work.0["stage_spine/stats/output_registrations"], report["stage_spine"]["stats"]["captured_anchors"].as_u64().unwrap());
        assert_eq!(legacy_work.0["stage_spine/stats/cell_output_span_seals"], 0);
        assert_eq!(legacy_work.0["stage_spine/stats/effect_buffer_takes"], 0);
        let mut old_spans = report.clone();
        old_spans["stage_spine"]["output_registration"] = "cell-span/v1".into();
        assert_eq!(Work::read(&old_spans).unwrap().0["stage_spine/stats/effect_buffer_takes"], 0);
        for field in ["effect_buffer_takes", "effect_buffer_returns", "effect_buffer_growths",
            "effect_buffer_pool_growths", "publication_buffer_moves"] {
            let mut missing = report.clone();
            missing["stage_spine"]["stats"].as_object_mut().unwrap().remove(field);
            assert!(Work::read(&missing).unwrap_err().contains(field));
        }
        legacy["stage_spine"].as_object_mut().unwrap().remove("joint_result_storage");
        assert_eq!(Work::read(&legacy).unwrap().0["stage_spine/stats/joint_history_frames"], 0);
        for field in ["joint_history_checks", "joint_history_frames", "joint_history_query_reads",
            "joint_history_query_writes", "joint_output_reads"] {
            let mut missing = report.clone();
            missing["stage_spine"]["stats"].as_object_mut().unwrap().remove(field);
            assert!(Work::read(&missing).unwrap_err().contains(field));
        }
        for field in ["output_registrations", "cell_output_registrations", "cell_output_span_seals", "output_span_checks", "output_residual_dispatches"] {
            let mut missing = report.clone();
            missing["stage_spine"]["stats"].as_object_mut().unwrap().remove(field);
            assert!(Work::read(&missing).unwrap_err().contains(field));
        }
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
