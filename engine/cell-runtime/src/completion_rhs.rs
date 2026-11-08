//! Shared bound-effect expressions derived from checked RHS bytecode. Copy
//! aliases share expression addresses; arithmetic produces dense temporary
//! values instead of writing RHS slots. No equivalence or constructor collision is predicted.
use super::*;
use crate::program::Template;

#[derive(Clone, Copy, Debug, Serialize)]
pub enum Arithmetic {
    Add,
    Sub,
    Mul,
}
impl Arithmetic {
    pub fn evaluate(self, a: i64, b: i64) -> Option<i64> {
        match self {
            Self::Add => a.checked_add(b),
            Self::Sub => a.checked_sub(b),
            Self::Mul => a.checked_mul(b),
        }
    }
}
#[derive(Clone, Debug, Serialize)]
pub enum Expr {
    Bound(usize),
    Integer(i64),
    Arithmetic(Arithmetic, [usize; 2]),
}
#[derive(Clone, Debug, Serialize)]
pub enum Effect {
    Union([usize; 2]),
    Set {
        table: usize,
        key: Vec<usize>,
        value: usize,
    },
}
#[derive(Clone, Debug, Default, Serialize)]
pub struct Plan {
    pub writes: Vec<usize>,
    pub values: Vec<Expr>,
    pub effects: Vec<Effect>,
    pub copies_elided: usize,
}
struct Compiler<'a> {
    template: &'a Template,
    slots: BTreeMap<usize, usize>,
    integers: BTreeMap<i64, usize>,
    plan: Plan,
}
impl Compiler<'_> {
    fn kind(&self, arg: &Arg) -> Option<&str> {
        match arg {
            Arg::Slot(s) => self.template.sorts.get(*s)?["kind"].as_str(),
            Arg::Literal(Value::Int(_)) => Some("i64"),
            _ => None,
        }
    }
    fn expr(&mut self, expr: Expr) -> usize {
        let id = self.plan.values.len();
        self.plan.values.push(expr);
        id
    }
    fn arg(&mut self, arg: &Arg) -> Option<usize> {
        if !matches!(self.kind(arg), Some("eq" | "i64")) {
            return None;
        }
        Some(match arg {
            Arg::Slot(slot) => match self.slots.get(slot) {
                Some(&id) => id,
                None => {
                    let id = self.expr(Expr::Bound(*slot));
                    self.slots.insert(*slot, id);
                    id
                }
            },
            Arg::Literal(Value::Int(n)) => match self.integers.get(n) {
                Some(&id) => id,
                None => {
                    let id = self.expr(Expr::Integer(*n));
                    self.integers.insert(*n, id);
                    id
                }
            },
            _ => return None,
        })
    }
}
impl Plan {
    pub fn derive(p: &Program, template: &Template) -> Option<Self> {
        let mut c = Compiler {
            template,
            slots: BTreeMap::new(),
            integers: BTreeMap::new(),
            plan: Self::default(),
        };
        let mut writes = BTreeSet::new();
        for op in template.ops.iter() {
            match op {
                Op::Copy(dst, arg) => {
                    let value = c.arg(arg)?;
                    c.slots.insert(*dst, value);
                    c.plan.copies_elided += 1;
                }
                Op::Union(a, b) if c.kind(a) == Some("eq") && c.kind(b) == Some("eq") => {
                    let args = [c.arg(a)?, c.arg(b)?];
                    c.plan.effects.push(Effect::Union(args));
                }
                Op::Let(dst, Call::Primitive(name, sort), args)
                    if sort == "i64"
                        && args.len() == 2
                        && args.iter().all(|a| c.kind(a) == Some("i64")) =>
                {
                    let operation = match name.as_str() {
                        "+" => Arithmetic::Add,
                        "-" => Arithmetic::Sub,
                        "*" => Arithmetic::Mul,
                        _ => return None,
                    };
                    let inputs = [c.arg(&args[0])?, c.arg(&args[1])?];
                    // Keep even unused arithmetic: overflow must retain the
                    // original failing RHS path, not silently admit a batch.
                    let result = c.expr(Expr::Arithmetic(operation, inputs));
                    c.slots.insert(*dst, result);
                }
                Op::Set(table, args, value)
                    if p.tables[*table].constructor
                        && p.cell_ownership.tables[*table]
                        && args.len() <= 4
                        && c.kind(value) == Some("eq") =>
                {
                    let key = args.iter().map(|a| c.arg(a)).collect::<Option<Vec<_>>>()?;
                    let value = c.arg(value)?;
                    c.plan.effects.push(Effect::Set {
                        table: *table,
                        key,
                        value,
                    });
                    writes.insert(*table);
                }
                _ => return None,
            }
        }
        c.plan.writes = writes.into_iter().collect();
        Some(c.plan)
    }
}
