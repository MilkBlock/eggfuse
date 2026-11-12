//! Recompile a proven Entry value projection without retaining producer history.
use eggfuse_cell_runtime::{program::Program,compiler};
use std::{fs,error::Error};
fn main()->Result<(),Box<dyn Error>> {
    let a=std::env::args().skip(1).collect::<Vec<_>>();
    if a.len()!=2 {return Err("usage: specialize_entry_values PROGRAM OUTPUT".into());}
    let p=Program::parse(serde_json::from_slice(&fs::read(&a[0])?)?)?;
    let result=compiler::specialize_entry_values(&p)?;
    Program::parse(result.clone())?;
    fs::write(&a[1],serde_json::to_vec_pretty(&result)?)?;
    println!("{}",result["entry_value_specialization"]);
    Ok(())
}
