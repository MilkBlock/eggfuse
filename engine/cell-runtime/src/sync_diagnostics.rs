//! Feature-gated wall-time diagnostics. Task residence includes OS descheduling;
//! neither pool residence nor the gaps around tasks are pure lock/wakeup cost.
//! No clocks, environment reads or added task fields exist in ordinary builds.
#[cfg(feature = "cell-sync-diagnostics")]
use {
    serde::{Deserialize, Serialize},
    std::time::Instant,
};

pub(crate) struct Clock {
    #[cfg(feature = "cell-sync-diagnostics")]
    start: Instant,
    #[cfg(feature = "cell-sync-diagnostics")]
    enter: Option<Instant>,
    #[cfg(feature = "cell-sync-diagnostics")]
    joined: Option<Instant>,
}
impl Clock {
    pub fn new() -> Self {
        Self {
            #[cfg(feature = "cell-sync-diagnostics")]
            start: Instant::now(),
            #[cfg(feature = "cell-sync-diagnostics")]
            enter: None,
            #[cfg(feature = "cell-sync-diagnostics")]
            joined: None,
        }
    }
    pub fn enter(&mut self) {
        #[cfg(feature = "cell-sync-diagnostics")]
        {
            self.enter = Some(Instant::now());
        }
    }
    pub fn join(&mut self) {
        #[cfg(feature = "cell-sync-diagnostics")]
        {
            self.joined = Some(Instant::now());
        }
    }
}
pub(crate) fn registry_inline() -> bool {
    #[cfg(feature = "cell-sync-diagnostics")]
    {
        static INLINE: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
        *INLINE.get_or_init(|| std::env::var("CELL_SYNC_REGISTRY_INLINE").as_deref() == Ok("1"))
    }
    #[cfg(not(feature = "cell-sync-diagnostics"))]
    {
        false
    }
}
#[cfg(feature = "cell-sync-diagnostics")]
#[derive(Clone, Copy)]
pub(crate) struct Span {
    start: Instant,
    end: Instant,
    worker: Option<usize>,
}
#[cfg(feature = "cell-sync-diagnostics")]
#[derive(Default, Clone, Debug, Serialize, Deserialize)]
pub struct Phase {
    calls: u64,
    pooled_calls: u64,
    traced_calls: u64,
    tasks: u64,
    prepare_ns: u64,
    pool_ns: u64,
    after_join_ns: u64,
    launch_ns: u64,
    task_span_ns: u64,
    return_ns: u64,
    task_elapsed_ns: u64,
    no_task_ns: u64,
    concurrency_ns: Vec<u64>,
    worker_tasks: Vec<u64>,
    worker_elapsed_ns: Vec<u64>,
}
#[cfg(feature = "cell-sync-diagnostics")]
impl Phase {
    pub(crate) fn record(&mut self, clock: Clock, spans: Option<&[Span]>, pooled: bool, workers: usize) {
        self.record_at(clock, spans, pooled, workers, Instant::now());
    }
    fn record_at(
        &mut self,
        clock: Clock,
        spans: Option<&[Span]>,
        pooled: bool,
        workers: usize,
        finish: Instant,
    ) {
        let (enter, joined) = (clock.enter.unwrap(), clock.joined.unwrap());
        let ns = |a: Instant, b: Instant| b.duration_since(a).as_nanos() as u64;
        self.calls += 1;
        self.pooled_calls += u64::from(pooled);
        self.prepare_ns += ns(clock.start, enter);
        self.pool_ns += ns(enter, joined);
        self.after_join_ns += ns(joined, finish);
        let Some(spans) = spans.filter(|s| !s.is_empty()) else {
            return;
        };
        self.traced_calls += 1;
        self.tasks += spans.len() as u64;
        self.worker_tasks.resize(workers + 1, 0);
        self.worker_elapsed_ns.resize(workers + 1, 0);
        let mut events = Vec::with_capacity(spans.len() * 2);
        for span in spans {
            assert!(enter <= span.start && span.end <= joined);
            let elapsed = ns(span.start, span.end);
            self.task_elapsed_ns += elapsed;
            let worker = span.worker.unwrap_or(workers);
            self.worker_tasks[worker] += 1;
            self.worker_elapsed_ns[worker] += elapsed;
            events.push((span.start, 1i32));
            events.push((span.end, -1));
        }
        events.sort_unstable_by(|a, b| a.0.cmp(&b.0).then_with(|| b.1.cmp(&a.1)));
        self.launch_ns += ns(enter, events[0].0);
        self.task_span_ns += ns(events[0].0, events.last().unwrap().0);
        self.return_ns += ns(events.last().unwrap().0, joined);
        let (mut previous, mut active) = (enter, 0usize);
        for (time, change) in events.into_iter().chain(std::iter::once((joined, 0))) {
            if self.concurrency_ns.len() <= active {
                self.concurrency_ns.resize(active + 1, 0);
            }
            let elapsed = ns(previous, time);
            self.concurrency_ns[active] += elapsed;
            if active == 0 {
                self.no_task_ns += elapsed;
            }
            active = (active as i32 + change) as usize;
            previous = time;
        }
        assert_eq!(active, 0);
    }
}
#[cfg(feature = "cell-sync-diagnostics")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Report {
    pub inline_registry: bool,
    pub classify: Phase,
    pub install: Phase,
    #[serde(default)]
    pub registration:Phase,
    pub constructors: Phase,
    pub queries: Phase,
    pub source_batches: u64,
    pub source_adoption_ns: u64,
    pub registered_source_batches: u64,
    pub registered_source_adoption_ns: u64,
}
#[cfg(feature = "cell-sync-diagnostics")]
impl Default for Report {
    fn default() -> Self {
        Self {
            inline_registry: registry_inline(),
            classify: Phase::default(),
            install: Phase::default(),
            registration:Phase::default(),
            constructors: Phase::default(),
            queries: Phase::default(),
            source_batches: 0,
            source_adoption_ns: 0,
            registered_source_batches: 0,
            registered_source_adoption_ns: 0,
        }
    }
}
#[cfg(all(test, feature = "cell-sync-diagnostics"))]
mod tests {
    use super::*;
    #[test]
    fn overlapped_tasks_partition_wall_time_without_counting_work_as_wait() {
        let start = Instant::now();
        let at = |n| start + std::time::Duration::from_nanos(n);
        let clock = Clock {
            start,
            enter: Some(at(2)),
            joined: Some(at(10)),
        };
        let spans = [
            Span {
                start: at(3),
                end: at(7),
                worker: Some(0),
            },
            Span {
                start: at(5),
                end: at(9),
                worker: Some(1),
            },
        ];
        let mut phase = Phase::default();
        phase.record_at(clock, Some(&spans), true, 4, at(12));
        assert_eq!(
            (phase.prepare_ns, phase.pool_ns, phase.after_join_ns),
            (2, 8, 2)
        );
        assert_eq!(
            (phase.launch_ns, phase.task_span_ns, phase.return_ns),
            (1, 6, 1)
        );
        assert_eq!(phase.concurrency_ns, vec![2, 4, 2]);
        assert_eq!(phase.task_elapsed_ns, 8);
        assert_eq!(phase.no_task_ns, 2);
        assert_eq!(phase.worker_tasks, vec![1, 1, 0, 0, 0]);
    }
    #[test]
    fn zero_duration_and_adjacent_tasks_do_not_underflow_active_count() {
        let start = Instant::now();
        let at = |n| start + std::time::Duration::from_nanos(n);
        let clock = Clock {
            start,
            enter: Some(at(0)),
            joined: Some(at(5)),
        };
        let spans = [
            Span {
                start: at(1),
                end: at(1),
                worker: None,
            },
            Span {
                start: at(1),
                end: at(3),
                worker: Some(0),
            },
            Span {
                start: at(3),
                end: at(4),
                worker: Some(0),
            },
        ];
        let mut phase = Phase::default();
        phase.record_at(clock, Some(&spans), false, 1, at(5));
        assert_eq!(phase.concurrency_ns, vec![2, 3, 0]);
        assert_eq!(phase.task_elapsed_ns, 3);
        assert_eq!(phase.worker_tasks, vec![2, 1]);
    }
}
