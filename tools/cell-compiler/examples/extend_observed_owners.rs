//! Extend an installed ownership catalog from passive observations, never replace its seed.
use eggfuse_cell_runtime::{program::Program, checksum::{artifact_digest, canonical}, graph::cell_ownership::composition};
use serde_json::{Value, json};
use std::{collections::BTreeSet, fs};
fn select(raw:&mut Value, trace:&Value, budget:usize)->Result<Value,Box<dyn std::error::Error>> {
    let observed=&trace["catalog_trace"];
    if trace["all_saved_run_checks_equal"]!=true || observed["schema"]!="eggfuse-ownership-catalog-trace/v1"
        || trace["runs"].as_u64().is_none_or(|runs|runs==0)
        || raw["sha256"].as_str().is_none() || observed["catalog_sha256"]!=raw["sha256"]
        || observed["source"]!=composition::source_digest(raw) {
        return Err("source-bound audited passive catalog trace required".into());
    }
    // A source without a selected catalog still has the implicit singleton
    // shapes. Start from that empty transition language rather than requiring
    // an unrelated workload's catalog just to bootstrap learning.
    if raw.get("ownership_fragments").is_none() {
        let schema = match raw.get("ownership_markers").map(|m|m["schema"].as_str()) {
            None | Some(Some("eggfuse-ownership-markers/v5")) => "eggfuse-ownership-fragments/v2",
            Some(Some("eggfuse-ownership-markers/v4")) => "eggfuse-ownership-fragments/v1",
            _ => return Err("unknown ownership marker address version".into()),
        };
        raw["ownership_fragments"]=json!({"schema":schema,"source":observed["source"],
            "max_frames":8,"fragments":[]});
    }
    let fragments=raw["ownership_fragments"]["fragments"].as_array_mut().ok_or("installed fragments required")?;
    let before=fragments.len();
    // Loading a selected path installs all its prefixes. Keep maximal paths,
    // preserving the exact seed language without spending budget twice.
    let seed=fragments.clone();
    fragments.retain(|f|!seed.iter().any(|other| {
        let a=f["hops"].as_array().unwrap();let b=other["hops"].as_array().unwrap();
        f["root"]==other["root"] && b.len()>a.len() && b.starts_with(a)
    }));
    let maximal_seed=fragments.len();
    let mut existing=fragments.iter().map(|f|canonical(f,false)).collect::<BTreeSet<_>>();
    let mut rows=observed["records"].as_array().ok_or("missing observations")?.iter().filter(|r|
        r["matched_births"].as_u64().unwrap_or(0)>1 && r["available_shared_inputs"].as_u64().unwrap_or(0)>0
        && r["fragment"]["hops"].as_array().is_some_and(|h|h.len()<8)).collect::<Vec<_>>();
    // Ranking only: proposed reuse/compiled instruction handles is not saved work.
    rows.sort_by(|a,b| {
        let benefit=|r:&Value|r["available_shared_inputs"].as_u64().unwrap() as u128;
        let cost=|r:&Value|r["static_instruction_handles"].as_u64().unwrap_or(0).max(1) as u128;
        (benefit(b)*cost(a)).cmp(&(benefit(a)*cost(b)))
            .then_with(||canonical(&a["fragment"],false).cmp(&canonical(&b["fragment"],false)))
    });
    let mut chosen=vec![];let mut alternatives=BTreeSet::new();
    let mut replaced_prefixes=0;
    let mut capacity_rejections=0;
    for row in rows {
        if chosen.len()==budget {break;}
        let f=&row["fragment"];
        let key=canonical(f,false);
        if existing.contains(&key) {continue;}
        let hops=f["hops"].as_array().unwrap();
        // A maximal path already installs all its prefixes. Extending a seed
        // therefore replaces its entry, even when the catalog is at capacity.
        if fragments.iter().any(|old|old["root"]==f["root"]
            && old["hops"].as_array().unwrap().starts_with(hops)) {continue;}
        let subsumed=|old:&Value|old["root"]==f["root"]
            && hops.starts_with(old["hops"].as_array().unwrap());
        let replaces=fragments.iter().filter(|old|subsumed(old)).count();
        if fragments.len()+1-replaces>256 {capacity_rejections+=1;continue;}
        let last=hops.last().unwrap();
        // Alternative Entries for one observed source/consumer overlap. Admit
        // one candidate per group rather than adding their support as savings.
        if !alternatives.insert((row["source_shape"].as_u64(),last["rule"].as_u64())) {continue;}
        fragments.retain(|old| {
            if subsumed(old) {existing.remove(&canonical(old,false));false} else {true}
        });
        replaced_prefixes+=replaces;
        existing.insert(key);fragments.push(f.clone());chosen.push(row.clone());
    }
    let extent=raw["ownership_fragments"]["max_frames"].as_u64().unwrap_or(4).max(8);
    raw["ownership_fragments"]["max_frames"]=json!(extent);
    raw.as_object_mut().unwrap().remove("ownership_markers");
    let report=json!({"scope":"passive proposal selection; not measured savings",
        "seed_fragments":before,"maximal_seed_fragments":maximal_seed,"added_fragments":chosen.len(),
        "replaced_prefixes":replaced_prefixes,"capacity_rejections":capacity_rejections,"max_frames":extent,
        "trace_catalog_sha256":observed["catalog_sha256"],"selected":chosen,
        "obligations":["typed Entry substitutions rechecked by Program loader", "runtime source/visibility/lifetime checks unchanged", "all seed paths retained through maximal prefix coverage; changed dispatch contexts require execution admission"]});
    raw["ownership_fragments"]["selection_provenance"]=report.clone();
    raw.as_object_mut().unwrap().remove("sha256");raw["sha256"]=artifact_digest(raw).into();
    Ok(report)
}
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=4 {return Err("usage: extend_observed_owners PROGRAM TRACE BUDGET NEW_DIR".into());}
    let mut raw:Value=serde_json::from_slice(&fs::read(&args[0])?)?;
    let trace:Value=serde_json::from_slice(&fs::read(&args[1])?)?;
    let mut seed=Program::parse(raw.clone())?;seed.prepare_cell_ownership()?;
    let mut report=select(&mut raw,&trace,args[2].parse()?)?;
    let mut checked=Program::parse(raw)?;checked.prepare_cell_ownership()?;
    let edges=|p:&Program| {
        let plan=&p.cell_ownership.composition;
        plan.transitions.iter().map(|(key,target)|canonical(&json!({
            "source":plan.shapes[key.shape],"hop":key.hop,"target":plan.shapes[*target]
        }),false)).collect::<BTreeSet<_>>()
    };
    let old=edges(&seed);let new=edges(&checked);
    if !old.is_subset(&new) {return Err("lost a checked seed transition".into());}
    report["all_seed_transitions_preserved"]=json!(true);
    fs::create_dir(&args[3])?;
    fs::write(format!("{}/program.json",args[3]),serde_json::to_vec_pretty(&checked.artifact)?)?;
    fs::write(format!("{}/selection.json",args[3]),serde_json::to_vec_pretty(&report)?)?;
    println!("seed={} added={} checked_shapes={} checked_transitions={}",report["seed_fragments"],report["added_fragments"],checked.cell_ownership.composition.shapes.len(),checked.cell_ownership.composition.transitions.len());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn singleton_catalog_bootstraps_only_from_matching_audited_source() {
        for (marker,version) in [(None,"v2"),(Some("eggfuse-ownership-markers/v4"),"v1"),
            (Some("eggfuse-ownership-markers/v5"),"v2")] {
            let mut raw=json!({"sha256":"test-catalog","recipe":{}});
            if let Some(schema)=marker {raw["ownership_markers"]=json!({"schema":schema});}
            let mut trace=json!({"all_saved_run_checks_equal":true,"runs":1,"catalog_trace":{"catalog_sha256":raw["sha256"],
                "schema":"eggfuse-ownership-catalog-trace/v1","source":composition::source_digest(&raw),
                "records":[{"source_shape":0,"fragment":{"root":0,"hops":[{"source_frame":0,"rule":1,"entry":0,"op":0}]},
                    "matched_births":4,"available_shared_inputs":4,"static_instruction_handles":2}]}});
            let before=raw.clone();
            trace["all_saved_run_checks_equal"]=json!(false);
            assert!(select(&mut raw,&trace,32).is_err());assert_eq!(raw,before);
            trace["all_saved_run_checks_equal"]=json!(true);
            trace["catalog_trace"]["catalog_sha256"]=json!("stale-catalog");
            assert!(select(&mut raw,&trace,32).is_err());assert_eq!(raw,before);
            trace["catalog_trace"]["catalog_sha256"]=raw["sha256"].clone();
            trace["catalog_trace"]["source"]=json!("different");
            assert!(select(&mut raw,&trace,32).is_err());assert_eq!(raw,before);
            trace["catalog_trace"]["source"]=composition::source_digest(&raw).into();
            let report=select(&mut raw,&trace,32).unwrap();
            assert_eq!(report["seed_fragments"],0);assert_eq!(report["added_fragments"],1);
            assert_eq!(raw["ownership_fragments"]["schema"],format!("eggfuse-ownership-fragments/{version}"));
        }
    }
    #[test]
    fn full_catalog_can_extend_a_seed_after_rejecting_an_unrelated_path() {
        let hop=|rule|json!({"source_frame":0,"rule":rule,"entry":0,"op":0});
        let seed=(0..256).map(|root|json!({"root":root,"hops":[hop(1)]})).collect::<Vec<_>>();
        let mut raw=json!({"sha256":"test-catalog","recipe":{},"ownership_fragments":{"fragments":seed.clone()}});
        let row=|root,hops,benefit|json!({"source_shape":root,"fragment":{"root":root,"hops":hops},
            "matched_births":benefit,"available_shared_inputs":benefit,"static_instruction_handles":2});
        let trace=json!({"all_saved_run_checks_equal":true,"runs":1,"catalog_trace":{"catalog_sha256":raw["sha256"],
            "schema":"eggfuse-ownership-catalog-trace/v1","source":composition::source_digest(&raw),
            "records":[row(999,vec![hop(2)],100),row(7,vec![hop(1),hop(3)],10)]}});
        let result=select(&mut raw,&trace,32).unwrap();
        assert_eq!(result["added_fragments"],1);
        assert_eq!(result["replaced_prefixes"],1);
        assert_eq!(result["capacity_rejections"],1);
        let paths=raw["ownership_fragments"]["fragments"].as_array().unwrap();
        assert_eq!(paths.len(),256);
        assert!(paths.iter().any(|f|f["root"]==7 && f["hops"].as_array().unwrap().len()==2));
        for old in seed {
            assert!(paths.iter().any(|new|new["root"]==old["root"]
                && new["hops"].as_array().unwrap().starts_with(old["hops"].as_array().unwrap())));
        }
    }
    #[test]
    fn maximal_seed_retains_prefixes_and_does_not_sum_alternative_anchors() {
        let hop=|rule,op|json!({"source_frame":0,"rule":rule,"entry":0,"op":op});
        let a=hop(1,0);let b=hop(2,0);
        let seed=vec![json!({"root":0,"hops":[a.clone()]}),json!({"root":0,"hops":[a.clone(),b]})];
        let mut raw=json!({"sha256":"test-catalog","recipe":{},"ownership_fragments":{"fragments":seed}});
        let row=|op,benefit|json!({"source_shape":7,"fragment":{"root":0,"hops":[a.clone(),hop(3,op)]},
            "matched_births":benefit,"available_shared_inputs":benefit,"static_instruction_handles":2});
        let trace=json!({"all_saved_run_checks_equal":true,"runs":1,"catalog_trace":{"catalog_sha256":raw["sha256"],
            "schema":"eggfuse-ownership-catalog-trace/v1","source":composition::source_digest(&raw),
            "records":[row(0,10),row(1,5)]}});
        let result=select(&mut raw,&trace,32).unwrap();
        assert_eq!(result["maximal_seed_fragments"],1);
        assert_eq!(result["added_fragments"],1);
        let paths=raw["ownership_fragments"]["fragments"].as_array().unwrap();
        for old in seed {
            assert!(paths.iter().any(|new|new["root"]==old["root"]
                && new["hops"].as_array().unwrap().starts_with(old["hops"].as_array().unwrap())));
        }
        assert_eq!(result["selected"][0]["matched_births"],10);
        let mut invalid=trace;invalid["all_saved_run_checks_equal"]=json!(false);
        assert!(select(&mut raw,&invalid,1).is_err());
    }
}
