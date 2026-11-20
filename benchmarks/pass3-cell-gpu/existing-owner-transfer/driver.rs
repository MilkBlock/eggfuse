#[path = "integral_runtime.rs"]
mod replay;
use eggfuse_cell_runtime::{checksum::artifact_digest, program::Program, transfer_audit as audit};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    fs,
    sync::atomic::{AtomicUsize, Ordering::Relaxed},
};
struct Charge;
#[global_allocator]
static ALLOC: Charge = Charge;
static LIVE: AtomicUsize = AtomicUsize::new(0);
static REQUESTS: AtomicUsize = AtomicUsize::new(0);
static FREED: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
fn debit(n: usize) {
    REQUESTS.fetch_add(n, Relaxed);
    let next = LIVE.fetch_add(n, Relaxed) + n;
    PEAK.fetch_max(next, Relaxed);
}
fn credit(n: usize) {
    FREED.fetch_add(n, Relaxed);
    LIVE.fetch_sub(n, Relaxed);
}
unsafe impl GlobalAlloc for Charge {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            debit(l.size());
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        credit(l.size());
        unsafe {
            System.dealloc(p, l);
        }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            credit(l.size());
            debit(n);
        }
        q
    }
}
fn accounting(reset: bool) -> [usize; 4] {
    let live = LIVE.load(Relaxed);
    if reset {
        PEAK.store(live, Relaxed);
    }
    [
        live,
        REQUESTS.load(Relaxed),
        FREED.load(Relaxed),
        PEAK.load(Relaxed),
    ]
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().skip(1).collect();
    let p = Program::parse(serde_json::from_slice(&fs::read(&a[0])?)?)?;
    let mut e = replay::executor(p, "off", &[])?;
    let _initial_unions = audit::take_trial_unions();
    let mut domain = [0u64; 7];
    let mut counts = vec![];
    let mut events = vec![];
    let mut refs = vec![];
    let mut stages = vec![];
    let mut seed = Vec::<u32>::new();
    let mut action = false;
    let mut probe = Value::Null;
    let mut base_unions = 0u64;
    let mut post_merge_unions = 0;
    let mode = &a[1];
    let physical_mode = mode.trim_end_matches("-probe");
    loop {
        let before = e.steps.len();
        audit::set_active(true);
        audit::enable_write_audit();

        e.execute_until(Some(before + 1))?;
        if e.steps.len() == before {
            break;
        }
        let rhs = audit::take_digests();
        let writes = audit::take_write_digests();
        let spine = audit::take_resume_digests();
        let unions = audit::take_trial_unions();
        let step = e.steps.last().unwrap();
        stages.push(json!([
            step.ruleset,
            step.path,
            step.iterations,
            step.epoch,
            step.executed_bindings,
            step.changed,
            rhs,
            writes,
            spine,
            unions
        ]));
        let report = e
            .graph
            .existing_owner_boundary(physical_mode, !action, &seed, accounting)?;
        for (i, v) in report["domain"].as_array().unwrap().iter().enumerate() {
            domain[i] += v.as_u64().unwrap();
        }
        counts.push(report["domain"].clone());
        let event = &report["event"];
        if !event.is_null() {
            if event["kind"] == "seed_existing_owners" {
                seed = serde_json::from_value(event["ids"].clone())?;
            } else {
                action = true;
                seed = serde_json::from_value(event["ids"].clone())?;
                base_unions = e.graph.stats.unions;
            }
            events.push(json!({"source_run":e.steps.len(),"event":event}));
            if action && mode.ends_with("-probe") {
                let previous: Vec<(u32, usize)> =
                    serde_json::from_value(event["old_members"].clone())?;
                let pick = a
                    .get(4)
                    .map(|n| n.parse::<usize>())
                    .transpose()?
                    .unwrap_or(0);
                let effect = e.graph.force_owner_repair(&seed, &previous, pick)?;
                if effect.get("rejected_by_source").is_some()
                    || effect.get("exhausted_candidates").is_some()
                {
                    probe = json!({"effect":effect});
                    break;
                }
                probe = json!({"effect":effect,"read":e.graph.existing_owner_read(&seed)?,"graph":artifact_digest(&e.graph.export()?)});
                break;
            }
        }
        // The normal source runtime, including transfer, compaction and future repair, remains active.
        if mode.starts_with("split") && seed.is_empty() {
            // Isolated action contrast: retain source frames until the first multi-member
            // proved component can serve as two independently allocated physical owners.
        } else if a[3] == "unpooled" {
            e.graph.transfer_completed_unpooled_owners()?;
        } else {
            e.graph.transfer_completed_owners()?;
        }
        e.graph.compact_source_record_capacity();
        e.graph.compact_retired_prefixes()?;
        if action {
            post_merge_unions = e.graph.stats.unions - base_unions;
            refs.push(artifact_digest(&e.graph.existing_owner_read(&seed)?));
        }
    }
    audit::set_active(false);
    fs::write(
        &a[2],
        serde_json::to_vec(
            &json!({"mode":mode,"storage":a[3],"domain":domain,"per_run":counts,
        "events":events,"post_action_read_digests":refs,"post_action_unions":post_merge_unions,
        "probe":probe,"source_checks":stages,"graph":artifact_digest(&e.graph.export()?),"final_state":e.graph.export()?,"runs":e.steps.len()}),
        )?,
    )?;
    Ok(())
}
