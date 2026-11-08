//! Independent native oracle and differential checks for the opt-in matcher.
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use serde_json::{Value as J, json};
use std::collections::{BTreeMap, BTreeSet};

fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("union-digest-test", source).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}

// Give each class a deterministic name from its first grounded constructor
// layer. These fixtures are reachable from scalar/nullary constructors, even
// after cyclic unions. Reject unresolved or duplicate class names; then compare
// every complete row, so this is an explicit bijection, not a hash/WL heuristic.
fn rows(mut rows: J) -> J {
    let rs = rows.as_array_mut().unwrap();
    let mut names = BTreeMap::<String, String>::new();
    loop {
        let mut ready = BTreeMap::<String, String>::new();
        for row in rs.iter() {
            let vs = row["values"].as_array().unwrap();
            let Some(id) = vs.last().unwrap()["eq"].as_str() else {
                continue;
            };
            if names.contains_key(id) {
                continue;
            }
            let mut key = vec![row["table"].clone()];
            let mut grounded = true;
            for v in &vs[..vs.len() - 1] {
                if let Some(id) = v["eq"].as_str() {
                    if let Some(name) = names.get(id) {
                        key.push(json!(name));
                    } else {
                        grounded = false;
                        break;
                    }
                } else {
                    key.push(v.clone());
                }
            }
            if grounded {
                let candidate = json!(key).to_string();
                ready
                    .entry(id.to_owned())
                    .and_modify(|old| *old = old.clone().min(candidate.clone()))
                    .or_insert(candidate);
            }
        }
        if ready.is_empty() {
            break;
        }
        let mut ordered: Vec<_> = ready.into_iter().map(|(id, key)| (key, id)).collect();
        ordered.sort();
        assert!(
            ordered.windows(2).all(|w| w[0].0 != w[1].0),
            "distinct classes have identical keys"
        );
        for (_, id) in ordered {
            let n = names.len();
            names.insert(id, format!("class-{n}"));
        }
    }
    for row in rs.iter_mut() {
        for v in row["values"].as_array_mut().unwrap() {
            if let Some(id) = v["eq"].as_str() {
                v["eq"] = json!(names.get(id).expect("ungrounded test class"));
            }
        }
    }
    rs.sort_by_cached_key(J::to_string);
    rows
}

fn differential(init: &str, runs: &[&str]) {
    let runs: Vec<_> = runs.iter().map(|r| format!("(run-schedule {r})")).collect();
    let source = format!("{init}\n{}", runs.join("\n"));
    let p = program(&source);
    let mut native = egglog::EGraph::default();
    native.parse_and_run_program(None, init).unwrap();
    let mut expected = vec![rows(native.device_snapshot().unwrap())];
    for run in runs {
        native.parse_and_run_program(None, &run).unwrap();
        expected.push(rows(native.device_snapshot().unwrap()));
    }
    for reverse in [false, true] {
        let mut p = p.clone();
        if reverse {
            // Change allocation order and rename all external equality labels.
            // Thus roots, witness IDs and packet order differ from the oracle.
            p.initial.reverse();
            for row in &mut p.initial {
                for v in row["values"].as_array_mut().unwrap() {
                    if let Some(id) = v["eq"].as_str() {
                        v["eq"] = json!(format!("renamed:{id}"));
                    }
                }
            }
        }
        let mut control = Executor::new(Graph::new(p.clone()).unwrap(), true);
        control.execute().unwrap();
        let reference = std::iter::once(control.initial_audit.as_ref().unwrap())
            .chain(control.snapshots.iter())
            .map(|s| rows(s["rows"].clone()))
            .collect::<Vec<_>>();
        assert_eq!(reference, expected, "ordinary Cell/native mismatch");
        for bits in [0, 64] {
            let mut digest =
                Executor::new(Graph::new_with_union_digest(p.clone(), bits).unwrap(), true);
            digest.execute().unwrap();
            let actual = std::iter::once(digest.initial_audit.as_ref().unwrap())
                .chain(digest.snapshots.iter())
                .map(|s| rows(s["rows"].clone()))
                .collect::<Vec<_>>();
            assert_eq!(
                actual, expected,
                "digest/native mismatch: reversed={reverse}, bits={bits}"
            );
            // Same-input audits additionally check bindings and schedule.
            assert_eq!(digest.binding_audit, control.binding_audit);
            let schedule = |e: &Executor| {
                e.steps
                    .iter()
                    .map(|s| (s.ruleset.clone(), s.changed))
                    .collect::<Vec<_>>()
            };
            assert_eq!(schedule(&digest), schedule(&control));
            assert_eq!(digest.graph.stats.repaired_dependencies, 0);
            assert_eq!(digest.graph.stats.repair_collisions, 0);
        }
    }
}

