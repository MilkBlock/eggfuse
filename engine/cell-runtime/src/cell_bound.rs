//! Dense operand wiring for a read-only proof of a bound Cell's effects.
//! Source operations remain authoritative for operators, tables and literals.
//! Copy aliases share temporary addresses; no speculative fact is published.
use crate::program::{Arg, Call, Op, Program, Template};
use crate::value::Value;
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
};

#[derive(Clone, Debug, Serialize)]
pub(crate) enum BoundValue {
    Operand {
        operation: usize,
        column: usize,
    },
    Result {
        operation: usize,
        inputs: [usize; 2],
    },
}

#[derive(Clone, Debug, Default, Serialize)]
pub(crate) struct BoundRhs {
    pub writes: Vec<usize>,
    #[serde(skip)]
    pub ops: std::sync::Arc<Vec<Op>>,
    pub values: Vec<BoundValue>,
    /// Original effect positions in source order, with contiguous input wiring.
    pub effects: Vec<usize>,
    pub arguments: Vec<usize>,
    pub copies_elided: usize,
}
struct Compiler<'a> {
    template: &'a Template,
    slots: BTreeMap<usize, usize>,
    integers: BTreeMap<i64, usize>,
    plan: BoundRhs,
}
impl Compiler<'_> {
    fn kind(&self, arg: &Arg) -> Option<&str> {
        match arg {
            Arg::Slot(s) => self.template.sorts.get(*s)?["kind"].as_str(),
            Arg::Literal(Value::Int(_)) => Some("i64"),
            _ => None,
        }
    }
    fn value(&mut self, source: BoundValue) -> usize {
        let id = self.plan.values.len();
        self.plan.values.push(source);
        id
    }
    fn arg(&mut self, operation: usize, column: usize) -> Option<usize> {
        let arg = self.template.ops[operation].operand(column)?;
        if !matches!(self.kind(arg), Some("eq" | "i64")) {
            return None;
        }
        Some(match arg {
            Arg::Slot(slot) => match self.slots.get(slot) {
                Some(&id) => id,
                None => {
                    let id = self.value(BoundValue::Operand { operation, column });
                    self.slots.insert(*slot, id);
                    id
                }
            },
            Arg::Literal(Value::Int(n)) => match self.integers.get(n) {
                Some(&id) => id,
                None => {
                    let id = self.value(BoundValue::Operand { operation, column });
                    self.integers.insert(*n, id);
                    id
                }
            },
            _ => return None,
        })
    }
    fn effect(&mut self, operation: usize, width: usize) -> Option<()> {
        for column in 0..width {
            let input = self.arg(operation, column)?;
            self.plan.arguments.push(input);
        }
        self.plan.effects.push(operation);
        Some(())
    }
}
impl BoundRhs {
    pub fn derive(p: &Program, template: &Template) -> Option<Self> {
        let mut c = Compiler {
            template,
            slots: BTreeMap::new(),
            integers: BTreeMap::new(),
            plan: Self {
                ops: template.ops.clone(),
                ..Self::default()
            },
        };
        let mut writes = BTreeSet::new();
        for (operation, op) in template.ops.iter().enumerate() {
            match op {
                Op::Copy(dst, _) => {
                    let value = c.arg(operation, 0)?;
                    c.slots.insert(*dst, value);
                    c.plan.copies_elided += 1;
                }
                Op::Union(a, b) if c.kind(a) == Some("eq") && c.kind(b) == Some("eq") => {
                    c.effect(operation, 2)?;
                }
                Op::Let(dst, Call::Primitive(name, sort), args)
                    if sort == "i64"
                        && matches!(name.as_str(), "+" | "-" | "*")
                        && args.len() == 2
                        && args.iter().all(|a| c.kind(a) == Some("i64")) =>
                {
                    let inputs = [c.arg(operation, 0)?, c.arg(operation, 1)?];
                    // Even unused arithmetic can fail. It must retain the
                    // original failing RHS path instead of admitting a batch.
                    let result = c.value(BoundValue::Result { operation, inputs });
                    c.slots.insert(*dst, result);
                }
                Op::Set(table, args, value)
                    if p.tables[*table].constructor
                        && p.cell_ownership.tables[*table]
                        && args.len() <= 4
                        && c.kind(value) == Some("eq") =>
                {
                    c.effect(operation, args.len() + 1)?;
                    writes.insert(*table);
                }
                _ => return None,
            }
        }
        c.plan.writes = writes.into_iter().collect();
        Some(c.plan)
    }
}
