//! Batch structural analysis of saved paths; does not execute the workload.
use eggfuse_cell_runtime::{program::Program, cell_completion::describe_path, checksum::canonical};
use serde_json::{Value,json};
use std::{collections::{BTreeMap,BTreeSet},fs};
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=3 {return Err("usage: review_completion_paths PROGRAM REVIEW_JSON OUTPUT".into());}
    let mut raw:Value=serde_json::from_slice(&fs::read(&args[0])?)?;
    // This tool re-analyzes source paths, not the archived executable catalog.
    // Drop its versioned derived completion certificate, then revalidate source.
    if let Some(plan)=raw.get_mut("iterative_bake").and_then(Value::as_object_mut) {
        plan.remove("completion");
    }
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=eggfuse_cell_runtime::checksum::artifact_digest(&raw).into();
    let p=Program::parse(raw)?;
    let review:Value=serde_json::from_slice(&fs::read(&args[1])?)?;
    if review["recipe_sha256"]!=p.artifact["recipe"]["sha256"] {return Err("different trace recipe".into());}
    let mut counts=BTreeMap::<String,usize>::new();
    let mut prior_counts=BTreeMap::<String,usize>::new();
    let mut classes=BTreeSet::new();let mut rows=vec![];
    for candidate in review["patterns"].as_array().ok_or("missing patterns")? {
        let path=serde_json::from_value::<Vec<(Option<usize>,(usize,Option<usize>))>>(candidate["path"].clone())?;
        let result=describe_path(&p,&path);
        let kind=result["kind"].as_str().unwrap();
        *counts.entry(kind.into()).or_default()+=1;
        // Exact previous admission restriction: normalize rejected every Set,
        // including when called separately on stages by staged_contract.
        let has_set=path.iter().any(|(_, (rid,_))|p.templates[p.rules[*rid].template].ops.iter()
            .any(|op|matches!(op,eggfuse_cell_runtime::program::Op::Set(..))));
        *prior_counts.entry(if has_set {"opaque".into()} else {kind.into()}).or_default()+=1;
        if kind!="opaque" {classes.insert(canonical(&result["structure"],false));}
        rows.push(json!({"path":path,"occurrences":candidate["occurrences"],"result":result}));
    }
    let result=json!({"scope":"saved trace structural analysis, no workload execution or speed claim",
        "counts":counts,"prior_set_rejection_counts":prior_counts,"supported_classes":classes.len(),"paths":rows});
    fs::write(&args[2],serde_json::to_vec_pretty(&result)?)?;
    println!("{}",json!({"counts":counts,"prior_set_rejection_counts":prior_counts,"supported_classes":classes.len()}));
    Ok(())
}
