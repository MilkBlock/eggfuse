//! Audit a bounded prefix of the actual worker configuration before using its
//! passive observations for Bake. The source program and schedule stay intact.
//! Whole control prefix precedes whole observed prefix; this is never timing.
use eggfuse_cell_runtime::{
    checksum::artifact_digest, executor::Executor, graph::Graph, program::Program,
};
use serde_json::{Value, json};
use std::{error::Error, fs, path::Path};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn executor(p: Program, observe: bool) -> Result<Executor> {
    // Keep the same setup order as the ordinary four-worker CLI lane.
    let mut g = Graph::new_with_repair_ports(p)?;
    g.use_cell_ownership()?;
    if observe { g.trace_ownership_catalog(16)?; }
    let mut e = Executor::new(g, true);
    e.use_query_workers(4, 64)?;
    // --entry-publications is intentionally inactive with --cell-ownership.
    e.use_cell_execution(1)?;
    e.use_cell_absorption()?;
    e.use_parallel_residuals()?;
    e.use_parallel_publication()?;
    Ok(e)
}

fn prefix(p: Program, limit: usize, expected: Option<&Value>) -> Result<Value> {
    if limit == 0 { return Err("a nonempty Run prefix is required".into()); }
    let program = p.artifact["sha256"].clone();
    if let Some(expected) = expected {
        if expected["program_sha256"] != program
            || expected["run_limit"] != json!(limit)
            || expected["run_checks"].as_array().map(Vec::len) != Some(limit)
        { return Err("expected checks must cover this exact catalog and Run prefix".into()); }
    }
    let mut e = executor(p, expected.is_some())?;
    let mut checks = Vec::with_capacity(limit);
    for at in 0..limit {
        e.execute_until(Some(at + 1))?;
        if e.steps.len() != at + 1 || e.snapshots.len() != 1 || e.binding_audit.len() != 1 {
            return Err(format!("expected one audited Run at {}; lower the prefix limit if the program ended", at + 1).into());
        }
        let graph = e.snapshots.pop().unwrap();
        let bindings = e.binding_audit.pop().unwrap();
        let step = &e.steps[at];
        let observed = json!({
            "graph": artifact_digest(&graph), "bindings": artifact_digest(&bindings),
            "run": {"ordinal":step.ordinal,"ruleset":step.ruleset,"path":step.path,
                "iterations":step.iterations,"epoch":step.epoch,
                "logical_matches":step.logical_matches,"executed_bindings":step.executed_bindings,
                "changed":step.changed},
        });
        if let Some(expected) = expected {
            if expected["run_checks"][at] != observed {
                return Err(format!("Run {} graph/bindings/source-summary differs", at + 1).into());
            }
        }
        checks.push(observed);
    }
    // Drop each large snapshot at its boundary rather than retaining the
    // prefix's graphs in a second history. Digests are audit output only.
    let mut result = json!({
        "schema":"eggfuse-worker-prefix-audit/v1",
        "scope":"actual standalone four-worker Cell runtime; bounded prefix, not full-program acceptance or timing",
        "program_sha256":program,"run_limit":limit,"runs":limit,
        "full_execution_claimed":false,"run_checks":checks,
        "configuration":{"query_workers":4,"query_grain":64,"cell_execution_grain":1,
            "repair_ports":true,"cell_ownership":true,"cell_absorption":true,
            "parallel_residuals":true,"parallel_publication":true,"audit_stages":true},
        "report":e.report(),
    });
    if let Some(expected) = expected {
        result["all_saved_run_checks_equal"] = json!(true);
        result["expected_trace_digest"] = artifact_digest(expected).into();
        result["catalog_trace"] = e.graph.ownership_catalog_trace()?;
    }
    Ok(result)
}

fn main() -> Result<()> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 3 {
        return Err("usage: worker_prefix_catalog_trace PROGRAM RUN_LIMIT NEW_DIR".into());
    }
    let output = Path::new(&args[2]);
    if output.exists() { return Err("output already exists".into()); }
    let raw: Value = serde_json::from_slice(&fs::read(&args[0])?)?;
    let limit = args[1].parse()?;
    let control = prefix(Program::parse(raw.clone())?, limit, None)?;
    let observed = prefix(Program::parse(raw)?, limit, Some(&control))?;
    fs::create_dir(output)?;
    fs::write(output.join("control.json"), serde_json::to_vec_pretty(&control)?)?;
    fs::write(output.join("trace.json"), serde_json::to_vec_pretty(&observed)?)?;
    println!("{}", json!({"audited_prefix_runs":limit,"full_execution_claimed":false,
        "proposals":observed["catalog_trace"]["records"].as_array().map(Vec::len),
        "witness_recipes":observed["catalog_trace"]["saturation"]["witness_recipes"].as_array().map(Vec::len),
        "all_saved_run_checks_equal":true}));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn program() -> Program {
        let core = eggfuse_bake::device_frontend::core("prefix", r#"
            (datatype E (N i64) (F E) (G E)) (N 1) (N 2)
            (ruleset a) (ruleset b) (ruleset c)
            (rule ((= x (N n))) ((F x)) :ruleset a)
            (rule ((= f (F x))) ((G f)) :ruleset b)
            (rule ((= f (F x))) ((delete (G f))) :ruleset c)
            (run a 1) (run b 1) (run c 1)
        "#).unwrap();
        Program::parse(eggfuse_cell_runtime::compiler::compile(core, &Default::default()).unwrap()).unwrap()
    }
    #[test]
    fn checked_prefix_keeps_the_original_source_and_does_not_claim_the_suffix() {
        let p = program();
        let control = prefix(p.clone(), 2, None).unwrap();
        assert_eq!(control["program_sha256"], p.artifact["sha256"]);
        assert_eq!(control["full_execution_claimed"], false);
        assert!(control.get("all_saved_run_checks_equal").is_none());
        let observed = prefix(p.clone(), 2, Some(&control)).unwrap();
        assert_eq!(observed["run_checks"], control["run_checks"]);
        assert_eq!(observed["all_saved_run_checks_equal"], true);
        assert_eq!(observed["catalog_trace"]["catalog_sha256"], p.artifact["sha256"]);
        let full = prefix(p, 3, None).unwrap();
        assert_ne!(full["run_checks"][1]["graph"], full["run_checks"][2]["graph"]);
    }
    #[test]
    fn rejects_wrong_checks_catalog_limit_and_missing_runs() {
        let p = program();
        let control = prefix(p.clone(), 2, None).unwrap();
        for pointer in ["/program_sha256", "/run_limit", "/run_checks/1/graph", "/run_checks/1/bindings", "/run_checks/1/run/epoch"] {
            let mut invalid = control.clone();
            *invalid.pointer_mut(pointer).unwrap() = Value::Null;
            assert!(prefix(p.clone(), 2, Some(&invalid)).is_err(), "{pointer}");
        }
        assert!(prefix(p.clone(), 0, None).is_err());
        assert!(prefix(p, 4, None).is_err());
    }
}
