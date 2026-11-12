//! Compare graph, ordered RHS and writes at every Run; report resume changes separately.
use eggfuse_cell_runtime::{program::Program,graph::Graph,executor::Executor,
    checksum::artifact_digest,transfer_audit as audit};
use serde_json::{Value,json};
use std::{fs,error::Error};
fn executor(path:&str)->Result<Executor,Box<dyn Error>> {
    let p=Program::parse(serde_json::from_slice(&fs::read(path)?)?)?;
    let mut e=Executor::new(Graph::new_with_local_congruence(p)?,false);
    e.graph.use_port_domains_only()?;e.use_completed_parent_takeover()?;Ok(e)
}
fn step(e:&mut Executor,run:usize)->Result<Value,Box<dyn Error>> {
    audit::take_digests();audit::take_write_digests();audit::take_resume_digests();
    audit::set_active(true);audit::enable_write_audit();e.execute_until(Some(run))?;audit::set_active(false);
    let effects=json!({"rhs":audit::take_digests(),"writes":audit::take_write_digests(),"resumes":audit::take_resume_digests()});
    e.graph.transfer_completed_owners()?;
    Ok(json!({"graph":artifact_digest(&e.graph.export()?),"audit":artifact_digest(&effects),"effects":effects}))
}
fn main()->Result<(),Box<dyn Error>> {
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    if a.len()!=4 {return Err("usage: audit_matched_handoffs BASE CANDIDATE SAVED_CHECKS OUTPUT".into());}
    let mut base=executor(&a[0])?;let mut candidate=executor(&a[1])?;
    let source_specialized=base.graph.program.artifact["source_core"]!=candidate.graph.program.artifact["source_core"];
    if source_specialized {
        eggfuse_cell_runtime::compiler::validate_entry_value_specialization(&base.graph.program,&candidate.graph.program)?;
    }
    let saved:Value=serde_json::from_slice(&fs::read(&a[2])?)?;
    let checks=saved["run_checks"].as_array().ok_or("saved checks missing")?;
    let mut resumes=vec![];
    for (i,expected) in checks.iter().enumerate() {
        let b=step(&mut base,i+1)?;let c=step(&mut candidate,i+1)?;
        if json!({"graph":b["graph"],"audit":b["audit"]})!=*expected {return Err(format!("baseline Run {} changed",i+1).into());}
        if b["graph"]!=c["graph"] || b["effects"]["rhs"]!=c["effects"]["rhs"] || b["effects"]["writes"]!=c["effects"]["writes"] {
            return Err(format!("candidate graph/RHS/write order differs at Run {}",i+1).into());
        }
        if b["effects"]["resumes"]!=c["effects"]["resumes"] {resumes.push(i+1);}
        if (i+1)%250==0 {eprintln!("checked {} Runs",i+1);}
    }
    base.execute()?;candidate.execute()?;
    if base.steps.len()!=checks.len() || candidate.steps.len()!=checks.len() {return Err("Run count differs".into());}
    let state=candidate.graph.export()?;
    if state!=base.graph.export()? {return Err("final exports differ".into());}
    let report=|e:&Executor|json!({"graph_work":e.graph.stats,"stage":e.report()["stage_spine"],
        "source_storage":e.graph.retained_cell_storage(),"key_lookup_calls":e.graph.key_lookup_calls.get()});
    fs::write(&a[3],serde_json::to_vec_pretty(&json!({"scope":"actual standalone Cell runtime; ordered resume history may change, graph/RHS/writes may not",
        "base_program":base.graph.program.artifact["sha256"],"program_sha256":candidate.graph.program.artifact["sha256"],
        "runs":checks.len(),"source_specialization_verified":source_specialized,"baseline_saved_checks_equal":true,"graph_rhs_writes_equal":true,
        "resume_changed_runs":resumes,"before":report(&base),"after":report(&candidate),"final_state":state}))?)?;
    Ok(())
}
