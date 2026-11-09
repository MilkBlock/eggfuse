#![cfg(feature = "iterative-bake")]
use eggfuse_cell_runtime::{checksum::artifact_digest, executor::Executor, graph::Graph, program::Program};
#[path = "support/cell_entry.rs"]
mod fixture;
use fixture::{program, SOURCE};

fn execute(p: Program, owned: bool, stable: bool) -> Executor {
    let graph = if stable { Graph::new_with_local_congruence(p) } else { Graph::new(p) }.unwrap();
    let mut e = Executor::new(graph, true);
    #[cfg(feature = "sparse-cells")]
    if owned { e.use_entry_publications().unwrap(); }
    #[cfg(not(feature = "sparse-cells"))]
    let _ = owned;
    e.execute().unwrap();
    e
}

fn compare(source: &str, owned: bool, stable: bool) -> (Executor, Executor) {
    let p = program(source);
    let consumer = p.artifact["recipe"]["rules"].as_array().unwrap().iter()
        .position(|r| r["metadata"]["name"] == "consumer").unwrap();
    let mut raw = p.artifact.clone();
    raw["multi_stage"]["routes"].as_array_mut().unwrap()
        .retain(|r| r["consumer"].as_u64() != Some(consumer as u64));
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    let old = execute(Program::parse(raw).unwrap(), owned, stable);
    let new = execute(p, owned, stable);
    assert_eq!(old.initial_audit, new.initial_audit);
    assert_eq!(old.snapshots, new.snapshots);
    assert_eq!(old.binding_audit, new.binding_audit);
    assert_eq!(old.graph.export().unwrap(), new.graph.export().unwrap());
    assert_eq!(old.steps.len(), new.steps.len());
    for (a, b) in old.steps.iter().zip(&new.steps) {
        for key in ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed"] {
            assert_eq!(a[key], b[key], "ordered Run field {key}");
        }
    }
    let a = old.report();
    let b = new.report();
    for key in ["history_capture_reads", "history_slots_written", "history_allocations", "root_handles_created"] {
        assert_eq!(a["stage_spine"]["stats"][key], b["stage_spine"]["stats"][key], "capture cost {key}");
    }
    (old, new)
}

#[test]
fn reused_constructor_receipt_resumes_all_residual_results() {
    for owned in [false, true] {
        for stable in [false, true] {
            let (old, new) = compare(SOURCE, owned, stable);
            assert!(new.graph.stats.register_prefix.receipt_hits > 0);
            assert!(new.graph.stats.register_prefix.receipt_slot_reads > 0);
            assert_eq!(new.graph.stats.register_prefix.receipt_steps, 0);
            assert_eq!(new.graph.stats.register_prefix.history_borrows, 0);
            assert_eq!(new.graph.stats.register_prefix.context_reads, 0);
            #[cfg(feature = "sparse-cells")]
            if owned {
                assert!(new.graph.stats.register_prefix.entry_publication_reads > 0);
                assert_eq!(new.graph.stats.register_prefix.publication_probes, 0);
            }
            assert!(new.graph.stats.register_prefix.resumes > 0);
            assert!(new.graph.key_lookup_calls.get() < old.graph.key_lookup_calls.get());
        }
    }
}

#[test]
fn elided_rhs_operation_reads_its_query_receipt() {
    let source = SOURCE.replace("((= x (N n)))", "((= x (N n)) (= a (A x)))");
    let (old, new) = compare(&source, true, true);
    assert!(new.graph.stats.register_prefix.receipt_hits > 0);
    assert!(new.graph.stats.register_prefix.resumes > 0);
    assert!(new.graph.key_lookup_calls.get() < old.graph.key_lookup_calls.get());
}

