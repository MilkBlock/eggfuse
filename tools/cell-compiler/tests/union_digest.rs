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
            let id = vs.last().unwrap()["eq"].as_str().unwrap();
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
    ] {
        let result = Graph::new_with_union_digest(program(source), 64);
        assert!(matches!(result, Err(e) if e.contains(reason)));
    }
    let p = program("(datatype E (N i64)) (N 0) (run 1)");
    assert!(Graph::new_with_union_digest(p, 65).is_err());
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
