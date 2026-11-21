// One issuer-selected bit in the existing template word grants a family of
// original Run activations. An internally instantiated root cannot grant this right.
use crate::program::Result;
use serde_json::{Value as J, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
};
pub(crate) const FLAG: usize = 1usize << (usize::BITS - 1);
#[derive(Clone, Copy, Debug)]
pub(crate) struct Right {
    pub serial: u64,
    pub rule: usize,
    pub run: usize,
    pub root: u64,
}
#[derive(Default)]
struct State {
    all: bool,
    allowed: BTreeSet<usize>,
    bad: bool,
    last: Option<(u64, usize)>,
    rules: BTreeMap<usize, [u64; 8]>,
    delivered: BTreeMap<u64, usize>,
    deep_seen: u64,
    unpaid: u64,
    unplanned: u64,
}
thread_local! {static S:RefCell<Option<State>>=const{RefCell::new(None)};}
pub fn configure(spec: &J) -> Result<()> {
    let mode = spec["mode"].as_str().unwrap_or("off");
    if !["off", "discovery", "learned"].contains(&mode) {
        return Err("invalid family policy".into());
    }
    let allowed = if mode == "learned" {
        serde_json::from_value(spec["rules"].clone()).map_err(|e| e.to_string())?
    } else {
        BTreeSet::new()
    };
    S.with_borrow_mut(|s| {
        *s = (mode != "off").then(|| State {
            all: mode == "discovery",
            allowed,
            bad: spec["wrong_prior"] == true,
            ..Default::default()
        })
    });
    Ok(())
}
pub(crate) fn encode(rule: usize, template: usize, n: usize) -> usize {
    assert_eq!(template & FLAG, 0);
    S.with_borrow_mut(|s| {
        if let Some(s) = s
            && (s.all || s.allowed.contains(&rule))
        {
            s.rules.entry(rule).or_default()[0] += n as u64;
            template | FLAG
        } else {
            template
        }
    })
}
pub(crate) fn accept(serial: u64, rule: usize, marked: bool) -> Result<()> {
    S.with_borrow_mut(|v| {
        if !marked {
            return Ok(());
        }
        let s = v.as_mut().ok_or("unconfigured paid-family option")?;
        if !(s.all || s.allowed.contains(&rule)) {
            return Err("producer attempted unpaid right".into());
        }
        s.rules.entry(rule).or_default()[1] += 1;
        s.last = Some((serial, rule));
        Ok(())
    })
}
pub(crate) fn install(serial: u64, rule: usize, run: usize, root: u64) -> Option<Right> {
    S.with_borrow_mut(|s| {
        let s = s.as_mut()?;
        if s.last.take() != Some((serial, rule)) {
            return None;
        }
        s.rules.entry(rule).or_default()[2] += 1;
        Some(Right {
            serial,
            rule,
            run,
            root,
        })
    })
}
pub(crate) fn route(
    right: Option<Right>,
    root: u64,
    rid: usize,
    run: usize,
) -> Result<Option<Right>> {
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return Ok(None) };
        s.deep_seen += 1;
        let Some(p) = right else {
            s.unpaid += 1;
            return Ok(None);
        };
        if p.root != root || p.rule != rid || p.run >= run || p.serial == 0 || s.bad {
            return Err("invalid predecessor on paid producer output".into());
        }
        s.rules.entry(rid).or_default()[3] += 1;
        Ok(Some(p))
    })
}
pub(crate) fn offer(rule: usize, points: u64) {
    S.with_borrow_mut(|s| {
        let r = s.as_mut().unwrap().rules.entry(rule).or_default();
        r[4] += points;
        r[5] += 1;
    })
}
pub(crate) fn issued(id: u64, rule: usize) {
    S.with_borrow_mut(|s| {
        let s = s.as_mut().unwrap();
        s.rules.entry(rule).or_default()[6] += 1;
        assert!(s.delivered.insert(id, rule).is_none());
    })
}
pub(crate) fn committed(id: u64) {
    S.with_borrow_mut(|s| {
        if let Some(s) = s
            && let Some(rule) = s.delivered.remove(&id)
        {
            s.rules.entry(rule).or_default()[7] += 1
        }
    })
}
pub fn report() -> J {
    S.with_borrow(|s|s.as_ref().map_or(J::Null,|s|json!({"rules":s.rules,"deep_seen":s.deep_seen,"unpaid":s.unpaid,"unplanned":s.unplanned,"uncommitted":s.delivered.len()})))
}
