//! Recompile only the Cell route component of a frozen artifact. All source,
//! other compiler plans and attached Bake decisions must remain unchanged.
use eggfuse_cell_runtime::{checksum::artifact_digest, compiler, program::Program};
use serde_json::{Value, json};
use std::{collections::BTreeSet, fs};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [input, output, audit] = args.as_slice() else {
        return Err("expected OLD_PROGRAM NEW_PROGRAM AUDIT.json".into());
    };
    let mut raw: Value = serde_json::from_slice(&fs::read(input)?)?;
    Program::parse(raw.clone())?; // Old wire addresses still require exact validation.
    let markers = serde_json::from_value::<BTreeSet<String>>(raw["marker_tables"].clone())?;
    let rebuilt = compiler::compile(raw["source_core"].clone(), &markers)?;
    let mut preserved = vec![];
    for (name, component) in rebuilt.as_object().ok_or("compiler artifact")? {
        if matches!(name.as_str(), "sha256" | "multi_stage") { continue; }
        if raw.get(name) != Some(component) { return Err(format!("changed non-route component: {name}").into()); }
        preserved.push(name.clone());
    }
    let before = raw["multi_stage"]["routes"].as_array().ok_or("old routes")?.len();
    raw["multi_stage"] = rebuilt["multi_stage"].clone();
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    let program = Program::parse(raw)?; // Revalidate the unchanged learned catalog too.
    fs::write(output, serde_json::to_vec_pretty(&program.artifact)?)?;
    fs::write(audit, serde_json::to_vec_pretty(&json!({
        "status":"pass", "program_sha256":program.artifact["sha256"],
        "preserved_compiler_components":preserved, "routes_before":before,
        "routes_after":program.artifact["multi_stage"]["routes"].as_array().unwrap().len(),
        "scope":"same source, recipe and Bake decisions; only route compilation changed; not a speed measurement"
    }))?)?;
    Ok(())
}
