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
fn completed_matches_share_the_run_worker_invocation_without_answer_packets() {
    let source = format!(r#"{HEADER}
(rule ((= x (N n)))
 ((let a (+ n 1)) (F x a) (let b (* a 2)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
(check (= (Out (N 2)) 6))
"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for (workers, grain) in [(1, 1), (2, 1), (4, 64)] {
        let mut candidate = executor(&source, workers);
        candidate.use_cell_execution(grain).unwrap();
        candidate.execute().unwrap();
        same(&control, &candidate);
        let report = candidate.report();
        let stats = &report["query_workers"]["stats"];
        let matched = &report["query_workers"]["matched"];
        assert_eq!(matched["execution"]["operations"], 128, "{report}");
        assert_eq!(matched["execution"]["later_operations"], 64);
        assert_eq!(matched["matched_only_invocations"], 1);
        assert_eq!(stats["answers"], 0, "existing matches produce no second answer vector");
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 64);
        assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 64);
        assert_eq!(report["cell_execution"]["runtime"]["stats"]["worker_segments"], 0);
        assert_eq!(matched[if workers > 1 { "worker_operations" } else { "inline_operations" }], 128);
    }
}

#[test]
fn completed_matches_and_cross_stage_queries_use_one_mixed_invocation() {
    let source = format!(r#"{HEADER}
(datatype Gated (Gate E))
(ruleset make)
(rule ((Start x)) ((Gate x)) :ruleset make)
(rule ((= x (N n))) ((let a (+ n 1)) (set (Out x) a)) :ruleset step)
(rule ((Gate x) (= n (Input x))) ((let b (+ n 3)) (set (Current x) b)) :ruleset step)
{}
(run-schedule (seq (run make) (run step)))
(check (= (Out (N 2)) 3) (= (Current (N 2)) 5))
"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for workers in [1, 4] {
        let mut candidate = executor(&source, workers);
        candidate.execute().unwrap();
        same(&control, &candidate);
        let report = candidate.report();
        let stats = &report["query_workers"]["stats"];
        assert!(report["query_workers"]["matched"]["mixed_invocations"].as_u64().unwrap() > 0, "{report}");
        assert!(stats["answers"].as_u64().unwrap() > 0);
        assert!(report["query_workers"]["matched"]["execution"]["operations"].as_u64().unwrap() > 0);
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 128);
    }
}

#[test]
fn completed_matches_defer_scalar_failure_until_after_the_original_shared_effect() {
    let source = format!(r#"{HEADER}
(rule ((= x (N n)))
 ((let a (+ n 1)) (set (Current x) a) (let b (/ a 0)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
"#, initial());
    let mut control = executor(&source, 0);
    let error = control.execute().unwrap_err();
    for workers in [1, 4] {
        let mut candidate = executor(&source, workers);
        candidate.use_cell_execution(1).unwrap();
        assert_eq!(candidate.execute().unwrap_err(), error);
        assert_eq!(candidate.graph.export().unwrap(), control.graph.export().unwrap());
        let report = candidate.report();
        assert_eq!(report["query_workers"]["matched"]["execution"]["later_deferred_failures"], 64);
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 1,
            "speculation for later bindings must not count as consumed work");
    }
}

#[test]
fn accepted_matches_keep_captured_scalars_when_an_earlier_rhs_deletes_their_source() {
    let source = format!(r#"{HEADER}
(rule ((= x (N n))) ((delete (N n))) :ruleset step)
(rule ((= x (N n))) ((let a (+ n 1)) (F x a) (set (Out x) a)) :ruleset step)
{}
(run-schedule (run step))
"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for workers in [1, 4] {
        let mut candidate = executor(&source, workers);
        candidate.execute().unwrap();
        same(&control, &candidate);
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 64,
            "deleting an earlier witness must not cancel accepted source-Run bindings");
        assert!(candidate.report()["query_workers"]["matched"]["execution"]["operations"]
            .as_u64().unwrap() >= 64);
    }
}

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
    assert_eq!(b.graph.stats.prepared_rhs_later_operations, 64);
    assert_eq!(b.report()["query_workers"]["stats"]["execution"]["later_operations"], 64);
    assert_eq!(b.report()["query_workers"]["stats"]["execution"]["frame_growths"], 0);
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
        "cell-execution-boundaries/v2"
    );
    Program::parse(encoded.clone()).unwrap();
    let mut legacy = encoded.clone();
    legacy["cell_execution"]["schema"] = "cell-execution-boundaries/v1".into();
    for rule in legacy["cell_execution"]["rules"].as_array_mut().unwrap() {
        rule.as_object_mut().unwrap().remove("input_ready");
    }
    Program::parse(legacy).unwrap();
    let mut forged = encoded.clone();
    forged["cell_execution"]["rules"][0]["input_ready"] = serde_json::json!([1]);
    assert!(Program::parse(forged).err().unwrap().contains("execution boundaries"));
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
(rule ((Gate x) (= n (Input x))) ((let a (+ n 1)) (F x a) (let b (+ a 0)) (F x b)) :ruleset consume)
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
            e.use_cell_execution(1).unwrap();
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
    assert!(b.graph.stats.prepared_rhs_later_operations > 0);
    assert!(
        b.report()["entry_schedule"]["stats"]["entry_publication_writes"]
            .as_u64()
            .unwrap()
            > 0,
        "this test must exercise actual owned Entry publication"
    );
}