#[test]
fn cascades_repeated_variables_late_insertion_and_noop_unions() {
    differential(
        r#"
        (datatype E (N i64) (Seed E E) (F E) (Pair E E) (Seen E) (Late E))
        (ruleset make) (ruleset alias) (ruleset read) (ruleset late)
        (rule ((Seed a b)) ((F (F (F a))) (F (F (F b))) (Pair a b) (Pair b a)) :ruleset make)
        (rule ((Seed a b)) ((union a b)) :ruleset alias)
        (rule ((= x (Pair a a))) ((Seen (F (F (F a))))) :ruleset read)
        (rule ((Seen x)) ((Late (Pair x x))) :ruleset late)
        (Seed (N 0) (N 1)) (Seed (N 1) (N 2))
        (Seed (N 7) (N 8)) (Pair (N 0) (N 9))
    "#,
        &[
            "(run make)",
            "(run read)",
            "(run alias)",
            "(run read)",
            "(run late)",
            "(run make)",
            "(run alias)",
            "(run read)",
        ],
    );
}

#[test]
fn cycles_distinct_operators_equal_outputs_and_correlated_keys() {
    differential(
        r#"
        (datatype E (N i64) (F E) (G E) (Pair E E) (Seen E))
        (ruleset cycle) (ruleset alias) (ruleset read)
        (rule ((= a (N 0))) ((union a (F a))) :ruleset cycle)
        (rule ((= a (N 1)) (= b (N 2))) ((union a b)) :ruleset alias)
        (rule ((= x (Pair a a))) ((Seen x)) :ruleset read)
        (F (N 0)) (F (F (N 0))) (G (N 0))
        (union (F (N 1)) (F (N 3)))
        (Pair (N 1) (N 2)) (Pair (N 2) (N 1)) (Pair (N 1) (N 4))
    "#,
        &[
            "(run read)",
            "(run cycle)",
            "(run alias)",
            "(run read)",
            "(run cycle)",
        ],
    );
}

#[test]
fn unsupported_effects_are_rejected() {
    for (source, reason) in [
        (
            "(datatype E (N i64)) (function f (E) E :merge old) (N 0) (run 1)",
            "immutable constructor",
        ),
        (
            "(datatype E (N i64)) (rule ((= a (N i))) ((subsume (N i)))) (N 0) (run 1)",
            "subsumption",
        ),
        (
            "(datatype E (N i64)) (function port (E) Unit :merge old) (function callback (E) Unit :merge (port (N 0))) (N 0) (run 1)",
            "Unit-presence",
        ),
    ] {
        let result = Graph::new_with_union_digest(program(source), 64);
        assert!(matches!(result, Err(e) if e.contains(reason)));
    }
    let p = program("(datatype E (N i64)) (N 0) (run 1)");
    assert!(Graph::new_with_union_digest(p, 65).is_err());
}

