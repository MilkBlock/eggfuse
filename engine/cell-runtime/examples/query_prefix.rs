//! Bounded, untimed work/Run diagnostic. Does not claim workload completion.
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};
#[cfg(feature = "allocation-metrics")]
#[path = "../src/allocation_metrics.rs"]
mod allocation_metrics;
#[cfg(feature = "allocation-metrics")]
#[global_allocator]
static ALLOCATOR: allocation_metrics::Meter = allocation_metrics::Meter;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [program, output, runs, workers, grain, mode @ ..] = args.as_slice() else {
        return Err("expected PROGRAM OUTPUT RUNS WORKERS GRAIN [canonical|stable]".into());
    };
    let program = Program::parse(serde_json::from_slice(&std::fs::read(program)?)?)?;
    let graph = match mode {
        [] => Graph::new_with_local_congruence(program)?,
        [mode] if mode == "stable" => Graph::new_with_local_congruence(program)?,
        [mode] if mode == "canonical" => Graph::new(program)?,
        _ => return Err("expected at most one backend: canonical or stable".into()),
    };
    let mut e = Executor::new(graph, false);
    let workers: usize = workers.parse()?;
    #[cfg(feature = "sparse-cells")]
    if workers != 0 { e.use_query_workers(workers, grain.parse()?)?; }
    #[cfg(not(feature = "sparse-cells"))]
    if workers != 0 { let _ = grain; return Err("query workers require sparse-cells".into()); }
    let runs = runs.parse()?;
    #[cfg(feature = "allocation-metrics")]
    let before = allocation_metrics::begin();
    e.execute_until(Some(runs))?;
    #[cfg(feature = "allocation-metrics")]
    let allocations = allocation_metrics::end(before);
    let output = std::path::Path::new(output);
    std::fs::create_dir(output)?;
    std::fs::write(output.join("state.json"), serde_json::to_vec(&e.graph.export()?)?)?;
    let report = e.report();
    #[cfg(feature = "allocation-metrics")]
    let report = {
        let mut report = report;
        report["allocations"] = allocations.report();
        report
    };
    std::fs::write(output.join("report.json"), serde_json::to_vec(&report)?)?;
    Ok(())
}
