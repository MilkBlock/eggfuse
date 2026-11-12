//! Observe a materialized Cell handoff, including root executions without a cursor.
//! This is diagnostic execution, not a memory or speed benchmark.
use eggfuse_cell_runtime::{
    checksum::artifact_digest, executor::Executor, graph::Graph, program::Program,
    transfer_audit as audit,
    program::{Call, Op},
};
use serde_json::{Value, json};
use std::{error::Error, fs};
fn main() -> Result<(), Box<dyn Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 4 {
        return Err("usage: runtime_handoff_trace PROGRAM EXPECTED_TRACE TABLE OUTPUT".into());
    }
    let expected: Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let checks = expected["run_checks"]
        .as_array()
        .ok_or("expected saved Run checks")?;
    let p = Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let table=p.tables.iter().position(|t| t.name==args[2]).ok_or("unknown handoff table")?;
    let selected=p.rules.iter().enumerate().filter_map(|(rid,r)| {
        (r.query.iter().any(|a|matches!(a.call,Call::Table(t) if t==table)) ||
         p.templates[r.template].ops.iter().any(|op|matches!(op,Op::Set(t,_,_) if *t==table)))
            .then_some(rid)
    }).collect::<Vec<_>>();
    let mut graph = Graph::new_with_local_congruence(p)?;
    graph.trace_ownership_catalog(16)?;
    let mut e = Executor::new(graph, false);
    e.collect_iterative_history(100_000);
    let mut windows=Vec::new();
    let mut runs = 0;
    loop {
        audit::take_digests();
        audit::take_write_digests();
        audit::take_resume_digests();
        let before=handoff_rows(&e.graph,table)?;
        audit::observation::begin(selected.iter().copied(),table);
        audit::set_active(true);
        audit::enable_write_audit();
        e.execute_until(Some(runs + 1))?;
        audit::set_active(false);
        let observation=audit::observation::finish();
        let effects = json!({"rhs":audit::take_digests(),"writes":audit::take_write_digests(),"resumes":audit::take_resume_digests()});
        if e.steps.len() == runs {
            break;
        }
        e.graph.compact_retained_capacity()?;
        let observed =
            json!({"graph":artifact_digest(&e.graph.export()?),"audit":artifact_digest(&effects)});
        if checks.get(runs) != Some(&observed) {
            return Err(format!("Run {} differs from saved graph/effect checks", runs + 1).into());
        }
        runs += 1;
        if observation["matches"].as_array().is_some_and(|r|!r.is_empty()) ||
            observation["effective_writes"].as_array().is_some_and(|r|!r.is_empty()) {
            windows.push(json!({"run":runs,"before":before,
                "after":handoff_rows(&e.graph,table)?,"observation":observation}));
        }
    }
    if runs != checks.len() {
        return Err("Run count differs from saved trace".into());
    }
    let mut result = json!({"scope":"actual standalone Cell runtime; passive installed-catalog observations, no compression or timing claim",
        "runs":runs,"all_saved_run_checks_equal":true,"expected_trace_digest":artifact_digest(&expected),
        "catalog_trace":e.graph.ownership_catalog_trace()?,"ownership":e.graph.ownership_report(),
        "source_storage":e.graph.retained_cell_storage(),"final_state":e.graph.export()?});
    result["completed_history"] = e.iterative_training().completion_history(&e.graph.program);
    result["handoff"]=json!({"table":args[2],"rules":selected,"windows":windows,
        "scope":"successful matched inputs, effective writes and Run-boundary row origins; not a closure proof"});
    fs::write(&args[3], serde_json::to_vec_pretty(&result)?)?;
    println!(
        "{}",
        json!({"runs":runs,"proposals":result["catalog_trace"]["records"].as_array().unwrap().len(),"all_saved_run_checks_equal":true})
    );
    Ok(())
}

fn handoff_rows(g:&Graph,table:usize)->Result<Value,String> {
    let mut rows=Vec::new();
    for witness in g.witnesses(table) {
        if let Some(row)=g.row(witness)? {
            rows.push(json!({"witness":witness,"origin":g.origin(witness),
                "values":row.values,"epoch":row.epoch,"hidden":row.hidden}));
        }
    }
    Ok(json!(rows))
}
