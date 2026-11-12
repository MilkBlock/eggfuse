//! Run a frozen affine input projection against actual freshly initialized Cells.
//! Address plans are fixture-bound; this is not a cross-stage execution hook.
use eggfuse_cell_runtime::{compiler, graph::Graph, program::Program, value::Value};
use serde_json::{Value as J, json};
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, env, fs, io, time::Instant};
fn err(s: impl ToString) -> io::Error {
    io::Error::other(s.to_string())
}
fn numbers(j: &J) -> Result<Vec<f32>, io::Error> {
    j.as_array()
        .ok_or_else(|| err("array required"))?
        .iter()
        .map(|x| {
            x.as_f64()
                .map(|x| x as f32)
                .ok_or_else(|| err("number required"))
        })
        .collect()
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let [input, output] = args.as_slice() else {
        return Err(err("INPUT OUTPUT required").into());
    };
    let input: J = serde_json::from_slice(&fs::read(input)?)?;
    if input["schema"] != "cell-affine-initial-projection/v1" {
        return Err(err("schema mismatch").into());
    }
    let mut results = vec![];
    for case in input["cases"].as_array().ok_or_else(|| err("cases"))? {
        let source = case["source"].as_str().ok_or_else(|| err("source"))?;
        if case["source_sha256"] != format!("{:x}", Sha256::digest(source.as_bytes())) {
            return Err(err("source digest mismatch").into());
        }
        let artifact = compiler::compile(
            eggfuse_bake::device_frontend::core("native-projection", source)?,
            &BTreeSet::new(),
        )
        .map_err(err)?;
        let graph = Graph::new(Program::parse(artifact).map_err(err)?).map_err(err)?;
        let plan = &input["plans"][case["plan"].as_str().ok_or_else(|| err("plan key"))?];
        let bias = numbers(&plan["bias"])?;
        let metadata = numbers(&plan["metadata"])?;
        let weight = plan["weight"]
            .as_array()
            .ok_or_else(|| err("weights"))?
            .iter()
            .map(numbers)
            .collect::<Result<Vec<_>, _>>()?;
        let mut reads = vec![];
        for r in case["reads"].as_array().ok_or_else(|| err("reads"))? {
            let cell = u32::try_from(r["cell"].as_u64().ok_or_else(|| err("cell"))?)?;
            let slot = usize::try_from(r["slot"].as_u64().ok_or_else(|| err("slot"))?)?;
            let template = usize::try_from(r["template"].as_u64().ok_or_else(|| err("template"))?)?;
            if graph
                .cells
                .get(&cell)
                .is_none_or(|c| c.template != template)
            {
                return Err(err("expired or mismatched input owner").into());
            }
            reads.push((cell, slot));
        }
        if weight.len() != reads.len() * 4 || weight.iter().any(|r| r.len() != bias.len()) {
            return Err(err("projection shape mismatch").into());
        }
        let mut state = vec![0f32; bias.len() + metadata.len()];
        let start = Instant::now();
        for _ in 0..100 {
            state[..bias.len()].copy_from_slice(&bias);
            state[bias.len()..].copy_from_slice(&metadata);
            for (i, (cell, slot)) in reads.iter().enumerate() {
                let Value::Int(value) = graph.slot(*cell, *slot).map_err(err)? else {
                    return Err(err("integer slot required").into());
                };
                let v = value as f32;
                let basis = [v / 4., (v / 4.).powi(2), v.sin(), v.cos() - 1.];
                for (b, row) in basis.iter().zip(&weight[i * 4..i * 4 + 4]) {
                    for (dst, w) in state[..bias.len()].iter_mut().zip(row) {
                        *dst += b * w;
                    }
                }
            }
            std::hint::black_box(&state);
        }
        results.push(json!({"id":case["id"],"state":state,"slot_reads":reads.len(),"projection_nanoseconds":start.elapsed().as_nanos() as f64/100.}));
    }
    fs::write(
        output,
        serde_json::to_vec(
            &json!({"scope":"live Graph.slot -> frozen affine projection, fresh initial instances only","model_sha256":input["model_sha256"],"cases":results}),
        )?,
    )?;
    Ok(())
}
