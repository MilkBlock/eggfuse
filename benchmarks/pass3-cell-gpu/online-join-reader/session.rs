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
    println!(
        "{}",
        json!({"failure":failure,"state_sha":format!("{:x}",Sha256::digest(state)),
        "issuer":live_issuer::finish(),"accepted":engine.issued.accepted,"rejected":engine.issued.rejected,"named_reads":engine.issued.reads,
        "schedule":engine.steps.iter().map(|s|json!([s.ruleset,s.epoch,s.path,s.iterations,s.executed_bindings,s.changed])).collect::<Vec<_>>(),
        "events":audit::take_events(),"rhs":audit::take_digests(),"resumes":audit::take_resume_digests(),"writes":audit::take_write_digests()})
    );
    Ok(())
}
