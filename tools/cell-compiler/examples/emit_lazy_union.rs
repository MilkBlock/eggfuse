//! Small checked input for the parameterized union experiment; no timing.
#[path = "emit_cell_retention.rs"]
mod fixture;
fn main() -> Result<(),Box<dyn std::error::Error>> {
    let output=std::path::PathBuf::from(std::env::args().nth(1).ok_or("output directory required")?);
    let source=include_str!("../tests/fixtures/lazy-union.egg");
    egglog::EGraph::default().parse_and_run_program(None,source)?;
    fixture::emit(source,&output)
}
