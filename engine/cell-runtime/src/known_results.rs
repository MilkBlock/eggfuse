//! Constructor knowledge carried by live recipe instances, not a global memo.
use crate::graph::{Dependency, FactRef};
use crate::cell::{Definition, Site, resolve_alias};
use crate::program::{Arg, Call, Op, Program, Result, array};
use serde::{Deserialize, Serialize};
use serde_json::{Value as J, json};
use std::collections::{BTreeMap, BTreeSet};
use std::rc::Rc;

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Plans {
    pub static_slots: Vec<Vec<Option<Arg>>>,
    pub static_skip: Vec<Rc<Vec<bool>>>,
    /// Original matched atom or constructor operation for each statically aliased slot's defining operation.
    #[serde(default)]
    pub static_sources: Vec<Vec<Option<Site>>>,
    pub values: BTreeMap<usize, Rc<Vec<Option<Arg>>>>,
    pub rules: BTreeMap<usize, Vec<Option<Site>>>,
    pub queries: BTreeSet<usize>,
    pub remember: BTreeMap<usize, BTreeSet<usize>>,
}
/// Keep a single requested query witness inline.
#[derive(Clone, Debug, Default)]
pub(crate) enum QueryFacts {
    #[cfg(feature = "structural-depth")]
    Tracked(Box<QueryFacts>, Vec<Option<Dependency>>, u8),
    #[default]
    None,
    One(usize, Option<FactRef>),
    All(Vec<Option<FactRef>>),
    // Only enabled for a compiled query continuation demanding mutable rows.
    Ports(Vec<Option<Dependency>>),
}
impl QueryFacts {
    #[cfg(feature = "structural-depth")]
    pub fn tracked(&self, atom: usize) -> Option<Dependency> {
        match self {
            Self::Tracked(_, rows, _) => rows.get(atom).copied().flatten(),
            _ => self.get(atom).map(Dependency::Fact),
        }
    }
    #[cfg(feature = "structural-depth")]
    pub fn mark(&mut self, depth: u8) {
        if let Self::Tracked(_, _, d) = self {
            *d = depth
        }
    }
    #[cfg(feature = "structural-depth")]
    pub fn depth(&self) -> u8 {
        if let Self::Tracked(_, _, d) = self {
            *d
        } else {
            0
        }
    }
    pub fn record(&mut self, atom: usize, witness: Option<Dependency>) {
        let fact = match witness {
            Some(Dependency::Fact(f)) => Some(f),
            _ => None,
        };
        match self {
            #[cfg(feature = "structural-depth")]
            Self::Tracked(original, rows, _) => {
                original.record(atom, witness);
                rows[atom] = witness;
            }
            Self::One(source, slot) if *source == atom => *slot = fact,
            Self::All(rows) => rows[atom] = fact,
            Self::Ports(rows) => rows[atom] = witness,
            _ => {}
        }
    }
    pub fn get(&self, atom: usize) -> Option<FactRef> {
        match self {
            #[cfg(feature = "structural-depth")]
            Self::Tracked(original, _, _) => original.get(atom),
            Self::One(source, fact) if *source == atom => *fact,
            Self::All(rows) => rows[atom],
            Self::Ports(rows) => match rows[atom] {
                Some(Dependency::Fact(f)) => Some(f),
                _ => None,
            },
            _ => None,
        }
    }
    pub(crate) fn receipt(&self, atom: usize) -> Option<Dependency> {
        match self {
            #[cfg(feature = "structural-depth")]
            Self::Tracked(_, rows, _) => rows[atom],
            Self::Ports(rows) => rows[atom],
            _ => self.get(atom).map(Dependency::Fact),
        }
    }
}
impl Plans {
    pub fn parse(p: &Program, raw: &J) -> Result<Self> {
        let (result, mut expected) = Self::derive(p)?;
        if raw.is_null() {
            return Ok(result);
        }
        if raw.get("static_aliases").is_none() {
            expected.as_object_mut().unwrap().remove("static_aliases");
        }
        if *raw != expected {
            return Err("known result projections differ from typed recipe".into());
        }
        // Reject non-array payloads even when a future compiler has no plans.
        array(&raw["plans"])?;
        Ok(result)
    }
    pub(crate) fn derive(p: &Program) -> Result<(Self, J)> {
        let mut plans = vec![];
        let mut result = Self::default();
        for (rid, r) in p.rules.iter().enumerate() {
            let cell = Definition::new(p, rid)?;
            let ops = &p.templates[r.template].ops;
            let norm = |aa: &[Arg]| aa.iter().map(|a| cell.template.resolve_copy(a)).collect::<Vec<_>>();
            let rows = cell.local_relations().map(|relation| {
                (relation.site, relation.table,
                    relation.columns().map(|a| cell.template.resolve_copy(a)).collect::<Vec<_>>())
            }).collect::<Vec<_>>();
            for (op, e) in ops.iter().enumerate() {
                let Op::Let(_, Call::Table(t), aa) = e else {
                    continue;
                };
                if !p.tables[*t].virtual_fact {
                    continue;
                }
                let key = norm(aa);
                for (source, table, values) in &rows {
                    if matches!(source,Site::Effect(i) if *i>=op) {
                        continue;
                    }
                    if table == t && values[..values.len() - 1] == key {
                        let (kind, index) = match source {
                            Site::Query(i) => {
                                result.queries.insert(rid);
                                ("query", i)
                            }
                            Site::Effect(i) => {
                                result.remember.entry(rid).or_default().insert(*i);
                                ("effect", i)
                            }
                        };
                        plans.push(json!({"rule":rid,"operation":op,"source_kind":kind,"source_index":index}));
                        result
                            .rules
                            .entry(rid)
                            .or_insert_with(|| vec![None; ops.len()])[op] = Some(*source);
                        if matches!(source, Site::Query(_))
                            || matches!(source,Site::Effect(i) if matches!(ops[*i],Op::Let(..)))
                        {
                            Rc::make_mut(
                                result
                                    .values
                                    .entry(rid)
                                    .or_insert_with(|| Rc::new(vec![None; ops.len()])),
                            )[op] = values.last().cloned();
                        }
                        break;
                    }
                }
            }
        }
        let mut static_aliases = vec![];
        let deleted = p
            .rules
            .iter()
            .flat_map(|r| p.templates[r.template].ops.iter())
            .filter_map(|e| {
                if let Op::Hide(t, _, true) = e {
                    Some(*t)
                } else {
                    None
                }
            })
            .collect::<BTreeSet<_>>();
        for (rid, r) in p.rules.iter().enumerate() {
            let t = &p.templates[r.template];
            let mut aliases = BTreeMap::new();
            let mut known: BTreeMap<(usize, Vec<Arg>), (Arg, J, Site)> = BTreeMap::new();
            let mut slots = vec![None; t.sorts.len()];
            let mut skip = vec![false; t.ops.len()];
            let mut sources = vec![None; t.ops.len()];
            for (i, a) in r.query.iter().enumerate() {
                if let Call::Table(t) = a.call
                    && p.tables[t].constructor
                    && !deleted.contains(&t)
                {
                    known
                        .entry((t, a.args[..a.args.len() - 1].to_vec()))
                        .or_insert((
                            a.args.last().unwrap().clone(),
                            p.artifact["recipe"]["rules"][rid]["query"][i]["args"]
                                .as_array()
                                .unwrap()
                                .last()
                                .unwrap()
                                .clone(),
                            Site::Query(i),
                        ));
                }
            }
            for (i, e) in t.ops.iter().enumerate() {
                match e {
                    Op::Copy(dst, a) => {
                        aliases.insert(*dst, resolve_alias(a, &aliases));
                    }
                    Op::Hide(t, _, true) => known.retain(|(table, _), _| table != t),
                    Op::Let(dst, Call::Table(t), aa) if p.tables[*t].constructor => {
                        let key = (*t, aa.iter().map(|a| resolve_alias(a, &aliases)).collect());
                        if let Some((value, j, source)) = known.get(&key) {
                            sources[i] = Some(*source);
                            slots[*dst] = Some(value.clone());
                            skip[i] = true;
                            aliases.insert(*dst, value.clone());
                            static_aliases
                                .push(json!({"rule":rid,"operation":i,"dst":dst,"value":j}));
                        } else {
                            known.insert(
                                key,
                                (Arg::Slot(*dst), json!({"slot":dst}), Site::Effect(i)),
                            );
                        }
                    }
                    _ => (),
                }
            }
            // Aliases never replace the original source in known, so nested
            // aliases resolve directly to a matched atom or an executed RHS.
            result.static_sources.push(sources);
            result.static_slots.push(slots);
            result.static_skip.push(Rc::new(skip));
        }
        let expected = json!({"schema":"eggfuse-known-results/v1","recipe_sha256":p.artifact["recipe"]["sha256"],"plans":plans,"static_aliases":static_aliases,
            "contract":"live canonical FactRef with identical full constructor key; dirty domains fall back; never skip set/union/guard"});
        Ok((result, expected))
    }
}

#[derive(Default, Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct Stats {
    pub static_eliminated: u64,
    pub lazy_prefix_eliminated: u64,
    pub static_observed_equal: u64,
    pub static_observed_other: u64,
    pub value_eligible: u64,
    pub value_reuses: u64,
    pub observed_same_value: u64,
    pub observed_other_value: u64,
    pub deletion_guard_misses: u64,
    pub requests: u64,
    pub planned: u64,
    pub query_sources: u64,
    pub effect_sources: u64,
    pub available: u64,
    pub unavailable: u64,
    pub dirty: u64,
    pub mismatched: u64,
    pub expired: u64,
    pub validated: u64,
    pub avoided_lookups: u64,
    pub observed_same_witness: u64,
    pub observed_other_witness: u64,
    pub retained_result_writes: u64,
    pub opportunities_by_table: BTreeMap<String, u64>,
}

impl Stats {
    pub(crate) fn elide_static(&mut self, aliases: Option<&[bool]>, op: usize) -> bool {
        if aliases.is_some_and(|skip| skip[op]) {
            self.static_eliminated += 1;
            self.avoided_lookups += 1;
            true
        } else {
            false
        }
    }
}
