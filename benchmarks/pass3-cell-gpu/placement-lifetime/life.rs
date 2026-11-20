type Error = Box<dyn std::error::Error>;
type Outcome<T> = Result<T, Error>;
use eggfuse_cell_runtime::{executor::Executor, graph::Graph};
struct Held(Option<Executor>);
impl std::ops::Deref for Held {
    type Target = Executor;
    fn deref(&self) -> &Executor {
        self.0.as_ref().expect("active source executor")
    }
}
impl std::ops::DerefMut for Held {
    fn deref_mut(&mut self) -> &mut Executor {
        self.0.as_mut().expect("active source executor")
    }
}

// Darwin's single-threaded diagnostic child owns its private memory image.
// It releases the Graph but keeps Program, Executor, and all observer objects
// alive until after the counter read. Only fixed-size words cross the pipe.
#[cfg(target_os = "macos")]
unsafe extern "C" {
    fn pthread_is_threaded_np() -> i32;
    fn fork() -> i32;
    fn pipe(fds: *mut i32) -> i32;
    fn read(fd: i32, p: *mut u8, n: usize) -> isize;
    fn write(fd: i32, p: *const u8, n: usize) -> isize;
    fn close(fd: i32) -> i32;
    fn waitpid(pid: i32, status: *mut i32, options: i32) -> i32;
    fn _exit(status: i32) -> !;
}

