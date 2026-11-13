//! Batch finite closure selections from one saved current-catalog execution.
use eggfuse_cell_runtime::{program::{Program,Call},checksum::artifact_digest,
    graph::cell_ownership::composition::{select_profile,source_digest}};
use serde_json::{Value,json};
use std::{fs,error::Error};
fn main()->Result<(),Box<dyn Error>> {
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    if a.len()!=3 {return Err("usage: bake_unit_closures PROGRAM PROFILE OUTPUT_DIRECTORY".into());}
    let mut p=Program::parse(serde_json::from_slice(&fs::read(&a[0])?)?)?;
    p.prepare_cell_ownership()?;
    let profile:Value=serde_json::from_slice(&fs::read(&a[1])?)?;
    if profile["source"]!=source_digest(&p.artifact) {return Err("profile source differs from current catalog".into());}
    let records=profile["records"].as_array().ok_or("records")?;
    let unit_hop=|record:&Value|record["fragment"]["hops"].as_array().unwrap().iter().any(|hop| {
        let rid=hop["rule"].as_u64().unwrap() as usize;
        let entry=hop["entry"].as_u64().unwrap() as usize;
        let atom=p.cell_ownership.entries[rid][entry];
        matches!(p.rules[rid].query[atom].call,Call::Table(t) if p.tables[t].schema.last().unwrap()["kind"]=="Unit")
    });
    let unit_records=records.iter().filter(|r|unit_hop(r)).count();
    let mut lengths=std::collections::BTreeMap::new();
    for r in records {*lengths.entry(r["fragment"]["hops"].as_array().unwrap().len()).or_insert(0usize)+=1;}
    fs::create_dir_all(&a[2])?;
    let mut candidates=vec![];
    for limit in [4usize,8,16] {
        let mut filtered=profile.clone();filtered["max_frames"]=json!(limit);
        filtered["records"]=records.iter().filter(|r|r["fragment"]["hops"].as_array().unwrap().len()<limit).cloned().collect::<Vec<_>>().into();
        let selection=select_profile(&filtered)?;
        let mut raw=p.artifact.clone();raw["ownership_fragments"]=selection.clone();
        raw.as_object_mut().unwrap().remove("ownership_markers");raw.as_object_mut().unwrap().remove("sha256");
        raw["sha256"]=artifact_digest(&raw).into();
        let mut q=Program::parse(raw.clone())?;q.prepare_cell_ownership()?;
        let dir=format!("{}/frames{}",a[2],limit);fs::create_dir_all(&dir)?;
        fs::write(format!("{}/program.json",dir),serde_json::to_vec_pretty(&raw)?)?;
        let mut unit_tables=std::collections::BTreeSet::new();
        for fragment in selection["fragments"].as_array().unwrap() {
            for hop in fragment["hops"].as_array().unwrap() {
                let rule=hop["rule"].as_u64().unwrap() as usize;
                let entry=hop["entry"].as_u64().unwrap() as usize;
                let atom=q.cell_ownership.entries[rule][entry];
                if let Call::Table(table)=q.rules[rule].query[atom].call {
                    if q.tables[table].schema.last().unwrap()["kind"]=="Unit" {unit_tables.insert(table);}
                }
            }
        }
        fs::write(format!("{}/unit-tables.json",dir),serde_json::to_vec_pretty(&unit_tables)?)?;
        candidates.push(json!({"max_frames":limit,"program":raw["sha256"],"fragments":selection["fragments"].as_array().unwrap().len(),
            "shapes":q.cell_ownership.composition.shapes.len(),"transitions":q.cell_ownership.composition.transitions.len(),
            "unit_entry_tables":unit_tables,"ranking":selection["ranking"]}));
    }
    let summary=json!({"source_program":p.artifact["sha256"],"records":records.len(),"records_with_unit_entry":unit_records,
        "hop_lengths":lengths,"candidates":candidates,"scope":"offline selections from one actual execution; candidates overlap; no runtime saving claimed"});
    fs::write(format!("{}/summary.json",a[2]),serde_json::to_vec_pretty(&summary)?)?;
    println!("{}",summary);Ok(())
}
