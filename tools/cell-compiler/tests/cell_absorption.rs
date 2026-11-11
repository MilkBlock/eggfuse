#![cfg(feature = "cell-absorption")]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};

const SOURCE: &str = r#"
(datatype E (N i64) (Get E i64) (Seen E i64))
(function Cost (E) i64 :merge (min old new))
(ruleset propagate) (ruleset forty) (ruleset thirty) (ruleset twenty) (ruleset two)
(ruleset late) (ruleset join) (ruleset read) (ruleset remove) (ruleset again)
(rule ((= g (Get x i)) (= n (Cost x))) ((set (Cost g) n)) :ruleset propagate)
(rule ((= x (N 0))) ((set (Cost x) 40)) :ruleset forty)
(rule ((= x (N 0))) ((set (Cost x) 30)) :ruleset thirty)
(rule ((= x (N 0))) ((set (Cost x) 20)) :ruleset twenty)
(rule ((= x (N 0))) ((set (Cost x) 2)) :ruleset two)
(rule ((= x (N 0))) ((Get x 2)) :ruleset late)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset join)
(rule ((= g (Get x i)) (= n (Cost g))) ((Seen g n)) :ruleset read)
(rule ((= x (N 0))) ((delete (Get x 1))) :ruleset remove)
(rule ((= x (N 0))) ((Get x 1)) :ruleset again)
(set (Cost (N 0)) 50) (set (Cost (N 1)) 3)
(set (Cost (Get (N 0) 0)) 7) (set (Cost (Get (N 0) 1)) 8)
(set (Cost (Get (N 1) 0)) 1)
(run-schedule (seq
 (run propagate) (run forty) (run propagate) (run read)
 (run thirty) (run propagate) (run late) (run propagate)
 (run twenty) (run propagate) (run join) (run propagate)
 (run remove) (run propagate) (run again) (run propagate)
 (run two) (run propagate) (run read)))
(check (= (Cost (Get (N 0) 0)) 1) (= (Cost (Get (N 0) 1)) 2)
       (= (Cost (Get (N 0) 2)) 2) (Seen (Get (N 0) 2) 2))
"#;

fn run(source: &str, enabled: bool, workers: usize) -> Executor {
    let core = eggfuse_bake::device_frontend::core("cell-absorption", source).unwrap();
    let p = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let mut e = Executor::new(Graph::new_with_repair_ports(p).unwrap(), true);
    e.use_entry_publications().unwrap();
    if enabled { e.use_cell_absorption().unwrap(); }
    if workers != 0 { e.use_query_workers(workers, 1).unwrap(); }
    e.execute().unwrap();
    e
}

#[test]
fn completed_min_domains_survive_scalar_changes_and_reopen_on_structure_changes() {
    egglog::EGraph::default().parse_and_run_program(None, SOURCE).unwrap();
    let before = run(SOURCE, false, 0);
    for workers in [0, 4] {
        let after = run(SOURCE, true, workers);
        assert_eq!(before.snapshots, after.snapshots, "every source Run graph and visibility");
        assert_eq!(before.steps.len(), after.steps.len());
        for (a, b) in before.steps.iter().zip(&after.steps) {
            for key in ["ordinal", "ruleset", "path", "iterations", "epoch", "changed", "logical_matches"] {
                assert_eq!(a[key], b[key], "{key}");
            }
        }
        let r = after.report();
        let stats = &r["neighbor_context"]["absorption"]["stats"];
        assert!(stats["matches_absorbed"].as_u64().unwrap() >= 4, "{stats}");
        assert!(stats["reused_bounds"].as_u64().unwrap() > 0, "{stats}");
        assert!(after.graph.stats.bindings < before.graph.stats.bindings);
        assert_eq!(after.graph.stats.function_updates, before.graph.stats.function_updates);
        assert_eq!(after.graph.stats.unions, before.graph.stats.unions);
    }
}

#[test]
fn singleton_absorption_keeps_later_scalar_updates_and_consumers() {
    let source = r#"
        (datatype E (N) (Get E i64) (Seen E i64))
        (function Cost (E) i64 :merge (min old new))
        (ruleset propagate) (ruleset twenty) (ruleset two) (ruleset read)
        (rule ((= g (Get x i)) (= n (Cost x))) ((set (Cost g) n)) :ruleset propagate)
        (rule ((= x (N))) ((set (Cost x) 20)) :ruleset twenty)
        (rule ((= x (N))) ((set (Cost x) 2)) :ruleset two)
        (rule ((= g (Get x i)) (= n (Cost g))) ((Seen g n)) :ruleset read)
        (set (Cost (N)) 30) (set (Cost (Get (N) 0)) 7)
        (run-schedule (seq (run propagate) (run twenty) (run propagate)
            (run read) (run two) (run propagate) (run read)))
        (check (= (Cost (Get (N) 0)) 2) (Seen (Get (N) 0) 7) (Seen (Get (N) 0) 2))
    "#;
    egglog::EGraph::default().parse_and_run_program(None, source).unwrap();
    let before = run(source, false, 0);
    for workers in [0,4] {
        let after = run(source, true, workers);
        assert_eq!(before.snapshots, after.snapshots);
        assert_eq!(before.steps.len(), after.steps.len());
        for (a,b) in before.steps.iter().zip(&after.steps) {
            for key in ["ordinal", "ruleset", "path", "iterations", "epoch", "changed", "logical_matches"] {
                assert_eq!(a[key],b[key],"{key}");
            }
        }
        let report = after.report();
        let stats = &report["neighbor_context"]["absorption"]["stats"];
        assert_eq!(stats["single_absorbed"],1,"{stats}");
        assert_eq!(stats["single_output_probes"],2,"the later lower input must still execute");
        assert_eq!(stats["groups_absorbed"],0,"singletons must not create a domain cache");
        assert_eq!(before.graph.stats.bindings-after.graph.stats.bindings,1);
        assert_eq!(before.graph.stats.function_updates,after.graph.stats.function_updates);
    }
}

#[test]
fn deletable_outputs_and_ordered_merges_have_no_absorption_proof() {
    for source in [
        SOURCE.replace(":merge (min old new)", ":merge new").replace("(check (= (Cost (Get (N 0) 0)) 1)", "(check (= (Cost (Get (N 0) 0)) 2)"),
        SOURCE.replace("(ruleset propagate)", "(ruleset unused)\n(rule ((= x (N 99))) ((delete (Cost x))) :ruleset unused)\n(ruleset propagate)")
            .replace("(run forty)", "(run unused) (run forty)"),
    ] {
        let before = run(&source, false, 0);
        let after = run(&source, true, 0);
        let r = after.report();
        assert_eq!(r["neighbor_context"]["absorption"]["plans"], 0, "{r}");
        assert_eq!(before.snapshots, after.snapshots);
        assert_eq!(before.binding_audit, after.binding_audit);
        assert_eq!(r["neighbor_context"]["absorption"]["stats"]["matches_absorbed"], 0);
    }
}
