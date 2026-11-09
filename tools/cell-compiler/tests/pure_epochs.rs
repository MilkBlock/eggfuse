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
fn overlapping_constructor_epochs_wait_but_independent_consumers_still_publish() {
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
        assert_eq!(point["stats"]["rhs_fact_births_while_pending"], 1);
        assert_eq!(point["stats"]["source_unions_while_pending"], 0);
        assert!(
            new.graph.port_completion_report()["stats"]["pure_epoch_order_rejections"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert_eq!(point["stats"]["bound_rhs_accepts"], 0);
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
fn overlapping_input_changes_preserve_source_epoch_order() {
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
            new.graph.port_completion_report()["stats"]["pure_epoch_order_rejections"]
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
        assert_eq!(s["stats"]["rhs_fact_births_while_pending"], 0);
        assert!(
            new.graph.port_completion_report()["stats"]["pure_epoch_order_rejections"]
                .as_u64()
                .unwrap()
                > 0
        );
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
fn overlapping_epochs_keep_the_collision_at_the_newer_epoch() {
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
            new.graph.port_completion_report()["stats"]["pure_epoch_order_rejections"]
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
            0
        );
        assert!(
            new.graph.port_completion_report()["stats"]["pure_epoch_order_rejections"]
                .as_u64()
                .unwrap()
                > 0
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

const DISPLACED: &str = r#"
(datatype E (N i64) (F E) (Seen E))
(datatype B (Nb i64) (H B) (J B))
(function score (B) i64 :merge (+ old new))
(ruleset a) (ruleset b) (ruleset observe)
(rule ((= x (F y))) ((Seen x)) :ruleset observe)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (Nb 0)) (= y (Nb 1)) (= z (Nb 2)) (= w (Nb 3)))
      ((union x y)) :ruleset b)
(F (N 0)) (F (N 1))
(Nb 0) (Nb 1) (Nb 2) (Nb 3)
(H (Nb 0)) (H (Nb 1))
(set (score (J (Nb 0))) 7)
(run-schedule (seq (run a) (run b) (run observe)))
"#;

fn check_displaced(case: &str, source: &str, accepted: bool) -> Executor {
    let mut old = executor(source, false);
    let mut new = executor(source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    let report = new.scoped_execution_report();
    let pending = new.graph.pending_completion_tasks();
    let ports = new.graph.port_completion_report();
    if report["global_observer"] == false {
        assert_eq!(report["stats"]["bound_rhs_attempts"], 1);
        assert_eq!(report["stats"]["bound_rhs_accepts"], u64::from(accepted));
        if accepted {
            assert!(new.graph.pending_completion_tasks() > 0);
        } else {
            assert!(
                new.graph.port_completion_report()["stats"]["pure_epoch_boundary_rejections"]
                    .as_u64()
                    .unwrap()
                    > 0
            );
        }
    }
    new.execute().unwrap();
    compare(&old, &new);
    if let Ok(directory) = std::env::var("DISPLACED_EPOCH_EVIDENCE") {
        std::fs::create_dir_all(&directory).unwrap();
        std::fs::write(
            std::path::Path::new(&directory).join(format!("{case}.json")),
            serde_json::to_vec_pretty(&serde_json::json!({
                "scope":"standalone single-thread Cell CPU; displaced source effects",
                "admitted":accepted, "pending_tasks":pending, "checkpoint":report,
                "ports":ports, "final_executor":new.scoped_execution_report(),
                "exact_final_state_and_ordered_bindings":true,
            }))
            .unwrap(),
        )
        .unwrap();
    }
    new
}

#[test]
fn unchanged_input_users_of_other_operators_do_not_block_the_source_union() {
    let new = check_displaced("unrelated-unchanged-user", DISPLACED, true);
    if new.scoped_execution_report()["global_observer"] == false {
        assert_eq!(
            new.scoped_execution_report()["stats"]["source_unions_while_pending"],
            1
        );
    }
}

#[test]
fn separate_operators_of_the_same_sort_can_cross_source_epochs() {
    let source = r#"
(datatype E (N i64) (F E) (H E) (Seen E))
(ruleset a) (ruleset b) (ruleset observe)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (N 2)) (= y (N 3))) ((union x y)) :ruleset b)
(rule ((= x (F y))) ((Seen x)) :ruleset observe)
(F (N 0)) (F (N 1)) (H (N 2)) (H (N 3))
(run-schedule (seq (run a) (run b) (run observe)))
"#;
    let mut old = executor(source, false);
    let mut new = executor(source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
        assert_eq!(
            new.scoped_execution_report()["stats"]["source_unions_while_pending"],
            1
        );
        assert_eq!(
            new.graph.port_completion_report()["stats"]["pure_epoch_order_rejections"],
            0
        );
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn disjoint_regions_of_the_same_operators_can_cross_source_epochs() {
    let source = r#"
(datatype E (N i64) (F E) (G E) (Seen E))
(ruleset a) (ruleset b) (ruleset observe)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (N 2)) (= y (N 3))) ((union x y)) :ruleset b)
(rule ((= x (G y))) ((Seen x)) :ruleset observe)
(N 0) (N 1) (N 2) (N 3)
(G (F (N 3))) (G (F (N 1))) (G (F (N 2))) (G (F (N 0)))
(run-schedule (seq (run a) (run b) (run observe)))
"#;
    let mut old = executor(source, false);
    let mut new = executor(source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    let checkpoint = new.scoped_execution_report();
    let ports = new.graph.port_completion_report();
    let pending = new.graph.pending_completion_tasks();
    if checkpoint["global_observer"] == false {
        assert!(pending > 0);
        assert_eq!(checkpoint["stats"]["rhs_completions"], 0);
        assert_eq!(checkpoint["stats"]["source_unions_while_pending"], 1);
        assert_eq!(checkpoint["stats"]["bound_rhs_accepts"], 1);
        assert!(
            ports["stats"]["pure_epoch_order_disjoint"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert_eq!(ports["stats"]["pure_epoch_order_rejections"], 0);
    }
    new.execute().unwrap();
    compare(&old, &new);
    if let Ok(path) = std::env::var("DISJOINT_ORDER_EVIDENCE") {
        std::fs::write(
            path,
            serde_json::to_vec_pretty(&serde_json::json!({
                "scope":"standalone Cell CPU; same-operator disjoint source epochs",
                "checkpoint":checkpoint,"ports":ports,"pending_tasks":pending,
                "exact_final_state_and_ordered_bindings":true,
            }))
            .unwrap(),
        )
        .unwrap();
    }
}

#[test]
fn disjoint_first_outputs_cannot_hide_a_shared_downstream_condition() {
    let source = r#"
(datatype E (N i64) (F E) (G E E) (Seen E))
(ruleset a) (ruleset b) (ruleset observe)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (N 2)) (= y (N 3))) ((union x y)) :ruleset b)
(rule ((= x (G y z))) ((Seen x)) :ruleset observe)
(N 0) (N 1) (N 2) (N 3)
(G (F (N 0)) (F (N 2))) (G (F (N 1)) (F (N 3)))
(run-schedule (seq (run a) (run b) (run observe)))
"#;
    let mut old = executor(source, false);
    let mut new = executor(source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    let checkpoint = new.scoped_execution_report();
    let ports = new.graph.port_completion_report();
    if checkpoint["global_observer"] == false {
        assert!(
            ports["stats"]["pure_epoch_order_disjoint"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert!(
            ports["stats"]["pure_epoch_frontier_conflicts"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert_eq!(checkpoint["stats"]["bound_rhs_accepts"], 0);
        assert_eq!(checkpoint["stats"]["source_unions_while_pending"], 0);
        assert_eq!(checkpoint["stats"]["rhs_completions"], 1);
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn unchanged_input_peers_of_the_same_operator_keep_the_mutable_boundary() {
    check_displaced(
        "same-operator-peer",
        &DISPLACED.replace("(score (J (Nb 0)))", "(score (H (Nb 0)))"),
        false,
    );
}

#[test]
fn chained_source_unions_must_include_every_displaced_root() {
    let source = DISPLACED
        .replace(
            "((union x y)) :ruleset b)",
            "((union x z) (union z y)) :ruleset b)",
        )
        .replace("(score (J (Nb 0)))", "(score (Nb 1))");
    check_displaced("transitive-source-pairs", &source, false);
}

#[test]
fn a_constructor_birth_does_not_change_its_read_only_input() {
    let source = DISPLACED
        .replace("((union x y)) :ruleset b)", "((union (J x) z)) :ruleset b)")
        .replace("(score (J (Nb 0)))", "(score (Nb 0))");
    let new = check_displaced("read-only-birth-input", &source, true);
    if new.scoped_execution_report()["global_observer"] == false {
        assert_eq!(
            new.scoped_execution_report()["stats"]["rhs_fact_births_while_pending"],
            1
        );
        assert_eq!(
            new.scoped_execution_report()["stats"]["source_unions_while_pending"],
            0
        );
    }
}

#[test]
fn new_set_keys_that_collide_after_source_unions_keep_both_result_endpoints() {
    let source = DISPLACED
        .replace(
            "((union x y)) :ruleset b)",
            "((union (H x) z) (union (H y) w) (union x y)) :ruleset b)",
        )
        .replace("(H (Nb 0)) (H (Nb 1))", "")
        .replace("(score (J (Nb 0)))", "(score (Nb 3))");
    check_displaced("future-birth-collision", &source, false);
}

#[test]
fn equal_absent_set_keys_are_not_independent_births() {
    let source = DISPLACED
        .replace(
            "((union x y)) :ruleset b)",
            "((union (H x) z) (union (H x) w)) :ruleset b)",
        )
        .replace("(H (Nb 0)) (H (Nb 1))", "")
        .replace("(score (J (Nb 0)))", "(score (Nb 3))");
    check_displaced("same-key-birth-collision", &source, false);
}

const ARITHMETIC: &str = r#"
(datatype E (N i64) (F E) (Final E))
(datatype B (Nb i64) (H B i64) (Seen B))
(ruleset a) (ruleset b) (ruleset consume) (ruleset observe)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset a)
(rule ((= x (Nb n)) (= n 0) (= y (Nb 1)))
      ((let copied x) (let k (- (* (+ n 5) 3) 2)) (union (H copied k) y)) :ruleset b)
(rule ((= x (H y k))) ((Seen x)) :ruleset consume)
(rule ((= x (F y))) ((Final x)) :ruleset observe)
(F (N 0)) (F (N 1)) (Nb 0) (Nb 1)
(run-schedule (seq (run a) (run b) (run consume) (run observe)))
"#;

#[test]
fn compiled_scalar_effects_preserve_arithmetic_and_publish_the_birth() {
    let mut old = executor(ARITHMETIC, false);
    let mut new = executor(ARITHMETIC, true);
    assert_eq!(
        old.graph.program.completion_plan.as_ref().unwrap().report()["pure_rhs_templates"],
        0
    );
    assert!(
        new.graph.program.completion_plan.as_ref().unwrap().report()["pure_rhs_templates"]
            .as_u64()
            .unwrap()
            > 0
    );
    old.execute().unwrap();
    new.execute_until(Some(3)).unwrap();
    let h = new
        .graph
        .program
        .tables
        .iter()
        .position(|t| t.name == "H")
        .unwrap();
    let rows = new.graph.witnesses(h);
    assert_eq!(rows.len(), 1);
    assert_eq!(
        new.graph.row(rows[0]).unwrap().unwrap().values[1],
        eggfuse_cell_runtime::value::Value::Int(13)
    );
    let seen = new
        .graph
        .program
        .tables
        .iter()
        .position(|t| t.name == "Seen")
        .unwrap();
    assert_eq!(new.graph.witness_count(seen), 1);
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
        assert!(
            new.scoped_execution_report()["stats"]["bound_rhs_input_reads"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert!(
            new.scoped_execution_report()["stats"]["rhs_fact_births_while_pending"]
                .as_u64()
                .unwrap()
                >= 1
        );
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn compiled_effect_overflow_retains_the_original_failing_rhs() {
    let source = ARITHMETIC
        .replace("(- (* (+ n 5) 3) 2)", "(+ n 9223372036854775807)")
        .replace("(= n 0)", "(= n 1)");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    assert_eq!(old.execute().unwrap_err(), new.execute().unwrap_err());
    if new.scoped_execution_report()["global_observer"] == false {
        assert_eq!(
            new.scoped_execution_report()["stats"]["bound_rhs_attempts"],
            1
        );
        assert_eq!(
            new.scoped_execution_report()["stats"]["bound_rhs_accepts"],
            0
        );
    }
}

#[test]
fn unused_arithmetic_failure_retains_the_original_effect_wait() {
    let source = ARITHMETIC
        .replace("(- (* (+ n 5) 3) 2)", "(+ n 9223372036854775807)")
        .replace("(= n 0)", "(= n 1)")
        .replace("(H copied k)", "(H copied 13)");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    assert_eq!(old.execute().unwrap_err(), new.execute().unwrap_err());
    if new.scoped_execution_report()["global_observer"] == false {
        let stats = &new.scoped_execution_report()["stats"];
        assert_eq!(stats["bound_rhs_attempts"], 1);
        assert_eq!(stats["bound_rhs_accepts"], 0);
    }
}

#[test]
fn compiled_arithmetic_keys_select_the_actual_mutable_collision_result() {
    let source = DISPLACED
        .replace("(H B)", "(H B i64)")
        .replace("(H (Nb 0))", "(H (Nb 0) 13)")
        .replace("(H (Nb 1))", "(H (Nb 1) 13)")
        .replace("(rule ((= x (Nb 0))", "(rule ((= x (Nb n)) (= n 0)")
        .replace(
            "((union x y)) :ruleset b)",
            "((union (H x (- (* (+ n 5) 3) 2)) w)) :ruleset b)",
        )
        .replace("(score (J (Nb 0)))", "(score (H (Nb 0) 13))");
    check_displaced("compiled-arithmetic-key", &source, false);
}
