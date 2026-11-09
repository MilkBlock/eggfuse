use eggfuse_cell_runtime::{
    checksum::artifact_digest, compiler, executor::Executor, graph::Graph, program::Program,
};
use serde_json::json;

fn source(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("ownership-receipts", src).unwrap();
    Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap()
}

fn assert_ordered_equal(expected: &Executor, actual: &Executor) {
    assert_eq!(expected.initial_audit, actual.initial_audit);
    assert_eq!(expected.snapshots, actual.snapshots);
    assert_eq!(expected.binding_audit, actual.binding_audit);
    assert_eq!(expected.graph.export().unwrap(), actual.graph.export().unwrap());
    assert_eq!(expected.steps.len(), actual.steps.len());
    for (a, b) in expected.steps.iter().zip(&actual.steps) {
        for key in ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches",
                    "executed_bindings", "changed"] {
            assert_eq!(a[key], b[key], "ordered Run field {key}");
        }
    }
}

const STAGES: &str = r#"
(datatype E (N i64) (F E) (G E) (H E) (Seen E))
(ruleset a) (ruleset b) (ruleset c) (ruleset merge)
(rule ((= x (N n))) ((G (F x))) :ruleset a)
(rule ((= x (G y))) ((H x)) :ruleset b)
(rule ((= x (H y))) ((Seen x)) :ruleset c)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run merge) (run c)))
"#;

#[test]
fn fragment_training_can_begin_after_executor_construction() {
    let p = source(STAGES);
    let mut early_graph = Graph::new_with_cell_ownership(p.clone()).unwrap();
    early_graph.train_ownership_fragments().unwrap();
    let mut early = Executor::new(early_graph, true);
    let mut late = Executor::new(Graph::new_with_cell_ownership(p).unwrap(), true);
    // Ownership has already adopted imported facts and configured Spine.
    // Receipt demand must observe this later training activation.
    late.graph.train_ownership_fragments().unwrap();
    early.execute().unwrap();
    late.execute().unwrap();
    assert_ordered_equal(&early, &late);
    let a = early.graph.ownership_fragment_profile().unwrap();
    let b = late.graph.ownership_fragment_profile().unwrap();
    assert_eq!(a, b);
    assert!(!b["records"].as_array().unwrap().is_empty());
    assert!(late.graph.ownership_report()["stats"]["composition_cross_stage_joins"]
        .as_u64().unwrap() > 0);
}

#[test]
fn admitted_receivers_keep_receipts_and_unbaked_rules_keep_original_order() {
    let p = source(STAGES);
    let mut training = Graph::new_with_cell_ownership(p.clone()).unwrap();
    training.train_ownership_fragments().unwrap();
    let mut training = Executor::new(training, false);
    training.execute().unwrap();
    let profile = training.graph.ownership_fragment_profile().unwrap();
    // Admit only the final receiver. Other covered RHS rules must use the
    // unchanged Spine alias requirements and ordinary boundary fallback.
    let receiver = p.sets["c"][0];
    let mut raw = p.artifact;
    let fragments = profile["records"].as_array().unwrap().iter()
        .map(|record| &record["fragment"])
        .filter(|fragment| fragment["hops"].as_array().unwrap().iter()
            .all(|hop| hop["rule"].as_u64() == Some(receiver as u64)))
        .cloned().collect::<Vec<_>>();
    assert!(!fragments.is_empty());
    raw["ownership_fragments"] = json!({"schema":"eggfuse-ownership-fragments/v1",
        "source":profile["source"], "fragments":fragments});
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    let p = Program::parse(raw).unwrap();
    assert!(p.cell_ownership.composition.active_rules[receiver]);
    assert_eq!(p.cell_ownership.composition.active_rules.iter().filter(|&&active| active).count(), 1);
    let mut expected = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut actual = Executor::new(Graph::new_with_local_congruence(p).unwrap(), true);
    expected.execute().unwrap();
    actual.execute().unwrap();
    assert_ordered_equal(&expected, &actual);
    let report = actual.graph.ownership_report();
    assert!(report["stats"]["composition_baked_hits"].as_u64().unwrap() > 0);
}

#[test]
fn inactive_ownership_receiver_preserves_static_query_alias_publication() {
    let p = source(r#"
(datatype E (N i64) (F E) (G E) (H E))
(ruleset alias) (ruleset consume)
(rule ((= f (F x))) ((F x) (G f)) :ruleset alias)
(rule ((= g (G x))) ((H g)) :ruleset consume)
(F (N 0)) (F (N 1))
(run-schedule (seq (run alias) (run consume)))
"#);
    let mut expected = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut actual = Executor::new(Graph::new_with_local_congruence(p).unwrap(), true);
    assert!(actual.graph.program.cell_ownership.composition.active_rules.iter().all(|&active| !active));
    expected.execute().unwrap();
    actual.execute().unwrap();
    assert_ordered_equal(&expected, &actual);
    assert!(actual.report()["stage_spine"]["stats"]["alias_query_forwards"].as_u64().unwrap() > 0);
}
