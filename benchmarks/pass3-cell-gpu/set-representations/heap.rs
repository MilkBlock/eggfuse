//! Count all native requested heap bytes while running the normal CPU source graph.
use eggfuse_cell_runtime::{executor::Executor,graph::Graph,program::Program,set_storage};
use std::{alloc::{System,GlobalAlloc,Layout},sync::atomic::{AtomicUsize,Ordering::Relaxed}};
use serde_json::json;
static LIVE:AtomicUsize=AtomicUsize::new(0);static PEAK:AtomicUsize=AtomicUsize::new(0);static REQUEST:AtomicUsize=AtomicUsize::new(0);
struct Alloc;
fn add(n:usize){let v=LIVE.fetch_add(n,Relaxed)+n;PEAK.fetch_max(v,Relaxed);REQUEST.fetch_add(n,Relaxed);}
unsafe impl GlobalAlloc for Alloc{
    unsafe fn alloc(&self,l:Layout)->*mut u8{let ptr=unsafe{System.alloc(l)};if !ptr.is_null(){add(l.size());}ptr}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)};LIVE.fetch_sub(l.size(),Relaxed);}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{let q=unsafe{System.realloc(p,l,n)};if !q.is_null(){
        if n>=l.size(){add(n-l.size());}else{LIVE.fetch_sub(l.size()-n,Relaxed);} }q}
}
#[global_allocator]static A:Alloc=Alloc;
fn main()->Result<(),Box<dyn std::error::Error>>{
    let p=std::env::args_os().nth(1).ok_or("expected program")?;
    let source=Program::parse(serde_json::from_slice(&std::fs::read(p)?)?)?;
    let program=LIVE.load(Relaxed);let mut e=Executor::new(Graph::new(source)?,false);let prepared=LIVE.load(Relaxed);
    PEAK.store(prepared,Relaxed);let req=REQUEST.load(Relaxed);e.execute()?;
    if let Some(msg)=set_storage::fault(){return Err(msg.into());}
    let peak=PEAK.load(Relaxed);let end=LIVE.load(Relaxed);let requests=REQUEST.load(Relaxed)-req;let runs=e.steps.len();
    let counters=set_storage::report();drop(e);let before=LIVE.load(Relaxed);set_storage::release_groups();
    let after=LIVE.load(Relaxed);set_storage::release_dictionary();let final_live=LIVE.load(Relaxed);
    println!("{}",json!({"runs":runs,"program_live":program,"after_setup":prepared,"peak_heap":peak,"completion_heap":end,
        "positive_allocator_growth":requests,"subscription_registry_teardown":before-after,"member_dictionary_teardown":after-final_live,
        "set_values":counters}));Ok(())
}
