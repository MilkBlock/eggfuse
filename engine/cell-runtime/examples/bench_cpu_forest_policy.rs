#[cfg(feature = "precomputed-forest")]
fn main() -> Result<(), Box<dyn std::error::Error>> {
    use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};
    use serde_json::json;
    use sha2::{Digest, Sha256};
    use std::time::Instant;

    let paths: Vec<_> = std::env::args_os().skip(1).collect();
    if paths.len() != 3 {
        return Err("expected PROGRAM WEIGHTS INPUTS".into());
    }
    let source = std::fs::read(&paths[0])?;
    let digest = format!("{:x}", Sha256::digest(&source));
    let program = Program::parse(serde_json::from_slice(&source)?)?;
    let model = serde_json::from_slice(&std::fs::read(&paths[1])?)?;
    let inputs = serde_json::from_slice(&std::fs::read(&paths[2])?)?;
    let mut samples = [Vec::new(), Vec::new()];
    let mut bindings = [0, 0];
    let mut neural_children = 0;
    let mut graph_digest = None;
    for trial in 0..12 {
        for arm in [trial % 2, 1 - trial % 2] {
            let mut runtime = Executor::new(Graph::new(program.clone())?, false);
            let start = Instant::now();
            if arm == 1 {
                runtime.use_cpu_forest_policy(&model, &inputs, &digest, true)?;
            }
            runtime.execute()?;
            let ms = start.elapsed().as_secs_f64() * 1000.;
            if trial >= 2 {
                samples[arm].push(ms);
            }
            let report = runtime.report();
            bindings[arm] = report["steps"]
                .as_array()
                .ok_or("missing source steps")?
                .iter()
                .map(|s| {
                    s["executed_bindings"]
                        .as_u64()
                        .expect("source binding count")
                })
                .sum::<u64>();
            if let Some(forest) = runtime.precomputed_report() {
                neural_children = forest["children"]
                    .as_array()
                    .ok_or("missing forest provenance")?
                    .len();
            }
            let mut bytes = Vec::new();
            runtime.graph.write_export(&mut bytes)?;
            let hash = Sha256::digest(bytes);
            if *graph_digest.get_or_insert(hash) != hash {
                return Err("final graphs differ".into());
            }
        }
    }
    println!(
        "{}",
        json!({"exact":{"samples_ms":samples[0],"rhs":bindings[0]},
        "with_policy":{"samples_ms":samples[1],"rhs":bindings[1],"neural_children":neural_children}})
    );
    Ok(())
}

#[cfg(not(feature = "precomputed-forest"))]
fn main() {
    eprintln!("Enable the precomputed-forest feature for this comparison.");
    std::process::exit(2);
}
