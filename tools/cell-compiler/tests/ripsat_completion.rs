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
