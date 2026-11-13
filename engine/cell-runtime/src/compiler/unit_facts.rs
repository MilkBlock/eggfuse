//! Lower constant Unit membership into the existing Cell fact representation.
//! This is a closed-source proof, not permission to drop a table's membership.
use super::*;
use crate::value::Value;

fn mentions(value:&J,name:&str)->bool {
    match value {
        J::Object(fields)=>value["call"]["table"]==name || fields.values().any(|v|mentions(v,name)),
        J::Array(values)=>values.iter().any(|v|mentions(v,name)),
        _=>false,
    }
}
fn eligible(p:&Program,table:usize)->bool {
    let t=&p.tables[table];
    if t.constructor || t.virtual_fact || t.schema.last().is_none_or(|s|s["kind"]!="Unit")
        || t.merge!=json!({"var":"old"})
        || p.initial.iter().any(|r|r["table"]==t.name)
        || p.artifact["source_core"]["tables"].as_array().unwrap().iter()
            .any(|other|mentions(&other["merge_expr"],&t.name)) {return false;}
    let mut writes=0;
    for rule in &p.rules {
        let template=&p.templates[rule.template];
        for op in template.ops.iter() {
            match op {
                // A virtual Unit Let creates membership, whereas a function
                // Let reads it and can fail. Never change that contract.
                Op::Let(_,Call::Table(t),_) | Op::Hide(t,_,_) if *t==table=>return false,
                Op::Set(t,_,v) if *t==table=> {
                    if template.resolve_copy(v)!=Arg::Literal(Value::Int(0)) {return false;}
                    writes+=1;
                },
                _=>(),
            }
        }
    }
    writes>0
}
fn rewrite(p:&Program,tables:&[usize])->Result<J> {
    if tables.windows(2).any(|w|w[0]>=w[1]) || tables.iter().any(|&t|t>=p.tables.len() || !eligible(p,t)) {
        return Err("Unit selection must be sorted, unique and individually proved eligible".into());
    }
    let mut core=p.artifact["source_core"].clone();
    for &table in tables {
        let t=core["tables"].as_array_mut().ok_or("core tables")?.iter_mut()
            .find(|t|t["name"]==p.tables[table].name).ok_or("source table")?;
        t["merge_expr"]=J::Null;t["merge"]=J::Null;
    }
    core.as_object_mut().ok_or("core")?.remove("sha256");
    core["sha256"]=crate::checksum::artifact_digest(&core).into();
    Ok(core)
}
/// Recompile Unit membership as ordinary virtual Cell facts. No new runtime
/// representation, approximate membership or independent producer index.
pub fn specialize_unit_facts(p:&Program)->Result<J> {
    let tables=(0..p.tables.len()).filter(|&t|eligible(p,t)).collect::<Vec<_>>();
    specialize_unit_facts_selected(p,&tables)
}
/// Selection is a cost decision; every selected table still needs the full proof.
pub fn specialize_unit_facts_selected(p:&Program,tables:&[usize])->Result<J> {
    let core=rewrite(p,tables)?;
    let markers=p.marker_tables.iter().map(|&t|p.tables[t].name.clone()).collect();
    let mut result=compile(core,&markers)?;
    result.as_object_mut().unwrap().remove("sha256");
    result["unit_fact_specialization"]=json!({"source_program":p.artifact["sha256"],"tables":tables,
        "contract":"constant Unit writes; no initial rows, RHS reads, visibility changes or merge readers; exact membership retained"});
    result["sha256"]=crate::checksum::artifact_digest(&result).into();
    Ok(result)
}
pub fn validate_unit_fact_specialization(source:&Program,target:&Program)->Result<()> {
    let proof=&target.artifact["unit_fact_specialization"];
    let tables:Vec<usize>=serde_json::from_value(proof["tables"].clone()).map_err(|e|format!("invalid Unit selection: {e}"))?;
    let core=rewrite(source,&tables)?;
    if target.artifact["source_core"]!=core || proof["source_program"]!=source.artifact["sha256"]
        || proof["tables"]!=json!(tables) {return Err("unproved Unit fact specialization".into());}
    Ok(())
}
