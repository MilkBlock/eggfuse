#![cfg(feature = "sparse-cells")]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};

fn run(source: &str, workers: Option<(usize, usize)>) -> Executor {
    run_mode(source, workers, true)
}
fn run_mode(source: &str, workers: Option<(usize, usize)>, stable: bool) -> Executor {
    let core = eggfuse_bake::device_frontend::core("cell-query-workers", source).unwrap();
    let program = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let graph = if stable { Graph::new_with_local_congruence(program) } else { Graph::new(program) };
    let mut e = Executor::new(graph.unwrap(), true);
    if let Some((workers, grain)) = workers { e.use_query_workers(workers, grain).unwrap(); }
    e.execute().unwrap();
    e
}
fn same(a: &Executor, b: &Executor) {
    assert_eq!(a.graph.export().unwrap(), b.graph.export().unwrap());
    assert_eq!(a.snapshots, b.snapshots, "source Run visibility");
    assert_eq!(a.binding_audit, b.binding_audit, "ordered bindings, not only the final graph");
    assert_eq!(a.steps.len(), b.steps.len());
    for (a,b) in a.steps.iter().zip(&b.steps) {
        for k in ["ordinal","ruleset","path","iterations","epoch","logical_matches","executed_bindings","changed"] {
            assert_eq!(a[k], b[k], "{k}");
        }
    }
}
#[test]
fn point_queries_keep_mutation_boundaries_delta_ownership_and_result_aliases() {
    let source = include_str!("fixtures/cell-point-queries.egg");
    let before = run(source, None);
    for workers in [1,2,4] {
        for grain in [1,16] {
            let after = run(source, Some((workers,grain)));
            same(&before, &after);
            let report = after.report();
            let stats = &report["query_workers"]["stats"];
            assert!(stats["answers"].as_u64().unwrap() > 0);
            assert!(stats["point_reads"].as_u64().unwrap() > stats["answers"].as_u64().unwrap());
            assert!(stats["owner_rejections"].as_u64().unwrap() > 0);
            assert_eq!(stats["entries"].as_u64().unwrap(), stats["worker_entries"].as_array().unwrap()
                .iter().map(|v| v.as_u64().unwrap()).sum::<u64>() + stats["coordinator_entries"].as_u64().unwrap());
        }
    }
}
#[test]
fn small_cell_runs_execute_inline_without_spawning_more_work() {
    let source = include_str!("fixtures/cell-point-queries.egg");
    let before = run(source, None);
    let after = run(source, Some((4,4096)));
    same(&before, &after);
    let (a,b) = (before.report(),after.report());
    assert_eq!(a["stats"], b["stats"]);
    assert_eq!(a["key_lookup_calls"], b["key_lookup_calls"]);
    let q = &b["query_workers"]["stats"];
    assert_eq!(q["entries"], q["coordinator_entries"]);
    assert!(q["entries"].as_u64().unwrap() > 0);
    assert!(q["worker_entries"].as_array().unwrap().iter().all(|v| v == 0));
    assert_eq!(q["cell_task_probes"], 0, "small Runs never build a Cell grouping index");
    assert_eq!(q["ungrouped_inline_entries"], q["spine_entries"]);
}

