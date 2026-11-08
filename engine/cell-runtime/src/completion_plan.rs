//! Conservative compiler proof of completion dependencies. A source table's
//! congruence can union its result sort, which can change any table containing
//! that sort. Transitive reachability includes arbitrarily long repair chains.
//! Checked merge reads and constructor births are separate obligations.
use crate::program::{Arg, Call, Op, Program, Result};
use crate::value::Value;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
#[path = "completion_access.rs"]
mod access;
#[path = "completion_effects.rs"]
mod effects;
#[path = "completion_rhs.rs"]
pub(crate) mod rhs;

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
    waits: Vec<Vec<u64>>,
    /// Tables that completion may read, including merges reached by its effects.
    pub completion_reads: Vec<Vec<usize>>,
    pub merges: Vec<effects::Merge>,
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
    /// Historical aggregate before incoming-union expansion. Runtime port
    /// scopes instead use the query footprint and actually matched rules.
    pub port_accesses: BTreeMap<String, Vec<usize>>,
    /// Mandatory source snapshot reads, before any RHS can run.
    pub query_demands: BTreeMap<String, Vec<usize>>,
    /// Separate source reads, RHS accesses, and conservative union effects.
    pub rule_demands: Vec<access::Rule>,
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
            Some("set") => {
                let (elements, opaque) = eq_sorts(std::slice::from_ref(&sort["element"]));
                names.extend(elements);
                unknown |= opaque;
            }
            _ => unknown = true,
        }
    }
    (names, unknown)
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
        let merges = (0..n)
            .map(|t| effects::Merge::derive(p, t))
            .collect::<Vec<_>>();
        let opaque_tables = p
            .tables
            .iter()
            .enumerate()
            .filter_map(|(i, _)| (sorts[i].1 || merges[i].opaque).then_some(i))
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
        transitive(&mut affects);
        // Closing an existing constructor key can publish an equality. A merge
        // constructing a previously absent key only publishes that table's new
        // fact; its fresh result is not a union of existing classes. Add birth
        // writes after equality-task closure so they do not invent that union.
        let task_effects = affects.clone();
        let completion_reads = affects
            .iter()
            .map(|row| {
                let mut reads = BTreeSet::new();
                for (t, merge) in merges.iter().enumerate() {
                    if row[t / 64] & (1 << (t % 64)) != 0 {
                        reads.extend(merge.reads.iter().copied());
                    }
                }
                reads.into_iter().collect::<Vec<_>>()
            })
            .collect::<Vec<_>>();
        for (i, row) in task_effects.iter().enumerate() {
            for (t, merge) in merges.iter().enumerate() {
                if row[t / 64] & (1 << (t % 64)) != 0 {
                    for &birth in &merge.births {
                        affects[i][birth / 64] |= 1 << (birth % 64);
                    }
                }
            }
        }
        // A selected merge must retain the original ordering with every task
        // that can alter its reads. These edges constrain waiting; reading a
        // table does not itself mutate that table or enqueue its consumers.
        let mut read_dependencies = vec![vec![0u64; n.div_ceil(64)]; n];
        for (from, row) in affects.iter().enumerate() {
            read_dependencies[from][from / 64] |= 1 << (from % 64);
            for (to, reads) in completion_reads.iter().enumerate() {
                if reads.iter().any(|&r| row[r / 64] & (1 << (r % 64)) != 0) {
                    read_dependencies[from][to / 64] |= 1 << (to % 64);
                }
            }
        }
        transitive(&mut read_dependencies);
        let mut waits = vec![vec![0u64; n.div_ceil(64)]; n];
        for (from, dependencies) in read_dependencies.iter().enumerate() {
            for (to, effects) in affects.iter().enumerate() {
                if dependencies[to / 64] & (1 << (to % 64)) != 0 {
                    for (word, &bits) in waits[from].iter_mut().zip(effects) {
                        *word |= bits;
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
            waits,
            completion_reads,
            merges,
            opaque_tables,
            deferrable: p
                .tables
                .iter()
                .enumerate()
                .map(|(i, t)| t.constructor && t.virtual_fact && !sorts[i].1)
                .collect(),
            rulesets: BTreeMap::new(),
            port_demands: BTreeMap::new(),
            port_accesses: BTreeMap::new(),
            query_demands: BTreeMap::new(),
            rule_demands: Vec::new(),
        };
        // If completion can reach an ordered mutable effect, retain its source
        // barrier. Deferring only the first constructor would hide that effect.
        for i in 0..n {
            plan.deferrable[i] &= (0..n).all(|j| {
                !plan.affects(i, j)
                    || (p.tables[j].constructor && p.tables[j].virtual_fact && !sorts[j].1)
            });
        }
        plan.rule_demands = (0..p.rules.len())
            .map(|rid| access::Rule::derive(p, &plan, rid, &sorts))
            .collect();
        for (name, rules) in &p.sets {
            let mut tables = BTreeSet::new();
            let mut direct = BTreeSet::new();
            let mut accesses = BTreeSet::new();
            let mut queries = BTreeSet::new();
            for &rid in rules {
                let demand = &plan.rule_demands[rid];
                queries.extend(demand.query.iter().copied());
                direct.extend(demand.query.iter().chain(&demand.rhs).copied());
                accesses.extend(demand.query.iter().chain(&demand.accesses).copied());
                let template = &p.templates[p.rules[rid].template];
                let (reads, unknown) = eq_sorts(&template.sorts);
                for (t, (names, opaque)) in sorts.iter().enumerate() {
                    if unknown || *opaque || !reads.is_disjoint(names) {
                        tables.insert(t);
                    }
                }
            }
            tables.extend(&direct);
            plan.rulesets.insert(
                name.clone(),
                plan.scope(&tables.into_iter().collect::<Vec<_>>())?,
            );
            plan.port_demands
                .insert(name.clone(), direct.into_iter().collect());
            plan.port_accesses
                .insert(name.clone(), accesses.into_iter().collect());
            plan.query_demands
                .insert(name.clone(), queries.into_iter().collect());
        }
        Ok(plan)
    }
    /// Compile once per template when the optional bound-effect path is enabled.
    /// Ordinary scoped execution does not allocate or retain this code.
    pub(crate) fn prepare_pure_rhs(&mut self, p: &Program) {
        let mut templates = BTreeMap::new();
        for (rid, demand) in self.rule_demands.iter_mut().enumerate() {
            let template = p.rules[rid].template;
            demand.pure = templates
                .entry(template)
                .or_insert_with(|| {
                    rhs::Plan::derive(p, &p.templates[template]).map(std::sync::Arc::new)
                })
                .clone();
        }
    }
    pub fn scope(&self, tables: &[usize]) -> Result<Scope> {
        if tables.iter().any(|&t| t >= self.affects.len()) {
            return Err("completion table out of bounds".into());
        }
        Ok(Scope {
            source: self.source.clone(),
            tables: tables.to_vec(),
            predecessors: self
                .waits
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
        let mut seen = BTreeSet::new();
        let pure = self
            .rule_demands
            .iter()
            .filter_map(|r| r.pure.as_ref())
            .filter(|p| seen.insert(std::sync::Arc::as_ptr(p)))
            .collect::<Vec<_>>();
        serde_json::json!({"tables":self.affects.len(), "opaque_tables":self.opaque_tables,
            "pure_rhs_templates":pure.len(),
            "pure_rhs_expressions":pure.iter().map(|p|p.values.len()).sum::<usize>(),
            "pure_rhs_effects":pure.iter().map(|p|p.effects.len()).sum::<usize>(),
            "pure_rhs_copies_elided":pure.iter().map(|p|p.copies_elided).sum::<usize>(),
            "dependency_edges":self.affects.iter().flatten().map(|word|word.count_ones() as usize).sum::<usize>(),
            "wait_edges":self.waits.iter().flatten().map(|word|word.count_ones() as usize).sum::<usize>(),
            "merge_read_edges":self.merges.iter().map(|m|m.reads.len()).sum::<usize>(),
            "merge_birth_edges":self.merges.iter().map(|m|m.births.len()).sum::<usize>(),
            "merges":self.merges.iter().enumerate().filter(|(_,m)|m.opaque||!m.reads.is_empty()).map(|(table,m)|serde_json::json!({"table":table,"reads":m.reads,"births":m.births,"opaque":m.opaque})).collect::<Vec<_>>(),
            "deferrable_tables":self.deferrable.iter().filter(|&&v|v).count(),
            "scope":"typed conservative completion dependencies; same-sort regions may be coarser than Cell wiring"})
    }
}

fn opaque_literal(a: &Arg) -> bool {
    matches!(a, Arg::Literal(Value::Eq(_) | Value::Set(_)))
}
fn transitive(rows: &mut [Vec<u64>]) {
    for k in 0..rows.len() {
        let via = rows[k].clone();
        for row in &mut *rows {
            if row[k / 64] & (1 << (k % 64)) != 0 {
                for (word, &other) in row.iter_mut().zip(&via) {
                    *word |= other;
                }
            }
        }
    }
}
