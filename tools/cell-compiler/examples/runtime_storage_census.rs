//! One actual execution with phase-boundary storage samples; no timing claims.
use eggfuse_cell_runtime::{program::Program,executor::Executor,graph::Graph};
use serde_json::{Value,json};
use std::fs;
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=2 {return Err("usage: runtime_storage_census PROGRAM OUTPUT".into());}
    let raw:Value=serde_json::from_slice(&fs::read(&args[0])?)?;
    let p=Program::parse(raw)?;
    let mut exec=Executor::new(Graph::new_with_local_congruence(p)?,false);
    let initial=exec.graph.retained_cell_storage();let mut samples=vec![];
    loop {
        let n=exec.steps.len();exec.execute_until(Some(n+1))?;
        if exec.steps.len()==n {break;}
        samples.push(json!({"run":exec.steps.len(),"storage":exec.graph.retained_cell_storage()}));
    }
    let output=json!({"scope":"actual Cell runtime; storage census only, not a compression comparison",
        "initial":initial,"final":exec.graph.retained_cell_storage(),"runs":samples,
        "report":exec.report()});
    fs::write(&args[1],serde_json::to_vec_pretty(&output)?)?;
    println!("{}",output["final"]);
    Ok(())
}
