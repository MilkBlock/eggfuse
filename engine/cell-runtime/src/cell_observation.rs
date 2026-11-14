//! Selected Run observation, compiled only with the existing transfer audit.
//! Copies evidence for an offline diagnostic. Never supplies execution facts,
//! performs a graph lookup, or changes matching/publication decisions.
use crate::{cell::{Instance, QueryFacts}, graph::Dependency, value::Value};
use serde_json::{Value as Json, json};
use std::{cell::RefCell, collections::{BTreeMap, BTreeSet}};

struct Capture {
    details: bool,
    rules: BTreeSet<usize>,
    table: usize,
    watermarks: BTreeMap<usize, u64>,
    matches: Vec<Json>,
    writes: Vec<Json>,
    counts: BTreeMap<(u64, usize), [u64; 3]>,
}
thread_local! {
    static CAPTURE: RefCell<Option<Capture>> = const { RefCell::new(None) };
}

/// Call between Runs. The caller separately enables the ordered write audit,
/// which supplies RHS source ordinals; repair writes have no RHS source.
pub fn begin(rules: impl IntoIterator<Item = usize>, table: usize) {
    CAPTURE.with_borrow_mut(|c| {
        assert!(c.is_none(), "unfinished Cell observation");
        *c = Some(Capture { details: true, rules: rules.into_iter().collect(), table,
            watermarks: BTreeMap::new(), matches: vec![], writes: vec![], counts: BTreeMap::new() });
    });
}

/// Aggregate successful matches, effective writes and direct tokens per rule
/// and Run. This first pass selects windows without retaining every binding.
pub fn begin_counts(rules: impl IntoIterator<Item = usize>, table: usize) {
    begin(rules, table);
    CAPTURE.with_borrow_mut(|c| c.as_mut().unwrap().details = false);
}

pub(crate) fn watermark(rule: usize, watermark: u64) {
    CAPTURE.with_borrow_mut(|c| {
        if let Some(c) = c && c.rules.contains(&rule) {
            c.watermarks.insert(rule, watermark);
        }
    });
}

// Export only already retained evidence. Missing projections remain unknown.
fn retained_witnesses(facts: &QueryFacts) -> Vec<(usize, Option<Dependency>)> {
    match facts {
        QueryFacts::None => vec![],
        QueryFacts::One(atom, fact) => vec![(*atom, fact.map(Dependency::Fact))],
        QueryFacts::All(rows) => rows.iter().enumerate().map(|(i, f)| (i, f.map(Dependency::Fact))).collect(),
        QueryFacts::Ports(rows) => rows.iter().copied().enumerate().collect(),
        #[cfg(feature = "structural-depth")]
        QueryFacts::Tracked(_, rows, _) => rows.iter().copied().enumerate().collect(),
    }
}

pub(crate) fn matched<'a>(epoch: u64, rows: impl Iterator<Item = (&'a usize, &'a Instance)>) {
    CAPTURE.with_borrow_mut(|c| {
        let Some(c) = c else { return };
        for (ordinal, (rule, row)) in rows.enumerate() {
            if !c.rules.contains(rule) { continue; }
            #[cfg(feature = "iterative-bake")]
            let direct = row.direct.is_some();
            #[cfg(not(feature = "iterative-bake"))]
            let direct = false;
            let counts = c.counts.entry((epoch, *rule)).or_default();
            counts[0] += 1;
            counts[2] += u64::from(direct);
            if !c.details { continue; }
            c.matches.push(json!({"ordinal":ordinal, "rule":rule,
                "watermark":c.watermarks.get(rule), "epoch":row.epoch,
                "values":row.values, "direct":direct,
                "parent":row.parent, "continuation":row.continuation,
                "retained_query_witnesses":retained_witnesses(&row.known)}));
        }
    });
}

pub(crate) fn write(epoch: u64, source: Option<(u64, usize)>, table: usize,
    index: usize, key: &[Value], old: Option<&Value>, new: &Value) {
    CAPTURE.with_borrow_mut(|c| {
        if let Some(c) = c && c.table == table {
            if let Some((_, rule)) = source && c.rules.contains(&rule) {
                c.counts.entry((epoch, rule)).or_default()[1] += 1;
            }
            if !c.details { return; }
            c.writes.push(json!({"epoch":epoch, "source":source, "index":index,
                "key":key, "old":old, "new":new}));
        }
    });
}

pub fn finish() -> Json {
    let c = CAPTURE.take().expect("missing Cell observation");
    json!({"matches":c.matches, "effective_writes":c.writes,
        "watermarks":c.watermarks, "counts":c.counts.into_iter()
            .map(|((epoch, rule), counts)| (epoch, rule, counts)).collect::<Vec<_>>()})
}

#[cfg(test)]
mod witness_tests {
    use super::*;
    use crate::graph::FactRef;
    #[test]
    fn export_preserves_missing_and_actual_returned_witnesses() {
        assert!(retained_witnesses(&QueryFacts::None).is_empty());
        let fact=FactRef {cell:7,op:3};
        assert_eq!(retained_witnesses(&QueryFacts::One(2,Some(fact))),vec![(2,Some(Dependency::Fact(fact)))]);
        assert_eq!(retained_witnesses(&QueryFacts::Ports(vec![None,Some(Dependency::Function(9))])),vec![(0,None),(1,Some(Dependency::Function(9)))]);
    }
}
