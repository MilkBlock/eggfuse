//! Single audited execution with actual work counters, not a timing benchmark.
#[path = "../src/work_credit.rs"]
#[allow(dead_code)]
mod work_credit;
use eggfuse_cell_runtime::{
    checksum::artifact_digest, executor::Executor, graph::Graph, program::Program,
    transfer_audit as audit,
};
use serde_json::{Value, json};
use std::{error::Error, fs};
fn main() -> Result<(), Box<dyn Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()<3 || args[3..].iter().any(|s|s!="--natural" && s!="--parent-takeover") {
        return Err("usage: runtime_closure_work PROGRAM SAVED_RUN_TRACE OUTPUT [--natural] [--parent-takeover]".into());
    }
    let saved: Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let checks = saved["run_checks"]
        .as_array()
        .ok_or("missing saved Run checks")?;
    let p = Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let sha = p.artifact["sha256"].clone();
    let selection = p.artifact["iterative_bake"]["closure_selection"].clone();
    let mut e = Executor::new(Graph::new_with_local_congruence(p)?, false);
    let natural=args.iter().any(|s|s=="--natural");
    let parent_takeover=args.iter().any(|s|s=="--parent-takeover");
    if parent_takeover {e.use_completed_parent_takeover()?;}
    let mut runs = 0;
    loop {
        audit::take_digests();
        audit::take_write_digests();
        audit::take_resume_digests();
        audit::set_active(true);
        audit::enable_write_audit();
        e.execute_until(Some(runs + 1))?;
        audit::set_active(false);
        let effects = json!({"rhs":audit::take_digests(),"writes":audit::take_write_digests(),"resumes":audit::take_resume_digests()});
        if e.steps.len() == runs {
            break;
        }
        if !natural {e.graph.compact_retained_capacity()?;}
        let observed =
            json!({"graph":artifact_digest(&e.graph.export()?),"audit":artifact_digest(&effects)});
        if checks.get(runs) != Some(&observed) {
            return Err(format!(
                "Run {} differs: expected {:?}, actual {observed}",
                runs + 1,
                checks.get(runs)
            )
            .into());
        }
        runs += 1;
    }
    if runs != checks.len() {
        return Err("Run count differs".into());
    }
    let report = e.report();
    let measured_work=work_credit::Work::read(&report)?;
    let result = json!({"scope":"actual standalone runtime work; no timing or memory speedup claim",
        "program_sha256":sha,"selection":selection,"diagnostic_compaction":!natural,"parent_takeover":parent_takeover,"source_storage":e.graph.retained_cell_storage(),"runs":runs,"all_saved_run_checks_equal":true,
        "measured_work":measured_work.0,"graph_work":e.graph.stats,"stage_work":report["stage_spine"]["stats"],
        "history_storage":report["stage_spine"]["published_history_storage"],
        "query_work":report["free_join"],"key_lookup_calls":report["key_lookup_calls"],
        "entry_work":report["entry_schedule"],"publication_work":report["publication"],
        "final_state":e.graph.export()?});
    fs::write(&args[2], serde_json::to_vec_pretty(&result)?)?;
    println!("{}", json!({"runs":runs,"all_saved_run_checks_equal":true}));
    Ok(())
}
