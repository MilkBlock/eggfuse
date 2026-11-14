//! Actual input and RHS result evidence. Read-only, before repair; audited per Run.
use eggfuse_cell_runtime::{
    executor::{CellBindingObserver, CellResultObserver, Executor},
    graph::Graph,
    program::Program,
    value,
};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    env, fs, io,
    rc::Rc,
    time::Instant,
};
fn err(e: impl ToString) -> io::Error {
    io::Error::other(e.to_string())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().skip(1).collect();
    if args.len() < 2
        || args[2..]
            .iter()
            .any(|s| s != "--all-slots" && s != "--relations" && !s.starts_with("--snapshot-runs="))
    {
        return Err(
            err("PROGRAM OUTPUT [--all-slots] [--relations] [--snapshot-runs=0,1,...]").into(),
        );
    }
    let snapshot_runs = snapshot_runs(&args[2..])?;
    let mut boundaries = Vec::new();
    let mut source_observations: Vec<Value> = Vec::new();
    let input = &args[0];
    let output = &args[1];
    let relations = true;
    let all_slots = relations || args.iter().any(|s| s == "--all-slots");
    let artifact: Value = serde_json::from_slice(&fs::read(input)?)?;
    let rules = artifact["recipe"]["rules"]
        .as_array()
        .ok_or_else(|| err("rules"))?;
    let selected: Vec<bool> = rules
        .iter()
        .map(|r| {
            all_slots
                || r["effects"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .any(|o| o["kind"] == "compute")
        })
        .collect();
    let sorts: Vec<Vec<Value>> = rules
        .iter()
        .map(|r| {
            r["slots"]
                .as_array()
                .unwrap()
                .iter()
                .map(|s| s["sort"].clone())
                .collect()
        })
        .collect();
    let records = Rc::new(RefCell::new(BTreeMap::<usize, Vec<Value>>::new()));
    let captured = records.clone();
    let observer_seconds = Rc::new(RefCell::new(0.));
    let timer = observer_seconds.clone();
    let mut executor = Executor::new(
        Graph::new(Program::parse(artifact.clone()).map_err(err)?).map_err(err)?,
        false,
    );
    executor.binding_observer = Some(CellBindingObserver {
        rules: vec![true; rules.len()],
        observe: Box::new(move |run, index, rid, slots, graph| {
            let start = Instant::now();
            let values = if selected[rid] {
                slots
                    .iter()
                    .map(|(i, v)| json!({"slot":i,"value":value::exported(v,&sorts[rid][*i])}))
                    .collect::<Vec<_>>()
            } else {
                vec![]
            };
            let mut store = captured.borrow_mut();
            let rows = store.entry(run).or_default();
            assert_eq!(rows.len(), index);
            let ports = if relations {
                slots.iter().filter_map(|(slot,v)|if let value::Value::Eq(id)=v {Some(json!({"slot":slot,"sort":sorts[rid][*slot]["name"],"identity":id,"before":value::root(&graph.parents,*id)}))}else{None}).collect::<Vec<_>>()
            } else {
                vec![]
            };
            rows.push(json!({"rule":rid,"values":values,"eq_ports":ports}));
            *timer.borrow_mut() += start.elapsed().as_secs_f64();
        }),
    });
    let results = records.clone();
    let result_sorts = sorts_for(&artifact);
    let result_time = Rc::new(RefCell::new(0.));
    let result_timer = result_time.clone();
    let captured_counts = Rc::new(RefCell::new(BTreeMap::<usize, usize>::new()));
    let result_counts = captured_counts.clone();
    executor.result_observer = Some(CellResultObserver {
        slots: result_sorts
            .iter()
            .map(|s| (0..s.len()).collect())
            .collect(),
        observe: Box::new(move |run, rid, completed, values, graph| {
            let start = Instant::now();
            let mut counts = result_counts.borrow_mut();
            let ordinal = counts.entry(run).or_default();
            let mut records = results.borrow_mut();
            let row = &mut records.get_mut(&run).expect("matched Run")[*ordinal];
            assert_eq!(row["rule"], json!(rid));
            *ordinal += 1;
            let outputs=values.into_iter().map(|(slot,v)|match v {
    Ok(v)=>{
     let mut out=json!({"slot":slot,"value":value::exported(&v,&result_sorts[rid][slot])});
     if let value::Value::Eq(id)=v {out["eq_port"]=json!({"sort":result_sorts[rid][slot]["name"],"identity":id,"at_rhs":value::root(&graph.parents,id)});}
     out
    },
    Err(reason)=>json!({"slot":slot,"unavailable":reason}),
   }).collect::<Vec<_>>();
            row["rhs"] = json!({"completed":completed,"slots":outputs});
            *result_timer.borrow_mut() += start.elapsed().as_secs_f64();
        }),
    });
    let mut reference = Executor::new(
        Graph::new(Program::parse(artifact.clone()).map_err(err)?).map_err(err)?,
        false,
    );
    if snapshot_runs.contains(&0) {
        let graph = executor.graph.export().map_err(err)?;
        assert_eq!(graph, reference.graph.export().map_err(err)?);
        boundaries.push(json!({"ordinal":0,"graph":graph}));
    }
    let mut reference_seconds = 0.;
    let mut run_graph_audit_seconds = 0.;
    let mut observed_execution_seconds = 0.;
    let start = Instant::now();
    if relations {
        while !executor.tasks.is_empty() {
            let next = executor.steps.len() + 1;
            let clock = Instant::now();
            #[cfg(feature = "slot-transfer-audit")]
            eggfuse_cell_runtime::transfer_audit::observation::begin(0..rules.len(), usize::MAX);
            executor.execute_until(Some(next)).map_err(err)?;
            #[cfg(feature = "slot-transfer-audit")]
            source_observations.push(json!({"ordinal":next,
                "observation":eggfuse_cell_runtime::transfer_audit::observation::finish()}));
            observed_execution_seconds += clock.elapsed().as_secs_f64();
            let clock = Instant::now();
            reference.execute_until(Some(next)).map_err(err)?;
            reference_seconds += clock.elapsed().as_secs_f64();
            let clock = Instant::now();
            let graph = executor.graph.export().map_err(err)?;
            assert_eq!(graph, reference.graph.export().map_err(err)?);
            if executor.steps.last().is_some_and(|s| s.ordinal == next)
                && snapshot_runs.contains(&next)
            {
                boundaries.push(json!({"ordinal":next,"graph":graph}));
            }
            run_graph_audit_seconds += clock.elapsed().as_secs_f64();
            if let Some(rows) = records.borrow_mut().get_mut(&next) {
                assert_eq!(
                    captured_counts.borrow().get(&next).copied().unwrap_or(0),
                    rows.len()
                );
                for row in rows.iter_mut() {
                    for slot in row["rhs"]["slots"].as_array_mut().unwrap() {
                        if let Some(port) = slot.get_mut("eq_port") {
                            let id = port["identity"].as_u64().unwrap();
                            port["after_run"] = json!(value::root(&executor.graph.parents, id));
                        }
                    }
                }
                for row in rows {
                    for port in row["eq_ports"].as_array_mut().unwrap() {
                        let id = port["identity"].as_u64().unwrap();
                        port["after"] = json!(value::root(&executor.graph.parents, id));
                    }
                }
            }
        }
    } else {
        executor.execute().map_err(err)?;
    }
    let execution_seconds = start.elapsed().as_secs_f64();
    assert!(executor.snapshots.is_empty() && executor.binding_audit.is_empty());
    let final_graph = executor.graph.export().map_err(err)?;

    assert_eq!(final_graph, reference.graph.export().map_err(err)?);
    assert_eq!(executor.steps.len(), reference.steps.len());
    for (a, b) in executor.steps.iter().zip(&reference.steps) {
        assert_eq!(
            (
                a.ordinal,
                a.ruleset.as_str(),
                a.changed,
                a.executed_bindings
            ),
            (
                b.ordinal,
                b.ruleset.as_str(),
                b.changed,
                b.executed_bindings
            )
        );
    }
    if boundaries.len() != snapshot_runs.len() {
        return Err(err("requested snapshot Run was not executed").into());
    }
    let runs = records
        .borrow()
        .iter()
        .map(|(ordinal, bindings)| json!({"ordinal":ordinal,"audit":{"bindings":bindings}}))
        .collect::<Vec<_>>();
    fs::write(
        output,
        serde_json::to_vec(
            &json!({"schema":"eggcc-gpu-supervision-rhs-trace/v1","recipe":artifact["recipe"],"steps":executor.steps,"all_slots":all_slots,"relations":relations,"program_sha256":artifact["sha256"],"runs":runs,
  "capture_and_audit_wall_seconds":execution_seconds,"audited_execution_seconds":observed_execution_seconds,"reference_execution_seconds":reference_seconds,"observer_seconds":*observer_seconds.borrow(),"result_observer_seconds":*result_time.borrow(),"run_graph_audit_seconds":run_graph_audit_seconds,"strict_run_graphs_equal":true,
  "strict_audit_reference_equal":true,"run_control_counts_equal":true,"source_observations":source_observations,"source_observation_enabled":cfg!(feature="slot-transfer-audit"),"full_snapshots":boundaries.len(),"boundaries":boundaries,"final":final_graph,
  "scope":if all_slots{"actual CPU inputs and RHS slot reads before repair; missing results explicit; no GPU takeover"}else{"live read-only Cell observer; scalar slots only; no GPU writeback"}}),
        )?,
    )?;
    Ok(())
}

fn sorts_for(artifact: &Value) -> Vec<Vec<Value>> {
    artifact["recipe"]["rules"]
        .as_array()
        .unwrap()
        .iter()
        .map(|r| {
            r["slots"]
                .as_array()
                .unwrap()
                .iter()
                .map(|s| s["sort"].clone())
                .collect()
        })
        .collect()
}

fn snapshot_runs(args: &[String]) -> Result<BTreeSet<usize>, io::Error> {
    let mut result = BTreeSet::new();
    for arg in args {
        if let Some(list) = arg.strip_prefix("--snapshot-runs=") {
            for value in list.split(',') {
                let ordinal = value
                    .parse::<usize>()
                    .map_err(|_| err("snapshot Run must be a nonnegative integer"))?;
                if !result.insert(ordinal) {
                    return Err(err("duplicate snapshot Run"));
                }
            }
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounded_explicit_snapshot_selection() {
        assert!(snapshot_runs(&[]).unwrap().is_empty());
        assert_eq!(
            snapshot_runs(&["--snapshot-runs=0,3,9".into()]).unwrap(),
            BTreeSet::from([0, 3, 9])
        );
        for value in ["", "-1", "1,1", "2,x"] {
            assert!(snapshot_runs(&[format!("--snapshot-runs={value}")]).is_err());
        }
    }
}
