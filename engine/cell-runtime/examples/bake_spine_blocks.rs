use eggfuse_cell_runtime::{
    checksum::artifact_digest,
    compiler::{bake_spine_blocks, bake_stage_blocks},
    program::Program,
};
use serde_json::Value;
use std::{env, fs};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1).collect::<Vec<_>>();
    let staged = args.last().is_some_and(|a| a == "--complete-stage");
    if staged {
        args.pop();
    }
    let [train, profile, target, out, limit] = args.as_slice() else {
        return Err(
            "expected TRAIN_PROGRAM TRAIN_SHAPES TARGET_PROGRAM OUTPUT LIMIT [--complete-stage]"
                .into(),
        );
    };
    let read = |path: &str| -> Result<Value, Box<dyn std::error::Error>> {
        Ok(serde_json::from_slice(&fs::read(path)?)?)
    };
    let training = Program::parse(read(train)?)?;
    let target = Program::parse(read(target)?)?;
    let bake = if staged {
        bake_stage_blocks
    } else {
        bake_spine_blocks
    };
    let plan = bake(&training, &read(profile)?, &target, limit.parse()?)?;
    let mut artifact = target.artifact;
    artifact.as_object_mut().unwrap().remove("sha256");
    // Continuations refer to the old leaf catalog by index and seed digest.
    // Replacing its leaves requires learning a fresh continuation catalog.
    artifact.as_object_mut().unwrap().remove("iterative_bake");
    artifact["spine_blocks"] = plan;
    artifact["sha256"] = artifact_digest(&artifact).into();
    let validated = Program::parse(artifact)?;
    fs::write(out, serde_json::to_vec(&validated.artifact)?)?;
    Ok(())
}
