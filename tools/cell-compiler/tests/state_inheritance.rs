#![cfg(feature = "iterative-bake")]
#[path = "../examples/emit_cell_retention.rs"]
mod fixture;
use eggfuse_cell_runtime::{program::Program, graph::Graph, executor::Executor, checksum::artifact_digest};
use serde_json::{Value, json};
fn seal(mut raw: Value) -> Value {
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    raw
}
fn run(raw: Value) -> Executor {
    let p = Program::parse(raw).unwrap();
    let mut e = Executor::new(Graph::new_with_local_congruence(p).unwrap(), true);
    e.execute().unwrap(); e
}
#[test]
fn extraction_replaces_transfer_without_changing_source_run_visibility() {
    let source = include_str!("fixtures/history-retention.egg");
    let mut evidence = vec![];
    for source in [source.to_owned(), source.replace("(run retire)", ""), source.replace("((delete (Right x)))", "((union x (N 1)))")] {
        let directory = tempfile::tempdir().unwrap();
        fixture::emit(&source, &directory.path().join("case")).unwrap();
        let mut raw: Value = serde_json::from_slice(&std::fs::read(directory.path().join("case/program.json")).unwrap()).unwrap();
        let p = Program::parse(raw.clone()).unwrap();
        let plan = eggfuse_cell_compiler::state_plan::compile(&p).unwrap();
        assert!(plan["implementations"].as_array().unwrap().iter().any(|v| v == "inherit"));
        raw["iterative_bake"]["state_plan"] = plan.clone();
        let inherited = run(seal(raw.clone()));
        for v in raw["iterative_bake"]["state_plan"]["implementations"].as_array_mut().unwrap() { *v = json!("materialize"); }
        let materialized = run(seal(raw.clone()));
        assert_eq!(inherited.graph.export().unwrap(), materialized.graph.export().unwrap());
        assert_eq!(inherited.snapshots, materialized.snapshots);
        assert_eq!(inherited.binding_audit, materialized.binding_audit);
        assert_eq!(inherited.steps.len(), materialized.steps.len());
        for (a,b) in inherited.steps.iter().zip(&materialized.steps) {
            for k in ["ordinal","ruleset","path","iterations","epoch","logical_matches","executed_bindings","changed"] { assert_eq!(a[k], b[k]); }
        }
        let a=materialized.report(); let b=inherited.report();
        assert_eq!(a["key_lookup_calls"], b["key_lookup_calls"]);
        assert!(a["stage_spine"]["stats"]["history_allocations"].as_u64().unwrap() > b["stage_spine"]["stats"]["history_allocations"].as_u64().unwrap());
        evidence.push(json!({"state_plan":plan,"source":source,"exact_state_and_run_bindings":true,
            "history_allocations":[a["stage_spine"]["stats"]["history_allocations"],b["stage_spine"]["stats"]["history_allocations"]],
            "history_slots_written":[a["stage_spine"]["stats"]["history_slots_written"],b["stage_spine"]["stats"]["history_slots_written"]],
            "key_lookup_calls":[a["key_lookup_calls"],b["key_lookup_calls"]]}));
        raw["iterative_bake"]["state_plan"]["implementations"][0] = json!("inherit");
        assert!(Program::parse(seal(raw.clone())).is_err());
        raw["iterative_bake"]["state_plan"]["implementations"][0] = json!("materialize");
        raw["iterative_bake"]["state_plan"]["contracts"][1]["activation"]["boundary"] = json!("early");
        assert!(Program::parse(seal(raw)).is_err());
    }
    if let Ok(path) = std::env::var("CELL_STATE_EVIDENCE") {
        std::fs::write(path, serde_json::to_vec_pretty(&json!({"scope":"standalone Cell CPU; diagnostic work, no speed measurement","cases":evidence})).unwrap()).unwrap();
    }
}

#[test]
fn empty_catalog_is_supported() {
    let core = eggfuse_bake::device_frontend::core("empty", "(datatype E (N i64)) (N 0) (ruleset r) (run-schedule (run r))").unwrap();
    let raw = eggfuse_cell_runtime::compiler::compile(core, &Default::default()).unwrap();
    let p = Program::parse(raw).unwrap();
    let plan = eggfuse_cell_compiler::state_plan::compile(&p).unwrap();
    assert_eq!(plan["implementations"], json!([]));
}
