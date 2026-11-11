#![cfg(feature = "parallel-entry-filters")]
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};

fn run(source: &str, enabled: bool, workers: usize) -> Executor {
    let core = eggfuse_bake::device_frontend::core("parallel-entry-filters",source).unwrap();
    let program = Program::parse(compiler::compile(core,&Default::default()).unwrap()).unwrap();
    let mut e = Executor::new(Graph::new_with_repair_ports(program).unwrap(),true);
    e.use_entry_publications().unwrap();
    if workers != 0 { e.use_query_workers(workers,1).unwrap(); }
    if enabled { e.use_parallel_entry_filters().unwrap(); }
    e.execute().unwrap(); e
}

#[test]
fn parallel_filters_keep_late_inputs_union_visibility_and_order() {
    let mut source = String::from(r#"
(datatype E (N i64))
(relation Driver (E)) (relation Link (E E)) (relation Live (E)) (relation Seen (E i64))
(function Tick () i64 :merge new)
(ruleset read) (ruleset late) (ruleset join) (ruleset remove) (ruleset again)
(rule ((Driver x) (Link x y) (Live y) (= t (Tick))) ((Seen x t)) :ruleset read)
(rule () ((Live (N 10008)) (set (Tick) 2)) :ruleset late)
(rule () ((union (N 10009) (N 10007)) (set (Tick) 3)) :ruleset join)
(rule () ((delete (Live (N 10007))) (set (Tick) 4)) :ruleset remove)
(rule () ((Live (N 10007)) (set (Tick) 5)) :ruleset again)
(set (Tick) 1) (Live (N 10007))
"#);
    for i in 0..4096 {
        source.push_str(&format!("(Driver (N {i})) (Link (N {i}) (N {}))\n",i+10000));
    }
    source.push_str(r#"
(run-schedule (seq (run read) (run late) (run read) (run join) (run read)
    (run remove) (run read) (run again) (run read)))
(check (Seen (N 7) 1) (Seen (N 8) 2) (Seen (N 9) 3) (Seen (N 8) 4) (Seen (N 7) 5))
"#);
    egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
    let before=run(&source,false,0);
    for workers in [2,4] {
        let after=run(&source,true,workers);
        assert_eq!(before.snapshots,after.snapshots,"every source Run graph and visibility");
        assert_eq!(before.binding_audit,after.binding_audit,"ordered inputs, not only final state");
        assert_eq!(before.steps.len(),after.steps.len());
        for (a,b) in before.steps.iter().zip(&after.steps) {
            for key in ["ordinal","ruleset","path","iterations","epoch","logical_matches","executed_bindings","changed"] {
                assert_eq!(a[key],b[key],"{key}");
            }
        }
        let report=after.report();
        assert_eq!(report["sieve"]["stats"], before.report()["sieve"]["stats"], "same guards once, including failed candidates");
        let stats = &report["sieve"]["parallel"]["stats"];
        assert!(stats["batches"].as_u64().unwrap() > 0, "{stats}");
        assert!(stats["probes"].as_u64().unwrap() > 0, "{stats}");
        assert_eq!(stats["worker_rows"].as_array().unwrap().iter().map(|v|v.as_u64().unwrap()).sum::<u64>(), stats["rows"].as_u64().unwrap());
    }
}
