use crate::{graph::Dependency, program::Result, single_witness::SourceHeader, slots::Slots};
use serde::Serialize;
use serde_json::{Value as J, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
};
#[derive(Clone)]
pub(crate) struct Lane {
    pub w: Dependency,
    pub version: u64,
    pub epoch: u64,
    pub values: Slots,
    pub refs: Vec<(usize, Dependency)>,
    pub root: u64,
}
pub(crate) struct Closed {
    pub pivot: usize,
    pub first_model: u64,
    pub first_root: u64,
    pub scores: [f32; 2],
    pub lanes: Vec<Lane>,
    ep: u64,
    wm: u64,
}
#[derive(Default, Serialize)]
struct Counts {
    release_offers: u64,
    duplicate_addresses: u64,
    nonempty_banks: u64,
    without_offer: u64,
    cardinality: u64,
    order_version: u64,
    uncertified: u64,
    closed_banks: u64,
    closed_lanes: u64,
    delivered: u64,
    confirmed: u64,
    original_checks: u64,
    peak_bank: usize,
}
#[derive(Default)]
struct State {
    run: usize,
    collect: BTreeMap<(usize, usize), BTreeMap<Dependency, Option<Lane>>>,
    ready: BTreeMap<usize, Closed>,
    counts: Counts,
    closed_rules: BTreeMap<usize, u64>,
    active: BTreeSet<u64>,
    audit: bool,
    fault: bool,
}
thread_local! {static S:RefCell<Option<State>>=const{RefCell::new(None)};}
pub fn configure(active: bool, audit: bool, fault: bool) {
    S.with_borrow_mut(|v| {
        *v = active.then(|| State {
            audit,
            fault,
            ..Default::default()
        })
    })
}
pub(crate) fn release(
    run: usize,
    rid: usize,
    pivot: usize,
    w: Dependency,
    version: u64,
    epoch: u64,
    values: &Slots,
    refs: &[(usize, Dependency)],
    root: u64,
) {
    S.with_borrow_mut(|s| {
        let Some(s) = s else { return };
        if s.run != run {
            assert!(s.ready.is_empty());
            s.collect.clear();
            s.run = run
        }
        let bank = s.collect.entry((rid, pivot)).or_default();
        let lane = Lane {
            w,
            version,
            epoch,
            values: values.clone(),
            refs: refs.to_vec(),
            root,
        };
        use std::collections::btree_map::Entry;
        match bank.entry(w) {
            Entry::Vacant(v) => {
                v.insert(Some(lane));
            }
            Entry::Occupied(mut v) => {
                v.insert(None);
                s.counts.duplicate_addresses += 1;
            }
        }
        s.counts.release_offers += 1;
    })
}
pub(crate) fn certify(
    run_epoch: u64,
    rid: usize,
    pivot: Option<usize>,
    sources: &[SourceHeader],
    scores: &[f32],
    wm: u64,
    first_model: u64,
    floor: f32,
) -> Result<bool> {
    S.with_borrow_mut(|s| {
        let Some(s) = s else { return Ok(false) };
        let Some(pivot) = pivot else { return Ok(false) };
        if sources.is_empty() {
            return Ok(false);
        }
        s.counts.nonempty_banks += 1;
        let Some(bank) = s.collect.remove(&(rid, pivot)) else {
            s.counts.without_offer += 1;
            return Ok(false);
        };
        if bank.len() != sources.len() {
            s.counts.cardinality += 1;
            return Ok(false);
        }
        let mut group = [None, None];
        let mut lanes = Vec::with_capacity(bank.len());
        for (((_, lane), h), &score) in bank.into_iter().zip(sources).zip(scores) {
            let Some(lane) = lane else {
                s.counts.order_version += 1;
                return Ok(false);
            };
            if h.source != Some(lane.w) || h.version != lane.version || score < floor {
                s.counts.order_version += 1;
                return Ok(false);
            }
            let slot = usize::from(h.version >= wm);
            if group[slot].is_some_and(|x: u32| x != score.to_bits()) {
                s.counts.uncertified += 1;
                return Ok(false);
            }
            group[slot] = Some(score.to_bits());
            lanes.push(lane);
        }
        let first_root = crate::joint_root::internal_serials(lanes.len())?;
        s.counts.closed_banks += 1;
        s.counts.closed_lanes += lanes.len() as u64;
        s.counts.peak_bank = s.counts.peak_bank.max(lanes.len());
        *s.closed_rules.entry(rid).or_default() += lanes.len() as u64;
        assert!(
            s.ready
                .insert(
                    rid,
                    Closed {
                        pivot,
                        first_model,
                        first_root,
                        scores: group.map(|x| f32::from_bits(x.unwrap_or(0))),
                        lanes,
                        ep: run_epoch,
                        wm
                    }
                )
                .is_none()
        );
        Ok(true)
    })
}
pub(crate) fn take(rid: usize, epoch: u64, wm: u64) -> Result<Option<(Closed, bool)>> {
    S.with_borrow_mut(|s| {
        let Some(s) = s else { return Ok(None) };
        let Some(c) = s.ready.remove(&rid) else {
            return Ok(None);
        };
        if c.ep != epoch || c.wm != wm || s.fault {
            return Err("integral release epoch or watermark mismatch".into());
        }
        s.counts.delivered += c.lanes.len() as u64;
        s.counts.original_checks += u64::from(s.audit) * c.lanes.len() as u64;
        Ok(Some((c, s.audit)))
    })
}
pub(crate) fn consume(serial: u64) {
    S.with_borrow_mut(|s| {
        if let Some(s) = s
            && s.active.remove(&serial)
        {
            s.counts.confirmed += 1;
        }
    })
}
pub(crate) fn issued(serial: u64) {
    S.with_borrow_mut(|s| assert!(s.as_mut().unwrap().active.insert(serial)));
}
pub fn report() -> J {
    S.with_borrow(|s|s.as_ref().map_or(J::Null,|s|json!({"counts":s.counts,"uncommitted_internal":s.active.len(),"rules":s.closed_rules})))
}
