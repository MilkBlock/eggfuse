use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use std::collections::BTreeSet;

fn executors(source: &str, workers: usize, limit: usize) -> (Executor, Executor) {
    let core = eggfuse_bake::device_frontend::core("completion-batches", source).unwrap();
    let compiled = compiler::compile(core, &BTreeSet::new()).unwrap();
    let serial =
        Graph::new_with_scoped_completion(Program::parse(compiled.clone()).unwrap()).unwrap();
    let mut parallel =
        Graph::new_with_scoped_completion(Program::parse(compiled).unwrap()).unwrap();
    parallel.use_parallel_port_guards(workers, 32).unwrap();
    parallel.use_completion_read_batches(limit).unwrap();
    (Executor::new(serial, false), Executor::new(parallel, false))
}
fn compare(source: &str, workers: usize, limit: usize) -> serde_json::Value {
    let (mut serial, mut parallel) = executors(source, workers, limit);
    serial.execute().unwrap();
    parallel.execute().unwrap();
    assert_eq!(
        serial.graph.export().unwrap(),
        parallel.graph.export().unwrap()
    );
    assert_eq!(serial.steps.len(), parallel.steps.len());
    for (a, b) in serial.steps.iter().zip(&parallel.steps) {
        for key in [
            "ordinal",
            "ruleset",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(a[key], b[key], "{key}");
        }
    }
    assert_eq!(parallel.graph.pending_completion_tasks(), 0);
    let report = parallel.graph.completion_batch_report();
    assert!(
        report["stats"]["dispatches"].as_u64().unwrap() > 0,
        "{report}"
    );
    assert_eq!(
        report["stats"]["prepared_tasks"].as_u64().unwrap(),
        report["stats"]["committed_tasks"].as_u64().unwrap()
            + report["stats"]["unused_tasks"].as_u64().unwrap()
    );
    assert_eq!(
        report["worker_tasks"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_u64().unwrap())
            .sum::<u64>(),
        report["stats"]["prepared_tasks"].as_u64().unwrap()
    );
    report
}
fn siblings(anchor_last: bool, anchor: bool, chain: bool) -> String {
    let mut src = String::from("(datatype E (N i64) (F E i64) (G E))\n(N 0) (N 1) (N 2)\n");
    let roots = if anchor_last {
        vec![1, 2, 0]
    } else if anchor {
        vec![0, 1, 2]
    } else {
        vec![1, 2]
    };
    for root in roots {
        for i in 0..6 {
            let term = format!("(F (N {root}) {i})");
            src.push_str(&if chain {
                format!("(G {term})\n")
            } else {
                format!("{term}\n")
            });
        }
    }
    src.push_str(
        r#"
(ruleset merge)
(rule ((= a (N 0)) (= b (N 1)) (= c (N 2))) ((union a b) (union a c)) :ruleset merge)
(run-schedule (run merge))
"#,
    );
    src
}

#[test]
fn same_sort_tasks_reuse_reads_across_result_unions() {
    let source = siblings(false, true, false);
    for (workers, limit) in [(2, 16), (4, 4)] {
        let report = compare(&source, workers, limit);
        assert!(
            report["stats"]["reused_after_union"].as_u64().unwrap() > 0,
            "{report}"
        );
        assert_eq!(report["stats"]["unused_tasks"], 0);
    }
}

#[test]
fn direct_worker_reads_skip_preparation_and_unused_candidates() {
    let report = compare(&siblings(false, true, false), 2, 16);
    let stats = &report["stats"];
    assert_eq!(stats["prepared_candidates"], 0);
    assert!(stats["candidate_fact_lookups"].as_u64().unwrap() > 0);
    assert_eq!(stats["candidate_fact_lookups"], stats["guard_candidates"]);
    assert!(
        stats["candidate_fact_lookups"].as_u64().unwrap()
            < stats["candidate_positions"].as_u64().unwrap(),
        "{report}"
    );
    assert!(
        stats["pending_probes"].as_u64().unwrap()
            <= stats["candidate_fact_lookups"].as_u64().unwrap()
    );
}

#[test]
fn pending_peers_can_become_survivors_and_retired_peers_are_rejected() {
    compare(&siblings(false, false, false), 2, 16);
    let retired = compare(&siblings(true, true, false), 2, 16);
    assert!(
        retired["stats"]["selection_dead_skips"].as_u64().unwrap() > 0,
        "{retired}"
    );
}

