//! Benchmark driver for the unmodified default Rust Cell executor. The audit build
//! is separate; no research provider is installed or linked on the timed path.
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};
#[global_allocator]
static ALLOCATOR: eggfuse_cell_runtime::RuntimeAllocator = eggfuse_cell_runtime::RuntimeAllocator;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    io::{BufRead, Write},
    time::Instant,
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let source = std::env::args_os().nth(1).ok_or("expected program.json")?;
    let program = Program::parse(serde_json::from_slice(&std::fs::read(source)?)?)?;
    let mut out = std::io::BufWriter::new(std::io::stdout().lock());
    for line in std::io::stdin().lock().lines() {
        let request: Value = serde_json::from_str(&line?)?;
        let audit = request["audit"] == true;
        if audit && !cfg!(feature = "audit") {
            return Err("use the audit binary".into());
        }
        let mut executor = Executor::new(Graph::new(program.clone())?, false);
        #[cfg(feature = "audit")]
        if audit {
            use eggfuse_cell_runtime::transfer_audit as trace;
            trace::set_active(true);
            trace::enable_write_audit();
            trace::enable_events();
        }
        let start = Instant::now();
        executor.execute()?;
        let ms = start.elapsed().as_secs_f64() * 1000.;
        let mut graph = Vec::new();
        executor.graph.write_export(&mut graph)?;
        let summary = executor.report();
        let steps = summary["steps"].as_array().ok_or("missing source steps")?;
        let rhs: u64 = steps
            .iter()
            .map(|s| s["executed_bindings"].as_u64().expect("source count"))
            .sum();
        let mut record = json!({"ms":ms,"state_sha":format!("{:x}",Sha256::digest(&graph)),"rhs_count":rhs,"runs":steps.len()});
        #[cfg(feature = "audit")]
        if audit {
            use eggfuse_cell_runtime::transfer_audit as trace;
            trace::set_active(false);
            record["rhs"] = json!(trace::take_digests());
            record["writes"] = json!(trace::take_write_digests());
            record["resumes"] = json!(trace::take_resume_digests());
            record["unions"] = json!(
                trace::take_events()
                    .ok_or("missing source events")?
                    .into_iter()
                    .map(|events| events
                        .into_iter()
                        .filter(|event| event[0] == "union")
                        .collect::<Vec<_>>())
                    .collect::<Vec<_>>()
            );
            record["schedule"] = json!(
                steps
                    .iter()
                    .map(|s| json!([
                        s["ruleset"],
                        s["epoch"],
                        s["path"],
                        s["iterations"],
                        s["executed_bindings"],
                        s["changed"]
                    ]))
                    .collect::<Vec<_>>()
            );
        }
        writeln!(out, "{}", record)?;
        out.flush()?;
    }
    Ok(())
}
