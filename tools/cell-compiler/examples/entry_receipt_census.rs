//! Final-boundary availability of original constructor donors; no lookup fallback.
use eggfuse_cell_runtime::{cell::Site,cell_entry_invariants,
    executor::Executor,graph::{Graph,Dependency},program::{Program,Call}};
use serde_json::{Value,json};
use std::{collections::BTreeMap,fs,error::Error};
fn main()->Result<(),Box<dyn Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=3 {return Err("usage: entry_receipt_census PROGRAM AUDITED_CONTROL OUTPUT".into());}
    let p=Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let proofs=cell_entry_invariants::exports(&p);
    let control:Value=serde_json::from_slice(&fs::read(&args[1])?)?;
    if control["all_saved_run_checks_equal"]!=true || control["program_sha256"]!=p.artifact["sha256"] {
        return Err("audited control from this Program required".into());
    }
    let mut e=Executor::new(Graph::new_with_local_congruence(p)?,false);
    e.graph.use_port_domains_only()?;
    e.use_completed_parent_takeover()?;
    let mut runs=0;
    loop {
        e.execute_until(Some(runs+1))?;
        if e.steps.len()==runs {break;}
        e.graph.transfer_completed_owners()?;
        runs+=1;
    }
    if json!(runs)!=control["runs"] || e.graph.export()?!=control["final_state"] {
        return Err("Run count or exact final export differs".into());
    }
    let g=&e.graph;
    let mut report=vec![];
    for proof in proofs {
        let mut counts=BTreeMap::<&str,usize>::new();
        for witness in g.witnesses(proof.view) {
            let Some(row)=g.row(witness)?.filter(|r|!r.hidden) else {continue;};
            let outcome=if let Some(context)=g.continuation_context(witness) {
                if let Some(writer)=proof.writers.iter().find(|w|
                    g.program.rules[w.rule].template==context.template && w.operation==context.op) {
                    match writer.donor {
                        Site::Query(atom)=>match g.program.rules[writer.rule].query[atom].call {
                            Call::Table(t) if t==proof.view=>"inductive_query_not_constructor_receipt",
                            _=>"query_receipt_required",
                        },
                        Site::Effect(op)=> {
                            let donor=Dependency::Fact(g.context_fact(context,op));
                            if let Some(actual)=g.row(donor)? {
                                if actual.hidden {"donor_hidden"}
                                else if actual.table!=proof.constructor {"donor_wrong_table"}
                                else if actual.values.iter().eq(proof.columns.iter().map(|&i|&row.values[i])) {
                                    "resident_original_constructor"
                                } else {"donor_fields_differ"}
                            } else {"actual_result_receipt_required"}
                        }
                    }
                } else {"unrecognized_writer"}
            } else {"source_context_missing"};
            *counts.entry(outcome).or_default()+=1;
        }
        report.push(json!({"view":g.program.tables[proof.view].name,
            "constructor":g.program.tables[proof.constructor].name,"columns":proof.columns,"counts":counts}));
    }
    fs::write(&args[2],serde_json::to_vec_pretty(&json!({
        "scope":"actual standalone Cell runtime final donor census; no lookup fallback, memory or speed claim",
        "program_sha256":g.program.artifact["sha256"],"runs":runs,"final_export_equal":true,
        "per_run_audit_repeated":false,"relations":report}))?)?;
    println!("{}",json!({"runs":runs,"final_export_equal":true}));
    Ok(())
}
