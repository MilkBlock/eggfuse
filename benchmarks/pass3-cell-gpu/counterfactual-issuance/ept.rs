// Optional audit for the ordinary, fully settled source-Run schedule.
use crate::{
    graph::{Dependency, FactRef, Graph},
    program::Result,
};
use serde_json::{Value as J, json};
use std::{cell::RefCell, collections::VecDeque};

#[derive(Default)]
struct Ledger {
    ordinal: u64,
    owner: Option<u64>,
    queue: VecDeque<((u64, u64), Option<u64>)>,
    births: Vec<(FactRef, usize, Option<u64>)>,
    events: Vec<J>,
    runs: Vec<Vec<J>>,
}
thread_local! {static E:RefCell<Option<Ledger>>=const{RefCell::new(None)};}
pub fn start(enabled: bool) {
    E.with_borrow_mut(|v| *v = enabled.then(Ledger::default));
}
pub(crate) fn rhs() {
    E.with_borrow_mut(|v| {
        if let Some(s) = v {
            s.ordinal += 1;
            s.owner = Some(s.ordinal);
        }
    });
}
pub(crate) fn end_rhs() {
    E.with_borrow_mut(|v| {
        if let Some(s) = v {
            s.owner = None;
        }
    });
}
pub(crate) fn birth(f: FactRef, t: usize) {
    E.with_borrow_mut(|v| {
        if let Some(s) = v {
            s.births.push((f, t, s.owner));
        }
    });
}
pub(crate) fn write(t: usize, i: usize) {
    E.with_borrow_mut(|v| {
        if let Some(s) = v {
            s.events.push(json!([1, s.owner, t, i]));
        }
    });
}
pub(crate) fn queue(a: u64, b: u64) {
    E.with_borrow_mut(|v| {
        if let Some(s) = v {
            s.queue.push_back(((a, b), s.owner));
        }
    });
}
pub(crate) fn union(a: u64, b: u64, hi: u64, lo: u64) -> Result<()> {
    E.with_borrow_mut(|v| {
        if let Some(s) = v {
            let (expected, owner) = s.queue.pop_front().ok_or("EPT union lacks source")?;
            if expected != (a, b) {
                return Err("EPT requires FIFO union source".into());
            }
            if hi != lo {
                s.events.push(json!([2, owner, hi, lo]));
            }
        }
        Ok(())
    })
}
pub(crate) fn hide(t: usize, w: Dependency) {
    E.with_borrow_mut(|v| {
        if let Some(s) = v {
            s.events.push(json!([3, s.owner, t, w]));
        }
    });
}
pub(crate) fn boundary(g: &Graph) -> Result<()> {
    E.with_borrow_mut(|v| {
        if let Some(s) = v {
            if s.owner.is_some() || !s.queue.is_empty() || !g.settled() {
                return Err("unsettled EPT boundary".into());
            }
            for (f, t, owner) in s.births.drain(..) {
                if g.row(Dependency::Fact(f))?
                    .is_some_and(|r| !r.hidden && r.table == t)
                {
                    s.events.push(json!([0, owner, t, f]));
                }
            }
            s.runs.push(std::mem::take(&mut s.events));
        }
        Ok(())
    })
}
pub fn finish() -> Option<Vec<Vec<J>>> {
    E.take().map(|s| s.runs)
}
