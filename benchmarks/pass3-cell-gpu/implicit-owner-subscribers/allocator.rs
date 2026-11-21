struct Measured;
thread_local! {static DROPPED:std::cell::Cell<Option<i64>>=const{std::cell::Cell::new(None)};}
fn account(delta: i64) {
    let _ = DROPPED.try_with(|v| {
        if let Some(n) = v.get() {
            v.set(Some(n + delta))
        }
    });
}
unsafe impl std::alloc::GlobalAlloc for Measured {
    unsafe fn alloc(&self, layout: std::alloc::Layout) -> *mut u8 {
        let p = unsafe {
            std::alloc::GlobalAlloc::alloc(&eggfuse_cell_runtime::RuntimeAllocator, layout)
        };
        if !p.is_null() {
            account(-(layout.size() as i64))
        }
        p
    }
    unsafe fn alloc_zeroed(&self, layout: std::alloc::Layout) -> *mut u8 {
        let p = unsafe {
            std::alloc::GlobalAlloc::alloc_zeroed(&eggfuse_cell_runtime::RuntimeAllocator, layout)
        };
        if !p.is_null() {
            account(-(layout.size() as i64))
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: std::alloc::Layout) {
        account(layout.size() as i64);
        unsafe {
            std::alloc::GlobalAlloc::dealloc(&eggfuse_cell_runtime::RuntimeAllocator, p, layout)
        }
    }
    unsafe fn realloc(&self, p: *mut u8, layout: std::alloc::Layout, n: usize) -> *mut u8 {
        let q = unsafe {
            std::alloc::GlobalAlloc::realloc(&eggfuse_cell_runtime::RuntimeAllocator, p, layout, n)
        };
        if !q.is_null() {
            account(layout.size() as i64 - n as i64)
        }
        q
    }
}
#[global_allocator]
static ALLOCATOR: Measured = Measured;
fn drop_bytes(f: impl FnOnce()) -> i64 {
    DROPPED.set(Some(0));
    f();
    DROPPED.replace(None).unwrap()
}
