#![cfg(all(feature="iterative-bake",feature="sparse-cells",feature="storage-metrics"))]
use eggfuse_cell_runtime::{compiler,program::Program,graph::Graph,executor::Executor,transfer_audit as audit};
fn program(source:&str)->Program {
    let core=eggfuse_bake::device_frontend::core("unit-facts",source).unwrap();
    Program::parse(compiler::compile(core,&["View".to_owned()].into_iter().collect()).unwrap()).unwrap()
}
const SOURCE:&str=r#"
(datatype E (N i64) (Out E))
(function View (E) Unit :merge old)
(ruleset make) (ruleset consume) (ruleset join)
(rule ((= x (N n))) ((set (View x) ())) :ruleset make)
(rule ((View x)) ((Out x)) :ruleset consume)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset join)
(N 0) (N 1)
(run-schedule (seq (saturate (run make)) (run consume) (run join) (saturate (run make)) (run consume)))
(check (View (N 0)) (Out (N 0)) (Out (N 1)))
"#;
#[test]
fn cell_membership_preserves_duplicate_union_and_saturation_boundaries() {
    let p=program(SOURCE);
    let q=Program::parse(compiler::specialize_unit_facts(&p).unwrap()).unwrap();
    compiler::validate_unit_fact_specialization(&p,&q).unwrap();
    assert_eq!(q.artifact["unit_fact_specialization"]["tables"].as_array().unwrap().len(),1);
    let run=|p| {
        audit::take_logical_write_digests();
        let mut e=Executor::new(Graph::new(p).unwrap(),true);
        audit::set_active(true);audit::enable_write_audit();
        e.execute().unwrap();audit::set_active(false);
        let writes=audit::take_logical_write_digests();
        (e,writes)
    };
    let (b,bw)=run(p);let (a,aw)=run(q);
    assert!(bw.iter().map(|(n,_)|*n).sum::<u64>()>0);
    assert_eq!(aw,bw);
    assert_eq!(a.snapshots,b.snapshots);
    assert_eq!(a.steps.len(),b.steps.len());
    assert!(a.graph.program.tables.iter().find(|t|t.name=="View").unwrap().virtual_fact);
}
#[test]
fn deletion_blocks_membership_rewrite() {
    let p=program(&SOURCE.replace("((Out x))", "((delete (View x)) (Out x))"));
    let q=compiler::specialize_unit_facts(&p).unwrap();
    assert!(q["unit_fact_specialization"]["tables"].as_array().unwrap().is_empty());
}
#[test]
fn typed_rhs_read_blocks_membership_rewrite() {
    let p=program(SOURCE);
    let mut core=p.artifact["source_core"].clone();
    let group=core["rulesets"].as_array_mut().unwrap().iter_mut().find(|g|g["name"]=="consume").unwrap();
    let rule=&mut group["rules"][0];
    let arg=rule["head"][0]["args"][0].clone();
    rule["head"].as_array_mut().unwrap().insert(0,serde_json::json!({"op":"let","dst":"unit_read",
        "sort":{"name":"Unit","kind":"Unit"},"call":{"table":"View"},"args":[arg]}));
    let p=Program::parse(compiler::compile(core,&Default::default()).unwrap()).unwrap();
    let q=compiler::specialize_unit_facts(&p).unwrap();
    assert!(q["unit_fact_specialization"]["tables"].as_array().unwrap().is_empty());
}

#[test]
fn source_checker_rejects_forged_membership_selection() {
    let p=program(SOURCE);
    let mut q=Program::parse(compiler::specialize_unit_facts(&p).unwrap()).unwrap();
    q.artifact["unit_fact_specialization"]["tables"]=serde_json::json!([]);
    assert!(compiler::validate_unit_fact_specialization(&p,&q).is_err());
}

#[test]
fn owned_unit_facts_use_shared_ports_across_union() {
    let p=program(SOURCE);
    let mut raw=compiler::specialize_unit_facts(&p).unwrap();
    raw["unit_fact_ownership"]=serde_json::json!(true);
    let q=Program::parse(raw).unwrap();
    let mut b=Executor::new(Graph::new_with_local_congruence(p).unwrap(),true);
    b.graph.use_port_domains_only().unwrap();b.use_completed_parent_takeover().unwrap();b.execute().unwrap();
    let mut a=Executor::new(Graph::new_with_local_congruence(q).unwrap(),true);
    a.graph.use_port_domains_only().unwrap();a.use_completed_parent_takeover().unwrap();a.execute().unwrap();
    assert_eq!(a.snapshots,b.snapshots);
    assert_eq!(a.steps.len(),b.steps.len());
}

#[test]
fn logical_write_audit_detects_reordered_effects_with_equal_final_state() {
    let source=SOURCE.replace("(ruleset make)",
        "(function AuditA (E) Unit :merge old) (function AuditB (E) Unit :merge old) (ruleset make)")
        .replace("((Out x))", "((set (AuditA x) ()) (set (AuditB x) ()) (Out x))");
    let other=source.replace("(set (AuditA x) ()) (set (AuditB x) ())",
        "(set (AuditB x) ()) (set (AuditA x) ())");
    let run=|source:&str| {
        let mut e=Executor::new(Graph::new(program(source)).unwrap(),true);
        audit::take_logical_write_digests();audit::set_active(true);audit::enable_write_audit();
        e.execute().unwrap();audit::set_active(false);
        (e.graph.export().unwrap(),audit::take_logical_write_digests())
    };
    let (a,aw)=run(&source);let (b,bw)=run(&other);
    assert_eq!(a,b);assert_ne!(aw,bw);
}

#[test]
fn initial_membership_keeps_the_function_representation() {
    let p=program(&SOURCE.replace("(N 0) (N 1)","(N 0) (N 1) (set (View (N 0)) ())"));
    let q=compiler::specialize_unit_facts(&p).unwrap();
    assert!(q["unit_fact_specialization"]["tables"].as_array().unwrap().is_empty());
}
