#![cfg(feature = "iterative-bake")]
use eggfuse_cell_runtime::{
    compiler,
    executor::Executor,
    graph::{Graph, repair_cells::Catalog},
    program::Program,
};
use serde_json::{Value as J, json};
use std::collections::BTreeSet;
fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("repair-cells", source).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn compare(p: Program) -> (Executor, Executor) {
    let mut a = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_repair_cells(p).unwrap(), true);
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
    (a, b)
}
const CHAIN: &str = r#"
(datatype E (N i64) (F E E) (G E) (H E) (Seen E))
(ruleset first) (ruleset second) (ruleset read)
(rule ((= a (N 1)) (= b (N 2))) ((union a b)) :ruleset first)
(rule ((= a (N 3)) (= b (N 4))) ((union a b)) :ruleset second)
(rule ((= x (H y))) ((Seen x)) :ruleset read)
(H (G (F (N 1) (N 3)))) (H (G (F (N 2) (N 4))))
(run-schedule (seq (run first) (run read) (run second) (run read)))
(check (= (H (G (F (N 1) (N 3)))) (H (G (F (N 2) (N 4))))))
"#;
#[test]
fn committed_deltas_complete_multiport_chains_across_runs() {
    let p = program(CHAIN);
    let g = p.tables.iter().position(|t| t.name == "G").unwrap();
    let h = p.tables.iter().position(|t| t.name == "H").unwrap();
    let raw = p.repair_cells.artifact(&p);
    assert_eq!(
        raw["tables"][g], raw["tables"][h],
        "same typed port layout must share cells"
    );
    let union = &raw["shapes"][raw["tables"][g].as_u64().unwrap() as usize]["collision"]["ops"][0];
    assert_eq!(union, &json!({"Union":[{"Slot":0},{"Slot":1}]}));
    let (a, b) = compare(p);
    let stats = b.graph.repair_cell_report()["stats"].clone();
    assert!(stats["delta_cells"].as_u64().unwrap() > 0);
    assert!(stats["key_cells"].as_u64().unwrap() > 0);
    assert!(stats["union_requests"].as_u64().unwrap() >= 3);
    assert!(b.graph.fact_decode_calls.get() < a.graph.fact_decode_calls.get());
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, CHAIN).unwrap();
}
#[test]
fn batched_result_and_key_deltas_preserve_merges_visibility_and_retirement() {
    let source = r#"
(datatype E (N i64) (F E) (Pair E E) (Seen E))
(function count (E) i64 :merge (+ old new))
(function chosen (E) E :merge old)
(ruleset change) (ruleset read) (ruleset hide) (ruleset delete) (ruleset insert)
(rule ((= a (N 1)) (= b (N 2)) (= c (N 3))) ((union a b) (union (F b) c) (union b c)) :ruleset change)
(rule ((= f (F a))) ((Seen f)) :ruleset read)
(rule ((= a (N 1))) ((subsume (F a))) :ruleset hide)
(rule ((= a (N 1))) ((delete (F a))) :ruleset delete)
(rule ((= a (N 1))) ((F a)) :ruleset insert)
(F (N 1)) (F (N 2)) (Pair (F (N 1)) (N 1)) (N 3)
(set (count (N 1)) 3) (set (count (N 2)) 7)
(set (chosen (N 1)) (F (N 1))) (set (chosen (N 2)) (N 2))
(run-schedule (seq (run change) (run read) (run hide) (run read) (run delete) (run insert) (run read)))
(check (= (count (N 1)) 10))
"#;
    compare(program(source));
    egglog::EGraph::default()
        .parse_and_run_program(None, source)
        .unwrap();
}
#[test]
fn unsupported_container_keys_and_duplicate_initial_buckets_remain_exact() {
    let source = r#"
(datatype E (N i64)) (sort Es (Set E)) (constructor Bag (Es) E)
(ruleset change)
(rule ((= a (N 1)) (= b (N 2))) ((union (Bag (set-of a)) b) (union a b)) :ruleset change)
(Bag (set-of (N 1))) (Bag (set-of (N 2)))
(run-schedule (run change))
"#;
    let mut p = program(source);
    let bag = p.tables.iter().position(|t| t.name == "Bag").unwrap();
    assert!(p.repair_cells.artifact(&p)["tables"][bag].is_null());
    let mut duplicate = p
        .initial
        .iter()
        .find(|r| r["table"] == "N")
        .unwrap()
        .clone();
    duplicate["values"]
        .as_array_mut()
        .unwrap()
        .last_mut()
        .unwrap()["eq"] = json!("extra-result");
    p.initial.push(duplicate);
    compare(p);
}
#[test]
fn repair_templates_reconstruct_wiring_and_ignore_allocation_ids() {
    let p = program(CHAIN);
    let mut artifact = p.artifact.clone();
    artifact["repair_cells"] = p.repair_cells.artifact(&p);
    // Source recipe and templates stay fixed while imported equality labels and
    // allocation order change. Differential semantics are checked in both runs.
    let mut renamed = p.clone();
    fn rename(v: &mut J) {
        match v {
            J::Array(xs) => xs.iter_mut().for_each(rename),
            J::Object(obj) => {
                if let Some(id) = obj.get_mut("eq") {
                    *id = json!(format!("renamed-{id}"));
                } else {
                    obj.values_mut().for_each(rename);
                }
            }
            _ => (),
        }
    }
    renamed.initial.iter_mut().for_each(rename);
    renamed.initial.reverse();
    assert_eq!(
        p.repair_cells.artifact(&p),
        renamed.repair_cells.artifact(&renamed)
    );
    compare(renamed);
    Program::parse(artifact.clone()).unwrap();
    artifact["repair_cells"]["shapes"][0]["delta"]["inputs"][0] = json!({"Anchor":999});
    assert!(Program::parse(artifact).is_err());
    assert!(Catalog::select(&p, &[p.repair_cells.len()]).is_err());
    let mut empty = p.artifact.clone();
    empty["repair_cells"] = Catalog::select(&p, &[]).unwrap();
    let (_, b) = compare(Program::parse(empty).unwrap());
    assert_eq!(b.graph.repair_cell_report()["enabled"], false);
}
#[test]
fn bake_scores_complete_repair_executions_and_registers_shared_cells() {
    use std::{fs, process::Command};
    let p = program(CHAIN);
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("input.json");
    fs::write(&path, serde_json::to_vec(&p.artifact).unwrap()).unwrap();
    let out = dir.path().join("trial");
    let result = Command::new(env!("CARGO_BIN_EXE_eggfuse-cell-compiler"))
        .args(["bake-repair", "--program"])
        .arg(&path)
        .arg("--output")
        .arg(&out)
        .args(["--trial-limit", "2", "--rounds", "1"])
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let history: J = serde_json::from_slice(&fs::read(out.join("rounds.json")).unwrap()).unwrap();
    for trial in history[0]["trials"].as_array().unwrap() {
        assert_eq!(trial["semantic_audit"], true);
        assert!(
            trial["work"]["counters"]["repair_cells/stats/steps"]["after"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert!(
            trial["work"]["counters"]["fact_decode_calls"]["saved"]
                .as_i64()
                .unwrap()
                >= 0
        );
    }
    let registry: J =
        serde_json::from_slice(&fs::read(out.join("cell-egraph.json")).unwrap()).unwrap();
    assert_eq!(registry["repair_units"], p.repair_cells.len() * 5);
    Program::parse(serde_json::from_slice(&fs::read(out.join("program.json")).unwrap()).unwrap())
        .unwrap();
}
