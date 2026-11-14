//! Offline catalog preparation from synthetic executions. No GPU runtime policy.
use eggfuse_cell_runtime::{checksum::artifact_digest,compiler,executor::Executor,graph::Graph,iterative::{Catalog,Limits},program::Program};
use serde_json::{Value,json};
use std::{env,fs};
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args=env::args().skip(1).collect::<Vec<_>>();
    let [input,output,report]=args.as_slice() else {return Err("PROGRAM OUTPUT REPORT".into())};
    let raw:Value=serde_json::from_slice(&fs::read(input)?)?;
    let p=Program::parse(raw)?;
    let mut observed=Executor::new(Graph::new(p.clone())?,true);
    observed.execute_until(None)?;
    let profile=observed.spine_shape_report();
    let leaves=compiler::bake_stage_blocks(&p,&profile,&p,32)?;
    let mut raw=p.artifact.clone();raw["spine_blocks"]=leaves.clone();
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into();
    let seed=Program::parse(raw)?;
    let roots=(0..seed.rules.len()).collect::<Vec<_>>();
    let mut plan=Catalog::seed_with_roots(&seed,Limits{support:1,..Default::default()},&roots)?;
    Catalog::emit_query_handoffs(&seed,&mut plan)?;
    let mut raw=seed.artifact.clone();raw["iterative_bake"]=plan.clone();
    raw.as_object_mut().unwrap().remove("sha256");raw["sha256"]=artifact_digest(&raw).into();
    let mut learner=Executor::new(Graph::new(Program::parse(raw)?)?,true);
    learner.collect_iterative_pairs();learner.execute_until(None)?;
    let choices=learner.graph.program.iterative.select(&learner.graph.program,learner.iterative_training());
    plan["joins"]=json!(choices.iter().map(|(j,_)|j).collect::<Vec<_>>());
    Catalog::emit_query_handoffs(&seed,&mut plan)?;
    let mut raw=seed.artifact.clone();raw["iterative_bake"]=plan;
    raw.as_object_mut().unwrap().remove("sha256");raw["sha256"]=artifact_digest(&raw).into();
    let mut candidate=Executor::new(Graph::new(Program::parse(raw.clone())?)?,true);
    candidate.execute_until(None)?;
    if observed.snapshots!=candidate.snapshots || observed.binding_audit!=candidate.binding_audit {
        return Err("catalog changed Run snapshots or ordered matches".into());
    }
    fs::write(report,serde_json::to_vec_pretty(&json!({"profile":profile,"leaves":leaves,"choices":choices,"training":learner.iterative_training().report(),"report":candidate.report(),"run_snapshots_and_bindings_equal":true}))?)?;
    fs::write(output,serde_json::to_vec(&raw)?)?;
    Ok(())
}
