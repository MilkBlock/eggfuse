//! Single-lane allocation high-water trace, including work between Run boundaries.
//! This measures process requested heap, not an inferred Graph-only peak or RSS.
use eggfuse_cell_runtime::{executor::Executor, graph::Graph, program::Program};
use serde_json::json;
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
use std::{error::Error, fs};

static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
struct Counted;
fn added(bytes: usize) {
    let live = LIVE.fetch_add(bytes, Relaxed) + bytes;
    PEAK.fetch_max(live, Relaxed);
}
unsafe impl GlobalAlloc for Counted {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            added(l.size());
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) };
        LIVE.fetch_sub(l.size(), Relaxed);
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            if n >= l.size() {
                added(n - l.size());
            } else {
                LIVE.fetch_sub(l.size() - n, Relaxed);
            }
        }
        q
    }
}
#[global_allocator]
static ALLOCATOR: Counted = Counted;
struct Sample {
    run: usize,
    before: usize,
    execution_peak: usize,
    before_takeover: usize,
    takeover_peak: usize,
    after: usize,
}
fn reset_peak() {
    PEAK.store(LIVE.load(Relaxed), Relaxed);
}
fn detach(exec: Executor) -> Graph {
    exec.graph
}
fn main() -> Result<(), Box<dyn Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if !(args.len()==3 || (args.len()==4 && args[3]=="--port-domains-only")) || !matches!(args[2].as_str(), "baseline" | "takeover" | "record-control" | "inherited-owners") {
        return Err("usage: runtime_storage_peak PROGRAM OUTPUT baseline|takeover|record-control|inherited-owners [--port-domains-only]".into());
    }
    let p = Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let program = p.artifact["sha256"].clone();
    // Fixed trace buffer is allocated before observation. It never grows while
    // runtime peaks are sampled; its capacity is reported separately.
    let mut samples = Vec::with_capacity(4096);
    let trace_bytes = samples.capacity() * std::mem::size_of::<Sample>();
    let source_loaded = LIVE.load(Relaxed);
    reset_peak();
    let mut e = Executor::new(Graph::new_with_local_congruence(p)?, false);
    if args[2] == "inherited-owners" {e.use_completed_parent_takeover()?;}
    if args.len()==4 {e.graph.use_port_domains_only()?;}
    let setup_peak = PEAK.load(Relaxed);
    let setup_live = LIVE.load(Relaxed);
    loop {
        let n = e.steps.len();
        if samples.len() == samples.capacity() {
            return Err("trace capacity exhausted".into());
        }
        let before = LIVE.load(Relaxed);
        reset_peak();
        e.execute_until(Some(n + 1))?;
        let execution_peak = PEAK.load(Relaxed);
        let before_takeover = LIVE.load(Relaxed);
        if e.steps.len() == n {
            break;
        }
        reset_peak();
        if args[2] == "takeover" {
            e.graph.compact_retained_capacity()?;
        }
        if args[2] == "inherited-owners" {e.graph.transfer_completed_owners()?;}
        if matches!(args[2].as_str(), "record-control" | "inherited-owners") {
            e.graph.compact_source_record_capacity();
        }
        let takeover_peak = PEAK.load(Relaxed);
        let after = LIVE.load(Relaxed);
        samples.push(Sample {
            run: n + 1,
            before,
            execution_peak,
            before_takeover,
            takeover_peak,
            after,
        });
    }
    let high_water = samples
        .iter()
        .map(|s| s.execution_peak.max(s.takeover_peak))
        .max()
        .unwrap_or(setup_live);
    let max_takeover_extra = samples
        .iter()
        .map(|s| s.takeover_peak.saturating_sub(s.before_takeover))
        .max()
        .unwrap_or(0);
    let state = e.graph.export()?;
    if args[2] == "takeover" {
        // Catch a stale runtime library reused from a different worktree.
        let census = e.graph.retained_cell_storage();
        if census.get("delegated_cell_frames").is_none() {
            return Err(
                "runtime lacks takeover census; rebuild with an isolated target directory".into(),
            );
        }
    }
    let mut result = json!({"program_sha256":program,"mode":args[2],"runs":samples.len(),
        "port_index":e.graph.stable_port_report(),
        "ownership_storage":e.graph.ownership_storage_trace(),
        "source_storage":e.graph.retained_cell_storage(),
        "completion_work":e.graph.stats,
        "maintenance":e.graph.maintenance_report(),
        "scope":"single-lane process live requested heap including Program, Graph, Executor and fixed diagnostic buffer; not Graph-exclusive peak or RSS",
        "trace_buffer_bytes":trace_bytes,"source_loaded_live_bytes":source_loaded,
        "setup_peak_bytes":setup_peak,"setup_live_bytes":setup_live,
        "execution_and_takeover_peak_bytes":high_water,"max_takeover_extra_bytes":max_takeover_extra,
        "net_growth_over_setup_bytes":high_water.saturating_sub(setup_live),
        "final_state_sha256":eggfuse_cell_runtime::checksum::artifact_digest(&state),"samples":samples.iter().map(|s|json!({"run":s.run,"before":s.before,
            "execution_peak":s.execution_peak,"before_takeover":s.before_takeover,
            "takeover_peak":s.takeover_peak,"after":s.after})).collect::<Vec<_>>()});
    // Charge the retained compiled program separately, after dropping Executor
    // caches and Graph. No other Program clone is kept alive in this lane.
    let graph = detach(e);
    let mut released = Vec::with_capacity(40);
    let before = LIVE.load(Relaxed);
    let program = graph.release_storage_by_field(|| LIVE.load(Relaxed), &mut released);
    let graph_bytes = before - LIVE.load(Relaxed);
    let mut program_fields = Vec::with_capacity(128);
    let before = LIVE.load(Relaxed);
    program.release_storage_by_field(|| LIVE.load(Relaxed), &mut program_fields);
    let program_bytes = before - LIVE.load(Relaxed);
    assert_eq!(
        program_bytes,
        program_fields.iter().map(|(_, bytes)| bytes).sum::<usize>()
    );
    let attributed= released.iter().map(|(_,bytes)|bytes).sum::<usize>();
    assert!(attributed<=graph_bytes);
    result["graph_unlisted_teardown_bytes"] = json!(graph_bytes-attributed);
    result["graph_fields"] = json!(released);
    result["program_fields"] = json!(program_fields);
    result["graph_owned_teardown_bytes"] = json!(graph_bytes);
    result["retained_program_teardown_bytes"] = json!(program_bytes);
    result["teardown_scope"] = json!(
        "single-lane Graph then retained Program requested bytes; no Executor caches; shared allocations charged to their last owner"
    );
    fs::write(&args[1], serde_json::to_vec_pretty(&result)?)?;
    println!(
        "{}",
        json!({"runs":result["runs"],"process_peak":high_water,
        "net_growth_over_setup":result["net_growth_over_setup_bytes"],"takeover_extra":max_takeover_extra})
    );
    Ok(())
}
