//! Separate exact reference, offline teacher and search-free receiver entry points.
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program, transfer_audit};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{env, fs, time::Instant};

#[derive(serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct Tape {
    schema: String,
    program_sha256: String,
    repair_events: Vec<eggfuse_cell_runtime::cell_tokens::RepairEvent>,
    requests: Vec<eggfuse_cell_runtime::cell_tokens::Request>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().skip(1).collect();
    let [role, program, tape, audit, rest @ ..] = args.as_slice() else {
        return Err("expected reference|capture|replay|online PROGRAM TAPE audit|time".into());
    };
    #[cfg(feature = "cell-token-ept")]
    let (rest, ept) = match rest { [rest @ .., flag] if flag=="--ept" => (rest,true), _ => (rest,false) };
    let (rest, layout_path) = match rest {
        [rest @ ..,flag,path] if flag=="--layouts" && (role=="assist" || role=="online") => (rest,Some(path)),
        _ => (rest,None),
    };
    let (rest, higher_path) = match rest {
        [rest @ .., flag, path] if flag == "--higher" && (role == "assist" || role == "online") => (rest, Some(path)),
        _ => (rest,None),
    };
    let (rest, recall_path) = match rest {
        [rest @ .., flag, path] if flag == "--recall" && role == "replay" => (rest, Some(path)),
        _ => (rest, None),
    };
    let (rest, memory_path) = match rest {
        [rest @ .., flag, path] if flag == "--memory" => (rest, Some(path)),
        _ => (rest, None),
    };
    let (rest, export_path) = match rest {
        [rest @ .., flag, path] if flag == "--export" => (rest, Some(path)),
        _ => (rest, None),
    };
    let limit = match rest {
        [] => None,
        [n] => Some(n.parse::<usize>()?),
        _ => return Err("expected optional Run count".into()),
    };
    let do_audit = match audit.as_str() {
        "audit" => true,
        "time" => false,
        _ => return Err("invalid audit mode".into()),
    };
    let compiled = fs::read(program)?;
    let digest = format!("{:x}", Sha256::digest(&compiled));
    let p = Program::parse(serde_json::from_slice(&compiled)?)?;
    let packets = if role == "replay" || role == "shadow-waves" {
        let saved: Tape = serde_json::from_slice(&fs::read(tape)?)?;
        if saved.schema != "cell-token-replay/v2" || saved.program_sha256 != digest {
            return Err("tape schema or compiled program digest differs".into());
        }
        Some(saved.requests)
    } else {
        None
    };
    let started = Instant::now();
    let mut engine = Executor::new(Graph::new(p)?, false);
    #[cfg(feature = "cell-token-ept")]
    if ept {engine.graph.token_ept=Some(Default::default());}
    match role.as_str() {
        "replay" | "capture" | "shadow-waves" => engine.start_tokens(packets)?,
        "online" | "online-waves" => engine.start_tokens(Some(Vec::new()))?,
        "assist" => engine.start_token_assist()?,
        "reference" => (),
        _ => return Err("unknown execution mode".into()),
    }
    if let Some(path) = layout_path {
        if higher_path.is_some() { return Err("choose a single higher Cell ABI".into()); }
        engine.enable_layout_tokens(serde_json::from_slice(&fs::read(path)?)?)?;
    }
    if let Some(path) = higher_path {
        engine.enable_higher_tokens(serde_json::from_slice(&fs::read(path)?)?)?;
    }
    if let Some(path) = recall_path {
        let probes: Tape = serde_json::from_slice(&fs::read(path)?)?;
        if probes.schema != "cell-token-replay/v2" || probes.program_sha256 != digest {
            return Err("recall tape/program mismatch".into());
        }
        engine.audit_token_recall(probes.requests)?;
    }
    if let Some(path) = memory_path {
        engine.export_token_memory(Some(std::path::Path::new(path)))?;
    } else if role == "online-waves" || role == "shadow-waves" {
        engine.enable_token_waves(role == "shadow-waves")?;
    } else if role == "online" {
        engine.export_token_memory(None)?;
    }
    if do_audit {
        transfer_audit::set_active(true);
        transfer_audit::enable_write_audit();
        transfer_audit::enable_events();
    }
    engine.execute_until(limit)?;
    let elapsed = started.elapsed().as_secs_f64();
    transfer_audit::set_active(false);
    let mut export = vec![];
    engine.graph.write_export(&mut export)?;
    if let Some(path) = export_path {
        fs::write(path, &export)?;
    }
    let search: f64 = engine.steps.iter().map(|s| s.phases.search).sum();
    let mut report = json!({
        "source_search_phase_seconds": search, "repair_phase_seconds":engine.steps.iter().map(|s|s.phases.repair).sum::<f64>(),
        "role":role,"run_limit":limit,"seconds":elapsed,"state_sha":format!("{:x}",Sha256::digest(export)),
        "matches":engine.steps.iter().map(|s|s.executed_bindings).sum::<usize>(),
        "runs":engine.steps.len(),
        "schedule":engine.steps.iter().map(|s|json!([s.ruleset,s.path,s.iterations,s.epoch,s.executed_bindings,s.changed])).collect::<Vec<_>>()
    });
    report["residual_candidates"] = json!(engine.graph.stats.residual_candidates);
    #[cfg(feature = "cell-token-ept")]
    if let Some(e)=&engine.graph.token_ept {report["ept"]=e.report();}
    if let Some(h) = engine.tokens() {
        if let Some(counts)=h.layout_report() {report["layouts"]=counts;}
        if let Some(counts) = h.higher_report() { report["higher"] = counts; }
        if let Some(a) = &h.assist { report["assist"] = json!(a); }
        if let Some(audit) = &h.recall {
            report["recall_verdicts"] = json!(audit.verdicts);
            report["unused_recall"] = json!(audit.pending());
        }
        if let Some(w) = &h.waves {
            report["prefixes_checked"] = json!(w.prefixes_checked);
            report["prefix_reads"] = json!(w.prefix_reads);
            report["prefix_verify_seconds"] = json!(w.prefix_time.as_secs_f64());
            report["wave_batches"] = json!(w.batches);
            report["wave_requests"] = json!(w.requests);
            if w.shadow { report["wave_checks"] = json!(w.checks); }
        }
        report["runtime_events"] = json!(h.repair_events);
        report["event_registration_seconds"] = json!(h.event_time.as_secs_f64());
        report["counts"] = json!(h.counts);
        report["verify_seconds"] = json!(h.verify_time.as_secs_f64());
        report["unused"] = json!(h.unused());
        if role == "capture" {
            fs::write(
                tape,
                serde_json::to_vec(&Tape {
                    schema: "cell-token-replay/v2".into(),
                    program_sha256: digest,
                    repair_events: h.repair_events.clone(),
                    requests: h.tape.clone(),
                })?,
            )?;
        }
    }
    if do_audit {
        report["rhs"] = json!(transfer_audit::take_digests());
        report["writes"] = json!(transfer_audit::take_write_digests());
        report["resumes"] = json!(transfer_audit::take_resume_digests());
        report["events"] = json!(transfer_audit::take_events());
    }
    println!("{}", serde_json::to_string(&report)?);
    Ok(())
}
