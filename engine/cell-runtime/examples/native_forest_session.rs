//! One authoritative CPU Cell graph per trial. Source and compiled plans stay in memory.
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::time::Instant;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args_os()
        .nth(1)
        .ok_or("expected compiled source program")?;
    let bytes = std::fs::read(path)?;
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let program = Program::parse(serde_json::from_slice(&bytes)?)?;
    let layout = eggfuse_cell_runtime::precomputed_forest::SealedLayout::parse(&std::fs::read(
        std::env::args_os()
            .nth(2)
            .ok_or("expected compiled forest layout")?,
    )?)?;
    let stdin = std::io::stdin();
    let mut input = stdin.lock();
    let mut out = std::io::BufWriter::new(std::io::stdout().lock());
    loop {
        let mut runtime = Executor::new(Graph::new(program.clone())?, false);
        writeln!(out, "ready")?;
        out.flush()?;
        let mut size = [0u8; 4];
        input.read_exact(&mut size)?;
        let size = u32::from_le_bytes(size) as usize;
        if size == 0 {
            break;
        }
        let mut words = vec![0; size];
        input.read_exact(&mut words)?;
        let start = Instant::now();
        runtime.use_precomputed_words(&layout, &words, &digest)?;
        let validated = Instant::now();
        runtime.execute()?;
        let done = Instant::now();
        let result = runtime.precomputed_report().unwrap();
        writeln!(
            out,
            "{}",
            json!({"validation_ms":(validated-start).as_secs_f64()*1000.,
            "inference_ms":(done-validated).as_secs_f64()*1000.,"rhs":result["rhs"],"children":result["children"].as_array().unwrap().len()})
        )?;
        out.flush()?;
        // Graph verification follows the measured reply, before the next pristine graph is exposed.
        let mut data = Vec::new();
        runtime.graph.write_export(&mut data)?;
        writeln!(out, "{:x}", Sha256::digest(data))?;
        out.flush()?;
    }
    Ok(())
}
