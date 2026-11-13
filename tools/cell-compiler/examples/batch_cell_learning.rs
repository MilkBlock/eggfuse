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
    if a.len()<2 {return Err("batch_cell_learning prepare SUITE OUTPUT CASE... | apply OUTPUT | verify OUTPUT | observe OUTPUT | apply-passive ROOT VARIANT | check-passive ROOT VARIANT".into());}
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
    } else if a[0]=="apply-passive" || a[0]=="check-passive" {
        if !(a.len()==3 || (a.len()==4 && a[0]=="check-passive" && matches!(a[3].as_str(),"template-fields"|"template-overlap"|"witness-trace"))) {return Err("apply-passive/check-passive ROOT VARIANT [template-fields|template-overlap|witness-trace]".into());}
        let root=Path::new(&a[1]);let variant=root.join(&a[2]);
        let manifest=read(root.join("manifest.json"))?;
        let mut reports=vec![];
        for case in manifest["cases"].as_array().unwrap() {
            let name=case["case"].as_str().unwrap();let source=root.join(name);let dir=variant.join(name);
            let seed=read(source.join("candidate.json"))?;
            let proposal=read(dir.join("selection.json"))?;
            if proposal["source_program"]!=seed["sha256"] || proposal["selection"]["source"]!=source_digest(&seed) {
                return Err("passive selection seed mismatch".into());
            }
            if a[0]=="apply-passive" {
                let mut old=Program::parse(seed.clone())?;old.prepare_cell_ownership()?;
                let mut raw=seed;raw["ownership_fragments"]=proposal["selection"].clone();
                raw.as_object_mut().unwrap().remove("ownership_markers");
                raw.as_object_mut().unwrap().remove("sha256");raw["sha256"]=artifact_digest(&raw).into();
                let mut checked=Program::parse(raw.clone())?;checked.prepare_cell_ownership()?;
                let edges=|p:&Program| {
                    let plan=&p.cell_ownership.composition;
                    plan.transitions.iter().map(|(key,target)|artifact_digest(&json!({
                        "source":plan.shapes[key.shape],"hop":key.hop,"target":plan.shapes[*target]
                    }))).collect::<std::collections::BTreeSet<_>>()
                };
                if !edges(&old).is_subset(&edges(&checked)) {return Err("lost a seed transition".into());}
                write(dir.join("candidate.json"),&raw)?;
                reports.push(json!({"case":name,"program":raw["sha256"],"all_seed_transitions_preserved":true,
                    "shapes":checked.cell_ownership.composition.shapes.len(),"transitions":checked.cell_ownership.composition.transitions.len()}));
                eprintln!("compiled {name}");
            } else {
                let observation=read(source.join("catalog-observation.json"))?;
                if observation["source_program"]!=seed["sha256"] || observation["all_saved_run_checks_equal"]!=true {
                    return Err("audited seed observation required".into());
                }
                let checks=observation["run_checks"].as_array().ok_or("missing Run checks")?;
                // Earlier observations did not save the terminal non-Run effects.
                // Reconstruct that one check without repeating all baseline exports.
                let terminal_path=source.join("terminal-check.json");
                let terminal=if terminal_path.exists() {
                    let cached=read(&terminal_path)?;
                    if cached["source_program"]!=seed["sha256"] {return Err("terminal cache seed mismatch".into());}
                    cached["check"].clone()
                } else {
                    let mut base=executor(seed.clone())?;base.execute_until(Some(checks.len()))?;
                    let check=step(&mut base,checks.len()+1)?;
                    if base.steps.len()!=checks.len() || check["graph"]!=observation["final_state"] {return Err("terminal control differs".into());}
                    write(&terminal_path,&json!({"source_program":seed["sha256"],"check":check}))?;check
                };
                let raw=read(dir.join("candidate.json"))?;
                if raw["ownership_fragments"]!=proposal["selection"] {return Err("candidate differs from selection".into());}
                let mut target=executor(raw)?;
                if a.get(3).is_some_and(|a|a=="witness-trace") {target.graph.trace_ownership_catalog(16)?;}
                if a.get(3).is_some_and(|a|matches!(a.as_str(),"template-fields"|"template-overlap")) {target.graph.use_template_stable_fields()?;}
                if a.get(3).is_some_and(|a|a=="template-overlap") {
                    target.graph.use_parallel_port_guards(2,1)?;
                    target.graph.use_completion_read_batches(16)?;
                    target.graph.use_overlapped_completion()?;
                }
                for (i,expected) in checks.iter().enumerate() {
                    let observed=step(&mut target,i+1)?;
                    if target.steps.len()!=i+1 || observed!=*expected {
                        write(dir.join("failure.json"),&json!({"run":i+1,"expected":expected,"observed":observed}))?;
                        return Err(format!("{name}: differs at Run {}",i+1).into());
                    }
                }
                if step(&mut target,checks.len()+1)?!=terminal || target.steps.len()!=checks.len() {return Err("terminal check differs".into());}
                reports.push(json!({"case":name,"runs":checks.len(),"all_saved_run_checks_equal":true,
                    "program":target.graph.program.artifact["sha256"],"source_storage":target.graph.retained_cell_storage(),
                    "catalog_trace":if a.get(3).is_some_and(|a|a=="witness-trace") {Some(target.graph.ownership_catalog_trace()?)} else {None},
                    "completion_batches":target.graph.completion_batch_report(),
                    "stable_ports":target.graph.stable_port_report(),
                    "final_state":artifact_digest(&target.graph.export()?)}));
                if a.get(3).is_some_and(|a|a=="witness-trace") {
                    let report=reports.last_mut().unwrap();
                    let saturation=report["catalog_trace"]["saturation"].take();
                    report["catalog_trace"]=json!({"saturation":saturation});
                    for field in ["source_storage","stable_ports","completion_batches"] {report.as_object_mut().unwrap().remove(field);}
                    let tmp=dir.join("witness-checked.json.tmp");
                    write(&tmp,report)?;
                    fs::rename(tmp,dir.join("witness-checked.json"))?;
                }
                eprintln!("checked {name}: {} Runs",checks.len());
            }
        }
        write(variant.join(if a[0]=="apply-passive" {"compiled.json"} else if a.get(3).is_some_and(|a|a=="witness-trace") {"witness-checked.json"} else {"checked.json"}),&json!({"cases":reports}))?;
    } else if a[0]=="verify" || a[0]=="observe" {
        let observe=a[0]=="observe";
        let root=Path::new(&a[1]);let manifest=read(root.join("manifest.json"))?;
        let mut reports=vec![];
        for case in manifest["cases"].as_array().unwrap() {
            let name=case["case"].as_str().unwrap();let dir=root.join(name);
            let mut base=executor_control(read(dir.join("baseline.json"))?,false)?;
            let mut target=executor(read(dir.join("candidate.json"))?)?;
            if observe {target.graph.trace_ownership_catalog(16)?;}
            let mut checks=vec![];
            let mut runs=0;
            loop {
                let b=step(&mut base,runs+1)?;let t=step(&mut target,runs+1)?;
                if base.steps.len()!=target.steps.len() || b!=t {
                    write(dir.join("failure.json"),&json!({"run":runs+1,"before":b,"after":t}))?;
                    return Err(format!("{name} differs at Run {}",runs+1).into());
                }
                if base.steps.len()==runs {break;}
                if observe {checks.push(t);}
                runs+=1;
            }
            let report=json!({"case":name,"runs":runs,"run_graph_rhs_writes_equal":true,
                "baseline":base.graph.program.artifact["sha256"],"candidate":target.graph.program.artifact["sha256"],
                "final_state":artifact_digest(&target.graph.export()?),
                "scope":"same-source runtime regression check; not native egglog semantic admission"});
            if observe {
                write(dir.join("catalog-observation.json"),&json!({
                    "source_program":target.graph.program.artifact["sha256"],
                    "all_saved_run_checks_equal":true,"runs":runs,"run_checks":checks,
                    "catalog_trace":target.graph.ownership_catalog_trace()?,
                    "source_storage":target.graph.retained_cell_storage(),
                    "ownership_storage":target.graph.ownership_storage_trace(),
                    "final_state":report["final_state"]}))?;
            }
            write(dir.join("verification.json"),&report)?;reports.push(report);eprintln!("verified {name}: {runs} Runs");
        }
        write(root.join("verification.json"),&json!({"cases":reports}))?;
    } else {return Err("unknown mode".into());}
    Ok(())
}
