use eggfuse_cell_runtime::{
    compiler, completion_plan::Plan, graph::Graph, program::Program, value::Value,
};
use std::collections::BTreeSet;

fn program(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("scoped-completion", src).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn table(p: &Program, name: &str) -> usize {
    p.tables.iter().position(|t| t.name == name).unwrap()
}
fn value(g: &Graph, table: usize, key: &[Value]) -> Value {
    g.lookup(table, key)
        .unwrap()
        .unwrap()
        .values
        .last()
        .unwrap()
        .clone()
}
const INDEPENDENT: &str = r#"
(datatype A (Na i64) (Fa A) (Ga A))
(datatype B (Nb i64) (Fb B) (Gb B))
(Ga (Fa (Na 0))) (Ga (Fa (Na 1)))
(Gb (Fb (Nb 0))) (Gb (Fb (Nb 1)))
(run-schedule (run))
"#;
fn merge_inputs(g: &mut Graph) {
    g.epoch = 1;
    for name in ["Na", "Nb"] {
        let t = table(&g.program, name);
        g.enqueue_union(value(g, t, &[Value::Int(0)]), value(g, t, &[Value::Int(1)]))
            .unwrap();
    }
}

#[test]
fn scoped_wait_leaves_unrelated_chain_pending_and_preserves_origin_epoch() {
    let p = program(INDEPENDENT);
    let ga = table(&p, "Ga");
    let gb = table(&p, "Gb");
    let fa = table(&p, "Fa");
    let fb = table(&p, "Fb");
    let mut reference = Graph::new_with_local_congruence(p.clone()).unwrap();
    let mut scoped = Graph::new_with_scoped_completion(p).unwrap();
    merge_inputs(&mut reference);
    merge_inputs(&mut scoped);
    reference.repair().unwrap();
    scoped.commit_scoped_unions().unwrap();
    let a = scoped.completion_scope(&[ga]).unwrap();
    let b = scoped.completion_scope(&[gb]).unwrap();
    assert!(!scoped.scope_ready(&a).unwrap());
    assert!(!scoped.scope_ready(&b).unwrap());
    scoped.complete_scope(&b).unwrap();
    assert!(scoped.scope_ready(&b).unwrap());
    assert!(!scoped.scope_ready(&a).unwrap());
    assert_eq!(scoped.witness_count(fb), 1);
    assert_eq!(scoped.witness_count(gb), 1);
    assert_eq!(scoped.witness_count(fa), 2);
    assert_eq!(scoped.witness_count(ga), 2);
    assert!(scoped.pending_completion_tasks() > 0);
    // An independent source epoch can advance while A's unchanged survivors
    // retain their original epoch. Absorbing a duplicate is not a new delta.
    scoped.epoch = 9;
    scoped.complete_scope(&a).unwrap();
    assert_eq!(scoped.epoch, 9);
    for w in scoped.witnesses(ga) {
        assert_eq!(scoped.row(w).unwrap().unwrap().epoch, 0);
    }
    for w in reference.witnesses(ga) {
        assert_eq!(reference.row(w).unwrap().unwrap().epoch, 0);
    }
    assert_eq!(scoped.pending_completion_tasks(), 0);
    scoped.epoch = reference.epoch;
    scoped.collect_garbage();
    reference.collect_garbage();
    assert_eq!(scoped.export().unwrap(), reference.export().unwrap());
    assert!(
        scoped.scoped_completion_report()["stats"]["bypassed_tasks"]
            .as_u64()
            .unwrap()
            > 0
    );
}

#[test]
fn typed_reachability_includes_multi_sort_congruence_cascades() {
    let p = program(
        r#"
(datatype A (Na i64) (Fa A))
(datatype B (Wrap A))
(datatype C (Finish B))
(datatype D (Separate i64))
(ruleset read)
(rule ((= x (Finish y))) ((Finish y)) :ruleset read)
(Finish (Wrap (Fa (Na 0)))) (Finish (Wrap (Fa (Na 1))))
(Separate 0)
(run-schedule (run read))
"#,
    );
    let plan = Plan::derive(&p).unwrap();
    let f = table(&p, "Fa");
    let end = table(&p, "Finish");
    let separate = table(&p, "Separate");
    assert!(plan.affects(f, end));
    assert!(!plan.affects(f, separate));
    assert!(plan.deferrable[f]);
    let mut g = Graph::new_with_scoped_completion(p).unwrap();
    let n = table(&g.program, "Na");
    g.epoch = 1;
    g.enqueue_union(
        value(&g, n, &[Value::Int(0)]),
        value(&g, n, &[Value::Int(1)]),
    )
    .unwrap();
    g.commit_scoped_unions().unwrap();
    let scope = g.completion_scope(&[end]).unwrap();
    assert!(!g.scope_ready(&scope).unwrap());
    g.complete_scope(&scope).unwrap();
    assert_eq!(g.witness_count(end), 1);
    assert!(g.scope_ready(&scope).unwrap());
}

#[test]
fn mutable_merge_effects_and_foreign_scopes_cannot_bypass_completion() {
    let p = program(
        r#"
(datatype A (Na i64) (Fa A))
(function score (A) i64 :merge (min old new))
(Fa (Na 0)) (Fa (Na 1))
(set (score (Fa (Na 0))) 10)
(set (score (Fa (Na 1))) 20)
(run-schedule (run))
"#,
    );
    let f = table(&p, "Fa");
    let s = table(&p, "score");
    let plan = Plan::derive(&p).unwrap();
    assert!(plan.affects(f, s));
    assert!(!plan.deferrable[f]);
    let mut g = Graph::new_with_scoped_completion(p).unwrap();
    let n = table(&g.program, "Na");
    g.epoch = 1;
    g.enqueue_union(
        value(&g, n, &[Value::Int(0)]),
        value(&g, n, &[Value::Int(1)]),
    )
    .unwrap();
    let scope = g.completion_scope(&[s]).unwrap();
    assert!(!g.scope_ready(&scope).unwrap());
    g.complete_scope(&scope).unwrap();
    assert_eq!(g.witness_count(s), 1);
    let foreign = Graph::new_with_scoped_completion(program(INDEPENDENT))
        .unwrap()
        .completion_scope(&[0])
        .unwrap();
    assert!(g.complete_scope(&foreign).is_err());
}

#[test]
fn checked_merge_reads_complete_their_scope_without_a_global_barrier() {
    let p = program(
        r#"
(datatype A (Na i64) (Fa A))
(datatype B (Nb i64))
(function port (B) i64 :merge old)
(function callback (B) i64 :merge (port (Nb 0)))
(Fa (Na 0)) (Fa (Na 1)) (Nb 0) (Nb 1)
(set (port (Nb 0)) 7)
(set (callback (Nb 0)) 1)
(set (callback (Nb 1)) 2)
(run-schedule (run))
"#,
    );
    let f = table(&p, "Fa");
    let callback = table(&p, "callback");
    let plan = Plan::derive(&p).unwrap();
    assert!(!plan.opaque_tables.contains(&callback));
    assert!(plan.merges[callback].reads.contains(&table(&p, "port")));
    assert!(
        !plan.affects(f, callback),
        "a dormant merge is not an alias between sorts"
    );
    assert!(plan.deferrable[f]);
    let mut control = Graph::new_with_local_congruence(p.clone()).unwrap();
    let mut scoped = Graph::new_with_scoped_completion(p).unwrap();
    merge_inputs(&mut control);
    merge_inputs(&mut scoped);
    control.repair().unwrap();
    scoped.commit_scoped_unions().unwrap();
    let scope = scoped.completion_scope(&[callback]).unwrap();
    scoped.complete_scope(&scope).unwrap();
    assert_eq!(
        scoped.scoped_completion_report()["stats"]["opaque_full_completions"],
        0
    );
    assert!(scoped.pending_completion_tasks() > 0);
    assert_eq!(scoped.witness_count(f), 2);
    let nb = table(&scoped.program, "Nb");
    assert_eq!(
        value(&scoped, callback, &[value(&scoped, nb, &[Value::Int(0)])]),
        Value::Int(7)
    );
    scoped.repair().unwrap();
    control.collect_garbage();
    scoped.collect_garbage();
    assert_eq!(control.export().unwrap(), scoped.export().unwrap());
}

const EXECUTOR_STAGES: &str = r#"
(datatype A (Na i64) (Fa A) (Ga A) (SeenA A))
(datatype B (Nb i64) (Fb B) (Gb B) (SeenB B))
(ruleset seed) (ruleset independent) (ruleset follow) (ruleset observe)
(rule ((= x (Na 0)) (= y (Na 1)))
      ((Ga (Fa x)) (Ga (Fa y)) (union x y)) :ruleset seed)
(rule ((= x (Nb n))) ((Gb (Fb x))) :ruleset independent)
(rule ((= x (Gb y))) ((SeenB x)) :ruleset follow)
(rule ((= x (Ga y))) ((SeenA x)) :ruleset observe)
(Na 0) (Na 1) (Nb 0)
(run-schedule (seq (run seed) (run independent) (run follow) (run observe)))
"#;

#[test]
fn executor_publishes_and_consumes_b_while_a_completion_and_contexts_remain_pending() {
    use eggfuse_cell_runtime::executor::Executor;
    let p = program(EXECUTOR_STAGES);
    let mut reference = Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), false);
    let mut scoped = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    scoped.use_scoped_execution().unwrap();
    reference.execute().unwrap();
    scoped.execute_until(Some(1)).unwrap();
    let report = scoped.scoped_execution_report();
    let first =
        serde_json::json!({"executor":report,"graph":scoped.graph.scoped_completion_report()});
    let global_observer = report["global_observer"].as_bool().unwrap();
    if !global_observer {
        assert!(scoped.graph.pending_completion_tasks() > 0, "{report}");
        assert!(report["pending_anchors"].as_u64().unwrap() > 0, "{report}");
        assert!(
            report["retained_contexts"].as_u64().unwrap() > 0,
            "{report}"
        );
    }
    scoped.execute_until(Some(3)).unwrap();
    let seen_b = table(&scoped.graph.program, "SeenB");
    assert_eq!(scoped.graph.witness_count(seen_b), 1);
    assert!(scoped.steps[2].changed);
    assert_eq!(scoped.steps[2].executed_bindings, 1);
    let report = scoped.scoped_execution_report();
    let third = serde_json::json!({"executor":report,"graph":scoped.graph.scoped_completion_report(),
        "seen_b_facts":scoped.graph.witness_count(seen_b),"third_run_bindings":scoped.steps[2].executed_bindings,
        "third_run_changed":scoped.steps[2].changed});
    if !global_observer {
        assert!(scoped.graph.pending_completion_tasks() > 0, "{report}");
        assert_eq!(report["stats"]["runs_with_unrelated_pending"], 2);
        assert!(
            report["stats"]["published_tables_while_pending"]
                .as_u64()
                .unwrap()
                >= 3,
            "{report}"
        );
        assert!(report["pending_anchors"].as_u64().unwrap() > 0, "{report}");
    }
    scoped.execute().unwrap();
    assert_eq!(scoped.graph.pending_completion_tasks(), 0);
    assert_eq!(
        scoped.graph.export().unwrap(),
        reference.graph.export().unwrap()
    );
    assert_eq!(scoped.scoped_execution_report()["retained_contexts"], 0);
    assert_eq!(scoped.scoped_execution_report()["retained_forwards"], 0);
    for (a, b) in scoped.steps.iter().zip(&reference.steps) {
        assert_eq!(a.executed_bindings, b.executed_bindings);
        assert_eq!(a.changed, b.changed);
    }
    if let Ok(path) = std::env::var("SCOPED_EXECUTOR_EVIDENCE") {
        std::fs::write(path, serde_json::to_vec_pretty(&serde_json::json!({
            "scope":"standalone Cell CPU; actual Executor, two independent datatypes, single thread",
            "program_sha256":scoped.graph.program.artifact["sha256"],
            "after_seed":first,"after_b_consumption":third,
            "final_executor":scoped.scoped_execution_report(),
            "final_graph":scoped.graph.scoped_completion_report(),
            "reference_spine":reference.report()["stage_spine"]["stats"],
            "scoped_spine":scoped.report()["stage_spine"]["stats"],
            "final_state_and_ordered_step_bindings_match":true,
            "same_sort_locality_verified":false,"parallel_or_timing_claim":false,
        })).unwrap()).unwrap();
    }
}

