//! Verified producer-local projections and their source-schedule permissions.
//! A projection never certifies uniqueness after union; the executor checks that
//! obligation against the current Run snapshot before bypassing an atom.
use crate::{cell::{Definition, Site}, program::*};
use serde::{Deserialize, Serialize};
use serde_json::Value as J;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::rc::Rc;

#[derive(Clone, Copy, Debug)]
pub(crate) struct WitnessSource {
    pub source: crate::cell::Site,
    pub retained: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LocalRead {
    pub atom: usize,
    pub table: usize,
    pub columns: Vec<Arg>,
    pub effect: Option<usize>,
    /// Normalize elided operations to their actual query/effect donor once.
    #[serde(skip)]
    pub(crate) witness: Option<WitnessSource>,
    #[serde(default)]
    pub(crate) assignments: Vec<(usize, Arg)>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Continuation {
    pub producer: usize,
    pub consumer: usize,
    pub anchor: usize,
    pub reads: Vec<LocalRead>,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct MultiStage {
    #[serde(default)]
    pub stage_entries: Vec<(usize, usize, Rc<Vec<usize>>)>,
    pub routes: HashMap<(usize, usize, usize, usize), Rc<Continuation>>,
    pub entries: HashMap<(usize, usize), Rc<Vec<usize>>>,
    pub finishes: Vec<Rc<Vec<usize>>>,
}
pub(crate) fn extend(
    atom: &Atom,
    table: usize,
    columns: &[Arg],
    mapping: &mut BTreeMap<usize, Arg>,
) -> Result<()> {
    if !matches!(atom.call,Call::Table(t) if t==table) || atom.args.len() != columns.len() {
        return Err("continuation operator/arity differs".into());
    }
    for (to, from) in atom.args.iter().zip(columns) {
        match to {
            Arg::Slot(slot) => {
                if let Some(old) = mapping.get(slot) {
                    if old != from {
                        return Err("continuation relative binding differs".into());
                    }
                } else {
                    mapping.insert(*slot, from.clone());
                }
            }
            _ if to != from => return Err("continuation literal differs".into()),
            _ => {}
        }
    }
    Ok(())
}
/// extend() verifies literals, repeated slots and agreement with the pivot.
/// A physically identical pivot already bound those slots in the shared packet.
pub(crate) fn assignments(pivot: &Atom, atom: &Atom, columns: &[Arg]) -> Vec<(usize, Arg)> {
    let mut seen: BTreeSet<_> = pivot
        .args
        .iter()
        .filter_map(|a| match a {
            Arg::Slot(i) => Some(*i),
            _ => None,
        })
        .collect();
    atom.args
        .iter()
        .zip(columns)
        .filter_map(|(dst, src)| match dst {
            Arg::Slot(i) if seen.insert(*i) => Some((*i, src.clone())),
            _ => None,
        })
        .collect()
}
impl MultiStage {
    pub(crate) fn witness_report(&self) -> J {
        let mut retained = 0;
        let mut local = 0;
        let mut skipped = 0;
        for read in self.routes.values().flat_map(|r| &r.reads) {
            match read.witness {
                Some(w) => {
                    retained += usize::from(w.retained);
                    local += usize::from(matches!(w.source, crate::cell::Site::Effect(_)));
                }
                None => skipped += 1,
            }
        }
        serde_json::json!({"retained_receipt_reads":retained,"physical_fallback_reads":local,
            "excluded_reads":skipped,"new_capture_slots":0,
            "contract":"existing admitted receipts only; nonempty complete keys; full live row validation"})
    }
    pub fn parse(program: &Program, raw: &J) -> Result<Self> {
        if raw.is_null() {
            return Ok(Self::default());
        }
        if raw["schema"] != "eggfuse-multistage/v1"
            || raw["recipe_sha256"] != program.artifact["recipe"]["sha256"]
            || raw["control"] != program.artifact["recipe"]["control"]
        {
            return Err("multi-stage source/control differs".into());
        }
        let sets = program.artifact["recipe"]["rulesets"]
            .as_array()
            .ok_or("recipe sets")?
            .iter()
            .map(|s| serde_json::json!({"name":s["name"],"rule_ids":s["rule_ids"]}))
            .collect::<Vec<_>>();
        if raw["rule_sets"] != J::Array(sets) {
            return Err("multi-stage permissions differ".into());
        }
        if raw["stage_entries"].is_null() {
            {
                return Err("stage Spine programs require compiler stage_entries; recompile source_sk_mk through the Cell CPU target".into());
            }
        } else if raw["stage_entries"] != crate::stage_spine::compile_entries(program) {
            return Err("stage entry program differs from exhaustive typed key flow".into());
        }
        let mut result = Self::default();
        if let Some(entries) = raw["stage_entries"].as_array() {
            for e in entries {
                result.stage_entries.push((
                    e["rule"].as_u64().unwrap() as usize,
                    e["anchor"].as_u64().unwrap() as usize,
                    Rc::new(
                        e["atoms"]
                            .as_array()
                            .unwrap()
                            .iter()
                            .map(|i| i.as_u64().unwrap() as usize)
                            .collect(),
                    ),
                ));
            }
        }
        let verify_points = |rid: usize,
                             anchor: Option<usize>,
                             raw: &J|
         -> Result<Rc<Vec<usize>>> {
            let rule = program.rules.get(rid).ok_or("point program rule")?;
            let mut known = BTreeSet::new();
            let mut covered = BTreeSet::new();
            for (i, atom) in rule.query.iter().enumerate() {
                if anchor == Some(i) || (anchor.is_none() && matches!(atom.call, Call::Table(_))) {
                    covered.insert(i);
                    for arg in &atom.args {
                        if let Arg::Slot(s) = arg {
                            known.insert(*s);
                        }
                    }
                }
            }
            let mut order = vec![];
            for i in array(raw)? {
                let i = i.as_u64().ok_or("point instruction")? as usize;
                let atom = rule.query.get(i).ok_or("point instruction range")?;
                if !covered.insert(i) || (anchor.is_none() && matches!(atom.call, Call::Table(_))) {
                    return Err("invalid point instruction domain".into());
                }
                let full = !atom.args[..atom.args.len() - 1]
                    .iter()
                    .any(|a| matches!(a,Arg::Slot(s) if !known.contains(s)));
                let inverse = matches!(atom.call,Call::Table(t) if program.tables[t].schema.last().unwrap()["kind"]=="eq")
                    && matches!(atom.args.last(),Some(Arg::Slot(s)) if known.contains(s));
                if !full && !inverse {
                    return Err("point read has unbound inputs".into());
                }
                for arg in &atom.args {
                    if let Arg::Slot(s) = arg {
                        known.insert(*s);
                    }
                }
                order.push(i);
            }
            Ok(Rc::new(order))
        };
        for entry in array(&raw["entries"])? {
            let rid = entry["rule"].as_u64().ok_or("point rule")? as usize;
            let anchor = entry["anchor"].as_u64().ok_or("point anchor")? as usize;
            if !matches!(
                program
                    .rules
                    .get(rid)
                    .and_then(|r| r.query.get(anchor))
                    .map(|a| &a.call),
                Some(Call::Table(_))
            ) {
                return Err("point entry is not a fact".into());
            }
            let order = verify_points(rid, Some(anchor), &entry["atoms"])?;
            if result.entries.insert((rid, anchor), order).is_some() {
                return Err("duplicate point entry".into());
            }
        }
        if array(&raw["finishes"])?.len() != program.rules.len() {
            return Err("point finishes differ".into());
        }
        for (rid, finish) in array(&raw["finishes"])?.iter().enumerate() {
            result.finishes.push(verify_points(rid, None, finish)?);
        }
        for route in array(&raw["routes"])? {
            let number = |name: &str| {
                route[name]
                    .as_u64()
                    .map(|n| n as usize)
                    .ok_or_else(|| format!("invalid continuation {name}"))
            };
            let producer = number("producer")?;
            let effect = number("effect")?;
            let consumer = number("consumer")?;
            let anchor = number("anchor")?;
            let target = program.rules.get(consumer).ok_or("continuation consumer")?;
            let cell = Definition::new(program, producer)?;
            let (table, cols) = cell.local_columns(Site::Effect(effect))?;
            let mut mapping = BTreeMap::new();
            extend(
                target.query.get(anchor).ok_or("continuation anchor")?,
                table,
                &cols,
                &mut mapping,
            )?;
            let mut covered = BTreeSet::from([anchor]);
            let mut reads = vec![];
            for step in array(&route["steps"])? {
                let atom = step["atom"].as_u64().ok_or("continuation atom")? as usize;
                let index = step["source_index"]
                    .as_u64()
                    .ok_or("continuation source index")? as usize;
                let kind = string(&step["source_kind"])?;
                if !covered.insert(atom) {
                    return Err("duplicate continuation atom".into());
                }
                let site = Site::parse(kind, index)?;
                let (table, columns) = cell.local_columns(site)?;
                extend(
                    target.query.get(atom).ok_or("continuation atom index")?,
                    table,
                    &columns,
                    &mut mapping,
                )?;
                let assignments = if kind == "effect" {
                    assignments(&target.query[anchor], &target.query[atom], &columns)
                } else {
                    vec![]
                };
                if let Some(raw) = step.get("assignments") {
                    if *raw != serde_json::json!(assignments) {
                        return Err("invalid producer slot wiring".into());
                    }
                }
                reads.push(LocalRead {
                    assignments,
                    atom,
                    table,
                    effect: (kind == "effect").then_some(index),
                    // Empty keys already use a singleton directory read. A
                    // receipt dispatch cannot remove hashing/field work there.
                    witness: (program.tables[table].virtual_fact
                        && columns.len() > 1).then(|| WitnessSource { retained: false, source:
                        if kind == "query" { crate::cell::Site::Query(index) }
                        else { program.known_results.static_sources.get(producer)
                            .and_then(|sources| sources[index])
                            .unwrap_or(crate::cell::Site::Effect(index)) } }),
                    columns,
                });
            }
            let residual = (0..target.query.len())
                .filter(|i| !covered.contains(i))
                .map(J::from)
                .collect::<Vec<_>>();
            if route["residual"] != J::Array(residual) {
                return Err("continuation residual domain differs".into());
            }
            if result
                .routes
                .insert(
                    (program.rules[producer].template, effect, consumer, anchor),
                    Rc::new(Continuation {
                        producer,
                        consumer,
                        anchor,
                        reads,
                    }),
                )
                .is_some()
            {
                return Err("duplicate continuation".into());
            }
        }
        Ok(result)
    }
}

/// Use only receipts already admitted by the catalog. Missing query receipts
/// cannot be recovered by interpreting an equality representative as a row ID.
pub(crate) fn compile_witnesses(p: &mut Program) {
    for route in p.multi_stage.routes.values_mut() {
        let producer = route.producer;
        for read in &mut Rc::make_mut(route).reads {
            let Some(witness) = &mut read.witness else { continue };
            #[cfg(feature = "iterative-bake")]
            {
                witness.retained = p.iterative.exports(producer).contains(&witness.source);
            }
            #[cfg(not(feature = "iterative-bake"))]
            let _ = producer;
            if !witness.retained && matches!(witness.source, crate::cell::Site::Query(_)) {
                read.witness = None;
            }
        }
    }
}
