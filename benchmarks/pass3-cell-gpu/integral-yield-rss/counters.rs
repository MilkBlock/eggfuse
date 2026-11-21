// Local run numbering follows the existing source Run boundary on this single-threaded native path.
// Only detailed audit requests retain the per-Run array; sampled processes publish one fixed page.
#[derive(Default)]
struct RunCounts {
    enabled: bool,
    collect: bool,
    n: u64,
    hash: u64,
    rows: Vec<[u64; 4]>,
}
thread_local! {static RUNS:std::cell::RefCell<RunCounts>=Default::default();}
pub fn configure(mode: bool, collect: bool) {
    RUNS.with_borrow_mut(|s| {
        *s = RunCounts {
            enabled: mode || collect,
            collect,
            hash: 0xcbf29ce484222325,
            ..Default::default()
        }
    });
}
pub(crate) fn complete_run() {
    RUNS.with_borrow_mut(|s| {
        if !s.enabled {
            return;
        }
        s.n += 1;
        let [wire, single, multi] = crate::joint_root::external_wire_counters();
        let confirmed = crate::integral_packets::confirmed_total();
        let values = [wire, confirmed, single, multi];
        for v in values {
            s.hash = (s.hash ^ v).wrapping_mul(1099511628211);
        }
        crate::rss_window::publish_run(s.n, values);
        if s.collect {
            s.rows.push(values);
        }
    });
}
pub fn report() -> serde_json::Value {
    RUNS.with_borrow_mut(|s|serde_json::json!({"completed":s.n,"digest":s.hash.to_string(),"rows":std::mem::take(&mut s.rows)}))
}
