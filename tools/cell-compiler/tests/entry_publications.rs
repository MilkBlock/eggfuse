#![cfg(feature = "sparse-cells")]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use std::collections::BTreeSet;

fn compare(source: &str) -> (Executor, Executor) {
    compare_mode(source, true)
}
fn compare_mode(source: &str, audit: bool) -> (Executor, Executor) {
    let core = eggfuse_bake::device_frontend::core("entry-publications", source).unwrap();
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut old = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), audit);
    let mut nodes = Executor::new(Graph::new_with_repair_ports(p).unwrap(), audit);
    nodes.use_entry_publications().unwrap();
    #[cfg(feature = "iterative-bake")]
    {
        let execute = |runtime: &mut Executor| {
            use eggfuse_cell_runtime::transfer_audit as audit;
            audit::set_active(true);
            audit::enable_write_audit();
            runtime.execute().unwrap();
            audit::set_active(false);
            (audit::take_digests(), audit::take_write_digests(), audit::take_resume_digests())
        };
        // Equal final facts alone cannot identify which producer continuation
        // won. Compare the ordered RHS, mutation and resume-root digests too.
        assert_eq!(execute(&mut old), execute(&mut nodes));
    }
    #[cfg(not(feature = "iterative-bake"))]
    {
        old.execute().unwrap();
        nodes.execute().unwrap();
    }
    assert_eq!(old.snapshots, nodes.snapshots);
    assert_eq!(old.binding_audit, nodes.binding_audit);
    assert_eq!(old.graph.export().unwrap(), nodes.graph.export().unwrap());
    assert_eq!(old.steps.len(), nodes.steps.len());
    for (a, b) in old.steps.iter().zip(&nodes.steps) {
        for k in ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed"] {
            assert_eq!(a[k], b[k], "{k}");
        }
    }
    for k in ["resumed_steps", "anchor_publications", "bindings"] {
        assert_eq!(old.report()["stage_spine"]["stats"][k], nodes.report()["stage_spine"]["stats"][k], "{k}");
    }
    assert_eq!(old.report()["stage_spine"]["entry_references"], nodes.report()["stage_spine"]["entry_references"]);
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, source).unwrap();
    (old, nodes)
}

