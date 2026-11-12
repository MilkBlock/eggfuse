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
    let expanded=rows.iter().map(|r| if r["result"]["kind"]=="opaque" {
        json!({"normalization":"opaque-source-contract","ordered_source":r["path"]})
    } else {r["result"]["structure"].clone()}).collect::<Vec<_>>();
    let mut shared=expanded.clone();
    let stage_occurrences=shared.iter().map(|s|s["stages"].as_array().map_or(0,Vec::len)).sum::<usize>();
    let stages=eggfuse_cell_runtime::cell_completion::share_stages(&mut shared);
    for (before,after) in expanded.iter().zip(&shared) {
        assert_eq!(Some(before.clone()),eggfuse_cell_runtime::cell_completion::expand_stages(after,&stages));
    }
    let entries=rows.iter().enumerate().map(|(id,r)|json!({"unit":id,"class":id,"source_path":r["path"]})).collect::<Vec<_>>();
    let before=json!({"schema":"eggfuse-constructor-completion-contracts/v1",
        "recipe":review["recipe_sha256"],"structures":expanded,"implementations":entries,"transitions":[]});
    let mut after=before.clone();after["structures"]=json!(shared);after["stage_structures"]=json!(stages);
    let old_registry=eggfuse_bake::native_analyze::register_cpu_completion_structures(&before)?;
    let new_registry=eggfuse_bake::native_analyze::register_cpu_completion_structures(&after)?;
    assert_eq!(old_registry["eclasses"],new_registry["eclasses"]);
    assert_eq!(old_registry["units"],new_registry["units"]);
    let bytes=|value:&Value|serde_json::to_vec(value).unwrap().len();
    let compression=json!({"roundtrip_exact":true,"native_partition_unchanged":true,
        "stage_occurrences":stage_occurrences,"unique_stages":stages.len(),
        "contracts_bytes_before":bytes(&before),"contracts_bytes_after":bytes(&after),
        "structure_bytes_before":bytes(&before["structures"]),
        "structure_bytes_after_with_pool":bytes(&json!({"structures":after["structures"],"stage_structures":after["stage_structures"]})),
        "descriptor_key_bytes_before":old_registry["descriptor_key_bytes"],
        "descriptor_key_bytes_after":new_registry["descriptor_key_bytes"],
        "stage_pool_bytes":bytes(&after["stage_structures"]),"eclasses":new_registry["eclasses"],
        "scope":"compiler representation and native registry key payload; not runtime heap or speed"});
    let result=json!({"scope":"saved trace structural analysis, no workload execution or speed claim",
        "counts":counts,"prior_set_rejection_counts":prior_counts,"supported_classes":classes.len(),"compression":compression,"paths":rows});
    fs::write(&args[2],serde_json::to_vec_pretty(&result)?)?;
    println!("{}",compression);
    Ok(())
}
