use crate::{
    graph::{Dependency, Graph},
    program::{Arg, Call, Result},
    value::Value,
};
use serde_json::{Value as J, json};
use std::{cell::RefCell, collections::BTreeMap};

struct Read {
    pivot: usize,
    table: usize,
    keys: Vec<Arg>,
    size: bool,
}
struct LocalTests {
    table: usize,
    fields: Vec<(usize, Arg)>,
    comparisons: Vec<(usize, [Arg; 2])>,
}
impl LocalTests {
    fn matches(&self, g: &Graph, row: &crate::graph::Row, tests: &[bool; 15]) -> bool {
        let get = |a: &Arg| match a {
            Arg::Slot(i) => row.values[*i].clone(),
            Arg::Literal(v) => crate::value::canon(v, &g.parents),
        };
        let order = |cmp: std::cmp::Ordering| match cmp {
            std::cmp::Ordering::Less => 0,
            std::cmp::Ordering::Equal => 1,
            std::cmp::Ordering::Greater => 2,
        };
        self.fields
            .iter()
            .all(|(i, arg)| tests[order(row.values[*i].cmp(&get(arg)))])
            && self.comparisons.iter().all(|(op, args)| {
                let (Value::Int(a), Value::Int(b)) = (get(&args[0]), get(&args[1])) else {
                    return true;
                };
                tests[op * 3 + order(a.cmp(&b))]
            })
    }
}
struct Policy {
    local: BTreeMap<(usize, usize), LocalTests>,
    actions: [bool; 8],
    tests: [bool; 15],
    predictions: Vec<(u64, bool)>,
    audit: bool,
    omitted: BTreeMap<usize, Vec<Source>>,
    audited: u64,
    reads: BTreeMap<(usize, usize), Read>,
    counts: BTreeMap<usize, [u64; 4]>,
    filter: bool,
}
thread_local! { static S:RefCell<Option<Policy>>=const {RefCell::new(None)}; }

pub fn configure(g: &Graph, config: &J, audit: bool) -> Result<()> {
    S.with_borrow_mut(|s| *s = None);
    if config.is_null() {
        return Ok(());
    }
    let actions: [bool; 8] =
        serde_json::from_value(config["actions"].clone()).map_err(|e| e.to_string())?;
    for (i, &keep) in actions.iter().enumerate() {
        if keep != (i & 4 != 0 && i & 3 != 0) {
            return Err("uncertified source presence or delta decision".into());
        }
    }
    let tests: [bool; 15] =
        serde_json::from_value(config["tests"].clone()).map_err(|e| e.to_string())?;
    for (i, &keep) in tests.iter().enumerate() {
        let k = i % 3;
        if !keep && [k == 1, k == 0, k <= 1, k == 2, k >= 1][i / 3] {
            return Err("unsafe decision for local test".into());
        }
    }
    let mut local = BTreeMap::new();
    if config["local"] == true {
        for (rid, r) in g.program.rules.iter().enumerate() {
            for (pivot, a) in r.query.iter().enumerate() {
                let Call::Table(table) = a.call else { continue };
                let project = |arg: &Arg| match arg {
                    Arg::Slot(v) => a
                        .args
                        .iter()
                        .position(|x| matches!(x,Arg::Slot(s) if v==s))
                        .map(Arg::Slot),
                    Arg::Literal(v) => Some(Arg::Literal(v.clone())),
                };
                let fields = a
                    .args
                    .iter()
                    .enumerate()
                    .filter_map(|(i, arg)| {
                        let col = project(arg)?;
                        if matches!(&col,Arg::Slot(j) if *j==i) {
                            None
                        } else {
                            Some((i, col))
                        }
                    })
                    .collect::<Vec<_>>();
                let comparisons = r
                    .query
                    .iter()
                    .filter_map(|q| {
                        let Call::Primitive(op, out) = &q.call else {
                            return None;
                        };
                        if out != "Unit" || !matches!(op.as_str(), "<" | "<=" | ">" | ">=") {
                            return None;
                        }
                        let [x, y, _] = q.args.as_slice() else {
                            return None;
                        };
                        Some((
                            ["=", "<", "<=", ">", ">="]
                                .iter()
                                .position(|&name| name == op)?,
                            [project(x)?, project(y)?],
                        ))
                    })
                    .collect::<Vec<_>>();
                if !fields.is_empty() || !comparisons.is_empty() {
                    local.insert(
                        (rid, pivot),
                        LocalTests {
                            table,
                            fields,
                            comparisons,
                        },
                    );
                }
            }
        }
    }
    let mut reads = BTreeMap::new();
    for (rid, r) in g.program.rules.iter().enumerate() {
        if !r.seminaive || r.query.len() != 2 {
            continue;
        }
        for pivot in 0..2 {
            let a = &r.query[pivot];
            let b = &r.query[1 - pivot];
            let (Call::Table(first), Call::Table(table)) = (&a.call, &b.call) else {
                continue;
            };
            if g.program.tables[*table].constructor {
                continue;
            }
            let Some((_, keys)) = b.args.split_last() else {
                continue;
            };
            let cols: Option<Vec<_>> = keys
                .iter()
                .map(|key| match key {
                    Arg::Slot(v) => a
                        .args
                        .iter()
                        .position(|p| matches!(p,Arg::Slot(s) if s==v))
                        .map(Arg::Slot),
                    Arg::Literal(v) => Some(Arg::Literal(v.clone())),
                })
                .collect();
            let Some(keys) = cols else { continue };
            let size = config["size_rule"].as_u64() == Some(rid as u64);
            if config["only_size"] == true && !size {
                continue;
            }
            reads.insert(
                (rid, pivot),
                Read {
                    pivot: *first,
                    table: *table,
                    keys,
                    size,
                },
            );
        }
    }
    S.with_borrow_mut(|s| {
        *s = Some(Policy {
            tests,
            predictions: vec![],
            audit,
            omitted: BTreeMap::new(),
            audited: 0,
            local,
            actions,
            reads,
            counts: BTreeMap::new(),
            filter: config["filter"] == true,
        })
    });
    Ok(())
}

