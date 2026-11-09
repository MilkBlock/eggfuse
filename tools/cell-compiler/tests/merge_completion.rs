use eggfuse_cell_runtime::{
    compiler, completion_plan::Plan, executor::Executor, graph::Graph, program::Program,
};
use std::collections::BTreeSet;

fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("merge-completion", source).unwrap();
    Program::parse(compiler::compile(core, &BTreeSet::new()).unwrap()).unwrap()
}
fn table(p: &Program, name: &str) -> usize {
    p.tables.iter().position(|t| t.name == name).unwrap()
}
fn executor(source: &str, ports: bool) -> Executor {
    let mut e = Executor::new(
        Graph::new_with_scoped_completion(program(source)).unwrap(),
        false,
    );
    if ports {
        e.use_port_scopes().unwrap();
    }
    e
}
fn compare(old: &Executor, new: &Executor) {
    assert_eq!(old.graph.export().unwrap(), new.graph.export().unwrap());
    assert_eq!(old.steps.len(), new.steps.len());
    for (a, b) in old.steps.iter().zip(&new.steps) {
        for key in [
            "ordinal",
            "ruleset",
            "epoch",
            "logical_matches",
            "executed_bindings",
            "changed",
        ] {
            assert_eq!(a[key], b[key], "{key}");
        }
    }
}

#[test]
fn cell_calls_preserve_ordered_merge_reads_primitives_and_constructor_results() {
    let source = r#"
(datatype E (N i64) (Pair E E) (Seen E))
(function port (E) i64 :merge (max old new))
(function ordered (E) E :merge (Pair old new))
(function total (E) i64 :merge (+ old new))
(function callback (E) i64 :merge (+ (port (N 0)) (+ old new)))
(ruleset first) (ruleset second) (ruleset third) (ruleset observe)
(rule ((= x (ordered (N 0)))) ((Seen x)) :ruleset observe)
(rule ((= key (N 0)) (= a (N 1)))
      ((set (port key) 7) (set (ordered key) a)
       (set (total key) 3) (set (callback key) 2)) :ruleset first)
(rule ((= key (N 0)) (= a (N 1)))
      ((set (ordered key) a) (set (total key) 3)) :ruleset second)
(rule ((= key (N 0)) (= b (N 2)))
      ((set (ordered key) b) (set (callback key) 5)) :ruleset third)
(N 0) (N 1) (N 2)
(run-schedule (seq (run first) (run second) (run third) (run observe)))
(check (= (total (N 0)) 6) (= (callback (N 0)) 14)
       (Seen (Pair (N 1) (N 2))))
"#;
    let p = program(source);
    let mut old = Executor::new(Graph::new(p.clone()).unwrap(), true);
    old.graph.merge_programs_enabled = false;
    let mut new = Executor::new(Graph::new(p).unwrap(), true);
    #[cfg(feature = "iterative-bake")]
    {
        use eggfuse_cell_runtime::transfer_audit as audit;
        let execute = |e: &mut Executor| {
            audit::set_active(true);
            audit::enable_write_audit();
            e.execute().unwrap();
            audit::set_active(false);
            (audit::take_digests(), audit::take_write_digests(), audit::take_resume_digests())
        };
        assert_eq!(execute(&mut old), execute(&mut new));
    }
    #[cfg(not(feature = "iterative-bake"))]
    { old.execute().unwrap(); new.execute().unwrap(); }
    compare(&old, &new);
    assert_eq!(old.snapshots, new.snapshots);
    assert!(new.graph.stats.merge_program_constructs > 0);
    assert!(new.graph.stats.merge_port_reads > 0);
    let work = |e: &Executor| {
        let mut stats = serde_json::to_value(&e.graph.stats).unwrap();
        for key in ["merge_program_calls", "merge_program_operations", "merge_program_constructs"] {
            stats.as_object_mut().unwrap().remove(key);
        }
        stats
    };
    assert_eq!(work(&old), work(&new));
    egglog::EGraph::default().parse_and_run_program(None, source).unwrap();
}

