use eggfuse_cell_runtime::{
    executor::Executor, graph::Graph, named_only::Packet, program::Program,
};
use serde_json::json;
use std::io::BufRead;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args_os().skip(1).collect::<Vec<_>>();
    let [path] = args.as_slice() else {
        return Err("expected PROGRAM.json".into());
    };
    let program = Program::parse(serde_json::from_slice(&std::fs::read(path)?)?)?;
    for line in std::io::stdin().lock().lines() {
        let packets: Vec<Packet> = serde_json::from_str(&line?)?;
        let mut engine = Executor::new(Graph::new(program.clone())?, false);
        for p in packets {
            engine.issued.submit(p);
        }
        use eggfuse_cell_runtime::transfer_audit;
        transfer_audit::set_active(true);
        transfer_audit::enable_write_audit();
        transfer_audit::enable_events();
        engine.execute()?;
        transfer_audit::set_active(false);
        let mut state = vec![];
        engine.graph.write_export(&mut state)?;
        use sha2::{Digest, Sha256};
        println!(
            "{}",
            json!({"protocol":"named-only/v1","accepted":engine.issued.accepted,
            "rejected":engine.issued.rejected,"unused":engine.issued.unused(),"named_reads":engine.issued.reads, "rhs":transfer_audit::take_digests(), "writes":transfer_audit::take_write_digests(), "resumes":transfer_audit::take_resume_digests(),
            "events":transfer_audit::take_events(),
            "schedule":engine.steps.iter().map(|s|json!([s.ruleset,s.epoch,s.path,s.iterations,s.executed_bindings,s.changed])).collect::<Vec<_>>(),
            "run_matches":engine.steps.iter().map(|s|s.logical_matches).collect::<Vec<_>>(),
            "state_sha":format!("{:x}",Sha256::digest(&state))})
        );
    }
    Ok(())
}
