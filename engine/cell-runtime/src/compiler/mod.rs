//! Compile native typed egglog to the standalone Cell CPU instruction format.

#[cfg(feature = "spine-blocks")]
mod spine_blocks;
#[cfg(feature = "spine-blocks")]
pub use spine_blocks::{bake_spine_blocks, bake_stage_blocks};
mod recipe;
use crate::{
    cell::{Definition, Site, bind_relation, project_rows, unique_projection},
    program::*,
};
use serde_json::{Value as J, json};
use std::collections::{BTreeMap, BTreeSet};

fn points(
    p: &Program,
    r: &Rule,
    mut left: BTreeSet<usize>,
    mut known: BTreeSet<usize>,
) -> Vec<usize> {
    let mut order = vec![];
    loop {
        let ready=left.iter().filter_map(|&i|{let a=&r.query[i];let (out,key)=a.args.split_last()?;
            let bound=|v:&Arg|match v{Arg::Literal(_)=>true,Arg::Slot(s)=>known.contains(s)};
            let priority=if key.iter().all(bound){usize::from(matches!(a.call,Call::Table(_)))}else if matches!(a.call,Call::Table(t) if p.tables[t].schema.last().unwrap()["kind"]=="eq") && matches!(out,Arg::Slot(s) if known.contains(s)){2}else{return None};Some((priority,i))}).min();
        let Some((_, i)) = ready else { break };
        left.remove(&i);
        order.push(i);
        known.extend(
            r.query[i]
                .args
                .iter()
                .filter_map(|a| if let Arg::Slot(s) = a { Some(*s) } else { None }),
        );
    }
    order
}
fn multistage(p: &Program, known: &crate::known_results::Plans) -> J {
    let mut readers = vec![vec![]; p.tables.len()];
    let (mut entries, mut finishes, mut routes, mut loaders) = (vec![], vec![], vec![], vec![]);
    for (rid, r) in p.rules.iter().enumerate() {
        let all = (0..r.query.len()).collect::<BTreeSet<_>>();
        let mut rest = all.clone();
        let mut slots = BTreeSet::new();
        for (i, a) in r.query.iter().enumerate() {
            if let Call::Table(t) = a.call {
                readers[t].push((rid, i));
                rest.remove(&i);
                let known = a
                    .args
                    .iter()
                    .filter_map(|v| if let Arg::Slot(s) = v { Some(*s) } else { None })
                    .collect::<BTreeSet<_>>();
                slots.extend(&known);
                let mut tail = all.clone();
                tail.remove(&i);
                let atoms = points(p, r, tail, known);
                if !atoms.is_empty() {
                    entries.push(json!({"rule":rid,"anchor":i,"atoms":atoms}));
                }
            }
        }
        finishes.push(points(p, r, rest, slots));
    }
    for (producer, r) in p.rules.iter().enumerate() {
        if !r.query.iter().any(|a| matches!(a.call, Call::Table(_))) {
            loaders.push(producer);
            continue;
        }
        let cell = Definition::new(p, producer).expect("typed Cell")
            .with_aliases(&known.static_slots[producer]);
        let local = cell.local_relations().map(|relation| {
            (relation.site, relation.table,
                relation.columns().map(|a| cell.value(a)).collect::<Vec<_>>())
        }).collect::<Vec<_>>();
        for (site, t, cols) in &local {
            let Site::Effect(effect) = *site else { continue };
            for &(consumer, anchor) in &readers[*t] {
                let q = &p.rules[consumer].query;
                let mut mapping = BTreeMap::new();
                if bind_relation(&q[anchor], *t, cols, &mut mapping).is_err() {
                    continue;
                }
                let mut remaining = (0..q.len())
                    .filter(|i| *i != anchor)
                    .collect::<BTreeSet<_>>();
                let mut steps = vec![];
                loop {
                    let n = remaining.len();
                    for i in remaining.clone() {
                        let a = &q[i];
                        if !a.args.iter().any(|v| {
                            matches!(v, Arg::Literal(_))
                                || matches!(v,Arg::Slot(s) if mapping.contains_key(s))
                        }) {
                            continue;
                        }
                        let Call::Table(target) = a.call else { continue };
                        let candidates = local.iter().filter_map(|(site, table, row)| {
                            if *table != target { return None; }
                            // An elided RHS constructor is the same witness as
                            // its earlier query/effect donor. Its distinct SSA
                            // output must not create a second ambiguous match.
                            // Keep it as a publication anchor above; only omit
                            // it from donor selection here.
                            if let Site::Effect(op) = *site
                                && known.static_sources.get(producer).and_then(|sources| sources[op]).is_some() {
                                return None;
                            }
                            Some(((site, row), row.as_slice()))
                        });
                        let projections = project_rows(&a.args, &mapping, candidates, PartialEq::eq,
                            |literal, value| matches!(value, Arg::Literal(v) if v == literal));
                        if let Some(((site, _), m)) = unique_projection(projections,
                            |a, b| a.0.1 == b.0.1) {
                            let (kind, idx) = site.coordinates();
                            mapping = m;
                            let mut step = json!({"atom":i,"source_kind":kind,"source_index":idx});
                            if kind == "effect" {
                                // Wire coordinates remain the original source
                                // projection, even when value proofs use aliases.
                                let (_, columns) = cell.local_columns(*site).expect("local Cell source");
                                step["assignments"] =
                                    json!(crate::multistage::assignments(&q[anchor], a, &columns));
                            }
                            steps.push(step);
                            remaining.remove(&i);
                        }
                    }
                    if remaining.len() == n {
                        break;
                    }
                }
                if !steps.is_empty()
                    || q.iter()
                        .filter(|a| matches!(a.call, Call::Table(_)))
                        .count()
                        == 1
                {
                    routes.push(json!({"producer":producer,"effect":effect,"consumer":consumer,"anchor":anchor,"steps":steps,"residual":remaining}));
                }
            }
        }
    }
    let ir = &p.artifact["recipe"];
    let sets = ir["rulesets"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| json!({"name":s["name"],"rule_ids":s["rule_ids"]}))
        .collect::<Vec<_>>();
    json!({"schema":"eggfuse-multistage/v1","recipe_sha256":ir["sha256"],"control":ir["control"],"rule_sets":sets,"routes":routes,"entries":entries,"finishes":finishes,"stage_entries":crate::stage_spine::compile_entries(p),"data_loaders":loaders,
        "contract":{"activation":"committed producer fact; current visible exhaustive projection","publication":"original Run occurrence, after all entry bindings are gathered","late_input":"ordinary delta route remains authoritative","alias_alternatives":"residual matching whenever a projection is not exhaustive"}})
}

