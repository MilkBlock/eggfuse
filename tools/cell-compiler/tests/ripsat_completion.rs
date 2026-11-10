#![cfg(feature = "iterative-bake")]
use eggfuse_cell_runtime::{checksum::artifact_digest, compiler, executor::Executor,
    graph::Graph, iterative::{Catalog,Limits}, program::Program};
use serde_json::{Value,json};
#[path = "../examples/emit_cell_retention.rs"]
mod fixture;

fn seal(mut raw:Value) -> Value {
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into(); raw
}
#[test]
fn alternate_routes_share_the_native_cell_registry_but_keep_entry_proofs() {
    let source=r#"
(datatype E (N i64) (Start E) (Left E) (Right E) (End E E))
(ruleset a)
(rule ((= s (Start x))) ((Left x) (Right x)) :ruleset a :name "left-first")
(rule ((= anchor (Start input))) ((Right input) (Left input)) :ruleset a :name "right-first")
(rule ((= s (Start x)) (= l (Left x))) ((Right x)) :ruleset a :name "stronger-entry")
(Start (N 1))
(run-schedule (run a))
"#;
    let core=eggfuse_bake::device_frontend::core("ripsat",source).unwrap();
    let p=Program::parse(compiler::compile(core,&Default::default()).unwrap()).unwrap();
    let profile=json!({"schema":"eggfuse-spine-shapes/v1","program_sha256":p.artifact["sha256"],
        "prefixes":(0..3).map(|r|json!({"edge":[0,0,r,0],"visits":2})).collect::<Vec<_>>()});
    let blocks=compiler::bake_spine_blocks(&p,&profile,&p,3).unwrap();
    let mut raw=p.artifact; raw["spine_blocks"]=blocks;
    let p=Program::parse(seal(raw.clone())).unwrap();
    let mut plan=Catalog::seed(&p,Limits::default()).unwrap();
    Catalog::emit_query_handoffs(&p,&mut plan).unwrap();
    raw["iterative_bake"]=plan;
    let p=Program::parse(seal(raw)).unwrap();
    let result=eggfuse_cell_compiler::state_plan::completion(&p).unwrap();
    let implementations=result["contracts"]["implementations"].as_array().unwrap();
    let class=|r|implementations.iter().find(|i|i["source_path"][0][1][0]==r).unwrap()["class"].clone();
    assert_eq!(class(0),class(1));
    assert_ne!(class(0),class(2));
    assert_eq!(implementations.len(),3);
    assert_eq!(result["contracts"]["structures"].as_array().unwrap().len(),2);
    // The actual ripsat registry, not a CPU-only map, interns both derivations.
    assert_eq!(result["cell_egraph"]["registered_compositions"],3);
    assert_eq!(result["cell_egraph"]["eclasses"],2);
}

#[test]
fn failed_rhs_does_not_train_a_completed_transition() {
    let source=include_str!("fixtures/history-retention.egg")
        .replace("((Mid x))", "((Mid x) (panic \"not-completed\"))");
    let dir=tempfile::tempdir().unwrap();
    fixture::emit(&source,&dir.path().join("case")).unwrap();
    let raw=serde_json::from_slice(&std::fs::read(dir.path().join("case/program.json")).unwrap()).unwrap();
    let p=Program::parse(raw).unwrap();
    let entries=p.iterative.entries();
    let bridge=p.templates.iter().position(|t|t.name=="bridge").unwrap();
    let bridge=p.rules.iter().position(|r|r.template==bridge).unwrap();
    let mut e=Executor::new(Graph::new(p).unwrap(),true);
    e.collect_iterative_pairs();
    assert!(e.execute().is_err());
    let report=e.report();
    assert!(report["stage_spine"]["stats"]["resumed_steps"].as_u64().unwrap()>0);
    let hits=report["stage_spine"]["iterative_bake"]["applied_units"].as_object().unwrap();
    for (unit,_) in hits {
        let entry=&entries[unit.parse::<usize>().unwrap()];
        assert_ne!(entry["expanded"].as_array().unwrap().last().unwrap()[1][0],bridge,
            "the bridge RHS failed and must not establish its completion: {hits:?}");
    }
}

