//! Driver compiled into the pinned integral member-storage implementation.
#[path="integral_runtime.rs"] mod replay;
use eggfuse_cell_runtime::{executor::Executor,graph::IntegralCatalog,program::Program,transfer_audit as audit,checksum::artifact_digest};
use serde_json::{Value,json};
use std::{fs,path::Path,time::Instant};
type R<T>=Result<T,Box<dyn std::error::Error>>;
fn phases(j:&Value,names:&mut Vec<String>){
    if let Some(s)=j.get("run").and_then(Value::as_str){if !names.iter().any(|n|n==s){names.push(s.into());}}
    if let Some(o)=j.as_object(){for x in o.values(){phases(x,names);}}
    if let Some(a)=j.as_array(){for x in a{phases(x,names);}}
}
fn main()->R<()>{
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    let p=Program::parse(serde_json::from_slice(&fs::read(&a[0])?)?)?;
    let out=Path::new(&a[1]);fs::create_dir(out)?;
    let mut names=Vec::new();phases(&p.artifact["recipe"]["control"],&mut names);
    let mut catalog=IntegralCatalog{schema:"eggfuse-integral-bake/v2".into(),source:p.artifact["sha256"].as_str().unwrap().into(),phases:names.clone(),max_members:64,edges:vec![]};
    let exec=|cat:&IntegralCatalog|->R<Executor>{
        let mut e=replay::executor(p.clone(),"primary",&names)?;
        e.use_integral_member_views()?;e.use_integral_neighbors()?;e.use_integral_library(cat.clone())?;Ok(e)
    };
    if a[2]=="learn"{
        let mut history=Vec::new();
        for _ in 0..4{
            let mut e=exec(&catalog)?;e.graph.collect_integral_compositions();
            e.execute()?;
            let observation=e.graph.integral_composition_report();let next=eggfuse_cell_compiler::integral_bake::next(&catalog,&observation,8)?;
            history.push(json!({"units":catalog.edges.len(),"next":next.edges.len(),"runs":e.steps.len(),"layout_switches":observation["layout_switches"]}));
            if next.edges.len()==catalog.edges.len(){break;}catalog=next;
        }
        fs::write(out.join("library.json"),serde_json::to_vec(&catalog)?)?;
        fs::write(out.join("history.json"),serde_json::to_vec(&history)?)?;
        fs::write(out.join("phases"),names.join(","))?;
        println!("{}",json!({"history":history,"frozen":catalog.edges.len()}));return Ok(())
    }
    catalog=serde_json::from_slice(&fs::read(&a[3])?)?;
    let mut e=exec(&catalog)?;let detailed=a[2]=="audit";
    let mode=a[4].parse::<u8>()?;
    let mask=if a[5]=="all"{None}else{Some(serde_json::from_slice(&fs::read(&a[5])?)?)};
    e.graph.configure_storage_trial(mode,mask,a[2]!="timing");
    let mut views=Vec::new();
    let start=Instant::now();
    let mut checks=Vec::new();
    loop{
        let before=e.steps.len();
        if detailed{audit::take_digests();audit::take_write_digests();audit::take_resume_digests();audit::set_active(true);audit::enable_write_audit();}
        e.execute_until(Some(before+1))?;
        if e.steps.len()==before{break;}
        e.graph.transfer_completed_owners()?;e.graph.compact_source_record_capacity();e.graph.compact_retired_prefixes()?;e.graph.compact_integral_ports()?;
        if detailed{
            views.push(e.graph.check_integral_trial_views()?);
            let s=e.steps.last().unwrap();
            checks.push(json!([s.ruleset,s.path,s.iterations,s.epoch,s.executed_bindings,s.changed,
                audit::take_digests(),audit::take_write_digests(),audit::take_resume_digests(),
                artifact_digest(&e.graph.export()?)]));
        }
    }
    let ms=start.elapsed().as_secs_f64()*1000.;
    fs::write(out.join("result.json"),serde_json::to_vec(&json!({"inference_ms":ms,"runs":e.steps.len(),"integral":e.integral_report(),
        "physical":e.graph.physical_record_counts(),"graph":artifact_digest(&e.graph.export()?),"stage_checks":checks,"view_checks":views,"admissions":e.graph.trial_admissions()}))?)?;
    Ok(())
}
