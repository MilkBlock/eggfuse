#![cfg(feature = "sparse-cells")]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
fn artifact(source: &str) -> serde_json::Value {
    let core = eggfuse_bake::device_frontend::core("cell-execution", source).unwrap();
    compiler::compile(core, &Default::default()).unwrap()
}
fn executor(source: &str, workers: usize) -> Executor {
    let program = Program::parse(artifact(source)).unwrap();
    let mut e = Executor::new(Graph::new_with_repair_ports(program).unwrap(), true);
    e.use_entry_publications().unwrap();
    if workers > 0 {
        e.use_query_workers(workers, 8).unwrap();
        #[cfg(feature = "parallel-residuals")]
        e.use_parallel_residuals().unwrap();
    }
    e
}
fn same(a: &Executor, b: &Executor) {
    assert_eq!(a.snapshots, b.snapshots, "every source Run state");
    assert_eq!(
        a.binding_audit, b.binding_audit,
        "input identity excludes prepared RHS slots"
    );
    assert_eq!(a.graph.export().unwrap(), b.graph.export().unwrap());
    assert_eq!(a.steps.len(), b.steps.len());
    for (a, b) in a.steps.iter().zip(&b.steps) {
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
            assert_eq!(a[k], b[k], "{k}");
        }
    }
}
fn initial() -> String {
    (0..64)
        .map(|i| format!("(Start (N {i})) (set (Input (N {i})) {i}) (set (Current (N {i})) 1)\n"))
        .collect()
}
const HEADER: &str = r#"
(datatype E (N i64) (Start E) (F E i64))
(function Input (E) i64 :merge new)
(function Current (E) i64 :merge new)
(function Out (E) i64 :merge new)
(ruleset step)
"#;