#[test]
fn a_derived_input_alias_invalidates_prefetched_conditions() {
    let source = r#"
(datatype E (N i64) (F E i64) (H E E))
(N 0) (N 1) (N 2) (N 3)
(F (N 0) 0) (F (N 1) 0)
(H (F (N 0) 0) (N 2))
(H (F (N 1) 0) (N 3))
(ruleset merge)
(rule ((= a (N 0)) (= b (N 1)) (= c (N 2)) (= d (N 3)))
      ((union a b) (union c d)) :ruleset merge)
(run-schedule (run merge))
(check (= (H (F (N 0) 0) (N 2)) (H (F (N 1) 0) (N 3))))
"#;
    let report = compare(source, 2, 16);
    assert!(
        report["stats"]["conflicting_unions"].as_u64().unwrap() > 0,
        "{report}"
    );
    assert!(report["stats"]["unused_tasks"].as_u64().unwrap() > 0);
}

#[test]
fn an_absorbing_input_class_is_checked_even_when_its_root_number_survives() {
    let source = r#"
(datatype E (N i64) (F E i64) (H E E))
(N 0) (N 1) (N 2) (N 3)
(F (N 0) 0) (F (N 1) 0)
(H (F (N 0) 0) (N 3))
(H (F (N 1) 0) (N 2))
(ruleset merge)
(rule ((= a (N 0)) (= b (N 1)) (= c (N 2)) (= d (N 3)))
      ((union a b) (union c d)) :ruleset merge)
(run-schedule (run merge))
"#;
    let report = compare(source, 2, 16);
    assert!(
        report["stats"]["conflicting_unions"].as_u64().unwrap() > 0,
        "{report}"
    );
}

fn earlier_child(dependent: bool) -> serde_json::Value {
    use eggfuse_cell_runtime::value::Value;
    let source = "(datatype E (N i64) (F E i64) (G E) (H E E))\n(N 0) (N 1) (N 10) (N 11) (N 2) (N 3)\n(ruleset empty) (run-schedule (run empty))";
    let (mut serial, mut parallel) = executors(source, 2, 16);
    for executor in [&mut serial, &mut parallel] {
        executor.execute().unwrap();
        let graph = &mut executor.graph;
        let table = |name: &str| {
            graph
                .program
                .tables
                .iter()
                .position(|t| t.name == name)
                .unwrap()
        };
        let (n, f, g, h) = (table("N"), table("F"), table("G"), table("H"));
        let roots = [0, 1, 10, 11, 2, 3].map(|i| {
            graph
                .lookup(n, &[Value::Int(i)])
                .unwrap()
                .unwrap()
                .values
                .last()
                .unwrap()
                .clone()
        });
        // This child predates its eventual F producer; source aliases attach
        // it to that producer without changing the child's FactRef.
        let left = dependent.then(|| graph.dynamic_construct(g, vec![roots[2].clone()]).unwrap());
        let right = graph.dynamic_construct(g, vec![roots[3].clone()]).unwrap();
        for i in 0..6 {
            let a = graph
                .dynamic_construct(f, vec![roots[0].clone(), Value::Int(i)])
                .unwrap();
            let b = graph
                .dynamic_construct(f, vec![roots[1].clone(), Value::Int(i)])
                .unwrap();
            if i == 0 {
                graph.enqueue_union(a, roots[2].clone()).unwrap();
                graph.enqueue_union(b, roots[3].clone()).unwrap();
            }
        }
        if let Some(left) = left {
            graph
                .dynamic_construct(h, vec![left, roots[4].clone()])
                .unwrap();
            graph
                .dynamic_construct(h, vec![right, roots[5].clone()])
                .unwrap();
        }
        graph.repair().unwrap();
        graph
            .enqueue_union(roots[0].clone(), roots[1].clone())
            .unwrap();
        if dependent {
            graph
                .enqueue_union(roots[4].clone(), roots[5].clone())
                .unwrap();
        }
        graph.repair().unwrap();
        if dependent {
            assert_eq!(graph.witness_count(h), 1);
        }
    }
    assert_eq!(
        serial.graph.export().unwrap(),
        parallel.graph.export().unwrap()
    );
    parallel.graph.completion_batch_report()
}

#[test]
fn a_new_earlier_child_task_preserves_independent_prefetched_reads() {
    let report = earlier_child(false);
    assert!(
        report["stats"]["bridged_tasks"].as_u64().unwrap() > 0,
        "{report}"
    );
}

#[test]
fn a_bridged_child_union_invalidates_its_dependent_prefetched_suffix() {
    let report = earlier_child(true);
    assert!(
        report["stats"]["bridged_tasks"].as_u64().unwrap() > 0,
        "{report}"
    );
    assert!(
        report["stats"]["conflicting_unions"].as_u64().unwrap() > 0,
        "{report}"
    );
    assert!(
        report["stats"]["unused_tasks"].as_u64().unwrap() > 0,
        "{report}"
    );
}

