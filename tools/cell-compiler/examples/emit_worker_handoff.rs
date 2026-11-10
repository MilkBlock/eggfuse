//! Emit and reconstruct-validate static preparation for worker handoff changes.
use eggfuse_cell_runtime::program::Program;
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args:Vec<_>=std::env::args().skip(1).collect();
    let [input,output]=args.as_slice() else {return Err("expected PROGRAM OUTPUT".into())};
    let p=Program::parse(serde_json::from_slice(&std::fs::read(input)?)?)?;
    let plan=eggfuse_cell_compiler::worker_handoff::compile(&p);
    eggfuse_cell_compiler::worker_handoff::validate(&p,&plan)?;
    std::fs::write(output,serde_json::to_vec_pretty(&plan)?)?;
    Ok(())
}
