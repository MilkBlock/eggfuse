//! Execute frozen catalogs from the identical initial state and admit bounded
//! adjacent winners. Only install artifacts after the semantic audit succeeds.
use eggfuse_cell_runtime::{
    checksum::artifact_digest,
    executor::Executor,
    graph::Graph,
    iterative::{Catalog, Limits},
    program::Program,
    transfer_audit,
};
use serde_json::{Value as J, json};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};
use crate::work_credit::Work;
type Result<T> = eggfuse_bake::pipeline::Result<T>;
pub(crate) type Stamp = (String, String, Vec<String>, Vec<(u64, String)>, Vec<(u64, String)>);
#[derive(Clone, Copy)]
pub(crate) struct Execution {
    pub entry_publications: bool,
    pub repair_ports: bool,
    pub repair_cells: bool,
    pub local_unions: bool,
}
pub(crate) fn replay(p: Program, collect: bool, config: Execution) -> Result<(Executor, Stamp)> {
    let mut graph = if config.repair_cells { Graph::new_with_repair_cells(p)? } else if config.repair_ports { Graph::new_with_repair_ports(p)? } else { Graph::new(p)? };
    if config.local_unions { graph.use_local_union_cells()?; }
    let mut exec = Executor::new(graph, false);
    #[cfg(feature = "sparse-cells")]
    if config.entry_publications { exec.use_entry_publications()?; }
    if collect { exec.collect_iterative_pairs(); }
    transfer_audit::take_digests();
    transfer_audit::take_write_digests();
    transfer_audit::take_resume_digests();
    transfer_audit::set_active(true);
    transfer_audit::enable_write_audit();
    let result = exec.execute_until(None);
    transfer_audit::set_active(false);
    result?;
    let rhs = transfer_audit::take_digests();
    let writes = transfer_audit::take_write_digests();
    let resumes = transfer_audit::take_resume_digests();
    let mut hasher = Sha256::new();
    exec.graph.write_export(&mut hasher)?;
    let graph = format!("{:x}", hasher.finalize());
    let schedule = exec.steps.iter().map(|s| {
        ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed"].map(|k| &s[k])
    }).collect::<Vec<_>>();
    let stamp = (graph, artifact_digest(&json!(schedule)), rhs, writes, resumes);
    Ok((exec, stamp))
}
fn save(path: &Path, value: &J) -> Result<()> {
    let mut f = tempfile::NamedTempFile::new_in(path.parent().unwrap())?;
    serde_json::to_writer(&mut f, value)?;
    f.persist(path)?;
    Ok(())
}
pub(crate) fn run(args: Vec<String>) -> Result<()> {
    let opts = super::options(
        args.into_iter(),
        &[
            "--program",
            "--output",
            "--rounds",
            "--objective",
            "--max-depth",
            "--max-nodes",
            "--new-per-round",
            "--max-units",
            "--candidate-slots",
            "--min-support",
            "--producer-profile",
            "--resume-catalog",
            "--score",
            "--trial-limit",
            "--entry-publications",
            "--repair-ports",
            "--repair-cells",
            "--local-unions",
        ],
    )?;
    let measured = match opts.get("--score").map(String::as_str).unwrap_or("measured-work") {
        "measured-work" => true,
        "static" => false,
        _ => return Err("score must be measured-work or static".into()),
    };
    let trial_limit = opts.get("--trial-limit").map(|s| s.parse()).transpose()?.unwrap_or(8usize);
    if trial_limit == 0 { return Err("trial limit must be positive".into()); }
    let flag = |name| -> Result<bool> { Ok(opts.get(name).map(|s| s.parse()).transpose()?.unwrap_or(false)) };
    let config = Execution { entry_publications: flag("--entry-publications")?, repair_ports: flag("--repair-ports")?, repair_cells: flag("--repair-cells")?, local_unions: flag("--local-unions")? };
    if config.entry_publications && !cfg!(feature = "sparse-cells") {
        return Err("entry publications require the sparse-cells build".into());
    }
    let path = opts
        .get("--program")
        .ok_or("--program SEED_PROGRAM required")?;
    let output = opts.get("--output").ok_or("--output NEW_DIR required")?;
    let seed = Program::parse(super::read(Path::new(path))?)?;
    let rounds = opts
        .get("--rounds")
        .map(|s| s.parse())
        .transpose()?
        .unwrap_or(4usize);
    let resume_plan = opts
        .get("--resume-catalog")
        .map(|path| super::read(Path::new(path)))
        .transpose()?;
    let native = eggfuse_bake::bake_limits::BakeLimits::from_env()?;
    let mut limits = if let Some(plan) = &resume_plan {
        serde_json::from_value(plan["limits"].clone())?
    } else {
        Limits {
            depth: native.max_depth,
            nodes: native.max_nodes,
            total: native.max_units,
            ..Default::default()
        }
    };
    for (name, slot) in [
        ("--max-depth", &mut limits.depth),
        ("--max-nodes", &mut limits.nodes),
        ("--new-per-round", &mut limits.per_round),
        ("--max-units", &mut limits.total),
        ("--candidate-slots", &mut limits.candidates),
    ] {
        if let Some(s) = opts.get(name) {
            *slot = s.parse()?
        }
    }
    if let Some(s) = opts.get("--min-support") {
        limits.support = s.parse()?
    }
    let (handoffs, congruence, query_ports) = match opts
        .get("--objective")
        .map(String::as_str)
        .unwrap_or("copies")
    {
        "copies" => (false, false, false),
        "rhs-lookups" => (true, false, false),
        "rhs-congruence" => (true, true, false),
        "stage-congruence" => (true, true, true),
        _ => return Err("unknown iterative Bake objective".into()),
    };
    let mut plan = if let Some(mut plan) = resume_plan {
        if opts.contains_key("--producer-profile") {
            return Err("resume a catalog or select producer roots, not both".into());
        }
        let mut raw = seed.artifact.clone();
        raw["iterative_bake"] = plan.clone();
        // Reconstruct the old certificate before changing its objective/limits.
        Program::parse(raw)?;
        plan["limits"] = json!(limits);
        plan.as_object_mut()
            .ok_or("invalid resume catalog")?
            .remove("rhs_handoffs");
        plan
    } else if let Some(path) = opts.get("--producer-profile") {
        if !congruence {
            return Err("producer receipts require a congruence objective".into());
        }
        let profile = super::read(Path::new(path))?;
        if profile["schema"] != "eggfuse-spine-shapes/v1"
            || profile["program_sha256"] != seed.artifact["sha256"]
        {
            return Err("producer profile belongs to another seed program".into());
        }
        let mut roots = std::collections::BTreeSet::new();
        for prefix in profile["prefixes"]
            .as_array()
            .ok_or("missing producer prefixes")?
        {
            let [r, op, consumer, pivot]: [usize; 4] =
                serde_json::from_value(prefix["edge"].clone())?;
            let source = seed.rules.get(r).ok_or("unknown producer rule")?;
            let table = match seed.templates[source.template].ops.get(op) {
                Some(eggfuse_cell_runtime::program::Op::Let(
                    _,
                    eggfuse_cell_runtime::program::Call::Table(t),
                    _,
                ))
                | Some(eggfuse_cell_runtime::program::Op::Set(t, _, _)) => *t,
                _ => return Err("producer profile references a nonpublication operation".into()),
            };
            let target = seed.rules.get(consumer).and_then(|r| r.query.get(pivot));
            if !matches!(target.map(|a| &a.call), Some(eggfuse_cell_runtime::program::Call::Table(t)) if *t == table)
            {
                return Err("producer profile references incompatible tables".into());
            }
            if prefix["visits"].as_u64().ok_or("invalid producer visits")? > 0 {
                roots.insert(r);
            }
        }
        let mut plan =
            Catalog::seed_with_roots(&seed, limits, &roots.into_iter().collect::<Vec<_>>())?;
        plan["producer_profile_sha256"] = artifact_digest(&profile).into();
        plan
    } else {
        Catalog::seed(&seed, limits)?
    };
    let out = Path::new(output);
    fs::create_dir(out)?;
    let mut reference = None;
    let mut history = Vec::new();
    let compile_plan = |plan: &mut J| -> Result<Program> {
        if query_ports {
            Catalog::emit_query_handoffs(&seed, plan)?;
        } else if congruence {
            Catalog::emit_congruence_handoffs(&seed, plan)?;
        } else if handoffs {
            Catalog::emit_handoffs(&seed, plan)?;
        }
        let mut artifact = seed.artifact.clone();
        artifact.as_object_mut().unwrap().remove("sha256");
        artifact["iterative_bake"] = plan.clone();
        artifact["sha256"] = artifact_digest(&artifact).into();
        Ok(Program::parse(artifact)?)
    };
    for round in 0..=rounds {
        let p = compile_plan(&mut plan)?;
        let units = p.iterative.entries();
        let registry = eggfuse_bake::native_analyze::register_cpu_blocks(
            &plan,
            &units,
            plan["joins"].as_array().unwrap(),
            eggfuse_bake::bake_limits::BakeLimits {
                max_depth: limits.depth,
                max_nodes: limits.nodes,
                max_units: limits.total,
            },
        )?;
        let (exec, stamp) = replay(p, true, config)?;
        if let Some(expected) = &reference {
            if expected != &stamp {
                return Err(format!(
                    "round {round} differs from initial graph, schedule, ordered RHS, writes or resumes"
                )
                .into());
            }
        } else {
            reference = Some(stamp.clone())
        }
        let p = exec.graph.program.clone();
        let cat = &p.iterative;
        let train = exec.iterative_training();
        let mut admitted = if round < rounds {
            cat.select(&p, train)
        } else {
            vec![]
        };
        let train_report = train.report();
        let direct_origins = train.direct_origins;
        let report = exec.report();
        drop(exec);
        let mut credit = json!({"policy":if measured {"measured-work"} else {"static"},
            "entry_publications":config.entry_publications,"repair_ports":config.repair_ports,"repair_cells":config.repair_cells,"local_unions":config.local_unions});
        if measured && !admitted.is_empty() {
            // Pair discovery can force producer roots into existence. Score
            // with collection disabled in BOTH executions, as in inference.
            let (baseline, baseline_stamp) = replay(p.clone(), false, config)?;
            if baseline_stamp != stamp { return Err("pair collection changed execution".into()); }
            let work = Work::read(&baseline.report())?;
            drop(baseline);
            let mut trials = Vec::new();
            let mut best = None;
            let mut best_score = 0;
            let proposals = std::mem::take(&mut admitted);
            credit["ranked_proposals"] = json!(proposals.len());
            credit["untried_ranked_proposals"] = json!(proposals.len().saturating_sub(trial_limit));
            for (join, evidence) in proposals.into_iter().take(trial_limit) {
                let start = std::time::Instant::now();
                let mut candidate = plan.clone();
                candidate["joins"].as_array_mut().unwrap().push(json!(join));
                let candidate = compile_plan(&mut candidate)?;
                let compile_seconds = start.elapsed().as_secs_f64();
                let candidate_hash = candidate.artifact["sha256"].clone();
                let start = std::time::Instant::now();
                let (trial, actual) = replay(candidate, false, config)?;
                if actual != stamp { return Err("candidate changed graph, schedule, RHS, writes or resumes".into()); }
                let (score, delta) = work.savings(&Work::read(&trial.report())?);
                let row = json!({"join":join,"proposal":evidence,"program_sha256":candidate_hash,
                    "semantic_audit":true,"compile_seconds":compile_seconds,
                    "replay_and_export_hash_seconds":start.elapsed().as_secs_f64(),"work":delta});
                eprintln!("round {round} trial {}: {score} net saved operations", trials.len());
                trials.push(row);
                save(&out.join(format!("round-{round}-trials.json")), &json!(trials))?;
                if score > best_score {
                    best_score = score;
                    best = Some((join, evidence));
                }
            }
            if let Some(winner) = best { admitted.push(winner); }
            // One measured addition per round: never sum independent credits
            // and then assume the corresponding cells do not overlap.
            credit["trials"] = json!(trials);
            credit["selected_net_saved_operations"] = json!(best_score);
        }
        let stopped = if round == rounds {
            "round_limit"
        } else if units.len() == limits.total {
            "catalog_full"
        } else if admitted.is_empty() {
            if measured && credit.get("trials").is_some() {
                if credit["untried_ranked_proposals"].as_u64().unwrap_or(0) > 0 { "trial_limit" }
                else { "no_measured_gain" }
            } else { "no_profitable_candidate" }
        } else {
            "continue"
        };
        let spine = &report["stage_spine"]["stats"];
        let stats = &report["stats"];
        history.push(json!({"round":round,"units":units.len(),"source_program":p.artifact["sha256"],"work":train_report,"rhs_completion":{"lets":stats["handoff_lets"],"sets":stats["handoff_sets"],"closed":stats["handoff_closed"],"noop_unions":stats["handoff_noop_unions"],"deep":stats["handoff_deep"]},"query_completion":{"attempts":spine["query_receipt_attempts"],"hits":spine["query_receipt_hits"],"function_hits":spine["query_receipt_function_hits"],"missing":spine["query_receipt_missing"],"stale":spine["query_receipt_stale"],"port_refreshes":spine["port_refreshes"]},"admitted":admitted,
            "runs":stamp.2.len(),"final_state_sha256":stamp.0,"schedule_sha256":stamp.1,
            "ordered_rhs_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&stamp.2)?)),"stop":stopped,"resumed_steps":spine["resumed_steps"]}));
        history.last_mut().unwrap()["credit"] = credit;
        history.last_mut().unwrap()["ordered_writes_sha256"] = artifact_digest(&json!(stamp.3)).into();
        history.last_mut().unwrap()["ordered_resumes_sha256"] = artifact_digest(&json!(stamp.4)).into();
        // Immutable round checkpoints make an interrupted run inspectable.
        let dir = out.join(format!("round-{round}"));
        fs::create_dir(&dir)?;
        save(&dir.join("catalog.json"), &plan)?;
        save(&dir.join("cell-egraph.json"), &registry)?;
        save(&out.join("rounds.json"), &json!(history))?;
        eprintln!(
            "round {round}: {} blocks, {} new, {} direct origins",
            units.len(),
            admitted.len(),
            direct_origins
        );
        if stopped != "continue" {
            save(&out.join("program.json"), &p.artifact)?;
            save(&out.join("rhs.json"), &json!(stamp.2))?;
            save(&out.join("expanded.json"), &json!(units))?;
            break;
        }
        for (join, _) in admitted {
            plan["joins"].as_array_mut().unwrap().push(json!(join));
        }
    }
    Ok(())
}
