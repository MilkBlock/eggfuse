//! Bounded, opt-in coordinator trace. Archived forwarding is diagnostic evidence
//! only: neither execution nor receipt resolution consults this archive.
use crate::{graph::{Dependency,Graph},cell::Site};
use serde::Serialize;
use std::cell::RefCell;
#[derive(Serialize)]
#[serde(tag="kind",rename_all="snake_case")]
enum Kind {
    Forward { from:Dependency,to:Dependency,epoch:u64 },
    Clear { epoch:u64,edges:usize },
    ParentForward { child:u32,from:Dependency,to:Dependency,source_users:usize,
        source_facts:usize,source_slots:usize,target_visible:bool,parent_cycle:bool },
    ParentScan { frames:usize,parents:usize },
    Retire { fact:Dependency,table:usize,template:Option<usize>,tracking:bool },
    Capture { rule:usize,slot:usize,witness:Dependency },
    Refresh { path:&'static str,rule:usize,slot:usize,from:Option<Dependency>,to:Dependency },
    Failure { rule:usize,site:Site,slot:usize,table:usize,original:Dependency,resolved:Dependency,
        archived_target:Dependency,hops:usize,target_table:Option<usize>,target_visible:bool },
}
#[derive(Serialize)]
struct Event {run:usize,event:Kind}
#[derive(Serialize)]
struct Trace {limit:usize,run:usize,dropped:usize,events:Vec<Event>}
thread_local! {static TRACE:RefCell<Option<Trace>>=const {RefCell::new(None)};}
pub fn start(limit:usize) {TRACE.with(|t|*t.borrow_mut()=Some(Trace{limit,run:0,dropped:0,events:Vec::new()}));}
pub fn set_run(run:usize) {TRACE.with(|t|if let Some(t)=t.borrow_mut().as_mut(){t.run=run;});}
pub(crate) fn enabled()->bool {TRACE.with(|t|t.borrow().is_some())}
fn record(event:impl FnOnce()->Kind) {
    TRACE.with(|trace|if let Some(t)=trace.borrow_mut().as_mut() {
        if t.events.len()<t.limit {t.events.push(Event{run:t.run,event:event()});}
        else {t.dropped+=1;}
    });
}
pub(crate) fn forward(from:Dependency,to:Dependency,epoch:u64){record(||Kind::Forward{from,to,epoch});}
pub(crate) fn clear(epoch:u64,edges:usize){record(||Kind::Clear{epoch,edges});}
pub(crate) fn parent_scan(frames:usize,parents:usize){record(||Kind::ParentScan{frames,parents});}
pub(crate) fn parent_forward(child:u32,from:Dependency,to:Dependency,source_users:usize,
    source_facts:usize,source_slots:usize,target_visible:bool,parent_cycle:bool) {
    record(||Kind::ParentForward{child,from,to,source_users,source_facts,source_slots,target_visible,parent_cycle});
}
pub(crate) fn retire(fact:Dependency,table:usize,template:Option<usize>,tracking:bool){record(||Kind::Retire{fact,table,template,tracking});}
pub(crate) fn capture(rule:usize,slot:usize,witness:Dependency){record(||Kind::Capture{rule,slot,witness});}
pub(crate) fn refresh(path:&'static str,rule:usize,slot:usize,from:Option<Dependency>,to:Dependency){record(||Kind::Refresh{path,rule,slot,from,to});}
pub(crate) fn failure(g:&Graph,rule:usize,site:Site,slot:usize,table:usize,original:Dependency,resolved:Dependency) {
    let Some((target,hops))=TRACE.with(|trace| {
        let trace=trace.borrow();let trace=trace.as_ref()?;
        let mut current=original;let mut hops=0;
        // No second maintained forwarding index. The rare failure observer
        // replays its bounded event archive, outside the execution decision.
        while let Some(next)=trace.events.iter().rev().find_map(|e|match e.event {
            Kind::Forward{from,to,..} if from==current=>Some(to),_=>None,
        }) {
            if next==current || hops>=trace.events.len() {break;}
            current=next;hops+=1;
        }
        Some((current,hops))
    }) else {return;};
    let target_table=g.live_table(target);
    let target_visible=g.receipt_visible(target,table);
    record(||Kind::Failure{rule,site,slot,table,original,resolved,archived_target:target,hops,target_table,target_visible});
}
pub fn finish()->serde_json::Value {
    TRACE.with(|t|t.borrow_mut().take().map_or(serde_json::Value::Null,|t|serde_json::json!({
        "schema":"cell-receipt-lifetime-trace/v1","scope":"bounded coordinator observation, never used for execution or semantic proof",
        "complete_archive":t.dropped==0,"trace":t})))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn trace_limit_reports_loss_and_finish_disables_observation() {
        start(1);set_run(9);clear(3,2);clear(4,0);
        let trace=finish();assert_eq!(trace["complete_archive"],false);
        assert_eq!(trace["trace"]["dropped"],1);assert_eq!(trace["trace"]["events"][0]["run"],9);
        assert!(!enabled());assert!(finish().is_null());
    }
}
