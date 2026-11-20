use eggfuse_cell_runtime::{executor::Executor,graph::Graph,ordinary_witness as neural,program::Program};
use std::{io::{BufRead,Write},time::Instant};
use sha2::{Digest,Sha256};
use serde_json::{Value as J,json};
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args().collect();
    let program=Program::parse(serde_json::from_slice(&std::fs::read(&a[1])?)?)?;
    let plan=std::fs::read(&a[2])?;let weights=std::fs::read(&a[3])?;
    let mut out=std::io::BufWriter::new(std::io::stdout().lock());
    for line in std::io::stdin().lock().lines(){
        let req:J=serde_json::from_str(&line?)?;
        let mode=req["mode"].as_str().unwrap();let audit=req["audit"].as_bool()==Some(true);
        neural::configure(&program,&plan,&weights,mode,req["radius"].as_u64().unwrap() as u32,req["residual"].as_bool()==Some(true),
                          req["cap"].as_u64().unwrap() as usize,audit)?;
        let mut ex=Executor::new(Graph::new(program.clone())?,false);
        eggfuse_cell_runtime::transfer_audit::set_active(audit);
        if audit{eggfuse_cell_runtime::transfer_audit::enable_write_audit();eggfuse_cell_runtime::transfer_audit::enable_events();}
        let start=Instant::now();ex.execute()?;let ms=start.elapsed().as_secs_f64()*1000.;
        let mut state=vec![];ex.graph.write_export(&mut state)?;
        let mut v=json!({"ms":ms,"runs":ex.steps.len(),"state_sha":format!("{:x}",Sha256::digest(&state)),"report":neural::report()});
        if audit{
            eggfuse_cell_runtime::transfer_audit::set_active(false);
            v["rhs"]=serde_json::to_value(eggfuse_cell_runtime::transfer_audit::take_digests())?;
            v["writes"]=serde_json::to_value(eggfuse_cell_runtime::transfer_audit::take_write_digests())?;
            v["resumes"]=serde_json::to_value(eggfuse_cell_runtime::transfer_audit::take_resume_digests())?;
            if let Some(events)=eggfuse_cell_runtime::transfer_audit::take_events(){let mut unions=vec![];
                for evs in events{for e in evs{if e[0]=="union"{unions.push(e)}}}
                v["unions"]=json!(unions);
            }
        }
        writeln!(out,"{}",v)?;out.flush()?;
    }
    Ok(())
}
