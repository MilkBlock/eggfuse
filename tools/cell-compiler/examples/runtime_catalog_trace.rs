//! Observe the installed catalog against saved per-Run graph and effect audits.
//! This is diagnostic execution, not a memory or speed benchmark.
use eggfuse_cell_runtime::{
    checksum::artifact_digest, executor::Executor, graph::Graph, program::Program,
    transfer_audit as audit,
};
use serde_json::{Value, json};
use std::{error::Error, fs};
fn main() -> Result<(), Box<dyn Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 3 && !((args.len() == 4 || args.len() == 5) && args[3] == "--closure-history") {
        return Err("usage: runtime_catalog_trace PROGRAM EXPECTED_TRACE OUTPUT [--closure-history [EVENT_LIMIT]]".into());
    }
    let expected: Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let checks = expected["run_checks"]
        .as_array()
        .ok_or("expected saved Run checks")?;
    let p = Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let mut graph = Graph::new_with_local_congruence(p)?;
    graph.trace_ownership_catalog(16)?;
    let mut e = Executor::new(graph, false);
    if args.len() == 5 { e.collect_iterative_history(args[4].parse()?); }
    else if args.len() == 4 { e.collect_iterative_pairs(); }
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
        e.graph.compact_retained_capacity()?;
        let observed =
            json!({"graph":artifact_digest(&e.graph.export()?),"audit":artifact_digest(&effects)});
        if checks.get(runs) != Some(&observed) {
            return Err(format!("Run {} differs from saved graph/effect checks", runs + 1).into());
        }
        runs += 1;
    }
    if runs != checks.len() {
        return Err("Run count differs from saved trace".into());
    }
    let mut result = json!({"scope":"actual standalone Cell runtime; passive installed-catalog observations, no compression or timing claim",
        "runs":runs,"all_saved_run_checks_equal":true,"expected_trace_digest":artifact_digest(&expected),
        "catalog_trace":e.graph.ownership_catalog_trace()?,"ownership":e.graph.ownership_report(),
        "source_storage":e.graph.retained_cell_storage(),"final_state":e.graph.export()?});
    if args.len() >= 4 {
        result["completed_history"] = e.iterative_training().completion_history(&e.graph.program);
    }
    fs::write(&args[2], serde_json::to_vec_pretty(&result)?)?;
    println!(
        "{}",
        json!({"runs":runs,"proposals":result["catalog_trace"]["records"].as_array().unwrap().len(),"all_saved_run_checks_equal":true})
    );
    Ok(())
}
