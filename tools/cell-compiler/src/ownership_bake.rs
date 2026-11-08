//! Emit rechecked entry/body ownership markers without executing a workload.
use crate::Result;
use eggfuse_cell_runtime::{checksum::artifact_digest, program::Program};
use serde_json::json;
use std::{fs, path::Path};
pub(crate) fn run(args: Vec<String>) -> Result<()> {
    if args.iter().any(|s| s == "--help") {
        println!("bake-cell-ownership --program FILE --output NEW_DIR");
        return Ok(());
    }
    let opts = super::options(args.into_iter(), &["--program", "--output"])?;
    let p = Program::parse(super::read(Path::new(
        opts.get("--program").ok_or("--program required")?,
    ))?)?;
    let out = Path::new(opts.get("--output").ok_or("--output required")?);
    let markers = p.cell_ownership.artifact(&p);
    let mut raw = p.artifact.clone();
    raw.as_object_mut().unwrap().remove("sha256");
    raw["ownership_markers"] = markers.clone();
    raw["sha256"] = artifact_digest(&raw).into();
    let checked = Program::parse(raw)?;
    fs::create_dir(out)?;
    super::write(&out.join("program.json"), &checked.artifact)?;
    super::write(&out.join("markers.json"), &markers)?;
    super::write(
        &out.join("coverage.json"),
        &json!({"scope":"typed compiler coverage, no workload execution or timing",
        "templates":p.cell_ownership.markers.len(),"covered_bodies":p.cell_ownership.markers.iter().map(|m|m.bodies.iter().filter(|x|**x).count()).sum::<usize>(),
        "covered_tables":p.cell_ownership.tables.iter().filter(|x|**x).count(),"entry_ports":p.cell_ownership.entries.iter().map(Vec::len).sum::<usize>()}),
    )?;
    Ok(())
}