#[test]
fn unit_presence_is_correlated_and_wakes_repeated_variable_consumers() {
    differential(
        r#"
        (datatype E (N i64) (Pair E E) (Seen E))
        (function Mark (E E) Unit :merge old)
        (relation Present (E E))
        (ruleset alias) (ruleset read) (ruleset late)
        (rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset alias)
        (rule ((Mark a a) (Present a a)) ((Seen a)) :ruleset read)
        (rule ((Seen a)) ((set (Mark a a) ()) (Present a a)) :ruleset late)
        (set (Mark (N 0) (N 1)) ()) (set (Mark (N 1) (N 0)) ())
        (set (Mark (N 0) (N 2)) ()) (Present (N 0) (N 1)) (Present (N 1) (N 0))
    "#,
        &[
            "(run read)",
            "(run alias)",
            "(run read)",
            "(run late)",
            "(run alias)",
            "(run read)",
        ],
    );
}

#[test]
fn bake_markers_and_compact_unit_ports_survive_union_digests() {
    let temp = tempfile::tempdir().unwrap();
    let source = temp.path().join("ports.egg");
    let out = temp.path().join("compiled");
    let text = include_str!("fixtures/union-digest-ports.egg");
    std::fs::write(&source, text).unwrap();
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_eggfuse-cell-compiler"))
        .args(["compile", "--source"])
        .arg(&source)
        .arg("--output")
        .arg(&out)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let artifact =
        serde_json::from_slice(&std::fs::read(out.join("program.json")).unwrap()).unwrap();
    let p = Program::parse(artifact).unwrap();
    assert!(
        !p.marker_tables.is_empty(),
        "fixture must exercise real selected Bake markers"
    );
    let mut control = Executor::new(Graph::new(p.clone()).unwrap(), true);
    control.execute().unwrap();
    let reference: Vec<_> = control
        .snapshots
        .iter()
        .map(|s| rows(s["rows"].clone()))
        .collect();
    let mut final_rows = J::Null;
    for bits in [0, 64] {
        let mut digest =
            Executor::new(Graph::new_with_union_digest(p.clone(), bits).unwrap(), true);
        digest.execute().unwrap();
        assert_eq!(
            digest
                .snapshots
                .iter()
                .map(|s| rows(s["rows"].clone()))
                .collect::<Vec<_>>(),
            reference
        );
        assert_eq!(digest.binding_audit, control.binding_audit);
        final_rows = rows(digest.graph.export().unwrap()["rows"].clone());
        let report = digest.report();
        assert!(
            report["union_digest"]["stats"]["unit_rows_rekeyed"]
                .as_u64()
                .unwrap()
                > 0
        );
        assert_eq!(digest.graph.stats.repaired_dependencies, 0);
        if cfg!(feature = "view-ports") {
            assert!(report["view_storage"]["compact"].as_u64().unwrap() > 0);
            assert!(
                report["union_digest"]["stats"]["unit_compact_rekeys"]
                    .as_u64()
                    .unwrap()
                    > 0
            );
            assert!(
                report["union_digest"]["stats"]["unit_compact_retired"]
                    .as_u64()
                    .unwrap()
                    > 0
            );
        }
    }
    // Independent oracle also executes the original and compiler-marked source checks.
    for (index, source) in [
        text.to_owned(),
        std::fs::read_to_string(out.join("source_sk_mk.egg")).unwrap(),
    ]
    .into_iter()
    .enumerate()
    {
        let mut native = egglog::EGraph::default();
        native.parse_and_run_program(None, &source).unwrap();
        if index == 1 {
            assert_eq!(rows(native.device_snapshot().unwrap()), final_rows);
        }
    }
}

