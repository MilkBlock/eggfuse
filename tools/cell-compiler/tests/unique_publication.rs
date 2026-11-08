use eggfuse_cell_runtime::{
    compiler, executor::Executor, graph::Graph, program::Program, value::Value,
};
use std::collections::BTreeSet;

fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("unique-publication", source).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn executor(p: Program, unique: bool) -> Executor {
    let mut e = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    e.use_pure_epochs().unwrap();
    if unique {
        e.use_unique_port_publication().unwrap();
    }
    e
}
fn compare(a: &Executor, b: &Executor) {
    assert_eq!(a.graph.export().unwrap(), b.graph.export().unwrap());
    assert_eq!(a.steps.len(), b.steps.len());
    for (a, b) in a.steps.iter().zip(&b.steps) {
        for key in [
            "ordinal",
            "ruleset",
            "path",
            "iterations",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(a[key], b[key], "{key}");
        }
    }
}
fn table(e: &Executor, name: &str) -> usize {
    e.graph
        .program
        .tables
        .iter()
        .position(|t| t.name == name)
        .unwrap()
}
fn proof(e: &Executor) -> serde_json::Value {
    e.graph.stable_port_report()["unique_publication"]["stats"].clone()
}
const UNIQUE: &str = r#"
(datatype E (N i64) (F E) (G E) (Seen E))
(ruleset a) (ruleset observe)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (F y))) ((Seen x)) :ruleset observe)
(N 0) (N 1) (F (N 1)) (G (N 0))
(run-schedule (seq (run a) (run observe)))
"#;

#[test]
fn a_unique_input_publishes_without_enqueuing_a_key_obligation() {
    let p = program(UNIQUE);
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    old.execute_until(Some(1)).unwrap();
    new.execute_until(Some(1)).unwrap();
    if new.scoped_execution_report()["global_observer"] == false {
        assert_eq!(old.graph.pending_completion_tasks(), 1);
        assert_eq!(new.graph.pending_completion_tasks(), 0);
    }
    assert_eq!(proof(&new)["accepted"], 1);
    assert_eq!(
        new.graph.stable_port_report()["stats"]["equality_enqueues"],
        0
    );
    let checkpoint = serde_json::json!({"executor":new.scoped_execution_report(),"stable_ports":new.graph.stable_port_report(),"previous_pending":old.graph.pending_completion_tasks(),"current_pending":new.graph.pending_completion_tasks()});
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(new.graph.witness_count(table(&new, "Seen")), 1);
    if let Ok(path) = std::env::var("UNIQUE_PUBLICATION_EVIDENCE") {
        std::fs::write(
            path,
            serde_json::to_vec_pretty(&serde_json::json!({
                "scope":"standalone single-thread Cell CPU; direct uniqueness publication",
                "checkpoint":checkpoint,"exact_final_state_and_ordered_source_observations":true,
                "final_executor":new.scoped_execution_report(),"final_proof":proof(&new),
            }))
            .unwrap(),
        )
        .unwrap();
    }
}

#[test]
fn a_foreign_same_operator_peer_retains_congruence() {
    let source = UNIQUE.replace("(G (N 0))", "(F (N 0))");
    let p = program(&source);
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    old.execute_until(Some(1)).unwrap();
    new.execute_until(Some(1)).unwrap();
    assert_eq!(proof(&new)["accepted"], 0);
    assert!(proof(&new)["peer_rejections"].as_u64().unwrap() > 0);
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
    }
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(new.graph.witness_count(table(&new, "F")), 1);
}

#[test]
fn an_already_pending_peer_is_part_of_the_complete_input_domain() {
    let source = r#"
(datatype E (N i64) (F E E) (Seen E))
(ruleset a) (ruleset observe)
(rule ((= u (N 0)) (= v (N 1)) (= x (N 2)) (= y (N 3)))
      ((union x y) (union u v)) :ruleset a)
(rule ((= x (F u v))) ((Seen x)) :ruleset observe)
(N 0) (N 1) (N 2) (N 3)
(F (N 1) (N 2)) (F (N 1) (N 3))
(run-schedule (seq (run a) (run observe)))
"#;
    let p = program(source);
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    old.execute_until(Some(1)).unwrap();
    new.execute_until(Some(1)).unwrap();
    assert_eq!(proof(&new)["accepted"], 0);
    assert!(proof(&new)["pending_skips"].as_u64().unwrap() > 0);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(new.graph.witness_count(table(&new, "F")), 1);
}

#[test]
fn a_hidden_peer_still_prevents_unique_publication() {
    let source = UNIQUE
        .replace(
            "(ruleset a)",
            "(ruleset hide)\n(rule ((= x (N 0))) ((subsume (F x))) :ruleset hide)\n(ruleset a)",
        )
        .replace("(G (N 0))", "(F (N 0))")
        .replace("(seq (run a)", "(seq (run hide) (run a)");
    let p = program(&source);
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    old.execute_until(Some(2)).unwrap();
    new.execute_until(Some(2)).unwrap();
    assert_eq!(proof(&new)["accepted"], 0);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(new.graph.witness_count(table(&new, "Seen")), 0);
}

