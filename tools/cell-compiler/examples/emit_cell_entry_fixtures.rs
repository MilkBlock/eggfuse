//! Emit the same short Cell Entry cases used by the differential tests, for
//! frozen-runtime work/allocation comparisons. Does not benchmark or train.
#[path = "../tests/support/cell_entry.rs"]
mod fixture;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args().nth(1).ok_or("expected output directory")?;
    let path = std::path::Path::new(&path);
    std::fs::create_dir_all(path)?;
    for (name, source) in [("reused", fixture::SOURCE.to_owned()),
                           ("replaced", fixture::replaced_source()),
                           ("borrowed", fixture::borrowed_source()),
                           ("full", fixture::full_source())] {
        let program = fixture::program(&source);
        std::fs::write(path.join(format!("{name}.egg")), source)?;
        std::fs::write(path.join(format!("{name}.json")), serde_json::to_vec_pretty(&program.artifact)?)?;
    }
    Ok(())
}