#[test]
fn full_spine_reads_the_published_receipt_before_a_key_lookup() {
    let source = fixture::full_source();
    let (old, new) = compare(&source, true, true);
    let report = new.report();
    assert!(report["stage_spine"]["stats"]["local_witness_receipt_hits"].as_u64().unwrap() > 0, "{}", report["stage_spine"]["stats"]);
    assert!(report["stage_spine"]["stats"]["local_witness_hits"].as_u64().unwrap() > 0);
    assert!(report["stage_spine"]["stats"]["local_witness_slot_reads"].as_u64().unwrap() > 0);
    assert_eq!(report["stage_spine"]["stats"]["local_witness_receipt_steps"], 0);
    assert_eq!(report["stage_spine"]["stats"]["local_witness_contexts"], 0);
    assert_eq!(report["stage_spine"]["stats"]["local_witness_history_borrows"], 0);
    assert!(new.graph.key_lookup_calls.get() < old.graph.key_lookup_calls.get());
}

#[test]
fn all_reused_rhs_uses_publication_instead_of_physical_producer() {
    let source = SOURCE.replace("(A (N 0)) (A (N 1))", "(A (N 0)) (A (N 1)) (B (N 0) 0) (B (N 1) 1)");
    let (_, new) = compare(&source, true, true);
    assert!(new.graph.stats.register_prefix.receipt_hits > 0);
    assert!(new.graph.stats.register_prefix.resumes > 0);
}

#[test]
fn entry_publication_replacement_keeps_new_runs_and_late_inputs_visible() {
    let source = fixture::replaced_source();
    for stable in [false, true] {
        let (_, new) = compare(&source, true, stable);
        #[cfg(feature = "sparse-cells")]
        {
            assert!(new.report()["entry_schedule"]["stats"]["entry_publications_retired"].as_u64().unwrap() > 0);
            assert!(new.graph.stats.register_prefix.entry_publication_reads > 0);
            assert_eq!(new.graph.stats.register_prefix.publication_probes, 0);
        }
        assert!(new.graph.stats.register_prefix.receipt_hits > 0);
    }
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, &source).unwrap();
}

fn chain_source() -> String {
    SOURCE.replace("(A E)", "(A E) (C E)")
        .replace("((A x) (B x n))", "((let a (A x)) (C a) (B x n))")
        .replace("(= a (A x)) (Edge x y)", "(= a (A x)) (= c (C a)) (Edge x y)")
        .replace("((Out a y))", "((Out c y))")
        .replace("(Keep (A x))", "(Keep (C (A x)))")
        .replace("(A (N 0)) (A (N 1))", "(C (A (N 0))) (C (A (N 1)))")
        .replace("(Out (A (N 0))", "(Out (C (A (N 0)))")
        .replace("(Out (A (N 1))", "(Out (C (A (N 1)))")
}

#[test]
fn retired_receipt_falls_back_without_reviving_old_fact() {
    // The second key is learned from the first donor. A pivot-only Entry
    // predicate cannot reject the candidate before reaching the retired donor.
    let source = chain_source().replace("(ruleset make)", r#"
(ruleset replace)
(rule ((B x n) (= a (A x)) (= c (C a)))
 ((delete (C a)) (let fresh (C a)) (union fresh c)) :ruleset replace)
(ruleset make)"#).replace("(run make) (run consume)", "(run make) (run replace) (run consume)");
    let (_, new) = compare(&source, true, true);
    assert!(new.graph.stats.register_prefix.receipt_hits > 0);
    assert!(new.graph.stats.register_prefix.misses.fact_missing > 0
        || new.graph.stats.register_prefix.misses.cell_missing > 0, "{:?}", new.graph.stats.register_prefix);
}

#[test]
fn zero_argument_donors_keep_the_existing_singleton_read() {
    let source = SOURCE.replace("(A E)", "(A)")
        .replace("(A x)", "(A)")
        .replace("(A (N 0))", "(A)").replace("(A (N 1))", "(A)");
    let (_, new) = compare(&source, true, true);
    assert_eq!(new.graph.stats.register_prefix.eligible_seeds, 0);
    assert_eq!(new.graph.stats.register_prefix.publication_probes, 0);
}

#[test]
fn borrowed_expansion_fields_follow_each_candidate_and_late_delta() {
    let source = fixture::borrowed_source();
    for stable in [false, true] {
        let (_, new) = compare(&source, true, stable);
        assert!(new.graph.stats.register_prefix.resumes > 0);
        assert!(new.graph.stats.register_expansion_rows > 0);
        assert!(new.graph.stats.register_result_writes > new.graph.stats.register_prefix.field_writes);
    }
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
}