pub(crate) fn reject(
    g: &Graph,
    rid: usize,
    pivot: Option<usize>,
    w: Option<Dependency>,
    wm: u64,
    ticket: u64,
) -> Result<bool> {
    S.with_borrow_mut(|s| {
        let (Some(s), Some(pivot), Some(w)) = (s, pivot, w) else {
            return Ok(false);
        };
        let local = s.local.get(&(rid, pivot));
        let read = s.reads.get(&(rid, pivot));
        if local.is_none() && read.is_none() {
            return Ok(false);
        }
        let Some(row) = g.row(w)? else {
            return Ok(false);
        };
        if row.hidden {
            return Ok(false);
        }
        if let Some(tests) = local
            && tests.table == row.table
            && !tests.matches(g, &row, &s.tests)
        {
            s.counts.entry(rid).or_default()[0] += 1;
            return Ok(s.filter && !s.actions[0]);
        }
        let Some(read) = read else {
            return Ok(false);
        };
        if row.table != read.pivot {
            return Ok(false);
        }
        let key: Vec<_> = read
            .keys
            .iter()
            .map(|a| match a {
                Arg::Slot(i) => row.values[*i].clone(),
                Arg::Literal(v) => crate::value::canon(v, &g.parents),
            })
            .collect();
        let suffix = g.lookup(read.table, &key)?.filter(|r| !r.hidden);
        let lane = (usize::from(suffix.is_some()) << 2)
            | (usize::from(row.epoch >= wm) << 1)
            | usize::from(suffix.as_ref().is_some_and(|r| r.epoch >= wm));
        let keep = s.actions[lane];
        let counts = s.counts.entry(rid).or_default();
        if !keep {
            counts[usize::from(suffix.is_some())] += 1;
        } else if read.size && pivot == 0 {
            let old = g.lookup(read.table, &[row.values.last().unwrap().clone()])?;
            let value = suffix.as_ref().unwrap().values.last();
            let improves = match (old.as_ref().and_then(|r| r.values.last()), value) {
                (None, Some(Value::Int(_))) => true,
                (Some(Value::Int(a)), Some(Value::Int(b))) => b < a,
                _ => return Err("size reader requires i64".into()),
            };
            if s.audit {
                s.predictions.push((ticket, improves));
            }
            counts[2 + usize::from(improves)] += 1;
        } else {
            counts[2] += 1
        }
        Ok(s.filter && !keep)
    })
}
pub fn report() -> J {
    S.with_borrow(|s| json!(s.as_ref().map(|v| &v.counts)))
}

pub fn forecasts() -> J {
    S.with_borrow(|s| json!(s.as_ref().map(|p| &p.predictions)))
}

pub(crate) type Source = (u64, Option<Dependency>, u64, bool, f32);
pub(crate) fn omitted(rid: usize, source: Source) {
    S.with_borrow_mut(|s| {
        if let Some(s) = s
            && s.audit
        {
            s.omitted.entry(rid).or_default().push(source);
        }
    });
}
pub(crate) fn audit_batch(rid: usize) -> Option<Vec<Source>> {
    S.with_borrow_mut(|s| s.as_mut()?.omitted.remove(&rid))
}
pub(crate) fn audited(n: usize) {
    S.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.audited += n as u64
        }
    });
}
pub fn audit_count() -> u64 {
    S.with_borrow(|s| s.as_ref().map_or(0, |s| s.audited))
}
