//! Select real repair templates by complete audited replay, paying their VM,
//! copy and dispatch work. No hit-count or prospective-chain credit is given.
use crate::{
    Result,
    iterate::{Execution, replay},
    work_credit::Work,
};
use eggfuse_cell_runtime::{
    checksum::artifact_digest, graph::repair_cells::Catalog, program::Program,
};
use serde_json::json;
use std::{collections::BTreeSet, fs, path::Path};
fn with_selection(seed: &Program, selected: &[usize]) -> Result<Program> {
    let mut raw = seed.artifact.clone();
    raw.as_object_mut().unwrap().remove("sha256");
    raw["repair_cells"] = Catalog::select(seed, selected)?;
    raw["sha256"] = artifact_digest(&raw).into();
    Ok(Program::parse(raw)?)
}
pub(crate) fn run(args: Vec<String>) -> Result<()> {
    if args.iter().any(|a| a == "--help") {
        println!(
            "cell-compiler bake-repair --program FILE --output NEW_DIR [--rounds N] [--trial-limit N] [--entry-publications true|false]"
        );
        return Ok(());
    }
    let opts = super::options(
        args.into_iter(),
        &[
            "--program",
            "--output",
            "--rounds",
            "--trial-limit",
            "--entry-publications",
        ],
    )?;
    let seed = Program::parse(super::read(Path::new(
        opts.get("--program").ok_or("--program required")?,
    ))?)?;
    let out = Path::new(opts.get("--output").ok_or("--output required")?);
    let rounds = opts
        .get("--rounds")
        .map(|v| v.parse())
        .transpose()?
        .unwrap_or(1usize);
    let limit = opts
        .get("--trial-limit")
        .map(|v| v.parse())
        .transpose()?
        .unwrap_or(4usize);
    if limit == 0 {
        return Err("trial limit must be positive".into());
    }
    let owned = opts
        .get("--entry-publications")
        .map(|v| v.parse())
        .transpose()?
        .unwrap_or(false);
    let config = |enabled| Execution {
        entry_publications: owned,
        repair_ports: true,
        repair_cells: enabled,
        local_unions: false,
        cell_ownership: false,
    };
    let all = (0..seed.repair_cells.len()).collect::<Vec<_>>();
    fs::create_dir(out)?;
    let discovery = with_selection(&seed, &all)?;
    let (profile, expected) = replay(discovery.clone(), false, config(true))?;
    let report = profile.report();
    drop(profile);
    super::write(&out.join("discovery-program.json"), &discovery.artifact)?;
    super::write(&out.join("profile.json"), &report)?;
    super::write(
        &out.join("audit.json"),
        &json!({
            "final_state_sha256":expected.0,"schedule_sha256":expected.1,
            "ordered_rhs_sha256":artifact_digest(&json!(expected.2)),
            "ordered_writes_sha256":artifact_digest(&json!(expected.3)),
            "ordered_resumes_sha256":artifact_digest(&json!(expected.4)),
            "scope":"standalone Cell CPU; every scored replay must match these digests",
        }),
    )?;
    super::write(
        &out.join("templates.json"),
        &json!(discovery.repair_cells.registry_nodes()),
    )?;
    let source_units = discovery.iterative.entries();
    let registry = eggfuse_bake::native_analyze::register_cpu_repair_blocks(
        &discovery.artifact["iterative_bake"],
        &source_units,
        discovery.artifact["iterative_bake"]["joins"]
            .as_array()
            .map(Vec::as_slice)
            .unwrap_or(&[]),
        &discovery.repair_cells.registry_nodes(),
        eggfuse_bake::bake_limits::BakeLimits {
            max_depth: 64,
            max_nodes: 64,
            max_units: 4096,
        },
    )?;
    super::write(&out.join("cell-egraph.json"), &registry)?;
    let mut selected = BTreeSet::new();
    let mut history = vec![];
    for round in 0..rounds {
        let current = with_selection(&seed, &selected.iter().copied().collect::<Vec<_>>())?;
        let (baseline, stamp) = replay(current, false, config(!selected.is_empty()))?;
        if stamp != expected {
            return Err("repair discovery changed graph, schedule, RHS, writes or resumes".into());
        }
        let work = Work::read(&baseline.report())?;
        drop(baseline);
        let mut ranked = all
            .iter()
            .copied()
            .filter(|id| !selected.contains(id))
            .collect::<Vec<_>>();
        ranked.sort_by_key(|&id| {
            std::cmp::Reverse(
                report["repair_cells"]["stats"]["by_shape"][id][0]
                    .as_u64()
                    .unwrap_or(0),
            )
        });
        // The complete family is a separate proposal: shared dispatch overhead
        // makes its measured credit different from summing singleton credits.
        let mut proposals = if ranked.is_empty() {
            vec![]
        } else {
            vec![all.clone()]
        };
        proposals.extend(ranked.iter().map(|&id| {
            let mut s = selected.clone();
            s.insert(id);
            s.into_iter().collect::<Vec<_>>()
        }));
        let mut seen = BTreeSet::new();
        proposals.retain(|p| seen.insert(p.clone()));
        let untried = proposals.len().saturating_sub(limit);
        let mut best = None;
        let mut score = 0;
        let mut trials = vec![];
        for ids in proposals.into_iter().take(limit) {
            let start = std::time::Instant::now();
            let trial = with_selection(&seed, &ids)?;
            let compile_seconds = start.elapsed().as_secs_f64();
            let start = std::time::Instant::now();
            let (exec, actual) = replay(trial, false, config(true))?;
            if actual != expected {
                return Err(
                    "repair candidate changed graph, schedule, RHS, writes or resumes".into(),
                );
            }
            let (net, delta) = work.savings(&Work::read(&exec.report())?);
            trials.push(json!({"selected":ids,"semantic_audit":true,"compile_seconds":compile_seconds,"replay_and_hash_seconds":start.elapsed().as_secs_f64(),"work":delta,"repair_cells":exec.graph.repair_cell_report()["stats"]}));
            eprintln!(
                "repair round {round}: {} shapes, {net} net saved operations",
                ids.len()
            );
            if net > score {
                score = net;
                best = Some(ids);
            }
            super::write(
                &out.join(format!("round-{round}-trials.json")),
                &json!(trials),
            )?;
        }
        let admitted = best.is_some();
        if let Some(ids) = best {
            selected = ids.into_iter().collect();
        }
        history.push(json!({"round":round,"selected":selected,"net_saved_operations":score,"untried_proposals":untried,
            "stop":if admitted && round + 1 == rounds {"round_limit"} else if admitted {"continue"} else if untried > 0 {"trial_limit"} else {"no_measured_gain"},"trials":trials}));
        if !admitted {
            break;
        }
    }
    // Even a zero-round run must audit its final selection against discovery.
    let final_program = with_selection(&seed, &selected.iter().copied().collect::<Vec<_>>())?;
    let (exec, actual) = replay(final_program.clone(), false, config(!selected.is_empty()))?;
    if actual != expected {
        return Err("final repair selection changed execution".into());
    }
    super::write(&out.join("program.json"), &final_program.artifact)?;
    super::write(&out.join("rounds.json"), &json!(history))?;
    super::write(&out.join("final-report.json"), &exec.report())?;
    Ok(())
}
