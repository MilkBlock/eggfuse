use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use serde_json::json;
use std::collections::BTreeSet;
fn program(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("ownership", src).unwrap();
    let raw = compiler::compile(core, &BTreeSet::new()).unwrap();
    let p = Program::parse(raw.clone()).unwrap();
    let mut g = Graph::new_with_cell_ownership(p).unwrap();
    g.train_ownership_fragments().unwrap();
    let mut training = Executor::new(g, false);
    training.execute().unwrap();
    let profile = training.graph.ownership_fragment_profile().unwrap();
    // Semantic fixtures exercise every observed bounded continuation, including
    // single-use paths. Production selection has its own repeated-use test.
    let mut raw = raw;
    raw["ownership_fragments"] = json!({"schema":"eggfuse-ownership-fragments/v2", "source":profile["source"],
        "fragments":profile["records"].as_array().unwrap().iter().map(|r|r["fragment"].clone()).collect::<Vec<_>>()});
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = eggfuse_cell_runtime::checksum::artifact_digest(&raw).into();
    Program::parse(raw).unwrap()
}

#[test]
fn saturation_observer_sees_birth_free_effects_and_rejects_unproved_work() {
    for (body, outcome) in [
        ("(N n)", "rhs_covered"),
        ("(union x x)", "rhs_covered_by_inputs"),
        ("(F x)", "missing_local_constructor"),
        ("(union x (N 1))", "write_effect"),
    ] {
        let source = format!("(datatype E (N i64) (F E)) (N 0) (N 1) (ruleset r)\n(rule ((= x (N n))) ({body}) :ruleset r) (run r 1)");
        let core = eggfuse_bake::device_frontend::core("saturation", &source).unwrap();
        let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
        let mut a = Executor::new(Graph::new_with_cell_ownership(p.clone()).unwrap(), true);
        let mut g = Graph::new_with_cell_ownership(p).unwrap();
        g.trace_ownership_catalog(8).unwrap();
        let mut b = Executor::new(g, true);
        a.execute().unwrap(); b.execute().unwrap();
        assert_eq!(a.graph.export().unwrap(), b.graph.export().unwrap());
        assert_eq!(a.snapshots, b.snapshots);
        assert_eq!(a.binding_audit, b.binding_audit);
        let report = b.graph.ownership_catalog_trace().unwrap();
        let rows = report["saturation"]["rows"].as_array().unwrap();
        assert!(rows.iter().any(|r|r["outcome"] == outcome), "{body}: {report}");
        let applications = rows.iter().map(|r|r["counts"]["applications"].as_u64().unwrap()).sum::<u64>();
        assert_eq!(applications, 2, "count applications, not anchor alternatives");
    }
}

#[test]
fn saturation_observer_does_not_skip_a_nontrivial_union() {
    let source = "(datatype E (N i64)) (N 0) (N 1) (ruleset r)
        (rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset r) (run r 1)";
    let core = eggfuse_bake::device_frontend::core("union-coverage", source).unwrap();
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut g = Graph::new_with_cell_ownership(p).unwrap();
    g.trace_ownership_catalog(8).unwrap();
    let mut e = Executor::new(g, false);
    e.execute().unwrap();
    let report = e.graph.ownership_catalog_trace().unwrap();
    let rows = report["saturation"]["rows"].as_array().unwrap();
    assert_eq!(rows.len(), 1, "{report}");
    assert_eq!(rows[0]["outcome"], "nontrivial_union", "{report}");
    assert_eq!(rows[0]["counts"]["applications"], 1);
}
fn compare(src: &str) -> Executor {
    let p = program(src);
    let mut a = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_cell_ownership(p.clone()).unwrap(), true);
    let mut port_keys = Executor::new(Graph::new_with_scoped_completion(p.clone()).unwrap(), true);
    let mut scoped = Executor::new(Graph::new_with_scoped_completion(p.clone()).unwrap(), false);
    let mut port_scopes = Executor::new(Graph::new_with_scoped_completion(p).unwrap(), false);
    port_scopes.use_port_scopes().unwrap();
    port_scopes.execute().unwrap();
    scoped.use_scoped_execution().unwrap();
    scoped.execute().unwrap();
    a.execute().unwrap();
    b.execute().unwrap();
    port_keys.execute().unwrap();
    assert_eq!(a.graph.export().unwrap(), port_scopes.graph.export().unwrap());
    assert_eq!(a.steps.len(), port_scopes.steps.len());
    for (x, y) in a.steps.iter().zip(&port_scopes.steps) {
        for k in ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed"] {
            assert_eq!(x[k], y[k], "port scopes: {k}");
        }
    }
    assert_eq!(a.graph.export().unwrap(), scoped.graph.export().unwrap());
    assert_eq!(a.steps.len(), scoped.steps.len());
    for (x, y) in a.steps.iter().zip(&scoped.steps) {
        for k in ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed"] {
            assert_eq!(x[k], y[k], "scoped execution: {k}");
        }
    }
    assert_eq!(a.initial_audit, port_keys.initial_audit);
    assert_eq!(a.snapshots, port_keys.snapshots);
    assert_eq!(a.binding_audit, port_keys.binding_audit);
    assert_eq!(a.steps.len(), port_keys.steps.len());
    for (x, y) in a.steps.iter().zip(&port_keys.steps) {
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
            assert_eq!(x[k], y[k], "port keys: {k}");
        }
    }
    port_keys.graph.ownership_report();
    port_keys.graph.stable_port_report();
    assert_eq!(a.initial_audit, b.initial_audit);
    assert_eq!(a.snapshots, b.snapshots);
    assert_eq!(a.binding_audit, b.binding_audit);
    assert_eq!(a.steps.len(), b.steps.len());
    for (x, y) in a.steps.iter().zip(&b.steps) {
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
            assert_eq!(x[k], y[k], "{k}");
        }
    }
    a.graph.maintenance_report();
    b.graph.maintenance_report();
    assert_eq!(b.graph.ownership_report()["pending_keys"], 0);
    egglog::EGraph::default()
        .parse_and_run_program(None, src)
        .unwrap();
    b
}
const STAGES: &str = r#"
(datatype E (N i64) (F E) (G E) (H E) (Seen E))
(ruleset a) (ruleset b) (ruleset c)
(rule ((= x (N n))) ((G (F x))) :ruleset a)
(rule ((= x (G y))) ((H x)) :ruleset b)
(rule ((= x (H y))) ((Seen x)) :ruleset c)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run c)))
"#;

#[path = "support/port_sharing.rs"]
mod port_sharing;

