//! Conservative compiler proof of completion dependencies. A source table's
//! congruence can union its result sort, which can change any table containing
//! that sort. Transitive reachability includes arbitrarily long repair chains.
//! Opaque merge programs and unclassified containers retain a global boundary.
use crate::program::{Arg, Call, Op, Program, Result};
use crate::value::Value;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize)]
pub struct Scope {
    source: String,
    tables: Vec<usize>,
    pub(crate) predecessors: Vec<bool>,
}
impl Scope {
    pub fn tables(&self) -> &[usize] {
        &self.tables
    }
}
#[derive(Clone, Debug, Serialize)]
pub struct Plan {
    source: String,
    #[serde(skip)]
    affects: Vec<Vec<u64>>,
    #[serde(skip)]
    global_effects: Vec<bool>,
    pub opaque_tables: Vec<usize>,
    /// Only pure constructor completion may cross source Run boundaries.
    /// Mutable merges can allocate nodes or have source-ordered effects.
    pub deferrable: Vec<bool>,
    pub rulesets: BTreeMap<String, Scope>,
    /// Direct table observations/effects, for a proved concrete port influence.
    /// An empty list observes nothing; unknown implicit effects demand all.
    pub port_demands: BTreeMap<String, Vec<usize>>,
}
fn eq_sorts(schema: &[serde_json::Value]) -> (BTreeSet<String>, bool) {
    let mut names = BTreeSet::new();
    let mut unknown = false;
    for sort in schema {
        match sort["kind"].as_str() {
            Some("eq") => match sort["name"].as_str() {
                Some(name) => {
                    names.insert(name.to_owned());
                }
                None => unknown = true,
            },
            Some("i64" | "f64" | "String" | "bool" | "Unit" | "structural_key") => (),
            _ => unknown = true,
        }
    }
    (names, unknown)
}
fn table_call(value: &serde_json::Value) -> bool {
    match value {
        serde_json::Value::Object(obj) => {
            value["call"]["table"].is_string() || obj.values().any(table_call)
        }
        serde_json::Value::Array(xs) => xs.iter().any(table_call),
        _ => false,
    }
}
impl Plan {
    pub fn derive(p: &Program) -> Result<Self> {
        let source = p.artifact["sha256"]
            .as_str()
            .ok_or("completion source checksum")?
            .to_owned();
        let n = p.tables.len();
        let sorts = p
            .tables
            .iter()
            .map(|t| eq_sorts(&t.schema))
            .collect::<Vec<_>>();
        let opaque_tables = p
            .tables
            .iter()
            .enumerate()
            .filter_map(|(i, t)| (sorts[i].1 || table_call(&t.merge)).then_some(i))
            .collect::<Vec<_>>();
        let mut affects = vec![vec![false; n]; n];
        for (i, t) in p.tables.iter().enumerate() {
            affects[i][i] = true;
            if opaque_tables.contains(&i) {
                affects[i].fill(true);
                continue;
            }
            if t.constructor
                && let Some(sort) = t.schema.last()
                && sort["kind"] == "eq"
            {
                let name = sort["name"].as_str().ok_or("constructor result sort")?;
                for (j, (names, unknown)) in sorts.iter().enumerate() {
                    affects[i][j] |= *unknown || names.contains(name);
                }
            }
            // An opaque merge's reads are a barrier only when that merge is
            // actually pending. Its mere presence must not connect unrelated
            // sorts; the runtime switches to ordered full completion then.
        }
        let mut affects = affects
            .into_iter()
            .map(|row| {
                let mut bits = vec![0u64; n.div_ceil(64)];
                for (j, yes) in row.into_iter().enumerate() {
                    if yes {
                        bits[j / 64] |= 1 << (j % 64);
                    }
                }
                bits
            })
            .collect::<Vec<_>>();
        for k in 0..n {
            let via = affects[k].clone();
            for row in &mut affects {
                if row[k / 64] & (1 << (k % 64)) != 0 {
                    for (word, &other) in row.iter_mut().zip(&via) {
                        *word |= other;
                    }
                }
            }
        }
        let mut plan = Self {
            source,
            global_effects: affects
                .iter()
                .map(|row| {
                    row.iter()
                        .map(|word| word.count_ones() as usize)
                        .sum::<usize>()
                        == n
                })
                .collect(),
            affects,
            opaque_tables,
            deferrable: p
                .tables
                .iter()
                .enumerate()
                .map(|(i, t)| t.constructor && t.virtual_fact && !sorts[i].1)
                .collect(),
            rulesets: BTreeMap::new(),
            port_demands: BTreeMap::new(),
        };
        // If completion can reach an ordered mutable effect, retain its source
        // barrier. Deferring only the first constructor would hide that effect.
        for i in 0..n {
            plan.deferrable[i] &= (0..n).all(|j| {
                !plan.affects(i, j)
                    || (p.tables[j].constructor && p.tables[j].virtual_fact && !sorts[j].1)
            });
        }
        for (name, rules) in &p.sets {
            let mut tables = BTreeSet::new();
            let mut implicit = false;
            let mut union_sorts = BTreeSet::new();
            for &rid in rules {
                let rule = &p.rules[rid];
                let template = &p.templates[rule.template];
                for atom in rule.query.iter() {
                    implicit |= atom.args.iter().any(opaque_literal);
                    if let Call::Table(t) = atom.call {
                        tables.insert(t);
                    }
                }
                for op in template.ops.iter() {
                    // A source union can enter a pending region through the
                    // result of an otherwise unrelated constructor. Its future
                    // write influence must complete before matching this Run.
                    match op {
                        Op::Union(a, b) => {
                            for arg in [a, b] {
                                if let Arg::Slot(slot) = arg {
                                    let (sorts, unknown) =
                                        eq_sorts(std::slice::from_ref(&template.sorts[*slot]));
                                    union_sorts.extend(sorts);
                                    implicit |= unknown;
                                }
                            }
                        }
                        Op::Set(t, _, _) if p.tables[*t].constructor => {
                            let (sorts, unknown) =
                                eq_sorts(&p.tables[*t].schema[p.tables[*t].schema.len() - 1..]);
                            union_sorts.extend(sorts);
                            implicit |= unknown;
                        }
                        _ => (),
                    }
                    implicit |= match op {
                        Op::Copy(_, a) => opaque_literal(a),
                        Op::Let(_, _, args) | Op::Hide(_, args, _) => {
                            args.iter().any(opaque_literal)
                        }
                        Op::Set(_, args, v) => args.iter().any(opaque_literal) || opaque_literal(v),
                        Op::Union(a, b) => opaque_literal(a) || opaque_literal(b),
                        Op::Panic => false,
                    };
                    match op {
                        Op::Let(_, Call::Table(t), _) | Op::Set(t, _, _) | Op::Hide(t, _, _) => {
                            tables.insert(*t);
                        }
                        _ => (),
                    }
                }
                // Eq-valued primitive guards also depend on future congruence,
                // even when a sort does not appear as a separate table atom.
                let (reads, unknown) = eq_sorts(&template.sorts);
                implicit |= unknown;
                // Capture direct tables separately before adding all same-sort
                // observations to the older type-only footprint below.
                let direct = plan.port_demands.entry(name.clone()).or_default();
                for atom in rule.query.iter() {
                    if let Call::Table(t) = atom.call {
                        direct.push(t);
                    }
                }
                for op in template.ops.iter() {
                    match op {
                        Op::Let(_, Call::Table(t), _) | Op::Set(t, _, _) | Op::Hide(t, _, _) => {
                            direct.push(*t);
                            implicit |= plan.opaque_tables.contains(t);
                        }
                        _ => (),
                    }
                }
                for (t, (names, opaque)) in sorts.iter().enumerate() {
                    if unknown || *opaque || !reads.is_disjoint(names) {
                        tables.insert(t);
                    }
                }
            }
            plan.rulesets.insert(
                name.clone(),
                plan.scope(&tables.into_iter().collect::<Vec<_>>())?,
            );
            let direct = plan.port_demands.entry(name.clone()).or_default();
            for (t, (names, unknown)) in sorts.iter().enumerate() {
                if !union_sorts.is_empty() && (*unknown || !names.is_disjoint(&union_sorts)) {
                    for other in 0..n {
                        if plan.affects[t][other / 64] & (1 << (other % 64)) != 0 {
                            direct.push(other);
                        }
                    }
                }
            }
            if implicit {
                *direct = (0..n).collect();
            }
            direct.sort_unstable();
            direct.dedup();
        }
        Ok(plan)
    }
    pub fn scope(&self, tables: &[usize]) -> Result<Scope> {
        if tables.iter().any(|&t| t >= self.affects.len()) {
            return Err("completion table out of bounds".into());
        }
        Ok(Scope {
            source: self.source.clone(),
            tables: tables.to_vec(),
            predecessors: self
                .affects
                .iter()
                .map(|row| tables.iter().any(|&t| row[t / 64] & (1 << (t % 64)) != 0))
                .collect(),
        })
    }
    pub(crate) fn validate(&self, scope: &Scope) -> Result<()> {
        if scope.source != self.source || scope.predecessors.len() != self.affects.len() {
            return Err("completion scope belongs to a different program".into());
        }
        Ok(())
    }
    pub fn affects(&self, from: usize, to: usize) -> bool {
        self.affects[from][to / 64] & (1 << (to % 64)) != 0
    }
    pub(crate) fn global_effects(&self, table: usize) -> bool {
        self.global_effects[table]
    }
    pub fn report(&self) -> serde_json::Value {
        serde_json::json!({"tables":self.affects.len(), "opaque_tables":self.opaque_tables,
            "dependency_edges":self.affects.iter().flatten().map(|word|word.count_ones() as usize).sum::<usize>(),
            "deferrable_tables":self.deferrable.iter().filter(|&&v|v).count(),
            "scope":"typed conservative completion dependencies; same-sort regions may be coarser than Cell wiring"})
    }
}

fn opaque_literal(a: &Arg) -> bool {
    matches!(a, Arg::Literal(Value::Eq(_) | Value::Set(_)))
}
