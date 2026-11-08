use eggfuse_cell_runtime::{
    checksum::artifact_digest,
    compiler,
    executor::Executor,
    graph::{Dependency, Graph},
    program::Program,
    value::Value,
};
use serde_json::json;
use std::collections::BTreeSet;

fn source(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("stable-ports", src).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn baked(src: &str) -> Program {
    let p = source(src);
    let mut raw = p.artifact.clone();
    let mut g = Graph::new_with_cell_ownership(p).unwrap();
    g.train_ownership_fragments().unwrap();
    let mut e = Executor::new(g, false);
    e.execute().unwrap();
    let profile = e.graph.ownership_fragment_profile().unwrap();
    // These semantic fixtures exercise every observed local route. Production
    // ranking and performance admission are separate concerns.
    raw["ownership_fragments"] = json!({"schema":"eggfuse-ownership-fragments/v1",
        "source":profile["source"],"fragments":profile["records"].as_array().unwrap()
            .iter().map(|r|r["fragment"].clone()).collect::<Vec<_>>()});
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    Program::parse(raw).unwrap()
}
fn compare(src: &str) -> Executor {
    let p = baked(src);
    let mut old = Executor::new(Graph::new_with_cell_ownership(p.clone()).unwrap(), true);
    let mut new = Executor::new(Graph::new_with_stable_ports(p.clone()).unwrap(), true);
    let mut keyed = Executor::new(Graph::new_with_port_keys(p).unwrap(), true);
    old.execute().unwrap();
    new.execute().unwrap();
    keyed.execute().unwrap();
    assert_eq!(old.initial_audit, keyed.initial_audit);
    assert_eq!(old.snapshots, keyed.snapshots);
    assert_eq!(old.binding_audit, keyed.binding_audit);
    assert_eq!(old.steps.len(), keyed.steps.len());
    for (a, b) in old.steps.iter().zip(&keyed.steps) {
        for k in [
            "ordinal",
            "ruleset",
            "path",
            "iterations",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(a[k], b[k], "port keys: {k}");
        }
    }
    keyed.graph.ownership_report();
    assert!(
        keyed.graph.stable_port_report()["birth_indexed_port_keys"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert_eq!(
        keyed.graph.ownership_report()["stats"]["key_completions"],
        0
    );
    assert_eq!(old.initial_audit, new.initial_audit);
    assert_eq!(old.snapshots, new.snapshots);
    assert_eq!(old.binding_audit, new.binding_audit);
    assert_eq!(old.steps.len(), new.steps.len());
    for (a, b) in old.steps.iter().zip(&new.steps) {
        for k in [
            "ordinal",
            "ruleset",
            "path",
            "iterations",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(a[k], b[k], "{k}");
        }
    }
    new.graph.ownership_report();
    let report = new.graph.stable_port_report();
    assert!(report["live_port_fields"].as_u64().unwrap() > 0);
    assert_eq!(report["pending_canonical_keys"], 0);
    egglog::EGraph::default()
        .parse_and_run_program(None, src)
        .unwrap();
    new
}

#[test]
fn cross_stage_fields_are_stable_while_legacy_keys_still_complete() {
    let e = compare(
        r#"
(datatype E (N i64) (F E) (G E) (H E))
(ruleset a) (ruleset b) (ruleset merge)
(rule ((= x (N n))) ((G (F x))) :ruleset a)
(rule ((= g (G f))) ((H g)) :ruleset b)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run merge)))
(check (= (H (G (F (N 0)))) (H (G (F (N 1))))))
"#,
    );
    let p = e.graph.stable_port_report();
    assert!(p["stats"]["notifications"].as_u64().unwrap() > 0);
    assert!(p["stats"]["legacy_key_enqueues"].as_u64().unwrap() > 0);
    let old_path = e.graph.ownership_report();
    assert_eq!(old_path["stats"]["port_checks"], 0);
    assert_eq!(old_path["stats"]["row_copies"], 0);
}

#[test]
fn multi_input_aliases_preserve_partial_equality_and_ordered_effects() {
    compare(
        r#"
(datatype E (N i64) (Pair E E) (Wrap E))
(ruleset build) (ruleset first) (ruleset second)
(rule ((= a (N 0)) (= b (N 1)) (= c (N 2)) (= d (N 3)))
      ((Wrap (Pair a c)) (Wrap (Pair b d))) :ruleset build)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset first)
(rule ((= c (N 2)) (= d (N 3))) ((union c d)) :ruleset second)
(N 0) (N 1) (N 2) (N 3)
(run-schedule (seq (run build) (run first) (run second)))
(check (= (Pair (N 0) (N 2)) (Pair (N 1) (N 3))))
"#,
    );
}

