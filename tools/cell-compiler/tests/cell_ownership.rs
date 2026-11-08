use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use serde_json::json;
use std::collections::BTreeSet;
fn program(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("ownership", src).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn compare(src: &str) -> Executor {
    let p = program(src);
    let mut a = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_cell_ownership(p).unwrap(), true);
    a.execute().unwrap();
    b.execute().unwrap();
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
#[test]
fn live_bodies_cross_stages_without_internal_subscriptions() {
    let e = compare(STAGES);
    let r = e.graph.ownership_report();
    let s = &r["stats"];
    assert!(s["owned_live"].as_u64().unwrap() > 0, "{r}");
    assert!(s["cross_stage_continuations"].as_u64().unwrap() > 0, "{r}");
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
fn bounded_owner_splits_preserve_native_routes_and_candidate_completeness() {
    let mut src = String::from(
        "(datatype E (N i64) (F E) (G E))\n(ruleset make) (ruleset merge)\n(rule ((= x (N 0))) (",
    );
    for i in 0..270 {
        src.push_str(&format!("(G (F (N {i}))) "));
    }
    src.push_str(" ) :ruleset make)\n(rule ((= x (N 0)) (= y (N 269))) ((union x y)) :ruleset merge)\n(N 0)\n(run-schedule (seq (run make) (run merge)))");
    let e = compare(&src);
    let r = e.graph.ownership_report();
    assert!(r["stats"]["capacity_splits"].as_u64().unwrap() > 0);
    assert!(r["inventory"]["largest_owner"].as_u64().unwrap() <= 256);
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
            .any(|m| m.active && m.unions.is_empty())
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
    raw["ownership_markers"]["plan"]["max_continuation_facts"] = json!(1);
    assert!(Program::parse(raw).is_err());
}
