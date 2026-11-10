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

#[test]
fn mixed_exports_share_old_slots_and_keep_new_constructor_results() {
    let source = include_str!("fixtures/history-retention.egg")
        .replace("(Mid E)", "(Mid E) (Extra E)")
        .replace("((Mid x))", "((Left x) (Right x) (Extra x) (Mid x))")
        .replace("((Left x) (Right x)) :ruleset c", "((Left x) (Right x) (Extra x)) :ruleset c");
    let dir=tempfile::tempdir().unwrap();
    fixture::emit(&source,&dir.path().join("case")).unwrap();
    let mut raw:Value=serde_json::from_slice(&std::fs::read(dir.path().join("case/program.json")).unwrap()).unwrap();
    let p=Program::parse(raw.clone()).unwrap();
    let plan=eggfuse_cell_compiler::state_plan::compile(&p).unwrap();
    assert!(plan["contracts"].as_array().unwrap().iter().any(|c| c["exports"].as_array().is_some_and(|e| !e.is_empty()) && c["can_inherit"]==true));
    raw["iterative_bake"]["state_plan"]=plan;
    let inherited=run(seal(raw.clone()));
    for choice in raw["iterative_bake"]["state_plan"]["implementations"].as_array_mut().unwrap() { *choice=json!("materialize"); }
    let materialized=run(seal(raw));
    assert_eq!(inherited.graph.export().unwrap(),materialized.graph.export().unwrap());
    assert_eq!(inherited.snapshots,materialized.snapshots);
    assert_eq!(inherited.binding_audit,materialized.binding_audit);
    let a=materialized.report();let b=inherited.report();
    assert!(b["stage_spine"]["stats"]["history_inherited_slots"].as_u64().unwrap()>0);
    assert!(a["stage_spine"]["stats"]["history_slots_written"].as_u64().unwrap()>b["stage_spine"]["stats"]["history_slots_written"].as_u64().unwrap());
    assert_eq!(a["key_lookup_calls"],b["key_lookup_calls"]);
}

#[test]
fn worker_handoff_is_bound_to_operations_and_catalog() {
    let dir=tempfile::tempdir().unwrap();
    fixture::emit(include_str!("fixtures/history-retention.egg"),&dir.path().join("case")).unwrap();
    let raw=serde_json::from_slice(&std::fs::read(dir.path().join("case/program.json")).unwrap()).unwrap();
    let p=Program::parse(raw).unwrap();
    let plan=eggfuse_cell_compiler::worker_handoff::compile(&p);
    assert!(!plan["entry_schedule"].is_null());
    assert_eq!(plan["rules"].as_array().unwrap().len(),p.rules.len());
    let expanded=p.iterative.state_contracts(&p);
    for (compact,original) in plan["stage_contracts"].as_array().unwrap().iter().zip(expanded.as_array().unwrap()) {
        if original["initial"]==true {assert_eq!(compact,original);continue;}
        let mut restored=compact.clone();
        restored.as_object_mut().unwrap().remove("pivot");
        for field in ["interface","effects","environment"] {restored[field]=original[field].clone();}
        assert_eq!(&restored,original);
        assert_eq!(compact["pivot"],original["interface"]["pivot"]);
    }
    assert_eq!(plan["completion_forecast"]["status"],"derived");
    for rule in plan["rules"].as_array().unwrap() {
        for effect in plan["layouts"][rule["layout"].as_u64().unwrap() as usize]["effects"].as_array().unwrap() {
            if let Some(table)=effect["table"].as_u64() {
                for node in plan["entry_routes"][table as usize].as_array().unwrap() {
                    assert_eq!(plan["entry_schedule"]["nodes"][node.as_u64().unwrap() as usize]["table"],p.tables[table as usize].name);
                }
            }
        }
    }
    eggfuse_cell_compiler::worker_handoff::validate(&p,&plan).unwrap();
    for field in ["program","stage_contracts","entry_schedule","rules","obligations","entry_routes","completion_forecast","layouts","worker_execution_proved","required_order","established_after"] {
        let mut corrupt=plan.clone();corrupt[field]=Value::Null;
        assert!(eggfuse_cell_compiler::worker_handoff::validate(&p,&corrupt).is_err());
    }
}

#[test]
fn catalog_rejects_duplicate_paths_without_retaining_a_runtime_lookup_copy() {
    let dir=tempfile::tempdir().unwrap();
    fixture::emit(include_str!("fixtures/history-retention.egg"),&dir.path().join("case")).unwrap();
    let mut raw:Value=serde_json::from_slice(&std::fs::read(dir.path().join("case/program.json")).unwrap()).unwrap();
    let p=Program::parse(raw.clone()).unwrap();
    let entries=p.iterative.entries();
    let cloned=p.iterative.clone();
    drop(p);
    assert_eq!(entries,cloned.entries());
    assert_eq!(cloned.path_storage()["lookup_payload_bytes"],0);
    let joins=raw["iterative_bake"]["joins"].as_array_mut().unwrap();
    assert!(!joins.is_empty());
    joins.push(joins[0].clone());
    assert!(matches!(Program::parse(seal(raw)),Err(e) if e.contains("duplicate continuation")));
}
