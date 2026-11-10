//! A Unit view can deliver sealed rows directly to a family of binary joins.
//! Every rule reader is accounted for. Unsupported query shapes keep the normal plan.
use crate::{cell::{Field, Query}, program::*, value::Value};
use serde::Serialize;
use serde_json::{Value as Json, json};
use std::{
    collections::BTreeSet,
    rc::Rc,
};

/// Immutable fields exported at the repaired barrier. A projected Unit key
/// shares the producer's array until repair switches it to identity wiring.
#[cfg(feature = "view-consumers")]
#[derive(Clone)]
pub(crate) struct Tuple {
    pub witness: crate::graph::Dependency,
    pub epoch: u64,
    pub fields: crate::graph::RowFields,
    pub columns: Option<Rc<Vec<usize>>>,
}
#[cfg(feature = "view-consumers")]
impl Tuple {
    pub fn port(&self, column: usize) -> &Value {
        match &self.columns {
            Some(cols) if column == cols.len() => &Value::Int(0),
            Some(cols) => &self.fields[cols[column]],
            None => &self.fields[column],
        }
    }
    pub fn flat(row: &crate::graph::Row) -> Self {
        Self {
            witness: row.witness,
            epoch: row.epoch,
            fields: row.values.clone(),
            columns: None,
        }
    }
}

#[derive(Debug, Clone)]
pub(crate) struct Member {
    pub rule: usize,
    pub driver_atom: usize,
    pub peer_atom: usize,
    pub query: Query,
    pub inputs: crate::program::InputSlots,
}
// These adapters are used only while deriving/serializing a plan. Execution
// reads Cell instructions; no view-specific tests or output ports are retained.
fn wire_field(field: &Field) -> Json {
    match field {
        Field::Anchor(i) => json!({"Driver":i}),
        Field::Column { step: 0, column } => json!({"Peer":column}),
        Field::Literal(Value::Int(0)) => json!("Unit"),
        _ => unreachable!("certified pair operand"),
    }
}
impl Member {
    fn predicates(&self, peer_key: usize) -> Vec<(Field, Field, &'static str)> {
        let mut tests = Vec::new();
        for (column, field) in &self.query.steps[0].expansion.as_ref().unwrap().checks {
            if *column != peer_key {
                tests.push((field.clone(), Field::Column { step: 0, column: *column }, "Equal"));
            }
        }
        for step in &self.query.steps[1..] {
            let Call::Primitive(name, _) = &step.call else { unreachable!() };
            let comparison = match name.as_str() {
                "<" => "Less", ">" => "Greater", "<=" => "LessEqual", ">=" => "GreaterEqual",
                _ => unreachable!("certified i64 predicate"),
            };
            tests.push((step.key[0].clone(), step.key[1].clone(), comparison));
            if let Some(prior) = &step.check_result {
                tests.push((prior.clone(), Field::Literal(Value::Int(0)), "Equal"));
            }
        }
        tests
    }
    fn wire(&self, peer_key: usize) -> Json {
        json!({"rule":self.rule,"driver_atom":self.driver_atom,"peer_atom":self.peer_atom,
            "tests":self.predicates(peer_key).iter().map(|(a,b,c)|
                json!({"left":wire_field(a),"right":wire_field(b),"comparison":c})).collect::<Vec<_>>(),
            "output":self.inputs.iter().zip(&self.query.inputs).map(|(slot,f)|
                json!([slot,wire_field(f)])).collect::<Vec<_>>()})
    }
}
/// A disjoint and exhaustive three-way comparison routes a pair to one member.
#[derive(Debug, Clone)]
pub(crate) struct Dispatch {
    pub left: Field,
    pub right: Field,
    pub less: usize,
    pub equal: usize,
    pub greater: usize,
}
impl Dispatch {
    fn derive(members: &[Member], peer_key: usize) -> Option<Self> {
        if members.len() != 3 {
            return None;
        }
        let first = members[0].predicates(peer_key);
        let [(left, right, _)] = first.as_slice() else {
            return None;
        };
        let mut slots = [None; 3];
        for (i, m) in members.iter().enumerate() {
            let tests = m.predicates(peer_key);
            let [(a, b, comparison)] = tests.as_slice() else { return None };
            let normal = (a, b) == (left, right);
            if !normal && (a, b) != (right, left) {
                return None;
            }
            let branch = match *comparison {
                "Less" => {
                    if normal {
                        0
                    } else {
                        2
                    }
                }
                "Equal" => 1,
                "Greater" => {
                    if normal {
                        2
                    } else {
                        0
                    }
                }
                _ => return None,
            };
            if slots[branch].replace(i).is_some() {
                return None;
            }
        }
        Some(Self {
            left: left.clone(),
            right: right.clone(),
            less: slots[0]?,
            equal: slots[1]?,
            greater: slots[2]?,
        })
    }
}
#[derive(Debug, Clone)]
pub(crate) struct Join {
    pub driver: usize,
    pub peer: usize,
    pub driver_key: usize,
    pub peer_key: usize,
    pub members: Vec<Member>,
    pub dispatch: Option<Dispatch>,
}
impl Serialize for Join {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error> {
        json!({"driver":self.driver,"peer":self.peer,"driver_key":self.driver_key,"peer_key":self.peer_key,
            "members":self.members.iter().map(|m| m.wire(self.peer_key)).collect::<Vec<_>>(),
            "dispatch":self.dispatch.as_ref().map(|d| json!({"left":wire_field(&d.left),"right":wire_field(&d.right),
                "less":d.less,"equal":d.equal,"greater":d.greater}))}).serialize(serializer)
    }
}
#[derive(Debug, Clone, Serialize)]
pub(crate) struct Write {
    pub rule: usize,
    pub op: usize,
    pub old: Vec<Arg>,
    pub cols: Rc<Vec<usize>>,
}
#[derive(Debug, Clone, Serialize)]
pub(crate) struct Block {
    pub view: usize,
    pub producer: Join,
    pub consumers: Join,
    pub writes: Vec<Write>,
}

