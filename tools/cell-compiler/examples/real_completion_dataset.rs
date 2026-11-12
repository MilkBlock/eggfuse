//! Export real Cell runtime executions, including publication-boundary graphs.
//! Usage: cargo run -p eggfuse-cell-compiler --example real_completion_dataset -- INPUT.json OUTPUT.json
//! Input: {"cases":[{"id":"...","source":"...","metadata":{},"verify_ruleset":"r"}]}.
//! verify_ruleset appends two actual Runs and requires both to leave the graph
//! unchanged. It verifies a fixed point for that ruleset only, not all rulesets.
use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, env, fs, io};

fn err(message: impl Into<String>) -> io::Error {
    io::Error::other(message.into())
}

fn canonical_export(mut graph: Value) -> Value {
    // Same runtime instance: IDs are intentionally not renamed. Sort only
    // enumeration order; preserve every visible/subsumed row and anchor.
    for field in ["rows", "anchors"] {
        if let Some(rows) = graph[field].as_array_mut() {
            rows.sort_by_cached_key(|row| row.to_string());
        }
    }
    graph
}

fn run_case(case: &Value) -> Result<Value, Box<dyn std::error::Error>> {
    let id = case["id"]
        .as_str()
        .ok_or_else(|| err("case.id must be a string"))?;
    let source = case["source"]
        .as_str()
        .ok_or_else(|| err(format!("{id}: source must be a string")))?;
    let verify = match case.get("verify_ruleset") {
        None | Some(Value::Null) => None,
        Some(Value::String(name))
            if !name.is_empty()
                && name
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '-')) =>
        {
            Some(name.as_str())
        }
        _ => {
            return Err(err(format!(
                "{id}: verify_ruleset must be a simple ruleset name"
            ))
            .into());
        }
    };
    let mut executed_source = source.to_owned();
    if let Some(name) = verify {
        executed_source.push_str(&format!(
            "\n(run-schedule (seq (run {name}) (run {name})))\n"
        ));
    }
    let core = eggfuse_bake::device_frontend::core(id, &executed_source)
        .map_err(|e| err(format!("{id}: frontend: {e}")))?;
    let artifact = compiler::compile(core, &BTreeSet::new())
        .map_err(|e| err(format!("{id}: compile: {e}")))?;
    let program_hash = format!("{:x}", Sha256::digest(serde_json::to_vec(&artifact)?));
    let program = Program::parse(artifact.clone()).map_err(|e| err(format!("{id}: parse: {e}")))?;
    let graph = Graph::new(program).map_err(|e| err(format!("{id}: graph: {e}")))?;
    let initial = graph.export().map_err(err)?;
    let mut executor = Executor::new(graph, true);
    // Audit snapshots are taken after each actual Run's completion/publication.
    // execute_until(Some(n)) is available, but audit retains every boundary
    // without guessing how many iterations the source saturation will need.
    executor
        .execute()
        .map_err(|e| err(format!("{id}: execute: {e}")))?;
    let final_graph = executor.graph.export().map_err(err)?;
    if executor.snapshots.len() != executor.steps.len() {
        return Err(err(format!("{id}: missing Run-boundary audit snapshots")).into());
    }
    let mut verification = json!({"requested":false,"status":"not_requested"});
    if let Some(name) = verify {
        let n = executor.steps.len();
        if n < 2 {
            return Err(err(format!("{id}: verification Runs were not executed")).into());
        }
        let before = if n == 2 {
            &initial
        } else {
            &executor.snapshots[n - 3]
        };
        let unchanged = (n - 2..n).all(|i| {
            executor.steps[i]["ruleset"].as_str() == Some(name)
                && executor.steps[i]["changed"].as_bool() == Some(false)
                && canonical_export(executor.snapshots[i].clone())
                    == canonical_export(before.clone())
        });
        verification = json!({"requested":true,"ruleset":name,
            "status":if unchanged {"pass"} else {"difference"},
            "run_ordinals":[n-1,n],"before":before,
            "scope":"two unchanged actual Runs of this ruleset on the same runtime instance"});
        if !unchanged {
            return Err(err(format!(
                "{id}: ruleset {name} is not at the requested fixed point"
            ))
            .into());
        }
    }
    let boundaries: Vec<_> = executor
        .steps
        .iter()
        .zip(&executor.snapshots)
        .map(|(step, graph)| json!({"ordinal":step["ordinal"],"graph":graph}))
        .collect();
    let mut output = json!({"id":id,"metadata":case.get("metadata"),
        "source":source,"source_sha256":format!("{:x}",Sha256::digest(source.as_bytes())),
        "executed_source_sha256":format!("{:x}",Sha256::digest(executed_source.as_bytes())),
        "program_sha256":program_hash,"initial":initial,"final":final_graph,
        "steps":executor.steps,"boundaries":boundaries,"fixed_point":verification,
        "logical_matches_are_committed_mutations":false});
    if case["include_program"].as_bool() == Some(true) {
        output["compiled_program"] = artifact;
    }
    if case["include_bindings"].as_bool() == Some(true) {
        // Successful query bindings, not an apply log or committed mutations.
        // Consumers must also inspect the completed Run's boundary export.
        output["binding_audit"] = json!(executor.binding_audit);
    }
    if case["native_reference"].as_bool() == Some(true) {
        let mut native = egglog::EGraph::default();
        eggfuse_bake::structural_key::source::install(&mut native, &executed_source)
            .map_err(|e| err(format!("{id}: native installation: {e}")))?;
        native
            .parse_and_run_program(Some(id.to_owned()), &executed_source)
            .map_err(|e| err(format!("{id}: native execution: {e}")))?;
        let rows = native
            .device_snapshot()
            .map_err(|e| err(format!("{id}: native export: {e}")))?;
        output["native_final"] = json!({"rows":rows,"anchors":[]});
        output["native_comparison"] = json!({"status":"not_compared",
            "scope":"independent native egglog execution; IDs require structural normalization"});
    }
    Ok(output)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let [input, output] = args.as_slice() else {
        return Err(err("expected INPUT.json OUTPUT.json").into());
    };
    let request: Value = serde_json::from_slice(&fs::read(input)?)?;
    let cases = request["cases"]
        .as_array()
        .ok_or_else(|| err("expected cases array"))?;
    if cases
        .iter()
        .any(|case| case["native_reference"].as_bool() == Some(true))
    {
        egglog::EGraph::set_num_threads(1);
    }
    let mut ids = BTreeSet::new();
    let mut results = Vec::with_capacity(cases.len());
    for case in cases {
        let id = case["id"]
            .as_str()
            .ok_or_else(|| err("case.id must be a string"))?;
        if !ids.insert(id) {
            return Err(err(format!("duplicate case id: {id}")).into());
        }
        results.push(run_case(case)?);
    }
    fs::write(
        output,
        serde_json::to_vec_pretty(&json!({
            "schema":"eggfuse.real-completion-dataset.v1",
            "scope":"actual compiled Cell runtime, empty marker set, full graph exports",
            "cases":results
        }))?,
    )?;
    Ok(())
}
