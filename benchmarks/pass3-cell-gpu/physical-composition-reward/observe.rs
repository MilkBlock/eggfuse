// Learn only from publications in the training corpus. For a held-out source,
// report its compiler-checked layout interface without executing a single Run.
#[path = "integral_runtime.rs"]
mod replay;
use eggfuse_cell_runtime::{executor::Executor, graph::IntegralCatalog, program::Program};
use serde_json::{Value, json};
use std::fs;

fn phases(control: &Value, names: &mut Vec<String>) {
    if let Some(s) = control.get("run").and_then(Value::as_str)
        && !names.iter().any(|n| n == s)
    {
        names.push(s.into());
    }
    if let Some(o) = control.as_object() {
        for value in o.values() {
            phases(value, names);
        }
    }
    if let Some(a) = control.as_array() {
        for value in a {
            phases(value, names);
        }
    }
}
fn install(
    p: Program,
    phases: &[String],
    catalog: &IntegralCatalog,
) -> Result<Executor, Box<dyn std::error::Error>> {
    let mut exe = replay::executor(p, "primary", phases)?;
    exe.use_integral_member_views()?;
    exe.use_integral_neighbors()?;
    exe.use_integral_library(catalog.clone())?;
    Ok(exe)
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args_os().skip(1).collect::<Vec<_>>();
    let p = Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let mut names = Vec::new();
    phases(&p.artifact["recipe"]["control"], &mut names);
    let mut base = IntegralCatalog {
        schema: "eggfuse-integral-bake/v2".into(),
        source: p.artifact["sha256"].as_str().ok_or("source sha")?.into(),
        phases: names.clone(),
        max_members: 64,
        edges: vec![],
    };
    if args[1] == "train" {
        let mut exe = install(p, &names, &base)?;
        exe.graph.collect_integral_compositions();
        exe.execute()?;
        let obs = exe.graph.integral_composition_report();
        let result = json!({"catalog":base,"training":obs["training"],"runs":exe.steps.len()});
        fs::write(&args[2], serde_json::to_vec(&result)?)?;
    } else if args[1] == "compile" {
        base.edges = serde_json::from_slice(&fs::read(&args[3])?)?;
        let _ = install(p, &names, &base)?;
        fs::write(&args[2], serde_json::to_vec(&base)?)?;
    } else {
        return Err("expected train or compile".into());
    }
    Ok(())
}
