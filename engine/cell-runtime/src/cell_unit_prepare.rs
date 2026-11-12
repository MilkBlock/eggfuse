//! Total Unit writes whose operands come exclusively from the successful Cell
//! match and its pure scalar program. Candidates stay in that same instance;
//! only the source winner may give a row an origin and publish its receipt.
use crate::{cell::{Definition, Instance}, graph::cell_births::units::Row,
    program::{Arg, Call, Op, Program}, value::Value};
use serde::Serialize;

#[derive(Clone, Debug, PartialEq, Eq)]
struct Site { operation: usize, table: usize, keys: Vec<Arg> }
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Plan { sites: Vec<Site>, required: Vec<usize> }
#[derive(Default, Debug)]
pub(crate) enum Prepared {
    #[default] Pending,
    Absent,
    Rows(Box<Vec<(usize, Row)>>),
}
impl Prepared {
    pub fn pending(&self) -> bool { matches!(self, Self::Pending) }
    pub fn take(&mut self, operation: usize) -> Option<Row> {
        let Self::Rows(rows) = self else { return None; };
        // Stored in reverse source order. An earlier operation can have been
        // supplied by a proven Cursor; discard its unused candidate here.
        while rows.last().is_some_and(|(op,_)| *op < operation) { rows.pop(); }
        rows.last().is_some_and(|(op,_)| *op == operation).then(|| rows.pop().unwrap().1)
    }
}
#[derive(Default, Serialize)]
pub(crate) struct Counts { pub instances: u64, pub rows: u64, pub bytes: u64, pub missing: u64 }
impl Counts {
    pub fn add(&mut self, other: &Self) {
        self.instances += other.instances; self.rows += other.rows;
        self.bytes += other.bytes; self.missing += other.missing;
    }
}
impl Plan {
    pub fn derive(p: &Program, rule: usize) -> Option<Self> {
        if cfg!(feature="structural-depth") || cfg!(feature="family-survey") { return None; }
        let cell = Definition::new(p, rule).ok()?;
        let execution = &p.executions[rule];
        let mut ready = cell.rule.inputs.iter().copied().collect::<std::collections::BTreeSet<_>>();
        let mut sites = Vec::new();
        let mut required = Vec::new();
        for (operation, op) in cell.template.ops.iter().enumerate() {
            if p.known_results.static_skip[rule][operation] || matches!(op, Op::Copy(..)) { continue; }
            match op {
                Op::Let(dst, Call::Primitive(..), _) if operation < execution.segments[0].end
                    || execution.input_ready.binary_search(&operation).is_ok() => { ready.insert(*dst); required.push(*dst); }
                Op::Set(table, keys, value) => {
                    let t = &p.tables[*table];
                    if t.virtual_fact || t.schema.last()?["kind"] != "Unit"
                        || !matches!(t.merge["var"].as_str(), Some("old"|"new"))
                        || cell.value(value) != Arg::Literal(Value::Int(0)) { return None; }
                    let keys: Vec<_> = keys.iter().map(|a|cell.value(a)).collect();
                    if keys.iter().any(|a|match a {
                        Arg::Slot(s) => !ready.contains(s),
                        Arg::Literal(v) => !matches!(v, Value::Int(_) | Value::Float(_) | Value::Text(_)),
                    }) { return None; }
                    sites.push(Site { operation, table: *table, keys });
                }
                _ => return None,
            }
        }
        (!sites.is_empty()).then_some(Self { sites, required })
    }
    pub fn storage_bytes(&self) -> usize {
        self.sites.capacity()*std::mem::size_of::<Site>()
            + self.required.capacity()*std::mem::size_of::<usize>()
            + self.sites.iter().map(|s|s.keys.capacity()*std::mem::size_of::<Arg>()).sum::<usize>()
    }
    pub fn prepare(&self, instance: &mut Instance, counts: &mut Counts) {
        if !instance.units.pending() { return; }
        instance.units = Prepared::Absent;
        // An unrelated failed scalar still prevents the later Set. A prepared
        // key alone is not evidence that the source prefix completed.
        if self.required.iter().any(|s|!instance.values.contains_key(s)) {
            counts.missing += 1; return;
        }
        let mut rows = Vec::with_capacity(self.sites.len());
        for site in &self.sites {
            let Some(keys) = site.keys.iter().map(|a| match a {
                Arg::Slot(s) => instance.values.get(s).cloned(), Arg::Literal(v) => Some(v.clone()),
            }).collect::<Option<Vec<_>>>() else { counts.missing += 1; continue; };
            let row = Row::prepared(site.table, keys);
            counts.bytes += (row.function.key.capacity()*std::mem::size_of::<Value>()
                + row.fields.len()*std::mem::size_of::<Value>()) as u64;
            rows.push((site.operation, row));
        }
        counts.bytes += (rows.capacity()*std::mem::size_of::<(usize, Row)>() + std::mem::size_of_val(&rows)) as u64;
        counts.instances += 1; counts.rows += rows.len() as u64;
        rows.reverse();
        if !rows.is_empty() { instance.units = Prepared::Rows(Box::new(rows)); }
    }
}
