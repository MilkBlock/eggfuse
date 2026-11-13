use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use std::collections::BTreeSet;

fn executor(source: &str, grain: Option<usize>) -> Executor {
    let core = eggfuse_bake::device_frontend::core("parallel-guards", source).unwrap();
    let program = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut graph = Graph::new_with_scoped_completion(program).unwrap();
    if let Some(grain) = grain {
        graph.use_parallel_port_guards(2, grain).unwrap();
    }
    let mut executor = Executor::new(graph, false);
    executor.use_pure_epochs().unwrap();
    executor
}

fn source(second_union: bool, recreate: bool) -> String {
    source_with_count(second_union, recreate, 12)
}

fn source_with_count(second_union: bool, recreate: bool, count: usize) -> String {
    let mut source = String::from(
        r#"
(datatype E (R i64) (F E E i64) (H E E i64) (G E) (Seen E))
(ruleset seed) (ruleset first) (ruleset second) (ruleset observe)
(ruleset erase) (ruleset recreate)
(R 0) (R 1) (R 2) (R 3)
(rule ((= x (R 0)) (= y (R 1))) ((union x y)) :ruleset first)
(rule ((= x (R 2)) (= y (R 3))) ((union x y)) :ruleset second)
(rule ((= x (G y))) ((Seen x)) :ruleset observe)
(rule ((= x (F (R 0) (R 2) 0))) ((delete (G x))) :ruleset erase)
(rule ((= x (F (R 0) (R 2) 0))) ((G x)) :ruleset recreate)
"#,
    );
    // Each small shared shape stays within the compiler's complete-site bound.
    // Scalar variants share equality inputs and therefore create foreign peers.
    for i in 0..count {
        source.push_str(&format!(
            r#"
(rule ((= x (R 0)) (= y (R 1)) (= a (R 2)) (= b (R 3)))
      ((G (F x a {i})) (G (F y b {i})) (H x a {i}) (H y b {i})) :ruleset seed)
"#
        ));
    }
    source.push_str("(run-schedule (seq (run seed) (run first)");
    if second_union {
        source.push_str(" (run second)");
    }
    if recreate {
        source.push_str(" (run erase) (run recreate)");
    }
    source.push_str(" (run observe)))\n");
    source
}

fn compare(serial: &Executor, parallel: &Executor) {
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
    assert_eq!(serial.graph.pending_completion_tasks(), 0);
    assert_eq!(parallel.graph.pending_completion_tasks(), 0);
}

#[test]
fn parallel_completion_preserves_partial_equalities_and_ordered_cascades() {
    for (second, recreate) in [(false, false), (true, false), (true, true)] {
        let source = source(second, recreate);
        let mut serial = executor(&source, None);
        let mut parallel = executor(&source, Some(1));
        serial.execute().unwrap();
        parallel.execute().unwrap();
        compare(&serial, &parallel);
        for name in ["F", "H", "G"] {
            let table = parallel
                .graph
                .program
                .tables
                .iter()
                .position(|t| t.name == name)
                .unwrap();
            assert_eq!(
                parallel.graph.witness_count(table),
                if second { 12 } else { 24 }
            );
        }
        let report = parallel.graph.parallel_guard_report();
        assert!(report["stats"]["rounds"].as_u64().unwrap() > 0, "{report}");
        assert_eq!(report["pool_builds"], 1);
        let count = report["worker_candidates"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_u64().unwrap())
            .sum::<u64>();
        assert_eq!(
            count,
            report["stats"]["prepared_candidates"].as_u64().unwrap()
        );
        assert_eq!(
            report["stats"]["prepared_candidates"],
            report["stats"]["collected_results"]
        );
        assert_eq!(report["stats"]["scratch_allocations"], 0);
        // Every extra port/key read must be exposed as speculative work.
        let before = serial.graph.stable_port_report();
        let after = parallel.graph.stable_port_report();
        for (counter, extra) in [
            ("port_reads", "port_reads"),
            ("root_resolutions", "port_reads"),
            ("key_field_comparisons", "key_fields"),
        ] {
            assert_eq!(
                after["stats"][counter].as_u64().unwrap(),
                before["stats"][counter].as_u64().unwrap()
                    + report["stats"]["speculative_guard_work"][extra]
                        .as_u64()
                        .unwrap(),
                "{counter}"
            );
        }
    }
}

#[test]
fn small_candidate_batches_keep_the_serial_path_and_work_counts() {
    let source = source(true, false);
    let mut serial = executor(&source, None);
    let mut configured = executor(&source, Some(4096));
    serial.execute().unwrap();
    configured.execute().unwrap();
    compare(&serial, &configured);
    let before = serial.graph.stable_port_report();
    let after = configured.graph.stable_port_report();
    assert_eq!(before["stats"], after["stats"]);
    assert_eq!(before["local_conditions"], after["local_conditions"]);
    let report = configured.graph.parallel_guard_report();
    assert!(report["stats"]["candidate_batches"].as_u64().unwrap() > 0);
    assert_eq!(report["stats"]["rounds"], 0);
    assert_eq!(report["stats"]["prepared_candidates"], 0);
}

#[test]
fn wide_rounds_preserve_results_and_charge_descriptor_storage() {
    let source = source_with_count(true, false, 20);
    let mut serial = executor(&source, None);
    let mut parallel = executor(&source, Some(17));
    serial.execute().unwrap();
    parallel.execute().unwrap();
    compare(&serial, &parallel);
    let report = parallel.graph.parallel_guard_report();
    assert!(
        report["stats"]["scratch_allocations"].as_u64().unwrap() > 0,
        "{report}"
    );
    assert!(report["stats"]["scratch_bytes_requested"].as_u64().unwrap() > 0);
}

#[test]
fn invalid_pool_configuration_does_not_change_graph_and_pool_is_reused() {
    let mut executor = executor(&source(false, false), None);
    let before = executor.graph.stable_port_report();
    for (workers, grain) in [(0, 1), (1, 1), (2, 0), (usize::MAX, 2)] {
        assert!(
            executor
                .graph
                .use_parallel_port_guards(workers, grain)
                .is_err()
        );
        assert_eq!(executor.graph.stable_port_report(), before);
    }
    executor.graph.use_parallel_port_guards(2, 1).unwrap();
    executor.graph.use_parallel_port_guards(2, 1).unwrap();
    assert!(executor.graph.use_parallel_port_guards(3, 1).is_err());
    assert_eq!(executor.graph.parallel_guard_report()["pool_builds"], 1);
}

#[test]
#[cfg(feature="sparse-cells")]
fn projected_fields_survive_worker_guards_and_recreated_facts() {
    let source=source(true,true);
    let mut serial=executor(&source,None);
    let mut parallel=executor(&source,Some(1));
    parallel.graph.use_template_stable_fields().unwrap();
    serial.execute().unwrap();parallel.execute().unwrap();
    compare(&serial,&parallel);
    assert!(parallel.graph.parallel_guard_report()["stats"]["rounds"].as_u64().unwrap()>0);
    let report=parallel.graph.stable_port_report();
    assert!(report["template_projected_nodes"].as_u64().unwrap()>0);
    assert!(report["stats"]["template_node_projections"].as_u64().unwrap()>0);
}
