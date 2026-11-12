//! Natural-lifetime storage control; partial Graph census, never total heap/RSS.
use eggfuse_cell_runtime::{program::Program,graph::Graph,executor::Executor,checksum::artifact_digest};
use serde_json::{Value,json};
use std::{fs,error::Error};
fn main()->Result<(),Box<dyn Error>> {
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    if a.len()<3 || a[3..].iter().any(|s|s!="--shared-owners" && s!="--parent-takeover") {return Err("usage: runtime_parent_storage PROGRAM AUDITED_WORK OUTPUT [--shared-owners] [--parent-takeover]".into());}
    let raw:Value=serde_json::from_slice(&fs::read(&a[0])?)?;
    let audit:Value=serde_json::from_slice(&fs::read(&a[1])?)?;
    if audit["program_sha256"]!=raw["sha256"] || audit["all_saved_run_checks_equal"]!=true {return Err("audit differs".into());}
    let expected=artifact_digest(&audit["final_state"]);
    let shared=a[3..].iter().any(|s|s=="--shared-owners");
    let parent_takeover=a[3..].iter().any(|s|s=="--parent-takeover");
    let mut modes=Vec::new();
    for retain in [true,false] {
        let mut e=Executor::new(Graph::new_with_local_congruence(Program::parse(raw.clone())?)?,false);
        if !retain && (!shared || parent_takeover) {e.use_completed_parent_takeover()?;}
        let mut samples=Vec::new();
        loop {
            let n=e.steps.len();e.execute_until(Some(n+1))?;
            if e.steps.len()==n {break;}
            if shared {
                if !retain {e.graph.transfer_completed_owners()?;}
                e.graph.compact_source_record_capacity();
            }
            let c=e.graph.retained_cell_storage();
            samples.push(json!({"run":n+1,"counted_bytes":c["counted_bytes"],"parent_links":c["parent_links"]}));
        }
        if artifact_digest(&e.graph.export()?)!=expected {return Err("final state differs from audited execution".into());}
        modes.push(json!({"retain_parent_bindings":retain,"runs":samples.len(),"samples":samples,
            "final_source_storage":e.graph.retained_cell_storage(),"graph_work":e.graph.stats}));
    }
    fs::write(&a[2],serde_json::to_vec_pretty(&json!({"program_sha256":raw["sha256"],
        "source_record_capacity_control":shared,"parent_takeover":parent_takeover,"scope":"actual standalone Cell runtime, counted Graph arrays/records at Run boundaries, not total egraph heap or execution peak",
        "final_state_sha256":expected,"modes":modes}))?)?;
    Ok(())
}
