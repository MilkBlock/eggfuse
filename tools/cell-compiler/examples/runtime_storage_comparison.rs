//! Actual graph compaction followed by continued execution, checked each Run.
use eggfuse_cell_runtime::{
    executor::Executor, graph::Graph, program::Program, transfer_audit as audit,
};
use serde_json::{Value, json};
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
use std::{fs, time::Instant};
static LIVE: AtomicUsize = AtomicUsize::new(0);
struct Counted;
unsafe impl GlobalAlloc for Counted {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            LIVE.fetch_add(l.size(), Relaxed);
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
                LIVE.fetch_add(n - l.size(), Relaxed);
            } else {
                LIVE.fetch_sub(l.size() - n, Relaxed);
            }
        }
        q
    }
}
#[global_allocator]
static ALLOCATOR: Counted = Counted;
fn detach(exec: Executor) -> Graph {
    exec.graph
}

fn step(exec: &mut Executor, next: usize) -> Result<Value, Box<dyn std::error::Error>> {
    audit::take_digests();
    audit::take_write_digests();
    audit::take_resume_digests();
    audit::set_active(true);
    audit::enable_write_audit();
    exec.execute_until(Some(next))?;
    audit::set_active(false);
    Ok(
        json!({"rhs":audit::take_digests(),"writes":audit::take_write_digests(),"resumes":audit::take_resume_digests()}),
    )
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if !(2..=3).contains(&args.len()) {
        return Err("usage: runtime_storage_comparison PROGRAM OUTPUT [OPTIMIZED_PROGRAM]".into());
    }
    let p = Program::parse(serde_json::from_slice(&fs::read(&args[0])?)?)?;
    let program = p.artifact["sha256"].clone();
    let mut baseline = Executor::new(Graph::new_with_local_congruence(p.clone())?, false);
    let optimized = if let Some(path) = args.get(2) {
        Program::parse(serde_json::from_slice(&fs::read(path)?)?)?
    } else {
        p
    };
    let mut compact = Executor::new(Graph::new_with_local_congruence(optimized)?, false);
    let mut run_checks = Vec::new();
    let mut runs = 0;
    let mut peak_before = 0;
    let mut peak_after = 0;
    let mut compaction_seconds = 0.0;
    loop {
        let a = step(&mut baseline, runs + 1)?;
        let b = step(&mut compact, runs + 1)?;
        if baseline.steps.len() != compact.steps.len() || a != b {
            return Err("Run execution/audit mismatch".into());
        }
        if baseline.steps.len() == runs {
            break;
        }
        runs += 1;
        let start = Instant::now();
        compact.graph.compact_retained_capacity()?;
        compaction_seconds += start.elapsed().as_secs_f64();
        let graph = baseline.graph.export()?;
        if graph != compact.graph.export()? {
            return Err("compaction changed graph state".into());
        }
        run_checks.push(json!({"graph":eggfuse_cell_runtime::checksum::artifact_digest(&graph), "audit":eggfuse_cell_runtime::checksum::artifact_digest(&a)}));
        let a = baseline.graph.retained_cell_storage();
        let b = compact.graph.retained_cell_storage();
        peak_before = peak_before.max(a["counted_bytes"].as_u64().unwrap());
        peak_after = peak_after.max(b["counted_bytes"].as_u64().unwrap());
    }
    let mut result = json!({"program_sha256":program,"runs":runs,"every_run_graph_and_ordered_audits_equal":true,
        "run_checks":run_checks,"baseline":baseline.graph.retained_cell_storage(),"compacted":compact.graph.retained_cell_storage(),
        "boundary_peak_before":peak_before,"boundary_peak_after":peak_after,"compaction_seconds":compaction_seconds,
        "scope":"actual Cell runtime state takeover and capacity reclamation; boundary array peaks exclude within-Run peaks; not a speed benchmark"});
    result["instance_trace"] = serde_json::to_value(
        compact
            .graph
            .cells
            .iter()
            .map(|(&id, c)| (id, c))
            .collect::<Vec<_>>(),
    )?;
    result["ownership"] = compact.graph.ownership_report();
    result["function_trace"] = serde_json::to_value(&compact.graph.functions)?;
    result["final_state"] = compact.graph.export()?;
    // Drop executor caches before measurement. Both source Programs survive
    // both graph drops, so shared source/template data is not attributed to Graph.
    let baseline = detach(baseline);
    let compact = detach(compact);
    let mut baseline_fields = Vec::with_capacity(40);
    let mut compact_fields = Vec::with_capacity(40);
    let live = LIVE.load(Relaxed);
    let baseline_program =
        baseline.release_storage_by_field(|| LIVE.load(Relaxed), &mut baseline_fields);

    let graph_before = live - LIVE.load(Relaxed);
    let live = LIVE.load(Relaxed);
    let compact_program =
        compact.release_storage_by_field(|| LIVE.load(Relaxed), &mut compact_fields);
    let graph_after = live - LIVE.load(Relaxed);
    result["field_release_baseline"] = json!(baseline_fields);
    result["field_release_compacted"] = json!(compact_fields);
    result["graph_owned_heap_requested_before"] = json!(graph_before);
    result["graph_owned_heap_requested_after"] = json!(graph_after);
    result["heap_scope"] = json!(
        "actual System allocator bytes released by Graph drop, excluding retained Programs and already-dropped Executor caches; field attribution charges shared allocations to last owner; not RSS/allocator padding"
    );
    drop((baseline_program, compact_program));
    fs::write(&args[1], serde_json::to_vec_pretty(&result)?)?;
    println!(
        "{}",
        json!({"runs":runs,"boundary_peak_before":peak_before,"boundary_peak_after":peak_after,"compaction_seconds":compaction_seconds,"graph_heap_before":graph_before,"graph_heap_after":graph_after})
    );
    Ok(())
}
