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
    if let [mode, path] = args.as_slice() && mode == "receipt-contract" {
        let p = Program::parse(serde_json::from_slice(&fs::read(path)?)?)?;
        println!("{}", eggfuse_cell_runtime::receipt_contract::describe(&p));
        return Ok(());
    }
    let [role, program, tape, audit, rest @ ..] = args.as_slice() else {
        return Err("expected reference|capture|replay|online PROGRAM TAPE audit|time".into());
    };
    #[cfg(feature = "cell-token-ept")]
    let (rest, ept, origins) = match rest {
        [rest @ .., flag] if flag == "--ept-origins" => (rest, true, true),
        [rest @ .., flag] if flag == "--ept" => (rest, true, false),
        _ => (rest, false, false),
    };
    let (rest, named_next) = match rest {
        [rest @ .., flag] if flag == "--audit-next-proofs" && role=="replay" => (rest,true),
        _ => (rest,false),
    };
    let (rest, exact_next) = match rest {
        [rest @ .., flag] if flag == "--audit-exact-next" && role == "replay" => (rest, true),
        _ => (rest, false),
    };
    // Offline observation only; never expose reference rows to an online policy.
    let (rest, row_history) = match rest {
        [rest @ .., flag, path] if flag == "--row-history" && matches!(role.as_str(), "reference" | "replay") => (rest, Some(path)),
        _ => (rest, None),
    };
    let verified_layouts=matches!(rest,[..,flag,_] if flag=="--verified-layouts" && role=="online");
    let (rest, layout_path) = match rest {
        [rest @ ..,_,path] if verified_layouts => (rest,Some((path,false))),
        [rest @ ..,flag,path] if (flag=="--layouts" || flag=="--layout-feedback") && (role=="assist" || role=="online") => (rest,Some((path,flag=="--layout-feedback"))),
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
    if ept {
        let mut ledger=eggfuse_cell_runtime::token_ept::Ledger::default();
        if origins { ledger.enable_origins(); }
        if layout_path.is_some_and(|(_,feedback)|feedback) {ledger.enable_step_credit();}
        engine.graph.token_ept=Some(ledger);
    }
    match role.as_str() {
        "replay" | "capture" | "shadow-waves" => engine.start_tokens(packets)?,
        "online" | "online-waves" | "online-transactions" | "online-ccp-v0.1" => engine.start_tokens(Some(Vec::new()))?,
        "assist" => engine.start_token_assist()?,
        "reference" => (),
        "anchor-census" => engine.enable_anchor_census(),
        "anchor-partition" => engine.enable_anchor_partition()?,
        _ => return Err("unknown execution mode".into()),
    }
    if let Some((path,feedback)) = layout_path {
        if higher_path.is_some() { return Err("choose a single higher Cell ABI".into()); }
        engine.configure_layout_tokens(serde_json::from_slice(&fs::read(path)?)?,feedback)?;
        if verified_layouts {engine.verify_layouts_before_proposals()?;}
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
    if role == "online-ccp-v0.1" && memory_path.is_some() {
        return Err("CCP requires the online typed publication stream".into());
    }
    if let Some(path) = memory_path {
        engine.export_token_memory(Some(std::path::Path::new(path)))?;
    } else if role == "online-ccp-v0.1" {
        engine.enable_ccp_v01()?;
        println!("{}",json!({"protocol":"Cell Communication Protocol","version":[0,1],"program_sha256":digest,"commit_scope":"source_run","transport":"ordered-pipe"}));
    } else if role == "online-transactions" {
        engine.enable_token_transactions()?;
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
    if let Some(path) = row_history {
        use std::{collections::BTreeSet, io::{BufWriter, Write}};
        let mut output = BufWriter::new(fs::File::create(path)?);
        let mut previous = BTreeSet::new();
        loop {
            let run = engine.steps.len();
            let mut bytes = Vec::new();
            engine.graph.write_export(&mut bytes)?;
            let state: serde_json::Value = serde_json::from_slice(&bytes)?;
            let current = state["rows"].as_array().ok_or("missing exported rows")?
                .iter().filter(|r| r["subsumed"] == false)
                .map(serde_json::to_string).collect::<Result<BTreeSet<_>, _>>()?;
            serde_json::to_writer(&mut output, &json!({
                "run":run, "added":current.difference(&previous).collect::<Vec<_>>(),
                "removed":previous.difference(&current).collect::<Vec<_>>()
            }))?;
            output.write_all(b"\n")?;
            previous = current;
            if limit.is_some_and(|n| run >= n) { break; }
            engine.execute_until(Some(run + 1))?;
            if run == engine.steps.len() { break; }
        }
        output.flush()?;
    } else {
        engine.execute_until(limit)?;
    }
    if role == "online-ccp-v0.1" { engine.finish_ccp_v01()?; }
    if named_next {
        println!("{}",serde_json::to_string(&engine.audit_next_named_run()?)?);
        return Ok(());
    }
    if exact_next {
        let mut bytes = Vec::new();
        engine.graph.write_export(&mut bytes)?;
        let run = engine.steps.len() + 1;
        let next = engine.audit_next_exact_run();
        let result = match next {
            Ok(step) => json!({"next":step}),
            Err(source_error) => json!({"source_error":source_error}),
        };
        println!("{}", json!({"run":run,"prefix_sha":format!("{:x}",Sha256::digest(bytes)),"result":result}));
        return Ok(());
    }
    let elapsed = started.elapsed().as_secs_f64();
    transfer_audit::set_active(false);
    let mut export = vec![];
    engine.graph.write_export(&mut export)?;
    if let Some(path) = export_path {
        fs::write(path, &export)?;
    }
    let search: f64 = engine.steps.iter().map(|s| s.phases.search).sum();
    let mut report = json!({
        "rhs_phase_seconds": engine.steps.iter().map(|s| s.phases.rhs).sum::<f64>(),
        "source_search_phase_seconds": search, "repair_phase_seconds":engine.steps.iter().map(|s|s.phases.repair).sum::<f64>(),
        "role":role,"run_limit":limit,"seconds":elapsed,"state_sha":format!("{:x}",Sha256::digest(export)),
        "matches":engine.steps.iter().map(|s|s.executed_bindings).sum::<usize>(),
        "runs":engine.steps.len(),
        "schedule":engine.steps.iter().map(|s|json!([s.ruleset,s.path,s.iterations,s.epoch,s.executed_bindings,s.changed])).collect::<Vec<_>>()
    });
    if role=="online-ccp-v0.1" {report["committed_through_run"]=json!(engine.steps.len());}
    if let Some(rows)=engine.anchor_coverage() {report["anchor_coverage"]=json!(rows);}
    if let Some(history)=engine.tokens() {report["anchor_verify_seconds"]=json!(history.anchor_verify_time.as_secs_f64());}
    if let Some(rows)=engine.anchor_census_rows() {report["anchor_census"]=json!(rows);}
    report["residual_candidates"] = json!(engine.graph.stats.residual_candidates);
    #[cfg(feature = "cell-token-ept")]
    if let Some(e)=&engine.graph.token_ept {report["ept"]=e.report();}
    #[cfg(feature = "cell-token-ept")]
    if role == "replay" && origins {
        let work = &engine.graph.stats;
        report["primitive_work"] = json!({
            "committed_rhs": report["matches"],
            "constructor_requests": work.constructor_requests,
            "constructor_reused": work.constructor_reused,
            "function_updates": work.function_updates,
            "merge_calls": work.merge_calls,
            "merge_program_operations": work.merge_program_operations,
            "unions": work.unions,
            "repaired_dependencies": work.repaired_dependencies
        });
    }
    if let Some(h) = engine.tokens() {
        if let Some(counts)=h.layout_report() {report["layouts"]=counts;}
        if let Some(counts) = h.higher_report() { report["higher"] = counts; }
        if let Some(a) = &h.assist { report["assist"] = json!(a); }
        if let Some(audit) = &h.recall {
            report["recall_verdicts"] = json!(audit.verdicts);
            report["unused_recall"] = json!(audit.pending());
        }
        if let Some(w) = &h.waves {
            if let Some(m)=&w.transactions {report["txn_stats"]=json!(m);}
            report["prefixes_checked"] = json!(w.prefixes_checked);
            report["prefix_reads"] = json!(w.prefix_reads);
            report["prefix_verify_seconds"] = json!(w.prefix_time.as_secs_f64());
            report["guard_failures"] = json!(w.guard_failures.iter().map(|(&(run, rule, pc, reason), &count)| (run, rule, pc, reason, count)).collect::<Vec<_>>());
            report["wave_batches"] = json!(w.batches);
            report["wave_requests"] = json!(w.requests);
            if w.shadow { report["wave_checks"] = json!(w.checks); }
        }
        if role != "online-ccp-v0.1" { report["runtime_events"] = json!(h.repair_events); }
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
