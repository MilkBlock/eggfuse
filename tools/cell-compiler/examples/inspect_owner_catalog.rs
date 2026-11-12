//! Export checked owner layout coordinates for offline trace analysis only.
use eggfuse_cell_runtime::program::Program;
use serde_json::{Value,json};
use std::fs;
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=2 {return Err("usage: inspect_owner_catalog PROGRAM OUTPUT".into());}
    let raw:Value=serde_json::from_slice(&fs::read(&args[0])?)?;
    let mut p=Program::parse(raw)?;p.prepare_cell_ownership()?;
    let plan=&p.cell_ownership.composition;
    let report=json!({"scope":"checked compile-time owner coordinates; no workload execution",
        "program_sha256":p.artifact["sha256"],"entries":p.cell_ownership.entries,
        "active_rules":plan.active_rules,"max_frames":plan.max_frames,
        "fragments":plan.fragments,"transitions":plan.transitions,
        "shapes":plan.shapes.iter().map(|s|json!({"programs":s.programs,"ports":s.ports})).collect::<Vec<_>>()});
    fs::write(&args[1],serde_json::to_vec_pretty(&report)?)?;
    Ok(())
}
