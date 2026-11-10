use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use std::collections::BTreeSet;

fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("staged-completion", source).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn executor(source: &str, staged: bool) -> Executor {
    let mut e = Executor::new(
        Graph::new_with_scoped_completion(program(source)).unwrap(),
        false,
    );
    if staged {
        e.use_port_scopes().unwrap();
    }
    e
}
fn table(e: &Executor, name: &str) -> usize {
    e.graph
        .program
        .tables
        .iter()
        .position(|t| t.name == name)
        .unwrap()
}
fn compare(old: &Executor, new: &Executor) {
    assert_eq!(old.graph.export().unwrap(), new.graph.export().unwrap());
    assert_eq!(old.steps.len(), new.steps.len());
    for (a, b) in old.steps.iter().zip(&new.steps) {
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
}
const SOURCE: &str = r#"
(datatype E (Na i64) (Nb i64) (Fa E) (Ga E) (Fb E) (Gb E) (SeenB E) (SeenA E))
(datatype Flag (Missing))
(function score (E) i64 :merge (min old new))
(ruleset a) (ruleset b) (ruleset follow) (ruleset observe)
(rule ((= x (Na 0)) (= y (Na 1))) ((Ga (Fa x)) (Ga (Fa y)) (union x y)) :ruleset a)
(rule ((= m (Missing))) ((Ga (Fa (Na 0))) (union (Na 0) (Na 1))) :ruleset b)
(rule ((= x (Nb 0))) ((Gb (Fb x))) :ruleset b)
(rule ((= x (Gb y))) ((SeenB x)) :ruleset follow)
(rule ((= x (Ga y))) ((SeenA x)) :ruleset observe)
(Na 0) (Na 1) (Nb 0) (set (score (Nb 0)) 7)
(run-schedule (seq (run a) (run b) (run follow) (run observe)))
"#;

#[test]
fn an_unmatched_rhs_does_not_block_other_bindings_and_their_consumers() {
    let mut old = executor(SOURCE, false);
    let mut new = executor(SOURCE, true);
    let ga = table(&new, "Ga");
    let plan = new.graph.program.completion_plan.as_ref().unwrap();
    assert!(new.graph.program.sets["b"].iter().any(|&r| {
        let demand = &plan.rule_demands[r];
        demand.query.contains(&ga) || demand.rhs.contains(&ga)
    }));
    assert!(!plan.query_demands["b"].contains(&ga));
    old.execute().unwrap();
    new.execute_until(Some(3)).unwrap();
    assert_eq!(new.graph.witness_count(table(&new, "SeenB")), 1);
    let point = serde_json::json!({"executor":new.scoped_execution_report(),"graph":new.graph.scoped_completion_report(),"seen_b_facts":new.graph.witness_count(table(&new,"SeenB"))});
    if point["executor"]["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
        assert_eq!(
            point["executor"]["stats"]["executed_bindings_while_pending"],
            2
        );
        assert_eq!(
            point["executor"]["stats"]["rhs_fact_births_while_pending"],
            3
        );
        assert_eq!(point["executor"]["stats"]["rhs_completions"], 0);
    }
    new.execute().unwrap();
    compare(&old, &new);
    if let Ok(path) = std::env::var("STAGED_COMPLETION_EVIDENCE") {
        std::fs::write(path,serde_json::to_vec_pretty(&serde_json::json!({"scope":"standalone single-thread Cell CPU; unmatched RHS omitted only after query completion", "checkpoint":point,"final_executor":new.scoped_execution_report(),"exact_final_state_and_ordered_bindings":true,"parallel_or_timing_claim":false})).unwrap()).unwrap();
    }
}

#[test]
fn matched_rhs_waits_after_the_independent_query_snapshot() {
    let source = SOURCE.replace(
        "((Gb (Fb x))) :ruleset b)",
        "((Gb (Fb x)) (Ga (Fa (Na 0)))) :ruleset b)",
    );
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    assert_eq!(new.graph.pending_completion_tasks(), 0);
    if new.scoped_execution_report()["global_observer"] == false {
        let stats = &new.scoped_execution_report()["stats"];
        assert_eq!(stats["query_bindings_while_pending"], 1);
        assert_eq!(stats["rhs_completions"], 1);
        assert_eq!(stats["rhs_access_completions"], 1);
        assert_eq!(stats["rhs_union_completions"], 0);
        assert_eq!(stats["executed_bindings_while_pending"], 0);
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn a_matched_union_keeps_its_future_effect_fence() {
    let source = SOURCE
        .replace(
            "(rule ((= x (Nb 0))) ((Gb (Fb x))) :ruleset b)",
            "(rule ((= x (Nb 0)) (= y (Nb 1))) ((union x y)) :ruleset b)",
        )
        .replace("(Nb 0) (set (score", "(Nb 0) (Nb 1) (set (score");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    assert_eq!(new.graph.pending_completion_tasks(), 0);
    if new.scoped_execution_report()["global_observer"] == false {
        let stats = &new.scoped_execution_report()["stats"];
        assert_eq!(stats["query_bindings_while_pending"], 1);
        assert_eq!(stats["rhs_completions"], 1);
        assert_eq!(stats["rhs_access_completions"], 0);
        assert_eq!(stats["rhs_union_completions"], 1);
        assert_eq!(stats["executed_bindings_while_pending"], 0);
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn an_empty_saturating_run_does_not_force_its_unexecuted_effects() {
    let source = SOURCE
        .replace(
            "(run-schedule",
            r#"
(ruleset empty)
(rule ((= m (Missing))) ((Ga (Fa (Na 0)))) :ruleset empty)
(run-schedule"#,
        )
        .replace(
            "(seq (run a) (run b)",
            "(seq (run a) (saturate (run empty)) (run b)",
        );
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    assert!(!new.steps[1].changed);
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
        assert_eq!(new.scoped_execution_report()["stats"]["rhs_empty_skips"], 1);
    }
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn current_rhs_cannot_activate_another_rule_in_the_same_matching_snapshot() {
    let source = SOURCE
        .replace(
            "((Gb (Fb x))) :ruleset b)",
            "((Gb (Fb x)) (Missing)) :ruleset b)",
        )
        .replace("(run b) (run follow)", "(run b) (run b) (run follow)");
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    assert_eq!(new.steps[1].executed_bindings, 1);
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
    }
    new.execute_until(Some(3)).unwrap();
    assert_eq!(new.graph.pending_completion_tasks(), 0);
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn matched_entry_origins_survive_completion_and_publication_before_rhs() {
    let source = r#"
(datatype A (Na i64) (Fa A) (Ga A))
(datatype B (Nb i64) (Fb B) (Gb B))
(ruleset producer) (ruleset seed) (ruleset consumer)
(rule ((= x (Nb 0))) ((Fb x)) :ruleset producer)
(rule ((= x (Na 0)) (= y (Na 1))) ((Ga (Fa x)) (Ga (Fa y)) (union x y)) :ruleset seed)
(rule ((= x (Fb y))) ((Gb x) (Ga (Fa (Na 0)))) :ruleset consumer)
(Na 0) (Na 1) (Nb 0)
(run-schedule (seq (run producer) (run seed) (run consumer)))
"#;
    let mut old = executor(source, false);
    let mut new = executor(source, true);
    old.execute().unwrap();
    new.execute().unwrap();
    compare(&old, &new);
    if new.scoped_execution_report()["global_observer"] == false {
        let stats = &new.scoped_execution_report()["stats"];
        assert_eq!(stats["rhs_completions"], 1);
        assert!(
            stats["peak_matched_origin_slots"].as_u64().unwrap() > 0,
            "{stats}"
        );
    }
    assert_eq!(
        old.report()["stage_spine"]["stats"]["resumed_steps"],
        new.report()["stage_spine"]["stats"]["resumed_steps"]
    );
    assert_eq!(new.scoped_execution_report()["retained_forwards"], 0);
}

#[test]
fn identical_completion_obligations_share_owners_across_rules() {
    let p=program("(relation A (i64)) (relation B (i64)) (ruleset r)\n(rule ((A x)) ((B x)) :ruleset r)\n(rule ((A x) (= x 1)) ((B x)) :ruleset r)\n(A 1) (run-schedule (run r))");
    let plan=eggfuse_cell_runtime::completion_plan::Plan::derive(&p).unwrap();
    let mut owners=std::collections::BTreeMap::new();
    let mut duplicates=0;
    for demand in &plan.rule_demands {
        for list in [&demand.query,&demand.rhs,&demand.accesses] {
            if let Some(previous)=owners.get(list.as_ref()) {
                assert!(std::rc::Rc::ptr_eq(previous,list));duplicates+=1;
            } else {owners.insert(list.to_vec(),list.clone());}
        }
    }
    assert!(duplicates>0);
    let snapshot=serde_json::to_value(&plan).unwrap();
    let cloned=plan.clone();drop(plan);
    assert_eq!(snapshot,serde_json::to_value(&cloned).unwrap());
}