#[test]
fn executor_equality_guard_and_source_check_wait_for_deferred_chain() {
    use eggfuse_cell_runtime::executor::Executor;
    let source = EXECUTOR_STAGES.replace(
        "(run-schedule (seq (run seed) (run independent) (run follow) (run observe)))",
        r#"
(ruleset guard)
(datatype Flag (Bad))
(rule ((= x (Ga (Fa (Na 0)))) (= y (Ga (Fa (Na 1)))) (!= x y))
      ((Bad)) :ruleset guard)
(run-schedule (seq (run seed) (run independent) (run guard)))
(check (= (Ga (Fa (Na 0))) (Ga (Fa (Na 1)))))
"#,
    );
    let p = program(&source);
    let mut reference = Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), false);
    let mut scoped = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    scoped.use_scoped_execution().unwrap();
    reference.execute().unwrap();
    scoped.execute().unwrap();
    assert_eq!(
        scoped
            .graph
            .witness_count(table(&scoped.graph.program, "Bad")),
        0
    );
    assert_eq!(
        scoped.graph.export().unwrap(),
        reference.graph.export().unwrap()
    );
}

#[test]
fn deferred_anchor_retirement_recreation_and_forwarding_keep_source_identity() {
    use eggfuse_cell_runtime::executor::Executor;
    let source = EXECUTOR_STAGES.replace(
        "(run-schedule (seq (run seed) (run independent) (run follow) (run observe)))",
        r#"
(ruleset erase) (ruleset recreate)
(rule ((= x (Fa (Na 0)))) ((delete (Ga x))) :ruleset erase)
(rule ((= x (Fa (Na 1)))) ((Ga x)) :ruleset recreate)
(run-schedule (seq (run seed) (run independent) (run follow)
                   (run erase) (run recreate) (run observe)))
"#,
    );
    let p = program(&source);
    let mut reference = Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), false);
    let mut scoped = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    scoped.use_scoped_execution().unwrap();
    reference.execute().unwrap();
    scoped.execute_until(Some(3)).unwrap();
    scoped.execute_until(Some(4)).unwrap();
    let ga = table(&scoped.graph.program, "Ga");
    assert_eq!(scoped.graph.witness_count(ga), 0);
    scoped.execute().unwrap();
    assert_eq!(scoped.graph.witness_count(ga), 1);
    assert_eq!(
        scoped
            .graph
            .witness_count(table(&scoped.graph.program, "SeenA")),
        1
    );
    assert_eq!(
        scoped.graph.export().unwrap(),
        reference.graph.export().unwrap()
    );
    assert_eq!(scoped.scoped_execution_report()["pending_anchors"], 0);
    let left = scoped.report();
    let right = reference.report();
    for key in [
        "anchor_publications",
        "receipt_hits",
        "receipt_redirects",
        "missing_capture_rows",
    ] {
        assert_eq!(
            left["stage_spine"]["stats"][key], right["stage_spine"]["stats"][key],
            "{key}"
        );
    }
}

