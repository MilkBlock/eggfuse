use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use serde_json::{Value as J, json};
use std::collections::BTreeSet;
fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("local-union", source).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn compare(p: Program) -> (Executor, Executor) {
    let mut a = Executor::new(Graph::new_with_repair_ports(p.clone()).unwrap(), true);
    let mut b = Executor::new(Graph::new_with_local_unions(p).unwrap(), true);
    a.execute().unwrap();
    b.execute().unwrap();
    assert_eq!(a.initial_audit, b.initial_audit);
    assert_eq!(a.snapshots, b.snapshots);
    assert_eq!(a.binding_audit, b.binding_audit);
    assert_eq!(a.steps.len(), b.steps.len());
    for (x, y) in a.steps.iter().zip(&b.steps) {
        for key in [
            "ordinal",
            "ruleset",
            "path",
            "iterations",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(x[key], y[key], "{key}");
        }
    }
    for e in [&a, &b] {
        e.graph.maintenance_report();
    }
    assert_eq!(b.graph.local_union_report()["untracked_live"], 0);
    (a, b)
}
const CHAIN: &str = r#"
(datatype E (N i64) (F E) (G E) (H E) (Seen E))
(ruleset make) (ruleset read) (ruleset external)
(rule ((= x (N 0)) (= y (N 1)))
 ((let a (F x)) (let b (F y)) (G a) (G b) (H (G a)) (H (G b)) (union x y)) :ruleset make)
(rule ((= x (H y))) ((Seen x)) :ruleset read)
(rule ((= x (N 0)) (= y (N 2))) ((union x y)) :ruleset external)
(N 0) (N 1) (N 2)
(run-schedule (seq (run make) (run read) (run external) (run read)))
(check (= (H (G (F (N 0)))) (H (G (F (N 1))))))
"#;
#[test]
fn internal_union_chain_removes_lifetime_subscriptions() {
    let (a, b) = compare(program(CHAIN));
    let ma = a.graph.maintenance_report();
    let mb = b.graph.maintenance_report();
    let local = b.graph.local_union_report();
    assert!(
        local["stats"]["retired_unsubscribed"].as_u64().unwrap() >= 3,
        "{local}"
    );
    assert!(local["stats"]["congruence_retirements"].as_u64().unwrap() >= 3);
    assert!(local["stats"]["completed_boundaries"].as_u64().unwrap() > 0);
    assert_eq!(local["stats"]["forced_boundaries"], 0);
    assert!(
        mb["stats"]["reverse_edges_created"].as_u64()
            < ma["stats"]["reverse_edges_created"].as_u64()
    );
    assert!(mb["stats"]["union_wake_visits"].as_u64() < ma["stats"]["union_wake_visits"].as_u64());
    egglog::EGraph::default()
        .parse_and_run_program(None, CHAIN)
        .unwrap();
}
#[test]
fn mutable_effects_and_external_unions_restore_live_boundaries() {
    let source = r#"
(datatype E (N i64) (F E) (G E) (Seen E))
(function count (E) i64 :merge (+ old new))
(ruleset make) (ruleset read) (ruleset change) (ruleset erase) (ruleset again)
(rule ((= x (N 0)) (= y (N 1))) ((F x) (F y) (set (count x) 3) (set (count y) 7) (union x y)) :ruleset make)
(rule ((= x (F y))) ((Seen x)) :ruleset read)
(rule ((= x (N 0)) (= y (N 2))) ((union x y)) :ruleset change)
(rule ((= x (N 0))) ((delete (F x))) :ruleset erase)
(rule ((= x (N 0))) ((F x)) :ruleset again)
(N 0) (N 1) (N 2)
(run-schedule (seq (run make) (run read) (run change) (run read) (run erase) (run again) (run read)))
(check (= (count (N 0)) 10))
"#;
    compare(program(source));
    egglog::EGraph::default()
        .parse_and_run_program(None, source)
        .unwrap();
}
#[test]
fn typed_plan_rejects_corruption_and_ignores_runtime_identity_labels() {
    let p = program(CHAIN);
    let plan = p.local_union_cells.artifact(&p);
    assert!(!plan["selected"].as_array().unwrap().is_empty());
    let mut raw = p.artifact.clone();
    raw["local_union_cells"] = plan;
    Program::parse(raw.clone()).unwrap();
    raw["local_union_cells"]["selected"] = json!([999999]);
    assert!(Program::parse(raw).is_err());
    let mut renamed = p;
    fn rename(v: &mut J) {
        match v {
            J::Array(xs) => xs.iter_mut().for_each(rename),
            J::Object(o) => {
                if let Some(eq) = o.get_mut("eq") {
                    *eq = json!(format!("r-{eq}"));
                } else {
                    o.values_mut().for_each(rename);
                }
            }
            _ => (),
        }
    }
    renamed.initial.iter_mut().for_each(rename);
    renamed.initial.reverse();
    compare(renamed);
}

