//! Actual eggcc CPU execution with bounded-memory query-binding audit export.
//! This collects successful bindings, not a GPU mutation trace.
use eggfuse_cell_runtime::{executor::Executor,graph::Graph,program::Program};
use serde_json::{Value,json};
use std::{env,fs,io,time::Instant};
fn err(e:impl ToString)->io::Error{io::Error::other(e.to_string())}
fn main()->Result<(),Box<dyn std::error::Error>>{
 let args:Vec<_>=env::args().skip(1).collect();let [input,output]=args.as_slice() else{return Err(err("PROGRAM OUTPUT").into())};
 let bytes=fs::read(input)?;let artifact:Value=serde_json::from_slice(&bytes)?;
 let program=Program::parse(artifact.clone()).map_err(err)?;
 let mut executor=Executor::new(Graph::new(program).map_err(err)?,true);
 let start=Instant::now();let mut runs=Vec::new();
 while !executor.tasks.is_empty(){
  let previous=executor.steps.len();executor.execute_until(Some(previous+1)).map_err(err)?;
  for binding in executor.binding_audit.drain(..){runs.push(json!({"ordinal":executor.steps.len(),"audit":binding}));}
  executor.snapshots.clear();
 }
 let audited_seconds=start.elapsed().as_secs_f64();let final_graph=executor.graph.export().map_err(err)?;
 let start=Instant::now();let mut reference=Executor::new(Graph::new(Program::parse(artifact.clone()).map_err(err)?).map_err(err)?,false);
 reference.execute().map_err(err)?;let reference_seconds=start.elapsed().as_secs_f64();
 let same=final_graph==reference.graph.export().map_err(err)?;
 if !same{return Err(err("audit changes final graph").into())}
 fs::write(output,serde_json::to_vec(&json!({"schema":"eggcc-gpu-supervision-trace/v1",
  "recipe":artifact["recipe"],"program_sha256":artifact["sha256"],"runs":runs,
  "audited_execution_seconds":audited_seconds,"reference_execution_seconds":reference_seconds,
  "strict_audit_reference_equal":same,"final":final_graph,
  "scope":"actual CPU execution and successful bindings; no GPU takeover"}))?)?;Ok(())
}
