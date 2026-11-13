//! Two boundary samples around execute(), independent of storage instrumentation.
//! CPU includes the small sampling boundary; wall excludes it. No periodic sampler
//! or per-Cell clock is installed. Process CPU covers all threads, not just workers.
#[cfg(not(any(target_os = "macos", target_os = "linux")))]
compile_error!("inference-cpu currently supports macOS and Linux");

use std::{io, marker::PhantomData, rc::Rc, time::Instant};

struct Snapshot {
    user: f64,
    system: f64,
    coordinator: f64,
    voluntary: i64,
    involuntary: i64,
}

impl Snapshot {
    fn read() -> io::Result<Self> {
        let mut usage = std::mem::MaybeUninit::<libc::rusage>::uninit();
        // Both system calls initialize their output only on success.
        if unsafe { libc::getrusage(libc::RUSAGE_SELF, usage.as_mut_ptr()) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let usage = unsafe { usage.assume_init() };
        let mut clock = std::mem::MaybeUninit::<libc::timespec>::uninit();
        if unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, clock.as_mut_ptr()) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let clock = unsafe { clock.assume_init() };
        let seconds = |t: libc::timeval| t.tv_sec as f64 + t.tv_usec as f64 * 1e-6;
        Ok(Self {
            user: seconds(usage.ru_utime),
            system: seconds(usage.ru_stime),
            coordinator: clock.tv_sec as f64 + clock.tv_nsec as f64 * 1e-9,
            voluntary: usage.ru_nvcsw as i64,
            involuntary: usage.ru_nivcsw as i64,
        })
    }
}

pub struct Measurement {
    before: Snapshot,
    start: Instant,
    capture_seconds: f64,
    // Thread CPU comparisons must begin and finish on the same thread.
    _same_thread: PhantomData<Rc<()>>,
}

#[derive(serde::Serialize)]
pub struct Report {
    scope: &'static str,
    wall_seconds: f64,
    process_user_seconds: f64,
    process_system_seconds: f64,
    coordinator_cpu_seconds: f64,
    voluntary_context_switches: i64,
    involuntary_context_switches: i64,
    boundary_capture_seconds: f64,
}

impl Measurement {
    pub fn begin() -> io::Result<Self> {
        let capture = Instant::now();
        let before = Snapshot::read()?;
        let start = Instant::now();
        Ok(Self {
            before,
            start,
            capture_seconds: start.duration_since(capture).as_secs_f64(),
            _same_thread: PhantomData,
        })
    }

    pub fn finish(self) -> io::Result<Report> {
        let capture = Instant::now();
        let after = Snapshot::read()?;
        Ok(Report {
            scope: "runtime.execute only; process CPU covers all threads; coordinator off-CPU includes scheduling and blocking, not pure synchronization; CPU boundaries include sampling skew",
            wall_seconds: capture.duration_since(self.start).as_secs_f64(),
            process_user_seconds: after.user - self.before.user,
            process_system_seconds: after.system - self.before.system,
            coordinator_cpu_seconds: after.coordinator - self.before.coordinator,
            voluntary_context_switches: after.voluntary - self.before.voluntary,
            involuntary_context_switches: after.involuntary - self.before.involuntary,
            boundary_capture_seconds: self.capture_seconds + capture.elapsed().as_secs_f64(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{hint::black_box, time::Duration};

    #[test]
    fn blocked_coordinator_does_not_hide_other_threads_cpu() {
        let measured = Measurement::begin().unwrap();
        std::thread::spawn(|| {
            let start = Snapshot::read().unwrap().coordinator;
            // Use a CPU budget, not a wall budget: a preempted test still does work.
            while Snapshot::read().unwrap().coordinator - start < 0.02 {
                let mut x = black_box(1u64);
                for _ in 0..10_000 {
                    x = black_box(x.wrapping_mul(6364136223846793005).wrapping_add(1));
                }
                black_box(x);
            }
        }).join().unwrap();
        std::thread::sleep(Duration::from_millis(20));
        let report = measured.finish().unwrap();
        let process_cpu = report.process_user_seconds + report.process_system_seconds;
        assert!(process_cpu - report.coordinator_cpu_seconds > 0.01);
        assert!(report.wall_seconds - report.coordinator_cpu_seconds > 0.01);
        assert!(report.boundary_capture_seconds >= 0.0);
        assert!(report.voluntary_context_switches >= 0);
        assert!(report.involuntary_context_switches >= 0);
    }
}