#[test]
fn source_unions_do_not_split_cell_wiring_or_change_effect_order() {
    use eggfuse_cell_runtime::graph::cell_ownership::composition;
    let core = eggfuse_bake::device_frontend::core("port-sharing", port_sharing::SOURCE).unwrap();
    let raw = compiler::compile(core, &Default::default()).unwrap();
    let mut p = Program::parse(raw.clone()).unwrap();
    p.prepare_cell_ownership().unwrap();
    let a = p.rules[p.sets["a"][0]].template;
    let b = p.rules[p.sets["b"][0]].template;
    let markers = &p.cell_ownership.markers;
    assert_eq!(markers[a].program_id, markers[b].program_id);
    assert!(std::sync::Arc::ptr_eq(&markers[a].program, &markers[b].program));
    let wire = p.cell_ownership.artifact(&p);
    assert_eq!(wire["schema"], "eggfuse-ownership-markers/v5");
    assert!(wire["plan"]["programs"].as_array().unwrap().iter().all(|x| x.get("unions").is_none()));
    assert!(wire["plan"]["markers"].as_array().unwrap().iter().all(|x| x.get("unions").is_none()));

    // Legacy addresses are reconstructed from borrowed source operations only
    // while loading/emitting. Their full certificates are still checked.
    let mut legacy = raw;
    legacy["ownership_fragments"] = json!({"schema":"eggfuse-ownership-fragments/v1",
        "source":composition::source_digest(&legacy),"fragments":[]});
    let old = reparse(legacy);
    assert_ne!(old.cell_ownership.markers[a].program_id, old.cell_ownership.markers[b].program_id);
    assert!(old.cell_ownership.programs.len() > p.cell_ownership.programs.len());
    let mut bad = old.artifact.clone();
    bad["ownership_markers"] = old.cell_ownership.artifact(&old);
    let id = old.cell_ownership.markers[a].program_id;
    let unions = bad["ownership_markers"]["plan"]["programs"][id]["unions"].as_array_mut().unwrap();
    *unions.iter_mut().find(|v| !v.is_null()).unwrap() = json!(null);
    bad.as_object_mut().unwrap().remove("sha256");
    bad["sha256"] = eggfuse_cell_runtime::checksum::artifact_digest(&bad).into();
    assert!(Program::parse(bad).unwrap_err().contains("ownership marker"));

    let mut legacy = Executor::new(Graph::new_with_cell_ownership(old).unwrap(), true);
    let mut current = Executor::new(Graph::new_with_cell_ownership(p).unwrap(), true);
    legacy.execute().unwrap();
    current.execute().unwrap();
    assert_eq!(legacy.initial_audit, current.initial_audit);
    assert_eq!(legacy.snapshots, current.snapshots);
    assert_eq!(legacy.binding_audit, current.binding_audit);
    assert_eq!(legacy.graph.export().unwrap(), current.graph.export().unwrap());
    assert_eq!(legacy.graph.stats.union_requests, current.graph.stats.union_requests);
    // Also exercise trained continuations, native source checks and the existing
    // repair/scoped backends with the newly shared program addresses.
    compare(port_sharing::SOURCE);
}
#[test]
fn live_bodies_cross_stages_without_internal_subscriptions() {
    let e = compare(STAGES);
    let r = e.graph.ownership_report();
    let s = &r["stats"];
    assert!(s["owned_live"].as_u64().unwrap() > 0, "{r}");
    assert!(
        s["composition_cross_stage_joins"].as_u64().unwrap() > 0,
        "{r}"
    );
    assert!(s["internal_ports_seen"].as_u64().unwrap() > 0, "{r}");
    assert!(
        s["carried_facts"].as_u64().unwrap() > s["owned_live"].as_u64().unwrap(),
        "{r}"
    );
    assert_eq!(s["unbound_query_rows"], 0, "{r}");
    assert_eq!(
        e.graph.maintenance_report()["stats"]["live_reverse_edges"],
        0
    );
}
#[test]
fn equality_candidate_domains_use_owner_boundaries_without_table_fallback() {
    let e = compare(STAGES);
    let g = &e.graph;
    let before = g.ownership_report()["stats"]["unbound_query_rows"].clone();
    for table in 0..g.program.tables.len() {
        if !g.program.cell_ownership.tables[table] {
            continue;
        }
        let rows = g
            .witnesses(table)
            .into_iter()
            .filter_map(|w| g.row(w).unwrap())
            .collect::<Vec<_>>();
        for row in &rows {
            for (col, v) in row.values.iter().enumerate() {
                if !matches!(v, eggfuse_cell_runtime::value::Value::Eq(_)) {
                    continue;
                }
                let mut bound = vec![None; row.values.len()];
                bound[col] = Some(v.clone());
                let expected = rows
                    .iter()
                    .filter(|r| r.values[col] == *v)
                    .map(|r| r.witness)
                    .collect::<BTreeSet<_>>();
                let candidates = g
                    .candidates(table, &bound)
                    .into_iter()
                    .collect::<BTreeSet<_>>();
                assert!(expected.is_subset(&candidates));
                assert!(g.candidate_count(table, &bound) >= expected.len());
            }
        }
    }
    let r = g.ownership_report();
    assert!(r["stats"]["domain_queries"].as_u64().unwrap() > 0);
    assert_eq!(r["stats"]["unbound_query_rows"], before);
}
#[test]
fn late_boundary_unions_complete_owned_congruence_and_keep_ownership() {
    let prefix=STAGES.replace("(N 0) (N 1)","(ruleset merge)\n(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)\n(N 0) (N 1)");
    let src = format!(
        "{prefix}\n(run-schedule (seq (run merge) (run c)))\n(check (= (H (G (F (N 0)))) (H (G (F (N 1))))))"
    );
    let e = compare(&src);
    let r = e.graph.ownership_report();
    assert!(r["stats"]["key_completions"].as_u64().unwrap() > 0, "{r}");
    assert!(r["stats"]["owned_retirements"].as_u64().unwrap() > 0, "{r}");
    assert!(r["stats"]["owned_live"].as_u64().unwrap() > 0, "{r}");
    assert_eq!(
        e.graph.maintenance_report()["stats"]["live_reverse_edges"],
        0
    );
}
#[test]
fn native_result_aliases_and_query_domains_survive_multiple_union_waves() {
    for (left, right) in [
        ("x", "y"),
        ("(F x)", "y"),
        ("(G (F x))", "(F y)"),
        ("(F x)", "(F y)"),
    ] {
        let src = format!(
            r#"
(datatype E (N i64) (F E) (G E) (H E) (Seen E))
(ruleset a) (ruleset b) (ruleset merge) (ruleset read)
(rule ((= x (N n))) ((G (F x))) :ruleset a)
(rule ((= x (G y))) ((H x)) :ruleset b)
(rule ((= x (N 0)) (= y (N 1))) ((union {left} {right})) :ruleset merge)
(rule ((= z (G x)) (= w (H z))) ((Seen x)) :ruleset read)
(N 0) (N 1) (N 2)
(run-schedule (seq (run a) (run b) (run merge) (run read) (run a) (run b) (run read)))
"#
        );
        compare(&src);
    }
}
#[test]
fn wide_bodies_preserve_native_routes_without_lifetime_owner_splits() {
    let mut src = String::from(
        "(datatype E (N i64) (F E) (G E))\n(ruleset make) (ruleset merge)\n(rule ((= x (N 0))) (",
    );
    for i in 0..270 {
        src.push_str(&format!("(G (F (N {i}))) "));
    }
    src.push_str(" ) :ruleset make)\n(rule ((= x (N 0)) (= y (N 269))) ((union x y)) :ruleset merge)\n(N 0)\n(run-schedule (seq (run make) (run merge)))");
    let e = compare(&src);
    let r = e.graph.ownership_report();
    assert!(r["stats"]["owned_live"].as_u64().unwrap() > 256);
    assert!(r["inventory"]["largest_component_frames"].as_u64().unwrap() <= 4);
}
#[test]
fn deletion_external_aliases_and_mutable_merges_remain_visible() {
    compare(
        r#"
(datatype E (N i64) (F E) (G E) (H E))
(function count (E) i64 :merge (+ old new))
(ruleset a) (ruleset erase) (ruleset merge) (ruleset read)
(rule ((= x (N n))) ((G (F x)) (set (count x) 1)) :ruleset a)
(rule ((= x (N 0))) ((delete (F x))) :ruleset erase)
(rule ((= z (G x)) (= y (N 2))) ((union x y)) :ruleset merge)
(rule ((= z (G x))) ((H z)) :ruleset read)
(N 0) (N 1) (N 2)
(run-schedule (seq (run a) (run erase) (run merge) (run read)))
"#,
    );
}
#[test]
fn bake_emits_checked_markers_without_executing_the_program() {
    use std::{fs, process::Command};
    let p = program(STAGES);
    assert!(
        p.cell_ownership
            .markers
            .iter()
            .enumerate()
            .any(|(i, m)| m.program.active() && !p.templates[i].ops.iter().any(|op| matches!(op, eggfuse_cell_runtime::program::Op::Union(..))))
    );
    assert!(p.cell_ownership.routes.iter().any(|r| !r.is_empty()));
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("input.json");
    let out = temp.path().join("baked");
    fs::write(&input, serde_json::to_vec(&p.artifact).unwrap()).unwrap();
    let r = Command::new(env!("CARGO_BIN_EXE_eggfuse-cell-compiler"))
        .args(["bake-cell-ownership", "--program"])
        .arg(input)
        .arg("--output")
        .arg(&out)
        .output()
        .unwrap();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    let mut raw: serde_json::Value =
        serde_json::from_slice(&fs::read(out.join("program.json")).unwrap()).unwrap();
    Program::parse(raw.clone()).unwrap();
    assert!(!out.join("trial.json").exists());
    raw["ownership_markers"]["plan"]["composition"]["max_frames"] = json!(1);
    assert!(Program::parse(raw).is_err());
}

