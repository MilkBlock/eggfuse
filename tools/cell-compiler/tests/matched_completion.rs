#![cfg(feature = "iterative-bake")]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};

const MATCHED: &str = include_str!("fixtures/matched-completion.egg");
const BOUNDARIES: &str = include_str!("fixtures/matched-boundaries.egg");

fn execute(source: &str, local: bool) -> Executor {
    let core = eggfuse_bake::device_frontend::core("matched-completion", source).unwrap();
    let p = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let graph = if local { Graph::new_with_local_congruence(p) } else { Graph::new(p) }.unwrap();
    let mut e = Executor::new(graph, true);
    e.execute().unwrap();
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, source).unwrap();
    e
}

#[test]
fn matched_aliases_and_ordered_unions_complete_after_late_input() {
    let ordinary = execute(MATCHED, false);
    let local = execute(MATCHED, true);
    assert_eq!(ordinary.graph.export().unwrap(), local.graph.export().unwrap());
    assert_eq!(ordinary.snapshots, local.snapshots);
    assert_eq!(ordinary.binding_audit, local.binding_audit);
    for e in [&ordinary, &local] {
        // Two Choice rows remain distinct. The union-enabled old match also
        // re-enters on the second Run, alongside the late producer: 2 + 4.
        assert_eq!(e.graph.stats.matched_cells_completed, 6);
        assert_eq!(e.graph.stats.handoff_attempts, 0);
        assert_eq!(e.graph.stats.union_requests, 12);
        assert_eq!(e.report()["known_results"]["static_eliminated"], 12);
    }
}

#[test]
fn matched_completion_keeps_legacy_continuation_accounting() {
    // A second Run exposes the producer's committed fields to its consumer.
    // This also checks completion with a physical producer continuation.
    let source = MATCHED.replace(":ruleset make :name \"producer\"", ":ruleset complete :name \"producer\"")
        .replace("(run complete)", "(run complete) (run complete)");
    let e = execute(&source, false);
    assert!(e.graph.stats.matched_cells_completed > 0);
    let stats = &e.report()["multi_stage"]["stats"];
    assert!(stats["residual_bindings"].as_u64().unwrap() > 0);
    assert!(stats["max_depth"].as_u64().unwrap() > 0);
}

#[test]
fn mutable_query_reads_scalar_effects_and_deleted_aliases_keep_the_source_rhs() {
    for local in [false, true] {
        let e = execute(BOUNDARIES, local);
        assert_eq!(e.graph.stats.matched_cells_completed, 0);
        assert!(e.graph.stats.constructor_requests > 0);
        assert!(e.graph.stats.function_updates > 0);
    }
}