const INDEPENDENT: &str = r#"
(datatype A (Na i64) (Fa A) (Ga A) (SeenA A))
(datatype B (Nb i64))
(datatype C (Nc i64) (Smaller C C) (SeenC C))
(function merged (B) C :merge (Smaller old new))
(ruleset seed) (ruleset consumer) (ruleset observe)
(rule ((= a (Na 0)) (= b (Na 1)) (= x (Nb 0)) (= y (Nb 1)))
      ((Ga (Fa a)) (Ga (Fa b)) (union a b) (union x y)) :ruleset seed)
(rule ((= c (merged (Nb 0)))) ((SeenC c)) :ruleset consumer)
(rule ((= g (Ga x))) ((SeenA g)) :ruleset observe)
(Na 0) (Na 1)
(set (merged (Nb 0)) (Nc 0)) (set (merged (Nb 1)) (Nc 1))
(run-schedule (seq (run seed) (run consumer) (run observe)))
"#;

#[test]
fn constructor_merge_publishes_and_is_consumed_while_unrelated_congruence_remains() {
    let mut old = executor(INDEPENDENT, false);
    let mut new = executor(INDEPENDENT, true);
    let m = table(&new.graph.program, "merged");
    let smaller = table(&new.graph.program, "Smaller");
    let plan = new.graph.program.completion_plan.as_ref().unwrap();
    assert_eq!(plan.merges[m].reads, vec![smaller]);
    assert_eq!(plan.merges[m].births, vec![smaller]);
    assert!(plan.opaque_tables.is_empty());
    let seen = table(&new.graph.program, "SeenC");
    assert!(plan.affects(smaller, seen));
    assert!(
        !plan.affects(m, seen),
        "a constructor birth is not a result union"
    );
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    assert_eq!(new.graph.witness_count(smaller), 1);
    assert_eq!(
        new.graph.witness_count(table(&new.graph.program, "SeenC")),
        1
    );
    let point = serde_json::json!({"executor":new.scoped_execution_report(),"graph":new.graph.scoped_completion_report(),"ports":new.graph.port_completion_report(),"smaller_facts":new.graph.witness_count(smaller),"seen_c_facts":new.graph.witness_count(table(&new.graph.program,"SeenC"))});
    if point["executor"]["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
        assert_eq!(
            point["executor"]["stats"]["executed_bindings_while_pending"],
            1
        );
        assert_eq!(point["graph"]["stats"]["opaque_full_completions"], 0);
    }
    new.execute().unwrap();
    compare(&old, &new);
    if let Ok(path) = std::env::var("MERGE_COMPLETION_EVIDENCE") {
        std::fs::write(path, serde_json::to_vec_pretty(&serde_json::json!({"scope":"standalone single-thread Cell CPU; ordered merge creates a constructor while another region remains pending", "checkpoint":point,"final_executor":new.scoped_execution_report(),"exact_final_state_and_ordered_bindings":true,"parallel_or_timing_claim":false})).unwrap()).unwrap();
    }
}

#[test]
fn merge_constructor_reads_pull_in_the_pending_input_chain() {
    let source = INDEPENDENT
        .replace("(SeenC C))", "(SeenC C) (Pair A A))")
        .replace(
            ":merge (Smaller old new)",
            ":merge (Pair (Fa (Na 0)) (Fa (Na 1)))",
        );
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(1)).unwrap();
    // The merge's implicit constructor reads share A's pending inputs. They
    // must participate in the same ordered completion pass before publication.
    assert_eq!(new.graph.pending_completion_tasks(), 0);
    assert_eq!(new.graph.witness_count(table(&new.graph.program, "Fa")), 1);
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn source_set_demands_its_hidden_merge_constructor_reads() {
    let source = INDEPENDENT
        .replace("(SeenC C))", "(SeenC C) (Pair A A))")
        .replace(
            ":merge (Smaller old new)",
            ":merge (Pair (Fa (Na 0)) (Fa (Na 1)))",
        )
        .replace("(union a b) (union x y)", "(union a b)")
        .replace(
            "((SeenC c)) :ruleset consumer)",
            "((set (merged (Nb 0)) (Nc 2))) :ruleset consumer)",
        );
    let mut old = executor(&source, false);
    let mut new = executor(&source, true);
    old.execute().unwrap();
    new.execute_until(Some(1)).unwrap();
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
    }
    new.execute_until(Some(2)).unwrap();
    assert_eq!(new.graph.pending_completion_tasks(), 0);
    assert_eq!(
        new.scoped_execution_report()["stats"]["runs_with_unrelated_pending"],
        0
    );
    new.execute().unwrap();
    compare(&old, &new);
}

