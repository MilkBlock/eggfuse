//! Actual successful Cell inputs and writes at selected source Runs. No timing.
use eggfuse_cell_runtime::{executor::Executor, graph::Graph,
    program::{Call, Op, Program}, transfer_audit::{self, observation}};
use serde::Deserialize;
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, fs::File, io::BufWriter, path::Path,
    process::{Command, Stdio}};

#[derive(Deserialize)]
struct Windows { runs: Vec<usize>, attribute: String }

fn rows(graph: &Graph, tables: &BTreeSet<usize>) -> Result<Json, String> {
    let mut rows = vec![];
    for &table in tables {
        for witness in graph.witnesses(table) {
            if let Some(row) = graph.row(witness)? {
                rows.push(json!({"table":graph.program.tables[table].name,
                    "witness":row.witness,"epoch":row.epoch,
                    "hidden":row.hidden,"values":row.values}));
            }
        }
    }
    Ok(json!(rows))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [program, windows, output, mode, options @ ..] = args.as_slice() else {
        return Err("expected PROGRAM WINDOWS.json OUTPUT observe|control|census [--cell-absorption]".into());
    };
    let absorption = match options { [] => false, [flag] if flag == "--cell-absorption" => true,
        _ => return Err("unknown window option".into()) };
    let observe = match mode.as_str() {
        "observe" => true, "control" | "census" => false, _ => return Err("unknown mode".into()),
    };
    let windows: Windows = serde_json::from_slice(&std::fs::read(windows)?)?;
    if windows.runs.is_empty() || windows.runs[0] == 0
        || windows.runs.windows(2).any(|w| w[0] >= w[1]) {
        return Err("Run ordinals must be positive and strictly increasing".into());
    }
    let p = Program::parse(serde_json::from_slice(&std::fs::read(program)?)?)?;
    let table = p.tables.iter().position(|t| t.name == windows.attribute)
        .ok_or("unknown attribute")?;
    let rules: Vec<_> = p.rules.iter().enumerate().filter_map(|(rid, r)|
        p.templates[r.template].ops.iter().any(|op| matches!(op, Op::Set(t,_,_) if *t == table))
            .then_some(rid)).collect();
    if rules.is_empty() { return Err("no attribute writers".into()); }
    let tables: BTreeSet<_> = rules.iter().flat_map(|&r| p.rules[r].query.iter()
        .filter_map(|atom| match atom.call { Call::Table(t) => Some(t), _ => None }))
        .chain(std::iter::once(table)).collect();
    let mut e = Executor::new(Graph::new_with_repair_ports(p)?, false);
    e.use_entry_publications()?;
    if absorption {
        #[cfg(feature = "cell-absorption")]
        e.use_cell_absorption()?;
        #[cfg(not(feature = "cell-absorption"))]
        return Err("Cell absorption requires cell-absorption".into());
    }
    let output = Path::new(output);
    std::fs::create_dir(output)?;
    let mut checks = vec![];
    if mode == "census" {
        observation::begin_counts(rules.iter().copied(), table);
        transfer_audit::enable_write_audit();
        e.execute()?;
        transfer_audit::set_active(false);
        serde_json::to_writer(BufWriter::new(File::create(output.join("census.json"))?),
            &observation::finish())?;
    }
    for &run in windows.runs.iter().filter(|_| mode != "census") {
        e.execute_until(Some(run - 1))?;
        if e.steps.len() != run - 1 { return Err("source ended before window".into()); }
        let unions = e.graph.stats.unions;
        let before = if observe { rows(&e.graph, &tables)? } else { Json::Null };
        transfer_audit::set_active(true);
        transfer_audit::enable_write_audit();
        if observe { observation::begin(rules.iter().copied(), table); }
        e.execute_until(Some(run))?;
        let capture = if observe { observation::finish() } else { Json::Null };
        transfer_audit::set_active(false);
        checks.push(json!({"run":run,"bindings":transfer_audit::take_digests(),
            "writes":transfer_audit::take_write_digests(),
            "resumes":transfer_audit::take_resume_digests()}));
        if observe {
            let after = rows(&e.graph, &tables)?;
            let mut gzip = Command::new("gzip").arg("-1").stdin(Stdio::piped())
                .stdout(File::create(output.join(format!("run-{run}.json.gz")))?).spawn()?;
            serde_json::to_writer(BufWriter::new(gzip.stdin.take().ok_or("gzip stdin missing")?),
                &json!({"run":run,"step":e.steps.last(),"before":before,"after":after,
                    "unions_before":unions,"unions_after":e.graph.stats.unions,"capture":capture}))?;
            if !gzip.wait()?.success() { return Err("gzip failed".into()); }
        }
    }
    // Stream the complete bounded state into a digest, avoiding a large export.
    let mut hash = Sha256::new();
    e.graph.write_export(&mut hash)?;
    serde_json::to_writer(BufWriter::new(File::create(output.join("checks.json"))?),
        &json!({"state_sha256":format!("{:x}",hash.finalize()),"windows":checks,
            "rules":rules,"attribute":windows.attribute,"complete":e.tasks.is_empty()}))?;
    serde_json::to_writer(BufWriter::new(File::create(output.join("report.json"))?), &e.report())?;
    Ok(())
}
