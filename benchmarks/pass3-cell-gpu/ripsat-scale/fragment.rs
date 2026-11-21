//! Issued page variants carry a checked, target-local constructor program.
use crate::{
    graph::Graph,
    program::{Arg, Call, Op, Result},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    cell::{Cell, RefCell},
    collections::BTreeMap,
    rc::Rc,
};

const VARIANT: usize = 1 << 31;

#[derive(Deserialize)]
struct Selection {
    rule: usize,
    root: usize,
    features: [f32; 7],
    variant: usize,
    shape: String,
    instructions: Vec<(usize, String)>,
}

pub(crate) struct Instruction {
    pub dst: usize,
    pub table: usize,
    pub args: Vec<Arg>,
}

pub(crate) struct Block {
    shape: String,
    variant: usize,
    template: usize,
    pub ops: BTreeMap<usize, Instruction>,
    issued: Cell<u64>,
    accepted: Cell<u64>,
    executed: Cell<u64>,
    completed: Cell<u64>,
    current_count: Cell<usize>,
    length: usize,
    serial: Cell<u64>,
    writes: Option<RefCell<Vec<(u64, usize)>>>,
}
impl Block {
    pub fn applied(&self, op: usize) {
        self.executed.set(self.executed.get() + 1);
        let count = self.current_count.get() + 1;
        self.current_count.set(count);
        if count == self.length {
            self.completed.set(self.completed.get() + 1);
        }
        if let Some(rows) = &self.writes {
            rows.borrow_mut().push((self.serial.get(), op));
        }
    }
}
#[derive(Default)]
struct State {
    by_rule: Vec<Option<Rc<Block>>>,
    active: Option<Rc<Block>>,
}
thread_local! {static STATE: RefCell<State> = RefCell::new(State::default());}

pub fn configure(raw: &Value, g: &Graph, digest: &str, audit: bool) -> Result<()> {
    let mut state = State::default();
    if !raw.is_null() {
        if raw["target_sha256"].as_str() != Some(digest) {
            return Err("foreign RHS fragment target".into());
        }
        let candidates: Vec<Selection> =
            serde_json::from_value(raw["candidates"].clone()).map_err(|e| e.to_string())?;
        let weights: [f32; 7] =
            serde_json::from_value(raw["weights"].clone()).map_err(|e| e.to_string())?;
        let mut best: BTreeMap<usize, (f32, Selection)> = BTreeMap::new();
        for action in candidates {
            let score = match raw["mode"].as_str() {
                Some("ridge") => action
                    .features
                    .iter()
                    .zip(weights)
                    .map(|(x, w)| x * w)
                    .sum(),
                Some("size") => action.instructions.len() as f32,
                _ => return Err("unknown fragment policy".into()),
            };
            if !score.is_finite() {
                return Err("invalid fragment score".into());
            }
            let replace = best.get(&action.rule).is_none_or(|(old, prev)| {
                score > *old
                    || (score == *old && (action.variant, action.root) < (prev.variant, prev.root))
            });
            if replace {
                best.insert(action.rule, (score, action));
            }
        }
        state.by_rule.resize(g.program.rules.len(), None);
        for (_, s) in best.into_values() {
            let rid = s.rule;
            let rule = g
                .program
                .rules
                .get(rid)
                .ok_or("invalid RHS fragment rule")?;
            let src = &g.program.templates[rule.template].ops;
            if state.by_rule[rid].is_some()
                || s.variant >= VARIANT
                || rule.template >= VARIANT
                || s.instructions.len() < 2
            {
                return Err("invalid RHS fragment selection".into());
            }
            let mut ops = BTreeMap::new();
            let length = s.instructions.len();
            for (index, name) in s.instructions {
                let Some(Op::Let(dst, Call::Table(t), args)) = src.get(index) else {
                    return Err("fragment requires a table Let".into());
                };
                let table = &g.program.tables[*t];
                if !table.constructor || table.name != name {
                    return Err("fragment constructor mismatch".into());
                }
                if table.virtual_fact
                    && ops
                        .insert(
                            index,
                            Instruction {
                                dst: *dst,
                                table: *t,
                                args: args.clone(),
                            },
                        )
                        .is_some()
                {
                    return Err("duplicate fragment instruction".into());
                }
            }
            state.by_rule[rid] = Some(Rc::new(Block {
                variant: VARIANT | s.variant,
                template: rule.template,
                shape: s.shape,
                ops,
                length,
                current_count: Cell::new(0),
                completed: Cell::new(0),
                serial: Cell::new(0),
                writes: audit.then(RefCell::default),
                issued: Cell::new(0),
                accepted: Cell::new(0),
                executed: Cell::new(0),
            }));
        }
    }
    STATE.with(|s| s.replace(state));
    Ok(())
}
pub(crate) fn issue(rid: usize, word: usize, count: usize) -> usize {
    STATE.with_borrow(|s| {
        if let Some(Some(b)) = s.by_rule.get(rid) {
            if word & 0xffff_ffff == b.template {
                b.issued.set(b.issued.get() + count as u64);
                return (word & !0xffff_ffffusize) | b.variant;
            }
        }
        word
    })
}
pub(crate) fn source(rid: usize, word: usize) -> Option<usize> {
    if word & VARIANT == 0 {
        return Some(word);
    }
    STATE.with_borrow(|s| {
        let b = s.by_rule.get(rid)?.as_ref()?;
        (word == b.variant).then_some(b.template)
    })
}
pub(crate) fn activate(rid: usize, word: usize, serial: u64) {
    STATE.with_borrow_mut(|s| {
        s.active = if word & VARIANT == 0 {
            None
        } else {
            s.by_rule
                .get(rid)
                .and_then(|v| v.clone())
                .filter(|b| b.variant == word)
        };
        if let Some(b) = &s.active {
            b.accepted.set(b.accepted.get() + 1);
            b.current_count.set(0);
            b.serial.set(serial);
        }
    })
}
pub(crate) fn current() -> Option<Rc<Block>> {
    STATE.with_borrow(|s| s.active.clone())
}
pub fn report() -> Value {
    STATE.with_borrow(|s| {
        Value::Array(
            s.by_rule
                .iter()
                .enumerate()
                .filter_map(|(rid, b)| {
                    let b = b.as_ref()?;
                    Some(json!([
                        rid,
                        b.shape,
                        b.issued.get(),
                        b.accepted.get(),
                        b.executed.get(),
                        b.completed.get()
                    ]))
                })
                .collect(),
        )
    })
}

pub fn writes() -> Value {
    STATE.with_borrow(|s| {
        Value::Array(
            s.by_rule
                .iter()
                .flatten()
                .filter_map(|b| {
                    b.writes
                        .as_ref()
                        .map(|rows| json!([b.shape, *rows.borrow()]))
                })
                .collect(),
        )
    })
}
