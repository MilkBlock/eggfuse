//! Install actual boundary-provenance routes without inventing cursor ancestry.
use eggfuse_cell_runtime::{program::{Program,Op},iterative::Catalog,checksum::artifact_digest};
use serde_json::{Value,json};
use std::{collections::BTreeMap,fs,error::Error};
fn main()->Result<(),Box<dyn Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=5 {return Err("usage: bake_matched_handoffs TARGET TRACE_PROGRAM LINK_REPORT TRACE OUTPUT_DIR".into());}
    let mut raw:Value=serde_json::from_slice(&fs::read(&args[0])?)?;
    let p=Program::parse(raw.clone())?;
    let source:Value=serde_json::from_slice(&fs::read(&args[1])?)?;
    let report:Value=serde_json::from_slice(&fs::read(&args[2])?)?;
    let trace_bytes=fs::read(&args[3])?;
    use sha2::{Digest,Sha256};
    let trace:Value=serde_json::from_slice(&trace_bytes)?;
    if source["sha256"]!=report["program_sha256"] || source["recipe"]!=raw["recipe"]
        || trace["all_saved_run_checks_equal"]!=true || trace["completed_history"]["program_sha256"]!=source["sha256"]
        || report["trace_file_sha256"]!=format!("{:x}",Sha256::digest(&trace_bytes)) {
        return Err("matched routes require exact audited trace, report and identical typed recipes".into());
    }
    let table=p.tables.iter().position(|t|report["table"]==t.name).ok_or("unknown handoff table")?;
    let mut support=BTreeMap::new();
    for link in report["links"].as_array().ok_or("missing links")? {
        let producer=link["producer_rule"].as_u64().ok_or("producer")? as usize;
        let consumer=link["consumer_rule"].as_u64().ok_or("consumer")? as usize;
        let pivot=link["atom"].as_u64().ok_or("pivot")? as usize;
        let ops=p.templates[p.rules[producer].template].ops.iter().enumerate()
            .filter_map(|(op,i)|matches!(i,Op::Set(t,_,_) if *t==table).then_some(op)).collect::<Vec<_>>();
        let [op]=ops.as_slice() else {return Err("producer requires a unique observed table write".into());};
        *support.entry((producer,*op,consumer,pivot)).or_insert(0usize)+=1;
    }
    let routes=support.keys().copied().collect::<Vec<_>>();
    let mut plan=raw["iterative_bake"].clone();
    Catalog::emit_matched_routes(&p,&mut plan,&routes)?;
    raw["iterative_bake"]=plan;
    // Retain the exact selected source fragments as an experimental candidate,
    // rechecking their typed shapes below; runtime admission remains mandatory.
    raw.as_object_mut().unwrap().remove("ownership_markers");
    if raw.get("ownership_fragments").is_some() {
        raw["ownership_fragments"]["source"]=eggfuse_cell_runtime::graph::cell_ownership::composition::source_digest(&raw).into();
    }
    raw.as_object_mut().unwrap().remove("sha256");raw["sha256"]=artifact_digest(&raw).into();
    let mut checked=Program::parse(raw.clone())?;
    let mut before=p.clone();before.prepare_cell_ownership()?;checked.prepare_cell_ownership()?;
    if serde_json::to_value(&before.cell_ownership.composition.shapes)?!=serde_json::to_value(&checked.cell_ownership.composition.shapes)?
        || serde_json::to_value(&before.cell_ownership.composition.transitions)?!=serde_json::to_value(&checked.cell_ownership.composition.transitions)? {
        return Err("matched catalog changed selected ownership wiring".into());
    }
    let output=json!({"base_program":p.artifact["sha256"],"program_sha256":checked.artifact["sha256"],
        "support":support.into_iter().collect::<Vec<_>>(),"selection":raw["iterative_bake"]["matched_route_selection"],
        "contract":"residual query executes normally; boundary provenance selects finite RHS reuse only"});
    fs::create_dir_all(&args[4])?;
    fs::write(format!("{}/program.json",args[4]),serde_json::to_vec_pretty(&raw)?)?;
    fs::write(format!("{}/selection.json",args[4]),serde_json::to_vec_pretty(&output)?)?;
    println!("{}",output);
    Ok(())
}
