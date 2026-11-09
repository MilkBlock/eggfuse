//! Reconstruct all compiler-owned plans from a frozen program's original typed
//! source. Attached learned catalogs remain separately validated by the loader.
use eggfuse_cell_runtime::{checksum::artifact_digest, compiler, program::Program};
use serde_json::{Value, json};
use std::{collections::BTreeSet, env, fs};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let [input, output] = args.as_slice() else {
        return Err("expected PROGRAM OUTPUT.json".into());
    };
    let raw: Value = serde_json::from_slice(&fs::read(input)?)?;
    let markers = serde_json::from_value::<BTreeSet<String>>(raw["marker_tables"].clone())?;
    let rebuilt = compiler::compile(raw["source_core"].clone(), &markers)?;
    let mut checked = Vec::new();
    for (name, value) in rebuilt.as_object().ok_or("compiler artifact")? {
        if name == "sha256" {
            continue;
        }
        if raw.get(name) != Some(value) {
            return Err(format!("re-lowered component differs: {name}").into());
        }
        checked.push(json!({"component":name,"sha256":artifact_digest(value)}));
    }
    let program = Program::parse(raw)?;
    fs::write(
        output,
        serde_json::to_vec_pretty(&json!({
            "status":"pass", "scope":"compiler plans and attached catalog validation; not a runtime semantic or timing check",
            "program_sha256":program.artifact["sha256"], "components":checked,
        }))?,
    )?;
    Ok(())
}
