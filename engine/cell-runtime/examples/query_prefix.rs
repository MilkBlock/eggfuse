//! Bounded, untimed work/Run diagnostic. Does not claim workload completion.
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [program, output, runs, workers, grain] = args.as_slice() else {
        return Err("expected PROGRAM OUTPUT RUNS WORKERS GRAIN".into());
    };
    let program = Program::parse(serde_json::from_slice(&std::fs::read(program)?)?)?;
    let mut e = Executor::new(Graph::new_with_local_congruence(program)?, false);
    let workers: usize = workers.parse()?;
    #[cfg(feature = "sparse-cells")]
    if workers != 0 { e.use_query_workers(workers, grain.parse()?)?; }
    #[cfg(not(feature = "sparse-cells"))]
    if workers != 0 { let _ = grain; return Err("query workers require sparse-cells".into()); }
    e.execute_until(Some(runs.parse()?))?;
    let output = std::path::Path::new(output);
    std::fs::create_dir(output)?;
    std::fs::write(output.join("state.json"), serde_json::to_vec(&e.graph.export()?)?)?;
    std::fs::write(output.join("report.json"), serde_json::to_vec(&e.report())?)?;
    Ok(())
}
