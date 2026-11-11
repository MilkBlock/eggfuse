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
    let [program, output, runs, workers, grain, options @ ..] = args.as_slice() else {
        return Err("expected PROGRAM OUTPUT RUNS WORKERS GRAIN [canonical|stable] [--repair-ports] [--entry-publications] [--cell-absorption] [--cell-entry-reverse]".into());
    };
    let mut mode = None;
    let mut repair_ports = false;
    let mut entry_publications = false;
    let mut absorption = false;
    let mut reverse = false;
    for option in options {
        match option.as_str() {
            "canonical" | "stable" if mode.is_none() => mode = Some(option.as_str()),
            "--repair-ports" if !repair_ports => repair_ports = true,
            "--entry-publications" if !entry_publications => entry_publications = true,
            "--cell-absorption" if !absorption => absorption = true,
            "--cell-entry-reverse" if !reverse => reverse = true,
            _ => return Err(format!("unknown or repeated prefix option: {option}").into()),
        }
    }
    let mode = mode.unwrap_or("stable");
    let program = Program::parse(serde_json::from_slice(&std::fs::read(program)?)?)?;
    let graph = match mode {
        "stable" => Graph::new_with_local_congruence(program)?,
        "canonical" if repair_ports => Graph::new_with_repair_ports(program)?,
        "canonical" => Graph::new(program)?,
        _ => unreachable!(),
    };
    let mut e = Executor::new(graph, false);
    if absorption {
        #[cfg(feature = "cell-absorption")]
        e.use_cell_absorption()?;
        #[cfg(not(feature = "cell-absorption"))]
        return Err("Cell absorption requires cell-absorption".into());
    }
    if entry_publications {
        #[cfg(feature = "sparse-cells")]
        e.use_entry_publications()?;
        #[cfg(not(feature = "sparse-cells"))]
        return Err("entry publications require sparse-cells".into());
    }
    if reverse {
        #[cfg(feature = "cell-entry-reverse")]
        e.use_cell_entry_reverse()?;
        #[cfg(not(feature = "cell-entry-reverse"))]
        return Err("Cell Entry selection requires cell-entry-reverse".into());
    }
    let workers: usize = workers.parse()?;
    let grain: usize = grain.parse()?;
    #[cfg(feature = "sparse-cells")]
    if workers != 0 { e.use_query_workers(workers, grain)?; }
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
    let mut report = e.report();
    report["prefix_configuration"] = serde_json::json!({
        "backend":mode, "requested_repair_ports":repair_ports,
        "requested_entry_publications":entry_publications,
        "requested_runs":runs, "workers":workers, "grain":grain,
    });
    if absorption { report["prefix_configuration"]["requested_cell_absorption"] = true.into(); }
    if reverse { report["prefix_configuration"]["requested_cell_entry_reverse"] = true.into(); }
    #[cfg(feature = "allocation-metrics")]
    let report = {
        let mut report = report;
        report["allocations"] = allocations.report();
        report
    };
    std::fs::write(output.join("report.json"), serde_json::to_vec(&report)?)?;
    Ok(())
}
