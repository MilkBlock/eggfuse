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

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let (program_path, plan_path, requests, one_shot): (
        _,
        _,
        Box<dyn Iterator<Item = std::io::Result<String>>>,
        _,
    ) =
        match args.as_slice() {
            [flag, folder] if flag == "--bundle" => {
                let root = Path::new(folder);
                let mut request: Value =
                    serde_json::from_slice(&std::fs::read(root.join("request.json"))?)?;
                for field in [
                    "single_config",
                    "multi_weights",
                    "merge_config",
                    "root_config",
                ] {
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
                "use --bundle DIR for native inference, or PROGRAM PLANS for a persistent session"
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
        if one_shot {
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
        writeln!(out, "{}", report)?;
        out.flush()?;
    }
    Ok(())
}
