use eggfuse_cell_runtime::{
    compiler, completion_plan::Plan, graph::Graph, program::Program, value::Value,
};
use std::collections::BTreeSet;

fn program(src: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("scoped-completion", src).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn table(p: &Program, name: &str) -> usize {
    p.tables.iter().position(|t| t.name == name).unwrap()
}
fn value(g: &Graph, table: usize, key: &[Value]) -> Value {
    g.lookup(table, key)
        .unwrap()
        .unwrap()
        .values
        .last()
        .unwrap()
        .clone()
}
const INDEPENDENT: &str = r#"
(datatype A (Na i64) (Fa A) (Ga A))
(datatype B (Nb i64) (Fb B) (Gb B))
(Ga (Fa (Na 0))) (Ga (Fa (Na 1)))
(Gb (Fb (Nb 0))) (Gb (Fb (Nb 1)))
(run-schedule (run))
"#;
fn merge_inputs(g: &mut Graph) {
    g.epoch = 1;
    for name in ["Na", "Nb"] {
        let t = table(&g.program, name);
        g.enqueue_union(value(g, t, &[Value::Int(0)]), value(g, t, &[Value::Int(1)]))
            .unwrap();
    }
}

#[test]
fn scoped_wait_leaves_unrelated_chain_pending_and_preserves_origin_epoch() {
    let p = program(INDEPENDENT);
    let ga = table(&p, "Ga");
    let gb = table(&p, "Gb");
    let fa = table(&p, "Fa");
    let fb = table(&p, "Fb");
    let mut reference = Graph::new_with_local_congruence(p.clone()).unwrap();
    let mut scoped = Graph::new_with_scoped_completion(p).unwrap();
    merge_inputs(&mut reference);
    merge_inputs(&mut scoped);
    reference.repair().unwrap();
    scoped.commit_scoped_unions().unwrap();
    let a = scoped.completion_scope(&[ga]).unwrap();
    let b = scoped.completion_scope(&[gb]).unwrap();
    assert!(!scoped.scope_ready(&a).unwrap());
    assert!(!scoped.scope_ready(&b).unwrap());
    scoped.complete_scope(&b).unwrap();
    assert!(scoped.scope_ready(&b).unwrap());
    assert!(!scoped.scope_ready(&a).unwrap());
    assert_eq!(scoped.witness_count(fb), 1);
    assert_eq!(scoped.witness_count(gb), 1);
    assert_eq!(scoped.witness_count(fa), 2);
    assert_eq!(scoped.witness_count(ga), 2);
    assert!(scoped.pending_completion_tasks() > 0);
    // An independent source epoch can advance while A's facts retain their
    // originating equality epoch. Completing A must not stamp it as new work.
    scoped.epoch = 9;
    scoped.complete_scope(&a).unwrap();
    assert_eq!(scoped.epoch, 9);
    for w in scoped.witnesses(ga) {
        assert_eq!(scoped.row(w).unwrap().unwrap().epoch, 1);
    }
    assert_eq!(scoped.pending_completion_tasks(), 0);
    scoped.epoch = reference.epoch;
    scoped.collect_garbage();
    reference.collect_garbage();
    assert_eq!(scoped.export().unwrap(), reference.export().unwrap());
    assert!(
        scoped.scoped_completion_report()["stats"]["bypassed_tasks"]
            .as_u64()
            .unwrap()
            > 0
    );
}

#[test]
fn typed_reachability_includes_multi_sort_congruence_cascades() {
    let p = program(
        r#"
(datatype A (Na i64) (Fa A))
(datatype B (Wrap A))
(datatype C (Finish B))
(datatype D (Separate i64))
(ruleset read)
(rule ((= x (Finish y))) ((Finish y)) :ruleset read)
(Finish (Wrap (Fa (Na 0)))) (Finish (Wrap (Fa (Na 1))))
(Separate 0)
(run-schedule (run read))
"#,
    );
    let plan = Plan::derive(&p).unwrap();
    let f = table(&p, "Fa");
    let end = table(&p, "Finish");
    let separate = table(&p, "Separate");
    assert!(plan.affects(f, end));
    assert!(!plan.affects(f, separate));
    assert!(plan.deferrable[f]);
    let mut g = Graph::new_with_scoped_completion(p).unwrap();
    let n = table(&g.program, "Na");
    g.epoch = 1;
    g.enqueue_union(
        value(&g, n, &[Value::Int(0)]),
        value(&g, n, &[Value::Int(1)]),
    )
    .unwrap();
    g.commit_scoped_unions().unwrap();
    let scope = g.completion_scope(&[end]).unwrap();
    assert!(!g.scope_ready(&scope).unwrap());
    g.complete_scope(&scope).unwrap();
    assert_eq!(g.witness_count(end), 1);
    assert!(g.scope_ready(&scope).unwrap());
}

#[test]
fn mutable_merge_effects_and_foreign_scopes_cannot_bypass_completion() {
    let p = program(
        r#"
(datatype A (Na i64) (Fa A))
(function score (A) i64 :merge (min old new))
(Fa (Na 0)) (Fa (Na 1))
(set (score (Fa (Na 0))) 10)
(set (score (Fa (Na 1))) 20)
(run-schedule (run))
"#,
    );
    let f = table(&p, "Fa");
    let s = table(&p, "score");
    let plan = Plan::derive(&p).unwrap();
    assert!(plan.affects(f, s));
    assert!(!plan.deferrable[f]);
    let mut g = Graph::new_with_scoped_completion(p).unwrap();
    let n = table(&g.program, "Na");
    g.epoch = 1;
    g.enqueue_union(
        value(&g, n, &[Value::Int(0)]),
        value(&g, n, &[Value::Int(1)]),
    )
    .unwrap();
    let scope = g.completion_scope(&[s]).unwrap();
    assert!(!g.scope_ready(&scope).unwrap());
    g.complete_scope(&scope).unwrap();
    assert_eq!(g.witness_count(s), 1);
    let foreign = Graph::new_with_scoped_completion(program(INDEPENDENT))
        .unwrap()
        .completion_scope(&[0])
        .unwrap();
    assert!(g.complete_scope(&foreign).is_err());
}

#[test]
fn opaque_merge_requires_full_completion_only_when_pending() {
    let p = program(
        r#"
(datatype A (Na i64) (Fa A))
(datatype B (Nb i64))
(function port (B) i64 :merge old)
(function callback (B) i64 :merge (port (Nb 0)))
(Fa (Na 0)) (Fa (Na 1)) (Nb 0) (Nb 1)
(set (port (Nb 0)) 7)
(set (callback (Nb 0)) 1)
(set (callback (Nb 1)) 2)
(run-schedule (run))
"#,
    );
    let f = table(&p, "Fa");
    let callback = table(&p, "callback");
    let plan = Plan::derive(&p).unwrap();
    assert!(plan.opaque_tables.contains(&callback));
    assert!(
        !plan.affects(f, callback),
        "a dormant merge is not an alias between sorts"
    );
    assert!(plan.deferrable[f]);
    let mut control = Graph::new_with_local_congruence(p.clone()).unwrap();
    let mut scoped = Graph::new_with_scoped_completion(p).unwrap();
    merge_inputs(&mut control);
    merge_inputs(&mut scoped);
    control.repair().unwrap();
    scoped.commit_scoped_unions().unwrap();
    let scope = scoped.completion_scope(&[callback]).unwrap();
    scoped.complete_scope(&scope).unwrap();
    assert!(
        scoped.scoped_completion_report()["stats"]["opaque_full_completions"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert_eq!(scoped.pending_completion_tasks(), 0);
    let nb = table(&scoped.program, "Nb");
    assert_eq!(
        value(&scoped, callback, &[value(&scoped, nb, &[Value::Int(0)])]),
        Value::Int(7)
    );
    control.collect_garbage();
    scoped.collect_garbage();
    assert_eq!(control.export().unwrap(), scoped.export().unwrap());
}