fn release(g: Graph, with_program: bool, fields: &mut Vec<(&'static str, usize)>) -> [usize; 3] {
    let live = || LIVE.load(Relaxed);
    let base = live();
    let prog = g.release_storage_by_field(live, fields);
    let dynamic = base - live();
    if !with_program {
        std::mem::forget(prog);
        return [dynamic, 0, 0];
    }
    fields.clear();
    let base = live();
    prog.release_storage_by_field(live, fields);
    let library = fields
        .iter()
        .filter(|(key, _)| {
            key.starts_with("ownership.")
                || key.starts_with("composition.")
                || *key == "artifact.ownership_fragments"
        })
        .map(|(_, b)| *b)
        .sum();
    [dynamic, base - live(), library]
}

fn graph_probe(run: &mut Held, static_fields: bool) -> Outcome<[usize; 3]> {
    if unsafe { pthread_is_threaded_np() } != 0 {
        return Err("destructive fork probe requires a single-threaded process".into());
    }
    let mut fields = Vec::with_capacity(256);
    let mut fds = [-1, -1];
    if unsafe { pipe(fds.as_mut_ptr()) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let pid = unsafe { fork() };
    if pid < 0 {
        unsafe {
            close(fds[0]);
            close(fds[1]);
        }
        return Err(std::io::Error::last_os_error().into());
    }
    if pid == 0 {
        unsafe {
            close(fds[0]);
        }
        let executor = run.0.take().expect("child owns its private executor");
        let report = release(executor.graph, static_fields, &mut fields);
        // Other executor fields remain in scope until _exit, preserving all shared references.
        let len = std::mem::size_of_val(&report);
        let sent = unsafe { write(fds[1], report.as_ptr().cast::<u8>(), len) };
        unsafe { _exit(if sent == len as isize { 0 } else { 72 }) }
    }
    let mut report = [0usize; 3];
    let mut status = 0;
    unsafe {
        close(fds[1]);
    }
    let len = std::mem::size_of_val(&report);
    let count = unsafe { read(fds[0], report.as_mut_ptr().cast::<u8>(), len) };
    unsafe {
        close(fds[0]);
    }
    let child = unsafe { waitpid(pid, &mut status, 0) };
    if child != pid || status != 0 || count != len as isize {
        return Err(format!("incomplete graph probe {child} {status} {count}").into());
    }
    Ok(report)
}

fn main() -> Outcome<()> {
    let a: Vec<_> = std::env::args().skip(1).collect();
    let mode = match a[2].as_str() {
        "pooled" => 0,
        "defer" => 2,
        "defer-only" => 3,
        "multi-prefix" => 4,
        _ => return Err("unknown placement".into()),
    };
    let audit_run = a[4] == "audit";
    let stride = a[5].parse::<usize>()?;
    let spec: Value = serde_json::from_slice(&fs::read(&a[1])?)?;
    let offers = spec["offers"].as_array().ok_or("invalid offers")?;
    let policy = spec
        .get("weights")
        .cloned()
        .map(serde_json::from_value)
        .transpose()?;
    let forced = spec["forced"] == true;
    let runs = spec["runs"].as_u64().ok_or("missing horizon")? as usize;
    let mut curve = Vec::<[usize; 8]>::with_capacity(runs + 1);
    let mut stages = Vec::new();
    let base = accounting(false);
    let program = Program::parse(serde_json::from_slice(&fs::read(&a[0])?)?)?;
    let mut e = Held(Some(replay::executor(program, "off", &[])?));
    drop(audit::take_trial_unions());
    let initial = accounting(false);
    let mut counters = [[0usize; 2]; 4]; // source, placement, candidate validation, accepted move
    let mut pos = 0;
    let mut selected = 0;
    let mut saved = 0i64;
    let mut placement = [0u64; 5];
    let mut probes = 0;
    let mut probe_ns = 0u64;
    let static_start = if audit_run {
        [0; 3]
    } else {
        graph_probe(&mut e, true)?
    };
    let mut static_end = [0; 3];
    let mut before = initial;
    for index in 0..=runs {
        if index > 0 {
            if audit_run {
                audit::set_active(true);
                audit::enable_write_audit();
            }
            let start = accounting(false);
            e.execute_until(Some(index))?;
            if e.steps.len() != index {
                return Err("wrong source schedule".into());
            }
            if audit_run {
                let step = e.steps.last().unwrap();
                stages.push(json!([
                    step.ruleset,
                    step.path,
                    step.iterations,
                    step.epoch,
                    step.executed_bindings,
                    step.changed,
                    audit::take_digests(),
                    audit::take_write_digests(),
                    audit::take_resume_digests(),
                    audit::take_trial_unions()
                ]));
                audit::set_active(false);
            } else {
                drop(audit::take_trial_unions());
            }
            let end = accounting(false);
            counters[0][0] += end[1] - start[1];
            counters[0][1] += end[2] - start[2];
            if let Some(offer) = offers.get(pos)
                && offer["run"].as_u64() == Some(index as u64)
            {
                let start = accounting(false);
                let (accept, alloc, free) = e.graph.lifetime_action(
                    offer,
                    policy.as_ref(),
                    forced,
                    audit_run,
                    accounting,
                )?;
                let end = accounting(false);
                if free as i64 - alloc as i64
                    != offer["saved_bytes"].as_i64().ok_or("old effect missing")?
                {
                    return Err(format!(
                        "allocator transfer differs at Run {index}: {}",
                        free as i64 - alloc as i64
                    )
                    .into());
                }
                counters[2][0] += end[1] - start[1] - alloc;
                counters[2][1] += end[2] - start[2] - free;
                counters[3][0] += alloc;
                counters[3][1] += free;
                selected += usize::from(accept);
                saved += free as i64 - alloc as i64;
                pos += 1;
            }
            let start = accounting(false);
            e.graph.place_completed_fragments(mode, &mut placement)?;
            e.graph.compact_source_record_capacity();
            e.graph.compact_retired_prefixes()?;
            before = accounting(false);
            counters[1][0] += before[1] - start[1];
            counters[1][1] += before[2] - start[2];
        }
        if !audit_run {
            let charges = e.graph.prospective_owner_charge();
            let report = if index == 0 {
                static_start
            } else if index == runs {
                static_end = graph_probe(&mut e, true)?;
                static_end
            } else if stride > 0 && index % stride == 0 {
                let clock = std::time::Instant::now();
                let graph = graph_probe(&mut e, false)?;
                probe_ns += clock.elapsed().as_nanos() as u64;
                probes += 1;
                graph
            } else {
                [0; 3]
            };
            let [alloc, free] = counters
                .iter()
                .fold([0, 0], |v, x| [v[0] + x[0], v[1] + x[1]]);
            curve.push([
                index,
                report[0],
                before[0] - base[0],
                alloc,
                free,
                charges[0],
                charges[6],
                selected,
            ]);
        }
    }
    if pos != offers.len() {
        return Err("unconsumed physical opportunity".into());
    }
    let complete = e.steps.len();
    e.execute_until(Some(complete + 1))?;
    if e.steps.len() != complete {
        return Err("truncated original source".into());
    }
    let graph = artifact_digest(&e.graph.export()?);
    let after_export = if audit_run {
        [0; 3]
    } else {
        graph_probe(&mut e, true)?
    };
    // Independent destructive control in the parent after the final export.
    let mut fields = Vec::with_capacity(256);
    let executor = e.0.take().unwrap();
    let terminal = release(executor.graph, true, &mut fields);
    let out = json!({"curve":curve,"base":base[0],"initial":initial[0],"static_start":static_start,"static_end":static_end,"after_export":after_export,"terminal":terminal,
        "probes":probes,"probe_ns":probe_ns,"phase_bytes":counters,"runs":complete,"graph":graph,"source":stages,"placement":placement,"issued":pos,
        "selected":selected,"saved":saved,"program_fields":fields});
    fs::write(&a[3], serde_json::to_vec(&out)?)?;
    Ok(())
}
