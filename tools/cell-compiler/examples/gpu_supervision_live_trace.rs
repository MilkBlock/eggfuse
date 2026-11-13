//! Lightweight actual Cell-binding observer, without full Run snapshots.
use eggfuse_cell_runtime::{executor::{Executor,CellBindingObserver},graph::Graph,program::Program,value};
use serde_json::{Value,json};
use std::{cell::RefCell,collections::BTreeMap,env,fs,io,rc::Rc,time::Instant};
fn err(e:impl ToString)->io::Error{io::Error::other(e.to_string())}
fn main()->Result<(),Box<dyn std::error::Error>>{
 let args:Vec<_>=env::args().skip(1).collect();let (input,output,all_slots)=match args.as_slice(){[i,o]=>(i,o,false),[i,o,flag] if flag=="--all-slots"=>(i,o,true),_=>return Err(err("PROGRAM OUTPUT [--all-slots]").into())};
 let artifact:Value=serde_json::from_slice(&fs::read(input)?)?;
 let rules=artifact["recipe"]["rules"].as_array().ok_or_else(||err("rules"))?;
 let selected:Vec<bool>=rules.iter().map(|r|all_slots || r["effects"].as_array().unwrap().iter().any(|o|o["kind"]=="compute")).collect();
 let sorts:Vec<Vec<Value>>=rules.iter().map(|r|r["slots"].as_array().unwrap().iter().map(|s|s["sort"].clone()).collect()).collect();
 let records=Rc::new(RefCell::new(BTreeMap::<usize,Vec<Value>>::new()));let captured=records.clone();
 let observer_seconds=Rc::new(RefCell::new(0.));let timer=observer_seconds.clone();
 let mut executor=Executor::new(Graph::new(Program::parse(artifact.clone()).map_err(err)?).map_err(err)?,false);
 executor.binding_observer=Some(CellBindingObserver{rules:vec![true;rules.len()],observe:Box::new(move |run,index,rid,slots|{
  let start=Instant::now();
  let values=if selected[rid]{slots.iter().map(|(i,v)|json!({"slot":i,"value":value::exported(v,&sorts[rid][*i])})).collect::<Vec<_>>()}else{vec![]};
  let mut store=captured.borrow_mut();let rows=store.entry(run).or_default();assert_eq!(rows.len(),index);
  rows.push(json!({"rule":rid,"values":values}));*timer.borrow_mut()+=start.elapsed().as_secs_f64();
 })});
 let start=Instant::now();executor.execute().map_err(err)?;let execution_seconds=start.elapsed().as_secs_f64();
 assert!(executor.snapshots.is_empty()&&executor.binding_audit.is_empty());
 let final_graph=executor.graph.export().map_err(err)?;
 let mut reference=Executor::new(Graph::new(Program::parse(artifact.clone()).map_err(err)?).map_err(err)?,false);
 let start=Instant::now();reference.execute().map_err(err)?;let reference_seconds=start.elapsed().as_secs_f64();
 assert_eq!(final_graph,reference.graph.export().map_err(err)?);
 assert_eq!(executor.steps.len(),reference.steps.len());
 for (a,b) in executor.steps.iter().zip(&reference.steps){
  assert_eq!((a.ordinal,a.ruleset.as_str(),a.changed,a.executed_bindings),(b.ordinal,b.ruleset.as_str(),b.changed,b.executed_bindings));
 }
 let runs=records.borrow().iter().map(|(ordinal,bindings)|json!({"ordinal":ordinal,"audit":{"bindings":bindings}})).collect::<Vec<_>>();
 fs::write(output,serde_json::to_vec(&json!({"schema":"eggcc-gpu-supervision-trace/v1","recipe":artifact["recipe"],"steps":executor.steps,"all_slots":all_slots,"program_sha256":artifact["sha256"],"runs":runs,
  "audited_execution_seconds":execution_seconds,"reference_execution_seconds":reference_seconds,"observer_seconds":*observer_seconds.borrow(),
  "strict_audit_reference_equal":true,"run_control_counts_equal":true,"full_snapshots":0,"final":final_graph,
  "scope":if all_slots{"full multistage CPU execution and all typed Cell inputs; no GPU takeover"}else{"live read-only Cell observer; scalar slots only; no GPU writeback"}}))?)?;Ok(())
}
