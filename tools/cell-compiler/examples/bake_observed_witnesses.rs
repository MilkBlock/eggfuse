//! Install source- and catalog-bound apply observations as checked Cell routes.
//! Runtime key/lifecycle admission remains authoritative; frequency is no proof.
use eggfuse_cell_runtime::{checksum::{artifact_digest, canonical}, graph::cell_ownership::composition,
    program::Program};
use serde_json::{Value, json};
use std::{collections::BTreeSet, error::Error, fs};

fn recipes<'a>(raw: &Value, trace: &'a Value) -> Result<&'a Vec<Value>, String> {
    let observed=&trace["catalog_trace"];
    if trace["all_saved_run_checks_equal"]!=true || trace["runs"].as_u64().is_none_or(|n|n==0)
        || observed["schema"]!="eggfuse-ownership-catalog-trace/v1"
        || observed["catalog_sha256"]!=raw["sha256"]
        || observed["source"]!=composition::source_digest(raw) {
        return Err("matching source, installed catalog and audited Runs required".into());
    }
    observed["saturation"]["witness_recipes"].as_array()
        .ok_or_else(||"missing observed witness recipes".into())
}
fn main() -> Result<(),Box<dyn Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=3 {return Err("usage: bake_observed_witnesses PROGRAM AUDITED_TRACE OUTPUT_DIR".into());}
    let bytes=fs::read(&args[0])?;
    let mut raw:Value=serde_json::from_slice(&bytes)?;
    let trace_bytes=fs::read(&args[1])?;
    let trace:Value=serde_json::from_slice(&trace_bytes)?;
    let observed=recipes(&raw,&trace)?;
    let mut before=Program::parse(raw.clone())?;
    before.prepare_cell_ownership()?;
    // Extend an installed witness language, never discard its checked routes.
    let mut selected=raw.get("ownership_witnesses").map(|w|w["recipes"].as_array()
        .cloned().ok_or("invalid installed recipes")).transpose()?.unwrap_or_default();
    let old=selected.len();
    let mut seen=selected.iter().map(|r|canonical(r,false)).collect::<BTreeSet<_>>();
    for recipe in observed {
        if seen.insert(canonical(recipe,false)) {selected.push(recipe.clone());}
    }
    let count=selected.len();
    raw["ownership_witnesses"]=json!({"source":composition::source_digest(&raw),"recipes":selected});
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into();
    let mut after=Program::parse(raw)?;
    after.prepare_cell_ownership()?; // Typed positions, operators, wiring and key proofs.
    if serde_json::to_value(&before.cell_ownership.composition.shapes)?!=serde_json::to_value(&after.cell_ownership.composition.shapes)?
        || serde_json::to_value(&before.cell_ownership.composition.transitions)?!=serde_json::to_value(&after.cell_ownership.composition.transitions)? {
        return Err("witness installation changed composition wiring".into());
    }
    use sha2::{Digest,Sha256};
    let evidence=json!({"source_program":before.artifact["sha256"],"program_sha256":after.artifact["sha256"],
        "source_file_sha256":format!("{:x}",Sha256::digest(bytes)),
        "trace_file_sha256":format!("{:x}",Sha256::digest(trace_bytes)),
        "source_core_unchanged":before.artifact["source_core"]==after.artifact["source_core"],
        "audited_runs":trace["runs"],"existing_recipes":old,"selected_recipes":count,
        "composition_unchanged":true,"contract":"observations select typed routes; residual queries, exact unproved keys, visibility, generation and ordered effects remain live"});
    fs::create_dir(&args[2])?;
    fs::write(format!("{}/program.json",args[2]),serde_json::to_vec_pretty(&after.artifact)?)?;
    fs::write(format!("{}/selection.json",args[2]),serde_json::to_vec_pretty(&evidence)?)?;
    println!("{evidence}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture()->(Value,Value) {
        let raw=json!({"sha256":"installed-catalog","recipe":{},"ownership_fragments":{"fragments":[]}});
        let trace=json!({"all_saved_run_checks_equal":true,"runs":1,"catalog_trace":{
            "schema":"eggfuse-ownership-catalog-trace/v1","catalog_sha256":raw["sha256"],
            "source":composition::source_digest(&raw),"saturation":{"witness_recipes":[]}}});
        (raw,trace)
    }
    #[test]
    fn requires_audited_runs_and_the_actual_installed_catalog() {
        let (raw,trace)=fixture();assert!(recipes(&raw,&trace).unwrap().is_empty());
        for pointer in ["/all_saved_run_checks_equal","/runs","/catalog_trace/schema",
            "/catalog_trace/source","/catalog_trace/catalog_sha256","/catalog_trace/saturation/witness_recipes"] {
            let mut bad=trace.clone();*bad.pointer_mut(pointer).unwrap()=Value::Null;
            assert!(recipes(&raw,&bad).is_err(),"{pointer}");
        }
        let mut other=raw.clone();other["ownership_fragments"]["fragments"]=json!([{"root":2}]);
        other["sha256"]=json!("another-catalog");
        assert_eq!(composition::source_digest(&raw),composition::source_digest(&other));
        assert!(recipes(&other,&trace).is_err(),"same source alone cannot identify observed shapes");
    }
}
