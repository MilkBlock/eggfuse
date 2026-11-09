//! Emit a short versioned ownership fixture and its observed continuations.
//! This is standalone Cell CPU execution, not a timing experiment.
#[path = "../tests/support/port_sharing.rs"]
mod fixture;
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let out = std::path::PathBuf::from(std::env::args().nth(1).ok_or("output directory required")?);
    let core = eggfuse_bake::device_frontend::core("port-sharing", fixture::SOURCE)?;
    let mut p = Program::parse(compiler::compile(core, &Default::default())?)?;
    p.prepare_cell_ownership()?;
    let mut raw = p.artifact.clone();
    raw["ownership_markers"] = p.cell_ownership.artifact(&p);
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = eggfuse_cell_runtime::checksum::artifact_digest(&raw).into();
    let mut g = Graph::new_with_cell_ownership(Program::parse(raw.clone())?)?;
    g.train_ownership_fragments()?;
    let mut e = Executor::new(g, true);
    e.execute()?;
    std::fs::create_dir_all(&out)?;
    std::fs::write(out.join("source.egg"), fixture::SOURCE)?;
    std::fs::write(out.join("program.json"), serde_json::to_vec_pretty(&raw)?)?;
    std::fs::write(out.join("profile.json"), serde_json::to_vec_pretty(&e.graph.ownership_fragment_profile()?)?)?;
    std::fs::write(out.join("state.json"), serde_json::to_vec_pretty(&e.graph.export()?)?)?;
    Ok(())
}
