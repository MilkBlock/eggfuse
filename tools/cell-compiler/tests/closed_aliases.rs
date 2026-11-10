#![cfg(all(feature = "sparse-cells", feature = "iterative-bake"))]
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};
#[path = "support/closed_cell.rs"]
mod fixture;

fn compare(source: &str, congruence: bool) -> Executor {
    let p = fixture::program(source, congruence);
    let mut control = p.artifact.clone();
    control.as_object_mut().unwrap().remove("iterative_bake");
    let execute = |p| {
        let mut e = Executor::new(Graph::new_with_local_congruence(p).unwrap(), true);
        e.use_entry_publications().unwrap();
        e.execute().unwrap();
        e
    };
    let old = execute(Program::parse(control).unwrap());
    let new = execute(p);
    assert_eq!(old.snapshots, new.snapshots);
    assert_eq!(old.binding_audit, new.binding_audit);
    assert_eq!(old.graph.export().unwrap(), new.graph.export().unwrap());
    assert_eq!(old.steps.len(), new.steps.len());
    for (a,b) in old.steps.iter().zip(&new.steps) {
        for k in ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed"] {
            assert_eq!(a[k], b[k], "{k}");
        }
    }
    assert_eq!(old.report()["known_results"]["static_eliminated"], new.report()["known_results"]["static_eliminated"]);
    assert_eq!(old.graph.stats.union_requests, new.graph.stats.union_requests);
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, source).unwrap();
    new
}

#[test]
fn cell_aliases_complete_query_and_effect_sources_without_raw_alias_receipts() {
    let new = compare(&fixture::SOURCE.replace("(run retire)", ""), true);
    assert_eq!(new.graph.stats.handoff_closed, 2);
    assert_eq!(new.graph.stats.handoff_closed_fallback, 0);
    assert_eq!(new.graph.stats.handoff_attempts, 4);
    let report = new.report();
    assert!(report["stage_spine"]["stats"]["alias_query_forwards"].as_u64().unwrap() > 0);
    assert!(report["stage_spine"]["stats"]["alias_effect_forwards"].as_u64().unwrap() > 0);
}

#[test]
fn late_miss_resumes_the_prefix_without_rechecking_or_requeuing_its_union() {
    let new = compare(fixture::SOURCE, true);
    assert_eq!(new.graph.stats.handoff_closed, 1);
    assert_eq!(new.graph.stats.handoff_closed_fallback, 1);
    // Every actual check, including the failed one, counts once. The prefix's
    // result, receipt frame and queued union survive first-miss promotion.
    assert_eq!(new.graph.stats.handoff_attempts, 4);
    assert_eq!(new.report()["stage_spine"]["stats"]["effect_aborted_frames"], 0);
}

#[test]
fn alias_proofs_do_not_enable_unsupported_unions_or_relax_wire_validation() {
    let new = compare(&fixture::SOURCE.replace("(run retire)", ""), false);
    assert_eq!(new.graph.stats.handoff_closed, 0);
    assert!(new.graph.stats.handoff_attempts > 0, "union policy must be tested with active transfers");
    let mut raw = fixture::program(fixture::SOURCE, true).artifact;
    let state = raw["iterative_bake"]["rhs_handoffs"]["states"].as_array_mut().unwrap()
        .iter_mut().find(|n| !n["program"]["reuse"].as_array().unwrap().is_empty()).unwrap();
    assert_eq!(state["program"]["complete"], false);
    state["program"]["complete"] = true.into();
    assert!(matches!(Program::parse(raw), Err(e) if e.contains("invalid cross-Run RHS plan")));
}
