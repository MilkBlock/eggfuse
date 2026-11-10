//! Allocation-only diagnostic for executing versus discovering Cell programs.
//! The counter changes execution cost; do not use this executable for timing.
#[path = "../src/allocation_metrics.rs"]
mod allocation_metrics;
#[global_allocator]
static ALLOCATOR: allocation_metrics::Meter = allocation_metrics::Meter;

use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [program, output, mode] = args.as_slice() else {
        return Err("expected PROGRAM OUTPUT normal|learn".into());
    };
    if !matches!(mode.as_str(), "normal" | "learn") { return Err("unknown mode".into()); }
    let program = Program::parse(serde_json::from_slice(&std::fs::read(program)?)?)?;
    let mut exec = Executor::new(Graph::new_with_local_congruence(program)?, false);
    if mode == "learn" { exec.collect_iterative_pairs(); }
    let start = allocation_metrics::begin();
    exec.execute_until(None)?;
    let allocations = allocation_metrics::end(start).report();
    let output = std::path::Path::new(output);
    std::fs::create_dir(output)?;
    let mut report = exec.report();
    report["allocation_diagnostic"] = allocations;
    report["discovery_enabled"] = (mode == "learn").into();
    std::fs::write(output.join("report.json"), serde_json::to_vec(&report)?)?;
    exec.graph.write_export(&mut std::fs::File::create(output.join("state.json"))?)?;
    if mode == "learn" {
        let history = exec.iterative_training().completion_history(&exec.graph.program);
        std::fs::write(output.join("cell-history.json"), serde_json::to_vec(&history)?)?;
    }
    Ok(())
}