#[test]
fn prepared_later_results_survive_union_and_publication_without_worker_round_trips() {
    let source = format!(
        r#"{HEADER}
(ruleset observe)
(rule ((Start x) (= n (Input x)))
 ((let a (+ n 1)) (let f (F x a)) (let b (* a 2))
  (union f x) (let c (+ b 3)) (F f c) (set (Out x) c)) :ruleset step)
(rule ((= f (F x n))) ((set (Current f) n)) :ruleset observe)
{} (F (N 0) 1)
(run-schedule (seq (run step) (run observe)))
(check (= (Out (N 2)) 9) (= (F (N 2) 3) (N 2)))
"#,
        initial()
    );
    egglog::EGraph::default()
        .parse_and_run_program(None, &source)
        .unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for (workers, grain) in [(1, 1), (2, 1), (4, 1), (4, 64)] {
        let mut candidate = executor(&source, workers);
        candidate.use_cell_execution(grain).unwrap();
        candidate.execute().unwrap();
        same(&control, &candidate);
        let report = candidate.report();
        let counts = &report["cell_execution"]["runtime"]["stats"];
        assert_eq!(counts["local_operations"], 0);
        assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 128);
        assert!(
            counts["boundaries"][3].as_u64().unwrap() > 0,
            "union remains a real boundary"
        );
        assert_eq!(
            candidate.graph.stats.union_requests,
            control.graph.stats.union_requests
        );
        assert_eq!(counts["worker_operations"], 0);
        assert_eq!(counts["worker_segments"], 0);
    }
}

