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
    old.execute().unwrap();
    nodes.execute().unwrap();
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
    assert!(spine["fragment_packets"].as_u64().unwrap() > 0, "{spine}");
    assert_eq!(spine["fragment_receipts"], spine["fragment_direct_inserts_avoided"]);
    assert_eq!(spine["fragment_receipts"], spine["fragment_deliveries"]);
    assert!(report["entry_schedule"]["stats"]["fragment_slot_replacements"].as_u64().unwrap() > 0);
}

#[test]
fn repeated_fragment_publications_queue_a_new_packet_once() {
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
    assert!(stats["publication_pending_reuses"].as_u64().unwrap() > 0, "{stats}");
}
