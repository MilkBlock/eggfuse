// These diagnostic modes deliberately retain per-entry source ownership.
#![cfg(all(
    feature = "parallel-publication",
    not(any(feature = "structural-depth", feature = "cell-entry-reverse"))
))]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};

fn run(source: &str, workers: usize) -> Executor {
    let core = eggfuse_bake::device_frontend::core("cell-owner-pipeline", source).unwrap();
    let program = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let mut e = Executor::new(Graph::new_with_repair_ports(program).unwrap(), true);
    e.use_entry_publications().unwrap();
    if workers != 0 {
        e.use_query_workers(workers, 16).unwrap();
        e.use_parallel_residuals().unwrap();
        e.use_parallel_publication().unwrap();
        e.use_cell_execution(1).unwrap();
    }
    e.execute().unwrap();
    e
}
#[test]
fn owned_entries_continue_through_rhs_and_publication_with_late_inputs_and_union() {
    let mut source = String::from(
        r#"
(datatype E (N i64))
(function Left (E) i64 :merge (min old new))
(function Right (E) i64 :merge (min old new))
(function Out (E i64) Unit :merge old)
(function Audit (E) Unit :merge new)
(ruleset left) (ruleset right) (ruleset see) (ruleset lower)
(ruleset remove) (ruleset again) (ruleset join)
(rule ((= x (N i))) ((set (Left x) i)) :ruleset left)
(rule ((= x (N i)) (>= i 32)) ((set (Right x) (+ i 1))) :ruleset right)
(rule ((= a (Left x)) (= b (Right x)) (>= a 0)) ((set (Out x (+ a b)) ()) (set (Audit x) ())) :ruleset see)
(rule ((= x (N i))) ((set (Right x) 1)) :ruleset lower)
(rule ((= x (N i)) (< i 64)) ((delete (Right x))) :ruleset remove)
(rule ((= x (N i)) (< i 64)) ((set (Right x) 2)) :ruleset again)
(rule ((= x (N i)) (< i 64) (= y (N (+ i 64)))) ((union x y)) :ruleset join)
"#,
    );
    for i in 0..256 {
        source += &format!("(N {i})\n");
    }
    source += "(run-schedule (seq (run left) (run right) (run see) (run lower) (run see) (run remove) (run see) (run again) (run see) (run join) (run see)))";
    egglog::EGraph::default()
        .parse_and_run_program(None, &source)
        .unwrap();
    let before = run(&source, 0);
    for workers in [1, 2, 4] {
        let after = run(&source, workers);
        assert_eq!(
            before.snapshots, after.snapshots,
            "every Run, including union/retirement boundaries"
        );
        assert_eq!(
            before.binding_audit, after.binding_audit,
            "winner identity and effect order"
        );
        assert_eq!(
            before.graph.export().unwrap(),
            after.graph.export().unwrap()
        );
        let report = after.report();
        let queries = &report["query_workers"]["stats"];
        assert!(
            queries["owned_range_rows"].as_u64().unwrap() > 0,
            "whole Cell Entry ranges must run: {queries}"
        );
        assert!(queries["owned_range_answers"].as_u64().unwrap() > 0);
        assert!(queries["owned_support_checks"].as_u64().unwrap() > 0);
        if workers > 1 {
            assert!(
                queries["execution"]["units"]["rows"].as_u64().unwrap() > 0,
                "the same instance must continue into Unit RHS rows"
            );
        }
        assert!(
            report["entry_schedule"]["stats"]["owner_entry_updates"]
                .as_u64()
                .unwrap()
                > 0,
            "the table owner must publish into actual Shared Entries"
        );
    }
}
