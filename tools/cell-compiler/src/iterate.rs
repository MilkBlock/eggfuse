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
#[derive(Clone, Copy, Default)]
pub(crate) struct Execution {
    pub entry_publications: bool,
    pub repair_ports: bool,
    pub repair_cells: bool,
    pub local_unions: bool,
    pub cell_ownership: bool,
    pub stable_ports: bool,
    pub port_keys: bool,
    pub local_congruence: bool,
}
impl Execution {
    fn checked(mut self) -> Result<Self> {
        self.port_keys |= self.local_congruence;
        self.stable_ports |= self.port_keys;
        self.cell_ownership |= self.stable_ports;
        if self.cell_ownership && (self.repair_cells || self.local_unions) {
            return Err("cell ownership requires its own completion backend".into());
        }
        self.repair_ports |= self.cell_ownership;
        if self.entry_publications && !cfg!(feature = "sparse-cells") {
            return Err("entry publications require the sparse-cells build".into());
        }
        Ok(self)
    }
}
pub(crate) fn replay(p: Program, collect: bool, config: Execution) -> Result<(Executor, Stamp)> {
    let config = config.checked()?;
    let mut graph = if config.repair_cells { Graph::new_with_repair_cells(p)? } else if config.repair_ports { Graph::new_with_repair_ports(p)? } else { Graph::new(p)? };
    if config.local_unions { graph.use_local_union_cells()?; }
    if config.cell_ownership { graph.use_cell_ownership()?; }
    if config.stable_ports { graph.use_stable_port_fields()?; }
    if config.port_keys { graph.use_port_constructor_matching()?; }
    if config.local_congruence { graph.use_local_port_conditions()?; }
    let mut exec = Executor::new(graph, false);
    #[cfg(feature = "sparse-cells")]
    if config.entry_publications && !config.cell_ownership { exec.use_entry_publications()?; }
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn condition_replay_runs_and_scores_the_requested_backend() {
        let source = r#"
(datatype E (N i64) (F E))
(F (N 0)) (F (N 1))
(ruleset merge)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset merge)
(run-schedule (run merge))
"#;
        let core = eggfuse_bake::device_frontend::core("condition-replay", source).unwrap();
        let raw = eggfuse_cell_runtime::compiler::compile(core, &Default::default()).unwrap();
        let p = Program::parse(raw).unwrap();
        let (_, baseline) = replay(p.clone(), false, Execution { repair_ports: true, ..Default::default() }).unwrap();
        for collect in [false, true] {
            let (exec, stamp) = replay(p.clone(), collect, Execution { local_congruence: true, ..Default::default() }).unwrap();
            assert_eq!(baseline, stamp, "all ordered semantic stamps must match");
            let report = exec.report();
            assert_eq!(report["stable_ports"]["enabled"], true);
            assert_eq!(report["stable_ports"]["local_conditions"]["enabled"], true);
            let work = Work::read(&report).unwrap();
            assert!(work.0["stable_ports/stats/equality_completions"] > 0);
            assert!(work.0["stable_ports/local_conditions/stats/attempts"] > 0);
            assert_eq!(work.0["cell_ownership/stats/key_completions"], 0);
        }
        assert!(Execution { local_congruence: true, repair_cells: true, ..Default::default() }.checked().is_err());
        assert!(Execution { port_keys: true, local_unions: true, ..Default::default() }.checked().is_err());
    }
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
            "--cell-ownership",
            "--stable-ports",
            "--port-keys",
            "--local-congruence",
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
    let config = Execution { entry_publications: flag("--entry-publications")?, repair_ports: flag("--repair-ports")?, repair_cells: flag("--repair-cells")?, local_unions: flag("--local-unions")?, cell_ownership:flag("--cell-ownership")?,
        stable_ports:flag("--stable-ports")?, port_keys:flag("--port-keys")?, local_congruence:flag("--local-congruence")? }.checked()?;
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
        "stage-congruence" | "ripsat-completion" => (true, true, true),
        _ => return Err("unknown iterative Bake objective".into()),
    };
    let completion=opts.get("--objective").is_some_and(|s|s=="ripsat-completion");
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
    let compile_plan = |plan: &mut J, expand: bool, observed: Option<&std::collections::BTreeSet<usize>>| -> Result<Program> {
        plan.as_object_mut().unwrap().remove("state_plan");
        if completion {
            if expand {
                if let Some(observed) = observed { Catalog::emit_observed_ripsat_handoffs(&seed,plan,observed)?; }
                else { Catalog::emit_ripsat_handoffs(&seed,plan)?; }
            }
            else { Catalog::emit_existing_ripsat_handoffs(&seed,plan)?; }
        } else if query_ports {
            Catalog::emit_query_handoffs(&seed, plan)?;
        } else if congruence {
            Catalog::emit_congruence_handoffs(&seed, plan)?;
        } else if handoffs {
            Catalog::emit_handoffs(&seed, plan)?;
        }
        if completion {
            let artifact=crate::completion_bake::apply_plan(&seed,plan.clone())?;
            *plan=artifact["iterative_bake"].clone();
            return Ok(Program::parse(artifact)?);
        }
        let mut artifact = seed.artifact.clone();
        artifact.as_object_mut().unwrap().remove("sha256");
        artifact["iterative_bake"] = plan.clone();
        artifact["sha256"] = artifact_digest(&artifact).into();
        let mut p = Program::parse(artifact)?;
        plan["state_plan"] = crate::state_plan::compile(&p)?;
        p.artifact.as_object_mut().unwrap().remove("sha256");
        p.artifact["iterative_bake"] = plan.clone();
        p.artifact["sha256"] = artifact_digest(&p.artifact).into();
        Ok(Program::parse(p.artifact)?)
    };
    let mut prepared = None;
    for round in 0..=rounds {
        // Reuse the exact scored artifact, including inferred joins and IDs.
        let p = match prepared.take() {
            Some(p) => p,
            None => compile_plan(&mut plan, !measured, None)?,
        };
        let units = p.iterative.entries();
        let catalog_registry = if completion { None } else { Some(eggfuse_bake::native_analyze::register_cpu_blocks(
            &plan,
            &units,
            plan["joins"].as_array().unwrap(),
            eggfuse_bake::bake_limits::BakeLimits {
                max_depth: limits.depth,
                max_nodes: limits.nodes,
                max_units: limits.total,
            },
        )?) };
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
        let observed_units = train.completed_trace_units();
        let runtime_history = completion.then(|| train.completion_history(&p));
        let registry = if let Some(trace) = &runtime_history {
            let mut registry = eggfuse_bake::native_analyze::register_cpu_completion_structures(&trace["contracts"])?;
            registry["origin"] = json!({"kind":"completed-cell-runtime-history", "program_sha256":p.artifact["sha256"],
                "events":trace["events"].as_array().unwrap().len(), "dropped_events":trace["dropped_events"]});
            registry
        } else { catalog_registry.unwrap() };
        let train_report = train.report();
        let direct_origins = train.direct_origins;
        let report = exec.report();
        drop(exec);
        let mut credit = json!({"policy":if measured {"measured-work"} else {"static"},
            "entry_publications":config.entry_publications,"repair_ports":config.repair_ports,"repair_cells":config.repair_cells,"local_unions":config.local_unions,"cell_ownership":config.cell_ownership,
            "stable_ports":config.stable_ports,"port_keys":config.port_keys,"local_congruence":config.local_congruence});
        let mut selected_program = None;
        let infer = completion && units.len() < limits.total;
        if measured && round < rounds && (!admitted.is_empty() || infer) {
            // Don't replay a baseline for an empty structural expansion.
            let mut work = None;
            let mut trials = Vec::new();
            let mut best = None;
            let mut best_score = 0;
            let mut proposals = std::mem::take(&mut admitted).into_iter().map(Some).collect::<Vec<_>>();
            // Structural inference can be useful even without a newly observed
            // join. It competes as a real, separately replayed candidate.
            if infer { proposals.push(None); }
            credit["ranked_proposals"] = json!(proposals.len());
            credit["untried_ranked_proposals"] = json!(proposals.len().saturating_sub(trial_limit));
            for proposal in proposals.into_iter().take(trial_limit) {
                let start = std::time::Instant::now();
                let mut candidate = plan.clone();
                if let Some((join, _)) = &proposal {
                    candidate["joins"].as_array_mut().unwrap().push(json!(join));
                }
                let candidate = compile_plan(&mut candidate, true, Some(&observed_units))?;
                if candidate.artifact["iterative_bake"]["joins"] == plan["joins"] { continue; }
                let compile_seconds = start.elapsed().as_secs_f64();
                let candidate_hash = candidate.artifact["sha256"].clone();
                if work.is_none() {
                    // Training can force producer roots into existence. Both
                    // scored executions disable it, exactly as in inference.
                    let (baseline, baseline_stamp) = replay(p.clone(), false, config)?;
                    if baseline_stamp != stamp { return Err("pair collection changed execution".into()); }
                    work = Some(Work::read(&baseline.report())?);
                }
                let start = std::time::Instant::now();
                let (trial, actual) = replay(candidate, false, config)?;
                if actual != stamp { return Err("candidate changed graph, schedule, RHS, writes or resumes".into()); }
                let (score, delta) = work.as_ref().unwrap().savings(&Work::read(&trial.report())?);
                let row = json!({"join":proposal.as_ref().map(|(j,_)|j),
                    "proposal":proposal.as_ref().map(|(_,e)|json!(e)).unwrap_or(json!({"kind":"equivalent-routes","new_observation":false})),
                    "program_sha256":candidate_hash,
                    "semantic_audit":true,"compile_seconds":compile_seconds,
                    "replay_and_export_hash_seconds":start.elapsed().as_secs_f64(),"work":delta});
                eprintln!("round {round} trial {}: {score} net saved operations", trials.len());
                trials.push(row);
                save(&out.join(format!("round-{round}-trials.json")), &json!(trials))?;
                if score > best_score {
                    best_score = score;
                    best = Some((proposal, trial.graph.program.clone()));
                }
            }
            if let Some((proposal, program)) = best {
                if let Some(winner) = proposal { admitted.push(winner); }
                credit["selected_program_sha256"] = program.artifact["sha256"].clone();
                selected_program = Some(program);
            }
            // One measured catalog per round; score inferred routes jointly
            // with their initiating proposal, never sum overlapping credits.
            credit["trials"] = json!(trials);
            credit["selected_net_saved_operations"] = json!(best_score);
        }
        let stopped = if round == rounds {
            "round_limit"
        } else if units.len() == limits.total {
            "catalog_full"
        } else if admitted.is_empty() && selected_program.is_none() {
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
        if completion {
            let dispatch = &plan["completion"]["entry_dispatch"];
            history.last_mut().unwrap()["completion_entries"] = json!({
                "eligible_entries":dispatch["entries"].as_array().map_or(0,Vec::len),
                "eligible_states":dispatch["programs"],
                "scope":"static coverage, not saved work"});
        }
        history.last_mut().unwrap()["ordered_writes_sha256"] = artifact_digest(&json!(stamp.3)).into();
        history.last_mut().unwrap()["ordered_resumes_sha256"] = artifact_digest(&json!(stamp.4)).into();
        // Immutable round checkpoints make an interrupted run inspectable.
        let dir = out.join(format!("round-{round}"));
        fs::create_dir(&dir)?;
        save(&dir.join("catalog.json"), &plan)?;
        save(&dir.join("cell-egraph.json"), &registry)?;
        if let Some(trace) = &runtime_history { save(&dir.join("cell-history.json"), trace)?; }
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
        if let Some(next) = selected_program {
            plan = next.artifact["iterative_bake"].clone();
            prepared = Some(next);
        } else {
            for (join, _) in admitted {
                plan["joins"].as_array_mut().unwrap().push(json!(join));
            }
        }
    }
    Ok(())
}
