use eggfuse_cell_runtime::{
    executor::Executor, graph::Graph, live_issuer, program::Program, transfer_audit as audit,
};
use serde_json::json;
use sha2::{Digest, Sha256};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args_os().skip(1).collect::<Vec<_>>();
    let [program, model] = args.as_slice() else {
        return Err("expected PROGRAM MODEL".into());
    };
    let p = Program::parse(serde_json::from_slice(&std::fs::read(program)?)?)?;
    let mut engine = Executor::new(Graph::new(p)?, false);
    if std::env::var_os("EGGFUSE_SIGN_SAME_QUERY").is_some() {
        engine.issued.families = eggfuse_cell_runtime::named_only::Families::compile(
            &engine.graph.program,
            std::env::var_os("EGGFUSE_CARRY_SAME_QUERY").is_some(),
        )?;
    }
    live_issuer::init(
        &engine.graph,
        serde_json::from_slice(&std::fs::read(model)?)?,
        500000,
        std::env::var_os("EGGFUSE_JOIN_SCAN").is_none(),
    )?;
    audit::set_active(true);
    audit::enable_events();
    audit::enable_write_audit();
    let failure = engine.execute().err();
    audit::set_active(false);
    let mut state = vec![];
    engine.graph.write_export(&mut state)?;
    let events = audit::take_events().ok_or("missing audit events")?;
    let mut births = std::collections::BTreeSet::new();
    for e in events
        .iter()
        .flatten()
        .filter(|e| e[0] == "birth" && e[5].is_array())
    {
        let t = e[1].as_u64().ok_or("missing birth table")? as usize;
        if engine.graph.program.tables[t].constructor {
            births.insert((t, e[4].as_u64().ok_or("missing birth witness")?));
        }
    }
    let mut visible = vec![];
    for (t, table) in engine.graph.program.tables.iter().enumerate() {
        if !table.constructor {
            continue;
        }
        for w in engine.graph.witnesses(t) {
            if let eggfuse_cell_runtime::graph::Dependency::Fact(f) = w {
                let id = (u64::from(f.cell) << 32) | u64::from(f.op);
                if births.contains(&(t, id))
                    && engine
                        .graph
                        .row(w)?
                        .is_some_and(|r| !r.hidden && r.witness == w && r.table == t)
                {
                    visible.push((t, id));
                }
            }
        }
    }
    visible.sort_unstable();
    visible.dedup();
    println!(
        "{}",
        json!({"failure":failure,"state_sha":format!("{:x}",Sha256::digest(state)),
        "issuer":live_issuer::finish(),"cross_run":engine.issued.families.cross_run,"family_fanout":engine.issued.families.fanout(),"projected_commits":engine.issued.families.projected_commits,"internal_matches":engine.issued.families.internal,"family_packets":engine.issued.families.signed,"accepted":engine.issued.accepted,"rejected":engine.issued.rejected,"primitive_rejects":engine.issued.primitive_rejects,"named_reads":engine.issued.reads,
        "schedule":engine.steps.iter().map(|s|json!([s.ruleset,s.epoch,s.path,s.iterations,s.executed_bindings,s.changed])).collect::<Vec<_>>(),
        "visible_births":visible.len(),"visible_sha":format!("{:x}",Sha256::digest(serde_json::to_vec(&visible)?)), "events":events,"rhs":audit::take_digests(),"resumes":audit::take_resume_digests(),"writes":audit::take_write_digests()})
    );
    Ok(())
}
