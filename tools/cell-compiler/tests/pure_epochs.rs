use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use std::collections::BTreeSet;

fn executor(source: &str, pure: bool) -> Executor {
    let core = eggfuse_bake::device_frontend::core("pure-epochs", source).unwrap();
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut e = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    if pure {
        e.use_pure_epochs().unwrap();
    }
    e
}
fn compare(a: &Executor, b: &Executor) {
    assert_eq!(a.graph.export().unwrap(), b.graph.export().unwrap());
    assert_eq!(a.steps.len(), b.steps.len());
    for (a, b) in a.steps.iter().zip(&b.steps) {
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
const SOURCE: &str = r#"
(datatype E (N i64) (F E) (G E) (Keep E i64) (Seen E) (Final E))
(ruleset a) (ruleset b) (ruleset consume) (ruleset observe)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (N 0)) (= y (N 2))) ((union x y) (union (Keep x 42) y)) :ruleset b)
(rule ((= x (Keep y i))) ((Seen x)) :ruleset consume)
(rule ((= x (G y))) ((Final x)) :ruleset observe)
(G (F (N 0))) (G (F (N 1))) (G (F (N 2)))
(run-schedule (seq (run a) (run b) (run consume) (run observe)))
"#;

#[test]
fn pure_constructor_epochs_can_commit_and_publish_while_prior_congruence_is_pending() {
    let mut old = executor(SOURCE, false);
    let mut new = executor(SOURCE, true);
    old.execute().unwrap();
    new.execute_until(Some(3)).unwrap();
    let point = new.scoped_execution_report();
    let pending = new.graph.pending_completion_tasks();
    let seen = new
        .graph
        .program
        .tables
        .iter()
        .position(|t| t.name == "Seen")
        .unwrap();
    let consumed = new.graph.witness_count(seen);
    assert_eq!(consumed, 1);
    if point["global_observer"] == false {
        assert!(pending > 0);
        assert_eq!(point["stats"]["rhs_fact_births_while_pending"], 2);
        assert_eq!(point["stats"]["source_unions_while_pending"], 1);
        assert!(
            new.graph.scoped_completion_report()["stats"]["mixed_epoch_inserts"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert!(point["stats"]["bound_rhs_accepts"].as_u64().unwrap() > 0);
    }
    new.execute().unwrap();
    compare(&old, &new);
    if let Ok(path) = std::env::var("PURE_EPOCH_EVIDENCE") {
        std::fs::write(path,serde_json::to_vec_pretty(&serde_json::json!({"scope":"standalone single-thread Cell CPU; closed pure constructor source epochs", "checkpoint":point,"pending_tasks_at_checkpoint":pending,"consumed_facts_at_checkpoint":consumed,"final_executor":new.scoped_execution_report(),"queue":new.graph.scoped_completion_report(),"ports":new.graph.port_completion_report(),"exact_final_state_and_ordered_bindings":true})).unwrap()).unwrap();
    }
}

#[test]
fn a_live_mutable_boundary_keeps_the_source_effect_fence() {
    let source = SOURCE
        .replace(
            "(ruleset a)",
            "(function score (E) i64 :merge (+ old new))\n(ruleset a)",
        )
        .replace("(run-schedule", "(set (score (N 2)) 3)\n(run-schedule");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    if new.scoped_execution_report()["global_observer"] == false {
        assert_eq!(
            new.scoped_execution_report()["stats"]["bound_rhs_accepts"],
            0
        );
        assert!(
            new.graph.port_completion_report()["stats"]["pure_epoch_boundary_rejections"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert_eq!(
            new.scoped_execution_report()["stats"]["executed_bindings_while_pending"],
            0
        );
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn repeated_input_changes_coalesce_at_the_latest_task_epoch() {
    let source = SOURCE
        .replace("(F E)", "(F E E)")
        .replace(
            "(rule ((= x (N 0)) (= y (N 2)))",
            "(rule ((= x (N 2)) (= y (N 3)))",
        )
        .replace(
            "(G (F (N 0))) (G (F (N 1))) (G (F (N 2)))",
            "(G (F (N 0) (N 2))) (G (F (N 1) (N 3)))",
        );
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(
            new.graph.scoped_completion_report()["stats"]["advanced_task_epochs"]
                .as_u64()
                .unwrap()
                > 0
        );
        let g = new
            .graph
            .program
            .tables
            .iter()
            .position(|t| t.name == "G")
            .unwrap();
        for witness in new.graph.witnesses(g) {
            assert_eq!(new.graph.row(witness).unwrap().unwrap().epoch, 2);
        }
    }
}

#[test]
fn absent_constructor_sets_in_one_snapshot_can_collide_with_each_other() {
    let source = SOURCE
        .replace(
            "(rule ((= x (N 0)) (= y (N 2))) ((union x y) (union (Keep x 42) y)) :ruleset b)",
            "(rule ((= x (N 0)) (= y (N i)) (> i 0)) ((union (Keep x 42) y)) :ruleset b)",
        )
        .replace("(G (F (N 2)))", "(G (F (N 2))) (G (F (N 3)))");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    if new.scoped_execution_report()["global_observer"] == false {
        let s = new.scoped_execution_report();
        assert_eq!(s["stats"]["bound_rhs_noop_accepts"], 0);
        assert_eq!(s["stats"]["bound_rhs_key_reads"], 3);
        assert_eq!(s["stats"]["rhs_fact_births_while_pending"], 1);
        assert!(new.graph.pending_completion_tasks() > 0);
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn an_already_true_union_needs_no_effect_closure_even_with_a_mutable_user() {
    let source = SOURCE
        .replace(
            "((union x y) (union (Keep x 42) y)) :ruleset b)",
            "((union x x)) :ruleset b)",
        )
        .replace(
            "(ruleset a)",
            "(function score (E) i64 :merge (+ old new))\n(ruleset a)",
        )
        .replace("(run-schedule", "(set (score (N 0)) 3)\n(run-schedule");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    if new.scoped_execution_report()["global_observer"] == false {
        assert_eq!(
            new.scoped_execution_report()["stats"]["bound_rhs_noop_accepts"],
            1
        );
        assert!(new.graph.pending_completion_tasks() > 0);
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn an_older_task_cannot_backdate_a_collision_with_a_completed_newer_peer() {
    let source = r#"
(datatype E (N i64) (F E E) (G E) (Seen E))
(ruleset a) (ruleset b) (ruleset observe)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (N 2)) (= y (N 3))) ((union x y)) :ruleset b)
(rule ((= x (G y))) ((Seen x)) :ruleset observe)
(N 0) (N 1) (N 2) (N 3)
(G (F (N 0) (N 3))) (G (F (N 1) (N 2)))
(run-schedule (seq (run a) (run b) (run observe)))
"#;
    let mut old = executor(source, false);
    let mut new = executor(source, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    if new.scoped_execution_report()["global_observer"] == false {
        let g = new
            .graph
            .program
            .tables
            .iter()
            .position(|t| t.name == "G")
            .unwrap();
        for witness in new.graph.witnesses(g) {
            assert_eq!(new.graph.row(witness).unwrap().unwrap().epoch, 2);
        }
        assert!(
            new.graph.scoped_completion_report()["stats"]["completion_epoch_joins"]
                .as_u64()
                .unwrap()
                > 0
        );
    }
}

#[test]
fn shared_entry_results_survive_batched_two_dimensional_congruence() {
    let source = r#"
(datatype E (N i64) (F E E) (G E) (Seen E))
(ruleset make) (ruleset a) (ruleset b) (ruleset observe)
(rule ((= x (N i)) (= y (N j))) ((G (F x y))) :ruleset make)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (N 2)) (= y (N 3))) ((union x y)) :ruleset b)
(rule ((= x (G y))) ((Seen x)) :ruleset observe)
(N 0) (N 1) (N 2) (N 3)
(run-schedule (seq (run make) (run a) (run b) (run observe)))
"#;
    let mut old = executor(source, false);
    let mut new = executor(source, true);
    old.execute().unwrap();
    new.execute_until(Some(3)).unwrap();
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
        assert_eq!(
            new.scoped_execution_report()["stats"]["source_unions_while_pending"],
            1
        );
    }
    new.execute().unwrap();
    compare(&old, &new);
    assert_eq!(
        old.report()["stage_spine"]["stats"]["resumed_steps"],
        new.report()["stage_spine"]["stats"]["resumed_steps"]
    );
    assert!(
        new.report()["stage_spine"]["stats"]["resumed_steps"]
            .as_u64()
            .unwrap()
            > 0
    );
}

#[test]
fn the_pure_closure_budget_retains_the_original_effect_wait() {
    let mut source = String::from(
        "(datatype E (N i64) (F E))\n(datatype B (Nb i64))\n(constructor H (B i64) E)\n(ruleset a) (ruleset b)\n(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)\n(rule ((= x (Nb 0)) (= y (Nb 1))) ((union x y)) :ruleset b)\n(F (N 0)) (F (N 1))\n",
    );
    for i in 0..450 {
        source.push_str(&format!("(H (Nb 0) {i}) (H (Nb 1) {i})\n"));
    }
    source.push_str("(run-schedule (seq (run a) (run b)))\n");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(
            new.graph.port_completion_report()["stats"]["pure_epoch_budget_rejections"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert_eq!(
            new.scoped_execution_report()["stats"]["bound_rhs_accepts"],
            0
        );
    }
}
