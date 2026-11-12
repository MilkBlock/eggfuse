//! Keep selected Cell paths, but recompile their receipts after specialization.
use eggfuse_cell_runtime::{compiler,program::Program,iterative::Catalog,checksum::artifact_digest};
use serde_json::json;
use std::{fs,error::Error};
fn main()->Result<(),Box<dyn Error>> {
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    if a.len()!=2 && !(a.len()==3 && a[2]=="--verify-only") {
        return Err("usage: relower_entry_values SOURCE OUTPUT [--verify-only]".into());
    }
    let source=Program::parse(serde_json::from_slice(&fs::read(&a[0])?)?)?;
    if a.len()==3 {
        let target=Program::parse(serde_json::from_slice(&fs::read(&a[1])?)?)?;
        compiler::validate_entry_value_specialization(&source,&target)?;
        println!("{}",json!({"source_specialization_verified":true,"base":source.artifact["sha256"],"candidate":target.artifact["sha256"]}));
        return Ok(());
    }
    let mut raw=compiler::specialize_entry_values(&source)?;
    let old=&source.artifact;
    // This finite migration requires stable rule/slot/query coordinates. Do not
    // reinterpret an old route after rule deduplication or input reordering.
    let before=old["recipe"]["rules"].as_array().ok_or("rules")?;
    let after=raw["recipe"]["rules"].as_array().ok_or("rules")?;
    if before.len()!=after.len() || before.iter().zip(after).any(|(b,a)|
        ["metadata","query","slots"].iter().any(|k|b[k]!=a[k])) {
        return Err("specialization changed Cell coordinates; needs explicit mapping".into());
    }
    // Compilation can discover new ordinary routes unrelated to this rewrite.
    // Keep the previous selection; discard only routes whose required source
    // operation has become a Copy. The target parser rechecks every kept route.
    let removed=raw["entry_value_specialization"]["projections"].as_array().unwrap().iter()
        .map(|p|(p["rule"].as_u64().unwrap(),p["operation"].as_u64().unwrap()))
        .collect::<std::collections::BTreeSet<_>>();
    raw["multi_stage"]=old["multi_stage"].clone();
    raw["multi_stage"]["recipe_sha256"]=raw["recipe"]["sha256"].clone();
    raw["multi_stage"]["routes"].as_array_mut().unwrap().retain(|route| {
        let producer=route["producer"].as_u64().unwrap();
        !removed.contains(&(producer,route["effect"].as_u64().unwrap()))
            && !route["steps"].as_array().unwrap().iter().any(|step|
                step["source_kind"]=="effect" && removed.contains(&(producer,step["source_index"].as_u64().unwrap())))
    });
    raw["spine_blocks"]=old["spine_blocks"].clone();
    raw["spine_blocks"]["recipe_sha256"]=raw["recipe"]["sha256"].clone();
    raw["context_admission"]=old["context_admission"].clone();
    raw["context_admission"]["recipe"]=raw["recipe"]["sha256"].clone();
    let p=Program::parse(raw.clone())?;
    let mut plan=json!({});
    for key in ["schema","limits","joins","producer_roots","matched_entries"] {
        if let Some(v)=old["iterative_bake"].get(key) {plan[key]=v.clone();}
    }
    plan["recipe"]=raw["recipe"]["sha256"].clone();
    plan["seed"]=artifact_digest(&raw["spine_blocks"]).into();
    Catalog::relower_selected(&p,&mut plan,&old["iterative_bake"]["rhs_handoffs"])?;
    if plan["joins"]!=old["iterative_bake"]["joins"] {return Err("selected paths changed".into());}
    raw["iterative_bake"]=plan;
    // Source fragments are a candidate selection. Typed preparation must still
    // validate them, and changed wiring is reported rather than called equal.
    raw["ownership_fragments"]=old["ownership_fragments"].clone();
    raw["ownership_fragments"]["source"]=eggfuse_cell_runtime::graph::cell_ownership::composition::source_digest(&raw).into();
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into();
    let mut p=Program::parse(raw.clone())?;
    compiler::validate_entry_value_specialization(&source,&p)?;
    p.prepare_cell_ownership()?;
    let mut b=source.clone();b.prepare_cell_ownership()?;
    let report=json!({"base":old["sha256"],"candidate":raw["sha256"],
        "ordinary_routes_before":old["multi_stage"]["routes"].as_array().unwrap().len(),
        "ordinary_routes_after":raw["multi_stage"]["routes"].as_array().unwrap().len(),
        "selected_joins":raw["iterative_bake"]["joins"].as_array().unwrap().len(),
        "ownership_shapes_equal":serde_json::to_value(&b.cell_ownership.composition.shapes)?==serde_json::to_value(&p.cell_ownership.composition.shapes)?,
        "ownership_transitions_equal":serde_json::to_value(&b.cell_ownership.composition.transitions)?==serde_json::to_value(&p.cell_ownership.composition.transitions)?,
        "scope":"typed candidate; runtime admission and source-specialization semantic validation still required"});
    fs::write(&a[1],serde_json::to_vec_pretty(&raw)?)?;
    println!("{}",report);
    Ok(())
}