#[test]
fn empty_cell_completions_do_not_hide_later_inputs_or_keep_old_values() {
    let source = r#"
(datatype E (N i64) (Start E) (Gate E))
(function Cost (E) i64 :merge new)
(function Out (E) i64 :merge new)
(ruleset make) (ruleset see) (ruleset fill) (ruleset change)
(rule ((Start x)) ((Gate x)) :ruleset make)
(rule ((Gate x) (= c (Cost x)) (> c 0)) ((set (Out x) c)) :ruleset see)
(rule ((Start x)) ((set (Cost x) 7)) :ruleset fill)
(rule ((Start x)) ((set (Cost x) 9)) :ruleset change)
(Start (N 0)) (Start (N 1))
(set (Cost (N 0)) -1) (set (Cost (N 1)) -1)
(run-schedule (seq (run make) (run see) (run fill) (run see)))
(check (= (Out (N 0)) 7) (= (Out (N 1)) 7))
(run-schedule (seq (run change) (run see)))
(check (= (Out (N 0)) 9) (= (Out (N 1)) 9))
"#;
    let before = run(source, None);
    for workers in [1, 2, 4] {
        let after = run(source, Some((workers, 1)));
        same(&before, &after);
        let report = after.report();
        let stats = &report["query_workers"]["stats"];
        assert!(stats["spine_entries"].as_u64().unwrap() > stats["completion_headers"].as_u64().unwrap());
        assert!(stats["completion_headers"].as_u64().unwrap() > 0);
        assert_eq!(stats["completion_slot_initializations"], 0);
        assert_eq!(stats["completion_slot_writes"], 0);
    }
}
#[test]
fn constructor_points_and_residual_enumeration_keep_all_answers() {
    let source = r#"
(datatype E (Leaf i64) (Wrap E))
(function Cost (E) i64 :merge new)
(relation Edge (E E)) (relation Found (E E i64))
(ruleset see)
(rule ((Edge x y) (= n (Cost x)) (= z (Wrap y))) ((Found x z n)) :ruleset see)
(Edge (Leaf 0) (Leaf 1)) (Edge (Leaf 0) (Leaf 2))
(Wrap (Leaf 1)) (Wrap (Leaf 2)) (set (Cost (Leaf 0)) 7)
(run-schedule (run see))
(check (Found (Leaf 0) (Wrap (Leaf 1)) 7) (Found (Leaf 0) (Wrap (Leaf 2)) 7))
"#;
    let after = run(source, Some((2,1)));
    same(&run(source,None), &after);
    let report = after.report();
    let stats = &report["query_workers"]["stats"];
    assert!(stats["entries"].as_u64().unwrap() > 0);
    // Without complete stable ownership the same constructor queries still
    // use the exhaustive serial host, including its residual enumeration.
    let ordinary = run_mode(source, Some((2,1)), false);
    same(&run_mode(source, None, false), &ordinary);
    assert_eq!(ordinary.report()["query_workers"]["stats"]["constructors"]["lookups"], 0);
}

