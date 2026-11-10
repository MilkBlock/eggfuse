//! Offline completion compilation. Never runs the input workload implicitly.
use eggfuse_cell_runtime::{checksum::artifact_digest, iterative::Catalog,program::Program};
use serde_json::Value;
pub fn compile(p:Program) -> Result<Value,Box<dyn std::error::Error>> {
    let mut plan=p.artifact["iterative_bake"].clone();
    Catalog::emit_ripsat_handoffs(&p,&mut plan)?;
    apply_plan(&p,plan)
}
pub(crate) fn apply_plan(p:&Program,plan:Value) -> Result<Value,Box<dyn std::error::Error>> {
    let original=&p.artifact;
    let mut raw=p.artifact.clone();
    raw.as_object_mut().unwrap().remove("ownership_markers");
    raw.as_object_mut().unwrap().remove("ownership_fragments");
    raw["iterative_bake"]=plan;
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into();
    let p=Program::parse(raw)?;
    let completion=crate::state_plan::completion(&p)?;
    // Direct completion owns its projection proof. Do not enable unrelated
    // legacy history layouts globally on an artifact that did not select them.
    let state_plan=original["iterative_bake"].get("state_plan")
        .map(|_|crate::state_plan::compile(&p)).transpose()?;
    let mut raw=p.artifact;
    raw["iterative_bake"]["completion"]=completion;
    if let Some(state_plan)=state_plan {raw["iterative_bake"]["state_plan"]=state_plan;}
    restore_ownership(original,&mut raw)?;
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into();
    Program::parse(raw.clone())?;
    Ok(raw)
}

/// Recompile optional ownership code against the changed execution catalog.
/// Prior observations select the same fragments; they are not new performance
/// evidence. Every body, substitution and class mask is rederived and checked.
fn restore_ownership(original:&Value,raw:&mut Value) -> Result<(),Box<dyn std::error::Error>> {
    use eggfuse_cell_runtime::{checksum::artifact_digest_excluding_root,graph::cell_ownership::composition};
    let excluded=["sha256","iterative_bake","ownership_markers","ownership_fragments"];
    if artifact_digest_excluding_root(original,&excluded)!=artifact_digest_excluding_root(raw,&excluded) {
        return Err("completion changed authoritative source while recompiling ownership".into());
    }
    let had_markers=original.get("ownership_markers").is_some();
    let Some(old)=original.get("ownership_fragments") else {
        if had_markers {
            raw.as_object_mut().unwrap().remove("sha256");
            let mut p=Program::parse(raw.clone())?; p.prepare_cell_ownership()?;
            raw["ownership_markers"]=p.cell_ownership.artifact(&p);
        }
        return Ok(());
    };
    raw["ownership_fragments"]=serde_json::json!({"schema":old["schema"],
        "source":composition::source_digest(raw),"fragments":old["fragments"],
        "selection_provenance":{"previous_source":old["source"],"new_observations":false}});
    raw.as_object_mut().unwrap().remove("sha256");
    let mut checked=Program::parse(raw.clone())?;
    checked.prepare_cell_ownership()?;
    if had_markers {raw["ownership_markers"]=checked.cell_ownership.artifact(&checked);}
    if old.get("query_classes").is_some() {raw["ownership_fragments"]["query_classes"]=checked.bake_query_classes()?;}
    Ok(())
}
pub(crate) fn run(args:Vec<String>) -> Result<(),Box<dyn std::error::Error>> {
    let opts=crate::options(args.into_iter(),&["--program","--output"])?;
    let input=opts.get("--program").ok_or("--program required")?;
    let out=std::path::Path::new(opts.get("--output").ok_or("--output required")?);
    let p=Program::parse(serde_json::from_slice(&std::fs::read(input)?)?)?;
    let raw=compile(p)?;
    std::fs::create_dir(out)?;
    std::fs::write(out.join("program.json"),serde_json::to_vec_pretty(&raw)?)?;
    std::fs::write(out.join("cell-egraph.json"),serde_json::to_vec_pretty(&raw["iterative_bake"]["completion"])?)?;
    Ok(())
}