#[test]
fn repeated_key_notifications_preserve_the_snapshot_and_row_epoch() {
    let source = UNIQUE
        .replace("(F E)", "(F E E)")
        .replace(
            "(= y (N 1))) ((union x y))",
            "(= y (N 1)) (= z (N 2))) ((union x y) (union x z))",
        )
        .replace("(F y)", "(F y z)")
        .replace("(N 0) (N 1) (F (N 1))", "(N 0) (N 1) (N 2) (F (N 1) (N 2))");
    let p = program(&source);
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(proof(&new)["accepted"], 0);
    assert!(proof(&new)["batch_skips"].as_u64().unwrap() > 0);
    for witness in new.graph.witnesses(table(&new, "F")) {
        assert_eq!(new.graph.row(witness).unwrap().unwrap().epoch, 1);
    }
}

#[test]
fn deletion_and_recreation_do_not_leave_a_ghost_candidate() {
    let source = UNIQUE
        .replace(
            "(ruleset a)",
            r#"
(ruleset erase) (ruleset make) (ruleset b)
(rule ((= x (F y))) ((delete (F y))) :ruleset erase)
(rule ((= x (N 2))) ((F x)) :ruleset make)
(rule ((= x (N 0)) (= y (N 2))) ((union x y)) :ruleset b)
(ruleset a)"#,
        )
        .replace("(G (N 0))", "(G (N 0)) (N 2)")
        .replace(
            "(run a) (run observe)",
            "(run a) (run erase) (run make) (run b) (run observe)",
        );
    let p = program(&source);
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    assert!(proof(&new)["accepted"].as_u64().unwrap() >= 2);
    for witness in new.graph.witnesses(table(&new, "F")) {
        assert_eq!(new.graph.row(witness).unwrap().unwrap().epoch, 4);
    }
}

#[test]
fn an_older_union_cannot_backdate_a_new_unique_consumer() {
    let p = program("(datatype E (N i64) (F E) (G E)) (ruleset empty) (run-schedule (run empty))");
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    for e in [&mut old, &mut new] {
        e.execute().unwrap();
        let n = table(e, "N");
        let f = table(e, "F");
        let g = table(e, "G");
        let a = e.graph.dynamic_construct(n, vec![Value::Int(0)]).unwrap();
        let b = e.graph.dynamic_construct(n, vec![Value::Int(1)]).unwrap();
        e.graph.dynamic_construct(f, vec![a.clone()]).unwrap();
        let result = e.graph.dynamic_construct(f, vec![b.clone()]).unwrap();
        e.graph.epoch = 2;
        e.graph.enqueue_union(a, b).unwrap();
        e.graph.commit_scoped_unions().unwrap();
        assert!(e.graph.pending_completion_tasks() > 0);
        e.graph.epoch = 3;
        e.graph.dynamic_construct(g, vec![result]).unwrap();
        e.graph.repair().unwrap();
        for witness in e.graph.witnesses(g) {
            assert_eq!(e.graph.row(witness).unwrap().unwrap().epoch, 3);
        }
    }
    compare(&old, &new);
    assert_eq!(proof(&new)["accepted"], 1);
}

#[test]
fn a_large_input_domain_keeps_the_original_completion_path() {
    let mut source = UNIQUE
        .replace("(G E)", "(G E i64)")
        .replace("(G (N 0))", "");
    let at = source.find("(run-schedule").unwrap();
    let mut uses = String::new();
    for i in 0..90 {
        uses.push_str(&format!("(G (N 0) {i})\n"));
    }
    source.insert_str(at, &uses);
    let p = program(&source);
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    assert!(proof(&new)["budget_rejections"].as_u64().unwrap() > 0);
    assert_eq!(proof(&new)["accepted"], 0);
}

const ORDERED: &str = r#"
(datatype E (N i64) (F E i64))
(function record (i64) i64 :merge (+ (* old 10) new))
(ruleset a) (ruleset observe)
(rule ((= x (N 0)) (= y (N 1)) (= z (N 3))) ((union x y) (union x z)) :ruleset a)
(rule ((= y (F x i))) ((set (record 0) i)) :ruleset observe)
(N 0) (N 1) (N 3) (N 4)
(F (N 3) 1) (F (N 4) 2) (F (N 1) 1)
(set (record 0) 0)
(run-schedule (seq (run a) (run observe)))
"#;

#[test]
fn early_publication_preserves_survivor_order_for_ordered_merge_observations() {
    let p = program(ORDERED);
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn separate_source_epochs_preserve_ordered_merge_observations() {
    let source = ORDERED
        .replace("(ruleset a)", "(ruleset b) (ruleset a)")
        .replace(
            "((union x y) (union x z)) :ruleset a)",
            "((union x y)) :ruleset a)\n(rule ((= x (N 0)) (= z (N 3))) ((union x z)) :ruleset b)",
        )
        .replace("(run a) (run observe)", "(run a) (run b) (run observe)");
    let p = program(&source);
    let mut reference = Executor::new(Graph::new_with_scoped_completion(p.clone()).unwrap(), false);
    let mut old = executor(p.clone(), false);
    let mut new = executor(p, true);
    reference.execute().unwrap();
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&reference, &old);
    compare(&reference, &new);
}
