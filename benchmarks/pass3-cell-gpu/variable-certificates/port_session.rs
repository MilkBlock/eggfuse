use eggfuse_cell_runtime::{executor::Executor,forest_policy::{ForestInputs,ForestPolicy},graph::Graph,program::Program};
use std::io::{BufRead,Write};
use sha2::{Digest,Sha256};
use std::time::Instant;

fn main()->Result<(),Box<dyn std::error::Error>>{
    let args:Vec<_>=std::env::args_os().skip(1).collect();
    let source=std::fs::read(&args[0])?;let digest=format!("{:x}",Sha256::digest(&source));
    let program=Program::parse(serde_json::from_slice(&source)?)?;
    let model:ForestPolicy=serde_json::from_slice(&std::fs::read(&args[1])?)?;
    let plans:Vec<ForestInputs>=args[2..].iter().map(|p|serde_json::from_slice(&std::fs::read(p).unwrap()).unwrap()).collect();
    let stdin=std::io::stdin();let out=std::io::stdout();let mut out=out.lock();
    writeln!(out,"ready")?;out.flush()?;
    for line in stdin.lock().lines(){
        let tag=line?;if tag=="stop"{break;}let arm:usize=tag.parse()?;
        let mut runtime=Executor::new(Graph::new(program.clone())?,false);
        let begin=Instant::now();let info=runtime.use_cpu_forest_policy(&model,&plans[arm],&digest,true)?;
        let forward=begin.elapsed().as_secs_f64()*1000.;
        runtime.execute()?;let total=begin.elapsed().as_secs_f64()*1000.;
        let report=runtime.precomputed_report().unwrap();
        let mut graph=Vec::new();runtime.graph.write_export(&mut graph)?;
        writeln!(out,"{}",serde_json::json!({"total_ms":total,"setup_ms":forward,"ports_ms":info["ports_ms"],
                 "children":report["children"].as_array().unwrap().len(),"digest":format!("{:x}",Sha256::digest(graph)),
                 "header":info["certificate_sha256"]}))?;out.flush()?;
    }
    Ok(())
}
