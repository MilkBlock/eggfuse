#![cfg(feature = "sparse-cells")]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
fn artifact(source: &str) -> serde_json::Value {
    let core = eggfuse_bake::device_frontend::core("cell-execution", source).unwrap();
    compiler::compile(core, &Default::default()).unwrap()
}
fn executor(source: &str, workers: usize) -> Executor {
    let program = Program::parse(artifact(source)).unwrap();
    let mut e = Executor::new(Graph::new_with_repair_ports(program).unwrap(), true);
    e.use_entry_publications().unwrap();
    if workers > 0 {
        e.use_query_workers(workers, 8).unwrap();
        #[cfg(feature = "parallel-residuals")]
        e.use_parallel_residuals().unwrap();
    }
    e
}
fn same(a: &Executor, b: &Executor) {
    assert_eq!(a.snapshots, b.snapshots, "every source Run state");
    assert_eq!(
        a.binding_audit, b.binding_audit,
        "input identity excludes prepared RHS slots"
    );
    assert_eq!(a.graph.export().unwrap(), b.graph.export().unwrap());
    assert_eq!(a.steps.len(), b.steps.len());
    for (a, b) in a.steps.iter().zip(&b.steps) {
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
}
fn initial() -> String {
    (0..64)
        .map(|i| format!("(Start (N {i})) (set (Input (N {i})) {i}) (set (Current (N {i})) 1)\n"))
        .collect()
}
const HEADER: &str = r#"
(datatype E (N i64) (Start E) (F E i64))
(function Input (E) i64 :merge new)
(function Current (E) i64 :merge new)
(function Out (E) i64 :merge new)
(ruleset step)
"#;

#[test]
fn worker_query_continues_into_owned_slots_and_keeps_run_snapshot() {
    let source = format!(
        r#"{HEADER}
(rule ((Start x) (= n (Input x))) ((set (Input x) 1000)) :ruleset step)
(rule ((Start x) (= n (Input x))) ((let a (+ n 1)) (let b (* a 2)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
(check (= (Input (N 2)) 1000) (= (Out (N 2)) 6))
(run-schedule (run step))
(check (= (Out (N 2)) 2002))
"#,
        initial()
    );
    egglog::EGraph::default()
        .parse_and_run_program(None, &source)
        .unwrap();
    let mut before = executor(&source, 0);
    before.execute().unwrap();
    for workers in [1, 2, 4] {
        let mut after = executor(&source, workers);
        after.execute().unwrap();
        same(&before, &after);
        let r = after.report();
        let work = &r["query_workers"]["stats"]["execution"];
        assert!(work["operations"].as_u64().unwrap() > 0, "{r}");
        assert!(
            after.graph.stats.prepared_rhs_operations > 0,
            "prepared work must remove RHS execution"
        );
        assert!(work["operations"].as_u64().unwrap() >= after.graph.stats.prepared_rhs_operations);
        assert_eq!(
            work["frame_growths"], 0,
            "Bake reserves local results when query slots are allocated"
        );
        if workers > 1 {
            assert!(
                r["query_workers"]["stats"]["worker_local_operations"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_u64().unwrap())
                    .sum::<u64>()
                    > 0
            );
        }
    }
}

#[test]
fn constructor_boundary_consumes_prepared_values_without_replay() {
    let source = format!(
        r#"{HEADER}
(rule ((Start x)) ((set (Current x) 9)) :ruleset step)
(rule ((Start x) (= n (Input x)))
 ((let a (+ n 1)) (F x a) (let b (+ a 9)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
(check (= (Out (N 2)) 12) (F (N 2) 3))
"#,
        initial()
    );
    egglog::EGraph::default()
        .parse_and_run_program(None, &source)
        .unwrap();
    let mut a = executor(&source, 0);
    a.execute().unwrap();
    let mut b = executor(&source, 4);
    b.execute().unwrap();
    same(&a, &b);
    assert!(b.graph.stats.prepared_rhs_operations > 0);
    let plan = artifact(&source)["cell_execution"].to_string();
    assert!(plan.contains("Constructor") && plan.contains("Write"));
}

#[test]
fn speculative_failure_stays_at_original_rhs_position() {
    let source = format!(
        r#"{HEADER}
(rule ((Start x)) ((set (Current x) 9)) :ruleset step)
(rule ((Start x) (= n (Input x)))
 ((let a (+ n 1)) (let b (/ a 0)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
"#,
        initial()
    );
    let mut a = executor(&source, 0);
    let ea = a.execute().unwrap_err();
    let mut b = executor(&source, 4);
    let eb = b.execute().unwrap_err();
    assert_eq!(ea, eb);
    assert!(ea.contains("RHS primitive failed"), "{ea}");
    assert_eq!(
        a.graph.export().unwrap(),
        b.graph.export().unwrap(),
        "all and only earlier effects survive"
    );
    assert!(
        b.report()["query_workers"]["stats"]["execution"]["deferred_failures"]
            .as_u64()
            .unwrap()
            > 0
    );
}

#[test]
fn loader_reconstructs_dependency_cuts_from_source() {
    let source = format!(
        r#"{HEADER}
(rule ((Start x) (= n (Input x))) ((let a (+ n 1)) (set (Out x) a)) :ruleset step)
{} (run-schedule (run step))"#,
        initial()
    );
    let mut encoded = artifact(&source);
    assert_eq!(
        encoded["cell_execution"]["schema"],
        "cell-execution-boundaries/v1"
    );
    Program::parse(encoded.clone()).unwrap();
    encoded["cell_execution"]["rules"][0]["segments"][0]["end"] = serde_json::json!(99999);
    assert!(
        Program::parse(encoded)
            .err()
            .unwrap()
            .contains("execution boundaries")
    );
}

#[test]
fn real_publication_preserves_each_run_through_foreign_reuse_union_and_recreation() {
    let source = format!(
        r#"{HEADER}
(datatype Gated (Gate E))
(ruleset make) (ruleset consume) (ruleset publish) (ruleset join) (ruleset remove) (ruleset again)
(rule ((Start x)) ((Gate x)) :ruleset make)
(rule ((Gate x) (= n (Input x))) ((let a (+ n 1)) (F x a)) :ruleset consume)
(rule ((= f (F x n))) ((set (Out x) n)) :ruleset publish)
(rule () ((union (N 0) (N 1))) :ruleset join)
(rule () ((delete (F (N 3) 4))) :ruleset remove)
(rule () ((set (Input (N 3)) 9)) :ruleset again)
{} (F (N 0) 1)
(run-schedule (seq (run make) (run consume) (run publish) (run join)
 (run consume) (run publish) (run remove) (run again) (run consume) (run publish)))
(check (= (Out (N 3)) 10))
"#,
        initial()
    );
    egglog::EGraph::default()
        .parse_and_run_program(None, &source)
        .unwrap();
    let create = |workers| {
        let mut e = Executor::new(
            Graph::new_with_repair_ports(Program::parse(artifact(&source)).unwrap()).unwrap(),
            false,
        );
        e.use_entry_publications().unwrap();
        if workers > 0 {
            e.use_query_workers(workers, 8).unwrap();
            #[cfg(feature = "parallel-residuals")]
            e.use_parallel_residuals().unwrap();
        }
        e
    };
    let mut a = create(0);
    let mut b = create(4);
    for step in 1..=10 {
        a.execute_until(Some(step)).unwrap();
        b.execute_until(Some(step)).unwrap();
        assert_eq!(a.steps.len(), step);
        assert_eq!(b.steps.len(), step);
        assert_eq!(
            a.graph.export().unwrap(),
            b.graph.export().unwrap(),
            "real publication after Run {step}"
        );
        for key in ["epoch", "logical_matches", "executed_bindings", "changed"] {
            assert_eq!(a.steps[step - 1][key], b.steps[step - 1][key]);
        }
    }
    a.execute().unwrap();
    b.execute().unwrap();
    assert!(b.graph.stats.prepared_rhs_operations > 0);
    assert!(
        b.report()["entry_schedule"]["stats"]["entry_publication_writes"]
            .as_u64()
            .unwrap()
            > 0,
        "this test must exercise actual owned Entry publication"
    );
}
