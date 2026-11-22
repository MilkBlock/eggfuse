use crate::{
    graph::Graph,
    program::{Arg, Call, Result},
};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
};

#[derive(Default)]
struct Capture {
    counts: BTreeMap<(usize, usize), usize>,
    cases: Vec<Value>,
}
thread_local! {static CAPTURE:RefCell<Capture>=RefCell::default();}

pub(crate) fn observe(g: &Graph, rid: usize, run: usize, watermark: u64) -> Result<()> {
    let rule = &g.program.rules[rid];
    let [left, right] = rule.query.as_slice() else {
        return Ok(());
    };
    let (Call::Table(l), Call::Table(r)) = (&left.call, &right.call) else {
        return Ok(());
    };
    if l == r {
        return Ok(());
    }
    let mut slots = Vec::new();
    for atom in [left, right] {
        let Some(s) = atom
            .args
            .iter()
            .map(|a| if let Arg::Slot(k) = a { Some(*k) } else { None })
            .collect::<Option<Vec<_>>>()
        else {
            return Ok(());
        };
        if s.iter().collect::<BTreeSet<_>>().len() != s.len() {
            return Ok(());
        }
        slots.push(s);
    }
    let shared: Vec<_> = slots[0]
        .iter()
        .enumerate()
        .filter_map(|(i, k)| slots[1].iter().position(|v| v == k).map(|j| (i, j)))
        .collect();
    let [(i, j)] = shared.as_slice() else {
        return Ok(());
    };
    let size = g.witness_count(*l) + g.witness_count(*r);
    if size == 0 || size > 512 {
        return Ok(());
    }
    CAPTURE.with_borrow_mut(|capture| {
        let key = (rid, size.ilog2() as usize);
        let count = capture.counts.entry(key).or_default();
        if *count >= 2 {
            return Ok(());
        }
        *count += 1;
        let mut rows = vec![];
        for (role, t, c) in [(0, *l, *i), (1, *r, *j)] {
            for address in g.witnesses(t) {
                if let Some(row) = g.row(address)?
                    && !row.hidden
                {
                    rows.push(json!([role, &row.values[c], address, row.epoch]));
                }
            }
        }
        capture
            .cases
            .push(json!({"run":run,"rule":rid,"wm":watermark,"delta":rule.seminaive,"rows":rows}));
        Ok(())
    })
}
pub fn take() -> Vec<Value> {
    CAPTURE.take().cases
}