#[test]
fn unrelated_bodies_do_not_amplify_cross_stage_repair() {
    let mut reference = None;
    let mut evidence = Vec::new();
    for noise in [0, 32, 300] {
        let extras = (0..noise)
            .map(|i| format!("(Noise {i}) "))
            .collect::<String>();
        let src = format!(
            r#"
(datatype E (N i64) (F E) (G E) (H E) (Noise i64))
(ruleset a) (ruleset b) (ruleset merge)
(rule ((= x (N 0)) (= y (N 1))) ((G (F x)) (G (F y)) {extras}) :ruleset a)
(rule ((= z (G x))) ((H z)) :ruleset b)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run merge)))
(check (= (H (G (F (N 0)))) (H (G (F (N 1))))))
"#
        );
        let e = compare(&src);
        let report = e.graph.ownership_report();
        let stats = &report["stats"];
        let work = [
            "port_checks",
            "changed_ports",
            "body_visits",
            "slice_steps",
            "signal_activations",
        ]
        .map(|k| stats[k].as_u64().unwrap());
        if let Some(expected) = reference {
            assert_eq!(work, expected, "noise={noise}");
        } else {
            reference = Some(work);
        }
        assert_eq!(stats["port_checks"], stats["changed_ports"]);
        assert_eq!(stats["boundary_body_reads"], 0);
        assert_eq!(stats["boundary_rebuilds"], 0);
        assert!(stats["marker_union_requests"].as_u64().unwrap() > 0);
        if noise == 0 {
            assert!(stats["composition_cross_stage_joins"].as_u64().unwrap() > 0);
        }
        evidence
            .push(json!({"unrelated_bodies":noise,"inventory":report["inventory"],"stats":stats}));
    }
    println!(
        "SLICE_EVIDENCE {}",
        json!({"scope":"standalone Cell CPU; structural regression fixture, not timing", "cases":evidence})
    );
}

#[test]
fn future_union_after_failed_delete_never_activates_a_marker() {
    let e = compare(
        r#"
(datatype E (N i64) (F E) (G E))
(ruleset make)
(rule ((= x (N 0)) (= y (N 1)))
      ((G x) (G y) (delete (F x)) (union x y)) :ruleset make)
(N 0) (N 1)
(run-schedule (run make))
"#,
    );
    let r = e.graph.ownership_report();
    assert_eq!(r["stats"]["marker_union_requests"], 0);
    assert_eq!(r["stats"]["signal_activations"], 0);
    assert_eq!(e.graph.stats.unions, 0);
}

#[test]
fn shared_symbol_program_survives_origin_deletion_and_repeated_aliases() {
    let e = compare(
        r#"
(datatype E (N i64) (F E) (G E) (H E) (Pair E E))
(ruleset make) (ruleset erase) (ruleset merge) (ruleset again) (ruleset read)
(rule ((= x (N 0))) ((G (F x)) (Pair (F x) (F x))) :ruleset make)
(rule ((= x (N 0))) ((delete (F x))) :ruleset erase)
(rule ((= z (G x)) (= y (N 1))) ((union x y)) :ruleset merge)
(rule ((= x (N 1)) (= y (N 2))) ((union x y)) :ruleset again)
(rule ((= z (G x)) (= q (Pair x x))) ((H q)) :ruleset read)
(N 0) (N 1) (N 2)
(run-schedule (seq (run make) (run erase) (run merge) (run again) (run read)))
"#,
    );
    let r = e.graph.ownership_report();
    assert_eq!(r["stats"]["unchanged_port_checks"], 0);
    assert_eq!(r["stats"]["boundary_body_reads"], 0);
    assert!(r["stats"]["changed_ports"].as_u64().unwrap() > 0);
}

#[test]
fn symbolic_program_is_shared_and_untrusted_artifacts_are_rechecked() {
    let p = program(STAGES);
    let mut raw = p.artifact.clone();
    let marker = p
        .cell_ownership
        .markers
        .iter()
        .position(|m| !m.program.signals.is_empty())
        .unwrap();
    raw["ownership_markers"] = p.cell_ownership.artifact(&p);
    raw["ownership_markers"]["plan"]["programs"][p.cell_ownership.markers[marker].program_id]["signals"]
        [0][0]["columns"] = json!([999]);
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = eggfuse_cell_runtime::checksum::artifact_digest(&raw).into();
    let err = Program::parse(raw).unwrap_err();
    assert!(err.contains("ownership marker"), "{err}");
    // Import constructors with the same field structure share the actual
    // immutable program allocation, not a per-instance copy of destinations.
    let mut shared = false;
    for (i, a) in p.cell_ownership.markers.iter().enumerate() {
        for b in &p.cell_ownership.markers[i + 1..] {
            if !a.program.signals.is_empty() && a.program == b.program {
                assert!(std::sync::Arc::ptr_eq(&a.program, &b.program));
                shared = true;
            }
        }
    }
    assert!(shared);
}

#[test]
fn composition_substitutions_are_rechecked_even_with_a_valid_checksum() {
    let p = program(STAGES);
    let mut raw = p.artifact.clone();
    raw["ownership_markers"] = p.cell_ownership.artifact(&p);
    raw["ownership_markers"]["plan"]["composition"]["transitions"][0][0]["hop"]["source_frame"] =
        json!(999);
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = eggfuse_cell_runtime::checksum::artifact_digest(&raw).into();
    let err = Program::parse(raw).unwrap_err();
    assert!(err.contains("ownership marker"), "{err}");
}