#[test]
fn final_export_drains_deferred_work_without_an_explicit_dependent_run() {
    use eggfuse_cell_runtime::executor::Executor;
    let source = EXECUTOR_STAGES.replace(
        "(run-schedule (seq (run seed) (run independent) (run follow) (run observe)))",
        "(run-schedule (seq (run seed) (run independent) (run follow)))",
    );
    let p = program(&source);
    let mut reference = Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), false);
    let mut scoped = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    scoped.use_scoped_execution().unwrap();
    reference.execute().unwrap();
    scoped.execute().unwrap();
    assert_eq!(scoped.graph.pending_completion_tasks(), 0);
    assert_eq!(scoped.scoped_execution_report()["pending_anchors"], 0);
    assert_eq!(scoped.scoped_execution_report()["retained_forwards"], 0);
    assert_eq!(
        scoped.graph.export().unwrap(),
        reference.graph.export().unwrap()
    );
    // Completing A during final export retains its source epoch, not B's.
    for w in scoped.graph.witnesses(table(&scoped.graph.program, "Ga")) {
        assert_eq!(scoped.graph.row(w).unwrap().unwrap().epoch, 1);
    }
}

#[test]
fn global_audit_is_an_explicit_fence_and_keeps_ordered_snapshots() {
    use eggfuse_cell_runtime::executor::Executor;
    let p = program(EXECUTOR_STAGES);
    let mut reference = Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), true);
    let mut scoped = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), true);
    scoped.use_scoped_execution().unwrap();
    reference.execute().unwrap();
    scoped.execute().unwrap();
    assert_eq!(scoped.snapshots, reference.snapshots);
    assert_eq!(scoped.binding_audit, reference.binding_audit);
    assert_eq!(
        scoped.scoped_execution_report()["stats"]["runs_with_unrelated_pending"],
        0
    );
    assert_eq!(
        scoped.scoped_execution_report()["stats"]["global_observation_fences"],
        4
    );
}

