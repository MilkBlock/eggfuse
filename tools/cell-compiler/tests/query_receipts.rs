#![cfg(feature = "iterative-bake")]
use eggfuse_cell_runtime::{
    compiler,
    executor::Executor,
    graph::Graph,
    iterative::{Catalog, Limits},
    program::{Call, Program},
};
use serde_json::{Value as J, json};
use std::collections::BTreeSet;

fn seed(source: &str) -> (Program, J) {
    let core = eggfuse_bake::device_frontend::core("query-receipts", source).unwrap();
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let rules = p.artifact["recipe"]["rules"].as_array().unwrap();
    let id = |name| {
        rules
            .iter()
            .position(|r| r["metadata"]["name"] == name)
            .unwrap()
    };
    let (producer, consumer) = (id("producer"), id("consumer"));
    let publication = rules[producer]["effects"]
        .as_array()
        .unwrap()
        .iter()
        .position(|e| e["call"]["table"] == "Gateway")
        .unwrap();
    let pivot = p.rules[consumer]
        .query
        .iter()
        .position(|a| matches!(a.call, Call::Table(t) if p.tables[t].name == "Gateway"))
        .unwrap();
    let profile = json!({"schema":"eggfuse-spine-shapes/v1","program_sha256":p.artifact["sha256"],
        "prefixes":[{"edge":[producer,publication,consumer,pivot],"visits":2}]});
    let leaves = compiler::bake_stage_blocks(&p, &profile, &p, 1).unwrap();
    assert_eq!(leaves["entries"].as_array().unwrap().len(), 1);
    let mut raw = p.artifact;
    raw["spine_blocks"] = leaves;
    let p = Program::parse(raw).unwrap();
    let mut plan = Catalog::seed_with_roots(
        &p,
        Limits {
            support: 1,
            ..Default::default()
        },
        &[producer],
    )
    .unwrap();
    plan["joins"] = json!([{"left":1,"output":publication,"right":0}]);
    (p, plan)
}
fn execute(p: Program) -> Executor {
    let mut e = Executor::new(Graph::new(p).unwrap(), true);
    e.execute().unwrap();
    e
}
fn compare(p: &Program, plan: &J) -> Executor {
    let mut raw = p.artifact.clone();
    raw["iterative_bake"] = plan.clone();
    let base = execute(p.clone());
    let fast = execute(Program::parse(raw).unwrap());
    assert_eq!(base.snapshots, fast.snapshots);
    assert_eq!(base.binding_audit, fast.binding_audit);
    assert_eq!(base.steps.len(), fast.steps.len());
    for (x, y) in base.steps.iter().zip(&fast.steps) {
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
    fast
}
const SOURCE: &str = r#"
(datatype E (N i64) (Start E E) (F E) (G E) (H E) (Gateway E) (Out E))
(ruleset make) (ruleset consume) (ruleset replace)
(rule ((Start x y))
 ((let fx (F x)) (let fy (F y)) (let g (G fx)) (H g) (union x y) (Gateway fy))
 :ruleset make :name "producer")
(rule ((Gateway z) (= g (G z)) (= h (H g))) ((Out h)) :ruleset consume :name "consumer")
(rule ((Gateway z) (= g (G z))) ((delete (G z)) (let fresh (G z)) (union fresh g)) :ruleset replace)
(Start (N 1) (N 2)) (Start (N 3) (N 4))
(run-schedule (seq (run make) (run consume)))
"#;

#[test]
fn query_receipts_use_source_congruence_and_completed_prefix_ports() {
    let (p, mut plan) = seed(SOURCE);
    Catalog::emit_query_handoffs(&p, &mut plan).unwrap();
    assert_eq!(plan["rhs_handoffs"]["schema"], "eggfuse-result-switch/v3");
    let terminal = plan["rhs_handoffs"]["states"]
        .as_array()
        .unwrap()
        .last()
        .unwrap();
    assert_eq!(terminal["program"]["queries"].as_array().unwrap().len(), 2);
    let e = compare(&p, &plan);
    assert_eq!(e.report()["stage_spine"]["stats"]["query_receipt_hits"], 4);
    let mut invalid = p.artifact.clone();
    invalid["iterative_bake"] = plan.clone();
    let states = invalid["iterative_bake"]["rhs_handoffs"]["states"]
        .as_array_mut()
        .unwrap();
    states.last_mut().unwrap()["program"]["queries"][0]["atom"] = json!(999);
    assert!(Program::parse(invalid).is_err());
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, SOURCE).unwrap();
}

#[test]
fn retired_query_receipts_fall_back_after_an_intervening_run() {
    let source = SOURCE.replace(
        "(seq (run make) (run consume))",
        "(seq (run make) (run replace) (run consume))",
    );
    let (p, mut plan) = seed(&source);
    Catalog::emit_query_handoffs(&p, &mut plan).unwrap();
    let e = compare(&p, &plan);
    assert!(
        e.report()["stage_spine"]["stats"]["query_receipt_stale"]
            .as_u64()
            .unwrap()
            > 0
    );
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, &source).unwrap();
}

