//! Reconstruct settled states from audited history; never execute or install them.
use eggfuse_cell_runtime::{program::Program, cell_completion::describe_settled_path, checksum::canonical};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=3 { return Err("usage: review_settled_history PROGRAM TRACE OUTPUT".into()); }
    let raw:Value=serde_json::from_slice(&fs::read(&args[0])?)?;
    let trace:Value=serde_json::from_slice(&fs::read(&args[1])?)?;
    let h=&trace["completed_history"];
    if trace["all_saved_run_checks_equal"]!=true || h["program_sha256"]!=raw["sha256"]
        || h["dropped_events"]!=0 { return Err("source-bound complete audited history required".into()); }
    let p=Program::parse(raw)?;
    let mut ids=BTreeMap::new(); let mut structures=vec![]; let mut rows=vec![];
    for unit in h["contracts"]["implementations"].as_array().ok_or("missing implementations")? {
        let path=serde_json::from_value::<Vec<(Option<usize>,(usize,Option<usize>))>>(unit["source_path"].clone())?;
        let state=describe_settled_path(&p,&path);
        let class=if state["kind"]=="settled" {
            let key=canonical(&state["structure"],false);
            let next=structures.len();
            Some(*ids.entry(key).or_insert_with(|| {structures.push(state["structure"].clone());next}))
        } else {None};
        rows.push(json!({"unit":unit["unit"],"ordered_class":unit["class"],
            "ordered_normalization":unit.get("normalization").cloned().unwrap_or(json!("flat")),
            "settled_class":class,"ports":state["ports"],"source_path":path}));
    }
    fs::write(&args[2],serde_json::to_vec_pretty(&json!({
        "scope":"compile-only settled state candidates; no runtime state merging",
        "program_sha256":h["program_sha256"],"structures":structures,"implementations":rows}))?)?;
    println!("{} units, {} settled classes",rows.len(),structures.len());
    Ok(())
}
