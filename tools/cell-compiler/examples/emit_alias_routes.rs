//! Emit source-alias Cells with existing receipt retention and a residual query.
#[path = "../tests/support/cell_entry.rs"]
mod fixture;
use std::{fs, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = PathBuf::from(std::env::args().nth(1).ok_or("expected OUTPUT_DIRECTORY")?);
    for (case, source) in [("expanded", fixture::aliased_source(fixture::SOURCE)),
        ("retired", fixture::aliased_source(&fixture::replaced_source()))] {
        let directory = root.join(format!("fixture-{case}"));
        fs::create_dir_all(&directory)?;
        let program = fixture::program(&source);
        fs::write(directory.join("source.egg"), &source)?;
        fs::write(directory.join("program.json"), serde_json::to_vec_pretty(&program.artifact)?)?;
    }
    Ok(())
}
