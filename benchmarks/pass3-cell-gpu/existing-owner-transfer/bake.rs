use eggfuse_cell_runtime::{
    checksum::artifact_digest,
    compiler,
    executor::Executor,
    graph::{Graph, cell_ownership::composition},
    program::Program,
};
use serde_json::{Value, json};
use std::{collections::BTreeSet, fs, path::Path};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().skip(1).collect();
    let mut raw: Value = if a[0].ends_with(".egg") {
        let core = eggfuse_bake::device_frontend::core(
            "existing-owner-transfer",
            &fs::read_to_string(&a[0])?,
        )?;
        compiler::compile(core, &BTreeSet::new())?
    } else {
        serde_json::from_slice(&fs::read(&a[0])?)?
    };
    let out = Path::new(&a[1]);
    fs::create_dir(out)?;
    fs::write(out.join("original.json"), serde_json::to_vec(&raw)?)?;
    let mut graph = Graph::new_with_cell_ownership(Program::parse(raw.clone())?)?;
    graph.train_ownership_fragments()?;
    let mut train = Executor::new(graph, false);
    train.execute()?;
    let profile = train.graph.ownership_fragment_profile()?;
    raw.as_object_mut()
        .unwrap()
        .remove("cell_ownership_markers");
    let lib = if a[0].ends_with(".egg") {
        json!({"schema":"eggfuse-ownership-fragments/v2","source":profile["source"],"fragments":profile["records"].as_array().unwrap().iter().map(|r|&r["fragment"]).collect::<Vec<_>>()})
    } else {
        composition::select_profile(&profile)?
    };
    raw["ownership_fragments"] = lib.clone();
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"] = artifact_digest(&raw).into();
    let _ = Program::parse(raw.clone())?;
    fs::write(out.join("program.json"), serde_json::to_vec(&raw)?)?;
    fs::write(out.join("catalog.json"), serde_json::to_vec(&lib)?)?;
    println!(
        "{} training observations {} selected {}",
        a[0],
        profile["records"].as_array().unwrap().len(),
        lib["fragments"].as_array().unwrap().len()
    );
    Ok(())
}