#[test]
fn source_check_itself_completes_its_scope_after_an_independent_run() {
    use eggfuse_cell_runtime::executor::Executor;
    let source = EXECUTOR_STAGES.replace(
        "(run-schedule (seq (run seed) (run independent) (run follow) (run observe)))",
        "(run-schedule (seq (run seed) (run independent)))\n(check (= (Ga (Fa (Na 0))) (Ga (Fa (Na 1)))))");
    let mut scoped = Executor::new(
        Graph::new_with_scoped_completion(program(&source)).unwrap(),
        false,
    );
    scoped.use_scoped_execution().unwrap();
    scoped.execute_until(Some(2)).unwrap();
    if scoped.scoped_execution_report()["global_observer"] == false {
        assert!(scoped.graph.pending_completion_tasks() > 0);
    }
    scoped.execute().unwrap();
    assert_eq!(scoped.graph.pending_completion_tasks(), 0);
}

#[test]
fn compiler_rejecting_all_deferral_erases_runtime_scope_queries() {
    use eggfuse_cell_runtime::executor::Executor;
    let p = program(
        r#"
(datatype A (Na i64) (Fa A))
(function score (A) i64 :merge (min old new))
(ruleset merge)
(rule ((= x (Na 0)) (= y (Na 1))) ((union x y)) :ruleset merge)
(set (score (Fa (Na 0))) 10)
(set (score (Fa (Na 1))) 20)
(run-schedule (run merge))
"#,
    );
    let mut reference = Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), false);
    let mut scoped = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    scoped.use_scoped_execution().unwrap();
    reference.execute().unwrap();
    scoped.execute().unwrap();
    let report = scoped.scoped_execution_report();
    assert_eq!(report["compiler_admits_deferral"], false);
    assert_eq!(report["stats"]["ruleset_waits"], 0);
    assert_eq!(
        scoped.graph.scoped_completion_report()["stats"]["scope_requests"],
        0
    );
    assert_eq!(
        scoped.graph.export().unwrap(),
        reference.graph.export().unwrap()
    );
}

