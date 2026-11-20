//! Each request runs the complete native schedule on one freshly initialized Graph.
//! Per-binding attribution is taken at the native commit boundary after deduplication.
use eggfuse_cell_runtime::{
    executor::Executor, graph::Graph, ordinary_witness, program::Program, transfer_audit,
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    io::{BufRead, Write},
    path::Path,
    time::Instant,
};

const FROZEN_BUNDLE_SETTINGS: Option<&str> = None;
const FILE_FIELDS: &[&str] = &[
    "single_config",
    "multi_weights",
    "merge_config",
    "root_config",
    "baked_codes",
    "secondary_weights",
    "secondary_codes",
];

fn verify_profile(request: &Value) -> Result<(), Box<dyn std::error::Error>> {
    if request.get("cpu_profile").is_none() {
        return Ok(());
    }
    let encoded = FROZEN_BUNDLE_SETTINGS.ok_or("unsupported compiled CPU bundle profile")?;
    let options: Value = serde_json::from_str(encoded)?;
    for (field, value) in options
        .as_object()
        .ok_or("invalid compiled backend settings")?
    {
        if request.get(field) != Some(value) {
            return Err(format!("CPU bundle profile field mismatch: {field}").into());
        }
    }
    for field in [
        "single_config",
        "multi_weights",
        "merge_config",
        "root_config",
        "baked_codes",
    ] {
        if request[field].as_str().is_none() {
            return Err(format!("missing frozen bundle file: {field}").into());
        }
    }
    Ok(())
}