fn slots(a: &Atom) -> Option<Vec<usize>> {
    let v = a
        .args
        .iter()
        .map(|x| match x {
            Arg::Slot(i) => Some(*i),
            _ => None,
        })
        .collect::<Option<Vec<_>>>()?;
    (v.iter().collect::<BTreeSet<_>>().len() == v.len()).then_some(v)
}

fn member(
    p: &Program,
    rid: usize,
    driver: usize,
    spine: &BTreeSet<usize>,
) -> Option<(usize, usize, usize, Member)> {
    let r = &p.rules[rid];
    if !r.seminaive || spine.contains(&rid) {
        return None;
    }
    let tables = r
        .query
        .iter()
        .enumerate()
        .filter_map(|(i, a)| match a.call {
            Call::Table(t) => Some((i, t)),
            _ => None,
        })
        .collect::<Vec<_>>();
    let [a, b] = tables.as_slice() else {
        return None;
    };
    let (di, pi, peer) = if a.1 == driver {
        (a.0, b.0, b.1)
    } else if b.1 == driver {
        (b.0, a.0, a.1)
    } else {
        return None;
    };
    if peer == driver || !p.tables[peer].constructor {
        return None;
    }
    slots(&r.query[di])?;
    slots(&r.query[pi])?;
    for a in r.query.iter() {
        if let Call::Primitive(name, out) = &a.call {
            let [Arg::Slot(x), Arg::Slot(y), Arg::Slot(_)] = a.args.as_slice() else {
                return None;
            };
            if out != "Unit"
                || [x, y]
                    .iter()
                    .any(|k| p.templates[r.template].sorts[**k]["name"] != "i64")
            {
                return None;
            }
            if !matches!(name.as_str(), "<" | ">" | "<=" | ">=") { return None; }
        }
    }
    let query = Query::guarded_pair(r, di, pi)?;
    let (dk, pk) = query.steps[0].expansion.as_ref()?.checks.iter().find_map(|(col, field)| {
        if let Field::Anchor(driver_col) = field {
            (p.tables[peer].schema[*col]["kind"] == "eq").then_some((*driver_col, *col))
        } else { None }
    })?;
    Some((peer, dk, pk, Member { rule: rid, driver_atom: di, peer_atom: pi, query, inputs: r.inputs.clone() }))
}