#[test]
fn deleted_producer_retains_consumers_across_a_late_union() {
    compare(
        r#"
(datatype E (N i64) (F E) (G E) (H E))
(ruleset a) (ruleset b) (ruleset erase) (ruleset merge) (ruleset read)
(rule ((= x (N n))) ((F x)) :ruleset a)
(rule ((= f (F x))) ((G x)) :ruleset b)
(rule ((= f (F x))) ((delete (F x))) :ruleset erase)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(rule ((= g (G x))) ((H g)) :ruleset read)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run erase) (run merge) (run read)))
"#,
    );
}

#[test]
fn stable_address_survives_representative_change_and_expires_on_recreation() {
    let p = source("(datatype E (N i64) (F E)) (N 0) (N 1) (F (N 1)) (run-schedule (run))");
    let n = p.tables.iter().position(|t| t.name == "N").unwrap();
    let f = p.tables.iter().position(|t| t.name == "F").unwrap();
    let mut g = Graph::new_with_port_keys(p).unwrap();
    let a = g
        .lookup(n, &[Value::Int(0)])
        .unwrap()
        .unwrap()
        .values
        .last()
        .unwrap()
        .clone();
    let b = g
        .lookup(n, &[Value::Int(1)])
        .unwrap()
        .unwrap()
        .values
        .last()
        .unwrap()
        .clone();
    let old = g.lookup(f, &[b.clone()]).unwrap().unwrap();
    let Dependency::Fact(witness) = old.witness else {
        panic!("constructor fact")
    };
    let address = g.fact_port(witness, 0).unwrap();
    assert_eq!(g.read_port(address).unwrap(), b);
    g.enqueue_union(a.clone(), b.clone()).unwrap();
    g.repair().unwrap();
    assert_eq!(g.fact_port(witness, 0), Some(address));
    assert_eq!(g.read_port(address).unwrap(), a);
    assert_eq!(
        old.values[0], b,
        "a previously returned row is an immutable snapshot"
    );
    let domains = g.stable_port_report()["stats"]["port_domain_probes"]
        .as_u64()
        .unwrap();
    assert_eq!(g.lookup(f, &[a.clone()]).unwrap().unwrap().values[0], a);
    assert!(
        g.stable_port_report()["stats"]["port_domain_probes"]
            .as_u64()
            .unwrap()
            > domains,
        "alias lookup must complete an immutable birth-hint miss"
    );
    g.hide(f, &[a.clone()], true).unwrap();
    assert!(g.fact(witness).unwrap().is_none());
    assert!(
        g.read_port(address).is_err(),
        "retired component must not resolve a stale address"
    );
    g.dynamic_construct(f, vec![a.clone()]).unwrap();
    let new = g.lookup(f, &[a]).unwrap().unwrap();
    let Dependency::Fact(new_witness) = new.witness else {
        panic!("constructor fact")
    };
    assert_ne!(g.fact_port(new_witness, 0), Some(address));
    assert!(g.read_port(address).is_err());
    g.ownership_report();
    g.stable_port_report();
}

#[test]
fn simultaneous_input_changes_preserve_the_ordered_survivor() {
    compare(
        r#"
(datatype E (N i64) (F E) (G E))
(ruleset build) (ruleset merge)
(rule ((= x (N 1)) (= y (N 2))) ((G (F x)) (G (F y))) :ruleset build)
(rule ((= z (N 0)) (= x (N 1)) (= y (N 2))) ((union z x) (union z y)) :ruleset merge)
(N 0) (N 1) (N 2)
(run-schedule (seq (run build) (run merge)))
(check (= (G (F (N 1))) (G (F (N 2)))))
"#,
    );
}

#[test]
fn equal_input_ports_do_not_collapse_distinct_scalar_keys() {
    let e = compare(
        r#"
(datatype E (N i64) (F i64 E))
(ruleset build) (ruleset merge)
(rule ((= x (N 0)) (= y (N 1))) ((F 10 x) (F 20 y)) :ruleset build)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run build) (run merge)))
"#,
    );
    let f = e
        .graph
        .program
        .tables
        .iter()
        .position(|t| t.name == "F")
        .unwrap();
    assert_eq!(e.graph.witness_count(f), 2);
}
