use eggfuse_cell_runtime::{
    checksum::artifact_digest, compiler, executor::Executor, graph::Graph, program::Program,
    value::Value,
};
use serde_json::{Value as J, json};

fn parse(mut raw: J) -> Result<Program, String> {
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    Program::parse(raw)
}
fn source(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("query-classes", src).unwrap();
    Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap()
}
fn fragments(p: &Program) -> Program {
    let mut g = Graph::new_with_cell_ownership(p.clone()).unwrap();
    g.train_ownership_fragments().unwrap();
    let mut e = Executor::new(g, false);
    e.execute().unwrap();
    let profile = e.graph.ownership_fragment_profile().unwrap();
    let mut raw = p.artifact.clone();
    raw["ownership_fragments"] = json!({"schema":"eggfuse-ownership-fragments/v2",
        "source":profile["source"], "fragments":profile["records"].as_array().unwrap()
            .iter().map(|r|r["fragment"].clone()).collect::<Vec<_>>()});
    parse(raw).unwrap()
}
fn classified(mut p: Program) -> Program {
    let classes = p.bake_query_classes().unwrap();
    let mut raw = p.artifact.clone();
    if raw.get("ownership_fragments").is_none() {
        raw["ownership_fragments"] = json!({"schema":"eggfuse-ownership-fragments/v2",
            "source":eggfuse_cell_runtime::graph::cell_ownership::composition::source_digest(&raw),
            "fragments":[]});
    }
    raw["ownership_fragments"]["query_classes"] = classes;
    parse(raw).unwrap()
}

const STAGES: &str = r#"
(datatype E (N i64) (F E) (G E) (H E) (Pair E E))
(ruleset a) (ruleset b) (ruleset c) (ruleset merge)
(rule ((= x (N n))) ((F x)) :ruleset a)
(rule ((= f (F x))) ((G x) (Pair x x)) :ruleset b)
(rule ((= g (G x))) ((F x) (H x)) :ruleset c)
(rule ((= left (N 0)) (= right (N 1))) ((union left right)) :ruleset merge)
(N 0) (N 1) (G (N 2))
(run-schedule (seq (run a) (run merge) (run b) (run c) (run b)))
"#;