#[test]
fn shared_node_owns_last_publication_across_union_visibility_and_dormant_runs() {
    let (old, nodes) = compare(r#"
(datatype E (N i64) (Start E) (Gateway E) (Out E))
(ruleset make) (ruleset read) (ruleset merge) (ruleset hide) (ruleset remove) (ruleset again)
(rule ((Start x)) ((Gateway x)) :ruleset make)
(rule ((= g (Gateway x))) ((Out g)) :ruleset read)
(rule ((= a (N 1)) (= b (N 2))) ((union a b)) :ruleset merge)
(rule ((Gateway x)) ((subsume (Gateway x))) :ruleset hide)
(rule ((Start x)) ((delete (Gateway x))) :ruleset remove)
(rule ((Start x)) ((Gateway x)) :ruleset again)
(Start (N 1)) (Start (N 2))
(run-schedule (seq (run make) (run merge) (run read) (run hide) (run read) (run remove) (run again) (run read)))
"#);
    let a = old.report();
    let b = nodes.report();
    assert!(b["entry_schedule"]["stats"]["entry_publication_writes"].as_u64().unwrap() > 0);
    assert!(b["entry_schedule"]["stats"]["entry_publications_retired"].as_u64().unwrap() > 0);
    assert!(b["stage_spine"]["stats"]["legacy_entry_writes"].as_u64().unwrap()
        < a["stage_spine"]["stats"]["legacy_entry_writes"].as_u64().unwrap());
    assert!(b["stage_spine"]["stats"]["legacy_cursor_probes"].as_u64().unwrap()
        < a["stage_spine"]["stats"]["legacy_cursor_probes"].as_u64().unwrap());
}

#[test]
fn filtered_entries_and_mutable_function_results_keep_exact_matching() {
    compare(r#"
(datatype E (N i64) (Start E) (Pair E E) (Out E))
(function value (E) i64 :merge new)
(ruleset make) (ruleset update) (ruleset read)
(rule ((Start x)) ((Pair x x) (set (value x) 1)) :ruleset make)
(rule ((Start x)) ((set (value x) 2)) :ruleset update)
(rule ((Pair x x) (= n (value x)) (= n 2)) ((Out x)) :ruleset read)
(rule ((Pair x y) (= y (N 1))) ((Out y)) :ruleset read)
(Start (N 1)) (Start (N 2))
(run-schedule (seq (run make) (run read) (run update) (run read)))
"#);
}

#[test]
fn fragment_receipts_use_entry_slots_after_union_and_duplicate_publications() {
    let source = r#"
(datatype E (N i64) (Start E E) (F E) (Gateway E) (Out E))
(ruleset make) (ruleset consume)
(rule ((Start x y)) ((F x) (F y) (Gateway x) (Gateway y) (union x y)) :ruleset make)
(rule ((Start x y)) ((Gateway x)) :ruleset make)
(rule ((Gateway x) (= f (F x))) ((Out f)) :ruleset consume)
(Start (N 1) (N 2)) (Start (N 3) (N 4))
(run-schedule (seq (run make) (run consume) (run make) (run consume)))
"#;
    compare(source);
    let (_, nodes) = compare_mode(source, false);
    let report = nodes.report();
    let spine = &report["stage_spine"]["stats"];
    assert!(spine["cell_output_spans"].as_u64().unwrap() > 0, "{spine}");
    assert_eq!(spine["fragment_packets"], 0);
    assert!(spine["fragment_receipts"].as_u64().unwrap() > 0, "{spine}");
    assert_eq!(spine["fragment_receipts"], spine["fragment_direct_inserts_avoided"]);
    assert_eq!(spine["fragment_receipts"], spine["fragment_deliveries"]);
    let entries = &report["entry_schedule"]["stats"];
    assert!(entries["publication_loser_skips"].as_u64().unwrap() > 0, "{entries}");
    for k in ["fragment_pending_reads", "fragment_pending_writes", "fragment_slot_replacements"] {
        assert_eq!(entries[k], 0, "{k}");
    }
    assert_eq!(spine["completion_boundary_records"], spine["completion_boundary_reads"]);
}

#[test]
fn repeated_publications_skip_batch_losers_but_revalidate_later_batches() {
    let source = r#"
(datatype E (N i64) (Start E) (F E) (H E) (Gateway E) (Out E))
(ruleset make) (ruleset consume)
(rule ((Start x)) ((F x) (Gateway x)) :ruleset make)
(rule ((Start x)) ((H x) (Gateway x)) :ruleset make)
(rule ((Gateway x) (= f (F x)) (= h (H x))) ((Out x)) :ruleset consume)
(F (N 0)) (H (N 0)) (Gateway (N 0)) (Start (N 1))
(run-schedule (seq (run consume) (run make) (run consume)))
(check (Out (N 0)) (Out (N 1)))
"#;
    compare(source);
    let (_, nodes) = compare_mode(source, false);
    let report = nodes.report();
    let stats = &report["entry_schedule"]["stats"];
    assert!(stats["publication_pending_pushes"].as_u64().unwrap() > 0, "{stats}");
    assert!(stats["publication_loser_skips"].as_u64().unwrap() > 0, "{stats}");
    assert_eq!(stats["publication_pending_reuses"], 0, "a same-batch loser cannot maintain the queue");

    // The next source Run can publish to that still-packetless Entry before
    // consumption. The previous batch is no proof for this new application.
    let later = source.replace("(ruleset make)", "(ruleset later) (ruleset make)")
        .replace("(F (N 0))", "(rule ((Start x)) ((Gateway x)) :ruleset later)\n(F (N 0))")
        .replace("(run make) (run consume)", "(run make) (run later) (run consume)");
    compare(&later);
    let (_, nodes) = compare_mode(&later, false);
    let after = nodes.report();
    assert!(after["entry_schedule"]["stats"]["publication_pending_reuses"].as_u64().unwrap() > 0);
    assert!(after["stage_spine"]["stats"]["receipt_attempts"].as_u64().unwrap()
        > report["stage_spine"]["stats"]["receipt_attempts"].as_u64().unwrap());
}

#[test]
fn inline_function_output_keeps_last_producer_forwarding_and_late_inputs() {
    let source = r#"
(datatype E (N i64) (Start E) (Ready E) (Seen E i64))
(function Cost (E) i64 :merge (min old new))
(ruleset make) (ruleset join) (ruleset later) (ruleset read)
(rule ((Start x)) ((set (Cost x) 3)) :ruleset make)
(rule ((Start x)) ((set (Cost x) (+ 1 2))) :ruleset make)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset make)
(rule ((= x (N 2)) (= y (N 3))) ((union x y)) :ruleset join)
(rule ((Start x)) ((Ready x)) :ruleset later)
(rule ((Ready x) (= n (Cost x))) ((Seen x n)) :ruleset read)
(Start (N 0)) (Start (N 1)) (Start (N 2)) (Start (N 3))
(run-schedule (seq (run make) (run read) (run join) (run later) (run read)))
(check (Seen (N 0) 3) (Seen (N 2) 3))
"#;
    egglog::EGraph::default().parse_and_run_program(None, source).unwrap();
    compare(source);
    let (old, nodes) = compare_mode(source, false);
    let a = old.report();
    let b = nodes.report();
    let s = &b["stage_spine"]["stats"];
    assert!(s["inline_function_receipts"].as_u64().unwrap() > 0, "{s}");
    assert_eq!(s["inline_function_receipts"], s["inline_function_reads"]);
    assert!(s["receipt_redirects"].as_u64().unwrap() > 0, "{s}");
    assert_eq!(a["stage_spine"]["stats"]["inline_function_receipts"], 0);
    assert!(b["entry_schedule"]["stats"]["publication_loser_skips"].as_u64().unwrap() > 0);
}

#[test]
fn deletable_function_outputs_retain_boundary_publication() {
    let source = r#"
(datatype E (N i64) (Start E) (Seen E i64))
(function Cost (E) i64 :merge new)
(ruleset make) (ruleset remove) (ruleset remake) (ruleset read)
(rule ((Start x)) ((set (Cost x) 1)) :ruleset make)
(rule ((Start x)) ((delete (Cost x))) :ruleset remove)
(rule ((Start x)) ((set (Cost x) 2)) :ruleset remake)
(rule ((= n (Cost x))) ((Seen x n)) :ruleset read)
(Start (N 0))
(run-schedule (seq (run make) (run remove) (run read) (run remake) (run read)))
(check (Seen (N 0) 2))
"#;
    egglog::EGraph::default().parse_and_run_program(None, source).unwrap();
    compare(source);
    let (_, nodes) = compare_mode(source, false);
    assert_eq!(nodes.report()["stage_spine"]["stats"]["inline_function_receipts"], 0);
}

#[test]
fn refreshing_a_private_entry_rechecks_filters_before_reusing_its_packet() {
    let source = r#"
(datatype E (N i64) (Start E))
(function score (E) i64 :merge new)
(function out (E) i64 :merge new)
(ruleset first) (ruleset change) (ruleset reset) (ruleset read)
(rule ((Start x)) ((set (score x) 1)) :ruleset first)
(rule ((Start x)) ((set (score x) 2)) :ruleset change)
(rule ((Start x)) ((set (out x) 0)) :ruleset reset)
(rule ((= 1 (score x))) ((set (out x) 1)) :ruleset read)
(Start (N 0))
(run-schedule (seq (run first) (run read) (run reset) (run change) (run read)))
(check (= (out (N 0)) 0))
"#;
    egglog::EGraph::default().parse_and_run_program(None, source).unwrap();
    compare(source);
    let (_, nodes) = compare_mode(source, false);
    assert!(nodes.report()["entry_schedule"]["stats"]["row_reuses"].as_u64().unwrap() > 0);
}

#[test]
fn single_output_cells_keep_last_source_without_receipt_hash_coalescing() {
    let source = r#"
(datatype E (N i64) (Start E i64) (Gateway E) (Out E))
(ruleset make) (ruleset consume) (ruleset merge)
(rule ((Start x n)) ((Gateway x)) :ruleset make)
(rule ((Gateway x)) ((Out x)) :ruleset consume)
(rule ((= a (N 1)) (= b (N 2))) ((union a b)) :ruleset merge)
(Start (N 1) 10) (Start (N 1) 20) (Start (N 2) 30)
(run-schedule (seq (run make) (run merge) (run consume) (run make) (run consume)))
(check (Out (N 1)) (Out (N 2)))
"#;
    compare(source);
    let (_, nodes) = compare_mode(source, false);
    let report = nodes.report();
    let s = &report["stage_spine"]["stats"];
    assert!(s["cell_output_receipts"].as_u64().unwrap() > 0, "{s}");
    assert_eq!(s["cell_output_receipts"], s["cell_output_deliveries"]);
    assert_eq!(s["fragment_receipts"], 0);
    assert_eq!(s["direct_publication_hash_probes"], 0);
    assert!(report["entry_schedule"]["stats"]["publication_loser_skips"].as_u64().unwrap() > 0);
    // Repeated candidates still resolve their receipts, but only the winner
    // needs a visibility proof. Later Runs must publish and validate again.
    assert!(s["receipt_attempts"].as_u64().unwrap() < s["cell_output_deliveries"].as_u64().unwrap());
    assert_eq!(s["receipt_hits"], report["entry_schedule"]["stats"]["entry_publication_writes"]);
}

#[test]
fn interrupted_rhs_discards_only_its_private_receipts_and_keeps_prior_cell_outputs() {
    let source = r#"
(datatype E (N i64) (Start E) (F E) (H E) (Missing E) (Gateway E) (Out E))
(ruleset make) (ruleset consume)
(rule ((Start x)) ((F x) (Gateway x)) :ruleset make)
(rule ((Start x)) ((F x) (delete (Missing x)) (Gateway x)) :ruleset make)
(rule ((Start x)) ((H x) (Gateway x)) :ruleset make)
(rule ((Gateway x) (F x) (H x)) ((Out x)) :ruleset consume)
(Start (N 1))
(run-schedule (seq (run make) (run consume)))
(check (F (N 1)) (H (N 1)) (Out (N 1)))
"#;
    compare(source);
    let (_, nodes) = compare_mode(source, false);
    let report = nodes.report();
    let s = &report["stage_spine"]["stats"];
    assert_eq!(s["effect_aborted_frames"], 1, "{s}");
    // Only the first and third producer complete. The middle rule's earlier
    // graph effects remain, but it must not supply a continuation or overwrite
    // any completed Cell's receipts.
    // Initialization also supplies the Start Entry: three completed contexts,
    // five proposals and four distinct published anchors in total.
    assert_eq!(s["captured_contexts"], 3);
    assert_eq!(s["captured_anchors"], 5);
    assert_eq!(s["anchor_publications"], 4);
    assert_eq!(s["cell_output_receipts"], s["cell_output_deliveries"]);
    assert!(s["effect_outputs_reused"].as_u64().unwrap() > 0);
}

#[test]
fn mixed_cell_outputs_keep_direct_slots_beside_retirable_boundaries() {
    let source = include_str!("fixtures/mixed-cell-outputs.egg");
    compare(source);
    let (_, nodes) = compare_mode(source, false);
    let report = nodes.report();
    let s = &report["stage_spine"]["stats"];
    // Gateway has a permanent Entry; F can disappear. Both results belong to
    // the same completed producer, including when another producer reused it.
    assert!(s["fragment_receipts"].as_u64().unwrap() > 0, "{s}");
    assert!(s["completion_boundary_records"].as_u64().unwrap() > 0, "{s}");
    assert!(s["effect_outputs_reused"].as_u64().unwrap() > 0, "{s}");
    assert_eq!(s["direct_publication_hash_probes"], 0, "{s}");
    assert_eq!(s["cell_output_receipts"], s["cell_output_deliveries"]);
    assert!(report["entry_schedule"]["stats"]["entry_publications_retired"].as_u64().unwrap() > 0);
}

#[test]
fn completed_cell_publishes_only_last_exact_alias_without_dropping_donors() {
    let source = include_str!("fixtures/aliased-cell-outputs.egg");
    compare(source);
    let (old, nodes) = compare_mode(source, false);
    let before = old.report();
    let report = nodes.report();
    let s = &report["stage_spine"]["stats"];
    assert!(s["captured_anchors"].as_u64().unwrap()
        < before["stage_spine"]["stats"]["captured_anchors"].as_u64().unwrap());
    assert!(s["effect_aborted_frames"].as_u64().unwrap() > 0);
    assert!(s["completion_boundary_records"].as_u64().unwrap() > 0);
    // Query and earlier-effect donors must survive even when their own output
    // is removed; completed aliases keep the actual receipt, not an op address.
    assert!(s["alias_query_forwards"].as_u64().unwrap() > 0, "{s}");
    assert!(s["alias_effect_forwards"].as_u64().unwrap() > 0, "{s}");
    assert_eq!(s["cell_output_receipts"], s["cell_output_deliveries"]);
}

#[test]
fn effect_donor_occupies_publication_slot_without_fabricating_alias_execution() {
    let source = r#"
(datatype E (N i64) (Start E) (Gateway E) (Out E))
(ruleset make) (ruleset consume)
(rule ((Start x)) ((Gateway x) (Gateway x)) :ruleset make)
(rule ((Gateway x)) ((Out x)) :ruleset consume)
(Start (N 1))
(run-schedule (seq (run make) (run consume)))
(check (Out (N 1)))
"#;
    compare(source);
    let (_, nodes) = compare_mode(source, false);
    let report = nodes.report();
    let s = &report["stage_spine"]["stats"];
    assert_eq!(s["effect_output_copies"], 0, "{s}");
    assert!(s["effect_outputs_reused"].as_u64().unwrap() > 0);
    // The skipped alias must still have no raw result. Completion reads its
    // actual donor, whose result already occupies the final publication slot.
    assert!(s["alias_effect_forwards"].as_u64().unwrap() > 0);
    // Each captured Cell needs only its one actual source. The skipped second
    // Gateway must not reserve and initialize a permanently empty raw slot.
    assert_eq!(s["effect_slots_initialized"], s["effect_frames"], "{s}");
}

#[test]
fn sealed_outputs_keep_query_aliases_and_retirable_boundaries_in_source_order() {
    let source = r#"
(datatype E (N i64) (Start E) (F E) (G E) (Gateway E) (Boundary E) (Out E))
(ruleset make) (ruleset consume) (ruleset retire)
(rule ((Start x) (F x)) ((F x) (Gateway x) (Boundary x) (G x) (Gateway x)) :ruleset make)
(rule ((Gateway x) (F x) (= g (G x)) (Boundary x)) ((Out g)) :ruleset consume)
(rule ((Start x)) ((delete (Boundary x))) :ruleset retire)
(Start (N 1)) (F (N 1)) (G (N 1)) (Gateway (N 1))
(run-schedule (seq (run make) (run consume) (run retire) (run make) (run consume)))
(check (Out (G (N 1))))
"#;
    compare(source);
    let (_, nodes) = compare_mode(source, false);
    let report = nodes.report();
    let s = &report["stage_spine"]["stats"];
    let n = |key: &str| s[key].as_u64().unwrap();
    assert!(n("cell_output_span_seals") > 0, "{s}");
    assert!(n("cell_output_sealed_receipts") > n("cell_output_span_seals"), "{s}");
    assert!(n("alias_query_forwards") > 0, "{s}");
    assert!(n("alias_effect_forwards") > 0, "{s}");
    assert!(n("completion_boundary_records") > 0, "{s}");
    assert_eq!(n("captured_anchors"), n("output_registrations") + n("cell_output_sealed_receipts"));
    assert_eq!(n("cell_output_receipts"), n("cell_output_registrations") + n("cell_output_sealed_receipts"));
    assert_eq!(s["cell_output_receipts"], s["cell_output_deliveries"]);
}
