use eggfuse_cell_runtime::{
    checksum::artifact_digest, compiler, executor::Executor, graph::Graph, program::Program,
};

fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("register-prefix", source).unwrap();
    Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap()
}

fn without_consumer_routes(p: &Program) -> Program {
    let consumer = p.artifact["recipe"]["rules"].as_array().unwrap().iter()
        .position(|r| r["metadata"]["name"] == "consumer").unwrap();
    let mut raw = p.artifact.clone();
    let routes = raw["multi_stage"]["routes"].as_array_mut().unwrap();
    let before = routes.len();
    routes.retain(|r| r["consumer"].as_u64() != Some(consumer as u64));
    // Some negative fixtures deliberately have contradictory producer wiring.
    let _removed = before - routes.len();
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    Program::parse(raw).unwrap()
}

fn execute(p: Program, owned_entries: bool, stable_ports: bool) -> Executor {
    let graph = if stable_ports { Graph::new_with_local_congruence(p) }
        else { Graph::new(p) }.unwrap();
    let mut e = Executor::new(graph, true);
    #[cfg(feature = "sparse-cells")]
    #[cfg(feature = "sparse-cells")]
    if owned_entries { e.use_entry_publications().unwrap(); }
    #[cfg(not(feature = "sparse-cells"))]
    let _ = owned_entries;
    #[cfg(not(feature = "sparse-cells"))]
    let _ = owned_entries;
    e.execute().unwrap();
    e
}

fn compare(source: &str, owned_entries: bool, stable_ports: bool) -> Executor {
    let p = program(source);
    let baseline = execute(without_consumer_routes(&p), owned_entries, stable_ports);
    let actual = execute(p, owned_entries, stable_ports);
    assert_eq!(baseline.initial_audit, actual.initial_audit);
    assert_eq!(baseline.snapshots, actual.snapshots);
    assert_eq!(baseline.binding_audit, actual.binding_audit);
    assert_eq!(baseline.graph.export().unwrap(), actual.graph.export().unwrap());
    assert_eq!(baseline.steps.len(), actual.steps.len());
    for (a, b) in baseline.steps.iter().zip(&actual.steps) {
        for key in ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches",
                    "executed_bindings", "changed"] {
            assert_eq!(a[key], b[key], "ordered Run field {key}");
        }
    }
    assert_eq!(baseline.graph.stats.register_prefix.key_reads_avoided, 0);
    actual
}

const SOURCE: &str = r#"
(datatype E (N i64) (A E) (B E i64) (Edge E i64) (Out E i64))
(ruleset make) (ruleset consume)
(rule ((= x (N n))) ((A x) (B x n)) :ruleset make :name "producer")
(rule ((B x n) (= a (A x)) (Edge x y)) ((Out a y)) :ruleset consume :name "consumer")
(Edge (N 0) 10) (Edge (N 0) 11) (Edge (N 1) 12)
(run-schedule (seq (run make) (run consume)))
(check (Out (A (N 0)) 10) (Out (A (N 0)) 11) (Out (A (N 1)) 12))
"#;

fn chain_source() -> String {
    // C's key is learned from A, so Entry's pivot-only projection cannot reject
    // a stale/newer C before the prefix reaches that second key instruction.
    SOURCE.replace("(A E)", "(A E) (C E)")
        .replace("((A x) (B x n))", "((let a (A x)) (C a) (B x n))")
        .replace("(= a (A x)) (Edge x y)", "(= a (A x)) (= c (C a)) (Edge x y)")
        .replace("((Out a y))", "((Out c y))")
        .replace("(Out (A (N 0))", "(Out (C (A (N 0)))")
        .replace("(Out (A (N 1))", "(Out (C (A (N 1)))")
}

#[test]
fn local_effect_prefix_preserves_every_residual_expansion_result() {
    for owned_entries in [false, true] {
        for stable_ports in [false, true] {
            let e = compare(SOURCE, owned_entries, stable_ports);
            assert!(e.graph.stats.register_seeds > 0);
            let s = &e.graph.stats.register_prefix;
            assert!(s.key_reads_avoided > 0);
            assert!(s.resumes > 0);
            assert!(s.field_writes > 0);
            assert!(s.resumed_instructions >= s.resumes);
            assert_eq!(s.context_reads, s.eligible_seeds);
        }
    }
}

