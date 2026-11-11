#![cfg(feature = "parallel-residuals")]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
fn run(source:&str, workers:usize, enabled:bool)->Executor {
    let core=eggfuse_bake::device_frontend::core("parallel-residuals",source).unwrap();
    let program=Program::parse(compiler::compile(core,&Default::default()).unwrap()).unwrap();
    let mut e=Executor::new(Graph::new_with_repair_ports(program).unwrap(),true);
    e.use_entry_publications().unwrap();
    if workers>0 {e.use_query_workers(workers,8).unwrap();}
    if enabled {e.use_parallel_residuals().unwrap();}
    e.execute().unwrap();e
}
#[test]
fn complete_expansions_preserve_order_late_inputs_mutation_and_visibility() {
    let mut s=String::from(r#"
(datatype E (N i64) (Start E) (Wrap i64 E))
(function Cost (E) i64 :merge new)
(function Out (E i64) i64 :merge new)
(ruleset read) (ruleset change) (ruleset late) (ruleset join) (ruleset remove) (ruleset again)
(rule ((Start x) (Wrap i x) (= c (Cost x))) ((set (Out x i) c)) :ruleset read)
(rule ((Start x)) ((set (Cost x) 2)) :ruleset change)
(rule () ((Wrap 7 (N 120))) :ruleset late)
(rule () ((union (N 2) (N 122))) :ruleset join)
(rule () ((delete (Wrap 0 (N 3)))) :ruleset remove)
(rule () ((Wrap 0 (N 3))) :ruleset again)
"#);
    for i in 0..128 {
        s.push_str(&format!("(Start (N {i})) (set (Cost (N {i})) 1)\n"));
        if i<64 {s.push_str(&format!("(Wrap 0 (N {i})) (Wrap 1 (N {i}))\n"));}
    }
    s.push_str(r#"
(run-schedule (seq (run read) (run change) (run read) (run late) (run read)
 (run join) (run read) (run remove) (run read) (run again) (run read)))
(check (= (Out (N 120) 7) 2) (= (Out (N 122) 0) 2) (= (Out (N 3) 0) 2))
"#);
    egglog::EGraph::default().parse_and_run_program(None,&s).unwrap();
    let before=run(&s,0,false);
    for workers in [1,2,4] {
        let after=run(&s,workers,true);
        assert_eq!(before.snapshots,after.snapshots,"every Run state and visibility");
        assert_eq!(before.binding_audit,after.binding_audit,"ordered successful matches");
        assert_eq!(before.steps.len(),after.steps.len());
        for(a,b) in before.steps.iter().zip(&after.steps) {
            for k in ["epoch","ruleset","path","iterations","logical_matches","executed_bindings","changed"] {
                assert_eq!(a[k],b[k],"{k}");
            }
        }
        let r=after.report();let stats=&r["query_workers"]["residual_expansion"]["stats"];
        assert!(stats["entries"].as_u64().unwrap()>0,"{stats}");
        assert!(stats["expansion_rows"].as_u64().unwrap()>0,"{stats}");
        assert!(stats["direct_entries"].as_u64().unwrap()>0,"must omit Seed/domain handoffs");
        assert!(stats["filter_probes"].as_u64().unwrap()>0,"filter and query execute together");
        for key in ["probes", "rejected", "per_rule"] {
            assert_eq!(r["sieve"]["stats"][key],before.report()["sieve"]["stats"][key],"same necessary filters: {key}");
        }
        assert!(r["free_join"]["entry_probes"].as_u64().unwrap()<before.report()["free_join"]["entry_probes"].as_u64().unwrap());
        if workers>1 { assert!(stats["worker_rows"].as_array().unwrap().iter().map(|v|v.as_u64().unwrap()).sum::<u64>()>0); }
    }
}

#[test]
fn function_expansion_reads_current_values_after_delete_and_recreation() {
    let mut s=String::from(r#"
(function Start (i64) i64 :merge new)
(function Link (i64 i64) i64 :merge new)
(function Out (i64 i64) i64 :merge new)
(ruleset start) (ruleset read) (ruleset change) (ruleset remove) (ruleset again)
(rule ((= v (Link x 1))) ((set (Start x) 1)) :ruleset start)
(rule ((= g (Start x)) (= v (Link x y))) ((set (Out x y) v)) :ruleset read)
(rule ((= g (Start x))) ((set (Link x 0) 2) (set (Start x) 2)) :ruleset change)
(rule () ((delete (Link 3 0))) :ruleset remove)
(rule () ((set (Link 3 0) 5)) :ruleset again)
"#);
    // A later Run creates the Entry, so it owns enumeration of the older Link
    // rows independently of the bootstrap compiler's table write ordering.
    for i in 0..128 {s.push_str(&format!("(set (Link {i} 0) 1) (set (Link {i} 1) 9)\n"));}
    s.push_str(r#"
(run-schedule (seq (run start) (run read) (run change) (run read) (run remove) (run read) (run again) (run read)))
(check (= (Out 3 0) 5) (= (Out 4 0) 2) (= (Out 4 1) 9))
"#);
    egglog::EGraph::default().parse_and_run_program(None,&s).unwrap();
    let before=run(&s,0,false);
    let after=run(&s,4,true);
    assert_eq!(before.snapshots,after.snapshots);
    assert_eq!(before.binding_audit,after.binding_audit);
    assert!(after.report()["query_workers"]["residual_expansion"]["stats"]["expansion_rows"].as_u64().unwrap()>0, "{}", after.report()["query_workers"]);
}

#[test]
fn residuals_and_point_cells_share_one_run_snapshot_before_ordered_writes() {
    let mut s=String::from(r#"
(datatype E (N i64) (Start E) (Gate E) (Wrap i64 E))
(function Cost (E) i64 :merge new)
(function Point (E) i64 :merge new)
(function Out1 (E i64) i64 :merge new)
(function Out2 (E i64) i64 :merge new)
(ruleset make) (ruleset consume)
(rule ((Start x)) ((Gate x)) :ruleset make)
(rule ((Gate x) (= c (Cost x)))
      ((set (Cost x) (+ c 10)) (set (Point x) c)) :ruleset consume)
(rule ((Start x) (Wrap i x) (= c (Cost x))) ((set (Out1 x i) c)) :ruleset consume)
(rule ((Start x) (Wrap i x) (= c (Cost x))) ((set (Out2 x i) (+ c 1))) :ruleset consume)
"#);
    for i in 0..64 {
        s+=&format!("(Start (N {i})) (Wrap 0 (N {i})) (Wrap 1 (N {i})) (set (Cost (N {i})) 1)\n");
    }
    s+="(run-schedule (seq (run make) (run consume)))\n";
    for i in 0..64 {
        s+=&format!("(check (= (Point (N {i})) 1) (= (Out1 (N {i}) 0) 1) (= (Out2 (N {i}) 1) 2))\n");
    }
    s+="(run-schedule (run consume))\n";
    for i in 0..64 {
        s+=&format!("(check (= (Point (N {i})) 11) (= (Out1 (N {i}) 1) 11) (= (Out2 (N {i}) 0) 12))\n");
    }
    egglog::EGraph::default().parse_and_run_program(None,&s).unwrap();
    let before=run(&s,0,false);
    for workers in [1,2,4] {
        let after=run(&s,workers,true);
        assert_eq!(before.snapshots,after.snapshots,"no same-Run RHS leakage");
        assert_eq!(before.binding_audit,after.binding_audit,"deterministic winner and expansion order");
        let r=after.report(); let work=&r["query_workers"]["residual_expansion"]["stats"];
        assert!(work["mixed_runs"].as_u64().unwrap()>0,"{r}");
        assert!(work["direct_batches"].as_u64().unwrap()>work["merged_runs"].as_u64().unwrap(),"{work}");
        assert!(r["query_workers"]["stats"]["cross_rule_cells"].as_u64().unwrap()>0);
        assert_eq!(work["queued_row_owners"],work["input_rows"]);
        assert!(work["merge_tasks"].as_u64().unwrap()>0);
        if workers>1 {
            assert!(work["merge_pool_calls"].as_u64().unwrap()>0,"winner sorting must actually reach the pool: {work}");
            assert!(work["merge_worker_rows"].as_array().unwrap().iter().map(|v|v.as_u64().unwrap()).sum::<u64>()>=256);
        } else {
            assert_eq!(work["merge_pool_calls"],0);
        }
    }
}

#[test]
fn active_spine_keeps_owned_entries_and_transfers_uncovered_queries() {
    let mut s=String::from(r#"
(datatype E (N i64) (Gate E) (Start E E) (Pair E E))
(function Cost (E) i64 :merge new)
(function Out (E E) i64 :merge new)
(ruleset make) (ruleset read) (ruleset change) (ruleset join) (ruleset remove) (ruleset again)
(rule ((Start x y)) ((Pair x y)) :ruleset make)
(rule ((Gate x) (Pair x y) (= c (Cost y))) ((set (Out x y) c)) :ruleset read)
(rule ((Gate x) (Start x y)) ((set (Cost y) 2)) :ruleset change)
(rule () ((union (N 0) (N 1))) :ruleset join)
(rule () ((delete (Pair (N 3) (N 131)))) :ruleset remove)
(rule () ((Pair (N 3) (N 131)) (set (Cost (N 131)) 5)) :ruleset again)
"#);
    for i in 0..128 {
        s+=&format!("(Gate (N {i})) (Start (N {i}) (N {})) (set (Cost (N {})) 1)\n",i+128,i+128);
        // The same rule sees both source-produced and bootstrap constructors.
        if i>=64 {s+=&format!("(Pair (N {i}) (N {}))\n",i+128);}
    }
    s+=r#"
(run-schedule (seq (run make) (run read) (run change) (run read) (run join) (run read)
 (run remove) (run read) (run again) (run read)))
(check (= (Out (N 3) (N 131)) 5) (= (Out (N 80) (N 208)) 2))
"#;
    egglog::EGraph::default().parse_and_run_program(None,&s).unwrap();
    let trace=|workers,enabled| {
        #[cfg(feature="iterative-bake")]
        use eggfuse_cell_runtime::transfer_audit as audit;
        #[cfg(feature="iterative-bake")]
        {audit::set_active(true);audit::enable_write_audit();}
        let e=run(&s,workers,enabled);
        #[cfg(feature="iterative-bake")]
        {audit::set_active(false);}
        #[cfg(feature="iterative-bake")]
        let digests=(audit::take_digests(),audit::take_write_digests(),audit::take_resume_digests());
        #[cfg(not(feature="iterative-bake"))]
        let digests=();
        (e,digests)
    };
    let (before,trace_before)=trace(4,false);
    for workers in [1,2,4] {
        let (after,trace_after)=trace(workers,true);
        assert_eq!(before.snapshots,after.snapshots,"every Run and visibility");
        assert_eq!(before.binding_audit,after.binding_audit,"input winners and RHS ordering");
        assert_eq!(trace_before,trace_after,"actual effects and chosen continuation origins");
        let report=after.report();let work=&report["query_workers"]["residual_expansion"]["stats"];
        assert!(work["partitioned_entries"].as_u64().unwrap()>0,"{report}");
        assert!(work["partitioned_admitted"].as_u64().unwrap()>0,"{work}");
        assert!(work["partitioned_answers"].as_u64().unwrap()>0,"{work}");
        assert!(report["stage_spine"]["stats"]["routed_spine_seeds"].as_u64().unwrap()>0,"must retain actual owned continuations");
        let pooled=work["partitioned_worker_entries"].as_array().unwrap().iter().map(|v|v.as_u64().unwrap()).sum::<u64>();
        assert_eq!(pooled+work["partitioned_inline_entries"].as_u64().unwrap(),work["partitioned_entries"].as_u64().unwrap());
        assert_eq!(pooled>0,workers>1,"the newly uncovered queries must reach worker threads");
    }
}