#[test]
fn deletion_and_recreation_do_not_collapse_distinct_result_signals() {
    let e = compare(
        r#"
(datatype E (N i64) (F E) (G E) (H E))
(ruleset make) (ruleset merge)
(rule ((= x (N 0)))
      ((let a (F x)) (G a) (delete (F x)) (let b (F x)) (H b)) :ruleset make)
(rule ((= g (G a)) (= h (H b))) ((union a b)) :ruleset merge)
(N 0)
(run-schedule (seq (run make) (run merge)))
"#,
    );
    let r = e.graph.ownership_report();
    assert_eq!(r["stats"]["unchanged_port_checks"], 0);
    assert_eq!(r["stats"]["boundary_body_reads"], 0);
}

#[test]
fn checked_entries_share_slots_across_all_stages_of_identical_chains() {
    let initial = Graph::new_with_cell_ownership(program(STAGES))
        .unwrap()
        .ownership_report();
    let e = compare(STAGES);
    let r = e.graph.ownership_report();
    let s = &r["stats"];
    assert_eq!(
        s["boundary_live"], initial["stats"]["boundary_live"],
        "the closed chains must add no cross-template root bindings beyond their imported inputs"
    );
    assert_eq!(
        s["components_live"], 2,
        "one component per independent seed"
    );
    assert!(s["composition_substituted_ports"].as_u64().unwrap() >= 6);
    assert!(s["composition_baked_hits"].as_u64().unwrap() > 0);
    assert_eq!(s["composition_shape_builds"], 0);
    assert_eq!(s["composition_materializations"], 0);
    assert_eq!(s["composition_shape_steps"], 0);
    println!("COMPOSITION_EVIDENCE {}", r);
}

#[test]
fn component_keeps_a_deleted_producer_port_alive_for_later_external_union() {
    let e = compare(
        r#"
(datatype E (N i64) (F E) (G E) (H E))
(ruleset a) (ruleset b) (ruleset erase) (ruleset merge) (ruleset read)
(rule ((= x (N 0))) ((F x)) :ruleset a)
(rule ((= f (F x)) (= y (N 1))) ((G f)) :ruleset b)
(rule ((= x (N 0))) ((delete (F x))) :ruleset erase)
(rule ((= g (G x)) (= y (N 1))) ((union x y)) :ruleset merge)
(rule ((= g (G x))) ((H g)) :ruleset read)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run erase) (run merge) (run read)))
"#,
    );
    let r = e.graph.ownership_report();
    assert!(
        r["stats"]["composition_substituted_ports"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert_eq!(r["stats"]["unchanged_port_checks"], 0);
}

#[test]
fn dynamically_aliased_inputs_merge_ordered_slices_without_duplicate_field_work() {
    let e = compare(
        r#"
(datatype E (N i64) (Pair E E) (Both E E) (After E))
(ruleset a) (ruleset merge) (ruleset read)
(rule ((= p (Pair x y))) ((Both x y)) :ruleset a)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(rule ((= b (Both x y))) ((After b)) :ruleset read)
(N 0) (Pair (N 1) (N 1))
(run-schedule (seq (run a) (run merge) (run read)))
"#,
    );
    let r = e.graph.ownership_report();
    assert!(r["stats"]["coalesced_slice_steps"].as_u64().unwrap() > 0);
    assert_eq!(r["stats"]["port_checks"], r["stats"]["changed_ports"]);
    assert!(r["stats"]["dispatch_heap_pops"].as_u64().unwrap() > 0);
}

#[test]
fn composition_capacity_cuts_keep_external_notifications_complete() {
    let mut src = String::from("(datatype E (N i64)");
    for i in 0..20 {
        src.push_str(&format!(" (F{i} E)"));
    }
    src.push_str(")\n(ruleset merge)\n(N 0) (N 1)\n");
    for i in 0..20 {
        src.push_str(&format!(
            "(ruleset r{i})\n(rule ((= x (N n))) ((F{i} x)) :ruleset r{i})\n"
        ));
    }
    src.push_str(
        "(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)\n(run-schedule (seq",
    );
    for i in 0..20 {
        src.push_str(&format!(" (run r{i})"));
    }
    src.push_str(" (run merge)))\n(check (= (F19 (N 0)) (F19 (N 1))))\n");
    let e = compare(&src);
    let r = e.graph.ownership_report();
    assert!(r["stats"]["components_live"].as_u64().unwrap() > 2);
    assert!(r["inventory"]["largest_component_frames"].as_u64().unwrap() <= 4);
    assert_eq!(r["stats"]["boundary_body_reads"], 0);
    assert_eq!(r["stats"]["port_checks"], r["stats"]["changed_ports"]);
}

fn raw_program(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("ownership", src).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn reparse(mut raw: serde_json::Value) -> Program {
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = eggfuse_cell_runtime::checksum::artifact_digest(&raw).into();
    Program::parse(raw).unwrap()
}
#[test]
fn ordinary_load_and_execution_do_not_prepare_ownership_plans() {
    let p = raw_program(STAGES);
    assert!(p.cell_ownership.markers.is_empty());
    let mut e = Executor::new(Graph::new_with_repair_ports(p).unwrap(), true);
    e.execute().unwrap();
    assert!(e.graph.program.cell_ownership.markers.is_empty());
    assert_eq!(e.graph.ownership_report()["plan_prepared"], false);
}
#[test]
fn unseen_continuations_keep_external_union_notifications_without_compiling_code() {
    let src=STAGES.replace("(N 0) (N 1)","(ruleset merge)\n(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)\n(N 0) (N 1)");
    let src = format!("{src}\n(run-schedule (seq (run merge) (run c)))");
    let p = raw_program(&src);
    let mut a = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_cell_ownership(p).unwrap(), true);
    let shapes = b.graph.program.cell_ownership.composition.shapes.len();
    a.execute().unwrap();
    b.execute().unwrap();
    assert_eq!(a.snapshots, b.snapshots);
    assert_eq!(a.binding_audit, b.binding_audit);
    let r = b.graph.ownership_report();
    assert_eq!(r["stats"]["composition_transition_probes"], 0);
    assert_eq!(r["stats"]["composition_requests"], 0);
    assert_eq!(r["stats"]["composition_materializations"], 0);
    assert_eq!(r["inventory"]["runtime_composition_shapes"], json!(shapes));
    assert!(r["stats"]["key_completions"].as_u64().unwrap() > 0);
}
#[test]
fn a_local_suffix_is_shared_after_unrelated_producer_prefixes() {
    let src = r#"
(datatype E (N i64) (F E) (G E) (H E) (Seen E))
(ruleset a) (ruleset b) (ruleset c)
(rule ((= x (N 0))) ((F x)) :ruleset a)
(rule ((= x (N 1))) ((G (F x))) :ruleset a)
(rule ((= f (F x))) ((H f)) :ruleset b)
(rule ((= h (H f))) ((Seen h)) :ruleset c)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run c)))
"#;
    let p = program(src);
    let mut raw = p.artifact.clone();
    let rid = p.rules.len() - 1;
    let fragments = raw["ownership_fragments"]["fragments"]
        .as_array_mut()
        .unwrap();
    fragments
        .retain(|f| f["hops"].as_array().unwrap().len() == 1 && f["hops"][0]["rule"] == json!(rid));
    assert_eq!(
        fragments.len(),
        1,
        "one local H -> Seen route, independent of the F/G prefix"
    );
    let p = reparse(raw);
    let mut a = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_cell_ownership(p).unwrap(), true);
    a.execute().unwrap();
    b.execute().unwrap();
    assert_eq!(a.snapshots, b.snapshots);
    assert_eq!(a.binding_audit, b.binding_audit);
    let r = b.graph.ownership_report();
    assert_eq!(r["stats"]["composition_baked_hits"], 2);
    assert_eq!(r["stats"]["composition_shape_steps"], 0);
    assert_eq!(r["stats"]["marker_entries"], 2);
}
#[test]
fn profile_selection_requires_repeated_actual_shared_inputs() {
    use eggfuse_cell_runtime::graph::cell_ownership::composition::select_profile;
    for (src, expected) in [
        (STAGES.to_string(), true),
        (STAGES.replace("(N 0) (N 1)", "(N 0)"), false),
    ] {
        let mut g = Graph::new_with_cell_ownership(raw_program(&src)).unwrap();
        g.train_ownership_fragments().unwrap();
        let mut e = Executor::new(g, false);
        e.execute().unwrap();
        let profile = e.graph.ownership_fragment_profile().unwrap();
        let selected = select_profile(&profile).unwrap();
        assert_eq!(
            !selected["fragments"].as_array().unwrap().is_empty(),
            expected
        );
        assert_eq!(profile["alternatives_overlap"], true);
    }
}
#[test]
fn fragment_loading_validates_routes_even_before_enabling_ownership() {
    let p = program(STAGES);
    let mut raw = p.artifact.clone();
    raw["ownership_fragments"]["fragments"][0]["hops"][0]["source_frame"] = json!(999);
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = eggfuse_cell_runtime::checksum::artifact_digest(&raw).into();
    assert!(
        Program::parse(raw)
            .unwrap_err()
            .contains("ownership fragment")
    );
}

