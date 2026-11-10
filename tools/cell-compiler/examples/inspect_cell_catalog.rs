//! Exact finite Cell path/state contracts and retained path storage.
use eggfuse_cell_runtime::program::Program;
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args:Vec<_>=std::env::args().skip(1).collect();
    let [input,output]=args.as_slice() else {return Err("expected PROGRAM OUTPUT".into())};
    let p=Program::parse(serde_json::from_slice(&std::fs::read(input)?)?)?;
    let report=serde_json::json!({"program":p.artifact["sha256"],
        "entries":p.iterative.entries(),"contracts":p.iterative.state_contracts(&p),
        "storage":p.iterative.path_storage(),"dispatch":p.iterative.dispatch_storage(),"export_storage":p.iterative.export_storage()});
    std::fs::write(output,serde_json::to_vec_pretty(&report)?)?;
    Ok(())
}
