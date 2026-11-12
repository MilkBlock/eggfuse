//! Recompile conditional closure proofs from a saved, source-bound history.
//! Does not execute the workload or infer truth from application frequency.
use eggfuse_cell_runtime::{cell_completion, program::Program};
use serde_json::Value;
use std::{error::Error, fs};
fn main() -> Result<(), Box<dyn Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=3 {return Err("usage: recheck_closure_history PROGRAM AUDITED_TRACE OUTPUT".into());}
    let p=Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let mut trace:Value=serde_json::from_slice(&fs::read(&args[1])?)?;
    if trace["all_saved_run_checks_equal"]!=true || trace["completed_history"]["program_sha256"]!=p.artifact["sha256"] {
        return Err("history lacks audits or belongs to a different Program".into());
    }
    let paths=trace["completed_history"]["contracts"]["implementations"].as_array()
        .ok_or("missing source paths")?.iter().map(|r| {
            let id=r["unit"].as_u64().ok_or("missing unit")? as usize;
            let path:Vec<(Option<usize>,(usize,Option<usize>))>=serde_json::from_value(r["source_path"].clone())?;
            Ok((id,path))
        }).collect::<Result<std::collections::BTreeMap<_,_>,Box<dyn Error>>>()?;
    for row in trace["completed_history"]["closure_transfers"]["transfers"].as_array_mut().ok_or("missing transfers")? {
        let unit=row["unit"].as_u64().ok_or("missing transfer unit")? as usize;
        let path=paths.get(&unit).ok_or("missing transfer source path")?;
        row["after_source_runs"]=cell_completion::cross_run_closure_transfer(&p,path);
    }
    trace["closure_proof_rechecked_offline"]=Value::Bool(true);
    fs::write(&args[2],serde_json::to_vec_pretty(&trace)?)?;
    Ok(())
}