#[test]
fn future_uses_survive_equalities_late_activation_and_retirement() {
    let p = fragments(&source(STAGES));
    let c = classified(p.clone());
    let mut expected = Executor::new(Graph::new_with_local_congruence(p).unwrap(), true);
    let mut actual = Executor::new(Graph::new_with_local_congruence(c).unwrap(), true);
    for stage in 1..=5 {
        expected.execute_until(Some(stage)).unwrap();
        actual.execute_until(Some(stage)).unwrap();
        assert_eq!(
            expected.graph.export().unwrap(),
            actual.graph.export().unwrap()
        );
        assert_eq!(expected.snapshots, actual.snapshots);
        assert_eq!(expected.binding_audit, actual.binding_audit);
        // Compare true matches, not the deliberately over-approximated domain.
        for table in 0..actual.graph.program.tables.len() {
            for witness in actual.graph.witnesses(table) {
                let row = actual.graph.row(witness).unwrap().unwrap();
                for (column, value) in row.values.iter().enumerate() {
                    if !matches!(value, Value::Eq(_)) {
                        continue;
                    }
                    let mut bound = vec![None; row.values.len()];
                    bound[column] = Some(value.clone());
                    let matches = |g: &Graph| {
                        g.candidates(table, &bound)
                            .into_iter()
                            .filter(|&d| {
                                g.row(d)
                                    .unwrap()
                                    .is_some_and(|r| r.values[column] == *value)
                            })
                            .collect::<Vec<_>>()
                    };
                    assert_eq!(matches(&expected.graph), matches(&actual.graph));
                }
            }
        }
    }
    let g = &mut actual.graph;
    let n = g.program.tables.iter().position(|t| t.name == "N").unwrap();
    let f = g.program.tables.iter().position(|t| t.name == "F").unwrap();
    let h = g.program.tables.iter().position(|t| t.name == "H").unwrap();
    let a = g.lookup(n, &[Value::Int(0)]).unwrap().unwrap().values[1].clone();
    // Producer retirement leaves the later frame and original symbol alive.
    g.hide(f, &[a.clone()], true).unwrap();
    assert!(g.lookup(h, &[a.clone()]).unwrap().is_some());
    g.dynamic_construct(f, vec![a.clone()]).unwrap();
    assert!(g.lookup(f, &[a]).unwrap().is_some());
    let report = g.ownership_report();
    assert!(
        report["stats"]["composition_cross_stage_joins"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert!(report["stats"]["query_class_probes"].as_u64().unwrap() > 0);
}

#[test]
fn certificate_rejects_missing_current_or_future_uses_even_with_valid_checksum() {
    let plain = source(STAGES);
    let baked = fragments(&plain);
    let mut current = classified(baked.clone()).artifact;
    let masks = current["ownership_fragments"]["query_classes"]["masks"]
        .as_array_mut()
        .unwrap();
    for mask in masks.iter_mut().skip(1) {
        for word in mask.as_array_mut().unwrap() {
            *word = 0.into();
        }
    }
    assert!(
        parse(current)
            .unwrap_err()
            .contains("current body operator")
    );

    // A no-continuation proof covers all bodies but cannot certify this new
    // continuation graph. Source digests deliberately exclude fragments.
    let mut local = plain.clone();
    let proof = local.bake_query_classes().unwrap();
    let mut future = baked.artifact;
    future["ownership_fragments"]["query_classes"] = proof;
    assert!(parse(future).unwrap_err().contains("future Entry use"));
}

#[test]
fn training_and_unbaked_continuations_use_complete_fallback() {
    let plain = source(STAGES);
    for training in [false, true] {
        let mut a = Graph::new_with_local_congruence(plain.clone()).unwrap();
        let mut b = Graph::new_with_local_congruence(classified(plain.clone())).unwrap();
        if training {
            a.train_ownership_fragments().unwrap();
            b.train_ownership_fragments().unwrap();
        }
        let mut a = Executor::new(a, true);
        let mut b = Executor::new(b, true);
        a.execute().unwrap();
        b.execute().unwrap();
        assert_eq!(a.graph.export().unwrap(), b.graph.export().unwrap());
        assert_eq!(a.snapshots, b.snapshots);
        assert_eq!(a.binding_audit, b.binding_audit);
        let report = b.graph.ownership_report();
        if training {
            assert_eq!(report["stats"]["query_class_probes"], 0);
        } else {
            assert_eq!(report["stats"]["composition_cross_stage_joins"], 0);
            assert!(report["stats"]["boundary_live"].as_u64().unwrap() > 0);
        }
    }
}

#[test]
fn different_operators_of_one_layout_do_not_share_runtime_class() {
    let p = classified(source(
        r#"
(datatype E (N i64) (F E) (G E))
(F (N 0)) (G (N 0)) (F (N 1)) (G (N 1))
(run-schedule (run))
"#,
    ));
    let n = p.tables.iter().position(|t| t.name == "N").unwrap();
    let f = p.tables.iter().position(|t| t.name == "F").unwrap();
    let g = p.tables.iter().position(|t| t.name == "G").unwrap();
    let mut graph = Graph::new_with_local_congruence(p).unwrap();
    let a = graph.lookup(n, &[Value::Int(0)]).unwrap().unwrap().values[1].clone();
    assert_eq!(graph.candidates(f, &[Some(a.clone()), None]).len(), 1);
    assert_eq!(graph.candidates(g, &[Some(a.clone()), None]).len(), 1);
    graph.hide(f, &[a.clone()], true).unwrap();
    graph.hide(g, &[a.clone()], true).unwrap();
    assert!(graph.candidates(f, &[Some(a.clone()), None]).is_empty());
    graph.dynamic_construct(f, vec![a.clone()]).unwrap();
    assert_eq!(graph.candidates(f, &[Some(a), None]).len(), 1);
    graph.ownership_report(); // validates lifetime counts and retained boundaries
}

#[test]
fn grouping_never_proves_a_multi_input_equality() {
    let p = fragments(&source(
        r#"
(datatype E (N i64) (Pair E E) (F E))
(ruleset build) (ruleset first) (ruleset second)
(rule ((= x (N 0)) (= y (N 1)) (= z (N 2)) (= w (N 3)))
      ((F (Pair x z)) (F (Pair y w))) :ruleset build)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset first)
(rule ((= z (N 2)) (= w (N 3))) ((union z w)) :ruleset second)
(N 0) (N 1) (N 2) (N 3)
(run-schedule (seq (run build) (run first) (run second)))
"#,
    ));
    let pair = p.tables.iter().position(|t| t.name == "Pair").unwrap();
    let mut reference = Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), true);
    let mut actual = Executor::new(
        Graph::new_with_local_congruence(classified(p)).unwrap(),
        true,
    );
    for stage in 1..=3 {
        reference.execute_until(Some(stage)).unwrap();
        actual.execute_until(Some(stage)).unwrap();
        assert_eq!(reference.snapshots, actual.snapshots);
        assert_eq!(reference.binding_audit, actual.binding_audit);
        assert_eq!(
            actual.graph.witness_count(pair),
            if stage == 3 { 1 } else { 2 }
        );
    }
}
