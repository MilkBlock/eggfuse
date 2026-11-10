//! Reproducible deep Cell chains for history-lifetime work checks, not timing.
use eggfuse_cell_runtime::{checksum::artifact_digest, compiler,
    iterative::{Catalog, Limits}, program::Program};
use serde_json::{Value as J, json};
use std::{fs, path::Path};

pub(crate) fn emit(source: &str, out: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let core = eggfuse_bake::device_frontend::core("retention", source)?;
    let p = Program::parse(compiler::compile(core, &Default::default())?)?;
    let rules = p.artifact["recipe"]["rules"].as_array().unwrap();
    let id = |name| rules.iter().position(|r| r["metadata"]["name"] == name).unwrap();
    let (a, b, c) = (id("producer"), id("bridge"), id("consume"));
    let op = |r: usize, name| rules[r]["effects"].as_array().unwrap().iter()
        .position(|e| e["call"]["table"] == name).unwrap();
    let (gate, mid) = (op(a, "Gateway"), op(b, "Mid"));
    let prefixes = [a,b,c].map(|r| json!({"edge":[0,0,r,0],"visits":2}));
    let profile = json!({"schema":"eggfuse-spine-shapes/v1","program_sha256":p.artifact["sha256"],
        "prefixes":prefixes});
    let blocks = compiler::bake_spine_blocks(&p, &profile, &p, 3)?;
    let entries = blocks["entries"].as_array().unwrap();
    let entry = |rule| entries.iter().position(|e| e["consumer"] == rule).unwrap();
    let joins = json!([{"left":entry(a),"output":gate,"right":entry(b)},
        {"left":entries.len(),"output":mid,"right":entry(c)}]);
    let mut raw = p.artifact;
    raw["spine_blocks"] = blocks;
    let p = Program::parse(raw.clone())?;
    let mut plan = Catalog::seed(&p, Limits::default())?;
    plan["joins"] = joins;
    Catalog::emit_handoffs(&p, &mut plan)?;
    raw["iterative_bake"] = plan;
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = J::String(artifact_digest(&raw));
    Program::parse(raw.clone())?;
    fs::create_dir(out)?;
    fs::write(out.join("source.egg"), source)?;
    fs::write(out.join("program.json"), serde_json::to_vec_pretty(&raw)?)?;
    Ok(())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let out = std::path::PathBuf::from(std::env::args().nth(1).ok_or("output directory required")?);
    let source = include_str!("../tests/fixtures/history-retention.egg");
    emit(&source.replace("(run retire)", ""), &out.join("fixture-chain"))?;
    emit(source, &out.join("fixture-retired"))
}
