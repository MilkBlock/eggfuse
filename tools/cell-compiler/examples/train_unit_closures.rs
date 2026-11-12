//! Capture one execution of the current Unit-owning catalog for offline Bake.
use eggfuse_cell_runtime::{program::Program,graph::Graph,executor::Executor,checksum::artifact_digest};
use serde_json::json;
use std::{fs,error::Error};
fn main()->Result<(),Box<dyn Error>> {
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    if a.len()!=2 {return Err("usage: train_unit_closures PROGRAM OUTPUT_DIRECTORY".into());}
    let p=Program::parse(serde_json::from_slice(&fs::read(&a[0])?)?)?;
    if p.artifact["unit_fact_ownership"]!=true {return Err("requires explicit Unit ownership candidate".into());}
    let mut g=Graph::new_with_local_congruence(p)?;g.use_port_domains_only()?;
    g.continue_ownership_fragment_training(16)?;
    let mut e=Executor::new(g,false);e.use_completed_parent_takeover()?;e.execute()?;
    e.graph.transfer_completed_owners()?;
    let profile=e.graph.ownership_fragment_profile()?;
    fs::create_dir_all(&a[1])?;
    fs::write(format!("{}/profile.json",a[1]),serde_json::to_vec_pretty(&profile)?)?;
    let mut lengths=std::collections::BTreeMap::<usize,usize>::new();
    let mut unit_records=0;
    for record in profile["records"].as_array().unwrap() {
        let hops=record["fragment"]["hops"].as_array().unwrap();
        *lengths.entry(hops.len()).or_default()+=1;
        let has_unit=hops.iter().any(|hop| {
            let rid=hop["rule"].as_u64().unwrap() as usize;
            let entry=hop["entry"].as_u64().unwrap() as usize;
            let atom=e.graph.program.cell_ownership.entries[rid][entry];
            match e.graph.program.rules[rid].query[atom].call {
                eggfuse_cell_runtime::program::Call::Table(t)=>e.graph.program.tables[t].schema.last().unwrap()["kind"]=="Unit",
                _=>false,
            }
        });
        unit_records+=usize::from(has_unit);
    }
    let summary=json!({"hop_lengths":lengths,"records_with_unit_entry":unit_records,"program":e.graph.program.artifact["sha256"],"runs":e.steps.len(),
        "final_state":artifact_digest(&e.graph.export()?),"records":profile["records"].as_array().unwrap().len(),
        "scope":"actual standalone Cell runtime continuation observations; proposed fragment credits are not additive memory savings"});
    fs::write(format!("{}/summary.json",a[1]),serde_json::to_vec_pretty(&summary)?)?;
    println!("{}",summary);Ok(())
}
