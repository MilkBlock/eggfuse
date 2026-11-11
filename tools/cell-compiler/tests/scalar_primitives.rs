//! Native differential tests: operations execute in a rule, not bootstrap.
use eggfuse_cell_runtime::{
    compiler,
    executor::Executor,
    graph::Graph,
    program::Program,
    value::{self, FloatBits, Value},
};
use serde_json::{Value as J, json};
use std::collections::{BTreeSet, HashSet};

fn differential(sort: &str, expression: &str) {
    let source =
        format!("(function Out () {sort} :merge old) (rule () ((set (Out) {expression}))) (run 1)");
    let core = eggfuse_bake::device_frontend::core("scalar-test", &source).unwrap();
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut cpu = Executor::new(Graph::new(p).unwrap(), false);
    cpu.execute()
        .unwrap_or_else(|e| panic!("{expression}: {e}"));
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, &source).unwrap();
    let rows = cpu.graph.export().unwrap()["rows"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["table"] == "Out")
        .cloned()
        .collect::<Vec<_>>();
    assert_eq!(
        json!(rows),
        native.device_snapshot_tables(&["Out".into()]).unwrap(),
        "{expression}"
    );
}

#[test]
fn scalar_operations_match_native() {
    for (sort, expressions) in [
        (
            "i64",
            vec![
                "(+ 3 8)",
                "(- 3 8)",
                "(* -3 8)",
                "(/ -11 3)",
                "(% -11 3)",
                "(min -5 2)",
                "(max -5 2)",
                "(& -7 3)",
                "(| 7 8)",
                "(^ 7 3)",
                "(<< 1 63)",
                "(>> -7 2)",
                "(not-i64 0)",
                "(abs -9)",
                "(log2 9)",
                "(to-i64 -3.9)",
                "(to-i64 (^ -1.0 0.5))",
                "(to-i64 (^ 1.0e308 2.0))",
                "(count-matches \"ééa\" \"é\")",
                "(count-matches \"ab\" \"\")",
            ],
        ),
        (
            "f64",
            vec![
                "(+ 1.5 9.2)",
                "(- 1.5 9.2)",
                "(* -1.5 2.0)",
                "(/ 12.5 2.0)",
                "(% -12.5 2.0)",
                "(^ 9.0 2.5)",
                "(neg 0.0)",
                "(abs -1.5)",
                "(to-f64 9223372036854775807)",
                "(min -1.0 2.0)",
                "(max -1.0 2.0)",
                "(^ -1.0 0.5)",
                "(min (^ -1.0 0.5) 1.0)",
                "(max (^ -1.0 0.5) 1.0)",
                "(^ 1.0e308 2.0)",
            ],
        ),
        (
            "String",
            vec![
                "(to-string -42)",
                "(to-string 1.0)",
                "(to-string (neg 0.0))",
                "(to-string -0.0)",
                "(to-string (* -1.0e-308 1.0e-308))",
                "(to-string (^ -1.0 0.5))",
                "(to-string (^ 1.0e308 2.0))",
                "(+)",
                "(+ \"a\" \"é\" \"z\")",
                "(replace \"ééa\" \"é\" \"x\")",
            ],
        ),
        (
            "bool",
            vec![
                "(not true)",
                "(and true false)",
                "(or)",
                "(or false true false)",
                "(xor true true)",
                "(=> false true)",
                "(bool-= 3 3)",
                "(bool-!= \"a\" \"b\")",
                "(bool-< -3 2)",
                "(bool-> -3 2)",
                "(bool-<= 2 2)",
                "(bool->= 3 2)",
            ],
        ),
        (
            "Unit",
            vec![
                "(guard true)",
                "(< -1.0 2.0)",
                "(>= 2.0 2.0)",
                "(!= 1.0 2.0)",
                "(value-eq 1.0 1.0)",
            ],
        ),
    ] {
        for e in expressions {
            differential(sort, e);
        }
    }
}

