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
        println!("bake-cell-ownership --program FILE [--profile FILE] [--query-classes true|false] [--materialize-markers true|false] --output NEW_DIR");
        return Ok(());
    }
    let opts = super::options(args.into_iter(), &["--program", "--output", "--profile", "--query-classes", "--materialize-markers"])?;
    let classes = match opts.get("--query-classes").map(String::as_str) {
        None | Some("false") => false,
        Some("true") => true,
        _ => return Err("--query-classes must be true or false".into()),
    };
    let materialize = match opts.get("--materialize-markers").map(String::as_str) {
        None | Some("true") => true,
        Some("false") => false,
        _ => return Err("--materialize-markers must be true or false".into()),
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
    let markers = materialize.then(|| p.cell_ownership.artifact(&p));
    let mut raw = p.artifact.clone();
    if opts.get("--query-classes").is_some_and(|s| s == "false") {
        if let Some(fragments) = raw["ownership_fragments"].as_object_mut() {
            fragments.remove("query_classes");
        }
    }
    if classes {
        if raw.get("ownership_fragments").is_none() {
            raw["ownership_fragments"] = json!({"schema":p.cell_ownership.fragment_schema(),
                "source":composition::source_digest(&raw),"fragments":[]});
        }
        raw["ownership_fragments"]["query_classes"] = if materialize {
            p.bake_query_classes()?
        } else {json!(true)};
    }
    raw.as_object_mut().unwrap().remove("sha256");
    if let Some(markers) = &markers {
        raw["ownership_markers"] = markers.clone();
    } else {
        raw.as_object_mut().unwrap().remove("ownership_markers");
        // Keep the checked wiring address version even when no profile was
        // supplied. Source definitions rederive the plan; no repeated plan JSON.
        if raw.get("ownership_fragments").is_none() {
            raw["ownership_fragments"] = json!({"schema":p.cell_ownership.fragment_schema(),
                "source":composition::source_digest(&raw),"fragments":[]});
        }
    }
    raw["sha256"] = artifact_digest(&raw).into();
    let checked = Program::parse(raw)?;
    fs::create_dir(out)?;
    super::write(&out.join("program.json"), &checked.artifact)?;
    if let Some(markers) = &markers { super::write(&out.join("markers.json"), markers)?; }
    super::write(
        &out.join("coverage.json"),
        &json!({"scope":"typed compiler coverage, no workload execution or timing","materialized_markers":materialize,
        "templates":p.cell_ownership.markers.len(),"covered_bodies":p.cell_ownership.markers.iter().map(|m|m.program.fields.iter().filter(|fields|!fields.is_empty()).count()).sum::<usize>(),
        "covered_tables":p.cell_ownership.tables.iter().filter(|x|**x).count(),"entry_ports":p.cell_ownership.entries.iter().map(Vec::len).sum::<usize>(),
        "shared_port_programs":p.cell_ownership.markers.iter().map(|m|std::sync::Arc::as_ptr(&m.program)).collect::<std::collections::BTreeSet<_>>().len(),
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
        println!("profile-cell-ownership --program FILE [--max-frames 2..32] [--extend-catalog true|false] [--observe-catalog true|false] --output NEW_DIR");
        return Ok(());
    }
    let opts = super::options(args.into_iter(), &["--program", "--output", "--max-frames", "--extend-catalog", "--observe-catalog"])?;
    let out = Path::new(opts.get("--output").ok_or("--output required")?);
    if out.exists() {
        return Err("output already exists".into());
    }
    let p = Program::parse(super::read(Path::new(
        opts.get("--program").ok_or("--program required")?,
    ))?)?;
    let mut g = Graph::new_with_cell_ownership(p)?;
    let max_frames = opts.get("--max-frames").map(|s|s.parse::<usize>())
        .transpose().map_err(|_|"--max-frames must be an integer")?
        .unwrap_or(g.program.cell_ownership.composition.max_frames);
    let observe = match opts.get("--observe-catalog").map(String::as_str) {
        None | Some("false") => false,
        Some("true") => true,
        _ => return Err("--observe-catalog must be true or false".into()),
    };
    if observe {
        if opts.get("--extend-catalog").is_some_and(|v|v != "false") { return Err("observation and exploratory extension are separate modes".into()); }
        g.trace_ownership_catalog(max_frames)?;
    } else { match opts.get("--extend-catalog").map(String::as_str) {
        None | Some("false") => g.train_ownership_fragments_with_limit(max_frames)?,
        Some("true") => g.continue_ownership_fragment_training(max_frames)?,
        _ => return Err("--extend-catalog must be true or false".into()),
    } }
    let mut e = Executor::new(g, false);
    e.execute()?;
    let profile = if observe { e.graph.ownership_catalog_trace()? } else { e.graph.ownership_fragment_profile()? };
    let report = e.report();
    fs::create_dir(out)?;
    super::write(&out.join("profile.json"), &profile)?;
    super::write(&out.join("report.json"), &report)?;
    Ok(())
}
