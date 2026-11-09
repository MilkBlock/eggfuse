use eggfuse_cell_runtime::{
    checksum::artifact_digest,
    compiler,
    executor::Executor,
    graph::{Dependency, Graph},
    program::Program,
    value::Value,
};
use serde_json::json;
use std::collections::BTreeSet;

fn source(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("stable-ports", src).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn baked(src: &str) -> Program {
    let p = source(src);
    let mut raw = p.artifact.clone();
    let mut g = Graph::new_with_cell_ownership(p).unwrap();
    g.train_ownership_fragments().unwrap();
    let mut e = Executor::new(g, false);
    e.execute().unwrap();
    let profile = e.graph.ownership_fragment_profile().unwrap();
    // These semantic fixtures exercise every observed local route. Production
    // ranking and performance admission are separate concerns.
    raw["ownership_fragments"] = json!({"schema":"eggfuse-ownership-fragments/v1",
        "source":profile["source"],"fragments":profile["records"].as_array().unwrap()
            .iter().map(|r|r["fragment"].clone()).collect::<Vec<_>>()});
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    Program::parse(raw).unwrap()
}
fn compare(src: &str) -> Executor {
    let p = baked(src);
    let mut old = Executor::new(Graph::new_with_cell_ownership(p.clone()).unwrap(), true);
    let mut new = Executor::new(Graph::new_with_stable_ports(p.clone()).unwrap(), true);
    let mut keyed = Executor::new(Graph::new_with_port_keys(p.clone()).unwrap(), true);
    let mut local = Executor::new(Graph::new_with_local_congruence(p).unwrap(), true);
    old.execute().unwrap();
    new.execute().unwrap();
    keyed.execute().unwrap();
    local.execute().unwrap();
    assert_execution_equal(&old, &local);
    local.graph.ownership_report();
    assert_eq!(old.initial_audit, keyed.initial_audit);
    assert_eq!(old.snapshots, keyed.snapshots);
    assert_eq!(old.binding_audit, keyed.binding_audit);
    assert_eq!(old.steps.len(), keyed.steps.len());
    for (a, b) in old.steps.iter().zip(&keyed.steps) {
        for k in [
            "ordinal",
            "ruleset",
            "path",
            "iterations",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(a[k], b[k], "port keys: {k}");
        }
    }
    keyed.graph.ownership_report();
    assert!(
        keyed.graph.stable_port_report()["birth_indexed_port_keys"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert_eq!(
        keyed.graph.ownership_report()["stats"]["key_completions"],
        0
    );
    assert_eq!(old.initial_audit, new.initial_audit);
    assert_eq!(old.snapshots, new.snapshots);
    assert_eq!(old.binding_audit, new.binding_audit);
    assert_eq!(old.steps.len(), new.steps.len());
    for (a, b) in old.steps.iter().zip(&new.steps) {
        for k in [
            "ordinal",
            "ruleset",
            "path",
            "iterations",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(a[k], b[k], "{k}");
        }
    }
    new.graph.ownership_report();
    let report = new.graph.stable_port_report();
    assert!(report["live_port_fields"].as_u64().unwrap() > 0);
    assert_eq!(report["pending_canonical_keys"], 0);
    egglog::EGraph::default()
        .parse_and_run_program(None, src)
        .unwrap();
    new
}

fn assert_execution_equal(a: &Executor, b: &Executor) {
    assert_eq!(a.initial_audit, b.initial_audit);
    assert_eq!(a.snapshots, b.snapshots);
    assert_eq!(a.binding_audit, b.binding_audit);
    assert_eq!(a.steps.len(), b.steps.len());
    for (a, b) in a.steps.iter().zip(&b.steps) {
        for k in [
            "ordinal",
            "ruleset",
            "path",
            "iterations",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(a[k], b[k], "local conditions: {k}");
        }
    }
}

fn local_compare(src: &str) -> Executor {
    let p = baked(src);
    let mut old = Executor::new(Graph::new_with_port_keys(p.clone()).unwrap(), true);
    let mut new = Executor::new(Graph::new_with_local_congruence(p).unwrap(), true);
    old.execute().unwrap();
    new.execute().unwrap();
    assert_execution_equal(&old, &new);
    new.graph.ownership_report();
    egglog::EGraph::default()
        .parse_and_run_program(None, src)
        .unwrap();
    new
}

#[test]
fn local_conditions_require_all_inputs_before_cascading_to_outputs() {
    let src = r#"
(datatype E (N i64) (Pair E E) (Wrap E))
(ruleset build) (ruleset first) (ruleset second)
(rule ((= a (N 0)) (= b (N 1)) (= c (N 2)) (= d (N 3)))
      ((Wrap (Pair a c)) (Wrap (Pair b d))) :ruleset build)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset first)
(rule ((= c (N 2)) (= d (N 3))) ((union c d)) :ruleset second)
(N 0) (N 1) (N 2) (N 3)
(run-schedule (seq (run build) (run first) (run second)))
"#;
    let p = baked(src);
    let pair = p.tables.iter().position(|t| t.name == "Pair").unwrap();
    let wrap = p.tables.iter().position(|t| t.name == "Wrap").unwrap();
    let mut e = Executor::new(Graph::new_with_local_congruence(p).unwrap(), true);
    e.execute_until(Some(2)).unwrap();
    assert_eq!(e.graph.witness_count(pair), 2);
    assert_eq!(e.graph.witness_count(wrap), 2);
    assert_eq!(
        e.graph.stable_port_report()["local_conditions"]["stats"]["completed_conditions"],
        0
    );
    e.execute().unwrap();
    assert_eq!(e.graph.witness_count(pair), 1);
    assert_eq!(e.graph.witness_count(wrap), 1);
    assert_eq!(
        e.graph.stable_port_report()["local_conditions"]["stats"]["completed_conditions"],
        2
    );
    let reference = local_compare(src);
    assert_execution_equal(&reference, &e);
}

const LOCAL_STAGES: &str = r#"
(datatype E (N i64) (F E) (G E) (Tag E) (Noise E))
(ruleset build) (ruleset extend) (ruleset merge)
(rule ((= a (N 0)) (= b (N 1))) ((F a) (Tag b)) :ruleset build)
(rule ((= f (F a)) (= tag (Tag b))) ((G f) (G (F b))) :ruleset extend)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run build) (run extend) (run merge)))
(check (= (G (F (N 0))) (G (F (N 1)))))
"#;

