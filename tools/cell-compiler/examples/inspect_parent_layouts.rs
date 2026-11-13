//! Offline typed projection coverage. No workload execution or equality inference.
use eggfuse_cell_runtime::program::{Program,Arg,Op};
use serde_json::{Value,json};
use std::{error::Error,fs};
fn main()->Result<(),Box<dyn Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=3 {return Err("usage: inspect_parent_layouts PROGRAM COMPLETED_TRACE OUTPUT".into());}
    let mut p=Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    p.prepare_cell_ownership()?;
    let trace:Value=serde_json::from_slice(&fs::read(&args[1])?)?;
    if trace["completed_history"]["program_sha256"]!=p.artifact["sha256"] {return Err("trace program differs".into());}
    if trace["all_saved_run_checks_equal"]!=true || trace["completed_history"]["dropped_events"]!=0 {
        return Err("complete audited trace required".into());
    }
    let mut uses=vec![0usize;p.templates.len()];
    for e in trace["completed_history"]["events"].as_array().ok_or("missing events")? {
        let frame=&e["execution"]["frame"];
        if frame["parent"].is_object() { uses[frame["template"].as_u64().ok_or("invalid template")? as usize]+=1; }
    }
    let rows=p.templates.iter().enumerate().filter(|(i,_)|uses[*i]>0).map(|(i,t)| {
        let ports=&p.cell_ownership.markers[i].program.slots;
        let mut used=std::collections::BTreeSet::new();
        let mut read=|arg:&Arg| { if let Arg::Slot(slot)=arg {used.insert(*slot);} };
        for op in t.ops.iter() {
            match op {
                Op::Copy(_,a)=>read(a),
                Op::Let(_,_,args)|Op::Hide(_,args,_)=>args.iter().for_each(&mut read),
                Op::Set(_,args,v)=>{args.iter().for_each(&mut read);read(v);},
                Op::Union(a,b)=>{read(a);read(b);},
                Op::Panic=>{},
            }
        }
        let fields=t.parent_columns.iter().map(|(&slot,&column)|json!({
            "slot":slot,"column":column,"sort":t.sorts[slot],
            "symbol":ports.get(slot).copied().flatten(),"read_by_template_operation":used.contains(&slot)
        })).collect::<Vec<_>>();
        json!({"template":i,"name":t.name,"parented_completion_observations":uses[i],
            "fully_mapped":fields.iter().all(|f|!f["symbol"].is_null()),"fields":fields})
    }).collect::<Vec<_>>();
    fs::write(&args[2],serde_json::to_vec_pretty(&json!({"scope":"typed parent projection coverage at observed completions; static mapping does not prove live component binding or retirement",
        "program_sha256":p.artifact["sha256"],"templates":rows}))?)?;
    Ok(())
}
