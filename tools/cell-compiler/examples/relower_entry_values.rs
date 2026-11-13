//! Keep selected Cell paths, but recompile their receipts after specialization.
use eggfuse_cell_runtime::{compiler,program::Program,iterative::Catalog,checksum::artifact_digest};
use serde_json::json;
use std::{fs,error::Error};
fn main()->Result<(),Box<dyn Error>> {
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    if a.len()<2 || a[2..].iter().any(|x|x!="--verify-only" && x!="--unit-facts" && x!="--unit-ownership" && !x.starts_with("--unit-tables=") && !x.starts_with("--ownership-catalog=")) {
        return Err("usage: relower_entry_values SOURCE OUTPUT [--verify-only] [--unit-facts] [--unit-ownership] [--unit-tables=JSON] [--ownership-catalog=PROGRAM]".into());
    }
    let owned=a[2..].iter().any(|x|x=="--unit-ownership");
    let catalog=a[2..].iter().find_map(|x|x.strip_prefix("--ownership-catalog="));
    if catalog.is_some() && !owned {return Err("ownership catalog requires --unit-ownership".into());}
    let selected=a[2..].iter().find_map(|x|x.strip_prefix("--unit-tables="));
    let unit=selected.is_some() || owned || a[2..].iter().any(|x|x=="--unit-facts");
    let validate=if unit {compiler::validate_unit_fact_specialization} else {compiler::validate_entry_value_specialization};
    let source=Program::parse(serde_json::from_slice(&fs::read(&a[0])?)?)?;
    if a[2..].iter().any(|x|x=="--verify-only") {
        let target=Program::parse(serde_json::from_slice(&fs::read(&a[1])?)?)?;
        validate(&source,&target)?;
        println!("{}",json!({"source_specialization_verified":true,"base":source.artifact["sha256"],"candidate":target.artifact["sha256"]}));
        return Ok(());
    }
    let mut raw=if let Some(path)=selected {
        let tables:Vec<usize>=serde_json::from_slice(&fs::read(path)?)?;
        compiler::specialize_unit_facts_selected(&source,&tables)?
    } else if unit {compiler::specialize_unit_facts(&source)?} else {compiler::specialize_entry_values(&source)?};
    if owned {raw["unit_fact_ownership"]=true.into();}
    let old=&source.artifact;
    // This finite migration requires stable rule/slot/query coordinates. Do not
    // reinterpret an old route after rule deduplication or input reordering.
    let before=old["recipe"]["rules"].as_array().ok_or("rules")?;
    let after=raw["recipe"]["rules"].as_array().ok_or("rules")?;
    if before.len()!=after.len() || before.iter().zip(after).any(|(b,a)|
        ["metadata","query","slots"].iter().any(|k|b[k]!=a[k])) {
        return Err("specialization changed Cell coordinates; needs explicit mapping".into());
    }
    // Compilation can discover new ordinary routes unrelated to this rewrite.
    // Keep the previous selection; discard only routes whose required source
    // operation has become a Copy. The target parser rechecks every kept route.
    let removed=raw["entry_value_specialization"]["projections"].as_array().into_iter().flatten()
        .map(|p|(p["rule"].as_u64().unwrap(),p["operation"].as_u64().unwrap()))
        .collect::<std::collections::BTreeSet<_>>();
    raw["multi_stage"]=old["multi_stage"].clone();
    raw["multi_stage"]["recipe_sha256"]=raw["recipe"]["sha256"].clone();
    raw["multi_stage"]["routes"].as_array_mut().unwrap().retain(|route| {
        let producer=route["producer"].as_u64().unwrap();
        !removed.contains(&(producer,route["effect"].as_u64().unwrap()))
            && !route["steps"].as_array().unwrap().iter().any(|step|
                step["source_kind"]=="effect" && removed.contains(&(producer,step["source_index"].as_u64().unwrap())))
    });
    raw["spine_blocks"]=old["spine_blocks"].clone();
    raw["spine_blocks"]["recipe_sha256"]=raw["recipe"]["sha256"].clone();
    raw["context_admission"]=old["context_admission"].clone();
    raw["context_admission"]["recipe"]=raw["recipe"]["sha256"].clone();
    let p=Program::parse(raw.clone())?;
    let mut plan=json!({});
    for key in ["schema","limits","joins","producer_roots","matched_entries"] {
        if let Some(v)=old["iterative_bake"].get(key) {plan[key]=v.clone();}
    }
    plan["recipe"]=raw["recipe"]["sha256"].clone();
    plan["seed"]=artifact_digest(&raw["spine_blocks"]).into();
    Catalog::relower_selected(&p,&mut plan,&old["iterative_bake"]["rhs_handoffs"])?;
    if plan["joins"]!=old["iterative_bake"]["joins"] {return Err("selected paths changed".into());}
    raw["iterative_bake"]=plan;
    // Source fragments are a candidate selection. Typed preparation must still
    // validate them, and changed wiring is reported rather than called equal.
    raw["ownership_fragments"]=old["ownership_fragments"].clone();
    if owned {
        let mut before=if let Some(path)=catalog {
            Program::parse(serde_json::from_slice(&fs::read(path)?)?)?
        } else {source.clone()};
        let donor=&before.artifact["recipe"]["rules"];
        if donor.as_array().map(|r|r.len())!=old["recipe"]["rules"].as_array().map(|r|r.len())
            || donor.as_array().unwrap().iter().zip(old["recipe"]["rules"].as_array().unwrap()).any(|(b,a)|
                ["metadata","query","slots"].iter().any(|k|b[k]!=a[k])) {
            return Err("ownership catalog changed Cell coordinates".into());
        }
        before.prepare_cell_ownership()?;
        raw["ownership_fragments"]=before.artifact["ownership_fragments"].clone();
        let mut without=raw.clone();without.as_object_mut().unwrap().remove("ownership_fragments");
        let mut target=Program::parse(without)?;target.prepare_cell_ownership()?;
        let mut roots=std::collections::BTreeMap::<usize,std::collections::BTreeSet<usize>>::new();
        for (old,new) in before.cell_ownership.markers.iter().zip(&target.cell_ownership.markers) {
            roots.entry(old.program_id).or_default().insert(new.program_id);
        }
        let mut fragments=std::collections::BTreeSet::new();
        for fragment in before.artifact["ownership_fragments"]["fragments"].as_array().ok_or("fragments")? {
            let f:eggfuse_cell_runtime::graph::cell_ownership::composition::Fragment=serde_json::from_value(fragment.clone())?;
            for &root in roots.get(&f.root).ok_or("missing root implementation")? {
                let mut next=f.clone();next.root=root;
                for hop in &mut next.hops {
                    let atom=*before.cell_ownership.entries.get(hop.rule).and_then(|e|e.get(hop.entry)).ok_or("source Entry")?;
                    hop.entry=target.cell_ownership.entries[hop.rule].iter().position(|&a|a==atom).ok_or("target Entry removed")?;
                }
                fragments.insert(next);
            }
        }
        let expanded=fragments.len();
        fragments.retain(|f|target.cell_ownership.composition.supports_fragment(&target,f));
        let supported=fragments.len();
        let mut fragments=fragments.into_iter().collect::<Vec<_>>();
        // Representation changes can split a shared root implementation. Keep
        // the existing finite budget and all prefixes of retained fragments.
        fragments.sort_by(|a,b|a.hops.len().cmp(&b.hops.len()).then(a.cmp(b)));
        fragments.truncate(256);
        let retained=fragments.len();
        raw["ownership_fragments"]["fragments"]=serde_json::to_value(fragments)?;
        raw["ownership_fragments"].as_object_mut().unwrap().remove("ranking");
        raw["ownership_fragments"].as_object_mut().unwrap().remove("query_classes");
        raw["ownership_fragments"]["selection_provenance"]=json!({"previous_source":before.artifact["ownership_fragments"]["source"],
            "expanded_fragments":expanded,"supported_fragments":supported,"retained_fragments":retained,"budget_policy":"short prefixes first, deterministic; unmeasured cost",
            "new_observations":false,"mapping":"source template implementations and original query atoms; checked target substitutions"});
    }
    raw["ownership_fragments"]["source"]=eggfuse_cell_runtime::graph::cell_ownership::composition::source_digest(&raw).into();
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into();
    let mut p=Program::parse(raw.clone())?;
    validate(&source,&p)?;
    p.prepare_cell_ownership()?;
    let mut b=source.clone();b.prepare_cell_ownership()?;
    let report=json!({"base":old["sha256"],"candidate":raw["sha256"],
        "ordinary_routes_before":old["multi_stage"]["routes"].as_array().unwrap().len(),
        "ordinary_routes_after":raw["multi_stage"]["routes"].as_array().unwrap().len(),
        "selected_joins":raw["iterative_bake"]["joins"].as_array().unwrap().len(),
        "ownership_shapes_equal":serde_json::to_value(&b.cell_ownership.composition.shapes)?==serde_json::to_value(&p.cell_ownership.composition.shapes)?,
        "ownership_transitions_equal":serde_json::to_value(&b.cell_ownership.composition.transitions)?==serde_json::to_value(&p.cell_ownership.composition.transitions)?,
        "scope":"typed candidate; runtime admission and source-specialization semantic validation still required"});
    fs::write(&a[1],serde_json::to_vec_pretty(&raw)?)?;
    println!("{}",report);
    Ok(())
}
