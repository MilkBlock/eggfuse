//! Offline completion compilation. Never runs the input workload implicitly.
use eggfuse_cell_runtime::{checksum::artifact_digest, iterative::Catalog,program::Program};
use serde_json::Value;
pub fn compile(p:Program) -> Result<Value,Box<dyn std::error::Error>> {
    let mut plan=p.artifact["iterative_bake"].clone();
    Catalog::emit_ripsat_handoffs(&p,&mut plan)?;
    apply_plan(&p,plan)
}
/// Opt-in equality-parameter specialization. The ordinary completion compiler
/// remains a reproducible v4 control, including artifact compatibility checks.
pub fn compile_lazy_unions(p:Program) -> Result<Value,Box<dyn std::error::Error>> {
    let mut plan=p.artifact["iterative_bake"].clone();
    Catalog::emit_lazy_union_handoffs(&p,&mut plan)?;
    apply_plan(&p,plan)
}
pub fn compile_history_closures(p:Program, history:&Value, extra_units:usize) -> Result<Value,Box<dyn std::error::Error>> {
    let mut plan=p.artifact["iterative_bake"].clone();
    Catalog::emit_history_closures(&p,&mut plan,history,extra_units)?;
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
    // Ownership extent is part of the checked layout contract. Omitting an
    // explicit bound silently restores the four-frame default (or rejects a
    // previously valid longer fragment) on the next completion iteration.
    if let Some(limit)=old.get("max_frames") {
        raw["ownership_fragments"]["max_frames"]=limit.clone();
    }
    raw.as_object_mut().unwrap().remove("sha256");
    let mut checked=Program::parse(raw.clone())?;
    checked.prepare_cell_ownership()?;
    if had_markers {raw["ownership_markers"]=checked.cell_ownership.artifact(&checked);}
    if let Some(classes)=old.get("query_classes") {
        raw["ownership_fragments"]["query_classes"]=if classes==&Value::Bool(true) {
            Value::Bool(true)
        } else {checked.bake_query_classes()?};
    }
    Ok(())
}
pub(crate) fn run(args:Vec<String>) -> Result<(),Box<dyn std::error::Error>> {
    let opts=crate::options(args.into_iter(),&["--program","--output","--lazy-unions","--history","--extra-units"])?;
    if opts.contains_key("--extra-units") && !opts.contains_key("--history") {
        return Err("--extra-units requires --history".into());
    }
    let input=opts.get("--program").ok_or("--program required")?;
    let out=std::path::Path::new(opts.get("--output").ok_or("--output required")?);
    let p=Program::parse(serde_json::from_slice(&std::fs::read(input)?)?)?;
    let raw=if let Some(path)=opts.get("--history") {
        if opts.contains_key("--lazy-unions") {return Err("history closure lowering selects its checked union policy".into());}
        let history:Value=serde_json::from_slice(&std::fs::read(path)?)?;
        let history=history.get("completed_history").unwrap_or(&history);
        let extra=opts.get("--extra-units").map(|s|s.parse::<usize>()).transpose()?.unwrap_or(p.iterative.limits.per_round);
        compile_history_closures(p,history,extra)?
    } else { match opts.get("--lazy-unions").map(String::as_str) {
        None | Some("false") => compile(p)?,
        Some("true") => compile_lazy_unions(p)?,
        _ => return Err("--lazy-unions must be true or false".into()),
    }};
    std::fs::create_dir(out)?;
    std::fs::write(out.join("program.json"),serde_json::to_vec_pretty(&raw)?)?;
    std::fs::write(out.join("cell-egraph.json"),serde_json::to_vec_pretty(&raw["iterative_bake"]["completion"])?)?;
    Ok(())
}
