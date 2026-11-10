#![cfg(feature = "sparse-cells")]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};

fn run(source: &str, workers: Option<(usize, usize)>) -> Executor {
    let core = eggfuse_bake::device_frontend::core("cell-query-workers", source).unwrap();
    let program = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let mut e = Executor::new(Graph::new_with_local_congruence(program).unwrap(), true);
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
}
#[test]
fn uncovered_constructor_and_enumeration_queries_keep_all_answers() {
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
    assert_eq!(stats["entry_headers"], 0);
    assert_eq!(stats["entry_mask_checks"], 0);
    assert_eq!(stats["cell_source_reads"], 0);
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