#[test]
fn batch_configuration_is_bounded_and_requires_a_pool() {
    let core = eggfuse_bake::device_frontend::core(
        "batch-options",
        "(datatype E (N i64)) (N 0) (ruleset empty) (run-schedule (run empty))",
    )
    .unwrap();
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut graph = Graph::new_with_scoped_completion(p).unwrap();
    assert!(graph.use_completion_read_batches(16).is_err());
    graph.use_parallel_port_guards(2, 32).unwrap();
    for limit in [0, 1, 65, usize::MAX] {
        assert!(graph.use_completion_read_batches(limit).is_err());
    }
    graph.use_completion_read_batches(16).unwrap();
    graph.use_completion_read_batches(16).unwrap();
    assert!(graph.use_completion_read_batches(8).is_err());
}

#[test]
fn selective_batches_leave_unrelated_same_sort_completion_pending() {
    let source = r#"
(datatype E (Na i64) (Nb i64) (Fa E i64) (Fb E i64) (SeenA E) (SeenB E))
(ruleset seed) (ruleset a) (ruleset b)
(Na 0) (Na 1) (Nb 0) (Nb 1)
(rule ((= x (Na 0)) (= y (Na 1)) (= u (Nb 0)) (= v (Nb 1)))
      ((Fa x 0) (Fa y 0) (Fa x 1) (Fa y 1)
       (Fb u 0) (Fb v 0) (Fb u 1) (Fb v 1)
       (union x y) (union u v)) :ruleset seed)
(rule ((= x (Fb y i))) ((SeenB x)) :ruleset b)
(rule ((= x (Fa y i))) ((SeenA x)) :ruleset a)
(run-schedule (seq (run seed) (run b) (run a)))
"#;
    let (mut serial, mut parallel) = executors(source, 2, 16);
    serial.use_port_scopes().unwrap();
    parallel.use_port_scopes().unwrap();
    serial.execute().unwrap();
    parallel.execute_until(Some(2)).unwrap();
    if parallel.scoped_execution_report()["global_observer"] == false {
        assert!(parallel.graph.pending_completion_tasks() > 0);
        let a = parallel
            .graph
            .program
            .tables
            .iter()
            .position(|t| t.name == "Fa")
            .unwrap();
        let b = parallel
            .graph
            .program
            .tables
            .iter()
            .position(|t| t.name == "SeenB")
            .unwrap();
        assert_eq!(parallel.graph.witness_count(a), 4);
        assert_eq!(parallel.graph.witness_count(b), 2);
        assert!(
            parallel.graph.completion_batch_report()["stats"]["committed_tasks"]
                .as_u64()
                .unwrap()
                > 0
        );
    }
    parallel.execute().unwrap();
    assert_eq!(
        serial.graph.export().unwrap(),
        parallel.graph.export().unwrap()
    );
}

#[test]
fn partial_multi_input_guards_and_recreated_facts_keep_their_lifetimes() {
    let source = r#"
(datatype E (N i64) (F E E i64))
(N 0) (N 1) (N 2) (N 3)
(F (N 0) (N 2) 0) (F (N 1) (N 3) 0)
(F (N 0) (N 2) 1) (F (N 1) (N 3) 1)
(ruleset first) (ruleset second) (ruleset erase) (ruleset recreate)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset first)
(rule ((= a (N 2)) (= b (N 3))) ((union a b)) :ruleset second)
(rule ((= x (N 0)) (= y (N 2))) ((delete (F x y 0))) :ruleset erase)
(rule ((= x (N 0)) (= y (N 2))) ((F x y 0)) :ruleset recreate)
(run-schedule (seq (run first) (run second) (run erase) (run recreate)))
"#;
    let (mut serial, mut parallel) = executors(source, 2, 16);
    parallel.execute_until(Some(1)).unwrap();
    let f = parallel
        .graph
        .program
        .tables
        .iter()
        .position(|t| t.name == "F")
        .unwrap();
    assert_eq!(parallel.graph.witness_count(f), 4);
    parallel.execute().unwrap();
    serial.execute().unwrap();
    assert_eq!(
        serial.graph.export().unwrap(),
        parallel.graph.export().unwrap()
    );
    assert_eq!(parallel.graph.witness_count(f), 2);
    assert!(
        parallel.graph.completion_batch_report()["stats"]["dispatches"]
            .as_u64()
            .unwrap()
            >= 2
    );
}