#[cfg(feature = "sparse-cells")]
fn execute(raw:Value) -> (Executor,Value) {
    let p=Program::parse(raw).unwrap();
    let mut e=Executor::new(Graph::new_with_local_congruence(p).unwrap(),false);
    use eggfuse_cell_runtime::transfer_audit as audit;
    audit::take_digests(); audit::take_write_digests(); audit::take_resume_digests();
    audit::set_active(true); audit::enable_write_audit();
    let mut snapshots=vec![e.graph.export().unwrap()];
    loop {
        let previous=e.steps.len();
        e.execute_until(Some(previous+1)).unwrap();
        if e.steps.len()==previous {break;}
        snapshots.push(e.graph.export().unwrap());
    }
    audit::set_active(false);
    let evidence=json!({"states":snapshots,"inputs":audit::take_digests(),
        "writes":audit::take_write_digests(),"resumes":audit::take_resume_digests()});
    (e,evidence)
}

#[test]
#[cfg(feature = "sparse-cells")]
fn direct_completion_projects_real_results_and_preserves_every_run() {
    let base=include_str!("fixtures/history-retention.egg")
        .replace("(rule ((= x (N 2))) ((delete (Right x))) :ruleset retire)","")
        .replace("(Mid E)","(Mid E) (Seen E)")
        .replace("(N 1) (N 2)","(N 1) (N 2)\n(ruleset observe)\n(rule ((Left x)) ((Seen x)) :ruleset observe)\n(rule ((Right x)) ((Seen x)) :ruleset observe)")
        .replace("(run c)","(run c) (run observe)");
    for (case,source) in [base.clone(),base.replace("(N 1) (N 2)","(Left (N 1)) (Right (N 2))"),
        base.replace("(N 1) (N 2)","(N 1) (N 2)\n(rule ((= first (N 1)) (= second (N 2))) ((union first second)) :ruleset retire)"),
        base.replace("((Left x) (Right x) (Gateway x))","((Left x) (Right x) (Mid x) (Gateway x))")
            .replace("((Mid x))","((Right x) (Left x) (Mid x))"),
        base.replace("((Left x) (Right x) (Gateway x))","((Left x) (Right x) (Gateway x) (union (Left x) (Mid x)))")
            .replace("(rule ((= m (Mid x))) ((Left x) (Right x)) :ruleset c :name \"consume\")",
                "(rewrite (Mid x) (Left x) :ruleset c :name \"consume\")"),
    ].into_iter().enumerate() {
        let dir=tempfile::tempdir().unwrap();
        fixture::emit(&source,&dir.path().join("case")).unwrap();
        let raw:Value=serde_json::from_slice(&std::fs::read(dir.path().join("case/program.json")).unwrap()).unwrap();
        let compiled=eggfuse_cell_compiler::completion_bake::compile(Program::parse(raw.clone()).unwrap()).unwrap();
        check_entry_dispatch(&compiled);
        let (before,expected)=execute(raw); let (after,actual)=execute(compiled.clone());
        assert_eq!(expected,actual,"exact boundaries and ordered inputs/effects on the actual optimized path");
        assert_eq!(before.graph.export().unwrap(),after.graph.export().unwrap());
        assert_eq!(before.snapshots,after.snapshots);
        assert_eq!(before.binding_audit,after.binding_audit);
        for (a,b) in before.steps.iter().zip(&after.steps) {
            for key in ["ordinal","ruleset","path","iterations","epoch","logical_matches","executed_bindings","changed"] {assert_eq!(a[key],b[key],"{key}");}
        }
        let a=before.report(); let b=after.report();
        let stats=&b["stage_spine"]["stats"];
        assert!(stats["ripsat_completed"].as_u64().unwrap()>0,"case {case}; completion programs: {}; {stats}",compiled["iterative_bake"]["rhs_handoffs"]["completion_states"]);
        if case==3 {
            assert_eq!(stats["ripsat_completed"],4);
            assert!(stats["ripsat_projection_checks"].as_u64().unwrap()>0);
        }
        assert!(a["stats"]["handoff_attempts"].as_u64().unwrap()>b["stats"]["handoff_attempts"].as_u64().unwrap());
        assert!(a["stage_spine"]["stats"]["effect_slots_initialized"].as_u64().unwrap()>stats["effect_slots_initialized"].as_u64().unwrap());
        let mut corrupt=compiled.clone();
        let state=corrupt["iterative_bake"]["rhs_handoffs"]["completion_states"].as_array_mut().unwrap()
            .iter_mut().find(|s|!s.is_null()).unwrap();
        state["sources"][0][1]=json!(99999);
        assert!(Program::parse(seal(corrupt)).is_err());
        let mut corrupt=compiled;
        corrupt["iterative_bake"]["completion"]["contracts"]["structures"]=json!([]);
        assert!(Program::parse(seal(corrupt)).is_err());
    }
}

