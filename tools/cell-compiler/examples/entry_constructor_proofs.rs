//! Inspect whole-program Cell Entry value proofs without changing runtime state.
use eggfuse_cell_runtime::{program::Program,cell_entry_invariants};
use serde_json::json;
use std::{fs,error::Error};
fn main()->Result<(),Box<dyn Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=2 {return Err("usage: entry_constructor_proofs PROGRAM OUTPUT".into());}
    let p=Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let projections=cell_entry_invariants::discover(&p);
    let exports=cell_entry_invariants::exports(&p);
    let result=json!({"program_sha256":p.artifact["sha256"],"projections":projections,"exports":exports,
        "scope":"compile-time all-writer induction; result values only, not constructor receipts or saved runtime work"});
    fs::write(&args[1],serde_json::to_vec_pretty(&result)?)?;
    println!("{}",json!({"projections":projections.len(),"exports":exports.len()}));
    Ok(())
}
