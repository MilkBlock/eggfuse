use eggfuse_cell_runtime::{executor::Executor,graph::Graph,program::Program};
use std::io::{BufRead,Write};
use sha2::{Digest,Sha256};
use std::time::Instant;
fn main()->Result<(),Box<dyn std::error::Error>>{
    let args:Vec<_>=std::env::args_os().skip(1).collect();
    let p=Program::parse(serde_json::from_slice(&std::fs::read(&args[0])?)?)?;
    let mut out=std::io::stdout().lock();writeln!(out,"ready")?;out.flush()?;
    for s in std::io::stdin().lock().lines(){
        let path=s?;if path=="stop"{break;}
        let mut e=Executor::new(Graph::new(p.clone())?,false);
        let begin=Instant::now();
        if path!="exact"{e.use_single_witness(std::path::Path::new(&path))?;}
        let init=begin.elapsed().as_secs_f64()*1000.;
        e.execute()?;let elapsed=begin.elapsed().as_secs_f64()*1000.;
        let mut data=Vec::new();e.graph.write_export(&mut data)?;
        writeln!(out,"{}",serde_json::json!({"ms":elapsed,"init_ms":init,"graph":format!("{:x}",Sha256::digest(data)),
           "single":e.single_report().as_ref().map(|s|s["committed"].as_array().unwrap().len())}))?;out.flush()?;
    }
    Ok(())
}
