//! Direct typed lowering for bounded semantic diagnostics; no Bake discovery.
use eggfuse_cell_runtime::{compiler,program::Program};
use std::{env,fs,path::Path};
fn main()->Result<(),Box<dyn std::error::Error>> {
    let args=env::args().skip(1).collect::<Vec<_>>();
    let [command,source_flag,source,output_flag,output]=args.as_slice() else {return Err("compile --source SOURCE --output DIRECTORY".into())};
    if command!="compile" || source_flag!="--source" || output_flag!="--output" {return Err("invalid flags".into())}
    let text=fs::read_to_string(source)?;
    let core=eggfuse_bake::device_frontend::core("enumerated-local",&text)?;
    let program=Program::parse(compiler::compile(core,&Default::default())?)?;
    fs::create_dir(output)?;
    fs::write(Path::new(output).join("program.json"),serde_json::to_vec(&program.artifact)?)?;
    fs::write(Path::new(output).join("lowering.json"),b"{\"scope\":\"direct typed lowering; no native Bake discovery\"}\n")?;
    Ok(())
}