#[test]
fn pending_rows_remain_matchable_and_can_be_deleted_before_completion() {
    use eggfuse_cell_runtime::program::{Arg, Call, Op};
    use std::collections::BTreeMap;
    let p = program(
        r#"
(datatype E (N i64) (F E))
(rule ((= x (N 0)) (= y (N 1))) ((F x) (F y) (union x y)))
(N 0) (N 1) (run 1)
"#,
    );
    let r = p
        .rules
        .iter()
        .find(|r| {
            p.templates[r.template]
                .ops
                .iter()
                .any(|o| matches!(o, Op::Union(..)))
        })
        .unwrap()
        .clone();
    for (delete, skip_union) in [(false, false), (true, false), (false, true)] {
        let run = |local: bool| {
            let mut g = if local {
                Graph::new_with_local_unions(p.clone()).unwrap()
            } else {
                Graph::new_with_repair_ports(p.clone()).unwrap()
            };
            let mut inputs = BTreeMap::new();
            for atom in r.query.iter() {
                if let Call::Table(t) = atom.call {
                    let key = atom.args[..atom.args.len() - 1]
                        .iter()
                        .map(|a| match a {
                            Arg::Literal(v) => v.clone(),
                            _ => panic!("literal test key"),
                        })
                        .collect::<Vec<_>>();
                    let row = g.lookup(t, &key).unwrap().unwrap();
                    let Arg::Slot(s) = atom.args.last().unwrap() else {
                        panic!()
                    };
                    inputs.insert(*s, row.values.last().unwrap().clone());
                }
            }
            let cell = g.frame(r.template, inputs).unwrap();
            let mut born = vec![];
            for (op, ins) in p.templates[r.template].ops.iter().enumerate() {
                match ins {
                    Op::Copy(dst, a) => {
                        let v = g.argument(cell, a).unwrap();
                        g.cells.get_mut(&cell).unwrap().values.insert(*dst, v);
                    }
                    Op::Let(dst, Call::Table(t), args) => {
                        let key = args
                            .iter()
                            .map(|a| g.argument(cell, a).unwrap())
                            .collect::<Vec<_>>();
                        g.construct(cell, op, *t, args, *dst).unwrap();
                        born.push((*t, key));
                    }
                    Op::Union(a, b) => {
                        let (t, key) = &born[0];
                        let rows = g.candidates(*t, &[Some(key[0].clone()), None]);
                        assert!(
                            rows.iter()
                                .any(|&w| g.row(w).unwrap().is_some_and(|r| r.values[0] == key[0]))
                        );
                        if delete {
                            g.hide(*t, key, true).unwrap();
                        }
                        let (a, b) = (g.argument(cell, a).unwrap(), g.argument(cell, b).unwrap());
                        if !skip_union {
                            g.enqueue_union(a, b).unwrap();
                        }
                    }
                    _ => panic!("unexpected test effect"),
                }
            }
            g.repair().unwrap();
            assert_eq!(g.local_union_report()["untracked_live"], 0);
            if local {
                assert!(g.local_union_report()["fallback_queries"].as_u64().unwrap() > 0);
                if skip_union {
                    // An aborted RHS never commits its predicted equality.
                    assert!(
                        g.local_union_report()["stats"]["forced_boundaries"]
                            .as_u64()
                            .unwrap()
                            > 0
                    );
                }
            }
            g.maintenance_report();
            let mut bytes = vec![];
            g.write_export(&mut bytes).unwrap();
            bytes
        };
        assert_eq!(run(false), run(true));
    }
}

#[cfg(feature = "iterative-bake")]
#[test]
fn bake_charges_completion_and_fallback_work_without_rewarding_edge_gauges() {
    use std::{fs, process::Command};
    let p = program(CHAIN);
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("input.json");
    let output = temp.path().join("trial");
    fs::write(&input, serde_json::to_vec(&p.artifact).unwrap()).unwrap();
    let run = Command::new(env!("CARGO_BIN_EXE_eggfuse-cell-compiler"))
        .arg("bake-local-unions")
        .arg("--program")
        .arg(&input)
        .arg("--output")
        .arg(&output)
        .output()
        .unwrap();
    assert!(
        run.status.success(),
        "{}",
        String::from_utf8_lossy(&run.stderr)
    );
    let credit: J = serde_json::from_slice(&fs::read(output.join("credit.json")).unwrap()).unwrap();
    assert_eq!(credit["semantic_audit"], true);
    let counters = &credit["work"]["counters"];
    assert!(
        counters["maintenance/stats/reverse_insert_attempts"]["saved"]
            .as_i64()
            .unwrap()
            > 0
    );
    assert!(
        counters["local_union_cells/stats/completion_visits"]["saved"]
            .as_i64()
            .unwrap()
            < 0
    );
    assert!(
        counters
            .get("maintenance/stats/live_reverse_edges")
            .is_none()
    );
    let final_program = Program::parse(
        serde_json::from_slice(&fs::read(output.join("program.json")).unwrap()).unwrap(),
    )
    .unwrap();
    if credit["accepted"] == false {
        assert_eq!(
            Graph::new_with_local_unions(final_program)
                .unwrap()
                .local_union_report()["enabled"],
            false
        );
    }
    #[cfg(not(feature = "sparse-cells"))]
    {
        let unsupported = temp.path().join("unsupported");
        let run = Command::new(env!("CARGO_BIN_EXE_eggfuse-cell-compiler"))
            .arg("bake-local-unions")
            .arg("--program")
            .arg(&input)
            .arg("--output")
            .arg(&unsupported)
            .args(["--entry-publications", "true"])
            .output()
            .unwrap();
        assert!(!run.status.success());
        assert!(String::from_utf8_lossy(&run.stderr).contains("require the sparse-cells build"));
        assert!(!unsupported.exists());
    }
}
