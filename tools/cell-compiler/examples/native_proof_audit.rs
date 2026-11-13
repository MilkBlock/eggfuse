//! Actual CPU runtime Eq-delta auditor; optional saved GPU proposals are replay.
use eggfuse_cell_runtime::{
    executor::{CellBindingObserver, Executor},
    graph::Graph,
    program::Program,
    proof_audit::{Audit, Proposal},
};
use serde_json::{json, Value};
use std::{cell::RefCell, env, fs, io, rc::Rc, time::Instant};
fn err(e: impl ToString) -> io::Error {
    io::Error::other(e.to_string())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().skip(1).collect();
    if !(2..=3).contains(&args.len()) {
        return Err(err("PROGRAM OUTPUT [PROPOSALS_JSON]").into());
    }
    let artifact: Value = serde_json::from_slice(&fs::read(&args[0])?)?;
    let start = Instant::now();
    let program = Program::parse(artifact.clone()).map_err(err)?;
    let audit = Rc::new(RefCell::new(Audit::new(&program, 0)));
    let hook = audit.clone();
    let mut executor = Executor::new(Graph::new(program).map_err(err)?, false);
    executor.binding_observer = Some(CellBindingObserver {
        rules: vec![true; artifact["recipe"]["rules"].as_array().unwrap().len()],
        observe: Box::new(move |_, index, rule, slots, graph| {
            hook.borrow_mut().capture(index, rule, slots, graph)
        }),
    });
    let setup_seconds = start.elapsed().as_secs_f64();
    let mut frames = vec![];
    let start = Instant::now();
    while !executor.tasks.is_empty() {
        let before = executor.steps.len();
        executor.execute_until(Some(before + 1)).map_err(err)?;
        if executor.steps.len() > before {
            frames.push(audit.borrow_mut().finish(before + 1, &executor.graph));
        }
    }
    let audited_execution_seconds = start.elapsed().as_secs_f64();
    let mut reference = Executor::new(
        Graph::new(Program::parse(artifact).map_err(err)?).map_err(err)?,
        false,
    );
    let start = Instant::now();
    reference.execute().map_err(err)?;
    let reference_execution_seconds = start.elapsed().as_secs_f64();
    assert_eq!(
        executor.graph.export().map_err(err)?,
        reference.graph.export().map_err(err)?
    );
    assert_eq!(executor.steps.len(), reference.steps.len());
    for (a, b) in executor.steps.iter().zip(&reference.steps) {
        assert_eq!(
            (
                a.ordinal,
                &a.ruleset,
                &a.path,
                &a.iterations,
                a.epoch,
                a.changed,
                a.executed_bindings
            ),
            (
                b.ordinal,
                &b.ruleset,
                &b.path,
                &b.iterations,
                b.epoch,
                b.changed,
                b.executed_bindings
            )
        );
    }
    let proposals: Vec<Proposal> = if args.len() == 3 {
        serde_json::from_slice(&fs::read(&args[2])?)?
    } else {
        frames
            .iter()
            .map(|f| Proposal {
                execution: f.execution,
                program: f.program.clone(),
                run: f.run,
                epoch: f.epoch,
                equalities: f
                    .outcomes
                    .iter()
                    .filter(|o| o.equal)
                    .map(|o| o.claim.clone())
                    .collect(),
            })
            .collect()
    };
    // One packet per Run, including empty Runs: missing packets cannot pass.
    let start = Instant::now();
    let verdicts = frames
        .iter()
        .zip(&proposals)
        .map(|(f, p)| f.check(p))
        .collect::<Vec<_>>();
    let check_seconds = start.elapsed().as_secs_f64();
    let pass = frames.len() == proposals.len() && verdicts.iter().all(|v| v.pass);
    fs::write(
        &args[1],
        serde_json::to_vec(
            &json!({"scope":"actual CPU Cell runtime Eq-delta audit; saved proposal replay; no GPU takeover", "proposal_source":if args.len()==3{"external replay"}else{"exact checker control, not GPU predictions"},"pass":pass,"setup_seconds":setup_seconds,"audited_execution_seconds":audited_execution_seconds,"reference_execution_seconds":reference_execution_seconds,"check_seconds":check_seconds,"stats":audit.borrow().stats,"run_boundaries_equal":true,"final_graph_equal":true,"frames":frames,"verdicts":verdicts}),
        )?,
    )?;
    if !pass {
        return Err(err("proposal audit failed").into());
    }
    Ok(())
}