// One Cell exports to both a deferred A scope and an immediately readable B
// scope. Its promoted continuation must survive partial publication, duplicate
// B output from a later Cell, and eventual publication of the A fragment.
#[cfg(feature = "sparse-cells")]
#[test]
fn cell_completion_shares_one_continuation_across_partial_fragment_publication() {
    use eggfuse_cell_runtime::executor::Executor;
    let source = EXECUTOR_STAGES.replace(
        "((Ga (Fa x)) (Ga (Fa y)) (union x y))",
        "((Ga (Fa x)) (Ga (Fa y)) (Gb (Fb (Nb 0))) (union x y))",
    );
    let p = program(&source);
    let mut reference = Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), false);
    let mut scoped = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    reference.use_entry_publications().unwrap();
    scoped.use_entry_publications().unwrap();
    scoped.use_scoped_execution().unwrap();
    reference.execute().unwrap();
    scoped.execute_until(Some(3)).unwrap();
    let partial = scoped.scoped_execution_report();
    if partial["global_observer"] == false {
        assert!(partial["pending_anchors"].as_u64().unwrap() > 0, "{partial}");
        assert!(partial["retained_contexts"].as_u64().unwrap() > 0, "{partial}");
        assert!(scoped.report()["stage_spine"]["stats"]["fragment_deliveries"].as_u64().unwrap() > 0);
    }
    assert_eq!(scoped.graph.witness_count(table(&scoped.graph.program, "SeenB")), 1);
    scoped.execute().unwrap();
    assert_eq!(scoped.graph.export().unwrap(), reference.graph.export().unwrap());
    for (a, b) in scoped.steps.iter().zip(&reference.steps) {
        assert_eq!(a.executed_bindings, b.executed_bindings);
        assert_eq!(a.changed, b.changed);
    }
    assert_eq!(scoped.scoped_execution_report()["retained_contexts"], 0);
    let report = scoped.report();
    let stats = &report["stage_spine"]["stats"];
    assert_eq!(stats["completion_boundary_records"], stats["completion_boundary_reads"]);
    assert_eq!(stats["fragment_receipts"], stats["fragment_deliveries"]);
    assert_eq!(report["entry_schedule"]["stats"]["fragment_pending_writes"], 0);
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, &source).unwrap();
}

