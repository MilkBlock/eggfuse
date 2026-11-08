//! The first local-union admission trial compares the complete checked family
//! against the existing result-port backend. It does not claim subset convergence.
use crate::{
    Result,
    iterate::{Execution, replay},
    work_credit::Work,
};
use eggfuse_cell_runtime::{
    checksum::artifact_digest, graph::local_union_cells::Plan, program::Program,
};
use serde_json::json;
use std::{fs, path::Path, time::Instant};
pub(crate) fn run(args: Vec<String>) -> Result<()> {
    if args.iter().any(|a| a == "--help") {
        println!(
            "bake-local-unions --program FILE --output NEW_DIR [--entry-publications true|false]"
        );
        return Ok(());
    }
    let opts = super::options(
        args.into_iter(),
        &["--program", "--output", "--entry-publications"],
    )?;
    let p = Program::parse(super::read(Path::new(
        opts.get("--program").ok_or("--program required")?,
    ))?)?;
    let out = Path::new(opts.get("--output").ok_or("--output required")?);
    let owned = opts
        .get("--entry-publications")
        .map(|s| s.parse())
        .transpose()?
        .unwrap_or(false);
    if owned && !cfg!(feature = "sparse-cells") {
        return Err("entry publications require the sparse-cells build".into());
    }
    let config = |local_unions| Execution {
        entry_publications: owned,
        repair_ports: true,
        repair_cells: false,
        local_unions,
    };
    fs::create_dir(out)?;
    let start = Instant::now();
    let (baseline, expected) = replay(p.clone(), false, config(false))?;
    let baseline_seconds = start.elapsed().as_secs_f64();
    let baseline_report = baseline.report();
    let work = Work::read(&baseline_report)?;
    drop(baseline);
    let start = Instant::now();
    let (trial, actual) = replay(p.clone(), false, config(true))?;
    let trial_seconds = start.elapsed().as_secs_f64();
    if actual != expected {
        return Err(
            "local union completion changed graph, schedule, RHS, writes or resumes".into(),
        );
    }
    let report = trial.report();
    let (net, credit) = work.savings(&Work::read(&report)?);
    let selected = Plan::select(&p, net > 0);
    let mut raw = p.artifact.clone();
    raw.as_object_mut().unwrap().remove("sha256");
    raw["local_union_cells"] = selected;
    raw["sha256"] = artifact_digest(&raw).into();
    let final_program = Program::parse(raw)?;
    super::write(&out.join("program.json"), &final_program.artifact)?;
    super::write(&out.join("baseline.json"), &baseline_report)?;
    super::write(&out.join("trial.json"), &report)?;
    super::write(
        &out.join("credit.json"),
        &json!({"policy":"complete-family measured-work","accepted":net>0,
        "work":credit,"semantic_audit":true,"entry_publications":owned,"baseline_replay_and_hash_seconds":baseline_seconds,
        "trial_replay_and_hash_seconds":trial_seconds,"final_state_sha256":expected.0,"schedule_sha256":expected.1,
        "ordered_rhs_sha256":artifact_digest(&json!(expected.2)),"ordered_writes_sha256":artifact_digest(&json!(expected.3)),
        "ordered_resumes_sha256":artifact_digest(&json!(expected.4)),"scope":"standalone Cell CPU; no subset search or held-out validation"}),
    )?;
    eprintln!(
        "local union family: {net} net saved operations; accepted={}",
        net > 0
    );
    Ok(())
}