#[test]
fn retired_effects_resume_the_original_lookup_at_the_current_pc() {
    let source = chain_source().replace("(ruleset make) (ruleset consume)", r#"
(ruleset make) (ruleset consume) (ruleset replace)
(rule ((B x n) (= a (A x)) (= c (C a)))
 ((delete (C a)) (let fresh (C a)) (union fresh c)) :ruleset replace)
"#).replace("(run make) (run consume)", "(run make) (run replace) (run consume)");
    for stable in [false, true] {
        let e = compare(&source, true, stable);
        assert!(e.graph.stats.register_prefix.stale_fallbacks > 0);
    }
}

#[test]
fn newer_donor_stamp_keeps_the_original_delta_owner() {
    let source = chain_source().replace("(C a) (B x n)", "(B x n) (C a)");
    let e = compare(&source, true, true);
    assert!(e.graph.stats.register_prefix.owner_rejections > 0);
    assert!(e.graph.stats.register_prefix.key_reads_avoided > 0);
}

#[test]
fn prefix_guards_still_reject_and_uncovered_seeds_use_the_normal_kernel() {
    let source = SOURCE
        .replace("(B x n) (= a (A x)) (Edge x y)", "(B x n) (> n 0) (= a (A x)) (Edge x y)")
        .replace("(Edge (N 0) 10)", "(B (N 9) 9) (A (N 9)) (Edge (N 9) 19) (Edge (N 0) 10)")
        .replace("(check (Out (A (N 0)) 10) (Out (A (N 0)) 11) (Out (A (N 1)) 12))",
                 "(check (Out (A (N 1)) 12) (Out (A (N 9)) 19))");
    let e = compare(&source, true, true);
    assert!(e.graph.stats.register_prefix.primitive_checks > 0);
    assert!(e.graph.stats.register_prefix.primitive_rejections > 0);
    assert!(e.graph.stats.register_prefix.key_reads_avoided > 0);
}

#[test]
fn union_changes_and_repeated_output_constraints_remain_exact() {
    let source = SOURCE.replace("(rule ((= x (N n)))", "(rule ((= x (N n)) (= n 1))")
        .replace("(ruleset make) (ruleset consume)", r#"
(ruleset make) (ruleset consume) (ruleset merge)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
"#).replace("(run make) (run consume)", "(run make) (run merge) (run consume)");
    let merged = compare(&source, true, true);
    assert!(merged.graph.stats.register_prefix.key_reads_avoided > 0);

    let source = SOURCE
        .replace("(= a (A x))", "(= x (A x))")
        .replace("((Out a y))", "((Out x y))")
        .replace("(check (Out (A (N 0)) 10) (Out (A (N 0)) 11) (Out (A (N 1)) 12))", "");
    let e = compare(&source, true, false);
    // The static route may conservatively reject the contradictory symbolic
    // wiring altogether. Neither that rejection nor a dynamic output check can
    // turn a failed repeated variable constraint into a successful match.
    assert!(e.steps.iter().any(|s| s["ruleset"] == "consume" && s["executed_bindings"] == 0));
}

#[test]
fn mutable_function_prefix_is_not_mistaken_for_a_local_fact_operation() {
    let source = r#"
(datatype E (N i64) (B E) (Edge E i64) (Out E i64))
(function value (E) E :merge new)
(ruleset make) (ruleset update) (ruleset consume)
(rule ((= x (N 0))) ((set (value x) (N 1)) (B x)) :ruleset make)
(rule ((B x)) ((set (value x) (N 2))) :ruleset update)
(rule ((B x) (= v (value x)) (Edge x y)) ((Out v y)) :ruleset consume :name "consumer")
(Edge (N 0) 10) (Edge (N 0) 11)
(run-schedule (seq (run make) (run update) (run consume)))
(check (Out (N 2) 10) (Out (N 2) 11))
"#;
    let e = compare(source, true, false);
    assert_eq!(e.graph.stats.register_prefix.key_reads_avoided, 0);
    // Another pivot may have a legal B prefix, but a mutable value is never
    // fetched as a local FactRef. Its current output is required by the checks.
    assert_eq!(e.graph.stats.register_prefix.donor_reads, 0);
}
