//! Inspect exact completion obligations and their shared runtime storage.
use eggfuse_cell_runtime::{program::Program, completion_plan::Plan};
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args:Vec<_>=std::env::args().skip(1).collect();
    let [input,output]=args.as_slice() else {return Err("expected PROGRAM OUTPUT".into())};
    let p=Program::parse(serde_json::from_slice(&std::fs::read(input)?)?)?;
    let plan=Plan::derive(&p)?;
    let influence:Vec<_>=(0..p.tables.len()).map(|a|(0..p.tables.len()).map(|b|plan.affects(a,b)).collect::<Vec<_>>()).collect();
    let waits:Vec<_>=(0..p.tables.len()).map(|t|serde_json::to_value(plan.scope(&[t]).unwrap()).unwrap()).collect();
    let signature=eggfuse_cell_runtime::checksum::artifact_digest(&serde_json::json!({"affects":influence,"singleton_scopes":waits}));
    let report=serde_json::json!({"program":p.artifact["sha256"],"closure_sha256":signature,"storage":plan.demand_storage(),"matrices":plan.matrix_storage(),"table_lists":plan.table_list_storage(),"plan":plan});
    std::fs::write(output,serde_json::to_vec_pretty(&report)?)?;
    Ok(())
}
