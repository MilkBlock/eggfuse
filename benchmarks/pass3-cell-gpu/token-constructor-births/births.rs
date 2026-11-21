use serde_json::{Value as J, json};
use std::{
    cell::RefCell,
    collections::{HashMap, HashSet},
};

#[derive(Default)]
struct Ledger {
    executing: bool,
    // Serial and Run of the original neural producer of this Spine context.
    roots: HashMap<u64, (u64, u64)>,
    active: Option<(u64, u64, bool)>,
    nested: u32,
    seen: HashSet<u64>,
    rows: Vec<[u64; 8]>,
    coalesced: Vec<[u64; 2]>,
    live_steps: u64,
    cross_live_steps: u64,
}

thread_local! {static LEDGER:RefCell<Option<Ledger>>=const{RefCell::new(None)};}

pub fn reset(enabled: bool) {
    LEDGER.with_borrow_mut(|s| *s = enabled.then(Ledger::default));
}
pub fn execution() {
    LEDGER.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.executing = true;
        }
    });
}

pub(crate) fn begin(epoch: u64, serial: Option<u64>, spine: Option<(u64, bool)>) {
    LEDGER.with_borrow_mut(|s| {
        if let Some(s) = s {
            assert!(s.active.is_none());
            let token = serial.unwrap_or(0);
            let (lineage, cross) = match spine {
                Some((id, true)) => {
                    s.live_steps += 1;
                    let (root, born) = s.roots[&id];
                    let later = born != epoch;
                    s.cross_live_steps += u64::from(later);
                    (root, later)
                }
                Some((id, false)) => {
                    assert!(s.roots.insert(id, (token, epoch)).is_none());
                    (token, false)
                }
                None => (token, false),
            };
            s.active = Some((token, lineage, cross));
        }
    })
}
pub(crate) fn end() {
    LEDGER.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.active = None;
        }
    });
}
pub(crate) fn dynamic<T>(f: impl FnOnce() -> T) -> T {
    LEDGER.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.nested += 1;
        }
    });
    let v = f();
    LEDGER.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.nested -= 1;
        }
    });
    v
}
pub(crate) fn first(epoch: u64, id: u64, table: usize, constructor: bool) {
    LEDGER.with_borrow_mut(|s| {
        if let Some(s) = s {
            assert!(
                s.seen.insert(id),
                "a physical fact identity was activated twice"
            );
            let (token, root, cross) = s.active.unwrap_or_default();
            s.rows.push([
                id,
                table as u64,
                epoch,
                u64::from(constructor),
                token,
                root,
                u64::from(cross),
                u64::from(s.executing) | (u64::from(s.nested > 0) << 1),
            ]);
        }
    })
}
pub(crate) fn coalesced(loser: u64, keeper: u64) {
    LEDGER.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.coalesced.push([loser, keeper]);
        }
    });
}

pub fn report(graph: &crate::graph::Graph) -> crate::program::Result<J> {
    let Some(a) = LEDGER.with_borrow_mut(Option::take) else {
        return Ok(J::Null);
    };
    let mut endpoint = Vec::new();
    for (t, table) in graph.program.tables.iter().enumerate() {
        if !table.constructor {
            continue;
        }
        for w in graph.witnesses(t) {
            let crate::graph::Dependency::Fact(f) = w else {
                return Err("constructor exported as function row".into());
            };
            let row = graph.row(w)?.ok_or("export witness lacks source row")?;
            assert_eq!(row.table, t);
            endpoint.push([
                (u64::from(f.cell) << 32) | u64::from(f.op),
                t as u64,
                u64::from(row.hidden),
            ]);
        }
    }
    let expected = graph.stats.logical_facts_created;
    assert_eq!(expected, a.rows.len() as u64);
    Ok(
        json!({"rows":a.rows,"all_activations":expected,"endpoint":endpoint,"coalesced":a.coalesced,
              "spine_live_steps":a.live_steps,"cross_run_steps":a.cross_live_steps}),
    )
}