fn verify_bundle(root: &Path, request: &Value) -> Result<(), Box<dyn std::error::Error>> {
    let manifest = root.join("bundle-manifest.json");
    if !manifest.exists() && request.get("cpu_profile").is_none() {
        return Ok(());
    }
    let profile = request["cpu_profile"]
        .as_str()
        .ok_or("profile missing from versioned bundle")?;
    verify_profile(request)?;
    let data: Value = serde_json::from_slice(&std::fs::read(manifest)?)?;
    if data["profile"].as_str() != Some(profile) || data["format"] != "eggfuse.cpu-bundle/v1" {
        return Err("CPU bundle manifest does not match request".into());
    }
    let files = data["files"]
        .as_object()
        .ok_or("incomplete CPU bundle manifest")?;
    let mut required =
        std::collections::BTreeSet::from(["program.json", "plans.json", "request.json"]);
    for &field in FILE_FIELDS {
        if let Some(value) = request.get(field) {
            let name = value.as_str().ok_or("invalid bundle file reference")?;
            if Path::new(name).file_name().and_then(|part| part.to_str()) != Some(name) {
                return Err("profile file must be a bundle-local filename".into());
            }
            required.insert(name);
        }
    }
    if files.len() != required.len() {
        return Err("bundle file list differs from request".into());
    }
    for name in required {
        let expected = files
            .get(name)
            .and_then(Value::as_str)
            .ok_or("missing bundle file digest")?;
        let mut file = std::fs::File::open(root.join(name))?;
        let mut hash = Sha256::new();
        std::io::copy(&mut file, &mut hash)?;
        if format!("{:x}", hash.finalize()) != expected {
            return Err(format!("bundle digest mismatch: {name}").into());
        }
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let (program_path, plan_path, requests, one_shot): (
        _,
        _,
        Box<dyn Iterator<Item = std::io::Result<String>>>,
        _,
    ) =
        match args.as_slice() {
            [flag, folder] if flag == "--bundle" || flag == "--audit-bundle" => {
                let root = Path::new(folder);
                let mut request: Value =
                    serde_json::from_slice(&std::fs::read(root.join("request.json"))?)?;
                verify_bundle(root, &request)?;
                if flag == "--audit-bundle" {
                    request["audit"] = json!(true);
                    request["full_audit_report"] = json!(true);
                }
                for &field in FILE_FIELDS {
                    if let Some(file) = request[field].as_str() {
                        request[field] = json!(root.join(file));
                    }
                }
                (
                    root.join("program.json"),
                    root.join("plans.json"),
                    Box::new(std::iter::once(Ok(request.to_string()))),
                    true,
                )
            }
            [program, plans] => (
                Path::new(program).to_owned(),
                Path::new(plans).to_owned(),
                Box::new(std::io::stdin().lines()),
                false,
            ),
            _ => return Err(
                "use --bundle DIR for inference, --audit-bundle DIR for full source receipts, or PROGRAM PLANS for a persistent session"
                    .into(),
            ),
        };
    let program_bytes = std::fs::read(program_path)?;
    let digest = format!("{:x}", Sha256::digest(&program_bytes));
    let program = Program::parse(serde_json::from_slice(&program_bytes)?)?;
    let plan = std::fs::read(plan_path)?;
    let mut out = std::io::BufWriter::new(std::io::stdout().lock());
    for line in requests {
        let req: Value = serde_json::from_str(&line?)?;
        if one_shot && req["source_sha256"].as_str() != Some(digest.as_str()) {
            return Err("program digest differs from the compiled bundle".into());
        }
        verify_profile(&req)?;
        const ROOT_SUPPORT: bool = false;
        if req["root_config"].is_string() && !ROOT_SUPPORT {
            return Err("this binary has no root Cell recipe decoder".into());
        }
        const MERGE_SUPPORT: bool = false;
        if req["merge_config"].is_string() && !MERGE_SUPPORT {
            return Err("this binary was built without the nested merge policy".into());
        }
        let audit = req["audit"].as_bool().unwrap_or(false);
        let baseline = req["baseline"].as_bool() == Some(true);
        let mut runtime = Executor::new(Graph::new(program.clone())?, false);
        if baseline {
            ordinary_witness::disable();
        } else {
            let weights = std::fs::read(req["multi_weights"].as_str().ok_or("multi_weights")?)?;
            ordinary_witness::configure(
                &program,
                &plan,
                &weights,
                req["multi_mode"].as_str().ok_or("multi_mode")?,
                u32::try_from(req["radius"].as_u64().ok_or("radius")?)?,
                req["multi_residual"].as_bool().ok_or("multi_residual")?,
                match req.get("multi_generation").map(Value::as_str) {
                    None | Some(Some("bounded")) => usize::try_from(req["cap"].as_u64().ok_or("cap")?)?,
                    Some(Some("complete")) => usize::MAX,
                    _ => return Err("unknown multi-parent generation mode".into()),
                },
                audit,
            )?;

            runtime.use_single_witness(Path::new(
                req["single_config"].as_str().ok_or("single_config")?,
            ))?;
        }
        let initial_cells = runtime.graph.stats.cells_created;
        if audit {
            runtime.allocation_audit = Some(Vec::new());
            runtime.graph.joint_allocations = Some(Vec::new());
            transfer_audit::set_active(true);
            transfer_audit::enable_write_audit();
            transfer_audit::enable_events();
        }
        let start = Instant::now();
        if let Err(error) = runtime.execute() {
            let mut failure = json!({"source_error":error,"runs":runtime.steps.len(),"partial_rhs":ordinary_witness::report()["total_rhs"]});
            if let Some(pending)=ordinary_witness::unfinished_generation(){
                failure["unfinished_generation"]=pending;
            }
            if audit {
                transfer_audit::set_active(false);
                failure["rhs"] = json!(transfer_audit::take_digests());
                let _ = transfer_audit::take_write_digests();
                let _ = transfer_audit::take_resume_digests();
                let _ = transfer_audit::take_events();
            }
            writeln!(out, "{}", failure)?;
            out.flush()?;
            if one_shot {
                return Err("source execution failed".into());
            }
            continue;
        }
        let ms = start.elapsed().as_secs_f64() * 1000.;
        let mut state = vec![];
        runtime.graph.write_export(&mut state)?;
        let mut report = json!({"ms":ms,"state_sha":format!("{:x}",Sha256::digest(&state)),"runs":runtime.steps.len(),
            "single":runtime.single_report(),"multi":ordinary_witness::report()});
        if audit {
            transfer_audit::set_active(false);
            report["rhs"] = json!(transfer_audit::take_digests());
            report["writes"] = json!(transfer_audit::take_write_digests());
            report["resumes"] = json!(transfer_audit::take_resume_digests());
            report["events"] = json!(transfer_audit::take_events().ok_or("missing native events")?);
            report["initial_cells"] = json!(initial_cells);
            report["cell_ids"] = json!(runtime.graph.joint_allocations);
            report["new_cells"] = json!(runtime.graph.stats.cells_created - initial_cells);
            report["allocations"] = json!(runtime.allocation_audit);
            let source = runtime.report();
            report["schedule"] = json!(
                source["steps"]
                    .as_array()
                    .ok_or("missing schedule")?
                    .iter()
                    .map(|s| json!([
                        s["ruleset"],
                        s["epoch"],
                        s["path"],
                        s["iterations"],
                        s["executed_bindings"],
                        s["changed"]
                    ]))
                    .collect::<Vec<_>>()
            );
        }
        let profile_work = req.get("cpu_profile").map(|_| json!({
            "single_policy": report["single"]["mode"],
            "multi_policy": report["multi"]["generator"],
            "views": report["multi"]["embedding_views"],
            "sealed_before_verifier": report["multi"]["sealed_before_verifier"],
            "sealed_tuples": report["multi"]["paged_tuples"],
            "prefix_probes": report["multi"]["forward"]["probes"]
        }));
        if one_shot && req["full_audit_report"] != true {
            let single = &report["single"];
            let multi = &report["multi"];
            // Historical JSON is optional in a resident build. This counter is updated
            // only when the original source commit consumes the winning single token.
            let winners = single["guard_counts"][4].as_u64().unwrap_or(0);
            let learned = matches!(single["mode"].as_str(), Some("learned" | "zero-state"));
            let total = multi["total_rhs"].as_u64().ok_or("missing source count")?;
            let neural = if learned { winners } else { 0 }
                + multi["neural_committed"].as_u64().unwrap_or(0);
            report = json!({"backend":"cpu-rust","runs":report["runs"],"rhs":total,"neural_rhs":neural,
                "remaining_rhs":total-neural,"state_sha":report["state_sha"],"inference_ms":ms,
                "multi_raw_tuples":multi["counts"]["raw_tuples"],"single_scored":single["work"][0],
                "single_emitted":single["work"][1],"root_recipes_applied":report["root_recipe"]["applied"],"root_cells_allocated":report["root_recipe"]["allocated"],"merge_counts":report["merge_child"]["counts"]});
        }
        if one_shot && let Some(profile) = req.get("cpu_profile") {
            report["cpu_profile"] = profile.clone();
            report["profile_execution"] = profile_work.unwrap();
        }
        writeln!(out, "{}", report)?;
        out.flush()?;
    }
    Ok(())
}
