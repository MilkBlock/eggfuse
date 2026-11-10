//! Finite state implementations extracted by the compile-time Cell egraph.
//! Plans classify inherited and fresh results at original Run boundaries.
use eggfuse_cell_runtime::{program::Program, checksum::artifact_digest};
use serde_json::{Value, json};

pub fn compile(p: &Program) -> Result<Value, Box<dyn std::error::Error>> {
    let contracts = p.iterative.state_contracts(p);
    let mut graph = egglog::EGraph::default();
    graph.parse_and_run_program(None, "(datatype Implementation (Materialize i64 :cost 3) (Inherit i64 :cost 1))")?;
    let mut classes = std::collections::BTreeMap::new();
    let mut implementations = vec![];
    let mut extracted = vec![];
    for (index, contract) in contracts.as_array().unwrap().iter().enumerate() {
        let digest = artifact_digest(contract);
        let next = classes.len();
        let class = *classes.entry(digest).or_insert(next);
        let mut source = format!("(let candidate_{index} (Materialize {class}))");
        if contract["can_inherit"] == true {
            source.push_str(&format!("\n(union candidate_{index} (Inherit {class}))"));
        }
        source.push_str(&format!("\n(extract candidate_{index})"));
        let output = graph.parse_and_run_program(None, &source)?;
        let term = output.iter().find_map(|o| if let egglog::CommandOutput::ExtractBest(dag, _, term) = o {
            Some(dag.to_string(*term))
        } else { None }).ok_or("missing Cell extraction")?;
        implementations.push(if term.starts_with("(Inherit ") { "inherit" } else { "materialize" });
        extracted.push(term);
    }
    Ok(json!({"schema":"eggfuse-cell-state-plan/v2", "contracts":contracts,
        "implementations":implementations,"extracted":extracted,
        "cost_scope":"history transfer containers only; not latency or whole-cell cost"}))
}