#[test]
fn different_entry_guards_share_identical_local_code() {
    let src = r#"
(datatype E (N i64) (F E))
(ruleset a)
(rule ((= x (N 0))) ((F x)) :ruleset a)
(rule ((= x (N 1))) ((F x)) :ruleset a)
(N 0) (N 1)
(run-schedule (run a))
"#;
    let p = program(src);
    let plan = &p.cell_ownership.composition;
    assert_eq!(plan.transitions.len(), 2);
    assert_eq!(plan.transitions[0].1, plan.transitions[1].1);
    assert_eq!(plan.shapes.len(), p.cell_ownership.programs.len() + 1);
    let mut e = Executor::new(Graph::new_with_cell_ownership(p).unwrap(), true);
    e.execute().unwrap();
    assert_eq!(
        e.graph.ownership_report()["stats"]["composition_baked_hits"],
        2
    );
}

#[test]
fn active_marker_with_an_unseen_prefix_falls_back_without_expanding_code() {
    let src = r#"
(datatype E (N i64) (F E) (G E) (H E))
(ruleset a) (ruleset b) (ruleset merge)
(rule ((= x (N 0))) ((F x)) :ruleset a)
(rule ((= x (N 1))) ((G (F x))) :ruleset a)
(rule ((= f (F x))) ((H f)) :ruleset b)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run a) (run b) (run merge)))
"#;
    let p = program(src);
    let mut raw = p.artifact.clone();
    let fragments = raw["ownership_fragments"]["fragments"]
        .as_array_mut()
        .unwrap();
    fragments.retain(|f| {
        f["hops"].as_array().unwrap().len() == 2
            && f["hops"][0]["rule"] == 0
            && f["hops"][1]["rule"] == 2
    });
    assert_eq!(fragments.len(), 1);
    let p = reparse(raw);
    let mut a = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_cell_ownership(p).unwrap(), true);
    a.execute().unwrap();
    b.execute().unwrap();
    assert_eq!(a.snapshots, b.snapshots);
    assert_eq!(a.binding_audit, b.binding_audit);
    let r = b.graph.ownership_report();
    assert!(
        r["stats"]["composition_unbaked_fallbacks"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert_eq!(r["stats"]["composition_materializations"], 0);
    assert!(r["stats"]["key_completions"].as_u64().unwrap() > 0);
}

#[test]
fn component_retirement_cleans_previously_inactive_signal_slots() {
    let src = r#"
(datatype E (N i64) (F E) (Keep E))
(ruleset make) (ruleset erase) (ruleset merge) (ruleset finish)
(rule ((= x (N 0)) (= y (N 1))) ((Keep y) (F x)) :ruleset make)
(rule ((= x (N 0))) ((delete (F x))) :ruleset erase)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(rule ((= y (N 1))) ((delete (Keep y))) :ruleset finish)
(N 0) (N 1)
(run-schedule (seq (run make) (run erase) (run merge) (run finish)))
"#;
    let p = raw_program(src);
    let mut a = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_cell_ownership(p).unwrap(), true);
    a.execute_until(Some(2)).unwrap();
    b.execute_until(Some(2)).unwrap();
    assert_eq!(a.snapshots, b.snapshots);
    assert!(
        b.graph.ownership_report()["inventory"]["retained_inactive_signal_bindings"]
            .as_u64()
            .unwrap()
            > 0
    );
    a.execute().unwrap();
    b.execute().unwrap();
    assert_eq!(a.snapshots, b.snapshots);
    assert_eq!(a.binding_audit, b.binding_audit);
    let r = b.graph.ownership_report();
    assert_eq!(r["stats"]["signal_port_detaches"], 0);
    assert!(
        r["stats"]["component_signal_retire_visits"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert_eq!(r["inventory"]["retained_inactive_signal_bindings"], 0);
    egglog::EGraph::default()
        .parse_and_run_program(None, src)
        .unwrap();
}

#[test]
fn retained_inactive_routes_do_not_return_deleted_candidates() {
    let src = r#"
(datatype E (N i64) (F E) (Keep E))
(ruleset make) (ruleset erase) (ruleset merge)
(rule ((= x (N 0)) (= y (N 1))) ((Keep y) (F x)) :ruleset make)
(rule ((= x (N 0))) ((delete (F x))) :ruleset erase)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run make) (run erase) (run merge)))
"#;
    let p = raw_program(src);
    let mut a = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_cell_ownership(p).unwrap(), true);
    a.execute().unwrap();
    b.execute().unwrap();
    assert_eq!(a.snapshots, b.snapshots);
    assert_eq!(a.binding_audit, b.binding_audit);
    let g = &b.graph;
    let roots = (0..g.program.tables.len())
        .flat_map(|t| g.witnesses(t))
        .flat_map(|w| g.row(w).unwrap().unwrap().values.to_vec())
        .filter(|v| matches!(v, eggfuse_cell_runtime::value::Value::Eq(_)))
        .collect::<BTreeSet<_>>();
    for (table, schema) in g.program.tables.iter().enumerate() {
        let rows = g
            .witnesses(table)
            .into_iter()
            .filter_map(|w| g.row(w).unwrap())
            .collect::<Vec<_>>();
        for (column, sort) in schema.schema.iter().enumerate() {
            if sort["kind"] != "eq" {
                continue;
            }
            for root in &roots {
                let mut bound = vec![None; schema.schema.len()];
                bound[column] = Some(root.clone());
                let candidates = g.candidates(table, &bound);
                assert!(candidates.windows(2).all(|pair| pair[0] < pair[1]),
                    "candidate witnesses must remain sorted and unique");
                assert!(candidates.iter().all(|w| g.row(*w).unwrap().is_some()));
                let expected = rows
                    .iter()
                    .filter(|r| r.values[column] == *root)
                    .map(|r| r.witness)
                    .collect::<BTreeSet<_>>();
                assert!(expected.is_subset(&candidates.into_iter().collect()));
                assert!(g.candidate_count(table, &bound) >= expected.len());
            }
        }
    }
    let r = g.ownership_report();
    assert!(
        r["inventory"]["retained_inactive_signal_bindings"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert!(r["stats"]["domain_queries"].as_u64().unwrap() > 0);
    assert_eq!(r["stats"]["domain_planning_signals"], 0);
    assert_eq!(r["stats"]["domain_planning_slice_steps"], 0);
    assert_eq!(r["stats"]["signal_port_detaches"], 0);
    egglog::EGraph::default()
        .parse_and_run_program(None, src)
        .unwrap();
}

#[test]
fn baked_cells_rederive_the_same_plan_without_materialized_marker_json() {
    use std::{fs,process::Command};
    let p=program(STAGES);
    let temp=tempfile::tempdir().unwrap();
    let input=temp.path().join("input.json");
    fs::write(&input,serde_json::to_vec(&p.artifact).unwrap()).unwrap();
    let materialized=temp.path().join("materialized");
    let compact=temp.path().join("compact");
    for (input,out,flag) in [(input,materialized.clone(),"true"),
        (materialized.join("program.json"),compact.clone(),"false")] {
        let r=Command::new(env!("CARGO_BIN_EXE_eggfuse-cell-compiler"))
            .args(["bake-cell-ownership","--program"]).arg(input)
            .arg("--output").arg(out).args(["--materialize-markers",flag,"--query-classes","true"]).output().unwrap();
        assert!(r.status.success(),"{}",String::from_utf8_lossy(&r.stderr));
    }
    assert!(materialized.join("markers.json").exists());
    assert!(!compact.join("markers.json").exists());
    let load=|path:std::path::PathBuf| {
        Program::parse(serde_json::from_slice(&fs::read(path).unwrap()).unwrap()).unwrap()
    };
    let mut a=Executor::new(Graph::new_with_local_congruence(load(materialized.join("program.json"))).unwrap(),true);
    let mut b=Executor::new(Graph::new_with_local_congruence(load(compact.join("program.json"))).unwrap(),true);
    assert!(b.graph.program.artifact.get("ownership_markers").is_none());
    assert_eq!(b.graph.program.artifact["ownership_fragments"]["query_classes"],true);
    assert!(a.graph.program.artifact["ownership_fragments"]["query_classes"].is_object());
    assert_eq!(a.graph.program.cell_ownership,b.graph.program.cell_ownership);
    a.execute().unwrap();b.execute().unwrap();
    assert_eq!(a.graph.export().unwrap(),b.graph.export().unwrap());
    assert_eq!(a.snapshots,b.snapshots);
    assert_eq!(a.binding_audit,b.binding_audit);
}

#[test]
fn bounded_longer_catalog_preserves_cross_run_execution() {
    use eggfuse_cell_runtime::{checksum::artifact_digest, graph::cell_ownership::composition};
    assert_eq!(composition::checked_frame_limit(None).unwrap(), 4);
    for invalid in [json!(0), json!(1), json!(33), json!(-1), json!("16")] {
        assert!(composition::checked_frame_limit(Some(&invalid)).is_err());
    }
    let src = r#"
(datatype E (N i64) (A E) (B E) (C E) (D E) (F E) (G E))
(ruleset a) (ruleset b) (ruleset c) (ruleset d) (ruleset f) (ruleset g)
(rule ((= x (N n))) ((A x)) :ruleset a)
(rule ((= x (A y))) ((B x)) :ruleset b)
(rule ((= x (B y))) ((C x)) :ruleset c)
(rule ((= x (C y))) ((D x)) :ruleset d)
(rule ((= x (D y))) ((F x)) :ruleset f)
(rule ((= x (F y))) ((G x)) :ruleset g)
(N 0)
(run-schedule (seq (run a) (run b) (run c) (run d) (run f) (run g)))
"#;
    let core = eggfuse_bake::device_frontend::core("longer-owner", src).unwrap();
    let raw = compiler::compile(core, &BTreeSet::new()).unwrap();
    let p = Program::parse(raw.clone()).unwrap();
    let mut graph = Graph::new_with_cell_ownership(p.clone()).unwrap();
    graph.train_ownership_fragments_with_limit(8).unwrap();
    let mut training = Executor::new(graph, false);
    training.execute().unwrap();
    let profile = training.graph.ownership_fragment_profile().unwrap();
    assert_eq!(profile["max_frames"], 8);
    assert!(profile["records"].as_array().unwrap().iter()
        .any(|r|r["fragment"]["hops"].as_array().unwrap().len() >= 4));
    let mut raw = raw;
    raw["ownership_fragments"] = json!({"schema":"eggfuse-ownership-fragments/v2",
        "source":profile["source"], "max_frames":8,
        "fragments":profile["records"].as_array().unwrap().iter().map(|r|r["fragment"].clone()).collect::<Vec<_>>()});
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    let baked = Program::parse(raw.clone()).unwrap();
    assert_eq!(baked.cell_ownership.composition.max_frames, 8);
    let mut reference = Executor::new(Graph::new_with_repair_ports(p).unwrap(), false);
    let mut actual = Executor::new(Graph::new_with_cell_ownership(baked).unwrap(), false);
    for run in 1..=6 {
        reference.execute_until(Some(run)).unwrap();
        actual.execute_until(Some(run)).unwrap();
        assert_eq!(reference.graph.export().unwrap(), actual.graph.export().unwrap());
        assert_eq!(reference.steps.len(), actual.steps.len());
        for (left, right) in reference.steps.iter().zip(&actual.steps) {
            for key in ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed"] {
                assert_eq!(left[key], right[key], "{key}");
            }
        }
    }
    assert!(actual.graph.ownership_report()["inventory"]["largest_component_frames"].as_u64().unwrap() > 4);
    raw["ownership_fragments"]["max_frames"] = json!(4);
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    assert!(Program::parse(raw.clone()).is_err(), "a lower bound must reject deeper code");
    raw["ownership_fragments"]["fragments"].as_array_mut().unwrap()
        .retain(|f|f["hops"].as_array().unwrap().len() < 4);
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    let prefix_catalog = Program::parse(raw).unwrap();
    let seed_transitions = prefix_catalog.cell_ownership.composition.transitions.len();
    assert!(seed_transitions > 0);
    let mut observed_graph = Graph::new_with_cell_ownership(prefix_catalog.clone()).unwrap();
    observed_graph.trace_ownership_catalog(16).unwrap();
    assert!(observed_graph.continue_ownership_fragment_training(16).is_err());
    let mut observed = Executor::new(observed_graph, false);
    let mut unchanged = Executor::new(Graph::new_with_cell_ownership(prefix_catalog.clone()).unwrap(), false);
    let audit_run = |e: &mut Executor, run| {
        use eggfuse_cell_runtime::transfer_audit as audit;
        audit::take_digests(); audit::take_write_digests(); audit::take_resume_digests();
        audit::set_active(true); audit::enable_write_audit();
        e.execute_until(Some(run)).unwrap();
        audit::set_active(false);
        json!({"rhs":audit::take_digests(),"writes":audit::take_write_digests(),"resumes":audit::take_resume_digests()})
    };
    for run in 1..=6 {
        assert_eq!(audit_run(&mut unchanged, run), audit_run(&mut observed, run));
        assert_eq!(unchanged.graph.export().unwrap(), observed.graph.export().unwrap());
        assert_eq!(unchanged.graph.ownership_report()["inventory"], observed.graph.ownership_report()["inventory"]);
        assert_eq!(serde_json::to_value(unchanged.graph.cells.iter().collect::<Vec<_>>()).unwrap(),
            serde_json::to_value(observed.graph.cells.iter().collect::<Vec<_>>()).unwrap());
    }
    let trace = observed.graph.ownership_catalog_trace().unwrap();
    assert_eq!(trace["executed_max_frames"], 4);
    assert_eq!(trace["seed_transitions"], seed_transitions);
    assert!(!trace["records"].as_array().unwrap().is_empty());
    assert_eq!(observed.graph.ownership_report()["stats"]["composition_shape_builds"], 0);
    assert!(composition::select_profile(&trace).is_err(), "proposals must not masquerade as saved work");
    let mut graph = Graph::new_with_cell_ownership(prefix_catalog).unwrap();
    assert!(graph.train_ownership_fragments().is_err(), "fresh training must stay explicit");
    assert!(graph.continue_ownership_fragment_training(2).is_err());
    graph.continue_ownership_fragment_training(8).unwrap();
    let mut continued = Executor::new(graph, false);
    continued.execute().unwrap();
    assert_eq!(reference.graph.export().unwrap(), continued.graph.export().unwrap());
    let profile = continued.graph.ownership_fragment_profile().unwrap();
    assert_eq!(profile["seed_catalog"]["transitions"], seed_transitions);
    assert!(profile["records"].as_array().unwrap().iter()
        .any(|r|r["fragment"]["hops"].as_array().unwrap().len() >= 4));
    let report = continued.graph.ownership_report();
    assert!(report["stats"]["composition_baked_hits"].as_u64().unwrap() > 0);
    assert!(report["stats"]["composition_shape_builds"].as_u64().unwrap() > 0);
}

