//! Emit rechecked entry/body ownership markers without executing a workload.
use crate::Result;
use eggfuse_cell_runtime::{
    checksum::artifact_digest,
    executor::Executor,
    graph::{Graph, cell_ownership::composition},
    program::Program,
};
use serde_json::json;
use std::{fs, path::Path};
pub(crate) fn run(args: Vec<String>) -> Result<()> {
    if args.iter().any(|s| s == "--help") {
        println!("bake-cell-ownership --program FILE [--profile FILE] [--query-classes true|false] --output NEW_DIR");
        return Ok(());
    }
    let opts = super::options(args.into_iter(), &["--program", "--output", "--profile", "--query-classes"])?;
    let classes = match opts.get("--query-classes").map(String::as_str) {
        None | Some("false") => false,
        Some("true") => true,
        _ => return Err("--query-classes must be true or false".into()),
    };
    let mut raw = super::read(Path::new(
        opts.get("--program").ok_or("--program required")?,
    ))?;
    if let Some(path) = opts.get("--profile") {
        let profile = super::read(Path::new(path))?;
        if profile["source"] != composition::source_digest(&raw) {
            return Err("ownership profile source differs".into());
        }
        raw.as_object_mut().unwrap().remove("ownership_markers");
        raw["ownership_fragments"] = composition::select_profile(&profile)?;
        raw.as_object_mut().unwrap().remove("sha256");
        raw["sha256"] = artifact_digest(&raw).into();
    }
    let mut p = Program::parse(raw)?;
    p.prepare_cell_ownership()?;
    let out = Path::new(opts.get("--output").ok_or("--output required")?);
    let markers = p.cell_ownership.artifact(&p);
    let mut raw = p.artifact.clone();
    if opts.get("--query-classes").is_some_and(|s| s == "false") {
        if let Some(fragments) = raw["ownership_fragments"].as_object_mut() {
            fragments.remove("query_classes");
        }
    }
    if classes {
        if raw.get("ownership_fragments").is_none() {
            raw["ownership_fragments"] = json!({"schema":"eggfuse-ownership-fragments/v1",
                "source":composition::source_digest(&raw),"fragments":[]});
        }
        raw["ownership_fragments"]["query_classes"] = p.bake_query_classes()?;
    }
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
        "covered_tables":p.cell_ownership.tables.iter().filter(|x|**x).count(),"entry_ports":p.cell_ownership.entries.iter().map(Vec::len).sum::<usize>(),
        "shared_port_programs":p.cell_ownership.markers.iter().map(|m|std::rc::Rc::as_ptr(&m.program)).collect::<std::collections::BTreeSet<_>>().len(),
        "template_signal_steps":p.cell_ownership.markers.iter().flat_map(|m|&m.program.signals).map(Vec::len).sum::<usize>(),
        "composition_initial_shapes":p.cell_ownership.programs.len(),
        "composition_baked_shapes":p.cell_ownership.composition.shapes.len(),
        "composition_transitions":p.cell_ownership.composition.transitions.len(),
        "query_classes":checked.cell_ownership.query_classes.as_ref().map(|p|p.report()),
        "composition_input_sources":p.cell_ownership.composition.sources.iter().map(Vec::len).sum::<usize>()}),
    )?;
    Ok(())
}

/// Explicit training command. Baking itself never executes the input workload.
pub(crate) fn profile(args: Vec<String>) -> Result<()> {
    if args.iter().any(|a| a == "--help") {
        println!("profile-cell-ownership --program FILE --output NEW_DIR");
        return Ok(());
    }
    let opts = super::options(args.into_iter(), &["--program", "--output"])?;
    let out = Path::new(opts.get("--output").ok_or("--output required")?);
    if out.exists() {
        return Err("output already exists".into());
    }
    let p = Program::parse(super::read(Path::new(
        opts.get("--program").ok_or("--program required")?,
    ))?)?;
    let mut g = Graph::new_with_cell_ownership(p)?;
    g.train_ownership_fragments()?;
    let mut e = Executor::new(g, false);
    e.execute()?;
    let profile = e.graph.ownership_fragment_profile()?;
    let report = e.report();
    fs::create_dir(out)?;
    super::write(&out.join("profile.json"), &profile)?;
    super::write(&out.join("report.json"), &report)?;
    Ok(())
}
