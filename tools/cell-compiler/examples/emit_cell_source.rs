//! Emit a typed Cell program directly from a short source fixture, without
//! marker selection, training or execution. Usage: SOURCE.egg OUTPUT_DIRECTORY.
use eggfuse_cell_runtime::{compiler, program::Program};
use std::{fs, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [source, output] = args.as_slice() else { return Err("expected SOURCE OUTPUT_DIRECTORY".into()); };
    let text = fs::read_to_string(source)?;
    let core = eggfuse_bake::device_frontend::core(source, &text)?;
    let program = Program::parse(compiler::compile(core, &Default::default())?)?;
    let output = PathBuf::from(output);
    fs::create_dir_all(&output)?;
    fs::write(output.join("source.egg"), text)?;
    fs::write(output.join("program.json"), serde_json::to_vec_pretty(&program.artifact)?)?;
    Ok(())
}
