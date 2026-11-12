use eggfuse_cell_runtime::{compiler,program::{Program,Op},graph::Graph,executor::Executor};
fn program(source:&str)->Program {
    let core=eggfuse_bake::device_frontend::core("entry-values",source).unwrap();
    Program::parse(compiler::compile(core,&Default::default()).unwrap()).unwrap()
}
const SOURCE:&str=r#"
(datatype E (N i64) (A E) (Out E))
(function View (E E) Unit :merge old)
(function Limit () i64 :merge (min old new))
(set (Limit) 2)
(ruleset make) (ruleset consume) (ruleset late)
(rule ((= x (N n))) ((set (View x (A x)) ())) :ruleset make)
(rule ((View x a) (= x (N n)) (< n (Limit))) ((Out (A x))) :ruleset consume)
(rule ((View x a)) ((set (View x a) ())) :ruleset make)
(rule ((= x (N 0))) ((N 1)) :ruleset late)
(N 0)
(run-schedule (seq (run make) (run consume) (run late) (run make) (run consume)))
(check (Out (A (N 0))) (Out (A (N 1))))
"#;
fn execute(p:Program)->Executor {
    let mut e=Executor::new(Graph::new(p).unwrap(),true);e.execute().unwrap();e
}
#[test]
fn entry_values_replace_construction_without_history_or_receipts() {
    let p=program(SOURCE);
    let raw=compiler::specialize_entry_values(&p).unwrap();
    assert!(!raw["entry_value_specialization"]["projections"].as_array().unwrap().is_empty());
    let q=Program::parse(raw).unwrap();
    let constructors=|p:&Program|p.templates.iter().flat_map(|t|t.ops.iter()).filter(|op|matches!(op,Op::Let(..))).count();
    assert!(constructors(&q)<constructors(&p));
    let b=execute(p);let a=execute(q);
    assert_eq!(a.snapshots,b.snapshots);
    assert!(a.graph.stats.constructor_requests<b.graph.stats.constructor_requests);
    assert!(a.report()["stage_spine"]["stats"]["history_allocations"].as_u64().unwrap()
        <=b.report()["stage_spine"]["stats"]["history_allocations"].as_u64().unwrap());
    println!("constructor requests: {} -> {}",b.graph.stats.constructor_requests,a.graph.stats.constructor_requests);
}
#[test]
fn missing_writer_proof_keeps_construction() {
    let source=SOURCE.replace("(rule ((View x a)) ((set (View x a) ())) :ruleset make)",
        "(rule ((= x (N n))) ((set (View x x) ())) :ruleset make)");
    let p=program(&source);
    let raw=compiler::specialize_entry_values(&p).unwrap();
    assert!(raw["entry_value_specialization"]["projections"].as_array().unwrap().is_empty());
}

#[test]
fn hidden_constructor_is_not_projected() {
    let source=SOURCE.replace("(ruleset make)",
        "(ruleset hide-a) (rule ((A x)) ((subsume (A x))) :ruleset hide-a) (ruleset make)").replace("(run late)","(run late) (run hide-a)");
    let p=program(&source);
    let raw=compiler::specialize_entry_values(&p).unwrap();
    assert!(raw["entry_value_specialization"]["projections"].as_array().unwrap().is_empty());
}
