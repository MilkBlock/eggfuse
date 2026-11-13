#![cfg(all(feature="iterative-bake",feature="sparse-cells"))]
use eggfuse_cell_runtime::{program::{Program,Call},iterative::Catalog,executor::Executor,graph::Graph};
#[path="support/cell_entry.rs"]
#[allow(dead_code)]
mod fixture;

fn install(p:&Program)->Program {
    let rules=p.artifact["recipe"]["rules"].as_array().unwrap();
    let id=|name|rules.iter().position(|r|r["metadata"]["name"]==name).unwrap();
    let (producer,consumer)=(id("producer"),id("consumer"));
    let output=rules[producer]["effects"].as_array().unwrap().iter().position(|e|e["call"]["table"]=="B").unwrap();
    let pivot=p.rules[consumer].query.iter().position(|a|matches!(a.call,Call::Table(t) if p.tables[t].name=="B")).unwrap();
    let mut raw=p.artifact.clone();let mut plan=raw["iterative_bake"].clone();
    Catalog::emit_matched_routes(p,&mut plan,&[(producer,output,consumer,pivot)]).unwrap();
    assert_eq!(plan["matched_route_selection"]["routes"].as_array().unwrap().len(),1);
    raw["iterative_bake"]=plan;Program::parse(raw).unwrap()
}
fn execute(p:Program,owned:bool,workers:bool)->Executor {
    let mut e=Executor::new(Graph::new(p).unwrap(),true);
    if owned {e.use_entry_publications().unwrap();}
    if workers {e.use_query_workers(2,1).unwrap();}
    e.execute().unwrap();e
}
#[test]
fn residual_matches_inherit_results_after_guards_and_late_inputs() {
    let convert=|s:String|s.replace("((B x n) (= a (A x)) (Edge x y)) ((Out a y))",
        "((B x n) (Edge x y)) ((Out (A x) y))");
    let guarded=convert(fixture::SOURCE.into())
        .replace("(ruleset make)","(function Limit () i64 :merge (min old new))\n(set (Limit) 12)\n(ruleset make)")
        .replace("(Edge x y))", "(Edge x y) (< y (Limit)))")
        .replace(" (Out (A (N 1)) 12)", "");
    for source in [convert(fixture::SOURCE.into()),convert(fixture::replaced_source()),guarded] {
        let p=fixture::program(&source);
        let fast=install(&p);
        let base=execute(p,false,false);
        for (owned,workers) in [(false,false),(true,false),(true,true)] {
            let e=execute(fast.clone(),owned,workers);
            assert_eq!(base.snapshots,e.snapshots);
            assert_eq!(base.binding_audit,e.binding_audit);
            assert!(e.graph.stats.handoff_lets>base.graph.stats.handoff_lets,"matched route must remove actual constructor lookup work");
            assert!(e.report()["stage_spine"]["stats"]["matched_entry_resumptions"].as_u64().unwrap()>0);
        }
    }
}

#[test]
fn matched_routes_reject_a_nonmatching_publication_without_changing_the_plan() {
    let source=fixture::SOURCE.replace("((B x n) (= a (A x)) (Edge x y)) ((Out a y))",
        "((B x n) (Edge x y)) ((Out (A x) y))");
    let p=fixture::program(&source);
    let rules=p.artifact["recipe"]["rules"].as_array().unwrap();
    let producer=rules.iter().position(|r|r["metadata"]["name"]=="producer").unwrap();
    let consumer=rules.iter().position(|r|r["metadata"]["name"]=="consumer").unwrap();
    let wrong_output=rules[producer]["effects"].as_array().unwrap().iter().position(|e|e["call"]["table"]=="A").unwrap();
    let pivot=p.rules[consumer].query.iter().position(|a|matches!(a.call,Call::Table(t) if p.tables[t].name=="B")).unwrap();
    let mut plan=p.artifact["iterative_bake"].clone();let before=plan.clone();
    assert!(Catalog::emit_matched_routes(&p,&mut plan,&[(producer,wrong_output,consumer,pivot)]).is_err());
    assert_eq!(plan,before);
}

#[test]
fn selected_paths_relower_without_expansion_and_reject_removed_publications() {
    let p=fixture::program(fixture::SOURCE);
    let before=p.artifact["iterative_bake"].clone();
    let policy=before["rhs_handoffs"].clone();
    let mut plan=before.clone();
    Catalog::relower_selected(&p,&mut plan,&policy).unwrap();
    assert_eq!(plan["joins"],before["joins"]);
    assert_eq!(plan["rhs_handoffs"],before["rhs_handoffs"]);
    plan["joins"][0]["output"]=serde_json::json!(usize::MAX);
    let invalid=plan.clone();
    assert!(Catalog::relower_selected(&p,&mut plan,&policy).is_err());
    assert_eq!(plan,invalid);
}
