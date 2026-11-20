// One request runs one executor on this thread. No control state names a graph row.
use std::cell::Cell;
#[derive(Clone, Copy, Default, serde::Serialize)]
struct Counts {
    projected_marks_moved: u64,
    winning_marks_moved: u64,
    receipt_rows: u64,
    receipt_fields: u64,
    corrupt_controls: u64,
}
thread_local! {
    static POLICY: Cell<u8> = const {Cell::new(0)};
    static AUDIT: Cell<bool> = const {Cell::new(false)};
    static COUNTS: Cell<Counts> = Cell::new(Counts::default());
}
pub fn configure(bits: u64, audit: bool) -> crate::program::Result<()> {
    if bits > 7 {return Err("invalid verified binding transfer mode".into());}
    POLICY.set(bits as u8);
    AUDIT.set(audit);
    COUNTS.set(Counts::default());
    Ok(())
}
pub(crate) fn move_mark() -> bool {POLICY.get() & 1 != 0}
pub(crate) fn reuse_receipt() -> bool {POLICY.get() & 2 != 0}
pub(crate) fn run_tickets() -> bool {POLICY.get() & 4 != 0}
pub(crate) fn moved(winner: bool) {
    let mut c = COUNTS.get();
    if winner {c.winning_marks_moved += 1;} else {c.projected_marks_moved += 1;}
    COUNTS.set(c);
}
pub(crate) fn receipt(fields: usize) {
    let mut c = COUNTS.get();
    c.receipt_rows += 1;
    c.receipt_fields += fields as u64;
    COUNTS.set(c);
}
pub(crate) fn try_corruption() -> bool { AUDIT.get() && COUNTS.get().corrupt_controls == 0 }
pub(crate) fn corrupted() {
    let mut c=COUNTS.get();
    c.corrupt_controls+=1;
    COUNTS.set(c);
}
pub fn report() -> serde_json::Value {serde_json::json!(COUNTS.get())}
