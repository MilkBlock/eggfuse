use eggfuse_cell_runtime::{
    compiler, executor::Executor, graph::Graph, program::Program, value::Value,
};
use serde_json::json;
use std::collections::BTreeSet;
fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("repair-ports", source).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn compare(p: Program) -> (Executor, Executor) {
    let mut a = Executor::new(Graph::new(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_repair_ports(p).unwrap(), true);
    a.execute().unwrap();
    b.execute().unwrap();
    assert_eq!(a.initial_audit, b.initial_audit);
    assert_eq!(a.snapshots, b.snapshots);
    assert_eq!(a.binding_audit, b.binding_audit);
    for (x, y) in a.steps.iter().zip(&b.steps) {
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
            assert_eq!(x[k], y[k], "{k}");
        }
    }
    assert_eq!(a.steps.len(), b.steps.len());
    (a, b)
}
#[test]
fn result_ports_preserve_mutable_merges_visibility_and_later_key_repairs() {
    let source = r#"
(datatype E (N i64) (F E) (Pair E E) (Seen E))
(function chosen (E) E :merge old)
(function count (E) i64 :merge (+ old new))
(ruleset outputs) (ruleset keys) (ruleset read) (ruleset hide) (ruleset delete) (ruleset reinsert)
(rule ((= a (N 1)) (= b (N 2))) ((union (F a) b)) :ruleset outputs)
(rule ((= a (N 1)) (= b (N 2))) ((union a b)) :ruleset keys)
(rule ((= f (F a))) ((Seen f)) :ruleset read)
(rule ((= a (N 1))) ((subsume (F a))) :ruleset hide)
(rule ((= a (N 1))) ((delete (F a))) :ruleset delete)
(rule ((= a (N 1))) ((F a)) :ruleset reinsert)
(F (N 1)) (F (N 2)) (Pair (F (N 1)) (N 1))
(set (chosen (N 1)) (F (N 1))) (set (chosen (N 2)) (N 2))
(set (count (N 1)) 3) (set (count (N 2)) 7)
(run-schedule (seq (run outputs) (run read) (run keys) (run read) (run hide) (run read) (run delete) (run reinsert) (run read)))
(check (= (count (N 1)) 10))
"#;
    let p = program(source);
    let (a, b) = compare(p.clone());
    assert!(
        b.graph.repair_port_report()["stats"]["result_events"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert!(b.graph.stats.repaired_dependencies < a.graph.stats.repaired_dependencies);
    #[cfg(feature = "sparse-cells")]
    {
        let work = &b.graph.maintenance_report()["stats"];
        assert!(work["canonical_subscription_calls"].as_u64().unwrap() > 0);
        assert!(work["subscription_scalar_fields_skipped"].as_u64().unwrap() > 0);
        assert!(work["subscription_root_reads_omitted"].as_u64().unwrap() > 0);
        assert!(work["subscription_sets_replaced_in_place"].as_u64().unwrap() > 0);
    }
    let mut corrupt = p.artifact.clone();
    corrupt["repair_ports"]["key_eq_columns"] = json!([]);
    assert!(Program::parse(corrupt).is_err());
    let mut legacy = p.artifact;
    legacy.as_object_mut().unwrap().remove("repair_ports");
    compare(Program::parse(legacy).unwrap());
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, source).unwrap();
}
#[test]
fn duplicate_initial_keys_retain_collision_order() {
    let mut p = program("(datatype E (N i64)) (N 1) (N 2) (run 1)");
    let mut duplicate = p
        .initial
        .iter()
        .rev()
        .find(|r| r["table"] == "N")
        .unwrap()
        .clone();
    duplicate["values"]
        .as_array_mut()
        .unwrap()
        .last_mut()
        .unwrap()["eq"] = json!("extra-initial-result");
    p.initial.push(duplicate);
    let table = p.tables.iter().position(|t| t.name == "N").unwrap();
    let run = |fast| {
        let mut g = if fast {
            Graph::new_with_repair_ports(p.clone()).unwrap()
        } else {
            Graph::new(p.clone()).unwrap()
        };
        let a = g
            .lookup(table, &[Value::Int(1)])
            .unwrap()
            .unwrap()
            .values
            .last()
            .unwrap()
            .clone();
        let b = g
            .lookup(table, &[Value::Int(2)])
            .unwrap()
            .unwrap()
            .values
            .last()
            .unwrap()
            .clone();
        g.epoch = 1;
        g.enqueue_union(a, b).unwrap();
        g.repair().unwrap();
        g
    };
    let a = run(false);
    let b = run(true);
    let mut x = vec![];
    let mut y = vec![];
    a.write_export(&mut x).unwrap();
    b.write_export(&mut y).unwrap();
    assert_eq!(x, y);
    assert!(
        b.repair_port_report()["stats"]["ambiguous_bucket"]
            .as_u64()
            .unwrap()
            > 0
    );
}

#[test]
fn container_keys_keep_recursive_repair() {
    let source = r#"
(datatype E (N i64))
(sort Es (Set E))
(constructor Bag (Es) E)
(ruleset outputs) (ruleset keys)
(rule ((= a (N 1)) (= b (N 2))) ((union (Bag (set-of a)) b)) :ruleset outputs)
(rule ((= a (N 1)) (= b (N 2))) ((union a b)) :ruleset keys)
(Bag (set-of (N 1))) (Bag (set-of (N 2)))
(run-schedule (seq (run outputs) (run keys)))
(check (= (Bag (set-of (N 1))) (Bag (set-of (N 2)))))
"#;
    let p = program(source);
    let table = p.tables.iter().position(|t| t.name == "Bag").unwrap();
    let (_, b) = compare(p);
    assert!(b.graph.repair_port_report()["plan"]["key_eq_columns"][table].is_null());
    assert!(
        b.graph.repair_port_report()["stats"]["unsupported"]
            .as_u64()
            .unwrap()
            > 0
    );
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, source).unwrap();
}
