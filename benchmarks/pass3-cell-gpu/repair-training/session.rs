use eggfuse_cell_runtime::{executor::Executor,graph::{Graph,trial},program::Program,precomputed_forest::SealedLayout};
use serde_json::{Value as J,json};
use std::{io::{Read,BufRead,Write},time::Instant};
use sha2::{Sha256,Digest};
fn main()->Result<(),Box<dyn std::error::Error>>{
    let path=std::env::args_os().nth(1).ok_or("source program required")?;
    let bytes=std::fs::read(path)?;
    let source_digest=format!("{:x}",Sha256::digest(&bytes));
    let program=Program::parse(serde_json::from_slice(&bytes)?)?;
    let layout=std::env::args_os().nth(2).map(|p|std::fs::read(p)).transpose()?
        .map(|v|SealedLayout::parse(&v)).transpose()?;
    let mut input=std::io::stdin().lock();let mut out=std::io::BufWriter::new(std::io::stdout().lock());
    loop{
        let mut line=String::new();if input.read_line(&mut line)?==0{break;}
        let request:J=serde_json::from_str(&line)?;
        let names:Vec<String>=serde_json::from_value(request["tables"].clone())?;
        let mask=program.tables.iter().map(|t|names.contains(&t.name)).collect();
        let weights:trial::Weights=serde_json::from_value(request["weights"].clone())?;
        let audit=request["audit"].as_bool()==Some(true);
        trial::configure(request["mode"].as_str().unwrap(),mask,weights,audit);
        let mut ex=Executor::new(Graph::new_with_repair_ports(program.clone())?,false);
        if audit {
            eggfuse_cell_runtime::transfer_audit::set_active(true);
            eggfuse_cell_runtime::transfer_audit::enable_write_audit();
            eggfuse_cell_runtime::transfer_audit::enable_events();
        }
        writeln!(out,"ready")?;out.flush()?;
        let mut n=[0u8;4];input.read_exact(&mut n)?;
        let mut words=vec![0;u32::from_le_bytes(n) as usize];input.read_exact(&mut words)?;
        let start=Instant::now();
        if let Some(l)=&layout{ex.use_precomputed_words(l,&words,&source_digest)?;}
        else if !words.is_empty(){return Err("no layout for supplied forest".into());}
        let validated=Instant::now();ex.execute()?;let end=Instant::now();
        writeln!(out,"{}",json!({"ms":(end-validated).as_secs_f64()*1e3,
                                  "validation_ms":(validated-start).as_secs_f64()*1e3}))?;out.flush()?;
        let mut state=Vec::new();ex.graph.write_export(&mut state)?;
        let mut result=json!({"state_sha":format!("{:x}",Sha256::digest(&state)),"trial":trial::report(),
            "repair_key_probes":ex.graph.maintenance.repair_key_probes,"candidate_checks":ex.graph.maintenance.repair_candidate_checks,
            "fact_decodes":ex.graph.fact_decode_calls.get(),"port_decodes":ex.graph.fact_decode_ports.get(),"runs":ex.steps.len(),
            "unions":ex.graph.stats.unions,"forest":ex.precomputed_report(),"port_report":ex.graph.repair_port_report()});
        if audit{
            eggfuse_cell_runtime::transfer_audit::set_active(false);
            result["rhs"]=serde_json::to_value(eggfuse_cell_runtime::transfer_audit::take_digests())?;
            result["writes"]=serde_json::to_value(eggfuse_cell_runtime::transfer_audit::take_write_digests())?;
            result["resumes"]=serde_json::to_value(eggfuse_cell_runtime::transfer_audit::take_resume_digests())?;
            if let Some(events)=eggfuse_cell_runtime::transfer_audit::take_events(){
                let value=serde_json::to_value(events)?;
                let unions:Vec<&J>=value.as_array().unwrap().iter().flat_map(|r|r.as_array().unwrap().iter())
                    .filter(|e|e[0]=="union").collect();
                result["ordered_unions"]=serde_json::to_value(unions)?;
            }
        }
        writeln!(out,"{}",result)?;out.flush()?;
    }
    Ok(())
}