#[cfg(feature = "sparse-cells")]
#[test]
fn inline_function_completion_retires_beside_deferred_cell_outputs() {
    use eggfuse_cell_runtime::executor::Executor;
    let source = r#"
(datatype A (Na i64) (Fa A) (Ga A) (SeenA A))
(datatype B (Nb i64) (SeenB B))
(function score (B) i64 :merge (min old new))
(ruleset seed) (ruleset independent) (ruleset observe)
(rule ((= x (Nb n))) ((set (score x) 1)) :ruleset seed)
(rule ((= x (Na 0)) (= y (Na 1))) ((Ga (Fa x)) (Ga (Fa y)) (union x y)) :ruleset seed)
(rule ((= n (score x))) ((SeenB x)) :ruleset independent)
(rule ((= g (Ga f))) ((SeenA g)) :ruleset observe)
(Na 0) (Na 1) (Nb 0)
(run-schedule (seq (run seed) (run independent) (run observe)))
"#;
    let p = program(source);
    let mut reference = Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), false);
    let mut scoped = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    reference.use_entry_publications().unwrap();
    scoped.use_entry_publications().unwrap();
    scoped.use_port_scopes().unwrap();
    reference.execute().unwrap();
    scoped.execute_until(Some(2)).unwrap();
    let partial = scoped.report();
    let before = &partial["stage_spine"]["stats"];
    assert!(before["inline_function_receipts"].as_u64().unwrap() > 0, "{before}");
    assert_eq!(scoped.graph.witness_count(table(&scoped.graph.program, "SeenB")), 1);
    // Audit-mode features intentionally force a global visibility fence.
    if scoped.scoped_execution_report()["global_observer"] == false {
        assert!(scoped.scoped_execution_report()["pending_anchors"].as_u64().unwrap() > 0);
    }
    assert_eq!(before["inline_function_reads"], before["inline_function_receipts"]);
    scoped.execute().unwrap();
    assert_eq!(scoped.report()["stage_spine"]["stats"]["inline_function_reads"],
        before["inline_function_reads"], "a delivered function cannot be published twice");
    assert_eq!(scoped.graph.export().unwrap(), reference.graph.export().unwrap());
    assert_eq!(scoped.scoped_execution_report()["retained_contexts"], 0);
    for (a, b) in scoped.steps.iter().zip(&reference.steps) {
        assert_eq!(a.executed_bindings, b.executed_bindings);
        assert_eq!(a.changed, b.changed);
    }
    egglog::EGraph::default().parse_and_run_program(None, source).unwrap();
}
