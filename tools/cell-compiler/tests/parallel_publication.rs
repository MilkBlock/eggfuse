#![cfg(feature = "parallel-publication")]
use eggfuse_cell_runtime::{compiler,executor::Executor,graph::Graph,program::Program};

fn run(source:&str,workers:usize,publication:bool)->Executor {
    let core=eggfuse_bake::device_frontend::core("parallel-publication",source).unwrap();
    let program=Program::parse(compiler::compile(core,&Default::default()).unwrap()).unwrap();
    let mut e=Executor::new(Graph::new_with_repair_ports(program).unwrap(),true);
    e.use_entry_publications().unwrap();
    if workers>0 {
        e.use_query_workers(workers,16).unwrap();
        e.use_parallel_residuals().unwrap();
    }
    if publication {e.use_parallel_publication().unwrap();}
    e.execute().unwrap();e
}

#[test]
fn repaired_publication_keeps_late_values_aliases_and_retirements() {
    let mut source=String::from(r#"
(datatype E (N i64) (Start E) (Wrap i64 E))
(function Cost (E) i64 :merge (min old new))
(function Out (E i64) i64 :merge new)
(function Echo (E i64) i64 :merge new)
(ruleset see) (ruleset change) (ruleset join) (ruleset remove) (ruleset again)
(rule ((Start x) (Wrap i x) (= c (Cost x))) ((set (Out x i) c)) :ruleset see)
(rule ((= p (Wrap i x)) (= c (Cost x))) ((set (Cost p) (+ c 1)) (set (Echo x i) c)) :ruleset see)
(rule ((Start x)) ((set (Cost x) 2) (Wrap 3 x)) :ruleset change)
(rule ((= x (N i)) (>= i 0) (< i 64) (= j (+ i 128)) (= y (N j))) ((union x y)) :ruleset join)
(rule ((Start x)) ((delete (Wrap 0 x)) (delete (Cost x))) :ruleset remove)
(rule ((Start x)) ((Wrap 0 x) (set (Cost x) 7)) :ruleset again)
"#);
    for i in 0..256 {
        source+=&format!("(Start (N {i})) (Wrap 0 (N {i})) (Wrap 1 (N {i})) (set (Cost (N {i})) 9)\n");
    }
    source+=r#"
(run-schedule (seq (run see) (run change) (run see) (run join) (run see)))
(check (= (Out (N 128) 3) 2) (= (Echo (N 0) 1) 2))
(run-schedule (seq (run remove) (run see) (run again) (run see)))
(check (= (Out (N 0) 0) 7) (= (Echo (N 200) 1) 7))
"#;
    egglog::EGraph::default().parse_and_run_program(None,&source).unwrap();
    let before=run(&source,0,false);
    for workers in [1,2,4] {
        let after=run(&source,workers,true);
        assert_eq!(before.snapshots,after.snapshots,"every Run graph and visibility");
        assert_eq!(before.binding_audit,after.binding_audit,"exact winner and RHS order");
        let (mut a,mut b)=(before.report(),after.report());
        a["publication"].as_object_mut().unwrap().remove("parallel");
        let counts=b["publication"].as_object_mut().unwrap().remove("parallel").unwrap();
        assert_eq!(a["publication"],b["publication"],"one read per published row");
        assert_eq!(a["sieve"]["stats"],b["sieve"]["stats"],"ordered changes and collision invalidation");
        assert!(counts["column_rows"].as_u64().unwrap()>0,"{counts}");
        if workers>1 {
            assert!(counts["pool_calls"].as_u64().unwrap()>0,"{counts}");
            assert!(counts["worker_rows"].as_array().unwrap().iter().filter(|n|n.as_u64().unwrap()>0).count()>1);
        }
    }
}
