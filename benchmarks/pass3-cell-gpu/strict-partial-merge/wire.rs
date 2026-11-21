// The high bit in the original eight-byte template header announces a bitmap.
// The low 32 bits remain the source template, the other 31 bits name the Spine program.
use serde_json::{Value as J, json};
use std::cell::RefCell;
const MERGE: u64 = 1 << 63;
#[derive(Default)]
struct Wire {
    audit: bool,
    fault: u8,
    rows: Vec<J>,
}
thread_local! {static WIRE:RefCell<Wire>=RefCell::new(Wire::default());}
pub fn configure(audit: bool, fault: u8) -> crate::program::Result<()> {
    if fault > 2 {
        return Err("invalid strict wire fault".into());
    }
    WIRE.with_borrow_mut(|w| {
        *w = Wire {
            audit,
            fault,
            ..Default::default()
        }
    });
    Ok(())
}
pub(crate) fn pack(template: usize, has_merge: bool) -> [u8; 8] {
    let mut word = template as u64;
    assert_eq!(word & MERGE, 0, "Spine tag exceeded its 31-bit field");
    if has_merge {
        word |= MERGE;
    }
    WIRE.with_borrow(|w| {
        if w.fault == 1 && has_merge {
            word ^= MERGE;
        }
        if w.fault == 2 && template >> 32 != 0 {
            word ^= 1 << 62;
        }
    });
    word.to_le_bytes()
}
pub(crate) fn record(
    single: bool,
    rid: usize,
    epoch: u64,
    first: u64,
    n: usize,
    header: [u8; 8],
    tags: Option<&[u8]>,
) {
    WIRE.with_borrow_mut(|w| {
        if w.audit {
            w.rows
                .push(json!([single, rid, epoch, first, n, header, tags]));
        }
    });
}
pub(crate) fn source(h: [u8; 8]) -> usize {
    (u64::from_le_bytes(h) & 0xffff_ffff) as usize
}
pub(crate) fn spine(h: [u8; 8]) -> usize {
    ((u64::from_le_bytes(h) & !MERGE) >> 32) as usize
}
pub(crate) fn merge(h: [u8; 8]) -> bool {
    u64::from_le_bytes(h) & MERGE != 0
}
pub fn report() -> J {
    WIRE.with_borrow_mut(|w| json!(std::mem::take(&mut w.rows)))
}
