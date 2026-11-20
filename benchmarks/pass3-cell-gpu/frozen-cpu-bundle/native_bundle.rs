struct StagingFolder {
    path: std::path::PathBuf,
    published: bool,
}
impl Drop for StagingFolder {
    fn drop(&mut self) {
        if !self.published {
            let _ = std::fs::remove_dir_all(&self.path);
        }
    }
}
fn network_files(
    seed: u16,
) -> Result<(&'static [u8], &'static [u8], &'static [u8]), Box<dyn std::error::Error>> {
    match seed {
        1703 => Ok((
            include_bytes!("frozen-weights/single-1703.json"),
            include_bytes!("frozen-weights/multi-1703.json"),
            include_bytes!("frozen-weights/merge-1703.json"),
        )),
        1709 => Ok((
            include_bytes!("frozen-weights/single-1709.json"),
            include_bytes!("frozen-weights/multi-1709.json"),
            include_bytes!("frozen-weights/merge-1709.json"),
        )),
        _ => Err(format!("unknown frozen seed {seed}").into()),
    }
}
fn json_bytes(v: &Value) -> Result<Vec<u8>, serde_json::Error> {
    let mut bytes = serde_json::to_vec(v)?;
    bytes.push(b'\n');
    Ok(bytes)
}
fn compile_frozen_bundle(
    source: &Path,
    out: &Path,
    seed: u16,
) -> Result<(), Box<dyn std::error::Error>> {
    let (sweights, mweights, cweights) = network_files(seed)?;
    if out.exists() {
        return Err(format!("bundle destination already exists: {}", out.display()).into());
    }
    let program_bytes = std::fs::read(source)?;
    let digest = format!("{:x}", Sha256::digest(&program_bytes));
    let program = Program::parse(serde_json::from_slice(&program_bytes)?)?;
    let plans = ordinary_witness::compile_sealed_plans(&program)?;
    let mut single: Value = serde_json::from_slice(sweights)?;
    single["mode"] = json!("learned");
    single["residual"] = json!(false);
    let mut multi: Value = serde_json::from_slice(mweights)?;
    let q: Vec<Vec<f32>> = serde_json::from_value(multi["q"].clone())?;
    let k: Vec<Vec<f32>> = serde_json::from_value(multi["k"].clone())?;
    if q.len() != 10 || k.len() != 10 || q.iter().chain(&k).any(|row| row.len() != 16) {
        return Err("invalid port head dimensions".into());
    }
    let tied: Vec<Vec<_>> = q
        .iter()
        .zip(&k)
        .map(|(qr, kr)| qr.iter().zip(kr).map(|(l, r)| (l + r) * 0.5f32).collect())
        .collect();
    multi["q"] = json!(tied);
    multi["k"] = json!(tied);
    let multi_bytes = json_bytes(&multi)?;
    let codes = ordinary_witness::bake_port_codes(&multi_bytes)?;
    let gate: Value = serde_json::from_slice(cweights)?;
    let merge = json!({"program_sha256":program.artifact["sha256"],"weights":gate["weights"],"control":"learned","allow_empty":true});
    let root = json!({"control":"use","forbid_fallback":true,"encoding":"checked_slots"});
    let mut request: Value =
        serde_json::from_str(FROZEN_BUNDLE_SETTINGS.ok_or("frozen settings unavailable")?)?;
    for (field, file) in [
        ("single_config", "single.json"),
        ("multi_weights", "multi.json"),
        ("merge_config", "merge.json"),
        ("root_config", "root.json"),
        ("baked_codes", "ports.bin"),
    ] {
        request[field] = json!(file);
    }
    request["source_sha256"] = json!(digest);
    request["cap"] = json!(1000000);
    request["audit"] = json!(false);
    verify_profile(&request)?;
    let parent = out
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    std::fs::create_dir_all(parent)?;
    let unique = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_nanos();
    let path = parent.join(format!(".eggfuse-stage-{}-{unique}", std::process::id()));
    std::fs::create_dir(&path)?;
    let mut stage = StagingFolder {
        path,
        published: false,
    };
    let mut files = serde_json::Map::new();
    for (name, bytes) in [
        ("program.json", program_bytes),
        ("plans.json", plans),
        ("single.json", json_bytes(&single)?),
        ("multi.json", multi_bytes),
        ("ports.bin", codes),
        ("root.json", json_bytes(&root)?),
        ("merge.json", json_bytes(&merge)?),
        ("request.json", json_bytes(&request)?),
    ] {
        files.insert(name.into(), json!(format!("{:x}", Sha256::digest(&bytes))));
        std::fs::write(stage.path.join(name), bytes)?;
    }
    let manifest = json!({"format":"eggfuse.cpu-bundle/v1","profile":request["cpu_profile"],"seed":seed,"files":files});
    std::fs::write(
        stage.path.join("bundle-manifest.json"),
        json_bytes(&manifest)?,
    )?;
    if out.exists() {
        return Err("bundle destination appeared during compilation".into());
    }
    std::fs::rename(&stage.path, out)?;
    stage.published = true;
    Ok(())
}