#[test]
fn constructor_domains_follow_both_aliases_visibility_and_recreation() {
    let mut source = String::from(r#"
(datatype E (N i64) (Start E) (Gate E) (Pair E E i64))
(function Cost (E) i64 :merge new)
(function Out (E) i64 :merge new)
(ruleset make) (ruleset see) (ruleset first) (ruleset second)
(ruleset hide) (ruleset remove) (ruleset restore)
(rule ((Start x)) ((Gate x)) :ruleset make)
(rule ((Gate x) (= y (N 7)) (= p (Pair x y 5)) (= c (Cost p))) ((set (Out x) c)) :ruleset see)
(rule ((= x (N i)) (>= i 0) (< i 32) (= j (+ i 1000))) ((union x (N j))) :ruleset first)
(rule ((= x (N 7)) (= y (N 80))) ((union x y)) :ruleset second)
(rule ((= x (N 0)) (= y (N 7))) ((subsume (Pair x y 5)) (set (Cost (Pair x y 6)) 999)) :ruleset hide)
(rule ((= x (N 1)) (= y (N 7))) ((delete (Pair x y 5))) :ruleset remove)
(rule ((= x (N 1)) (= y (N 7))) ((set (Cost (Pair x y 5)) 77)) :ruleset restore)
"#);
    for i in 0..32 {
        source += &format!("(Start (N {i})) (set (Cost (Pair (N {}) (N 80) 5)) {})\n",i+1000,i+1);
    }
    source += "(N 7)\n";
    // The first equality is insufficient: every corresponding input and the
    // scalar guard must hold. Birth hashes are deliberately no longer current.
    source += "(run-schedule (seq (run make) (run see) (run first) (run see) (run second) (run see)))\n";
    for i in 0..32 { source += &format!("(check (= (Out (N {i})) {}))\n",i+1); }
    source += r#"
(run-schedule (seq (run hide) (run see) (run remove) (run see) (run restore) (run see)))
"#;
    let before = run(&source, None);
    for workers in [1,2,4] {
        let after = run(&source, Some((workers,16)));
        same(&before, &after);
        let r = after.report();
        let work = &r["query_workers"]["stats"]["constructors"];
        assert!(work["lookups"].as_u64().unwrap() > 0);
        assert!(work["domains"].as_u64().unwrap() > 0);
        assert!(work["signal_visits"].as_u64().unwrap() > 0);
        assert!(work["candidate_pushes"].as_u64().unwrap() > 0);
    }
}

#[test]
fn stage_entries_keep_guards_late_ports_and_ordered_winners() {
    let source = r#"
(datatype E (N i64) (Start E i64) (Gateway E i64) (Mark E))
(function score (E) i64 :merge old)
(function next (i64) E :merge old)
(ruleset make) (ruleset consume) (ruleset fill)
(rule ((= n (N 9))) ((set (next 3) n)) :ruleset fill)
(rule ((Start x i)) ((Mark x) (Gateway x i)) :ruleset make)
(rule ((Gateway x i) (= j (score x)) (= y (next j)) (= k (+ i j)) (> k 5))
      ((Mark x)) :ruleset consume)
(Start (N 1) 10) (Start (N 2) -10) (Start (N 3) 10)
(set (score (N 1)) 1) (set (score (N 2)) 2) (set (score (N 3)) 3)
(set (next 1) (N 9)) (set (next 2) (N 9))
(run-schedule (seq (run make) (run consume) (run fill) (run consume)))
(check (Mark (N 1)) (Mark (N 2)) (Mark (N 3)))
"#;
    let before = run(source, None);
    for workers in [1,2,4] {
        let after = run(source, Some((workers,1)));
        same(&before, &after);
        let report = after.report();
        assert!(report["query_workers"]["stats"]["spine_entries"].as_u64().unwrap() > 0);
        assert_eq!(before.report()["stage_spine"]["stats"]["cell_query_steps"],
            report["stage_spine"]["stats"]["cell_query_steps"]);
    }
}

#[test]
fn one_cell_runs_entries_for_multiple_rules_before_any_rhs_writes() {
    let mut source = String::from(r#"
(datatype E (N i64) (Start E) (Gate E) (Gate2 E))
(function Cost (E) i64 :merge new)
(function Out1 (E) i64 :merge new)
(function Out2 (E) i64 :merge new)
(function Out3 (E) i64 :merge new)
(ruleset make) (ruleset consume)
(rule ((Start x)) ((Gate x) (Gate2 x)) :ruleset make)
(rule ((Gate x) (= c (Cost x))) ((set (Cost x) (+ c 10)) (set (Out1 x) c)) :ruleset consume)
(rule ((Gate2 x) (= c (Cost x))) ((set (Out2 x) c)) :ruleset consume)
(rule ((Gate x) (= c (Cost x)) (= n (+ c 1))) ((set (Out3 x) n)) :ruleset consume)
"#);
    // One producer reuses a constructor in a different physical Cell. Grouping
    // must use actual source identity, without changing the returned binding.
    source += "(Gate2 (N 0))\n";
    for i in 0..32 { source += &format!("(Start (N {i})) (set (Cost (N {i})) {})\n", i+1); }
    source += "(run-schedule (seq (run make) (run consume)))\n";
    for i in 0..32 {
        source += &format!("(check (= (Out1 (N {i})) {0}) (= (Out2 (N {i})) {0}) (= (Out3 (N {i})) {1}))\n",i+1,i+2);
    }
    source += "(run-schedule (run consume))\n";
    for i in 0..32 {
        source += &format!("(check (= (Out1 (N {i})) {0}) (= (Out2 (N {i})) {0}) (= (Out3 (N {i})) {1}))\n",i+11,i+12);
    }
    let before = run(&source, None);
    for workers in [1,2,4] {
        let after = run(&source, Some((workers,16)));
        same(&before, &after);
        let report = after.report();
        let stats = &report["query_workers"]["stats"];
        assert!(stats["cross_rule_cells"].as_u64().unwrap() >= 31, "{stats}");
        assert!(stats["max_entries_per_cell"].as_u64().unwrap() >= 3);
        assert!(stats["spine_entries"].as_u64().unwrap() >= 95);
        assert!(stats["seed_range_comparisons"].as_u64().unwrap() > 0);
    }
}