#[test]
fn failed_primitives_reject_queries_without_aborting_the_run() {
    for expr in [
        "(/ x 0)",
        "(% x 0)",
        "(<< x -1)",
        "(>> x 64)",
        "(+ x 9223372036854775807)",
        "(abs -9223372036854775808)",
        "(/ 1.0 0.0)",
        "(% 1.0 -0.0)",
        "(guard false)",
        "(< 2.0 1.0)",
    ] {
        let source = format!(
            "(relation Input (i64)) (relation Hit ()) (Input 1)
            (rule ((Input x) (= y {expr})) ((Hit))) (run 1)"
        );
        let core = eggfuse_bake::device_frontend::core("failed-query", &source).unwrap();
        let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
        let mut cpu = Executor::new(Graph::new(p).unwrap(), false);
        cpu.execute().unwrap();
        let mut native = egglog::EGraph::default();
        native.parse_and_run_program(None, &source).unwrap();
        assert_eq!(native.get_size("Hit"), 0);
        assert!(
            !cpu.graph.export().unwrap()["rows"]
                .as_array()
                .unwrap()
                .iter()
                .any(|r| r["table"] == "Hit"),
            "{expr}"
        );
    }
    assert!(value::primitive("log2", &[Value::Int(0)], "i64", &J::Null).is_err());
}

#[test]
fn float_identity_and_typed_admission() {
    let f = |bits: u64| Value::Float(FloatBits(bits as i64));
    let values = [
        f(0),
        f((-0.0f64).to_bits()),
        f(f64::NAN.to_bits()),
        f(0xfff8000000000001),
    ];
    assert_eq!(values.into_iter().collect::<HashSet<_>>().len(), 2);
    assert!(value::scalar_signature("+", &["f64", "f64"], "f64"));
    assert!(!value::scalar_signature("+", &["i64", "f64"], "f64"));
    assert!(!value::scalar_signature("abs", &["String"], "String"));
    assert!(value::scalar_signature("or", &[], "bool"));
}

#[test]
fn float_function_keys_merge_zero_and_nan_identities() {
    let source = r#"
(function Index (f64) i64 :merge (min old new))
(ruleset fill) (ruleset read)
(rule () ((set (Index 0.0) 8) (set (Index (neg 0.0)) 3)
          (set (Index (^ -1.0 0.5)) 9) (set (Index (^ -2.0 0.5)) 4)) :ruleset fill)
(run-schedule (seq (run fill) (run read)))
(check (= (Index 0.0) 3) (= (Index (^ -1.0 0.5)) 4))
"#;
    let core = eggfuse_bake::device_frontend::core("float-keys", source).unwrap();
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut cpu = Executor::new(Graph::new(p).unwrap(), true);
    cpu.execute().unwrap();
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, source).unwrap();
    let mut a = cpu.graph.export().unwrap()["rows"].as_array().unwrap().iter()
        .filter(|r| r["table"] == "Index").cloned().collect::<Vec<_>>();
    let mut b = native.device_snapshot_tables(&["Index".into()]).unwrap().as_array().unwrap().clone();
    a.sort_by_key(J::to_string); b.sort_by_key(J::to_string);
    assert_eq!(a, b);
    assert_eq!(a.len(), 2);
}

#[cfg(feature = "sparse-cells")]
#[test]
fn unestablished_float_representation_is_not_raced_by_workers() {
    let source = r#"(function Out () String :merge old)
        (relation Input (f64 f64)) (Input -1.0e-308 1.0e-308)
        (rule ((Input x y)) ((set (Out) (to-string (* x y))))) (run 1)"#;
    let core = eggfuse_bake::device_frontend::core("float-workers", source).unwrap();
    assert!(core["float_zero_bits"].is_null());
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut cpu = Executor::new(Graph::new(p).unwrap(), false);
    assert!(cpu.use_query_workers(4, 1).unwrap_err().contains("zero representative"));
    cpu.execute().unwrap();
}

#[test]
fn malformed_float_representation_metadata_is_rejected() {
    let source = "(function Out () String :merge old) (rule () ((set (Out) (to-string 0.0)))) (run 1)";
    let mut core = eggfuse_bake::device_frontend::core("bad-zero", source).unwrap();
    core["float_zero_bits"] = json!(1);
    assert!(compiler::compile(core, &BTreeSet::new()).is_err());
}