#[test]
fn shared_conditions_cross_stage_and_ignore_unrelated_nodes() {
    let plain = local_compare(LOCAL_STAGES);
    let noise = (10..110)
        .map(|n| format!("(Noise (N {n}))\n"))
        .collect::<String>();
    let noisy =
        local_compare(&LOCAL_STAGES.replace("(N 0) (N 1)\n", &format!("(N 0) (N 1)\n{noise}")));
    let a = plain.graph.stable_port_report()["local_conditions"].clone();
    let b = noisy.graph.stable_port_report()["local_conditions"].clone();
    assert!(
        a["stats"]["cross_stage_conditions"].as_u64().unwrap() > 0,
        "{a}"
    );
    assert_eq!(a["stats"], b["stats"]);
}

#[test]
fn foreign_constructor_keeps_the_boundary_path_live() {
    let e = local_compare(
        r#"
(datatype E (N i64) (F E))
(ruleset build) (ruleset merge)
(rule ((= a (N n))) ((F a)) :ruleset build)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run build) (run merge)))
(check (= (F (N 0)) (F (N 1))))
"#,
    );
    let stats = e.graph.stable_port_report()["local_conditions"]["stats"].clone();
    assert!(stats["open_domains"].as_u64().unwrap() > 0, "{stats}");
    assert!(
        stats["boundary_collisions"].as_u64().unwrap() > 0,
        "{stats}"
    );
}

