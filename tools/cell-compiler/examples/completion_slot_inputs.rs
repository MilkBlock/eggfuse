//! Read completion inputs through existing Cell operands before executing rules.
//! This diagnostic does not reconstruct bindings or introduce runtime state.
use eggfuse_cell_runtime::{
    compiler,
    graph::{Dependency, Graph},
    program::{Arg, Call, Op, Program},
    value::{Value, exported},
};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, env, fs, io, time::Instant};
fn error(s: impl ToString) -> io::Error {
    io::Error::other(s.to_string())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let [input, output] = args.as_slice() else {
        return Err(error("INPUT OUTPUT required").into());
    };
    let request: serde_json::Value = serde_json::from_slice(&fs::read(input)?)?;
    let mut results = vec![];
    for case in request["cases"]
        .as_array()
        .ok_or_else(|| error("cases required"))?
    {
        let source = case["source"]
            .as_str()
            .ok_or_else(|| error("source required"))?;
        let core = eggfuse_bake::device_frontend::core("slot-inputs", source).map_err(error)?;
        let artifact = compiler::compile(core, &BTreeSet::new()).map_err(error)?;
        let program = Program::parse(artifact).map_err(error)?;
        let graph = Graph::new(program).map_err(error)?;
        let mut records = vec![];
        let mut reads = vec![];
        for t in 0..graph.program.tables.len() {
            for witness in graph.witnesses(t) {
                let Some(row) = graph.row(witness).map_err(error)? else {
                    continue;
                };
                let Dependency::Fact(f) = witness else {
                    return Err(error("fixture requires constructor facts").into());
                };
                let cell = graph
                    .cells
                    .get(&f.cell)
                    .ok_or_else(|| error("missing owner"))?;
                let template = &graph.program.templates[cell.template];
                let Op::Let(_, Call::Table(table), operands) = &template.ops[f.op as usize] else {
                    return Err(error("unexpected fact operation").into());
                };
                if *table != t {
                    return Err(error("table mismatch").into());
                }
                let mut fields = vec![];
                for (column, arg) in operands.iter().enumerate() {
                    if let Value::Int(expected) = &row.values[column] {
                        let actual = graph.argument(f.cell, arg).map_err(error)?;
                        if actual != Value::Int(*expected) {
                            return Err(error("slot and row disagree").into());
                        }
                        reads.push((f.cell, arg.clone()));
                        fields.push(json!({"column":column,"buffer_index":reads.len()-1,"cell":f.cell,"template":cell.template,"source":match arg{Arg::Slot(s)=>json!({"slot":s}),Arg::Literal(_)=>json!({"literal":true})}}));
                    }
                }
                records.push(json!({"table":graph.program.tables[t].name,
                    "values":row.values.iter().zip(&graph.program.tables[t].schema).map(|(v,s)|exported(v,s)).collect::<Vec<_>>(),
                    "subsumed":row.hidden,"scalar_fields":fields}));
            }
        }
        // Read the precompiled operand list directly: no row materialization in timed region.
        let start = Instant::now();
        let mut values = vec![];
        for _ in 0..100 {
            values.clear();
            for (cell, arg) in &reads {
                let Value::Int(x) = graph.argument(*cell, arg).map_err(error)? else {
                    return Err(error("integer expected").into());
                };
                values.push(x);
            }
            std::hint::black_box(&values);
        }
        let gather_ns = start.elapsed().as_nanos() as f64 / 100.;
        results.push(json!({"id":case["id"],"source_sha256":format!("{:x}",Sha256::digest(source.as_bytes())),"rows":records,"scalar_values":values,
            "operand_reads":reads.len(),"slot_reads":reads.iter().filter(|(_,a)|matches!(a,Arg::Slot(_))).count(),
            "gather_nanoseconds":gather_ns,"timing_scope":"warm Graph.argument only, excludes compilation and export"}));
    }
    fs::write(
        output,
        serde_json::to_vec_pretty(
            &json!({"scope":"actual initial Cell operands, before rule execution","cases":results}),
        )?,
    )?;
    Ok(())
}