#[test]
fn shared_entry_keeps_old_packets_and_observes_digest_at_publication() {
    use eggfuse_cell_runtime::entry_schedule::Scheduler;
    use std::rc::Rc;
    let p = program(
        r#"
        (datatype E (N i64) (Pair E E) (Seen E) (Same E))
        (ruleset any) (ruleset equal)
        (rule ((= x (Pair a b))) ((Seen x)) :ruleset any)
        (rule ((= x (Pair a a))) ((Same x)) :ruleset equal)
        (Pair (N 0) (N 1))
        (run-schedule (seq (run any) (run equal)))
    "#,
    );
    let any = p.sets["any"][0];
    let equal = p.sets["equal"][0];
    for bits in [0, 64] {
        let mut scheduler = Scheduler::new(&p, true);
        let mut graph = Graph::new_with_union_digest(p.clone(), bits).unwrap();
        let old = scheduler
            .seeds(&graph, any, 0)
            .unwrap()
            .pop()
            .unwrap()
            .packet
            .row
            .clone();
        let values = old.values.to_vec();
        assert!(Rc::ptr_eq(
            &old.values,
            &graph.row(old.witness).unwrap().unwrap().values
        ));
        assert!(scheduler.seeds(&graph, equal, 0).unwrap().is_empty());
        graph.epoch += 1;
        graph
            .enqueue_union(values[0].clone(), values[1].clone())
            .unwrap();
        graph.repair().unwrap();
        assert_eq!(&*old.values, &values[..]);
        // Both consumers stay on their previous snapshot until normal delivery.
        assert!(
            scheduler
                .seeds(&graph, any, graph.epoch)
                .unwrap()
                .is_empty()
        );
        assert!(
            scheduler
                .seeds(&graph, equal, graph.epoch)
                .unwrap()
                .is_empty()
        );
        scheduler.publish(&graph);
        let new = scheduler
            .seeds(&graph, any, graph.epoch)
            .unwrap()
            .pop()
            .unwrap()
            .packet
            .row
            .clone();
        assert_eq!(new.values[0], new.values[1]);
        assert_eq!(
            scheduler.seeds(&graph, equal, graph.epoch).unwrap().len(),
            1
        );
        assert!(Rc::ptr_eq(
            &new.values,
            &graph.row(new.witness).unwrap().unwrap().values
        ));
        assert!(!Rc::ptr_eq(&new.values, &old.values));
        let report = graph.union_digest_report();
        assert!(report["stats"]["shared_row_copies"].as_u64().unwrap() > 0);
        assert_eq!(report["owned_key_packets"], 0);
        assert_eq!(report["owned_argument_postings"], 0);
        assert_eq!(report["owned_key_buckets"], 0);
    }
}

#[test]
fn retiring_imported_duplicates_preserves_pending_transitive_unions() {
    let mut p = program("(datatype E (N i64) (F E) (G E)) (G (F (N 0))) (run 1)");
    let expected = rows(Graph::new(p.clone()).unwrap().export().unwrap()["rows"].clone());
    // The frontend normally exports canonical input. Inject aliases directly
    // to exercise the digest import queue and its early-retirement obligation.
    let mut duplicate = p
        .initial
        .iter()
        .find(|r| r["table"] == "F")
        .unwrap()
        .clone();
    duplicate["values"][1]["eq"] = json!("duplicate-F-result");
    p.initial.push(duplicate);
    let mut parent = p
        .initial
        .iter()
        .find(|r| r["table"] == "G")
        .unwrap()
        .clone();
    parent["values"][0]["eq"] = json!("duplicate-F-result");
    parent["values"][1]["eq"] = json!("duplicate-G-result");
    p.initial.push(parent);
    for reverse in [false, true] {
        let mut p = p.clone();
        if reverse {
            p.initial.reverse();
        }
        for bits in [0, 64] {
            let graph = Graph::new_with_union_digest(p.clone(), bits).unwrap();
            assert_eq!(rows(graph.export().unwrap()["rows"].clone()), expected);
            assert_eq!(graph.stats.unions, 2);
            assert!(graph.pending_unions.is_empty());
            assert_eq!(
                graph.union_digest_report()["stats"]["duplicate_rows_retired"],
                2
            );
        }
    }
}