#[test]
fn mixed_internal_and_external_candidates_preserve_survivor_order() {
    let e = local_compare(
        r#"
(datatype E (N i64) (F E) (G E))
(ruleset older) (ruleset inside) (ruleset merge)
(rule ((= a (N 1))) ((G (F a))) :ruleset older)
(rule ((= a (N 2)) (= b (N 3))) ((G (F a)) (G (F b))) :ruleset inside)
(rule ((= z (N 0)) (= a (N 1)) (= b (N 2)) (= c (N 3)))
      ((union z a) (union z b) (union z c)) :ruleset merge)
(N 0) (N 1) (N 2) (N 3)
(run-schedule (seq (run older) (run inside) (run merge)))
(check (= (G (F (N 1))) (G (F (N 3)))))
"#,
    );
    let stats = e.graph.stable_port_report()["local_conditions"]["stats"].clone();
    assert!(stats["local_candidates"].as_u64().unwrap() > 0, "{stats}");
    assert!(
        stats["boundary_candidates"].as_u64().unwrap() > 0,
        "{stats}"
    );
    assert!(
        stats["candidate_sort_comparisons"].as_u64().unwrap() > 0,
        "{stats}"
    );
}

#[test]
fn condition_budget_falls_back_instead_of_truncating_coverage() {
    let rhs = (1..17).map(|n| format!("(F (N {n})) ")).collect::<String>();
    let src = format!(
        r#"
(datatype E (N i64) (F E))
(ruleset build) (ruleset small) (ruleset merge)
(rule ((= a (N 0))) ((F a) {rhs}) :ruleset build)
(rule ((= a (N 17))) ((F a)) :ruleset small)
(rule ((= z (N -1)) (= a (N 0)) (= b (N 17))) ((union z a) (union z b)) :ruleset merge)
(N -1) (N 0) (N 17)
(run-schedule (seq (run build) (run small) (run merge)))
(check (= (F (N 0)) (F (N 17))))
"#
    );
    let e = local_compare(&src);
    let report = e.graph.stable_port_report()["local_conditions"].clone();
    assert!(report["uncovered_shapes"].as_u64().unwrap() > 0, "{report}");
    assert!(
        report["stats"]["uncovered_shapes"].as_u64().unwrap() > 0,
        "{report}"
    );
    assert!(
        report["stats"]["boundary_uncompiled_steps"]
            .as_u64()
            .unwrap()
            > 0,
        "{report}"
    );
}

#[test]
fn cross_stage_fields_are_stable_while_legacy_keys_still_complete() {
    let e = compare(
        r#"
(datatype E (N i64) (F E) (G E) (H E))
(ruleset a) (ruleset b) (ruleset merge)
(rule ((= x (N n))) ((G (F x))) :ruleset a)
(rule ((= g (G f))) ((H g)) :ruleset b)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run merge)))
(check (= (H (G (F (N 0)))) (H (G (F (N 1))))))
"#,
    );
    let p = e.graph.stable_port_report();
    assert!(p["stats"]["notifications"].as_u64().unwrap() > 0);
    assert!(p["stats"]["legacy_key_enqueues"].as_u64().unwrap() > 0);
    let old_path = e.graph.ownership_report();
    assert_eq!(old_path["stats"]["port_checks"], 0);
    assert_eq!(old_path["stats"]["row_copies"], 0);
}

#[test]
fn multi_input_aliases_preserve_partial_equality_and_ordered_effects() {
    compare(
        r#"
(datatype E (N i64) (Pair E E) (Wrap E))
(ruleset build) (ruleset first) (ruleset second)
(rule ((= a (N 0)) (= b (N 1)) (= c (N 2)) (= d (N 3)))
      ((Wrap (Pair a c)) (Wrap (Pair b d))) :ruleset build)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset first)
(rule ((= c (N 2)) (= d (N 3))) ((union c d)) :ruleset second)
(N 0) (N 1) (N 2) (N 3)
(run-schedule (seq (run build) (run first) (run second)))
(check (= (Pair (N 0) (N 2)) (Pair (N 1) (N 3))))
"#,
    );
}

