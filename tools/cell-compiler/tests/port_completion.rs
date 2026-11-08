use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use std::collections::BTreeSet;

fn program(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("port-completion", src).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn table(e: &Executor, name: &str) -> usize {
    e.graph
        .program
        .tables
        .iter()
        .position(|t| t.name == name)
        .unwrap()
}
fn executor(src: &str, ports: bool) -> Executor {
    let mut e = Executor::new(
        Graph::new_with_scoped_completion(program(src)).unwrap(),
        false,
    );
    if ports {
        e.use_port_scopes().unwrap();
    }
    e
}
fn compare(reference: &Executor, trial: &Executor) {
    assert_eq!(
        reference.graph.export().unwrap(),
        trial.graph.export().unwrap()
    );
    assert_eq!(reference.steps.len(), trial.steps.len());
    for (a, b) in reference.steps.iter().zip(&trial.steps) {
        for k in [
            "ordinal",
            "ruleset",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(a[k], b[k], "{k}");
        }
    }
}
const SAME_SORT: &str = r#"
(datatype E (Na i64) (Nb i64) (Context i64)
            (Fa E E) (Ga E) (Fb E E) (Gb E) (SeenA E) (SeenB E))
(function score (E) i64 :merge (min old new))
(ruleset a) (ruleset b) (ruleset consume-b) (ruleset consume-a)
(rule ((= x (Na 0)) (= y (Na 1)) (= c (Context 0)))
      ((Ga (Fa x c)) (Ga (Fa y c)) (union x y)) :ruleset a)
(rule ((= x (Nb 0)) (= c (Context 0))) ((Gb (Fb x c))) :ruleset b)
(rule ((= x (Gb y))) ((SeenB x)) :ruleset consume-b)
(rule ((= x (Ga y))) ((SeenA x)) :ruleset consume-a)
(Na 0) (Na 1) (Nb 0) (Context 0)
(set (score (Nb 0)) 7)
(run-schedule (seq (run a) (run b) (run consume-b) (run consume-a)))
"#;

#[test]
fn same_sort_and_shared_context_do_not_force_unrelated_cells_to_wait() {
    let mut old = executor(SAME_SORT, false);
    let mut new = executor(SAME_SORT, true);
    old.execute().unwrap();
    new.execute_until(Some(1)).unwrap();
    let global = new.scoped_execution_report()["global_observer"] == true;
    assert_eq!(
        new.graph.scoped_completion_report()["plan"]["deferrable_tables"],
        0
    );
    if !global {
        assert!(new.graph.pending_completion_tasks() > 0);
    }
    new.execute_until(Some(3)).unwrap();
    assert_eq!(new.graph.witness_count(table(&new, "SeenB")), 1);
    if !global {
        assert!(new.graph.pending_completion_tasks() > 0);
        assert_eq!(
            new.scoped_execution_report()["stats"]["runs_with_unrelated_pending"],
            2
        );
    }
    let checkpoint = serde_json::json!({"executor":new.scoped_execution_report(),
        "graph":new.graph.scoped_completion_report(),"ports":new.graph.port_completion_report(),
        "seen_b_facts":new.graph.witness_count(table(&new,"SeenB"))});
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(new.graph.pending_completion_tasks(), 0);
    if let Ok(path) = std::env::var("PORT_COMPLETION_EVIDENCE") {
        std::fs::write(path, serde_json::to_vec_pretty(&serde_json::json!({
            "scope":"standalone single-thread Cell CPU; same equality sort, shared context input, unrelated mutable boundary",
            "checkpoint":checkpoint,"final_ports":new.graph.port_completion_report(),
            "final_executor":new.scoped_execution_report(),"exact_final_state_and_ordered_bindings":true,
            "same_table_independence":false,"parallel_or_timing_claim":false,
        })).unwrap()).unwrap();
    }
}

#[test]
fn pending_foreign_alias_and_mutable_consumer_keep_the_dependency_live() {
    let source = SAME_SORT.replace(
        "(union x y)) :ruleset a)",
        "(union (Fa x c) (Nb 0)) (union x y)) :ruleset a)",
    );
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(1)).unwrap();
    // A's result can now reach score's key; the ordered mutable effect is eager.
    assert_eq!(new.graph.pending_completion_tasks(), 0);
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn same_sort_guard_and_source_check_wait_for_future_result_aliases() {
    let source = SAME_SORT.replace(
        "(run-schedule (seq (run a) (run b) (run consume-b) (run consume-a)))",
        r#"
(datatype Flag (Bad))
(ruleset guard)
(rule ((= x (Ga (Fa (Na 0) (Context 0))))
       (= y (Ga (Fa (Na 1) (Context 0)))) (!= x y)) ((Bad)) :ruleset guard)
(run-schedule (seq (run a) (run b) (run guard)))
(check (= (Ga (Fa (Na 0) (Context 0))) (Ga (Fa (Na 1) (Context 0)))))
"#,
    );
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(new.graph.witness_count(table(&new, "Bad")), 0);
}

#[test]
fn deletion_recreation_cannot_reuse_a_deferred_publication_incarnation() {
    let source = SAME_SORT.replace(
        "(run-schedule (seq (run a) (run b) (run consume-b) (run consume-a)))",
        r#"
(ruleset erase) (ruleset recreate)
(rule ((= x (Fa (Na 0) (Context 0)))) ((delete (Ga x))) :ruleset erase)
(rule ((= x (Fa (Na 1) (Context 0)))) ((Ga x)) :ruleset recreate)
(run-schedule (seq (run a) (run b) (run erase) (run recreate) (run consume-a)))
"#,
    );
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(new.graph.witness_count(table(&new, "Ga")), 1);
}

#[test]
fn completing_b_leaves_a_pending_when_both_start_in_the_same_source_run() {
    let source = r#"
(datatype E (Na i64) (Nb i64) (Fa E) (Ga E) (Fb E) (Gb E) (SeenB E) (SeenA E))
(ruleset seed) (ruleset b) (ruleset a)
(rule ((= x (Na 0)) (= y (Na 1)) (= u (Nb 0)) (= v (Nb 1)))
      ((Ga (Fa x)) (Ga (Fa y)) (Gb (Fb u)) (Gb (Fb v))
       (union x y) (union u v)) :ruleset seed)
(rule ((= x (Gb y))) ((SeenB x)) :ruleset b)
(rule ((= x (Ga y))) ((SeenA x)) :ruleset a)
(Na 0) (Na 1) (Nb 0) (Nb 1)
(run-schedule (seq (run seed) (run b) (run a)))
"#;
    let mut old = executor(source, false);
    let mut new = executor(source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    assert_eq!(new.graph.witness_count(table(&new, "SeenB")), 1);
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
        assert_eq!(new.graph.witness_count(table(&new, "Ga")), 2);
        assert_eq!(new.graph.witness_count(table(&new, "Gb")), 1);
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn source_check_forces_port_completion_without_an_intervening_rule() {
    let source = SAME_SORT.replace(
        "(run-schedule (seq (run a) (run b) (run consume-b) (run consume-a)))",
        "(run-schedule (seq (run a) (run b)))\n(check (= (Ga (Fa (Na 0) (Context 0))) (Ga (Fa (Na 1) (Context 0)))))");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn influence_budget_falls_back_without_truncating_the_completion_proof() {
    let mut source = String::from(
        "(datatype E (R i64) (F E i64))\n(ruleset merge) (ruleset idle)\n(rule ((= x (R 0)) (= y (R 1))) ((union x y)) :ruleset merge)\n",
    );
    for i in 0..600 {
        source.push_str(&format!("(F (R 0) {i}) (F (R 1) {i})\n"));
    }
    source.push_str("(run-schedule (seq (run merge) (run idle)))\n");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(1)).unwrap();
    let report = new.graph.port_completion_report();
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(
            report["stats"]["typed_fallbacks"].as_u64().unwrap() > 0,
            "{report}"
        );
        assert_eq!(
            report["stats"]["peak_group_visits"],
            report["visit_budget_per_group"]
        );
    }
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(new.graph.witness_count(table(&new, "F")), 600);
}

#[test]
fn incoming_union_waits_for_a_pending_region_reached_through_result_aliases() {
    let source = SAME_SORT
        .replace(
            "(rule ((= x (Nb 0)) (= c (Context 0))) ((Gb (Fb x c))) :ruleset b)",
            "(rule ((= x (Nb 0)) (= y (Nb 1))) ((union x y)) :ruleset b)",
        )
        .replace(
            "(set (score (Nb 0)) 7)",
            r#"
(Nb 1)
(Fb (Nb 0) (Context 0)) (Fb (Nb 1) (Context 0))
(Fa (Na 0) (Context 0))
(union (Fa (Na 0) (Context 0)) (Fb (Nb 1) (Context 0)))
(set (score (Nb 0)) 7)
"#,
        );
    let source = source.replace("((Ga (Fa x c)) (Ga (Fa y c)) (union x y)) :ruleset a)",
        "((let f (Fa x c)) (let g (Fa y c)) (Ga f) (Ga g) (union x y)) :ruleset a)");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(1)).unwrap();
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
    }
    new.execute_until(Some(2)).unwrap();
    assert_eq!(new.scoped_execution_report()["stats"]["runs_with_unrelated_pending"], 0,
        "the incoming union must close the alias-connected pending epoch before its source Run");
    new.execute().unwrap();
    compare(&old, &new);
}
