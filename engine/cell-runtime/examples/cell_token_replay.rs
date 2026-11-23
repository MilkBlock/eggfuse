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
    let packets = if role == "replay" {
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
    match role.as_str() {
        "replay" | "capture" => engine.start_tokens(packets)?,
        "online" => engine.start_tokens(Some(Vec::new()))?,
        "reference" => (),
        _ => return Err("unknown execution mode".into()),
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
    if let Some(h) = engine.tokens() {
        if let Some(audit) = &h.recall {
            report["recall_verdicts"] = json!(audit.verdicts);
            report["unused_recall"] = json!(audit.pending());
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