#[test]
fn later_query_constraints_cannot_prove_an_earlier_port() {
    let source = r#"
(datatype E (N i64) (Start E E) (F E) (G E) (Gateway E E) (Out E))
(ruleset make) (ruleset consume)
(rule ((Start a b)) ((let x (F a)) (G x) (Gateway b a)) :ruleset make :name "producer")
(rule ((Gateway z a) (= g (G z)) (= z (F a))) ((Out g)) :ruleset consume :name "consumer")
(Start (N 1) (N 2))
(run-schedule (seq (run make) (run consume)))
"#;
    let (p, mut plan) = seed(source);
    Catalog::emit_query_handoffs(&p, &mut plan).unwrap();
    let consumer = p.artifact["spine_blocks"]["entries"][0]["consumer"]
        .as_u64()
        .unwrap() as usize;
    let g = p.rules[consumer]
        .query
        .iter()
        .position(|a| matches!(a.call, Call::Table(t) if p.tables[t].name == "G"))
        .unwrap();
    for state in plan["rhs_handoffs"]["states"].as_array().unwrap() {
        if let Some(queries) = state["program"]["queries"].as_array() {
            assert!(queries.iter().all(|r| r["atom"] != g));
        }
    }
    compare(&p, &plan);
}

#[test]
fn resume_catalog_reconstructs_old_certificate_before_learning_new_query_work() {
    use std::{fs, process::Command};
    let (p, mut plan) = seed(SOURCE);
    Catalog::emit_congruence_handoffs(&p, &mut plan).unwrap();
    let tmp = tempfile::tempdir().unwrap();
    let program = tmp.path().join("program.json");
    let catalog = tmp.path().join("catalog.json");
    fs::write(&program, serde_json::to_vec(&p.artifact).unwrap()).unwrap();
    fs::write(&catalog, serde_json::to_vec(&plan).unwrap()).unwrap();
    let run = |out: &std::path::Path| {
        Command::new(env!("CARGO_BIN_EXE_eggfuse-cell-compiler"))
            .args(["iterate", "--program"])
            .arg(&program)
            .arg("--resume-catalog")
            .arg(&catalog)
            .arg("--output")
            .arg(out)
            .args(["--rounds", "0", "--objective", "stage-congruence"])
            .output()
            .unwrap()
    };
    let out = tmp.path().join("learned");
    let result = run(&out);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let rounds: J = serde_json::from_slice(&fs::read(out.join("rounds.json")).unwrap()).unwrap();
    assert_eq!(rounds[0]["units"], 3);
    assert_eq!(rounds[0]["query_completion"]["hits"], 4);
    plan["seed"] = json!("wrong-leaf-catalog");
    fs::write(&catalog, serde_json::to_vec(&plan).unwrap()).unwrap();
    let out = tmp.path().join("rejected");
    assert!(!run(&out).status.success());
    assert!(!out.exists());
}

#[test]
fn mutable_query_receipt_reads_current_value_without_proving_old_result_equal() {
    for effect in [false, true] {
        let source = format!(
            r#"
(datatype E (N i64) (Start E) (Gateway E) (F E) (Out E))
(function value (E) E :merge new)
(ruleset make) (ruleset update) (ruleset consume)
{}
(rule ((Gateway x)) ((set (value x) (N 2))) :ruleset update)
(rule ((Gateway x) (= v (value x)) (= f (F v))) ((Out f)) :ruleset consume :name "consumer")
(Start (N 0)) (set (value (N 0)) (N 1)) (F (N 2))
(run-schedule (seq (run make) (run update) (run consume)))
"#,
            if effect {
                r#"(rule ((Start x)) ((set (value x) (N 1)) (F (N 1)) (Gateway x)) :ruleset make :name "producer")"#
            } else {
                r#"(rule ((Start x) (= v (value x))) ((F v) (Gateway x)) :ruleset make :name "producer")"#
            }
        );
        let (p, mut plan) = seed(&source);
        Catalog::emit_query_handoffs(&p, &mut plan).unwrap();
        let consumer = p.artifact["spine_blocks"]["entries"][0]["consumer"]
            .as_u64()
            .unwrap() as usize;
        let f = p.rules[consumer]
            .query
            .iter()
            .position(|a| matches!(a.call, Call::Table(t) if p.tables[t].name == "F"))
            .unwrap();
        let queries = plan["rhs_handoffs"]["states"]
            .as_array()
            .unwrap()
            .last()
            .unwrap()["program"]["queries"]
            .as_array()
            .unwrap();
        assert!(queries.iter().all(|r| r["atom"] != f));
        let e = compare(&p, &plan);
        assert_eq!(
            e.report()["stage_spine"]["stats"]["query_receipt_function_hits"],
            1,
            "effect={effect}"
        );
        let mut native = egglog::EGraph::default();
        native.parse_and_run_program(None, &source).unwrap();
        native
            .parse_and_run_program(None, "(fail (check (Out (F (N 1)))))")
            .unwrap();
        native
            .parse_and_run_program(None, "(check (Out (F (N 2))))")
            .unwrap();
    }
}

#[test]
fn single_write_producer_preserves_mutable_query_receipt() {
    let source = r#"
(datatype E (N i64) (Start E) (Out E))
(function value (E) E :merge new)
(function Gateway (E) E :merge old)
(ruleset make) (ruleset update) (ruleset consume)
(rule ((Start x) (= v (value x))) ((set (Gateway x) v)) :ruleset make :name "producer")
(rule ((= g (Gateway x))) ((set (value x) (N 2))) :ruleset update)
(rule ((= g (Gateway x)) (= v (value x))) ((Out v)) :ruleset consume :name "consumer")
(Start (N 0)) (set (value (N 0)) (N 1))
(run-schedule (seq (run make) (run update) (run consume)))
(check (Out (N 2)))
"#;
    let (p, mut plan) = seed(source);
    Catalog::emit_query_handoffs(&p, &mut plan).unwrap();
    let e = compare(&p, &plan);
    assert!(e.graph.stats.single_writes > 0);
    assert_eq!(
        e.report()["stage_spine"]["stats"]["query_receipt_function_hits"],
        1
    );
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, source).unwrap();
}