#[test]
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
fn completed_component_discharges_parent_without_advancing_run_gc() {
    let src="(datatype E (N i64) (Start E) (Pair E E))
        (ruleset a) (ruleset b)
        (rule ((= x (N n))) ((Start x)) :ruleset a)
        (rule ((= s (Start x))) ((Pair s x)) :ruleset b)
        (N 1) (N 2) (run a 1) (run b 1)";
    let p=program(src);
    let mut reference=Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(),true);
    reference.execute().unwrap();
    for workers in [0,2] {
        let mut e=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),true);
        e.use_completed_parent_takeover().unwrap();
        if workers>0 { e.use_query_workers(workers,1).unwrap(); }
        e.execute().unwrap();
        assert_eq!(reference.graph.export().unwrap(),e.graph.export().unwrap());
        assert_eq!(reference.snapshots,e.snapshots);
        assert!(e.graph.stats.completed_parent_detachments>0,"{}",e.report());
    }
}

#[test]
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
fn completed_layout_distinguishes_dead_inputs_from_scalar_and_result_readers() {
    for body in ["(Pair x x)","(Indexed x i)","(Pair (Get x i) x)"] {
        let src=format!("(datatype E (N i64) (Get E i64) (Pair E E) (Indexed E i64))
            (ruleset init) (ruleset a) (ruleset b)
            (rule ((= x (N n))) ((Get x 7)) :ruleset init)
            (rule ((= g (Get x i))) ({body}) :ruleset a)
            (rule ((= q (Pair x y))) ((Indexed y 9)) :ruleset b)
            (N 1) (N 2) (run init 1) (run a 1) (run b 1)");
        let p=program(&src);
        let mut reference=Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(),true);
        reference.execute().unwrap();
        for workers in [0,2] {
            let mut e=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),true);
            e.use_completed_parent_takeover().unwrap();
            if workers>0 {e.use_query_workers(workers,1).unwrap();}
            e.execute().unwrap();
            assert_eq!(reference.graph.export().unwrap(),e.graph.export().unwrap(),"{body}");
            assert_eq!(reference.snapshots,e.snapshots,"{body}");
            if body=="(Pair x x)" {
                assert!(e.graph.stats.completed_parent_detachments>0,"unused i and g must not retain the full parent");
            }
        }
    }
}

