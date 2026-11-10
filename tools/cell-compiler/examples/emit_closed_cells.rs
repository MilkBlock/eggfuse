//! Emit short, reproducible Cell closure checks; no training or timing.
#[path = "../tests/support/closed_cell.rs"]
mod fixture;
use std::{fs, path::PathBuf};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let out = PathBuf::from(std::env::args().nth(1).ok_or("expected output directory")?);
    for (case, retired, congruence) in [("closed",false,true), ("retired",true,true), ("barrier",false,false)] {
        let source = if retired { fixture::SOURCE.to_owned() } else { fixture::SOURCE.replace("(run retire)", "") };
        let program = fixture::program(&source, congruence);
        let dir = out.join(format!("fixture-{case}"));
        fs::create_dir_all(&dir)?;
        fs::write(dir.join("source.egg"), source)?;
        fs::write(dir.join("program.json"), serde_json::to_vec_pretty(&program.artifact)?)?;
    }
    Ok(())
}
