//! Selected Run observation, compiled only with the existing transfer audit.
//! Copies evidence for an offline diagnostic. Never supplies execution facts,
//! performs a graph lookup, or changes matching/publication decisions.
use crate::{cell::Instance, value::Value};
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

pub(crate) fn matched<'a>(epoch: u64, rows: impl Iterator<Item = (&'a usize, &'a Instance)>, rules:&[crate::program::Rule]) {
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
                "values":row.input_view(&rules[*rule].inputs), "direct":direct,
                "parent":row.parent, "continuation":row.continuation}));
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
