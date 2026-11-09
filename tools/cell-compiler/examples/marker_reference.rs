//! Native semantic reference for source marker experiments; not a timing lane.
use std::{env, fs};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let [source, output] = args.as_slice() else {
        return Err("expected SOURCE.egg OUTPUT.json".into());
    };
    let text = fs::read_to_string(source)?;
    egglog::EGraph::set_num_threads(1);
    let mut eg = egglog::EGraph::default();
    eggfuse_bake::structural_key::source::install(&mut eg, &text)?;
    eg.parse_and_run_program(Some(source.clone()), &text)?;
    let rows = eg.device_snapshot().map_err(std::io::Error::other)?;
    fs::write(
        output,
        serde_json::to_vec(&serde_json::json!({"rows":rows,"anchors":[]}))?,
    )?;
    Ok(())
}
