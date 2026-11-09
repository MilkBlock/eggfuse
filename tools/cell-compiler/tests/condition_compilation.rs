use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program, value::Value};

fn source(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("condition-compilation", src).unwrap();
    Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap()
}

#[test]
fn bound_column_routes_exclude_wrong_columns_and_preserve_aliased_matches() {
    let p = source(r#"
(datatype E (N i64) (Pair E E) (Wrap E))
(ruleset build) (ruleset merge)
(rule ((= a (N 0)) (= b (N 1)))
      ((Wrap (Pair a b)) (Wrap (Pair b a))) :ruleset build)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset merge)
(N 0) (N 1)
(run-schedule (seq (run build) (run merge)))
"#);
    let pair = p.tables.iter().position(|t| t.name == "Pair").unwrap();
    let n = p.tables.iter().position(|t| t.name == "N").unwrap();
    for ports in [false, true] {
        let graph = if ports { Graph::new_with_local_congruence(p.clone()) }
            else { Graph::new_with_cell_ownership(p.clone()) }.unwrap();
        let mut e = Executor::new(graph, true);
        e.execute_until(Some(1)).unwrap();
        let a = e.graph.lookup(n, &[Value::Int(0)]).unwrap().unwrap().values[1].clone();
        for column in 0..2 {
            let mut bound = vec![None; 3];
            bound[column] = Some(a.clone());
            let candidates = e.graph.candidates(pair, &bound);
            assert_eq!(candidates.len(), 1, "other input column is not a candidate");
            assert_eq!(e.graph.row(candidates[0]).unwrap().unwrap().values[column], a);
        }
        e.execute().unwrap();
        let candidates = e.graph.candidates(pair, &[Some(a.clone()), None, None]);
        assert_eq!(candidates.len(), 1);
        assert_eq!(e.graph.row(candidates[0]).unwrap().unwrap().values[0], a);
        let stats = e.graph.ownership_report();
        if ports {
            assert!(stats["stats"]["domain_route_probes"].as_u64().unwrap() > 0);
            assert_eq!(stats["stats"]["domain_column_checks"], 0);
        }
    }
}

#[test]
fn typed_conditions_elide_impossible_operators_and_repeated_equalities() {
    let p = source(r#"
(datatype E (N i64) (F E E E) (G E E E))
(ruleset build) (ruleset merge)
(rule ((= a (N 0)) (= b (N 1)) (= c (N 2)))
      ((F a a c) (F b b c) (G a a c) (G b b c)) :ruleset build)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset merge)
(N 0) (N 1) (N 2)
(run-schedule (seq (run build) (run merge)))
"#);
    let f = p.tables.iter().position(|t| t.name == "F").unwrap();
    let g = p.tables.iter().position(|t| t.name == "G").unwrap();
    let mut reference = Executor::new(Graph::new_with_port_keys(p.clone()).unwrap(), true);
    let mut actual = Executor::new(Graph::new_with_local_congruence(p).unwrap(), true);
    reference.execute().unwrap();
    actual.execute().unwrap();
    assert_eq!(reference.snapshots, actual.snapshots);
    assert_eq!(reference.binding_audit, actual.binding_audit);
    assert_eq!(reference.graph.export().unwrap(), actual.graph.export().unwrap());
    assert_eq!(actual.graph.witness_count(f), 1);
    assert_eq!(actual.graph.witness_count(g), 1);
    let report = actual.graph.stable_port_report()["local_conditions"].clone();
    for field in ["operator_pairs_elided", "reflexive_inputs_elided", "duplicate_inputs_elided"] {
        assert!(report[field].as_u64().unwrap() > 0, "{field}: {report}");
    }
    assert_eq!(report["stats"]["shared_symbol_guards"], 0);

    // Generic constructor templates intentionally share a layout. Neither
    // operator may be inferred from that layout's program ID.
    let p = &actual.graph.program;
    let markers = &p.cell_ownership.markers;
    let fm = &markers[p.table_templates[f]];
    let gm = &markers[p.table_templates[g]];
    assert_eq!(fm.program_id, gm.program_id);
    let operators = eggfuse_cell_runtime::graph::cell_ownership::composition::conditions::operators(
        &p.templates, markers, &p.cell_ownership.programs);
    assert!(operators[fm.program_id][0].contains(&f));
    assert!(operators[fm.program_id][0].contains(&g));
}

#[test]
fn concrete_marker_filters_operators_even_when_port_layouts_are_shared() {
    let p = source(r#"
(datatype E (N i64) (F E) (G E))
(F (N 0)) (G (N 0)) (F (N 1)) (G (N 1))
(run-schedule (run))
"#);
    let n = p.tables.iter().position(|t| t.name == "N").unwrap();
    let f = p.tables.iter().position(|t| t.name == "F").unwrap();
    let g = p.tables.iter().position(|t| t.name == "G").unwrap();
    let mut graph = Graph::new_with_local_congruence(p).unwrap();
    assert_eq!(graph.program.cell_ownership.markers[graph.program.table_templates[f]].program_id,
        graph.program.cell_ownership.markers[graph.program.table_templates[g]].program_id);
    let a = graph.lookup(n, &[Value::Int(0)]).unwrap().unwrap().values[1].clone();
    for table in [f, g] {
        let rows = graph.candidates(table, &[Some(a.clone()), None]);
        assert_eq!(rows.len(), 1);
        assert_eq!(graph.row(rows[0]).unwrap().unwrap().table, table);
    }
    graph.hide(f, &[a.clone()], true).unwrap();
    assert!(graph.candidates(f, &[Some(a.clone()), None]).is_empty());
    assert_eq!(graph.candidates(g, &[Some(a.clone()), None]).len(), 1);
    graph.dynamic_construct(f, vec![a.clone()]).unwrap();
    assert_eq!(graph.candidates(f, &[Some(a), None]).len(), 1);
    let report = graph.ownership_report();
    assert!(report["stats"]["domain_type_rejections"].as_u64().unwrap() > 0);
    assert_eq!(report["stats"]["domain_legacy_fact_probes"], 0);
}