#[test]
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
fn shared_completed_owners_survive_later_reads_and_deletion() {
    for parent_takeover in [false,true] {
    let src="(datatype E (N i64) (Start E) (Pair E E) (Seen E)) (relation Flag ())
        (ruleset a) (ruleset b) (ruleset c) (ruleset d)
        (rule ((= x (N n)) (Flag)) ((Start x)) :ruleset a)
        (rule ((= s (Start x)) (Flag)) ((Pair s x)) :ruleset b)
        (rule ((Pair s x)) ((Seen x)) :ruleset c)
        (rule ((= x (N 1)) (= y (N 2))) ((union x y)) :ruleset d)
        (N 1) (N 2) (Flag) (run a 1) (run b 1) (run c 1) (run d 1) (run c 1)";
    let src=if parent_takeover {src.replace(" (Flag))", ")")} else {src.to_owned()};
    let p=program(&src);
    for workers in [0,2] {
    let mut reference=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
    let mut actual=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
    if parent_takeover {actual.use_completed_parent_takeover().unwrap();}
    if workers>0 {actual.use_query_workers(workers,1).unwrap();}
    let mut moved=0;
    loop {
        let n=reference.steps.len();
        reference.execute_until(Some(n+1)).unwrap();actual.execute_until(Some(n+1)).unwrap();
        if reference.steps.len()==n {break;}
        moved+=actual.graph.transfer_completed_owners().unwrap();
        assert_eq!(reference.graph.export().unwrap(),actual.graph.export().unwrap(),"Run {}",n+1);
        actual.graph.ownership_report();actual.graph.stable_port_report();
    }
    assert!(moved>0,"exercise physical source-frame removal");
    if parent_takeover {
        assert!(actual.graph.stats.completed_parent_detachments>0);
        assert!(actual.graph.stats.shared_owner_inherited_frames>0,"inherited frames must enter shared storage");
    }
    let table=actual.graph.program.tables.iter().position(|t|t.name=="Pair").unwrap();
    let witness=actual.graph.witnesses(table)[0];
    let eggfuse_cell_runtime::graph::Dependency::Fact(parent)=witness else {panic!("constructor fact")};
    assert!(actual.graph.cells.get(&parent.cell).is_none(),"Pair must have physically transferred");
    let template=actual.graph.program.templates.iter().position(|t|
        !t.parent_columns.is_empty() && t.name.contains("Seen")).unwrap();
    let slot=*actual.graph.program.templates[template].parent_columns.keys().next().unwrap();
    let child=actual.graph.linked_frame(template,Default::default(),Some(parent)).unwrap();
    let expected=actual.graph.slot(child,slot).unwrap();
    let storage=actual.graph.ownership_storage_trace();
    let frames=storage["components"].as_array().unwrap().iter()
        .find(|c|c["frames"].as_array().unwrap().iter().any(|id|*id==parent.cell)).unwrap()["frames"].clone();
    let mut deletions=Vec::new();
    for t in 0..actual.graph.program.tables.len() {
        for witness in actual.graph.witnesses(t) {
            if let eggfuse_cell_runtime::graph::Dependency::Fact(f)=witness
                && frames.as_array().unwrap().iter().any(|id|*id==f.cell) {
                deletions.push(actual.graph.row(witness).unwrap().unwrap());
            }
        }
    }
    for row in deletions {
        let key=&row.values[..row.values.len()-1];
        actual.graph.hide(row.table,key,true).unwrap();reference.graph.hide(row.table,key,true).unwrap();
    }
    actual.graph.collect_garbage();reference.graph.collect_garbage();
    assert_eq!(actual.graph.slot(child,slot).unwrap(),expected,"parent projection survives component death");
    assert!(actual.graph.stats.shared_owner_frames_restored>0);
    assert_eq!(reference.graph.export().unwrap(),actual.graph.export().unwrap());
    }
}
}

