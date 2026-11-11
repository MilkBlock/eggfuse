//! Native oracle and capability preflight for benchmarks/upstream-suite/run.py.
use eggfuse_cell_runtime::{compiler, program::Program};
use serde_json::json;
use std::{collections::BTreeSet, time::Instant};
#[global_allocator]
static ALLOCATOR: eggfuse_cell_runtime::RuntimeAllocator = eggfuse_cell_runtime::RuntimeAllocator;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().collect::<Vec<_>>();
    let source = std::fs::read_to_string(&args[2])?;
    if args[1] == "inspect" {
        let core = eggfuse_bake::device_frontend::core(&args[2], &source)?;
        let p = Program::parse(compiler::compile(core, &BTreeSet::new())?)?;
        println!(
            "{}",
            json!({"tables":p.tables.iter().map(|t| &t.name).collect::<Vec<_>>()})
        );
    } else if args[1] == "native" {
        let repeat = args[4].parse::<usize>()?;
        let mut times = vec![];
        let mut inference = vec![];
        for _ in 0..repeat {
            let start = Instant::now();
            let mut eg = egglog::EGraph::default();
            eg.parse_and_run_program(Some(args[2].clone()), &source)?;
            eg.serialize(egglog::SerializeConfig::default());
            times.push(start.elapsed().as_secs_f64());
            std::mem::forget(eg); // Same timed lifecycle as egglog/benches/common.rs.
            let mut eg = egglog::EGraph::default();
            let commands = eg.parse_program(Some(args[2].clone()), &source)?;
            let at = commands
                .iter()
                .position(|c| matches!(c, egglog::ast::Command::RunSchedule(_)))
                .ok_or("no schedule")?;
            eg.run_program(commands[..at].to_vec())?;
            let start = Instant::now();
            eg.run_program(commands[at..].to_vec())?;
            inference.push(start.elapsed().as_secs_f64());
        }
        // Untimed, separate oracle: no proof mode and no source rewriting.
        let mut eg = egglog::EGraph::default();
        eg.parse_and_run_program(Some(args[2].clone()), &source)?;
        std::fs::write(
            &args[3],
            serde_json::to_vec(&json!({"rows":eg.device_snapshot()?}))?,
        )?;
        println!(
            "{}",
            json!({"native_parse_execute_serialize_seconds":times,
            "native_schedule_and_checks_seconds":inference, "tables":eg.get_function_names()})
        );
    } else {
        return Err("expected inspect or native".into());
    }
    Ok(())
}
