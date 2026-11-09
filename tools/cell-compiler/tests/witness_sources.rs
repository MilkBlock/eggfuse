#![cfg(feature = "iterative-bake")]
use eggfuse_cell_runtime::{
    checksum::artifact_digest, compiler, executor::Executor, graph::Graph,
    iterative::{Catalog, Limits}, program::{Call, Program},
};
use serde_json::json;

// The keeper already demands A's receipt for RHS reuse. The residual consumer
// must use that same published receipt, without another capture/history packet.
const SOURCE: &str = r#"
(datatype E (N i64) (A E) (B E i64) (Edge E i64) (Out E i64) (Keep E))
(ruleset make) (ruleset consume) (ruleset keep)
(rule ((= x (N n))) ((A x) (B x n)) :ruleset make :name "producer")
(rule ((B x n) (= a (A x)) (Edge x y)) ((Out a y)) :ruleset consume :name "consumer")
(rule ((B x n)) ((Keep (A x))) :ruleset keep :name "keeper")
(A (N 0)) (A (N 1))
(Edge (N 0) 10) (Edge (N 0) 11) (Edge (N 1) 12)
(run-schedule (seq (run make) (run consume) (run keep)))
(check (Out (A (N 0)) 10) (Out (A (N 0)) 11) (Out (A (N 1)) 12))
"#;

fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("witness-sources", source).unwrap();
    let p = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let rules = p.artifact["recipe"]["rules"].as_array().unwrap();
    let id = |name| rules.iter().position(|r| r["metadata"]["name"] == name).unwrap();
    let (producer, keeper) = (id("producer"), id("keeper"));
    let publication = rules[producer]["effects"].as_array().unwrap().iter()
        .position(|e| e["call"]["table"] == "B").unwrap();
    let pivot = p.rules[keeper].query.iter()
        .position(|a| matches!(a.call, Call::Table(t) if p.tables[t].name == "B")).unwrap();
    let profile = json!({"schema":"eggfuse-spine-shapes/v1","program_sha256":p.artifact["sha256"],
        "prefixes":[{"edge":[producer,publication,keeper,pivot],"visits":2}]});
    let leaves = compiler::bake_stage_blocks(&p, &profile, &p, 1).unwrap();
    assert_eq!(leaves["entries"].as_array().unwrap().len(), 1);
    let mut raw = p.artifact;
    raw["spine_blocks"] = leaves;
    let p = Program::parse(raw).unwrap();
    let mut plan = Catalog::seed_with_roots(&p, Limits { support: 1, ..Default::default() }, &[producer]).unwrap();
    plan["joins"] = json!([{"left":1,"output":publication,"right":0}]);
    Catalog::emit_query_handoffs(&p, &mut plan).unwrap();
    let mut raw = p.artifact;
    raw["iterative_bake"] = plan;
    Program::parse(raw).unwrap()
}

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
    let source = SOURCE.replace("(Edge x y)) ((Out a y))", "(= n y)) ((Out a y))")
        .replace("(check (Out (A (N 0)) 10) (Out (A (N 0)) 11) (Out (A (N 1)) 12))",
            "(check (Out (A (N 0)) 0) (Out (A (N 1)) 1))");
    let (old, new) = compare(&source, true, true);
    let report = new.report();
    assert!(report["stage_spine"]["stats"]["local_witness_receipt_hits"].as_u64().unwrap() > 0, "{}", report["stage_spine"]["stats"]);
    assert!(report["stage_spine"]["stats"]["local_witness_hits"].as_u64().unwrap() > 0);
    assert!(new.graph.key_lookup_calls.get() < old.graph.key_lookup_calls.get());
}

#[test]
fn all_reused_rhs_uses_publication_instead_of_physical_producer() {
    let source = SOURCE.replace("(A (N 0)) (A (N 1))", "(A (N 0)) (A (N 1)) (B (N 0) 0) (B (N 1) 1)");
    let (_, new) = compare(&source, true, true);
    assert!(new.graph.stats.register_prefix.receipt_hits > 0);
    assert!(new.graph.stats.register_prefix.resumes > 0);
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
