//! Diagnostic prefix runner. It uses the actual runtime without changing its
//! lookup/repair implementation; prefix timings are not full-workload timings.
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{path::PathBuf, time::Instant};

#[global_allocator]
static ALLOCATOR: mimalloc::MiMalloc = mimalloc::MiMalloc;

fn digest(value: &Value) -> Result<String, Box<dyn std::error::Error>> {
    Ok(format!("{:x}", Sha256::digest(serde_json::to_vec(value)?)))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 4 {
        return Err("probe PROGRAM OUTPUT_JSON MODE RUN_LIMIT".into());
    }
    let program = Program::parse(serde_json::from_slice(&std::fs::read(&args[0])?)?)?;
    let mode = args[2].as_str();
    let limit: usize = args[3].parse()?;
    let mut graph = Graph::new_with_repair_ports(program)?;
    if mode != "fast" { graph.use_cell_ownership()?; }
    if !matches!(mode, "fast" | "ownership") { graph.use_stable_port_fields()?; }
    if !matches!(mode, "fast" | "ownership" | "stable") { graph.use_port_constructor_matching()?; }
    if matches!(mode, "local" | "pure" | "batch2" | "batch4" | "overlap2" | "overlap4") {
        graph.use_local_port_conditions()?;
    }
    if matches!(mode, "pure" | "batch2" | "batch4" | "overlap2" | "overlap4") {
        graph.use_scoped_completion()?;
    }
    match mode {
        "fast" | "ownership" | "stable" | "keys" | "local" | "pure" => (),
        "batch2" | "batch4" | "overlap2" | "overlap4" => {
            let workers = if mode.ends_with('2') { 2 } else { 4 };
            graph.use_parallel_port_guards(workers, 32)?;
            graph.use_completion_read_batches(16)?;
            if mode.starts_with("overlap") { graph.use_overlapped_completion()?; }
        }
        _ => return Err("unknown probe mode".into()),
    }
    let mut executor = Executor::new(graph, false);
    if mode == "fast" { executor.use_entry_publications()?; }
    if mode == "pure" { executor.use_pure_epochs()?; }
    let initial = executor.report();
    let initial_counters = json!({"key_lookup_calls":initial["key_lookup_calls"],
        "stats":initial["stats"],"stable_ports_stats":initial["stable_ports"]["stats"],
        "cell_ownership_stats":initial["cell_ownership"]["stats"]});
    let start = Instant::now();
    executor.execute_until(Some(limit))?;
    let elapsed = start.elapsed().as_secs_f64();
    let report = executor.report();
    let keys = ["ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed"];
    let schedule = Value::Array(executor.steps.iter().map(|step| {
        Value::Array(keys.iter().map(|key| step[*key].clone()).collect())
    }).collect());
    let mut phases = serde_json::Map::new();
    for key in ["search", "rhs", "repair", "delivery_gc", "query_update"] {
        let total: f64 = report["steps"].as_array().unwrap().iter()
            .map(|step| step["phases"][key].as_f64().unwrap()).sum();
        phases.insert(key.to_owned(), total.into());
    }
    let output = json!({
        "scope":"standalone Cell CPU diagnostic prefix, not full Raytrace performance",
        "mode":mode,"run_limit":limit,"completed_runs":executor.steps.len(),
        "diagnostic_elapsed_seconds":elapsed,"phases":phases,
        "initial_counters":initial_counters,
        "schedule_sha256":digest(&schedule)?,
        "state_sha256":digest(&executor.graph.export()?)?,
        "pending_tasks":executor.graph.pending_completion_tasks(),
        "key_lookup_calls":report["key_lookup_calls"],
        "stats":report["stats"],"stable_ports":report["stable_ports"],
        "cell_ownership_stats":report["cell_ownership"]["stats"],
        "scoped_executor":report["scoped_executor"],
        "port_completion":report["port_completion"],
        "source_stage_counts":report["steps"].as_array().unwrap().iter().fold(
            std::collections::BTreeMap::<String,usize>::new(), |mut counts,step| {
                *counts.entry(step["ruleset"].as_str().unwrap().to_owned()).or_default() += 1;
                counts
            }),
    });
    let path = PathBuf::from(&args[1]);
    std::fs::write(path, serde_json::to_vec_pretty(&output)?)?;
    println!("{mode}: {} Runs, {elapsed:.6} s (prefix only)", executor.steps.len());
    Ok(())
}
