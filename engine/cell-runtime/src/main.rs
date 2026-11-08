#[cfg(feature = "allocation-metrics")]
mod allocation_metrics;
#[cfg(feature = "allocation-metrics")]
#[global_allocator]
static ALLOCATOR: allocation_metrics::Meter = allocation_metrics::Meter;
#[cfg(not(feature = "allocation-metrics"))]
#[global_allocator]
static ALLOCATOR: mimalloc::MiMalloc = mimalloc::MiMalloc;
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};
use std::{path::PathBuf, time::Instant};
#[cfg(all(unix, feature = "storage-metrics"))]
fn peak_rss_bytes() -> Result<u64, Box<dyn std::error::Error>> {
    let mut usage = std::mem::MaybeUninit::<libc::rusage>::uninit();
    // getrusage initializes the output on success. Darwin reports bytes;
    // Linux reports KiB. Sample before building any export or report.
    if unsafe { libc::getrusage(libc::RUSAGE_SELF, usage.as_mut_ptr()) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let peak = unsafe { usage.assume_init() }.ru_maxrss as u64;
    Ok(if cfg!(target_os = "macos") {
        peak
    } else {
        peak * 1024
    })
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let opt = |k: &str| args.windows(2).find(|w| w[0] == k).map(|w| w[1].clone());
    if args.iter().any(|x| x == "--help") || args.is_empty() {
        println!(
            "eggfuse-cell-runtime --program FILE [--inspect-program | --output DIR] [--audit-stages] [--extract-unit-cost OPERATOR]"
        );
        println!("  --union-digest [--union-digest-hash-bits 0..64] (experimental constructor and scalar Unit matcher)");
        println!("  --congruence-cells (experimental equality expressions and persistent completion cells)");
        #[cfg(feature = "spine-blocks")]
        println!("  --repair-cells (experimental shared Cell repair templates)");
        println!("  --local-unions (experimental Cell-internal union completion without birth subscriptions)");
        println!("  --cell-ownership (persistent cross-stage scalar Cell completion)");
        println!("  --stable-ports (Cell ownership with stable stored equality fields)");
        println!("  --port-keys (stable fields and exact constructor matching through port domains)");
        println!("  --local-congruence (shared local conditions with checked boundary coverage)");
        println!("  --scoped-execution (experimental compiler-scoped waits and selective publication)");
        println!("  --scoped-queues (compiler-scoped ready queues; source Run publication barrier retained)");
        println!("  --repair-ports (experimental typed constructor result-port propagation)");
        #[cfg(feature = "sparse-cells")]
        println!("  --entry-publications (shared entry nodes own producer expressions)");
        #[cfg(feature = "structural-depth")]
        println!("  --structural-depth 0..3 [--structural-survey | --structural-catalog FILE]");
        #[cfg(feature = "rhs-locals")]
        println!("  --rhs-local-width N [--rhs-local-profile FILE] (0 disables local RHS blocks)");
        #[cfg(feature = "rhs-work-audit")]
        println!("  --rhs-cohort FILE (replay the recorded RHS work cohort)");
        return Ok(());
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut flags = args.iter();
    while let Some(flag) = flags.next() {
        if !seen.insert(flag) {
            return Err(format!("duplicate option {flag}").into());
        }
        match flag.as_str() {
            "--program" | "--output" | "--extract-unit-cost" | "--union-digest-hash-bits" => {
                flags
                    .next()
                    .filter(|v| !v.starts_with("--"))
                    .ok_or_else(|| format!("missing value for {flag}"))?;
            }
            #[cfg(feature = "structural-depth")]
            "--structural-depth" | "--structural-catalog" => {
                flags
                    .next()
                    .filter(|v| !v.starts_with("--"))
                    .ok_or_else(|| format!("missing value for {flag}"))?;
            }
            #[cfg(feature = "structural-depth")]
            "--structural-survey" => {}
            #[cfg(feature = "rhs-work-audit")]
            "--rhs-cohort" => {
                flags
                    .next()
                    .filter(|s| !s.starts_with("--"))
                    .ok_or("missing cohort path")?;
            }
            #[cfg(feature = "rhs-locals")]
            "--rhs-local-width" | "--rhs-local-profile" => {
                flags
                    .next()
                    .filter(|s| !s.starts_with("--"))
                    .ok_or("missing block width")?;
            }
            #[cfg(feature = "keeper-proof")]
            "--keeper-pairs" => {
                flags
                    .next()
                    .filter(|v| !v.starts_with("--"))
                    .ok_or("missing keeper pairs")?;
            }
            #[cfg(feature = "spine-blocks")]
            "--repair-cells" => {}
            "--audit-stages" | "--inspect-program" | "--cell-ownership" | "--stable-ports" | "--port-keys" | "--local-congruence" | "--scoped-queues" | "--scoped-execution" | "--local-unions" | "--union-digest" | "--congruence-cells" | "--repair-ports" => {}
            #[cfg(feature = "sparse-cells")]
            "--entry-publications" => {}
            _ => return Err(format!("unknown option {flag}").into()),
        }
    }
    let load_start = Instant::now();
    let bytes = std::fs::read(opt("--program").ok_or("--program required")?)?;
    let program = Program::parse(serde_json::from_slice(&bytes)?)?;
    let load_seconds = load_start.elapsed().as_secs_f64();
    if args.iter().any(|x| x == "--inspect-program") {
        let (rules, orientations) = program.context_cut_counts();
        println!(
            "{}",
            serde_json::json!({"context_cut_rules":rules,"context_cut_orientations":orientations,"backend":"cell-cpu", "validated":true,
            })
        );
        return Ok(());
    }
    let digest = args.iter().any(|x| x == "--union-digest");
    let expressions = args.iter().any(|x| x == "--congruence-cells");
    let cells = args.iter().any(|x| x == "--repair-cells");
    let local = args.iter().any(|x| x == "--local-unions");
    let scoped_execution = args.iter().any(|x| x == "--scoped-execution");
    let scoped_queues = scoped_execution || args.iter().any(|x| x == "--scoped-queues");
    let local_conditions = scoped_queues || args.iter().any(|x| x == "--local-congruence");
    let port_keys = local_conditions || args.iter().any(|x| x == "--port-keys");
    let stable_ports = port_keys || args.iter().any(|x| x == "--stable-ports");
    let ownership = stable_ports || args.iter().any(|x| x == "--cell-ownership");
    if ownership && (local || cells || digest || expressions) {
        return Err("--cell-ownership requires its own completion backend".into());
    }
    let ports = args.iter().any(|x| x == "--repair-ports");
    if (ports || cells || local) && (digest || expressions) {
        return Err("repair ports currently require the ordinary repair backend".into());
    }
    if digest && expressions {
        return Err("choose --union-digest or --congruence-cells".into());
    }
    if !digest && !expressions && opt("--union-digest-hash-bits").is_some() {
        return Err("--union-digest-hash-bits requires --union-digest or --congruence-cells".into());
    }
    let out = PathBuf::from(opt("--output").ok_or("--output required")?);
    let start = Instant::now();
    let audit = args.iter().any(|x| x == "--audit-stages");
    let mut graph = if digest || expressions {
        let bits = opt("--union-digest-hash-bits")
            .map(|v| v.parse()).transpose()?.unwrap_or(64);
        if expressions {
            Graph::new_with_congruence_cells(program, bits)?
        } else {
            Graph::new_with_union_digest(program, bits)?
        }
    } else if cells {
        #[cfg(feature = "spine-blocks")]
        { Graph::new_with_repair_cells(program)? }
        #[cfg(not(feature = "spine-blocks"))]
        { return Err("repair cells require spine-blocks".into()); }
    } else if ports || local || ownership {
        Graph::new_with_repair_ports(program)?
    } else {
        Graph::new(program)?
    };
    if local { graph.use_local_union_cells()?; }
    if ownership { graph.use_cell_ownership()?; }
    if stable_ports { graph.use_stable_port_fields()?; }
    if port_keys { graph.use_port_constructor_matching()?; }
    if local_conditions { graph.use_local_port_conditions()?; }
    if scoped_queues { graph.use_scoped_completion()?; }
    std::fs::create_dir(&out)?;
    let mut runtime = Executor::new(graph, audit);
    if scoped_execution { runtime.use_scoped_execution()?; }
    #[cfg(feature = "sparse-cells")]
    if !ownership && args.iter().any(|x| x == "--entry-publications") {
        runtime.use_entry_publications()?;
    }
    #[cfg(feature = "structural-depth")]
    {
        let survey = args.iter().any(|x| x == "--structural-survey");
        let depth = opt("--structural-depth")
            .map(|s| s.parse())
            .transpose()?
            .unwrap_or(if survey { 3 } else { 0 });
        runtime.configure_depth(depth, survey)?;
        if let Some(path) = opt("--structural-catalog") {
            runtime.use_depth_catalog(serde_json::from_reader(std::fs::File::open(path)?)?)?;
        }
    }
    #[cfg(feature = "rhs-work-audit")]
    if let Some(path) = opt("--rhs-cohort") {
        runtime.rhs_cohort(std::path::Path::new(&path))?;
    }
    #[cfg(feature = "rhs-locals")]
    runtime.configure_rhs_locals(
        opt("--rhs-local-width")
            .map(|v| v.parse())
            .transpose()?
            .unwrap_or(0),
    )?;
    #[cfg(feature = "rhs-locals")]
    if let Some(path) = opt("--rhs-local-profile") {
        runtime.use_rhs_local_profile(&serde_json::from_reader(std::fs::File::open(path)?)?)?;
    }
    #[cfg(feature = "keeper-proof")]
    if let Some(path) = opt("--keeper-pairs") {
        runtime.read_keepers(std::path::Path::new(&path))?;
    }
    #[cfg(all(unix, feature = "storage-metrics"))]
    let setup_peak_rss_bytes = peak_rss_bytes()?;
    let setup = start.elapsed().as_secs_f64();
    let start = Instant::now();
    #[cfg(feature = "slot-transfer-audit")]
    {
        eggfuse_cell_runtime::transfer_audit::set_active(true);
        eggfuse_cell_runtime::transfer_audit::enable_write_audit();
    }
    #[cfg(feature = "allocation-metrics")]
    let allocation_start = allocation_metrics::begin();
    if let Err(error) = runtime.execute() {
        std::fs::write(
            out.join("failure.json"),
            serde_json::to_vec_pretty(
                &serde_json::json!({"error":error,"status":"error","completed_steps":runtime.steps}),
            )?,
        )?;
        return Err(error.into());
    }
    #[cfg(feature = "allocation-metrics")]
    let allocation_delta = allocation_metrics::end(allocation_start);
    #[cfg(feature = "slot-transfer-audit")]
    {
        eggfuse_cell_runtime::transfer_audit::set_active(false);
        std::fs::write(
            out.join("resumes.json"),
            serde_json::to_vec(&eggfuse_cell_runtime::transfer_audit::take_resume_digests())?,
        )?;
        std::fs::write(
            out.join("writes.json"),
            serde_json::to_vec(&eggfuse_cell_runtime::transfer_audit::take_write_digests())?,
        )?;
        std::fs::write(
            out.join("rhs.json"),
            serde_json::to_vec(&eggfuse_cell_runtime::transfer_audit::take_digests())?,
        )?;
    }
    let seconds = start.elapsed().as_secs_f64();
    #[cfg(all(unix, feature = "storage-metrics"))]
    let inference_peak_rss_bytes = peak_rss_bytes()?;
    #[cfg(feature = "spine-shapes")]
    std::fs::write(
        out.join("spine-shapes.json"),
        serde_json::to_vec(&runtime.spine_shape_report())?,
    )?;
    #[cfg(feature = "family-survey")]
    std::fs::write(
        out.join("family-survey.json"),
        serde_json::to_vec(&runtime.family_survey())?,
    )?;
    #[cfg(feature = "structural-depth")]
    {
        let report = runtime.depth_report();
        if !report["catalog"].is_null() {
            std::fs::write(
                out.join("structural-catalog.json"),
                serde_json::to_vec_pretty(&report["catalog"])?,
            )?;
        }
        std::fs::write(
            out.join("structural-depth.json"),
            serde_json::to_vec(&report)?,
        )?;
    }
    #[cfg(feature = "rhs-work-audit")]
    runtime.write_rhs_work(&out)?;
    #[cfg(feature = "keeper-proof")]
    runtime.write_keepers(&out)?;
    let mut report = runtime.report();
    #[cfg(feature = "allocation-metrics")]
    {
        report["allocations"] = allocation_delta.report();
    }
    #[cfg(all(unix, feature = "storage-metrics"))]
    {
        report["peak_rss_through_setup_bytes"] = setup_peak_rss_bytes.into();
        report["peak_rss_through_inference_bytes"] = inference_peak_rss_bytes.into();
        report["storage"] = runtime.graph.storage_sample();
    }
    #[cfg(feature = "rhs-locals")]
    {
        report["rhs_locals"] = runtime.rhs_local_report();
    }
    report["inference_seconds"] = seconds.into();
    report["setup_seconds"] = setup.into();
    report["load_seconds"] = load_seconds.into();
    report["load_setup_inference_seconds"] = (load_seconds + setup + seconds).into();
    report["repair_ports"] = runtime.graph.repair_port_report();
    let export_start = Instant::now();
    let mut writer = std::io::BufWriter::new(std::fs::File::create(out.join("state.json"))?);
    runtime.graph.write_export(&mut writer)?;
    std::io::Write::flush(&mut writer)?;
    report["export_seconds"] = export_start.elapsed().as_secs_f64().into();
    if let Some(op) = opt("--extract-unit-cost") {
        std::fs::write(
            out.join("extraction.json"),
            serde_json::to_vec_pretty(&runtime.graph.extract_unit_cost(&op)?)?,
        )?;
    }
    if runtime.audit {
        if let Some(nodes) = runtime.graph.congruence_cells_audit() {
            std::fs::write(out.join("congruence-cells.json"), serde_json::to_vec(&nodes)?)?;
        }
        std::fs::write(
            out.join("stages.json"),
            serde_json::to_vec(&runtime.snapshots)?,
        )?;
        std::fs::write(
            out.join("binding-audit.json"),
            serde_json::to_vec(
                &serde_json::json!({"initial":runtime.initial_audit,"runs":runtime.binding_audit}),
            )?,
        )?;
    }
    std::fs::write(out.join("report.json"), serde_json::to_vec_pretty(&report)?)?;
    println!(
        "{}",
        serde_json::json!({"status":report["status"],"inference_seconds":seconds,"live_cells":runtime.graph.cells.len(),"stats":runtime.graph.stats})
    );
    Ok(())
}