/// Specialize ordinary typed Cell instructions after whole-program proof.
/// The optimized source core is explicit: no source-validation bypass and no
/// constructor receipt is fabricated from the View row.
fn entry_value_core(p: &Program) -> Result<(J,Vec<crate::cell_entry_invariants::Projection>)> {
    let mut core=p.artifact["source_core"].clone();
    let projections=crate::cell_entry_invariants::discover(p);
    for (set_id,set) in array(&p.artifact["recipe"]["rulesets"] )?.iter().enumerate() {
        for (position,rid) in array(&set["rule_ids"] )?.iter().enumerate() {
            let rid=rid.as_u64().ok_or("rule id")? as usize;
            for projection in projections.iter().filter(|x|x.rule==rid) {
                let effect=&mut core["rulesets"][set_id]["rules"][position]["head"][projection.operation];
                let dst=effect["dst"].clone();
                let sort=effect["sort"].clone();
                let name=p.artifact["recipe"]["rules"][rid]["slots"][projection.result_slot]["name"].clone();
                *effect=json!({"op":"copy","dst":dst,"sort":sort,"arg":{"var":name,"sort":sort}});
            }
        }
    }
    core.as_object_mut().ok_or("core object")?.remove("sha256");
    core["sha256"]=crate::checksum::artifact_digest(&core).into();
    Ok((core,projections))
}

/// Admit only the exact source rewrite re-proven from the original typed Cells.
/// This extends source acceptance without weakening graph or effect checks.
pub fn validate_entry_value_specialization(source:&Program,target:&Program)->Result<()> {
    let (core,projections)=entry_value_core(source)?;
    let proof=&target.artifact["entry_value_specialization"];
    if target.artifact["source_core"]!=core
        || proof["source_program"]!=source.artifact["sha256"]
        || proof["projections"]!=serde_json::to_value(projections).map_err(|e|e.to_string())? {
        return Err("unproved Entry source specialization".into());
    }
    Ok(())
}