#[test]
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
fn completed_instance_retires_unused_match_inputs_without_owner_transfer() {
    let p=program("(datatype E (N i64) (Start E) (Pair E E) (Seen E))
        (relation Unused (i64))
        (ruleset a) (ruleset b) (ruleset c)
        (rule ((= x (N n)) (Unused j)) ((Start x)) :ruleset a)
        (rule ((= s (Start x)) (Unused j)) ((Pair s x)) :ruleset b)
        (rule ((Pair s x)) ((Seen x)) :ruleset c)
        (N 1) (N 2) (Unused 17) (run a 1) (run b 1) (run c 1)");
    for workers in [0,2] {
        let mut reference=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
        let mut actual=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
        actual.use_completed_parent_takeover().unwrap();
        if workers>0 {actual.use_query_workers(workers,1).unwrap();}
        loop {
            let n=reference.steps.len();
            reference.execute_until(Some(n+1)).unwrap();actual.execute_until(Some(n+1)).unwrap();
            if reference.steps.len()==n {break;}
            assert_eq!(reference.graph.export().unwrap(),actual.graph.export().unwrap());
        }
        assert!(actual.graph.stats.completed_dead_slots_elided>0,
            "unused match inputs must retire without shared-owner transfer");
    }
}

#[test]
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
fn completed_writer_retires_unused_inputs_before_storage_handoff() {
    let p=program("(datatype E (N i64))
        (function Score (E) i64 :merge (max old new))
        (relation Unused (i64)) (relation Seen (E i64))
        (ruleset a) (ruleset b)
        (rule ((= x (N n)) (Unused j)) ((set (Score x) n)) :ruleset a)
        (rule ((= n (Score x))) ((Seen x n)) :ruleset b)
        (N 1) (N 2) (Unused 17) (run a 1) (run b 1)");
    for workers in [0,2] {
        let mut reference=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
        let mut actual=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
        actual.use_completed_parent_takeover().unwrap();
        if workers>0 {actual.use_query_workers(workers,1).unwrap();}
        reference.execute_until(Some(1)).unwrap();actual.execute_until(Some(1)).unwrap();
        assert_eq!(reference.graph.export().unwrap(),actual.graph.export().unwrap());
        assert!(actual.graph.stats.completed_dead_slots_elided>0);
        let old=reference.graph.retained_cell_storage();let new=actual.graph.retained_cell_storage();
        assert!(new["writer_count"].as_u64().unwrap()>0);
        assert!(new["writer_bytes"].as_u64().unwrap()<old["writer_bytes"].as_u64().unwrap());
        reference.execute_until(None).unwrap();actual.execute_until(None).unwrap();
        assert_eq!(reference.graph.export().unwrap(),actual.graph.export().unwrap());
    }
}

#[test]
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
fn port_domains_replace_birth_hints_across_union_and_deletion() {
    let p=program("(datatype E (N i64) (F E) (G E E))
        (ruleset a) (ruleset b) (ruleset c) (ruleset d)
        (rule ((= x (N n))) ((F x)) :ruleset a)
        (rule ((= x (N 1)) (= y (N 2))) ((union x y)) :ruleset b)
        (rule ((= u (F x))) ((G x u)) :ruleset c)
        (rule ((= u (F x))) ((delete (F x))) :ruleset d)
        (N 1) (N 2) (run a 1) (run b 1) (run c 1)
        (run d 1) (run a 1) (run c 1)");
    for workers in [0,2] {
        let mut reference=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
        let mut actual=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
        actual.graph.use_port_domains_only().unwrap();
        if workers>0 {actual.use_query_workers(workers,1).unwrap();}
        loop {
            let n=reference.steps.len();
            reference.execute_until(Some(n+1)).unwrap();actual.execute_until(Some(n+1)).unwrap();
            assert_eq!(reference.graph.export().unwrap(),actual.graph.export().unwrap());
            let report=actual.graph.stable_port_report();
            assert_eq!(report["birth_indexed_port_keys"],0);
            assert_eq!(report["birth_hints_enabled"],false);
            assert_eq!(actual.graph.ownership_report()["stats"]["domain_legacy_visits"],0);
            if reference.steps.len()==n {break;}
        }
    }
}

#[test]
#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
fn completed_scalar_chain_releases_operands_but_preserves_later_fact_reads() {
    let p=program("(datatype E (N i64) (Out i64) (Seen i64))
        (ruleset a) (ruleset retire) (ruleset b)
        (rule ((= x (N n))) ((let t (+ n 1)) (let v (* t 2)) (Out v)) :ruleset a)
        (rule ((= x (N n))) ((delete (N n))) :ruleset retire)
        (rule ((Out v)) ((Seen v)) :ruleset b)
        (N 3) (N 7) (run a 1) (run retire 1) (run b 1)");
    for workers in [0,2] {
        let mut reference=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
        let mut actual=Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(),false);
        actual.use_completed_parent_takeover().unwrap();
        if workers>0 {actual.use_query_workers(workers,1).unwrap();}
        for run in 1..=3 {
            reference.execute_until(Some(run)).unwrap();actual.execute_until(Some(run)).unwrap();
            assert_eq!(reference.graph.export().unwrap(),actual.graph.export().unwrap(),"Run {run}");
            assert_eq!(reference.steps.len(),actual.steps.len());
        }
        assert!(actual.graph.stats.completed_dead_slots_elided>=2,
            "completed scalar intermediates must not survive as execution scratch");
        assert!(actual.graph.stats.completed_parent_detachments>0,
            "a scalar operand needed only during execution must not pin the parent");
    }
}
