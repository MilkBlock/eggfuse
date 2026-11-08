//! Optional allocator-request accounting. Use a separate diagnostic executable;
//! atomic counters change execution cost and are not used for timing admission.
use std::alloc::{GlobalAlloc, Layout};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
static ALLOCS: AtomicU64 = AtomicU64::new(0);
static FREES: AtomicU64 = AtomicU64::new(0);
static REALLOCS: AtomicU64 = AtomicU64::new(0);
static REQUESTED: AtomicU64 = AtomicU64::new(0);
static RELEASED: AtomicU64 = AtomicU64::new(0);
static LIVE: AtomicU64 = AtomicU64::new(0);
static PEAK: AtomicU64 = AtomicU64::new(0);
pub struct Meter;
fn allocated(size: usize) {
    REQUESTED.fetch_add(size as u64, Relaxed);
    let live = LIVE.fetch_add(size as u64, Relaxed) + size as u64;
    PEAK.fetch_max(live, Relaxed);
}
fn released(size: usize) {
    RELEASED.fetch_add(size as u64, Relaxed);
    LIVE.fetch_sub(size as u64, Relaxed);
}
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let p = unsafe { mimalloc::MiMalloc.alloc(layout) };
        if !p.is_null() {
            ALLOCS.fetch_add(1, Relaxed);
            allocated(layout.size());
        }
        p
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let p = unsafe { mimalloc::MiMalloc.alloc_zeroed(layout) };
        if !p.is_null() {
            ALLOCS.fetch_add(1, Relaxed);
            allocated(layout.size());
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { mimalloc::MiMalloc.dealloc(p, layout) };
        FREES.fetch_add(1, Relaxed);
        released(layout.size());
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let next = unsafe { mimalloc::MiMalloc.realloc(p, layout, size) };
        if !next.is_null() {
            REALLOCS.fetch_add(1, Relaxed);
            released(layout.size());
            allocated(size);
        }
        next
    }
}
pub struct Snapshot([u64; 6]);
pub fn begin() -> Snapshot {
    let s = Snapshot([
        ALLOCS.load(Relaxed),
        FREES.load(Relaxed),
        REALLOCS.load(Relaxed),
        REQUESTED.load(Relaxed),
        RELEASED.load(Relaxed),
        LIVE.load(Relaxed),
    ]);
    PEAK.store(s.0[5], Relaxed);
    s
}
pub struct Delta([u64; 8]);
pub fn end(s: Snapshot) -> Delta {
    Delta([
        ALLOCS.load(Relaxed) - s.0[0],
        FREES.load(Relaxed) - s.0[1],
        REALLOCS.load(Relaxed) - s.0[2],
        REQUESTED.load(Relaxed) - s.0[3],
        RELEASED.load(Relaxed) - s.0[4],
        s.0[5],
        LIVE.load(Relaxed),
        PEAK.load(Relaxed),
    ])
}
impl Delta {
    pub fn report(&self) -> serde_json::Value {
        let d = self.0;
        serde_json::json!({"scope":"allocator requests during execute; separate diagnostic build; excludes setup and export; requested bytes are not RSS",
            "alloc_calls":d[0],"free_calls":d[1],"realloc_calls":d[2],"requested_bytes":d[3],"released_bytes":d[4],
            "live_bytes_before":d[5],"live_bytes_after":d[6],"peak_live_requested_bytes":d[7]})
    }
}