#[test]
fn incremental_operations_match_a_full_scan_congruence_oracle() {
    use eggfuse_cell_runtime::value::{Value, canon};
    fn root(parents: &[usize], mut i: usize) -> usize {
        while parents[i] != i {
            i = parents[i];
        }
        i
    }
    fn merge(parents: &mut [usize], a: usize, b: usize) -> bool {
        let (a, b) = (root(parents, a), root(parents, b));
        parents[a.max(b)] = a.min(b);
        a != b
    }
    let p = program("(datatype E (N i64) (F E) (G E) (Pair E E)) (run 1)");
    let table = |name: &str| p.tables.iter().position(|t| t.name == name).unwrap();
    for seed in 1..=6u64 {
        let mut random = seed;
        let mut next = || {
            random = random.wrapping_mul(6364136223846793005).wrapping_add(1);
            (random >> 32) as usize
        };
        let mut graphs = [
            Graph::new(p.clone()).unwrap(),
            Graph::new_with_union_digest(p.clone(), 64).unwrap(),
            Graph::new_with_union_digest(p.clone(), 0).unwrap(),
        ];
        let mut handles = [vec![], vec![], vec![]];
        let mut parents = vec![];
        let mut facts = vec![];
        for step in 0..128 {
            if step < 8 || next() % 4 != 0 {
                let (t, key) = if step < 8 {
                    (table("N"), vec![Value::Int(step)])
                } else {
                    let t = [table("F"), table("G"), table("Pair")][next() % 3];
                    let key = (0..p.tables[t].schema.len() - 1)
                        .map(|_| Value::Eq((next() % parents.len()) as u64))
                        .collect::<Vec<_>>();
                    (t, key)
                };
                for (graph, hs) in graphs.iter_mut().zip(&mut handles) {
                    let args = key
                        .iter()
                        .map(|v| match v {
                            Value::Eq(i) => canon(&hs[*i as usize], &graph.parents),
                            _ => v.clone(),
                        })
                        .collect();
                    hs.push(graph.dynamic_construct(t, args).unwrap());
                }
                facts.push((t, key, parents.len()));
                parents.push(parents.len());
            } else {
                let (a, b) = (next() % parents.len(), next() % parents.len());
                merge(&mut parents, a, b);
                for (graph, hs) in graphs.iter_mut().zip(&handles) {
                    graph.enqueue_union(hs[a].clone(), hs[b].clone()).unwrap();
                }
            }
            // Independent exhaustive fixed point; no subscriptions or digests.
            loop {
                let mut keys = BTreeMap::new();
                let mut changed = false;
                for (t, key, result) in &facts {
                    let key: Vec<_> = key
                        .iter()
                        .map(|v| match v {
                            Value::Eq(i) => Value::Eq(root(&parents, *i as usize) as u64),
                            _ => v.clone(),
                        })
                        .collect();
                    if let Some(other) = keys.insert((*t, key), *result) {
                        changed |= merge(&mut parents, other, *result);
                    }
                }
                if !changed {
                    break;
                }
            }
            for (graph, hs) in graphs.iter_mut().zip(&handles) {
                graph.repair().unwrap();
                for a in 0..parents.len() {
                    for b in 0..a {
                        assert_eq!(
                            root(&parents, a) == root(&parents, b),
                            canon(&hs[a], &graph.parents) == canon(&hs[b], &graph.parents),
                            "seed {seed}, step {step}, pair {a},{b}"
                        );
                    }
                }
                let live: BTreeSet<_> = facts
                    .iter()
                    .map(|(t, key, _)| {
                        (
                            *t,
                            key.iter()
                                .map(|v| match v {
                                    Value::Eq(i) => Value::Eq(root(&parents, *i as usize) as u64),
                                    _ => v.clone(),
                                })
                                .collect::<Vec<_>>(),
                        )
                    })
                    .collect();
                assert_eq!(
                    graph.export().unwrap()["rows"].as_array().unwrap().len(),
                    live.len()
                );
            }
        }
    }
}
