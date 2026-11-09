use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use std::collections::BTreeSet;

fn compare(source: &str) -> (Executor, Executor) {
    let core = eggfuse_bake::device_frontend::core("local-witness", source).unwrap();
    let p = Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap();
    let mut baseline = p.clone();
    baseline.multi_stage.routes.clear();
    let run = |p| {
        let mut e = Executor::new(Graph::new(p).unwrap(), true);
        e.execute().unwrap();
        e
    };
    let old = run(baseline);
    let new = run(p);
    assert_eq!(old.snapshots, new.snapshots);
    assert_eq!(old.binding_audit, new.binding_audit);
    assert_eq!(old.steps.len(), new.steps.len());
    for (a, b) in old.steps.iter().zip(&new.steps) {
        for k in ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed"] {
            assert_eq!(a[k], b[k], "{k}");
        }
    }
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, source).unwrap();
    (old, new)
}

const SOURCE: &str = r#"
(datatype E (N i64) (Start E) (F E) (G E) (Gateway E) (Out E))
(ruleset make) (ruleset consume) (ruleset replace) (ruleset hide)
(rule ((Start x)) ((let f (F x)) (G f) (Gateway x)) :ruleset make)
(rule ((Gateway x) (= f (F x)) (= g (G f))) ((Out g)) :ruleset consume)
(rule ((Start x)) ((delete (F x)) (let f (F x)) (G f)) :ruleset replace)
(rule ((Start x)) ((subsume (F x))) :ruleset hide)
(Start (N 1)) (Start (N 2))
(run-schedule (seq (run make) (run consume)))
"#;

#[test]
fn live_effect_witnesses_discharge_complete_spine_lookups() {
    let (old, new) = compare(SOURCE);
    let a = old.report();
    let b = new.report();
    let a = &a["stage_spine"]["stats"];
    let b = &b["stage_spine"]["stats"];
    assert!(b["local_witness_hits"].as_u64().unwrap() > 0, "{b}");
    assert!(b["port_refreshes"].as_u64().unwrap() < a["port_refreshes"].as_u64().unwrap());
}

#[test]
fn retired_donors_fall_back_to_recreated_rows() {
    let (_, new) = compare(&SOURCE.replace("(run make) (run consume)", "(run make) (run replace) (run consume)"));
    assert!(new.report()["stage_spine"]["stats"]["local_witness_stale"].as_u64().unwrap() > 0);
}

#[test]
fn hidden_donors_cannot_supply_a_match() {
    compare(&SOURCE.replace("(run make) (run consume)", "(run make) (run hide) (run consume)"));
}

#[test]
fn scalar_keys_and_later_equalities_are_checked() {
    compare(r#"
(datatype E (N i64) (Start E E) (F E i64) (Gateway E E) (Out E))
(ruleset make) (ruleset consume) (ruleset merge)
(rule ((Start x y)) ((F x 1) (F x 2) (Gateway x y)) :ruleset make)
(rule ((Gateway x y) (= a (F x 2)) (= b (F y 1)) (= a b)) ((Out a)) :ruleset consume)
(rule ((Start x y)) ((union x y)) :ruleset merge)
(Start (N 1) (N 2))
(run-schedule (seq (run make) (run consume) (run merge) (run consume)))
"#);
}
