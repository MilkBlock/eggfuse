//! Batch matched-source takeovers from one audited, installed catalog.
//! Observation frequency ranks candidates; typed queries prove their wiring.
use eggfuse_cell_runtime::{checksum::{artifact_digest, canonical}, graph::Graph,
    graph::cell_ownership::composition::source_digest, program::Program};
use serde_json::{Value, json};
use std::{collections::BTreeSet, error::Error, fs};

fn observation<'a>(raw:&Value, trace:&'a Value)->Result<&'a Value,String> {
    let catalog=&trace["catalog_trace"];
    if trace["all_saved_run_checks_equal"]!=true || trace["runs"].as_u64().is_none_or(|n|n==0)
        || catalog["schema"]!="eggfuse-ownership-catalog-trace/v1"
        || catalog["catalog_sha256"]!=raw["sha256"]
        || catalog["source"]!=source_digest(raw) {
        return Err("audited observations of this exact installed catalog required".into());
    }
    Ok(&catalog["multi_source"])
}

fn main()->Result<(),Box<dyn Error>> {
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    if a.len()<4 {return Err("usage: bake_observed_joins PROGRAM TRACE OUTPUT BUDGET...".into());}
    let raw:Value=serde_json::from_slice(&fs::read(&a[0])?)?;
    let trace:Value=serde_json::from_slice(&fs::read(&a[1])?)?;
    let observed=observation(&raw,&trace)?;
    let g=Graph::new_with_local_congruence(Program::parse(raw.clone())?)?;
    let compiled=g.compile_multi_source_candidates(&raw["sha256"],observed)?;
    let mut ranked=compiled["candidates"].as_array().ok_or("missing typed candidates")?.iter()
        .filter(|c|c["observed"]["applications"].as_u64().unwrap_or(0)>=2).collect::<Vec<_>>();
    ranked.sort_by(|a,b|b["observed"]["applications"].as_u64().cmp(&a["observed"]["applications"].as_u64())
        .then_with(||canonical(&a["compiled"]["pattern"],false).cmp(&canonical(&b["compiled"]["pattern"],false))));
    fs::create_dir_all(&a[2])?;
    fs::write(format!("{}/compiled.json",a[2]),serde_json::to_vec_pretty(&compiled)?)?;
    for budget in &a[3..] {
        let budget:usize=budget.parse()?;
        if budget==0 || budget>4096 {return Err("budget must be in 1..=4096".into());}
        let mut candidate=raw.clone();
        let mut patterns=raw.get("ownership_dual_sources").map(|v|v["patterns"].as_array()
            .cloned().ok_or("invalid installed patterns")).transpose()?.unwrap_or_default();
        let before=patterns.len();
        let mut seen=patterns.iter().map(|v|canonical(v,false)).collect::<BTreeSet<_>>();
        let mut added=0;
        for row in &ranked {
            if added==budget {break;}
            let pattern=&row["compiled"]["pattern"];
            if seen.insert(canonical(pattern,false)) {patterns.push(pattern.clone());added+=1;}
        }
        candidate["ownership_dual_sources"]=json!({"schema":"dual-source-patterns/v1",
            "source":source_digest(&raw),"patterns":patterns});
        candidate.as_object_mut().unwrap().remove("ownership_markers");
        candidate.as_object_mut().unwrap().remove("sha256");
        candidate["sha256"]=artifact_digest(&candidate).into();
        let mut checked=Program::parse(candidate)?;
        checked.prepare_cell_ownership()?;
        // Installation must keep all known ordinary suffix transitions. Added
        // joins inherit their bounded suffix closure through the same loader.
        let old=&g.program.cell_ownership.composition;
        let new=&checked.cell_ownership.composition;
        if old.transitions.iter().any(|edge|!new.transitions.contains(edge))
            || old.shapes.iter().enumerate().any(|(i,s)|new.shapes.get(i)!=Some(s)) {
            return Err("lost an installed suffix transition".into());
        }
        let dir=format!("{}/budget{budget}",a[2]);fs::create_dir(&dir)?;
        fs::write(format!("{dir}/program.json"),serde_json::to_vec_pretty(&checked.artifact)?)?;
        let report=json!({"source_program":raw["sha256"],"candidate_program":checked.artifact["sha256"],
            "audited_runs":trace["runs"],"trace_digest":artifact_digest(&trace),
            "typed_candidates":compiled["candidates"].as_array().unwrap().len(),
            "repeated_candidates":ranked.len(),"budget":budget,"existing_patterns":before,"added_patterns":added,
            "seed_transitions_preserved":true,"scope":"typed matched-source takeover candidates; counts are not savings",
            "obligations":"live anchors, current equalities, residual queries, pending work and source-local retirement remain runtime checks"});
        fs::write(format!("{dir}/selection.json"),serde_json::to_vec_pretty(&report)?)?;
        println!("{report}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_another_catalog_even_when_its_source_recipe_matches() {
        let raw=json!({"sha256":"catalog-a","recipe":{}});
        let mut trace=json!({"all_saved_run_checks_equal":true,"runs":2,"catalog_trace":{
            "schema":"eggfuse-ownership-catalog-trace/v1","catalog_sha256":"catalog-a",
            "source":source_digest(&raw),"multi_source":{}}});
        assert!(observation(&raw,&trace).is_ok());
        trace["catalog_trace"]["catalog_sha256"]=json!("catalog-b");
        assert!(observation(&raw,&trace).is_err());
        trace["catalog_trace"]["catalog_sha256"]=json!("catalog-a");
        trace["all_saved_run_checks_equal"]=json!(false);
        assert!(observation(&raw,&trace).is_err());
    }
}