#[test]
fn deleted_producer_retains_consumers_across_a_late_union() {
    compare(
        r#"
(datatype E (N i64) (F E) (G E) (H E))
(ruleset a) (ruleset b) (ruleset erase) (ruleset merge) (ruleset read)
(rule ((= x (N n))) ((F x)) :ruleset a)
(rule ((= f (F x))) ((G x)) :ruleset b)
(rule ((= f (F x))) ((delete (F x))) :ruleset erase)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(rule ((= g (G x))) ((H g)) :ruleset read)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run erase) (run merge) (run read)))
"#,
    );
}

#[test]
fn stable_address_survives_representative_change_and_expires_on_recreation() {
    let p = source("(datatype E (N i64) (F E)) (N 0) (N 1) (N 2) (F (N 2)) (run-schedule (run))");
    let n = p.tables.iter().position(|t| t.name == "N").unwrap();
    let f = p.tables.iter().position(|t| t.name == "F").unwrap();
    let mut g = Graph::new_with_port_keys(p).unwrap();
    let a = g
        .lookup(n, &[Value::Int(0)])
        .unwrap()
        .unwrap()
        .values
        .last()
        .unwrap()
        .clone();
    let b = g
        .lookup(n, &[Value::Int(1)])
        .unwrap()
        .unwrap()
        .values
        .last()
        .unwrap()
        .clone();
    let c = g
        .lookup(n, &[Value::Int(2)])
        .unwrap()
        .unwrap()
        .values
        .last()
        .unwrap()
        .clone();
    assert!(a < b && b < c, "fixture requires a two-link parent chain");
    let old = g.lookup(f, &[c.clone()]).unwrap().unwrap();
    let Dependency::Fact(witness) = old.witness else {
        panic!("constructor fact")
    };
    let address = g.fact_port(witness, 0).unwrap();
    assert_eq!(g.read_port(address).unwrap(), c);
    g.enqueue_union(b.clone(), c.clone()).unwrap();
    g.repair().unwrap();
    assert_eq!(g.read_port(address).unwrap(), b);
    g.enqueue_union(a.clone(), b.clone()).unwrap();
    g.repair().unwrap();
    assert_eq!(g.fact_port(witness, 0), Some(address));
    let probes = g.stable_port_report()["stats"]["root_parent_probes"]
        .as_u64()
        .unwrap();
    assert_eq!(g.read_port(address).unwrap(), a);
    assert_eq!(
        g.stable_port_report()["stats"]["root_parent_probes"]
            .as_u64()
            .unwrap()
            - probes,
        3,
        "the original binding follows both links; union must not rewrite it"
    );
    assert_eq!(
        old.values[0], c,
        "a previously returned row is an immutable snapshot"
    );
    let domains = g.stable_port_report()["stats"]["port_domain_probes"]
        .as_u64()
        .unwrap();
    assert_eq!(g.lookup(f, &[a.clone()]).unwrap().unwrap().values[0], a);
    assert!(
        g.stable_port_report()["stats"]["port_domain_probes"]
            .as_u64()
            .unwrap()
            > domains,
        "alias lookup must complete an immutable birth-hint miss"
    );
    g.hide(f, &[a.clone()], true).unwrap();
    assert!(g.fact(witness).unwrap().is_none());
    assert!(
        g.read_port(address).is_err(),
        "retired component must not resolve a stale address"
    );
    g.dynamic_construct(f, vec![a.clone()]).unwrap();
    let new = g.lookup(f, &[a]).unwrap().unwrap();
    let Dependency::Fact(new_witness) = new.witness else {
        panic!("constructor fact")
    };
    assert_ne!(g.fact_port(new_witness, 0), Some(address));
    assert!(g.read_port(address).is_err());
    g.ownership_report();
    g.stable_port_report();
}

