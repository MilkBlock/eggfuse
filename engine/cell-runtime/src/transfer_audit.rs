//! Ordered RHS inputs for each Run, used by iterative Bake and the audit build.
use std::cell::Cell;
#[path = "cell_observation.rs"]
pub mod observation;
thread_local! {
    static DIGESTS: std::cell::RefCell<Vec<String>> = const { std::cell::RefCell::new(Vec::new()) };
    static ACTIVE: Cell<bool> = const { Cell::new(false) };
}
pub fn set_active(on: bool) {
    ACTIVE.set(on);
    if !on {
        WRITE_ACTIVE.set(false);
        LOGICAL_ACTIVE.set(false);
        SOURCE.set(None);
    }
}
pub(crate) fn record_run(rows: impl Iterator<Item = impl serde::Serialize>) -> Result<(), String> {
    if ACTIVE.get() {
        use sha2::Digest;
        let mut digest = sha2::Sha256::new();
        for row in rows {
            serde_json::to_writer(&mut digest, &row).map_err(|e| e.to_string())?;
        }
        DIGESTS.with_borrow_mut(|runs| runs.push(format!("{:x}", digest.finalize())));
    }
    Ok(())
}
pub fn take_digests() -> Vec<String> {
    DIGESTS.take()
}

// Keep event order including multiple improvements to the same key in one Run.
thread_local! {
    static WRITE_ACTIVE:Cell<bool>=const{Cell::new(false)};
    static ORDINAL:Cell<u64>=const{Cell::new(0)};
    static SOURCE:Cell<Option<(u64,usize)>>=const{Cell::new(None)};
    static WRITES: std::cell::RefCell<Option<(u64,sha2::Sha256)>>=const{std::cell::RefCell::new(None)};
    static RESUMES: std::cell::RefCell<Option<(u64,sha2::Sha256)>>=const{std::cell::RefCell::new(None)};
    static RESUME_RUNS: std::cell::RefCell<Vec<(u64,String)>>=const{std::cell::RefCell::new(Vec::new())};
    static WRITE_RUNS: std::cell::RefCell<Vec<(u64,String)>>=const{std::cell::RefCell::new(Vec::new())};
    static LOGICAL_ACTIVE:Cell<bool>=const{Cell::new(false)};
    static LOGICAL_WRITES: std::cell::RefCell<Option<(u64,sha2::Sha256)>>=const{std::cell::RefCell::new(None)};
    static LOGICAL_RUNS: std::cell::RefCell<Vec<(u64,String)>>=const{std::cell::RefCell::new(Vec::new())};
}
pub fn enable_write_audit() {
    WRITE_ACTIVE.set(true);
}
/// Separately audit ordered effects when an implementation changes only the
/// internal Function witness addresses. The strict index-bearing audit stays
/// available; this digest still includes source ordinal, rule, key and values.
pub fn enable_logical_write_audit() {
    enable_write_audit();LOGICAL_ACTIVE.set(true);
}
pub(crate) fn rhs(rid: usize) {
    if WRITE_ACTIVE.get() {
        let n = ORDINAL.get();
        SOURCE.set(Some((n, rid)));
        ORDINAL.set(n + 1);
    }
}
// Source ordinals belong to the executing Cell, not whichever Cell the
// coordinator most recently admitted. The global admission counter stays put.
pub(crate) fn suspend_source() -> Option<(u64, usize)> { SOURCE.take() }
pub(crate) fn restore_source(source: Option<(u64, usize)>) { SOURCE.set(source); }
pub(crate) fn repaired() {
    SOURCE.set(None);
}
pub(crate) fn begin_writes() {
    if WRITE_ACTIVE.get() {
        ORDINAL.set(0);
        SOURCE.set(None);
        use sha2::Digest;
        RESUMES.replace(Some((0, sha2::Sha256::new())));
        WRITES.replace(Some((0, sha2::Sha256::new())));
        LOGICAL_WRITES.replace(LOGICAL_ACTIVE.get().then(||(0,sha2::Sha256::new())));
    }
}
pub(crate) fn effective(
    epoch: u64,
    table: usize,
    index: usize,
    key: &[crate::value::Value],
    old: Option<&crate::value::Value>,
    new: &crate::value::Value,
) -> Result<(), String> {
    logical_write(epoch,table,key,old,new)?;
    observation::write(epoch, SOURCE.get(), table, index, key, old, new);
    WRITES.with_borrow_mut(|state| -> Result<(),String> {
        if let Some((count, hash)) = state {
            serde_json::to_writer(hash, &(epoch, SOURCE.get(), table, index, key, old, new))
                .map_err(|e| e.to_string())?;
            *count += 1;
        }
        Ok(())
    })?;
    Ok(())
}
/// Storage-independent effective function/Unit-membership writes. Physical
/// function indices cannot survive migration to Cell FactRef identities.
pub(crate) fn logical_write(epoch:u64,table:usize,key:&[crate::value::Value],
    old:Option<&crate::value::Value>,new:&crate::value::Value)->Result<(),String> {
    LOGICAL_WRITES.with_borrow_mut(|state| {
        if let Some((count,hash))=state {
            serde_json::to_writer(hash,&(epoch,SOURCE.get(),table,key,old,new)).map_err(|e|e.to_string())?;
            *count+=1;
        }
        Ok(())
    })
}

pub(crate) fn end_writes() {
    use sha2::Digest;
    if let Some((n, h)) = RESUMES.take() {
        RESUME_RUNS.with_borrow_mut(|runs| runs.push((n, format!("{:x}", h.finalize()))));
    }
    if let Some((n,h))=LOGICAL_WRITES.take() {
        LOGICAL_RUNS.with_borrow_mut(|runs|runs.push((n,format!("{:x}",h.finalize()))));
    }
    if let Some((n, h)) = WRITES.take() {
        WRITE_RUNS.with_borrow_mut(|rs| rs.push((n, format!("{:x}", h.finalize()))));
    }
}
pub fn take_write_digests() -> Vec<(u64, String)> {
    WRITE_RUNS.take()
}
pub fn take_logical_write_digests() -> Vec<(u64,String)> {LOGICAL_RUNS.take()}

#[cfg(test)]
mod write_effect_tests {
    use super::*;
    use crate::value::Value;
    #[test]
    fn logical_effect_audit_preserves_strict_addresses_and_detects_reordering() {
        let record=|ids:[usize;2],reverse:bool| {
            set_active(true);enable_logical_write_audit();begin_writes();
            for n in if reverse {[1,0]}else{[0,1]} {
                rhs(7);effective(1,2,ids[n],&[Value::Int(n as i64)],None,&Value::Int(0)).unwrap();
            }
            end_writes();set_active(false);
            let result=(take_write_digests(),take_logical_write_digests());take_resume_digests();result
        };
        let a=record([0,1],false);let b=record([3,9],false);let c=record([3,9],true);
        assert_ne!(a.0,b.0,"strict witness diagnostic remains strict");
        assert_eq!(a.1,b.1,"internal address renaming preserves ordered effects");
        assert_ne!(b.1,c.1,"same final writes in a different source order must fail");
    }
}

pub(crate) fn resume(root: u64, producer: usize, consumer: usize, depth: u32) {
    use sha2::Digest;
    RESUMES.with_borrow_mut(|state| {
        if let Some((n, h)) = state {
            for word in [
                ORDINAL.get(),
                root,
                producer as u64,
                consumer as u64,
                u64::from(depth),
            ] {
                h.update(word.to_le_bytes());
            }
            *n += 1;
        }
    });
}
pub fn take_resume_digests() -> Vec<(u64, String)> {
    RESUME_RUNS.take()
}
