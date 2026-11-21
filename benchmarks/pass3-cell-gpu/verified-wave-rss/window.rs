// One shared page, written by the target. The OS sampler lives in the parent process.
use std::{
    cell::Cell,
    fs::OpenOptions,
    io,
    os::fd::AsRawFd,
    path::Path,
    sync::atomic::{AtomicU64, Ordering},
};
unsafe extern "C" {
    fn mmap(
        addr: *mut std::ffi::c_void,
        len: usize,
        prot: i32,
        flags: i32,
        fd: i32,
        offset: i64,
    ) -> *mut std::ffi::c_void;
    fn munmap(addr: *mut std::ffi::c_void, len: usize) -> i32;
    fn clock_gettime_nsec_np(clock: i32) -> u64;
}
#[link(name = "proc")]
unsafe extern "C" {
    fn proc_pidinfo(pid: i32, flavor: i32, arg: u64, buf: *mut std::ffi::c_void, bytes: i32)
    -> i32;
}
thread_local! {static PAGE:Cell<*mut AtomicU64>=const{Cell::new(std::ptr::null_mut())};}
fn now() -> u64 {
    unsafe { clock_gettime_nsec_np(8) }
} // CLOCK_UPTIME_RAW
fn rss() -> u64 {
    let mut data = [0u64; 12]; // sizeof(proc_taskinfo) = 96; resident_size is word 1.
    let bytes = unsafe {
        proc_pidinfo(
            std::process::id() as i32,
            4,
            0,
            data.as_mut_ptr().cast(),
            96,
        )
    };
    assert_eq!(bytes, 96, "proc_pidinfo(PROC_PIDTASKINFO)");
    data[1]
}
#[inline]
fn put(i: usize, n: u64) {
    PAGE.with(|p| {
        let base = p.get();
        if !base.is_null() {
            unsafe { (*base.add(i)).store(n, Ordering::Release) }
        }
    });
}
pub struct Window(*mut AtomicU64);
impl Window {
    pub fn open(path: &Path) -> io::Result<Self> {
        let file = OpenOptions::new().read(true).write(true).open(path)?;
        if file.metadata()?.len() < 4096 {
            return Err(io::Error::from(io::ErrorKind::InvalidInput));
        }
        let ptr = unsafe { mmap(std::ptr::null_mut(), 4096, 3, 1, file.as_raw_fd(), 0) };
        if ptr as isize == -1 {
            return Err(io::Error::last_os_error());
        }
        PAGE.with(|p| {
            assert!(p.get().is_null());
            p.set(ptr.cast())
        });
        // Charge the shared mapping and one-time OS lookup before taking the baseline.
        put(7, rss());
        Ok(Self(ptr.cast()))
    }
    pub fn begin(&self) {
        put(1, rss());
        put(0, now());
    }
    pub fn end(&self) {
        let end = now();
        put(3, rss());
        put(2, end);
    }
}
impl Drop for Window {
    fn drop(&mut self) {
        PAGE.with(|p| p.set(std::ptr::null_mut()));
        unsafe {
            munmap(self.0.cast(), 4096);
        }
    }
}
pub fn granted(n: usize) {
    put(4, n as u64);
}
pub fn redeemed(n: usize) {
    put(5, n as u64);
}
pub fn expired(n: usize) {
    put(6, n as u64);
}
