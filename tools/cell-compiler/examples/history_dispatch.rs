//! Replay two installed switches against one audited ancestry, without running
//! the workload. Dispatch differences do not certify saved RHS operations.
use eggfuse_cell_runtime::program::Program;
use serde_json::{Value,json};
use std::{error::Error,fs};
fn main()->Result<(),Box<dyn Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=4 {return Err("usage: history_dispatch BASE CANDIDATE AUDITED_TRACE OUTPUT".into());}
    let base=Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let candidate=Program::parse(serde_json::from_slice(&fs::read(&args[1])?)?)?;
    let trace:Value=serde_json::from_slice(&fs::read(&args[2])?)?;
    let history=&trace["completed_history"];
    if trace["all_saved_run_checks_equal"]!=true || history["program_sha256"]!=base.artifact["sha256"]
        || base.artifact["recipe"]!=candidate.artifact["recipe"] {
        return Err("dispatch comparison needs an audited source history and identical source recipes".into());
    }
    let before=base.iterative.describe_history_dispatch(history)?;
    let after=candidate.iterative.describe_history_dispatch(history)?;
    let observed=history["events"].as_array().ok_or("missing events")?;
    let mismatches=before.as_array().unwrap().iter().zip(observed).enumerate()
        .filter_map(|(i,(replayed,event))|(replayed["unit"]!=event["unit"]).then_some(i)).collect::<Vec<_>>();
    let mut changes=vec![];
    let mut direct_before=0;let mut direct_after=0;
    for (a,b) in before.as_array().unwrap().iter().zip(after.as_array().unwrap()) {
        direct_before+=usize::from(!a["transfer"]["direct"].is_null());
        direct_after+=usize::from(!b["transfer"]["direct"].is_null());
        if a["transfer"]!=b["transfer"] {changes.push(json!({"event":a["event"],"entry":a["entry"],"before":a,"after":b}));}
    }
    fs::write(&args[3],serde_json::to_vec_pretty(&json!({
        "scope":"offline switch replay; not runtime hits, witness validation or saved work",
        "base_program":base.artifact["sha256"],"candidate_program":candidate.artifact["sha256"],
        "events":before.as_array().unwrap().len(),"base_unit_mismatches":mismatches,"direct_plans":[direct_before,direct_after],"changes":changes}))?)?;
    Ok(())
}
