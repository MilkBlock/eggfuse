//! Attach a reconstructed/extracted finite state plan to an existing frozen program.
use eggfuse_cell_runtime::{program::Program, checksum::artifact_digest};
use std::{fs, time::Instant};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [input, output, audit] = args.as_slice() else { return Err("expected INPUT OUTPUT AUDIT".into()) };
    let start = Instant::now();
    let mut p = Program::parse(serde_json::from_slice(&fs::read(input)?)?)?;
    let parsed = start.elapsed().as_secs_f64();
    let clock = Instant::now();
    let plan = eggfuse_cell_compiler::state_plan::compile(&p)?;
    let compile = clock.elapsed().as_secs_f64();
    p.artifact["iterative_bake"]["state_plan"] = plan;
    p.artifact.as_object_mut().unwrap().remove("sha256");
    p.artifact["sha256"] = artifact_digest(&p.artifact).into();
    let clock = Instant::now();
    let p = Program::parse(p.artifact)?;
    let validation = clock.elapsed().as_secs_f64();
    fs::write(output, serde_json::to_vec_pretty(&p.artifact)?)?;
    fs::write(audit, serde_json::to_vec_pretty(&serde_json::json!({
        "parse_seconds":parsed,"extract_seconds":compile,"validation_seconds":validation,
        "scope":"one compiler diagnostic invocation; not inference timing"
    }))?)?;
    Ok(())
}
