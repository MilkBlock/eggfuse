//! Bounded diagnostic of repeated completed RHS projections. Never consulted
//! by execution, winner selection, history admission or publication.
use crate::{graph::Graph,program::{Program,Op,Call},value::Value};
use serde::Serialize;
use std::{cell::RefCell,collections::HashMap};
use crate::{graph::Dependency,cell::CompletedEffects};
#[derive(Serialize)]
struct Plan {rule:usize,slots:Vec<usize>,constructor_sites:usize,tables:Vec<usize>}
#[derive(Serialize)]
struct Event {run:usize,rule:usize,cell:u32,union_revision:u64,
    values:Option<Vec<Value>>,output_versions:Vec<u64>,facts:u64,updates:u64,union_requests:u64,constructor_requests:u64}
#[derive(Serialize)]
struct Trace {limit:usize,run:usize,dropped:usize,unsupported_completions:usize,
    plans:Vec<Option<Plan>>,events:Vec<Event>,
    boundaries:Vec<Boundary>,boundary_dropped:usize,
    #[serde(skip)] results:HashMap<(usize,Vec<Value>),(usize,usize,Option<Dependency>)>}
thread_local! {static TRACE:RefCell<Option<Trace>>=const {RefCell::new(None)};}
pub fn start(limit:usize,p:&Program) {
    let plans=p.rules.iter().enumerate().map(|(rule,r)| {
        let t=&p.templates[r.template];let mut sites=0;let mut tables=Vec::new();
        for op in t.ops.iter() {
            match op {
                Op::Copy(..)=>{},
                Op::Let(_,Call::Table(table),_) if p.tables[*table].constructor && p.tables[*table].virtual_fact=>{sites+=1;if !tables.contains(table){tables.push(*table);}},
                _=>return None,
            }
        }
        if sites==0 {return None;}
        let dead=p.executions[rule].completed_dead_slots.as_deref().unwrap_or(&[]);
        Some(Plan{rule,slots:r.inputs.iter().copied().filter(|s|dead.binary_search(s).is_err()).collect(),constructor_sites:sites,tables})
    }).collect();
    TRACE.with(|t|*t.borrow_mut()=Some(Trace{limit,run:0,dropped:0,unsupported_completions:0,plans,events:vec![],boundaries:vec![],boundary_dropped:0,results:HashMap::new()}));
}
pub fn set_run(run:usize){TRACE.with(|t|if let Some(t)=t.borrow_mut().as_mut(){t.run=run;});}
pub(crate) fn completed(g:&Graph,rule:usize,cell:u32,facts:u64,updates:u64,union_requests:u64,constructor_requests:u64) {
    TRACE.with(|t| {
        let mut t=t.borrow_mut();let Some(t)=t.as_mut() else {return;};
        let Some(plan)=&t.plans[rule] else {t.unsupported_completions+=1;return;};
        if t.events.len()>=t.limit {t.dropped+=1;return;}
        let values=plan.slots.iter().map(|&slot|g.slot(cell,slot).ok()).collect();
        let output_versions=plan.tables.iter().map(|&table|g.query_versions[table]).collect();
        t.events.push(Event{run:t.run,rule,cell,union_revision:g.stats.unions,values,output_versions,
            facts,updates,union_requests,constructor_requests});
    });
}
// This diagnostic archive owns no runtime references and never keeps a Cell alive.
// Keys deliberately are not re-canonicalized after unions: misses undercount reuse.
#[derive(Serialize)]
struct Boundary {
    run:usize,rule:usize,cell:u32,operation:usize,table:usize,
    previous_run:Option<usize>,previous_rule:Option<usize>,prior_status:&'static str,
    forwarded:bool,receipt:Option<Dependency>,facts:u64,success:bool,
    prior_receipt:Option<Dependency>,owner_links:serde_json::Value,
}
pub(crate) struct Probe { key:(usize,Vec<Value>), event:Boundary, facts:u64 }
pub(crate) fn before(g:&Graph,rule:usize,cell:u32,operation:usize,known:&crate::cell::QueryFacts)->Option<Probe> {
    TRACE.with(|t| {
        let mut t=t.borrow_mut();let t=t.as_mut()?;
        t.plans.get(rule)?.as_ref()?;
        let Op::Let(_,Call::Table(table),args)=&g.program.templates[g.program.rules[rule].template].ops[operation] else{return None};
        if t.boundaries.len()>=t.limit {t.boundary_dropped+=1;return None;}
        let key=(*table,g.arguments(cell,args).ok()?);
        let prior=t.results.get(&key);
        let mut forwarded=false;let mut prior_receipt=None;
        let status=match prior {
            None=>"unobserved",
            Some((_,_,None))=>"receipt_not_retained",
            Some((_,_,Some(old)))=>{
                let current=g.resolve_receipt(*old);forwarded=current!=*old;prior_receipt=Some(current);
                match g.live_table(current) {
                    None=>"retired",
                    Some(found) if found!=*table=>"wrong_table",
                    Some(_) if !g.receipt_visible(current,*table)=>"hidden",
                    Some(_)=>"visible",
                }
            }
        };
        Some(Probe{key,event:Boundary{run:t.run,rule,cell,operation,table:*table,
            previous_run:prior.map(|p|p.0),previous_rule:prior.map(|p|p.1),prior_status:status,
            forwarded,receipt:None,facts:0,success:false,prior_receipt,
            owner_links:prior_receipt.filter(|_|status=="visible").map_or(serde_json::Value::Null,
                |donor|g.trace_rhs_owner_links(cell,rule,donor,known))},facts:g.stats.logical_facts_created})
    })
}
pub(crate) fn after(g:&Graph,probe:Option<Probe>,effects:&impl CompletedEffects,success:bool) {
    let Some(mut probe)=probe else{return};
    TRACE.with(|t| {
        let mut t=t.borrow_mut();let Some(t)=t.as_mut() else{return};
        probe.event.facts=g.stats.logical_facts_created-probe.facts;
        probe.event.success=success;
        probe.event.receipt=effects.get(probe.event.operation);
        if success {
            t.results.insert(probe.key,(probe.event.run,probe.event.rule,probe.event.receipt));
        }
        t.boundaries.push(probe.event);
    });
}
pub fn finish()->serde_json::Value {
    TRACE.with(|t|t.borrow_mut().take().map_or(serde_json::Value::Null,|t|serde_json::json!({
        "schema":"cell-rhs-projection-trace/v1","complete_archive":t.dropped==0 && t.boundary_dropped==0,
        "scope":"completion projections and pre-boundary receipt/owner snapshots; candidates, not authorization to skip matches, publications or effects",
        "trace":t})))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounded_observation_reports_drops_and_missing_inputs() {
        let g=crate::query::test_projection_graph();
        TRACE.with(|t|*t.borrow_mut()=Some(Trace{limit:1,run:2,dropped:0,unsupported_completions:0,
            plans:vec![Some(Plan{rule:0,slots:vec![999],constructor_sites:1,tables:vec![]})],events:vec![],boundaries:vec![],boundary_dropped:0,results:HashMap::new()}));
        completed(&g,0,u32::MAX,0,0,0,1);completed(&g,0,u32::MAX,0,0,0,1);
        let result=finish();assert_eq!(result["complete_archive"],false);
        assert_eq!(result["trace"]["dropped"],1);
        assert!(result["trace"]["events"][0]["values"].is_null());
        assert!(finish().is_null());
    }
}
