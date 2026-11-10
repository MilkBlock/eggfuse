use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use serde_json::Value;

fn check_runs(source: &str, stages: &[&str]) {
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, source).unwrap();
    let anchors = native.capture_device_anchors().unwrap();
    let expected: Vec<_> = stages.iter().map(|set| {
        native.parse_and_run_program(None, &format!("(run-schedule (run {set}))")).unwrap();
        native.device_checkpoint(&anchors).unwrap()
    }).collect();
    let source = format!("{source}\n(run-schedule (seq {}))", stages.iter()
        .map(|set| format!("(run {set})")).collect::<Vec<_>>().join(" "));
    let core = eggfuse_bake::device_frontend::core("collision-delta", &source).unwrap();
    let compiled = compiler::compile(core, &Default::default()).unwrap();
    #[cfg(feature = "sparse-cells")]
    let modes = [0, 1, 4];
    #[cfg(not(feature = "sparse-cells"))]
    let modes = [0];
    for stable in [false, true] {
        for workers in modes {
            let program = Program::parse(compiled.clone()).unwrap();
            let graph = if stable { Graph::new_with_local_congruence(program) } else { Graph::new(program) };
            let mut e = Executor::new(graph.unwrap(), true);
            #[cfg(feature = "sparse-cells")]
            if workers != 0 { e.use_query_workers(workers, 1).unwrap(); }
            e.execute().unwrap();
            for (i, (actual, expected)) in e.snapshots.iter().zip(&expected).enumerate() {
                // These fixtures create all Eq values before execution. Map native
                // initial anchors through the current Cell roots, never by row order.
                let actual_anchors = actual["anchors"].as_array().unwrap();
                let native_anchors = expected["anchors"].as_array().unwrap();
                let root = |old: &Value| -> Value { actual_anchors.iter()
                    .find(|a| a["old"] == *old).expect("initial Eq anchor")["now"].clone() };
                // Check the partition independently: mapping expected rows through
                // actual roots alone could conceal an extra or missing union.
                for a in native_anchors {
                    for b in native_anchors {
                        assert_eq!(a["now"] == b["now"], root(&a["old"]) == root(&b["old"]),
                            "Run {} Eq partition", i + 1);
                    }
                }
                let mut expected = expected["rows"].clone();
                for row in expected.as_array_mut().unwrap() {
                    for v in row["values"].as_array_mut().unwrap() {
                        if let Some(old) = v["eq"].as_str() {
                            v["eq"] = actual["anchors"].as_array().unwrap().iter()
                                .find(|a| a["old"] == old).expect("initial Eq anchor")["now"].clone();
                        }
                    }
                }
                let rows = |v: &Value| {
                    let mut rows: Vec<_> = v.as_array().unwrap().iter().map(|row| {
                        let mut row = row.clone();
                        row.sort_all_objects();
                        row.to_string()
                    }).collect();
                    rows.sort();
                    rows
                };
                assert_eq!(rows(&actual["rows"]), rows(&expected),
                    "Run {} {}, stable={stable}, workers={workers}", i + 1, stages[i]);
            }
            assert_eq!(e.snapshots.len(), expected.len());
        }
    }
}

#[test]
fn unchanged_constructor_collision_does_not_refire_fill() {
    check_runs(r#"
(datatype E (N i64) (Start E) (Wrap E))
(function Cost (E) i64 :merge new)
(function Out (E) i64 :merge new)
(ruleset fill) (ruleset change) (ruleset see) (ruleset join)
(rule ((Start x)) ((set (Cost x) 1)) :ruleset fill)
(rule ((Start x)) ((set (Cost x) 2)) :ruleset change)
(rule ((= c (Cost x)) (= w (Wrap x))) ((set (Out x) c)) :ruleset see)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset join)
(Start (N 0)) (Start (N 1)) (Start (N 2))
(Wrap (N 0)) (Wrap (N 2))
"#, &["fill", "see", "change", "see", "join", "see", "fill", "see"]);
}

#[test]
fn function_collision_only_refires_when_the_merged_value_changes() {
    for initial in [2, 3] {
        check_runs(&format!(r#"
(datatype E (N i64))
(function Cost (E) i64 :merge (min old new))
(function Out (E) i64 :merge new)
(ruleset fill) (ruleset change) (ruleset join)
(rule ((= c (Cost x))) ((set (Out x) 1)) :ruleset fill)
(rule ((= c (Cost x))) ((set (Out x) 2)) :ruleset change)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset join)
(set (Cost (N 0)) {initial}) (set (Cost (N 1)) 2)
"#), &["fill", "change", "join", "fill"]);
    }
}

#[test]
fn duplicate_relation_retirement_is_not_a_new_match() {
    check_runs(r#"
(datatype E (N i64))
(relation Start (E))
(function Out (E) i64 :merge new)
(ruleset fill) (ruleset change) (ruleset join)
(rule ((Start x)) ((set (Out x) 1)) :ruleset fill)
(rule ((Start x)) ((set (Out x) 2)) :ruleset change)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset join)
(Start (N 0)) (Start (N 1))
"#, &["fill", "change", "join", "fill"]);
}

#[test]
fn congruence_outputs_still_enable_parent_matches() {
    check_runs(r#"
(datatype E (N i64) (Start E) (Wrap E) (Gate E))
(function Out (E) i64 :merge new)
(ruleset fill) (ruleset join)
(rule ((Wrap x) (Gate x)) ((set (Out x) 1)) :ruleset fill)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset join)
(Wrap (Start (N 0))) (Gate (Start (N 1)))
"#, &["fill", "join", "fill"]);
}

#[test]
fn collision_still_transfers_hidden_state() {
    check_runs(r#"
(datatype E (N i64) (Start E))
(function Out (E) i64 :merge new)
(ruleset fill) (ruleset join)
(rule ((Start x)) ((set (Out x) 1)) :ruleset fill)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset join)
(Start (N 0)) (Start (N 1)) (subsume (Start (N 1)))
"#, &["fill", "join", "fill"]);
}

#[test]
fn original_refill_source_checks_match_native() {
    let source = include_str!("../../../benchmarks/cell-point-support/baseline-refill.egg");
    egglog::EGraph::default().parse_and_run_program(None, source).unwrap();
    let core = eggfuse_bake::device_frontend::core("baseline-refill", source).unwrap();
    let compiled = compiler::compile(core, &Default::default()).unwrap();
    for audit in [false, true] {
        for stable in [false, true] {
            let program = Program::parse(compiled.clone()).unwrap();
            let graph = if stable { Graph::new_with_local_congruence(program) } else { Graph::new(program) };
            Executor::new(graph.unwrap(), audit).execute().unwrap();
        }
    }
}