#[test]
fn boundary_scalar_result_resumes_with_private_constructor_and_writer_owners() {
    for prefix in ["", "(F x n)", "(set (Input x) (+ n 100))"] {
        let source = format!(r#"{HEADER}
(function Flag (E) bool :merge new)
(rule ((Start x) (= n (Input x)))
 ({prefix} (let a (bool-< n 1000)) (let b (and a true)) (F x (+ n 1)) (set (Flag x) b)) :ruleset step)
{} (run-schedule (run step)) (check (= (Flag (N 2)) true))"#, initial());
        egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
        for ownership in [false,true] {
        let mut control = executor(&source,0);
        if ownership { control.graph.use_cell_ownership().unwrap(); }
        control.execute().unwrap();
        for workers in [2,4] {
            let mut candidate = executor(&source,workers);
            if ownership { candidate.graph.use_cell_ownership().unwrap(); }
            candidate.use_cell_execution(1).unwrap();
            candidate.execute().unwrap();
            same(&control,&candidate);
            let r = candidate.report();
            let work = &r["cell_execution"]["runtime"]["stats"];
            let s = &candidate.graph.stats;
            assert!(s.rhs_context_suspends > 0, "fixture must exercise actual RHS dispatch: {prefix}");
            assert_eq!(work["worker_segments"].as_u64().unwrap(),s.rhs_context_suspends);
            assert_eq!(s.rhs_context_resumes,s.rhs_context_suspends);
            assert_eq!(s.rhs_suspend_holds,s.rhs_suspend_releases);
            if prefix.is_empty() { assert!(s.rhs_suspend_private > 0); }
            else { assert!(s.rhs_suspend_public > 0); }
            if prefix.starts_with("(set") { assert!(s.rhs_suspend_promotions > 0); }
            println!("suspension {}",serde_json::json!({"prefix":prefix,"workers":workers,"ownership":ownership,
                "suspends":s.rhs_context_suspends,"resumes":s.rhs_context_resumes,
                "private":s.rhs_suspend_private,"public":s.rhs_suspend_public,
                "promotions":s.rhs_suspend_promotions,"holds":s.rhs_suspend_holds,
                "releases":s.rhs_suspend_releases,"worker_operations":work["worker_operations"]}));
        }
        }
    }
}

#[test]
fn a_worker_failure_after_a_shared_effect_preserves_the_exact_source_prefix() {
    for tail in [
        "(let b (/ a 0)) (set (Out x) b)",
        "(let b (* a 2)) (panic \"stop\")",
    ] {
        let source = format!(
            r#"{HEADER}
(rule ((Start x) (= n (Input x)))
 ((let a (+ n 1)) (F x a) {tail}) :ruleset step)
{} (run-schedule (run step))
"#,
            initial()
        );
        let mut control = executor(&source, 0);
        let error = control.execute().unwrap_err();
        for workers in [1, 2, 4] {
            let mut candidate = executor(&source, workers);
            candidate.use_cell_execution(1).unwrap();
            assert_eq!(candidate.execute().unwrap_err(), error);
            assert_eq!(
                candidate.graph.export().unwrap(),
                control.graph.export().unwrap()
            );
            assert_eq!(
                candidate.graph.stats.constructor_requests,
                control.graph.stats.constructor_requests
            );
            let report = candidate.report();
            let counts = &report["cell_execution"]["runtime"]["stats"];
            if tail.contains("/ a") {
                assert_eq!(counts["failures"], 1);
            } else {
                assert!(counts["boundaries"][5].as_u64().unwrap() > 0);
            }
        }
    }
}

#[test]
fn query_prepares_later_scalar_chains_without_an_initial_prefix_or_worker_round_trip() {
    let source = format!(r#"{HEADER}
(rule ((Start x) (= n (Input x)))
 ((F x n) (let a (+ n 1)) (let b (* a 2)) (set (Out x) b)) :ruleset step)
{} (run-schedule (run step)) (check (= (Out (N 2)) 6))"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for workers in [1, 2, 4] {
        for resume in [false, true] {
            let mut candidate = executor(&source, workers);
            if resume { candidate.use_cell_execution(1).unwrap(); }
            candidate.execute().unwrap();
            same(&control, &candidate);
            assert_eq!(candidate.graph.stats.prepared_rhs_operations, 0);
            assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 128);
            let r = candidate.report();
            assert_eq!(r["query_workers"]["stats"]["execution"]["later_operations"], 128);
            assert_eq!(r["query_workers"]["stats"]["execution"]["frame_growths"], 0);
            if resume {
                assert_eq!(r["cell_execution"]["runtime"]["stats"]["worker_segments"], 0);
                assert_eq!(r["cell_execution"]["runtime"]["stats"]["local_operations"], 0);
            }
        }
    }
}

#[test]
fn early_visibility_stop_discards_prepared_results_and_does_not_raise_future_errors() {
    for tail in ["(let a (+ n 1))", "(let a (/ n 0))"] {
        let source = format!(r#"{HEADER}
(rule ((Start x) (= n (Input x)))
 ((F x n) (delete (F x 1000)) {tail} (set (Out x) a)) :ruleset step)
{} (run-schedule (run step))"#, initial());
        let mut control = executor(&source, 0);
        control.execute().unwrap();
        let mut candidate = executor(&source, 4);
        candidate.use_cell_execution(1).unwrap();
        candidate.execute().unwrap();
        same(&control, &candidate);
        assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 0);
        let r = candidate.report();
        let prepared = &r["query_workers"]["stats"]["execution"];
        if tail.contains('/') {
            assert_eq!(prepared["later_deferred_failures"], 64);
        } else { assert_eq!(prepared["later_operations"], 64); }
        assert_eq!(r["cell_execution"]["runtime"]["stats"]["failures"], 0);
    }
}

#[test]
fn a_single_write_consumes_prepared_slots_between_unprepared_primitives() {
    let source = format!(r#"{HEADER}
(function Flag (E) bool :merge old)
(rule ((Start x) (= n (Input x)))
 ((let p (bool-< n 1000)) (let a (+ n 1))
  (let q (bool-< a 1000)) (let both (and p q)) (set (Flag x) both)) :ruleset step)
{} (run-schedule (run step)) (check (= (Flag (N 2)) true))"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for workers in [1, 2, 4] {
        let mut candidate = executor(&source, workers);
        candidate.execute().unwrap();
        same(&control, &candidate);
        assert_eq!(candidate.graph.stats.single_writes, 64);
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 0);
        assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 64);
        assert_eq!(candidate.report()["query_workers"]["stats"]["execution"]["later_operations"], 64);
    }
}