#[test]
fn container_elements_propagate_their_eq_sort_without_global_effects() {
    let p = program(
        r#"
(datatype A (Na i64) (Fa A))
(sort AS (Set A))
(datatype B (Box AS))
(datatype C (Other i64))
(Box (set-of (Fa (Na 0))))
(Box (set-of (Fa (Na 1))))
(Other 1)
(run-schedule (run))
"#,
    );
    let plan = Plan::derive(&p).unwrap();
    assert!(plan.opaque_tables.is_empty());
    assert!(plan.affects(table(&p, "Fa"), table(&p, "Box")));
    assert!(!plan.affects(table(&p, "Fa"), table(&p, "Other")));
}

#[test]
fn missing_checked_merge_code_retains_the_global_boundary() {
    let mut p = program(INDEPENDENT);
    let m = table(&p, "merged");
    p.merge_programs.merges.remove(&m);
    let plan = Plan::derive(&p).unwrap();
    assert!(plan.opaque_tables.contains(&m));
    assert!((0..p.tables.len()).all(|t| plan.affects(m, t)));
}

#[test]
fn source_union_includes_hidden_read_only_callbacks_in_its_write_fence() {
    let p = program(
        r#"
(datatype B (Nb i64))
(function port (i64) i64 :merge (min old new))
(function callback (B) i64 :merge (port 0))
(ruleset seed)
(rule ((= x (Nb 0)) (= y (Nb 1))) ((union x y)) :ruleset seed)
(set (port 0) 7)
(set (callback (Nb 0)) 1) (set (callback (Nb 1)) 2)
(run-schedule (run seed))
"#,
    );
    let plan = Plan::derive(&p).unwrap();
    let port = table(&p, "port");
    let callback = table(&p, "callback");
    assert!(!plan.affects(callback, port));
    assert!(plan.completion_reads[callback].contains(&port));
    // Check the per-Cell demands consumed by the actual matched-RHS wait.
    assert!(p.sets["seed"].iter().all(|&r| {
        let demand = &plan.rule_demands[r];
        !demand.query.contains(&port) && !demand.accesses.contains(&port)
    }));
    assert!(p.sets["seed"].iter().any(|&r| {
        let demand = &plan.rule_demands[r];
        demand.query.contains(&port) || demand.rhs.contains(&port)
    }));
}

#[test]
fn sibling_constructors_share_an_input_union_without_sharing_future_result_effects() {
    let source = r#"
(datatype E (N i64) (A E) (B E) (GA E) (GB E) (Seen E))
(function score (E) i64 :merge (min old new))
(ruleset seed) (ruleset consume) (ruleset observe)
(rule ((= x (N 0)) (= y (N 1))) ((union x y)) :ruleset seed)
(rule ((= b (B (N 0))) (= v (score b))) ((Seen b)) :ruleset consume)
(rule ((= a (GA x))) ((GA x)) :ruleset observe)
(GA (A (N 0))) (GA (A (N 1)))
(GB (B (N 0))) (GB (B (N 1)))
(set (score (B (N 0))) 7) (set (score (B (N 1))) 3)
(run-schedule (seq (run seed) (run consume) (run observe)))
"#;
    let mut old = executor(source, false);
    let mut new = executor(source, true);
    old.execute().unwrap();
    new.execute_until(Some(2)).unwrap();
    assert_eq!(
        new.graph.witness_count(table(&new.graph.program, "Seen")),
        1
    );
    if new.scoped_execution_report()["global_observer"] == false {
        assert!(new.graph.pending_completion_tasks() > 0);
        assert_eq!(new.graph.witness_count(table(&new.graph.program, "A")), 2);
        assert_eq!(new.graph.witness_count(table(&new.graph.program, "B")), 1);
        assert_eq!(
            new.scoped_execution_report()["stats"]["executed_bindings_while_pending"],
            1
        );
    }
    new.execute().unwrap();
    compare(&old, &new);
}
