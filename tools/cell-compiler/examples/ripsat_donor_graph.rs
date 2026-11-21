//! Export a finite donor region, native application history and byte-bound acceptance receipt.
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, env, fs, path::PathBuf};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<PathBuf> = env::args_os().skip(1).map(PathBuf::from).collect();
    let [entry, output] = args.as_slice() else {
        return Err("expected ENTRY.egg and a fresh OUTPUT directory".into());
    };
    let report = eggfuse_bake::native_analyze::ripen::run_with_evidence(entry, output)?;
    let mut hashes = BTreeMap::<String, String>::new();
    for name in [
        "entry.egg",
        "initial-state.json",
        "trigger-state.json",
        "history.json",
        "ripen.json",
        "saturated-rule-composition.json",
        "observed-saturated-state.json",
        "ripened.egg",
    ] {
        let path = output.join(name);
        if path.is_file() {
            hashes.insert(
                name.into(),
                format!("{:x}", Sha256::digest(fs::read(path)?)),
            );
        }
    }
    if hashes.get("entry.egg") != Some(&format!("{:x}", Sha256::digest(fs::read(entry)?))) {
        return Err("native entry copy differs from the input".into());
    }
    let path = output.join("acceptance.json");
    let mut acceptance: serde_json::Value = serde_json::from_slice(&fs::read(&path)?)?;
    acceptance["artifact_sha256"] = serde_json::to_value(hashes)?;
    fs::write(
        output.join("receipt.partial"),
        serde_json::to_vec_pretty(&acceptance)?,
    )?;
    fs::rename(output.join("receipt.partial"), path)?;
    println!(
        "{}",
        serde_json::json!({"ripen":report["ripen"],"export":report["saturated_rule_composition"]})
    );
    Ok(())
}
