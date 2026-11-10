//! Offline completion compilation. Never runs the input workload implicitly.
use eggfuse_cell_runtime::{checksum::artifact_digest, iterative::Catalog,program::Program};
use serde_json::Value;
pub fn compile(p:Program) -> Result<Value,Box<dyn std::error::Error>> {
    let mut plan=p.artifact["iterative_bake"].clone();
    Catalog::emit_ripsat_handoffs(&p,&mut plan)?;
    let mut raw=p.artifact;
    raw["iterative_bake"]=plan;
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into();
    let p=Program::parse(raw)?;
    let completion=crate::state_plan::completion(&p)?;
    let state_plan=crate::state_plan::compile(&p)?;
    let mut raw=p.artifact;
    raw["iterative_bake"]["completion"]=completion;
    raw["iterative_bake"]["state_plan"]=state_plan;
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into();
    Program::parse(raw.clone())?;
    Ok(raw)
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
