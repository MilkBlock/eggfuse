use eggfuse_cell_runtime::ordinary_witness::bake_port_codes;

fn main() -> Result<(),Box<dyn std::error::Error>> {
    let a:Vec<_>=std::env::args_os().skip(1).collect();
    if a.len()!=2{return Err("expected WEIGHTS.json COMPILED.bin".into());}
    let compiled=bake_port_codes(&std::fs::read(&a[0])?)?;
    std::fs::write(&a[1],compiled)?;
    Ok(())
}