#[test]
fn dynamic_miss_reuses_lookup_without_changing_slots_ids_or_alias_semantics() {
    use eggfuse_cell_runtime::program::Arg;
    use std::collections::BTreeMap;

    let p = source("(datatype E (N i64) (F E)) (N 0) (N 1) (run-schedule (run))");
    let n = p.tables.iter().position(|t| t.name == "N").unwrap();
    let f = p.tables.iter().position(|t| t.name == "F").unwrap();
    for ports in [false, true] {
        let make = |p| if ports { Graph::new_with_local_congruence(p) }
            else { Graph::new_with_repair_ports(p) }.unwrap();
        let mut actual = make(p.clone());
        let mut reference = make(p.clone());
        let a = actual.lookup(n, &[Value::Int(0)]).unwrap().unwrap().values[1].clone();
        let b = actual.lookup(n, &[Value::Int(1)]).unwrap().unwrap().values[1].clone();
        for graph in [&mut actual, &mut reference] {
            graph.enqueue_union(a.clone(), b.clone()).unwrap();
            graph.repair().unwrap();
        }
        // b is an old, noncanonical alias. Exercise miss, canonical hit,
        // deletion and recreation, comparing the former two-lookup path.
        for (i, input) in [b.clone(), a.clone(), b.clone()].into_iter().enumerate() {
            if i == 2 {
                actual.hide(f, &[b.clone()], true).unwrap();
                reference.hide(f, &[b.clone()], true).unwrap();
            }
            let before = actual.key_lookup_calls.get();
            let value = actual.dynamic_construct(f, vec![input.clone()]).unwrap();
            assert_eq!(actual.key_lookup_calls.get() - before, 1);
            let old = if let Some(row) = reference.lookup(f, &[input.clone()]).unwrap() {
                row.values.last().unwrap().clone()
            } else {
                let frame = reference.frame(reference.program.table_templates[f],
                    BTreeMap::from([(0, input)])).unwrap();
                reference.construct(frame, 0, f, &[Arg::Slot(0)], 1).unwrap()
            };
            assert_eq!(value, old, "result IDs must stay stable");
            assert_eq!(actual.export().unwrap(), reference.export().unwrap());
            assert_eq!(actual.stats.constructor_requests, reference.stats.constructor_requests);
            assert_eq!(actual.stats.constructor_reused, reference.stats.constructor_reused);
            assert_eq!(actual.stats.cells_created, reference.stats.cells_created);
            assert_eq!(actual.lookup(f, &[b.clone()]).unwrap().unwrap().values[0], a);
        }
    }
}

#[test]
fn simultaneous_input_changes_preserve_the_ordered_survivor() {
    compare(
        r#"
(datatype E (N i64) (F E) (G E))
(ruleset build) (ruleset merge)
(rule ((= x (N 1)) (= y (N 2))) ((G (F x)) (G (F y))) :ruleset build)
(rule ((= z (N 0)) (= x (N 1)) (= y (N 2))) ((union z x) (union z y)) :ruleset merge)
(N 0) (N 1) (N 2)
(run-schedule (seq (run build) (run merge)))
(check (= (G (F (N 1))) (G (F (N 2)))))
"#,
    );
}

#[test]
fn equal_input_ports_do_not_collapse_distinct_scalar_keys() {
    let e = compare(
        r#"
(datatype E (N i64) (F i64 E))
(ruleset build) (ruleset merge)
(rule ((= x (N 0)) (= y (N 1))) ((F 10 x) (F 20 y)) :ruleset build)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run build) (run merge)))
"#,
    );
    let f = e
        .graph
        .program
        .tables
        .iter()
        .position(|t| t.name == "F")
        .unwrap();
    assert_eq!(e.graph.witness_count(f), 2);
}