fn write(p: &Program, rid: usize, op: usize, table: usize, view_atom: usize) -> Option<Write> {
    let r = &p.rules[rid];
    let t = &p.templates[r.template];
    let Op::Set(_, args, Arg::Literal(Value::Int(0))) = &t.ops[op] else {
        return None;
    };
    let relevant = t.ops[..op]
        .iter()
        .rev()
        .take_while(|x| !matches!(x, Op::Hide(..)))
        .any(|x| match x {
            Op::Union(..) => true,
            Op::Set(t, _, _) => p.tables[*t].constructor,
            _ => false,
        });
    if !relevant {
        return None;
    }
    let old = &r.query[view_atom].args[..p.tables[table].schema.len() - 1];
    let next: Vec<_> = args.iter().map(|a| t.resolve_copy(a)).collect();
    if old == next
        || old
            .iter()
            .any(|a| matches!(a,Arg::Slot(s) if !r.inputs.contains(s)))
    {
        return None;
    }
    let cols = next
        .iter()
        .map(|a| old.iter().position(|b| b == a))
        .collect::<Option<Vec<_>>>()?;
    Some(Write {
        rule: rid,
        op,
        old: old.to_vec(),
        cols: Rc::new(cols),
    })
}

pub(crate) fn derive(p: &Program, spine: &BTreeSet<usize>) -> Vec<Block> {
    let mut reads = vec![BTreeSet::new(); p.tables.len()];
    let mut writes = vec![vec![]; p.tables.len()];
    for (rid, r) in p.rules.iter().enumerate() {
        for a in r.query.iter() {
            if let Call::Table(t) = a.call {
                reads[t].insert(rid);
            }
        }
        for (i, op) in p.templates[r.template].ops.iter().enumerate() {
            if let Op::Set(t, _, _) = op {
                writes[*t].push((rid, i));
            }
        }
    }
    let mut result = vec![];
    let mut claimed = BTreeSet::new();
    for (view, table) in p.tables.iter().enumerate() {
        if table.virtual_fact
            || table.schema.last().is_none_or(|s| s["kind"] != "Unit")
            || table.merge != serde_json::json!({"var":"old"})
            || reads[view].len() < 2
        {
            continue;
        }
        if p.sets.values().any(|rs| {
            let count = reads[view].iter().filter(|r| rs.contains(r)).count();
            count > 0 && count < reads[view].len()
        }) {
            continue;
        }
        let Some(members) = reads[view]
            .iter()
            .map(|&r| member(p, r, view, spine))
            .collect::<Option<Vec<_>>>()
        else {
            continue;
        };
        let (peer, dk, pk, _) = members[0];
        if members
            .iter()
            .any(|(t, i, j, _)| (*t, *i, *j) != (peer, dk, pk))
        {
            continue;
        }
        let owners: Vec<_> = writes[view]
            .iter()
            .filter(|(r, _)| !reads[view].contains(r))
            .collect();
        let [owner] = owners.as_slice() else {
            continue;
        };
        let (producer, op) = **owner;
        let r = &p.rules[producer];
        if !p.templates[r.template]
            .ops
            .iter()
            .enumerate()
            .all(|(n, o)| n == op || matches!(o, Op::Copy(..)))
        {
            continue;
        }
        let Some(base) = r.query.iter().find_map(|a| match a.call {
            Call::Table(t) if t != peer && p.tables[t].constructor => Some(t),
            _ => None,
        }) else {
            continue;
        };
        let Some((pt, dkp, pkp, pm)) = member(p, producer, base, spine) else {
            continue;
        };
        if pt != peer {
            continue;
        }
        let mut aliases = vec![];
        for (_, _, _, m) in &members {
            for &(rid, op) in &writes[view] {
                if rid == m.rule
                    && let Some(w) = write(p, rid, op, view, m.driver_atom)
                {
                    aliases.push(w)
                }
            }
        }
        if aliases.is_empty()
            || claimed.contains(&producer)
            || reads[view].iter().any(|r| claimed.contains(r))
        {
            continue;
        }
        claimed.insert(producer);
        claimed.extend(&reads[view]);
        let members: Vec<_> = members.into_iter().map(|v| v.3).collect();
        result.push(Block {
            view,
            producer: Join {
                driver: base,
                peer,
                driver_key: dkp,
                peer_key: pkp,
                members: vec![pm],
                dispatch: None,
            },
            consumers: Join {
                driver: view,
                peer,
                driver_key: dk,
                peer_key: pk,
                dispatch: Dispatch::derive(&members, pk),
                members,
            },
            writes: aliases,
        });
    }
    result
}
