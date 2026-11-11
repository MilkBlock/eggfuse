//! Selected source-Run boundaries for correctness diagnosis, never timing.
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program, value};
use serde::Deserialize;
use serde_json::json;
use std::{collections::BTreeSet, fs::File, io::BufWriter, path::Path};

#[derive(Deserialize)]
struct Windows {
    runs: Vec<usize>,
    tables: Vec<String>,
    track_roots: String,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [program, windows, output] = args.as_slice() else {
        return Err("expected PROGRAM WINDOWS.json OUTPUT".into());
    };
    let windows: Windows = serde_json::from_slice(&std::fs::read(windows)?)?;
    if windows.runs.is_empty() || windows.runs[0] == 0
        || windows.runs.windows(2).any(|w| w[0] >= w[1]) {
        return Err("Run boundaries must be positive and strictly increasing".into());
    }
    if !windows.tables.contains(&windows.track_roots) {
        return Err("tracked table must be included in the selected tables".into());
    }
    let p = Program::parse(serde_json::from_slice(&std::fs::read(program)?)?)?;
    let tables = windows.tables.iter().map(|name| {
        p.tables.iter().position(|t| &t.name == name).ok_or_else(|| format!("unknown table {name}"))
    }).collect::<Result<Vec<_>, _>>()?;
    let mut e = Executor::new(Graph::new_with_repair_ports(p)?, false);
    #[cfg(feature = "sparse-cells")]
    e.use_entry_publications()?;
    #[cfg(not(feature = "sparse-cells"))]
    return Err("source_windows requires sparse-cells".into());
    let output = Path::new(output);
    std::fs::create_dir(output)?;
    let mut tracked = BTreeSet::new();
    for &run in &windows.runs {
        e.execute_until(Some(run))?;
        if e.steps.len() != run { return Err(format!("source ended before Run {run}").into()); }
        let mut rows = Vec::new();
        for &table in &tables {
            let definition = &e.graph.program.tables[table];
            for witness in e.graph.witnesses(table) {
                if let Some(row) = e.graph.row(witness)? {
                    if definition.name == windows.track_roots {
                        for v in row.values.iter() {
                            if let value::Value::Eq(id) = v { tracked.insert(*id); }
                        }
                    }
                    rows.push(json!({"table":definition.name,"subsumed":row.hidden,
                        "values":row.values.iter().zip(&definition.schema)
                            .map(|(v,s)|value::exported(v,s)).collect::<Vec<_>>()}));
                }
            }
        }
        serde_json::to_writer(BufWriter::new(File::create(output.join(format!("run-{run}.json")))?),
            &json!({"run":run,"unions":e.graph.stats.unions,"rows":rows}))?;
    }
    e.execute()?;
    let roots = tracked.into_iter().map(|id| json!({"old":format!("Cell({id})"),
        "now":format!("Cell({})",value::root(&e.graph.parents,id))})).collect::<Vec<_>>();
    serde_json::to_writer(BufWriter::new(File::create(output.join("tracked-roots.json"))?), &roots)?;
    serde_json::to_writer(BufWriter::new(File::create(output.join("report.json"))?), &e.report())?;
    e.graph.write_export(BufWriter::new(File::create(output.join("state.json"))?))?;
    Ok(())
}
