use eggfuse_cell_runtime::{compiler,executor::{Executor,CellBindingObserver},graph::Graph,program::Program,value};
use std::{cell::RefCell,collections::BTreeSet,rc::Rc};

#[test]
fn observer_preserves_union_enabled_run_boundaries_and_filtering() {
 let source=r#"
(datatype Expr (N i64) (F Expr) (G Expr))
(ruleset grow)
(ruleset merge)
(ruleset finish)
(rule ((= x (N i))) ((F x)) :ruleset grow)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset merge)
(rewrite (F x) (G x) :ruleset finish)
(N 0)
(N 1)
(run-schedule (seq (run grow) (run merge) (run finish) (run grow)))
"#;
 let core=eggfuse_bake::device_frontend::core("binding-observer",source).unwrap();
 let artifact=compiler::compile(core,&BTreeSet::new()).unwrap();
 let make=||Executor::new(Graph::new(Program::parse(artifact.clone()).unwrap()).unwrap(),true);
 let mut baseline=make();baseline.execute().unwrap();
 for enabled in [true,false] {
  let calls=Rc::new(RefCell::new(Vec::new()));let captured=calls.clone();
  let roots=Rc::new(RefCell::new(Vec::new()));let root_samples=roots.clone();
  let mut observed=make();
  observed.binding_observer=Some(CellBindingObserver{rules:if enabled {vec![true;artifact["recipe"]["rules"].as_array().unwrap().len()]} else {vec![]},
   observe:Box::new(move |run,index,rule,slots,graph|{
    for (_,v) in slots.iter(){if let value::Value::Eq(id)=v{root_samples.borrow_mut().push((*id,value::root(&graph.parents,*id)));}}
    captured.borrow_mut().push((run,index,rule,slots.clone()))
   }) });
  observed.execute().unwrap();
  assert_eq!(baseline.snapshots,observed.snapshots);
  assert_eq!(baseline.binding_audit,observed.binding_audit);
  assert_eq!(baseline.graph.export().unwrap(),observed.graph.export().unwrap());
  let expected=baseline.binding_audit.iter().map(|r|r["bindings"].as_array().unwrap().len()).sum::<usize>();
  assert_eq!(calls.borrow().len(),if enabled {expected} else {0});
  if enabled {
   assert!(roots.borrow().iter().any(|(id,before)|*before!=value::root(&observed.graph.parents,*id)));
   for (run,index,rule,slots) in calls.borrow().iter() {
    let binding=&baseline.binding_audit[run-1]["bindings"][index];
    assert_eq!(binding["rule"].as_u64().unwrap() as usize,*rule);
    assert_eq!(binding["values"].as_array().unwrap().len(),slots.len());
   }
  }
 }
}