#[test]
fn unit_tails_write_candidate_rows_and_invalidate_duplicates_without_set_replay() {
    let seed=(0..128).map(|n|format!("(N {n})")).collect::<Vec<_>>().join("\n");
    let source=format!(r#"
(datatype E (N i64) (F E i64) (G E) (Seen E))
(function Stamp (i64) Unit :merge old)
(function Ticket (E E) Unit :merge old)
(ruleset step) (ruleset next) (ruleset change)
(rule ((= x (N n))) ((let v (+ n 1)) (let a (F x v)) (let b (G a))
 (set (Stamp 0) ()) (set (Ticket a b) ())) :ruleset step)
(rule ((Ticket a b)) ((Seen b)) :ruleset next)
(rule ((= x (N n)) (= n 1)) ((union x (N 0))) :ruleset change)
{seed}
(run-schedule (seq (run step) (run next) (run change) (run step) (run next)))
"#);
    egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
    let mut control=executor(&source,4);
    #[cfg(feature="iterative-bake")]
    {eggfuse_cell_runtime::transfer_audit::set_active(true);eggfuse_cell_runtime::transfer_audit::enable_write_audit();}
    control.execute().unwrap();
    #[cfg(feature="iterative-bake")]
    let writes=eggfuse_cell_runtime::transfer_audit::take_write_digests();
    let mut candidate=executor(&source,4);candidate.use_cell_execution(1).unwrap();
    candidate.execute().unwrap();same(&control,&candidate);
    #[cfg(feature="iterative-bake")]
    {assert_eq!(writes,eggfuse_cell_runtime::transfer_audit::take_write_digests());
     eggfuse_cell_runtime::transfer_audit::set_active(false);}
    let r=candidate.report();let w=&r["cell_execution"]["runtime"]["stats"]["births"];
    assert!(w["unit_worker_rows"].as_u64().unwrap()>0,"{w}");
    assert!(w["unit_invalidated"].as_u64().unwrap()>0,"{w}");
    assert_eq!(w["unit_candidates"].as_u64().unwrap(),w["unit_inserts"].as_u64().unwrap()+w["unit_invalidated"].as_u64().unwrap());
    let q=&r["cell_execution"]["runtime"]["stats"]["scheduler"];
    assert!(q["batches"].as_u64().unwrap()<q["jobs"].as_u64().unwrap());
    assert!(w["worker_batches"].as_u64().unwrap()<=q["batches"].as_u64().unwrap(),
        "only ready batches dispatch; singleton batches remain attached");
}

#[test]
fn scalar_failure_before_or_after_a_constructor_tail_keeps_the_source_prefix() {
    for after in [false,true] {
        let seed=(0..64).map(|n|format!("(N {})",if n==32 {i64::MAX}else{n})).collect::<Vec<_>>().join("\n");
        let compute="(let fail (+ n 1))";
        let source=format!(r#"
(datatype E (N i64) (F E) (G E) (H E))
(function Ticket (E) Unit :merge old)
(ruleset step)
(rule ((= x (N n))) ((F x) {} (let g (G (F x))) (let h (H g)) (set (Ticket h) ()) {}) :ruleset step)
{seed} (run-schedule (run step))
"#,if after {""}else{compute},if after {compute}else{""});
        let mut control=executor(&source,4);let error=control.execute().unwrap_err();
        let mut candidate=executor(&source,4);candidate.use_cell_execution(1).unwrap();
        assert_eq!(candidate.execute().unwrap_err(),error);
        assert_eq!(candidate.graph.export().unwrap(),control.graph.export().unwrap(),"after={after}");
    }
}

#[test]
fn workers_write_actual_rows_and_invalidate_duplicate_cells_before_publication() {
    for merge in ["(min old new)", "(max old new)", "old"] {
        let seed = (0..96).flat_map(|key| (0..8).map(move |v|
            format!("(Offer (N {key}) {v})"))).collect::<Vec<_>>().join("\n");
        let source = format!(r#"
(datatype E (N i64) (Offer E i64) (Seen E i64))
(function Score (E) i64 :merge {merge})
(ruleset step) (ruleset next) (ruleset change) (ruleset improve)
(rule ((= q (Offer x v))) ((set (Score x) v)) :ruleset step)
(rule ((= v (Score x))) ((Seen x v)) :ruleset next)
(rule ((= x (N n))) ((Offer x 100)) :ruleset improve)
(rule ((= x (N n)) (= n 1)) ((union x (N 0))) :ruleset change)
{seed}
(run-schedule (seq (run step) (run next) (run improve) (run step) (run next) (run change) (run step) (run next)))
"#);
        egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
        let mut control = executor(&source, 4);
        #[cfg(feature="iterative-bake")]
        { eggfuse_cell_runtime::transfer_audit::set_active(true);
          eggfuse_cell_runtime::transfer_audit::enable_write_audit(); }
        control.execute().unwrap();
        #[cfg(feature="iterative-bake")]
        let writes = eggfuse_cell_runtime::transfer_audit::take_write_digests();
        let mut candidate = executor(&source, 4);
        candidate.use_cell_execution(1).unwrap();
        candidate.execute().unwrap();
        same(&control, &candidate);
        #[cfg(feature="iterative-bake")]
        { assert_eq!(writes, eggfuse_cell_runtime::transfer_audit::take_write_digests(),
            "logical source improvements keep exact effect order");
          eggfuse_cell_runtime::transfer_audit::set_active(false); }
        let report = candidate.report();
        let work = &report["cell_execution"]["runtime"]["stats"]["writes"];
        assert!(work["worker_rows"].as_u64().unwrap() > 0, "{merge}: {work}");
        assert!(work["duplicate_targets"].as_u64().unwrap() > 0, "{work}");
        assert!(work["invalidated"].as_u64().unwrap() > 0, "{work}");
        assert!(work["row_writes"].as_u64().unwrap() < work["candidates"].as_u64().unwrap(), "{work}");
        assert_eq!(candidate.graph.stats.function_updates, control.graph.stats.function_updates);
    }
}

#[test]
fn speculative_scalar_failure_preserves_the_original_partial_effects() {
    let seed = (0..64).map(|i| format!("(Offer (N {i}) {})", if i == 32 { i64::MAX } else { i }))
        .collect::<Vec<_>>().join("\n");
    let source = format!(r#"
(datatype E (N i64) (Offer E i64))
(function Score (E) i64 :merge (min old new))
(ruleset step)
(rule ((= q (Offer x v))) ((set (Score x) (+ v 1))) :ruleset step)
{seed}
(run-schedule (run step))
"#);
    let mut control = executor(&source, 4);
    let mut candidate = executor(&source, 4);
    candidate.use_cell_execution(1).unwrap();
    assert_eq!(control.execute().unwrap_err(), candidate.execute().unwrap_err());
    assert_eq!(control.graph.export().unwrap(), candidate.graph.export().unwrap());
    assert_eq!(candidate.report()["cell_execution"]["runtime"]["stats"]["writes"]["fallback_batches"], 1);
}

#[test]
fn ready_cells_share_results_without_draining_or_replaying_their_prefix() {
    for shared in [false,true] {
      for ordered in [false,true] {
        let seed=(0..128).map(|n|format!("(N {n})")).collect::<Vec<_>>().join("\n");
        let root=if shared {"(N 0)"} else {"x"};
        let tail=if ordered {"(set (Count c) n) (union c x)"} else {""};
        let source=format!(r#"
(datatype E (N i64) (F E) (G E) (H E i64) (Seen E))
(function Count (E) i64 :merge (min old new))
(ruleset step) (ruleset next) (ruleset change)
(rule ((= x (N n))) ((let a (F {root})) (let b (G a)) (let c (H b n)) {tail}) :ruleset step)
(rule ((= x (H y n))) ((Seen x)) :ruleset next)
(rule ((= x (N n)) (= n 1)) ((union x (N 0))) :ruleset change)
{seed}
(run-schedule (seq (run step) (run next) (run change) (run step) (run next)))
"#);
        egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
        let mut control=executor(&source,4);
        #[cfg(feature="iterative-bake")]
        {eggfuse_cell_runtime::transfer_audit::set_active(true);eggfuse_cell_runtime::transfer_audit::enable_write_audit();}
        control.execute().unwrap();
        #[cfg(feature="iterative-bake")]
        let writes=eggfuse_cell_runtime::transfer_audit::take_write_digests();
        let mut candidate=executor(&source,4);candidate.use_cell_execution(1).unwrap();
        candidate.execute().unwrap();same(&control,&candidate);
        #[cfg(feature="iterative-bake")]
        {
            assert_eq!(writes,eggfuse_cell_runtime::transfer_audit::take_write_digests(),
                "source ordinals and ordered effective writes survive suspension");
            eggfuse_cell_runtime::transfer_audit::set_active(false);
        }
        let r=candidate.report();let queue=&r["cell_execution"]["runtime"]["stats"]["scheduler"];
        assert!(queue["jobs"].as_u64().unwrap()>0,"shared={shared}, ordered={ordered}: {queue}");
        if shared {
            assert!(queue["dependency_admissions"].as_u64().unwrap()>0,"shared={shared}, ordered={ordered}: {queue}");
            assert_eq!(queue["dependency_flushes"],0,"shared={shared}, ordered={ordered}: {queue}");
            let work=&r["cell_execution"]["runtime"]["stats"]["births"];
            assert!(work["result_hits"].as_u64().unwrap()>0,"{work}");
            assert!(work["local_reuses"].as_u64().unwrap()>0,"{work}");
        }
        else {assert!(queue["max_ready"].as_u64().unwrap()>1,"shared={shared}, ordered={ordered}: {queue}");
            assert!(queue["batches"].as_u64().unwrap()<queue["jobs"].as_u64().unwrap(),"shared={shared}, ordered={ordered}: {queue}");}
        assert_eq!(candidate.graph.stats.constructor_requests,control.graph.stats.constructor_requests);
        assert_eq!(candidate.graph.stats.constructor_reused,control.graph.stats.constructor_reused);
        assert_eq!(candidate.graph.stats.rhs_suspend_holds,candidate.graph.stats.rhs_suspend_releases);
    }
  }
}

#[test]
fn new_constructor_roots_complete_local_cells_and_publish_actual_results() {
    for existing in 0..=3 {
        let seed=(0..16).map(|n| {
            let mut term=format!("(N {n})");
            for name in ["F","G","H"].iter().take(existing) {term=format!("({name} {term})");}
            term
        }).collect::<Vec<_>>().join("\n");
        let source=format!(r#"
(datatype E (N i64) (F E) (G E) (H E) (Seen E))
(function Out (E) i64 :merge new)
(ruleset step) (ruleset next)
(rule ((= x (N n))) ((let a (F x)) (let b (G a)) (let c (H b)) (set (Out c) n)) :ruleset step)
(rule ((= n (Out x))) ((Seen x)) :ruleset next)
{seed}
(run-schedule (seq (run step) (run next) (run step) (run next)))
(check (Seen (H (G (F (N 2))))) (= (Out (H (G (F (N 2))))) 2))
"#);
        egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
        let mut control=executor(&source,4);control.execute().unwrap();
        for workers in [1,4] {
            let mut candidate=executor(&source,workers);candidate.use_cell_execution(1).unwrap();
            candidate.execute().unwrap();same(&control,&candidate);
            let r=candidate.report();let work=&r["cell_execution"]["runtime"]["stats"]["births"];
            let minimum=(2usize.saturating_sub(existing)*16) as u64;
            assert!(work["local_births"].as_u64().unwrap()>=minimum,"{r}");
            assert_eq!(work["committed_rows"],work["local_births"]);
            if workers>1 && minimum>0 {assert!(work["worker_operations"].as_u64().unwrap()>=minimum);}
            assert_eq!(candidate.graph.stats.constructor_requests,control.graph.stats.constructor_requests);
            assert_eq!(candidate.graph.stats.constructor_reused,control.graph.stats.constructor_reused);
            assert_eq!(candidate.graph.stats.logical_facts_created,control.graph.stats.logical_facts_created);
        }
    }
}

#[test]
fn shared_effects_cut_local_birth_proofs_and_later_failure_preserves_committed_rows() {
    for fail in [false,true] {
        let tail=if fail {"(panic \"after local construction\")"} else {"(set (Out (H b)) n)"};
        let source=format!(r#"
(datatype E (N i64) (F E) (G E) (H E))
(function Out (E) i64 :merge new)
(ruleset step)
(rule ((= x (N n))) ((let a (F x)) (set (Out a) n)
 (let b (G a)) (H b) {tail}) :ruleset step)
(N 1) (N 2)
(run-schedule (run step))
"#);
        let mut control=executor(&source,4);let expected=control.execute();
        for workers in [1,4] {
            let mut candidate=executor(&source,workers);candidate.use_cell_execution(1).unwrap();
            assert_eq!(candidate.execute(),expected);
            assert_eq!(candidate.graph.export().unwrap(),control.graph.export().unwrap());
            if !fail {same(&control,&candidate);}
            let r=candidate.report();
            assert_eq!(r["cell_execution"]["runtime"]["stats"]["births"]["local_births"],if fail {1}else{2});
            assert_eq!(candidate.graph.stats.constructor_requests,control.graph.stats.constructor_requests);
        }
    }
}

#[test]
fn local_constructor_candidates_compare_actual_bound_values_and_export_the_returned_witness() {
    let seed=(0..16).map(|n|format!("(set (Left (N {n})) {n}) (set (Right (N {n})) {n})"))
        .collect::<Vec<_>>().join("\n");
    let source=format!(r#"
(datatype E (N i64) (F E) (G E i64) (H E) (Seen E))
(function Left (E) i64 :merge new) (function Right (E) i64 :merge new)
(function Out (E) i64 :merge new)
(ruleset step) (ruleset next)
(rule ((= x (N n)) (= a (Left x)) (= b (Right x)))
 ((let u (F x)) (G u a) (let v (G u b)) (set (Out (H v)) n)) :ruleset step)
(rule ((= n (Out x))) ((Seen x)) :ruleset next)
{seed}
(run-schedule (seq (run step) (run next)))
(check (Seen (H (G (F (N 2)) 2))))
"#);
    egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
    let mut control=executor(&source,4);control.execute().unwrap();
    for workers in [1,4] {
        let mut candidate=executor(&source,workers);candidate.use_cell_execution(1).unwrap();
        candidate.execute().unwrap();same(&control,&candidate);
        assert_eq!(candidate.report()["cell_execution"]["runtime"]["stats"]["births"]["local_reuses"],16);
        assert_eq!(candidate.graph.stats.constructor_reused,control.graph.stats.constructor_reused);
    }
}

#[test]
fn constructor_continuation_crosses_completed_scalar_segments_but_stops_at_missing_results() {
    for existing in [1, 2] {
        let seed = (0..16).map(|n| {
            let first = format!("(F (N {n}) {})", n+1);
            if existing == 1 { first } else { format!("(G {first} {})", 2*(n+1)) }
        }).collect::<Vec<_>>().join("\n");
        let source = format!(r#"
(datatype E (N i64) (F E i64) (G E i64) (Seen E))
(function Out (E) i64 :merge new)
(ruleset step) (ruleset next)
(rule ((= x (N n)))
 ((let a (+ n 1)) (let u (F x a)) (let b (* a 2))
  (let v (G u b)) (set (Out v) b)) :ruleset step)
(rule ((= n (Out x))) ((Seen x)) :ruleset next)
{seed}
(run-schedule (seq (run step) (run next)))
(check (= (Out (G (F (N 2) 3) 6)) 6) (Seen (G (F (N 2) 3) 6)))
"#);
        egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
        let mut control=executor(&source,4);control.execute().unwrap();
        for workers in [1,4] {
            let mut candidate=executor(&source,workers);
            candidate.use_cell_execution(1).unwrap();candidate.execute().unwrap();
            same(&control,&candidate);
            assert_eq!(candidate.graph.stats.constructor_prefix_operations,16*existing);
            assert_eq!(candidate.graph.stats.prepared_rhs_operations,16);
            assert_eq!(candidate.graph.stats.prepared_rhs_later_operations,16);
            assert_eq!(candidate.graph.stats.constructor_requests,control.graph.stats.constructor_requests);
            assert_eq!(candidate.graph.stats.constructor_reused,control.graph.stats.constructor_reused);
            assert_eq!(candidate.graph.stats.constructor_prefix_rejected,0);
            let report=candidate.report();
            assert_eq!(report["query_workers"]["stats"]["execution"]["constructor"]["prefix_scalar_checks"],32);
        }
    }
}

#[test]
fn failed_scalar_does_not_certify_a_later_constructor_or_move_its_error() {
    for head in [false,true] {
        let first=if head {"(/ n 0)"} else {"(+ n 1)"};
        let second=if head {"(* a 2)"} else {"(/ a 0)"};
        let source=format!(r#"
(datatype E (N i64) (F E i64) (G E i64))
(function Out (E) i64 :merge new)
(ruleset step)
(rule ((= x (N n))) ((let a {first}) (let u (F x a))
 (let b {second}) (let v (G u b)) (set (Out v) b)) :ruleset step)
(G (F (N 1) 2) 4) (G (F (N 2) 3) 6)
(run-schedule (run step))
"#);
        let mut control=executor(&source,4);
        let error=control.execute().unwrap_err();
        for workers in [1,4] {
            let mut candidate=executor(&source,workers);candidate.use_cell_execution(1).unwrap();
            assert_eq!(candidate.execute().unwrap_err(),error);
            assert_eq!(candidate.graph.export().unwrap(),control.graph.export().unwrap());
            assert_eq!(candidate.graph.stats.constructor_requests,control.graph.stats.constructor_requests);
            assert_eq!(candidate.graph.stats.constructor_prefix_operations,u64::from(!head));
            let report=candidate.report();
            assert_eq!(report["query_workers"]["stats"]["execution"]["constructor"]["prefix_scalar_stops"],2);
        }
    }
}

#[test]
fn constructor_progress_and_later_scalar_preparation_share_the_instance_without_replaying_either() {
    let source = r#"
(datatype E (N i64) (F E) (G E) (H E))
(function Out (E) i64 :merge new)
(ruleset step)
(rule ((= x (N n)))
 ((let u (F x)) (let v (G u)) (set (Out v) (+ n 1)) (H u)) :ruleset step)
(G (F (N 1))) (G (F (N 2)))
(run-schedule (run step))
(check (= (Out (G (F (N 2)))) 3))
"#;
    egglog::EGraph::default().parse_and_run_program(None,source).unwrap();
    let mut control=executor(source,4);control.execute().unwrap();
    for workers in [1,4] {
        let mut candidate=executor(source,workers);
        candidate.use_cell_execution(1).unwrap();candidate.execute().unwrap();
        same(&control,&candidate);
        assert!(candidate.graph.stats.constructor_prefix_operations>=4);
        assert!(candidate.graph.stats.prepared_rhs_later_operations>=2);
        assert_eq!(candidate.graph.stats.prepared_rhs_operations,0,
            "constructor progress is not charged as scalar preparation");
        assert_eq!(candidate.graph.stats.constructor_prefix_receipt_writes,0);
    }
}

#[test]
fn entry_configuration_refreshes_the_shared_preparation_layout_before_the_first_run() {
    let source = r#"
(datatype E (N i64) (F E) (G E) (Seen E))
(ruleset step) (ruleset next)
(rule ((= x (N n))) ((G (F x))) :ruleset step)
(rule ((G x)) ((Seen x)) :ruleset next)
(G (F (N 1))) (G (F (N 2)))
(run-schedule (seq (run step) (run next) (run step) (run next)))
"#;
    let mut control=executor(source,4);control.execute().unwrap();
    let mut candidate=Executor::new(Graph::new_with_repair_ports(Program::parse(artifact(source)).unwrap()).unwrap(),true);
    candidate.use_query_workers(4,1).unwrap();
    candidate.use_cell_execution(1).unwrap();
    // Configuration precedes every instance. Refresh the compiled layout once,
    // preserving the same buffer path despite the order of configuration calls.
    candidate.use_entry_publications().unwrap();
    candidate.execute().unwrap();
    same(&control,&candidate);
    assert_eq!(candidate.graph.stats.constructor_prefix_rejected,0);
    assert!(candidate.graph.stats.constructor_prefix_operations>0);
    assert!(candidate.report()["stage_spine"]["stats"]["prepared_effect_buffer_moves"].as_u64().unwrap()>0);
    assert!(candidate.report()["stage_spine"]["stats"]["prepared_effect_spares_released"].as_u64().unwrap()>0);
    assert!(candidate.report()["stage_spine"]["owned_output_storage"]["pooled_buffers"].as_u64().unwrap()
        <= control.report()["stage_spine"]["owned_output_storage"]["pooled_buffers"].as_u64().unwrap(),
        "prepared frames replace idle cache entries instead of accumulating across Runs");
}

#[test]
fn worker_constructor_prefix_continues_to_first_missing_result_and_exports_actual_foreign_results() {
    for existing in [0,1,2,3] {
        for union in [false,true] {
            let seed = (0..16).map(|n| {
                let mut term=format!("(N {n})");
                for name in ["F","G","H"].iter().take(existing) {term=format!("({name} {term})");}
                term
            }).collect::<Vec<_>>().join("\n");
            let effect=if union {"(union (H (G (F x))) x)"} else {"(H (G (F x)))"};
            let source=format!(r#"
(datatype E (N i64) (F E) (G E) (H E) (Seen E))
(ruleset step) (ruleset next)
(rule ((= x (N n))) ({effect}) :ruleset step)
(rule ((H x)) ((Seen x)) :ruleset next)
{seed}
(run-schedule (seq (run step) (run next) (run step) (run next)))
"#);
            egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
            for stable in [false,true] {
                let create=|workers| {
                    let p=Program::parse(artifact(&source)).unwrap();
                    let g=if stable {Graph::new_with_local_congruence(p).unwrap()}
                        else {Graph::new_with_repair_ports(p).unwrap()};
                    let mut e=Executor::new(g,true);
                    e.use_entry_publications().unwrap();e.use_query_workers(workers,1).unwrap();e
                };
                let mut control=create(4);control.execute().unwrap();
                for workers in [1,4] {
                    let mut candidate=create(workers);
                    candidate.use_cell_execution(1).unwrap();candidate.execute().unwrap();
                    same(&control,&candidate);
                    // union(H(...),x) lowers its final constructor into an
                    // ordered Set. Only F/G may belong to its worker prefix.
                    let local = existing.min(if union {2} else {3});
                    assert!(candidate.graph.stats.constructor_prefix_operations >= (local*16) as u64,
                        "existing={existing} union={union} stable={stable} workers={workers}: {}",
                        serde_json::json!({"execution":candidate.report()["cell_execution"],
                            "preparation":candidate.report()["query_workers"]["stats"]["execution"],
                            "rule":candidate.graph.program.artifact["recipe"]["rules"][0]}));
                    assert_eq!(candidate.graph.stats.constructor_prefix_rejected,0);
                    assert_eq!(candidate.graph.stats.constructor_requests,control.graph.stats.constructor_requests);
                    assert_eq!(candidate.graph.stats.constructor_reused,control.graph.stats.constructor_reused);
                    let report=candidate.report();
                    if existing!=0 {
                        assert!(report["query_workers"]["stats"]["execution"]["constructor"]["prefix_slot_writes"].as_u64().unwrap()>0);
                    } else {
                        assert!(report["query_workers"]["stats"]["execution"]["constructor"]["misses"].as_u64().unwrap()>=16);
                    }
                }
            }
        }
    }
}

#[test]
fn prepared_constructor_witnesses_replace_source_lookups_in_both_execution_paths() {
    for stable in [false,true] {
    for scalar in [false, true] {
        let rhs = if scalar { "(let a (+ n 1)) (F x a) (set (Out x) a)" }
            else { "(F x n)" };
        let existing: String = (0..64).map(|n| format!("(F (N {n}) {})\n", n + i32::from(scalar))).collect();
        let source = format!("{HEADER}\n(rule ((= x (N n))) ({rhs}) :ruleset step)\n{}\n{existing}\n(run-schedule (run step))", initial());
        egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
        let create = |workers| {
            if !stable { return executor(&source, workers); }
            let mut e=Executor::new(Graph::new_with_local_congruence(Program::parse(artifact(&source)).unwrap()).unwrap(),true);
            e.use_entry_publications().unwrap(); e.use_query_workers(workers,8).unwrap(); e
        };
        let mut control = create(4);
        control.execute().unwrap();
        for workers in [1, 4] {
            let mut candidate = create(workers);
            candidate.use_cell_execution(1).unwrap();
            candidate.execute().unwrap();
            same(&control, &candidate);
            let r = candidate.report();
            let prep = &r["query_workers"]["stats"]["execution"]["constructor"];
            assert_eq!(prep["lookups"], 64, "{r}");
            assert_eq!(prep["hits"], 64);
            assert_eq!(candidate.graph.stats.constructor_prepared_accepted, 64);
            assert_eq!(candidate.graph.stats.constructor_prepared_rejected, 0);
            assert_eq!(candidate.graph.stats.constructor_prepared_sealed, 64);
            assert_eq!(candidate.graph.stats.constructor_prepared_fields, 0);
            assert_eq!(candidate.graph.stats.constructor_prepared_key_fields_avoided, 128);
            assert_eq!(candidate.graph.key_lookup_calls.get() - 64,
                control.graph.key_lookup_calls.get() - 64, "one source lookup removed per accepted witness");
            assert_eq!(candidate.graph.stats.rhs_frames_avoided, control.graph.stats.rhs_frames_avoided,
                "constructor-only source prefixes retain their frame avoidance");
            assert_eq!(r["query_workers"]["stats"]["worker_constructor_lookups"].as_array().unwrap()
                .iter().map(|v|v.as_u64().unwrap()).sum::<u64>(), if workers > 1 {64} else {0});
            eprintln!("constructor-preparation {}", serde_json::json!({"scalar":scalar,"workers":workers,"stable":stable,
                "prepared":prep,"accepted":candidate.graph.stats.constructor_prepared_accepted,
                "rejected":candidate.graph.stats.constructor_prepared_rejected}));
        }
    }
    }
}

#[test]
fn deleted_prepared_witnesses_cannot_supply_new_constructor_identity() {
    let source = format!(r#"{HEADER}
(rule ((= x (N n))) ((delete (F x n))) :ruleset step)
(rule ((= x (N n))) ((F x n)) :ruleset step)
{}
{}
(run-schedule (run step))
"#, initial(), (0..64).map(|n|format!("(F (N {n}) {n})\n")).collect::<String>());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 4);
    control.execute().unwrap();
    let mut candidate = executor(&source, 4);
    candidate.use_cell_execution(1).unwrap();
    candidate.execute().unwrap();
    same(&control, &candidate);
    let prep = &candidate.report()["query_workers"]["stats"]["execution"]["constructor"];
    assert_eq!(prep["hits"],64);
    assert_eq!(candidate.graph.stats.constructor_prepared_accepted,0);
    assert_eq!(candidate.graph.stats.constructor_prepared_rejected,64);
    assert_eq!(candidate.graph.key_lookup_calls.get(),control.graph.key_lookup_calls.get()+64,
        "stale speculation pays for both lookup paths");
}

#[test]
fn absent_constructor_preparation_does_not_prove_absence_at_source_position() {
    let source = format!(r#"{HEADER}
(rule ((= x (N n))) ((F x n)) :ruleset step)
(rule ((Start x) (= n (Input x))) ((F x n) (set (Out x) n)) :ruleset step)
{}
(run-schedule (run step)) (check (= (Out (N 2)) 2))
"#,initial());
    egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
    let mut control=executor(&source,4); control.execute().unwrap();
    let mut candidate=executor(&source,4); candidate.use_cell_execution(1).unwrap(); candidate.execute().unwrap();
    same(&control,&candidate);
    let r=candidate.report();
    let prep=&r["query_workers"]["stats"]["execution"]["constructor"];
    assert_eq!(prep["hits"],0);
    assert!(prep["misses"].as_u64().unwrap()>=64);
    assert_eq!(candidate.graph.stats.constructor_prepared_checks,0);
    assert_eq!(candidate.graph.stats.constructor_reused,control.graph.stats.constructor_reused);
}

#[test]
fn completed_matches_share_the_run_worker_invocation_without_answer_packets() {
    let source = format!(r#"{HEADER}
(rule ((= x (N n)))
 ((let a (+ n 1)) (F x a) (let b (* a 2)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
(check (= (Out (N 2)) 6))
"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for (workers, grain) in [(1, 1), (2, 1), (4, 64)] {
        let mut candidate = executor(&source, workers);
        candidate.use_cell_execution(grain).unwrap();
        candidate.execute().unwrap();
        same(&control, &candidate);
        let report = candidate.report();
        let stats = &report["query_workers"]["stats"];
        let matched = &report["query_workers"]["matched"];
        assert_eq!(matched["execution"]["operations"], 128, "{report}");
        assert_eq!(matched["execution"]["later_operations"], 64);
        assert_eq!(matched["matched_only_invocations"], 1);
        assert_eq!(stats["answers"], 0, "existing matches produce no second answer vector");
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 64);
        assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 64);
        assert_eq!(report["cell_execution"]["runtime"]["stats"]["worker_segments"], 0);
        assert_eq!(matched[if workers > 1 { "worker_operations" } else { "inline_operations" }], 128);
    }
}

#[test]
fn completed_matches_and_cross_stage_queries_use_one_mixed_invocation() {
    let source = format!(r#"{HEADER}
(datatype Gated (Gate E))
(ruleset make)
(rule ((Start x)) ((Gate x)) :ruleset make)
(rule ((= x (N n))) ((let a (+ n 1)) (set (Out x) a)) :ruleset step)
(rule ((Gate x) (= n (Input x))) ((let b (+ n 3)) (set (Current x) b)) :ruleset step)
{}
(run-schedule (seq (run make) (run step)))
(check (= (Out (N 2)) 3) (= (Current (N 2)) 5))
"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for workers in [1, 4] {
        let mut candidate = executor(&source, workers);
        candidate.execute().unwrap();
        same(&control, &candidate);
        let report = candidate.report();
        let stats = &report["query_workers"]["stats"];
        assert!(report["query_workers"]["matched"]["mixed_invocations"].as_u64().unwrap() > 0, "{report}");
        assert!(stats["answers"].as_u64().unwrap() > 0);
        assert!(report["query_workers"]["matched"]["execution"]["operations"].as_u64().unwrap() > 0);
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 128);
    }
}

#[test]
fn completed_matches_defer_scalar_failure_until_after_the_original_shared_effect() {
    let source = format!(r#"{HEADER}
(rule ((= x (N n)))
 ((let a (+ n 1)) (set (Current x) a) (let b (/ a 0)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
"#, initial());
    let mut control = executor(&source, 0);
    let error = control.execute().unwrap_err();
    for workers in [1, 4] {
        let mut candidate = executor(&source, workers);
        candidate.use_cell_execution(1).unwrap();
        assert_eq!(candidate.execute().unwrap_err(), error);
        assert_eq!(candidate.graph.export().unwrap(), control.graph.export().unwrap());
        let report = candidate.report();
        assert_eq!(report["query_workers"]["matched"]["execution"]["later_deferred_failures"], 64);
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 1,
            "speculation for later bindings must not count as consumed work");
    }
}

#[test]
fn accepted_matches_keep_captured_scalars_when_an_earlier_rhs_deletes_their_source() {
    let source = format!(r#"{HEADER}
(rule ((= x (N n))) ((delete (N n))) :ruleset step)
(rule ((= x (N n))) ((let a (+ n 1)) (F x a) (set (Out x) a)) :ruleset step)
{}
(run-schedule (run step))
"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for workers in [1, 4] {
        let mut candidate = executor(&source, workers);
        candidate.execute().unwrap();
        same(&control, &candidate);
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 64,
            "deleting an earlier witness must not cancel accepted source-Run bindings");
        assert!(candidate.report()["query_workers"]["matched"]["execution"]["operations"]
            .as_u64().unwrap() >= 64);
    }
}

#[test]
fn worker_query_continues_into_owned_slots_and_keeps_run_snapshot() {
    let source = format!(
        r#"{HEADER}
(rule ((Start x) (= n (Input x))) ((set (Input x) 1000)) :ruleset step)
(rule ((Start x) (= n (Input x))) ((let a (+ n 1)) (let b (* a 2)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
(check (= (Input (N 2)) 1000) (= (Out (N 2)) 6))
(run-schedule (run step))
(check (= (Out (N 2)) 2002))
"#,
        initial()
    );
    egglog::EGraph::default()
        .parse_and_run_program(None, &source)
        .unwrap();
    let mut before = executor(&source, 0);
    before.execute().unwrap();
    for workers in [1, 2, 4] {
        let mut after = executor(&source, workers);
        after.execute().unwrap();
        same(&before, &after);
        let r = after.report();
        let work = &r["query_workers"]["stats"]["execution"];
        assert!(work["operations"].as_u64().unwrap() > 0, "{r}");
        assert!(
            after.graph.stats.prepared_rhs_operations > 0,
            "prepared work must remove RHS execution"
        );
        assert!(work["operations"].as_u64().unwrap() >= after.graph.stats.prepared_rhs_operations);
        assert_eq!(
            work["frame_growths"], 0,
            "Bake reserves local results when query slots are allocated"
        );
        if workers > 1 {
            assert!(
                r["query_workers"]["stats"]["worker_local_operations"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_u64().unwrap())
                    .sum::<u64>()
                    > 0
            );
        }
    }
}

#[test]
fn constructor_boundary_consumes_prepared_values_without_replay() {
    let source = format!(
        r#"{HEADER}
(rule ((Start x)) ((set (Current x) 9)) :ruleset step)
(rule ((Start x) (= n (Input x)))
 ((let a (+ n 1)) (F x a) (let b (+ a 9)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
(check (= (Out (N 2)) 12) (F (N 2) 3))
"#,
        initial()
    );
    egglog::EGraph::default()
        .parse_and_run_program(None, &source)
        .unwrap();
    let mut a = executor(&source, 0);
    a.execute().unwrap();
    let mut b = executor(&source, 4);
    b.execute().unwrap();
    same(&a, &b);
    assert!(b.graph.stats.prepared_rhs_operations > 0);
    assert_eq!(b.graph.stats.prepared_rhs_later_operations, 64);
    assert_eq!(b.report()["query_workers"]["stats"]["execution"]["later_operations"], 64);
    assert_eq!(b.report()["query_workers"]["stats"]["execution"]["frame_growths"], 0);
    let plan = artifact(&source)["cell_execution"].to_string();
    assert!(plan.contains("Constructor") && plan.contains("Write"));
}

#[test]
fn speculative_failure_stays_at_original_rhs_position() {
    let source = format!(
        r#"{HEADER}
(rule ((Start x)) ((set (Current x) 9)) :ruleset step)
(rule ((Start x) (= n (Input x)))
 ((let a (+ n 1)) (let b (/ a 0)) (set (Out x) b)) :ruleset step)
{}
(run-schedule (run step))
"#,
        initial()
    );
    let mut a = executor(&source, 0);
    let ea = a.execute().unwrap_err();
    let mut b = executor(&source, 4);
    let eb = b.execute().unwrap_err();
    assert_eq!(ea, eb);
    assert!(ea.contains("RHS primitive failed"), "{ea}");
    assert_eq!(
        a.graph.export().unwrap(),
        b.graph.export().unwrap(),
        "all and only earlier effects survive"
    );
    assert!(
        b.report()["query_workers"]["stats"]["execution"]["deferred_failures"]
            .as_u64()
            .unwrap()
            > 0
    );
}

#[test]
fn loader_reconstructs_dependency_cuts_from_source() {
    let source = format!(
        r#"{HEADER}
(rule ((Start x) (= n (Input x))) ((let a (+ n 1)) (set (Out x) a)) :ruleset step)
{} (run-schedule (run step))"#,
        initial()
    );
    let mut encoded = artifact(&source);
    assert_eq!(
        encoded["cell_execution"]["schema"],
        "cell-execution-boundaries/v2"
    );
    Program::parse(encoded.clone()).unwrap();
    let mut legacy = encoded.clone();
    legacy["cell_execution"]["schema"] = "cell-execution-boundaries/v1".into();
    for rule in legacy["cell_execution"]["rules"].as_array_mut().unwrap() {
        rule.as_object_mut().unwrap().remove("input_ready");
    }
    Program::parse(legacy).unwrap();
    let mut forged = encoded.clone();
    forged["cell_execution"]["rules"][0]["input_ready"] = serde_json::json!([1]);
    assert!(Program::parse(forged).err().unwrap().contains("execution boundaries"));
    encoded["cell_execution"]["rules"][0]["segments"][0]["end"] = serde_json::json!(99999);
    assert!(
        Program::parse(encoded)
            .err()
            .unwrap()
            .contains("execution boundaries")
    );
}

#[test]
fn real_publication_preserves_each_run_through_foreign_reuse_union_and_recreation() {
    let source = format!(
        r#"{HEADER}
(datatype Gated (Gate E))
(ruleset make) (ruleset consume) (ruleset publish) (ruleset join) (ruleset remove) (ruleset again)
(rule ((Start x)) ((Gate x)) :ruleset make)
(rule ((Gate x) (= n (Input x))) ((let a (+ n 1)) (F x a) (let b (+ a 0)) (F x b)) :ruleset consume)
(rule ((= f (F x n))) ((set (Out x) n)) :ruleset publish)
(rule () ((union (N 0) (N 1))) :ruleset join)
(rule () ((delete (F (N 3) 4))) :ruleset remove)
(rule () ((set (Input (N 3)) 9)) :ruleset again)
{} (F (N 0) 1)
(run-schedule (seq (run make) (run consume) (run publish) (run join)
 (run consume) (run publish) (run remove) (run again) (run consume) (run publish)))
(check (= (Out (N 3)) 10))
"#,
        initial()
    );
    egglog::EGraph::default()
        .parse_and_run_program(None, &source)
        .unwrap();
    let create = |workers| {
        let mut e = Executor::new(
            Graph::new_with_repair_ports(Program::parse(artifact(&source)).unwrap()).unwrap(),
            false,
        );
        e.use_entry_publications().unwrap();
        if workers > 0 {
            e.use_query_workers(workers, 8).unwrap();
            e.use_cell_execution(1).unwrap();
            #[cfg(feature = "parallel-residuals")]
            e.use_parallel_residuals().unwrap();
        }
        e
    };
    let mut a = create(0);
    let mut b = create(4);
    for step in 1..=10 {
        a.execute_until(Some(step)).unwrap();
        b.execute_until(Some(step)).unwrap();
        assert_eq!(a.steps.len(), step);
        assert_eq!(b.steps.len(), step);
        assert_eq!(
            a.graph.export().unwrap(),
            b.graph.export().unwrap(),
            "real publication after Run {step}"
        );
        for key in ["epoch", "logical_matches", "executed_bindings", "changed"] {
            assert_eq!(a.steps[step - 1][key], b.steps[step - 1][key]);
        }
    }
    a.execute().unwrap();
    b.execute().unwrap();
    assert!(b.graph.stats.prepared_rhs_operations > 0);
    assert!(b.graph.stats.prepared_rhs_later_operations > 0);
    assert!(
        b.report()["entry_schedule"]["stats"]["entry_publication_writes"]
            .as_u64()
            .unwrap()
            > 0,
        "this test must exercise actual owned Entry publication"
    );
}

#[test]
fn prepared_later_results_survive_union_and_publication_without_worker_round_trips() {
    let source = format!(
        r#"{HEADER}
(ruleset observe)
(rule ((Start x) (= n (Input x)))
 ((let a (+ n 1)) (let f (F x a)) (let b (* a 2))
  (union f x) (let c (+ b 3)) (F f c) (set (Out x) c)) :ruleset step)
(rule ((= f (F x n))) ((set (Current f) n)) :ruleset observe)
{} (F (N 0) 1)
(run-schedule (seq (run step) (run observe)))
(check (= (Out (N 2)) 9) (= (F (N 2) 3) (N 2)))
"#,
        initial()
    );
    egglog::EGraph::default()
        .parse_and_run_program(None, &source)
        .unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for (workers, grain) in [(1, 1), (2, 1), (4, 1), (4, 64)] {
        let mut candidate = executor(&source, workers);
        candidate.use_cell_execution(grain).unwrap();
        candidate.execute().unwrap();
        same(&control, &candidate);
        let report = candidate.report();
        let counts = &report["cell_execution"]["runtime"]["stats"];
        assert_eq!(counts["local_operations"], 0);
        assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 128);
        assert!(
            counts["boundaries"][3].as_u64().unwrap() > 0,
            "union remains a real boundary"
        );
        assert_eq!(
            candidate.graph.stats.union_requests,
            control.graph.stats.union_requests
        );
        assert_eq!(counts["worker_operations"], 0);
        assert_eq!(counts["worker_segments"], 0);
    }
}

#[test]
fn boundary_scalar_result_resumes_with_private_constructor_and_writer_owners() {
    for prefix in ["", "(F x n)", "(set (Input x) (+ n 100))"] {
        let source = format!(r#"{HEADER}
(function Flag (E) bool :merge new)
(rule ((Start x) (= n (Input x)))
 ({prefix} (let a (bool-< n 1000)) (let b (and a true)) (F x (+ n 1)) (set (Flag x) b)) :ruleset step)
{} (run-schedule (run step)) (check (= (Flag (N 2)) true))"#, initial());
        egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
        for ownership in [false,true] {
        let mut control = executor(&source,0);
        if ownership { control.graph.use_cell_ownership().unwrap(); }
        control.execute().unwrap();
        for workers in [2,4] {
            let mut candidate = executor(&source,workers);
            if ownership { candidate.graph.use_cell_ownership().unwrap(); }
            candidate.use_cell_execution(1).unwrap();
            candidate.execute().unwrap();
            same(&control,&candidate);
            let r = candidate.report();
            let work = &r["cell_execution"]["runtime"]["stats"];
            let s = &candidate.graph.stats;
            assert!(s.rhs_context_suspends > 0, "fixture must exercise actual RHS dispatch: {prefix}");
            assert_eq!(work["worker_segments"].as_u64().unwrap(),s.rhs_context_suspends);
            assert_eq!(s.rhs_context_resumes,s.rhs_context_suspends);
            assert_eq!(s.rhs_suspend_holds,s.rhs_suspend_releases);
            if prefix.is_empty() { assert!(s.rhs_suspend_private > 0); }
            else { assert!(s.rhs_suspend_public > 0); }
            if prefix.starts_with("(set") { assert!(s.rhs_suspend_promotions > 0); }
            println!("suspension {}",serde_json::json!({"prefix":prefix,"workers":workers,"ownership":ownership,
                "suspends":s.rhs_context_suspends,"resumes":s.rhs_context_resumes,
                "private":s.rhs_suspend_private,"public":s.rhs_suspend_public,
                "promotions":s.rhs_suspend_promotions,"holds":s.rhs_suspend_holds,
                "releases":s.rhs_suspend_releases,"worker_operations":work["worker_operations"]}));
        }
        }
    }
}

#[test]
fn a_worker_failure_after_a_shared_effect_preserves_the_exact_source_prefix() {
    for tail in [
        "(let b (/ a 0)) (set (Out x) b)",
        "(let b (* a 2)) (panic \"stop\")",
    ] {
        let source = format!(
            r#"{HEADER}
(rule ((Start x) (= n (Input x)))
 ((let a (+ n 1)) (F x a) {tail}) :ruleset step)
{} (run-schedule (run step))
"#,
            initial()
        );
        let mut control = executor(&source, 0);
        let error = control.execute().unwrap_err();
        for workers in [1, 2, 4] {
            let mut candidate = executor(&source, workers);
            candidate.use_cell_execution(1).unwrap();
            assert_eq!(candidate.execute().unwrap_err(), error);
            assert_eq!(
                candidate.graph.export().unwrap(),
                control.graph.export().unwrap()
            );
            assert_eq!(
                candidate.graph.stats.constructor_requests,
                control.graph.stats.constructor_requests
            );
            let report = candidate.report();
            let counts = &report["cell_execution"]["runtime"]["stats"];
            if tail.contains("/ a") {
                assert_eq!(counts["failures"], 1);
            } else {
                assert!(counts["boundaries"][5].as_u64().unwrap() > 0);
            }
        }
    }
}

#[test]
fn query_prepares_later_scalar_chains_without_an_initial_prefix_or_worker_round_trip() {
    let source = format!(r#"{HEADER}
(rule ((Start x) (= n (Input x)))
 ((F x n) (let a (+ n 1)) (let b (* a 2)) (set (Out x) b)) :ruleset step)
{} (run-schedule (run step)) (check (= (Out (N 2)) 6))"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for workers in [1, 2, 4] {
        for resume in [false, true] {
            let mut candidate = executor(&source, workers);
            if resume { candidate.use_cell_execution(1).unwrap(); }
            candidate.execute().unwrap();
            same(&control, &candidate);
            assert_eq!(candidate.graph.stats.prepared_rhs_operations, 0);
            assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 128);
            let r = candidate.report();
            assert_eq!(r["query_workers"]["stats"]["execution"]["later_operations"], 128);
            assert_eq!(r["query_workers"]["stats"]["execution"]["frame_growths"], 0);
            if resume {
                assert_eq!(r["cell_execution"]["runtime"]["stats"]["worker_segments"], 0);
                assert_eq!(r["cell_execution"]["runtime"]["stats"]["local_operations"], 0);
            }
        }
    }
}

#[test]
fn early_visibility_stop_discards_prepared_results_and_does_not_raise_future_errors() {
    for tail in ["(let a (+ n 1))", "(let a (/ n 0))"] {
        let source = format!(r#"{HEADER}
(rule ((Start x) (= n (Input x)))
 ((F x n) (delete (F x 1000)) {tail} (set (Out x) a)) :ruleset step)
{} (run-schedule (run step))"#, initial());
        let mut control = executor(&source, 0);
        control.execute().unwrap();
        let mut candidate = executor(&source, 4);
        candidate.use_cell_execution(1).unwrap();
        candidate.execute().unwrap();
        same(&control, &candidate);
        assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 0);
        let r = candidate.report();
        let prepared = &r["query_workers"]["stats"]["execution"];
        if tail.contains('/') {
            assert_eq!(prepared["later_deferred_failures"], 64);
        } else { assert_eq!(prepared["later_operations"], 64); }
        assert_eq!(r["cell_execution"]["runtime"]["stats"]["failures"], 0);
    }
}

#[test]
fn a_single_write_consumes_prepared_slots_between_unprepared_primitives() {
    let source = format!(r#"{HEADER}
(function Flag (E) bool :merge old)
(rule ((Start x) (= n (Input x)))
 ((let p (bool-< n 1000)) (let a (+ n 1))
  (let q (bool-< a 1000)) (let both (and p q)) (set (Flag x) both)) :ruleset step)
{} (run-schedule (run step)) (check (= (Flag (N 2)) true))"#, initial());
    egglog::EGraph::default().parse_and_run_program(None, &source).unwrap();
    let mut control = executor(&source, 0);
    control.execute().unwrap();
    for workers in [1, 2, 4] {
        let mut candidate = executor(&source, workers);
        candidate.execute().unwrap();
        same(&control, &candidate);
        assert_eq!(candidate.graph.stats.single_writes, 64);
        assert_eq!(candidate.graph.stats.prepared_rhs_operations, 0);
        assert_eq!(candidate.graph.stats.prepared_rhs_later_operations, 64);
        assert_eq!(candidate.report()["query_workers"]["stats"]["execution"]["later_operations"], 64);
    }
}

#[test]
fn peer_results_resolve_dynamic_aliases_and_all_arguments_before_downstream_keys() {
    let seed=(0..96).map(|n|format!("(N {n})")).collect::<Vec<_>>().join("\n");
    let source=format!(r#"
(datatype E (N i64) (F E) (G E i64) (Pair E E) (Seen E))
(ruleset build) (ruleset read) (ruleset change)
(rule ((= x (N n))) ((let a (F (N 0))) (let p (G a n)) (let q (G a 0))
                    (let r (Pair p q))) :ruleset build)
(rule ((= r (Pair p q))) ((Seen r)) :ruleset read)
(rule ((= x (N n)) (= n 1)) ((union x (N 0))) :ruleset change)
{seed}
(run-schedule (seq (run build) (run read) (run change) (run build) (run read)))
(check (Seen (Pair (G (F (N 0)) 0) (G (F (N 0)) 0))))
"#);
    egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
    let mut control=executor(&source,4);control.execute().unwrap();
    for workers in [2,4] {
        let mut candidate=executor(&source,workers);candidate.use_cell_execution(1).unwrap();
        candidate.execute().unwrap();same(&control,&candidate);
        let r=candidate.report();let stats=&r["cell_execution"]["runtime"]["stats"];
        assert!(stats["scheduler"]["dependency_admissions"].as_u64().unwrap()>0,"{stats}");
        assert_eq!(stats["scheduler"]["dependency_flushes"],0,"{stats}");
        assert!(stats["births"]["result_hits"].as_u64().unwrap()>0,"{stats}");
        assert_eq!(stats["births"]["evaluations"].as_u64().unwrap(),
            stats["births"]["shared_slots"].as_u64().unwrap()+stats["births"]["duplicate_evaluations"].as_u64().unwrap());
        assert_eq!(candidate.graph.stats.constructor_requests,control.graph.stats.constructor_requests);
        assert_eq!(candidate.graph.stats.constructor_reused,control.graph.stats.constructor_reused);
        assert_eq!(candidate.graph.stats.logical_facts_created,control.graph.stats.logical_facts_created);
    }
}
