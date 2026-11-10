//! Inspect exact completion obligations and their shared runtime storage.
use eggfuse_cell_runtime::{program::Program, completion_plan::Plan};
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args:Vec<_>=std::env::args().skip(1).collect();
    let [input,output]=args.as_slice() else {return Err("expected PROGRAM OUTPUT".into())};
    let p=Program::parse(serde_json::from_slice(&std::fs::read(input)?)?)?;
    let plan=Plan::derive(&p)?;
    let report=serde_json::json!({"program":p.artifact["sha256"],"storage":plan.demand_storage(),"plan":plan});
    std::fs::write(output,serde_json::to_vec_pretty(&report)?)?;
    Ok(())
}