fn check_entry_dispatch(raw: &Value) {
    let plan = &raw["iterative_bake"];
    let dispatch = &plan["completion"]["entry_dispatch"];
    let switch = &plan["rhs_handoffs"];
    assert_eq!(dispatch["switch_sha256"], artifact_digest(switch));
    let programs = switch["completion_states"].as_array().unwrap();
    let mut routed = std::collections::BTreeSet::new();
    for entry in dispatch["entries"].as_array().unwrap() {
        assert!(!entry["states"].as_array().unwrap().is_empty());
        for pc in entry["states"].as_array().unwrap() {
            let pc = pc.as_u64().unwrap() as usize;
            assert!(routed.insert(pc), "one execution entry per program");
            assert!(!programs[pc].is_null());
            assert_eq!(entry["rule"], programs[pc]["rule"]);
        }
    }
    // Includes all suffix/fallback destinations, not just learned join edges.
    for (pc, program) in programs.iter().enumerate() {
        assert_eq!(routed.contains(&pc), !program.is_null());
    }
    assert_eq!(dispatch["programs"], routed.len());
    // Existing v1 artifacts remain valid without the optional dispatch export.
    let mut old = raw.clone();
    old["iterative_bake"]["completion"].as_object_mut().unwrap().remove("entry_dispatch");
    Program::parse(seal(old)).unwrap();
    for field in ["entries", "switch_sha256", "dynamic_checks", "default"] {
        let mut forged = raw.clone();
        forged["iterative_bake"]["completion"]["entry_dispatch"][field] = Value::Null;
        assert!(Program::parse(seal(forged)).is_err(), "unchecked {field}");
    }
    if !routed.is_empty() {
        let mut forged = raw.clone();
        forged["iterative_bake"]["completion"]["entry_dispatch"]["entries"][0]["states"][0] = json!(0);
        assert!(Program::parse(seal(forged)).is_err());
    }
}

#[test]
#[cfg(feature = "sparse-cells")]
fn deletable_results_keep_the_original_rhs_responsibility() {
    let dir=tempfile::tempdir().unwrap();
    fixture::emit(include_str!("fixtures/history-retention.egg"),&dir.path().join("case")).unwrap();
    let raw:Value=serde_json::from_slice(&std::fs::read(dir.path().join("case/program.json")).unwrap()).unwrap();
    let compiled=eggfuse_cell_compiler::completion_bake::compile(Program::parse(raw.clone()).unwrap()).unwrap();
    check_entry_dispatch(&compiled);
    let (before,expected)=execute(raw); let (after,actual)=execute(compiled);
    assert_eq!(expected,actual);
    assert_eq!(before.graph.export().unwrap(),after.graph.export().unwrap());
    assert_eq!(before.snapshots,after.snapshots);
    assert_eq!(before.binding_audit,after.binding_audit);
    assert_eq!(after.report()["stage_spine"]["stats"]["ripsat_completed"],0);
}
