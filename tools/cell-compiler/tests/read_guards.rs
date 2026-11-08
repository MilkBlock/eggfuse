use eggfuse_cell_runtime::{
    compiler,
    executor::Executor,
    graph::{Dependency, Graph},
    program::Program,
    value::Value,
};
use std::collections::BTreeSet;

fn graph() -> Graph {
    let source = r#"
(datatype E (N i64) (F E E String))
(N 0) (N 1) (F (N 0) (N 1) "label")
(ruleset empty) (run-schedule (run empty))
"#;
    let core = eggfuse_bake::device_frontend::core("read-guards", source).unwrap();
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut e = Executor::new(Graph::new_with_local_congruence(p).unwrap(), false);
    e.execute().unwrap();
    e.graph
}

#[test]
fn live_graph_guards_run_on_workers_without_mutating_graph_or_counters() {
    let g = graph();
    let table = g.program.tables.iter().position(|t| t.name == "F").unwrap();
    let row = g.row(g.witnesses(table)[0]).unwrap().unwrap();
    let Dependency::Fact(fact) = row.witness else {
        panic!()
    };
    let key = &row.values[..row.values.len() - 1];
    let right = g.stable_key_guard(fact, table, key).unwrap().unwrap();
    let wrong_operator = g.stable_key_guard(fact, table + 1, key).unwrap().unwrap();
    let mut wrong_key = key.to_vec();
    wrong_key[2] = Value::Text("different".to_owned().into());
    let wrong_scalar = g
        .stable_key_guard(fact, table, &wrong_key)
        .unwrap()
        .unwrap();
    let before = g.stable_port_report();
    let barrier = std::sync::Barrier::new(4);
    let answers = std::thread::scope(|scope| {
        let mut workers = Vec::new();
        for guard in [&right, &wrong_operator, &wrong_scalar] {
            let barrier = &barrier;
            workers.push(scope.spawn(move || {
                barrier.wait();
                guard.evaluate()
            }));
        }
        barrier.wait();
        workers
            .into_iter()
            .map(|w| w.join().unwrap())
            .collect::<Vec<_>>()
    });
    assert_eq!(
        answers
            .iter()
            .map(|(r, _)| *r.as_ref().unwrap())
            .collect::<Vec<_>>(),
        [true, false, false]
    );
    assert_eq!((answers[0].1.key_fields, answers[0].1.port_reads), (3, 2));
    assert_eq!((answers[1].1.key_fields, answers[1].1.port_reads), (0, 0));
    assert_eq!(g.stable_port_report(), before);
}

#[test]
fn a_new_read_borrow_observes_aliases_and_rejects_retired_instances() {
    let mut g = graph();
    let table = g.program.tables.iter().position(|t| t.name == "F").unwrap();
    let row = g.row(g.witnesses(table)[0]).unwrap().unwrap();
    let Dependency::Fact(fact) = row.witness else {
        panic!()
    };
    let port = g.fact_port(fact, 1).unwrap();
    let before = g.stable_port_reader().unwrap().read_port(port).unwrap();
    g.enqueue_union(row.values[0].clone(), row.values[1].clone())
        .unwrap();
    g.repair().unwrap();
    let after = g.stable_port_reader().unwrap().read_port(port).unwrap();
    assert_ne!(before, after);
    assert_eq!(after, row.values[0]);
    let key = [row.values[0].clone(), after, row.values[2].clone()];
    assert!(
        g.stable_key_guard(fact, table, &key)
            .unwrap()
            .unwrap()
            .evaluate()
            .0
            .unwrap()
    );
    g.hide(table, &key, false).unwrap();
    assert!(
        g.stable_key_guard(fact, table, &key)
            .unwrap()
            .unwrap()
            .evaluate()
            .0
            .unwrap()
    );
    g.hide(table, &key, true).unwrap();
    assert!(g.stable_key_guard(fact, table, &key).unwrap().is_none());
    assert!(g.stable_port_reader().unwrap().read_port(port).is_err());
}
