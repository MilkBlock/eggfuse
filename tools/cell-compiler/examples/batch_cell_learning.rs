//! Shared Cell learning across frozen pass3 inputs; never merge instance IDs.
use eggfuse_cell_runtime::{compiler,program::Program,graph::Graph,executor::Executor,
    checksum::artifact_digest,graph::cell_ownership::composition::{source_digest,select_profile_with_budget},
    transfer_audit as audit};
use serde_json::{Value,json};
use sha2::{Digest,Sha256};
use std::{fs,path::Path,error::Error};
type Result<T>=std::result::Result<T,Box<dyn Error>>;
fn read(p:impl AsRef<Path>)->Result<Value> {Ok(serde_json::from_slice(&fs::read(p)?)?)}
fn write(p:impl AsRef<Path>,v:&Value)->Result<()> {Ok(fs::write(p,serde_json::to_vec(v)?)?)}
fn executor(raw:Value)->Result<Executor> {executor_control(raw,true)}
fn executor_control(raw:Value,takeover:bool)->Result<Executor> {
    let mut g=Graph::new_with_local_congruence(Program::parse(raw)?)?;g.use_port_domains_only()?;
    let mut e=Executor::new(g,false);if takeover {e.use_completed_parent_takeover()?;}Ok(e)
}
fn step(e:&mut Executor,n:usize)->Result<Value> {
    audit::take_digests();audit::take_write_digests();
    audit::set_active(true);audit::enable_write_audit();
    let result=e.execute_until(Some(n));audit::set_active(false);result?;
    e.graph.transfer_completed_owners()?;
    Ok(json!({"graph":artifact_digest(&e.graph.export()?),"rhs":audit::take_digests(),"writes":audit::take_write_digests()}))
}
fn main()->Result<()> {
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    if a.len()<2 {return Err("batch_cell_learning prepare SUITE OUTPUT CASE... | apply OUTPUT | verify OUTPUT".into());}
    if a[0]=="prepare" {
        if a.len()<4 {return Err("prepare needs suite, output and cases".into());}
        let suite=read(&a[1])?;let base=Path::new(&a[1]).parent().unwrap();let out=Path::new(&a[2]);
        fs::create_dir_all(out)?;let mut cases=vec![];
        for name in &a[3..] {
            let case=suite["cases"].as_array().unwrap().iter().find(|c|c["name"]==*name).ok_or("unknown case")?;
            let mut bytes=vec![];
            for part in case["parts"].as_array().unwrap() {bytes.extend(fs::read(base.join(part.as_str().unwrap()))?);}
            let sha=format!("{:x}",Sha256::digest(&bytes));
            if case["sha256"]!=sha {return Err("frozen source checksum differs".into());}
            let source=String::from_utf8(bytes)?;
            let core=eggfuse_bake::device_frontend::core("batch-pass3",&source)?;
            let raw=compiler::compile(core,&Default::default())?;
            let mut p=Program::parse(raw.clone())?;p.prepare_cell_ownership()?;
            let dir=out.join(name);fs::create_dir_all(&dir)?;
            write(dir.join("baseline.json"),&raw)?;
            write(dir.join("interface.json"),&json!({"program":raw["sha256"],"profile_source":source_digest(&raw),
                "tables":raw["source_core"]["tables"],"rules":raw["recipe"]["rules"],
                "entries":p.cell_ownership.entries,"programs":p.cell_ownership.programs}))?;
            let mut e=executor(raw)?;e.graph.continue_ownership_fragment_training(16)?;e.execute()?;
            write(dir.join("profile.json"),&e.graph.ownership_fragment_profile()?)?;
            let summary=json!({"case":name,"pass":3,"source_sha256":sha,"runs":e.steps.len(),
                "program":e.graph.program.artifact["sha256"],"final_state":artifact_digest(&e.graph.export()?),
                "scope":"standalone Cell runtime; direct typed source, no input-specific marker catalog; training is not latency"});
            write(dir.join("training.json"),&summary)?;cases.push(summary);eprintln!("captured {name}");
        }
        write(out.join("manifest.json"),&json!({"schema":"cell-batched-learning/v1","cases":cases}))?;
    } else if a[0]=="apply" {
        let root=Path::new(&a[1]);let manifest=read(root.join("manifest.json"))?;
        let merged=read(root.join("pooled-profile.json"))?;
        let shared=select_profile_with_budget(&merged,1024,65536)?;
        write(root.join("shared-selection.json"),&shared)?;
        let chosen=shared["fragments"].as_array().unwrap().iter().map(|f|
            serde_json::from_value::<eggfuse_cell_runtime::graph::cell_ownership::composition::Fragment>(f.clone()))
            .collect::<std::result::Result<std::collections::BTreeSet<_>,_>>()?;
        for case in manifest["cases"].as_array().unwrap() {
            let name=case["case"].as_str().unwrap();let dir=root.join(name);
            let mut raw=read(dir.join("baseline.json"))?;
            let profile=read(dir.join("pooled-profile.json"))?;
            if profile["source"]!=source_digest(&raw) {return Err("pooled target source mismatch".into());}
            let mut selected=shared.clone();selected["source"]=profile["source"].clone();
            let mut fragments=vec![];
            for row in profile["records"].as_array().unwrap() {
                let canonical=serde_json::from_value(row["canonical_fragment"].clone())?;
                if chosen.contains(&canonical) {fragments.push(row["fragment"].clone());}
            }
            selected["fragments"]=fragments.into();
            let mut p=Program::parse(raw.clone())?;p.prepare_cell_ownership()?;
            for f in selected["fragments"].as_array().unwrap() {
                let f=serde_json::from_value(f.clone())?;
                // The seed has no fragments and the validation extent is explicit.
                p.cell_ownership.composition.max_frames=16;
                if !p.cell_ownership.composition.supports_fragment(&p,&f) {return Err(format!("unproved pooled fragment for {name}").into());}
            }
            raw["ownership_fragments"]=selected;
            raw.as_object_mut().unwrap().remove("sha256");raw["sha256"]=artifact_digest(&raw).into();
            let mut checked=Program::parse(raw.clone())?;checked.prepare_cell_ownership()?;
            write(dir.join("candidate.json"),&raw)?;
            eprintln!("compiled pooled catalog for {name}");
        }
    } else if a[0]=="verify" {
        let root=Path::new(&a[1]);let manifest=read(root.join("manifest.json"))?;
        let mut reports=vec![];
        for case in manifest["cases"].as_array().unwrap() {
            let name=case["case"].as_str().unwrap();let dir=root.join(name);
            let mut base=executor_control(read(dir.join("baseline.json"))?,false)?;
            let mut target=executor(read(dir.join("candidate.json"))?)?;
            let mut runs=0;
            loop {
                let b=step(&mut base,runs+1)?;let t=step(&mut target,runs+1)?;
                if base.steps.len()!=target.steps.len() || b!=t {
                    write(dir.join("failure.json"),&json!({"run":runs+1,"before":b,"after":t}))?;
                    return Err(format!("{name} differs at Run {}",runs+1).into());
                }
                if base.steps.len()==runs {break;}runs+=1;
            }
            let report=json!({"case":name,"runs":runs,"run_graph_rhs_writes_equal":true,
                "baseline":base.graph.program.artifact["sha256"],"candidate":target.graph.program.artifact["sha256"],
                "final_state":artifact_digest(&target.graph.export()?),
                "scope":"same-source runtime regression check; not native egglog semantic admission"});
            write(dir.join("verification.json"),&report)?;reports.push(report);eprintln!("verified {name}: {runs} Runs");
        }
        write(root.join("verification.json"),&json!({"cases":reports}))?;
    } else {return Err("unknown mode".into());}
    Ok(())
}