pub fn specialize_entry_values(p: &Program) -> Result<J> {
    let (core,projections)=entry_value_core(p)?;
    let markers=p.marker_tables.iter().map(|&t|p.tables[t].name.clone()).collect();
    let mut result=compile(core,&markers)?;
    result.as_object_mut().unwrap().remove("sha256");
    result["entry_value_specialization"]=json!({"source_program":p.artifact["sha256"],
        "projections":projections,"contract":"all-writer proof; explicit optimized core; regenerate receipt and publication plans"});
    result["sha256"]=crate::checksum::artifact_digest(&result).into();
    Ok(result)
}

pub fn compile(core: J, markers: &BTreeSet<String>) -> Result<J> {
    let ir = recipe::build(&core)?;
    let mut templates = vec![];
    for (rid, r) in array(&ir["rules"])?.iter().enumerate() {
        let reads = array(&r["interface"]["rows"])?;
        templates.push(json!({"rule":rid,"fact_operations":array(&r["effects"])?.iter().enumerate().filter_map(|(i,e)|matches!(e["kind"].as_str(),Some("construct"|"set")).then_some(i)).collect::<Vec<_>>(),"direct_entry":reads.len()==1,"entry_table":if reads.len()==1{reads[0]["table"].clone()}else{J::Null},"primitive_guards":r["interface"]["primitive_atoms"]}));
    }
    let mut j = json!({"schema":"eggfuse-cell-runtime/v1","initial":core["initial"],"requirements":recipe::requirements(&core),"source_core":core,"recipe":ir,"templates":templates,"contract":{"storage":"shared effect recipes plus instance slots and fact-position masks","native_runtime_dependency":false,"native_free_join":false,"completeness":"exact residual virtual-fact matching; no learned exclusion"}});
    let p = Program::load(j, true)?;
    let (known_results, known_json) = crate::known_results::Plans::derive(&p)?;
    let multi = multistage(&p, &known_results);
    let contexts = crate::local_context::derive(&p, &multi["stage_entries"]);
    let spine = multi["stage_entries"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x["rule"].as_u64().unwrap() as usize)
        .collect();
    let plans = [
        (
            "view_consumer_blocks",
            json!(crate::view_plan::derive(&p, &spine)),
        ),
        ("single_writes", crate::row_kernel::writes_wire(&p)),
        ("cell_execution", crate::cell::execution::Plan::wire(&p.executions)),
        ("neighbor_entries", json!(&p.neighbor_plans)),
        ("row_kernels", crate::row_kernel::wire(&p.rules, &p.kernels)),
        ("physical_plan", json!(&p.physical)),
        ("repair_ports", json!(&p.repair_ports)),
        (
            "merge_contracts",
            json!({"schema":"eggfuse-merge-contracts/v1","tables":p.tables.iter().map(|t|crate::merge_contract::table(&p,t)).collect::<Result<Vec<_>>>()?}),
        ),
        ("known_results", known_json),
        ("entry_schedule", crate::entry_schedule::Plan::derive(&p)?.1),
        ("merge_programs", crate::merge_programs::compile(&p)?),
        ("multi_stage", multi),
        ("local_contexts", json!(contexts)),
        (
            "context_cuts",
            json!(crate::local_context::select_cuts(&p)),
        ),
        ("marker_tables", json!(markers)),
    ];
    let entry = crate::entry_join::Plan::derive(&p);
    #[cfg(feature = "structural-depth")]
    let structural = json!(crate::depth_plan::Plan::derive(&p));
    #[cfg(feature = "rhs-locals")]
    let local_blocks = crate::local_rhs::wire(&p, &crate::local_rhs::derive(&p, &known_results));
    j = p.artifact;
    #[cfg(feature = "rhs-locals")]
    {
        j["local_rhs_blocks"] = local_blocks;
    }
    #[cfg(feature = "structural-depth")]
    {
        j["structural_ports"] = structural;
    }
    j["free_join_entry"] = json!(entry);
    for (k, v) in plans {
        j[k] = v;
    }
    j["sha256"] = json!(crate::checksum::artifact_digest(&j));
    Program::parse(j.clone())?;
    Ok(j)
}
