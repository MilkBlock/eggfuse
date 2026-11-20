use eggfuse_cell_runtime::{executor::Executor,forest_policy::{ForestInputs,ForestPolicy},graph::Graph,program::Program};
use std::io::{BufRead,Write};
use std::time::Instant;
use sha2::{Digest,Sha256};
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args_os().skip(1).collect();let bytes=std::fs::read(&a[0])?;
    let digest=format!("{:x}",Sha256::digest(&bytes));let p=Program::parse(serde_json::from_slice(&bytes)?)?;
    let model:ForestPolicy=serde_json::from_slice(&std::fs::read(&a[1])?)?;
    let plan:ForestInputs=serde_json::from_slice(&std::fs::read(&a[2])?)?;
    let stdin=std::io::stdin();let mut input=stdin.lock();let mut out=std::io::stdout().lock();
    loop{
        let mut e=Executor::new(Graph::new(p.clone())?,false);writeln!(out,"ready")?;out.flush()?;
        let mut cmd=String::new();input.read_line(&mut cmd)?;if cmd.trim()!="run"{break;}
        let start=Instant::now();let pred=e.use_cpu_forest_policy(&model,&plan,&digest,true)?;
        let verified=Instant::now();e.execute()?;let end=Instant::now();let r=e.precomputed_report().unwrap();
        writeln!(out,"{}",serde_json::json!({"validation_ms":(verified-start).as_secs_f64()*1000.,"inference_ms":(end-verified).as_secs_f64()*1000.,
            "active":pred["active"],"hash":pred["certificate_sha256"],"forward_ms":pred["forward_ms"],"rhs":r["rhs"],
            "children":r["children"].as_array().unwrap().len()}))?;out.flush()?;
        let mut state=Vec::new();e.graph.write_export(&mut state)?;writeln!(out,"{:x}",Sha256::digest(state))?;out.flush()?;
    }
    Ok(())
}
