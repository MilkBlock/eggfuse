use super::*;
use crate::joint_root::{MultiPage, Recipe, RootPage};
use std::mem::size_of;

#[derive(Clone, Copy)]
pub(crate) enum Timing {
    Run,
    Page,
}
#[derive(Clone, Copy, PartialEq)]
enum Storage {
    Capacity,
    Pooled,
    Named,
}
enum Policy {
    Capture,
    Fixed(usize),
    Previous,
    Score([f64; 8]),
}
#[derive(Clone, Copy, Default)]
struct Past {
    offers: usize,
    wins: usize,
    fresh: usize,
}
#[derive(Clone, Copy, Default)]
struct Range {
    slab: usize,
    start: usize,
    len: usize,
    taken: usize,
    named: usize,
}
#[derive(Clone)]
pub(crate) enum Handle {
    Single(RootPage),
    Multi(MultiPage),
}
impl Handle {
    fn recipe(&self, i: usize) -> Option<Recipe> {
        match self {
            Self::Single(p) => Some(p.at(i)),
            Self::Multi(p) => p.recipe(i),
        }
    }
}
struct Page {
    first: u64,
    n: usize,
    x: [f64; 8],
    handle: Option<Handle>,
    span: Range,
    granted: usize,
    cost: usize,
    wins: usize,
    fresh: usize,
}
struct RuleRecord {
    template: usize,
    x: [f64; 8],
    past: Past,
    now: Past,
    span: Range,
    request: usize,
    pages: Vec<Page>,
}
struct PrivateSlot {
    frame: Option<Cell>,
    named: Option<(u64, u64)>,
    fact_ptr: usize,
}
pub(crate) struct Claimed {
    pub frame: Cell,
    pub early_ptr: usize,
    pub preconstructed: bool,
}
#[derive(Default, serde::Serialize)]
struct Counts {
    runs: usize,
    rule_vectors: usize,
    pages: usize,
    offers: usize,
    committed: usize,
    fresh: usize,
    requested: usize,
    granted: usize,
    clipped: usize,
    preconstructed: usize,
    capacity_only: usize,
    used: usize,
    unused: usize,
    fallback: usize,
    missing_named: usize,
    stale_named: usize,
    parent_mismatch: usize,
    underforecast: usize,
    names_attached: usize,
    direct_fresh: usize,
    promoted: usize,
    payload_identity: usize,
    sampled_payloads: usize,
    slabs: usize,
    peak_slots: usize,
    peak_private_bytes: usize,
    header_capacity_bytes: usize,
    private_payload_capacity_bytes: usize,
}
pub(crate) struct Staging {
    timing: Timing,
    storage: Storage,
    policy: Policy,
    cap: usize,
    capture: bool,
    audit: bool,
    fault: u8,
    epoch: u64,
    set: String,
    history: std::collections::HashMap<String, std::collections::HashMap<usize, Past>>,
    rules: std::collections::HashMap<usize, RuleRecord>,
    order: Vec<usize>,
    slabs: Vec<Vec<PrivateSlot>>,
    used_budget: usize,
    bytes: usize,
    stats: Counts,
    samples: Vec<J>,
    grants: Vec<[usize; 6]>,
    seen: usize,
}
impl Staging {
    pub(crate) fn configure(cfg: &J, audit: bool) -> Result<Self> {
        let timing = match cfg["timing"].as_str() {
            Some("run") => Timing::Run,
            Some("page") => Timing::Page,
            _ => return Err("invalid stage timing".into()),
        };
        let storage = match cfg["storage"].as_str() {
            Some("capacity") => Storage::Capacity,
            Some("pooled") => Storage::Pooled,
            Some("named") => Storage::Named,
            _ => return Err("invalid stage storage".into()),
        };
        let cap = usize::try_from(cfg["cap"].as_u64().ok_or("missing private Cell budget")?)
            .map_err(|_| "invalid budget")?;
        if cap > 65536 {
            return Err("private Cell budget exceeds 65536 records".into());
        }
        let policy = match cfg["policy"].as_str() {
            Some("capture") => Policy::Capture,
            Some("previous") => Policy::Previous,
            Some("fixed") => Policy::Fixed(
                cfg["fixed"]
                    .as_u64()
                    .ok_or("missing fixed forecast")?
                    .min(cap as u64) as usize,
            ),
            Some("score") => {
                let w: [f64; 8] =
                    serde_json::from_value(cfg["weights"].clone()).map_err(|e| e.to_string())?;
                if !w.iter().all(|v| v.is_finite()) {
                    return Err("non-finite forecast weights".into());
                }
                Policy::Score(w)
            }
            _ => return Err("invalid count policy".into()),
        };
        let fault = match cfg["fault"].as_str() {
            None | Some("none") => 0,
            Some("withheld") => 1,
            Some("stale") => 2,
            _ => return Err("invalid private Cell fault".into()),
        };
        if fault != 0 && storage != Storage::Named {
            return Err("named fault needs named storage".into());
        }
        let capture = matches!(policy, Policy::Capture) || cfg["capture"].as_bool() == Some(true);
        Ok(Self {
            timing,
            storage,
            policy,
            cap,
            capture,
            audit,
            fault,
            epoch: 0,
            set: String::new(),
            history: Default::default(),
            rules: Default::default(),
            order: vec![],
            slabs: vec![],
            used_budget: 0,
            bytes: 0,
            stats: Default::default(),
            samples: vec![],
            grants: vec![],
            seen: 0,
        })
    }
    fn features(past: Past, lhs: usize, rhs: usize, offers: usize) -> [f64; 8] {
        let log = |v: usize| (v as f64).ln_1p();
        [
            1.,
            log(past.offers),
            log(past.wins),
            log(past.fresh),
            past.fresh as f64 / past.offers.max(1) as f64,
            log(lhs),
            log(rhs),
            log(offers),
        ]
    }
    fn predict(&self, x: &[f64; 8], past: Past, offers: usize) -> usize {
        match &self.policy {
            Policy::Capture => 0,
            Policy::Fixed(n) => *n,
            Policy::Previous => match self.timing {
                Timing::Run => past.fresh.min(self.cap),
                Timing::Page => ((offers as f64 * x[4]).round() as usize).min(self.cap),
            },
            Policy::Score(w) => w
                .iter()
                .zip(x)
                .map(|(a, b)| a * b)
                .sum::<f64>()
                .clamp(0., (self.cap as f64).ln_1p())
                .exp_m1()
                .round()
                .clamp(0., self.cap as f64) as usize,
        }
    }
    fn fill_slab(&mut self, g: &Graph, grants: &[(usize, usize)]) -> usize {
        let index = self.slabs.len();
        let count: usize = grants.iter().map(|v| v.1).sum();
        if count == 0 {
            return index;
        }
        let mut slab = Vec::with_capacity(count);
        for &(rid, n) in grants {
            let template = g.program.rules[rid].template;
            let facts = g.program.templates[template].ops.len().clamp(1, 4);
            for _ in 0..n {
                let (frame, ptr) = if self.storage != Storage::Capacity {
                    let c = Cell::private_layout(template, self.epoch, facts);
                    let ptr = c.facts.stage_allocation();
                    let bytes = c.facts.stage_bytes();
                    self.bytes += bytes;
                    self.stats.private_payload_capacity_bytes += bytes;
                    self.stats.preconstructed += 1;
                    (Some(c), ptr)
                } else {
                    self.stats.capacity_only += 1;
                    (None, 0)
                };
                slab.push(PrivateSlot {
                    frame,
                    named: None,
                    fact_ptr: ptr,
                });
            }
        }
        let headers = slab.capacity() * size_of::<PrivateSlot>();
        self.stats.slabs += 1;
        self.stats.header_capacity_bytes += headers;
        self.bytes += headers;
        self.stats.peak_private_bytes = self.stats.peak_private_bytes.max(self.bytes);
        self.slabs.push(slab);
        self.used_budget += count;
        self.stats.granted += count;
        self.stats.peak_slots = self.stats.peak_slots.max(self.used_budget);
        index
    }
    pub(crate) fn start(&mut self, g: &Graph, set: &str, active: &[usize]) {
        self.finish();
        self.set = set.to_owned();
        self.epoch = g.epoch;
        self.stats.runs += 1;
        let mut forecasts = vec![];
        for &rid in active {
            if self.rules.contains_key(&rid) {
                continue;
            }
            let p = &g.program.rules[rid];
            let past = self
                .history
                .get(set)
                .and_then(|history| history.get(&rid))
                .copied()
                .unwrap_or_default();
            let x = Self::features(
                past,
                p.query.len(),
                g.program.templates[p.template].ops.len(),
                0,
            );
            let n = if matches!(self.timing, Timing::Run) {
                self.predict(&x, past, 0)
            } else {
                0
            };
            self.rules.insert(
                rid,
                RuleRecord {
                    template: p.template,
                    x,
                    past,
                    now: Default::default(),
                    span: Default::default(),
                    request: n,
                    pages: vec![],
                },
            );
            self.order.push(rid);
            forecasts.push((rid, n));
            self.stats.requested += n;
        }
        if matches!(self.timing, Timing::Run) {
            self.stats.rule_vectors += 1;
            let requested: usize = forecasts.iter().map(|p| p.1).sum();
            if requested > self.cap {
                let mut rank = vec![];
                let mut used = 0;
                for (i, item) in forecasts.iter_mut().enumerate() {
                    let product = item.1 as u128 * self.cap as u128;
                    item.1 = (product / requested as u128) as usize;
                    used += item.1;
                    rank.push((std::cmp::Reverse(product % requested as u128), i));
                }
                rank.sort_unstable();
                for &(_, i) in rank.iter().take(self.cap - used) {
                    forecasts[i].1 += 1;
                }
                self.stats.clipped += requested - self.cap;
            }
            let slab = self.fill_slab(g, &forecasts);
            let mut start = 0;
            for (rid, n) in forecasts {
                self.rules.get_mut(&rid).unwrap().span = Range {
                    slab,
                    start,
                    len: n,
                    ..Default::default()
                };
                start += n;
            }
        }
    }
    pub(crate) fn page(&mut self, g: &Graph, rid: usize, first: u64, n: usize, handle: Handle) {
        let Some(r) = self.rules.get(&rid) else {
            return;
        };
        if n == 0 {
            return;
        }
        let p = &g.program.rules[rid];
        let x = Self::features(
            r.past,
            p.query.len(),
            g.program.templates[p.template].ops.len(),
            n,
        );
        let mut span = Range::default();
        if matches!(self.timing, Timing::Page) {
            let request = self.predict(&x, r.past, n);
            let grant = request.min(self.cap - self.used_budget);
            self.stats.requested += request;
            self.stats.clipped += request - grant;
            let slab = self.fill_slab(g, &[(rid, grant)]);
            span = Range {
                slab,
                start: 0,
                len: grant,
                ..Default::default()
            };
            self.rules.get_mut(&rid).unwrap().request += request;
        }
        let r = self.rules.get_mut(&rid).unwrap();
        let cost = span.len;
        let mut granted = cost;
        if self.storage == Storage::Named {
            let record = if matches!(self.timing, Timing::Run) {
                &mut r.span
            } else {
                &mut span
            };
            let k = n.min(record.len - record.named);
            let start = record.start + record.named;
            if k > 0 {
                for (i, s) in self.slabs[record.slab][start..start + k]
                    .iter_mut()
                    .enumerate()
                {
                    s.named = match self.fault {
                        1 => None,
                        2 => Some((self.epoch.wrapping_sub(1), first + i as u64)),
                        _ => Some((self.epoch, first + i as u64)),
                    };
                }
            }
            self.stats.names_attached += if self.fault == 1 { 0 } else { k };
            let slab = record.slab;
            record.named += k;
            granted = k;
            span = Range {
                slab,
                start,
                len: k,
                ..Default::default()
            };
        }
        r.pages.push(Page {
            first,
            n,
            x,
            handle: (granted > 0 && self.storage == Storage::Named).then_some(handle),
            span,
            granted,
            cost,
            wins: 0,
            fresh: 0,
        });
        r.now.offers += n;
        self.stats.pages += 1;
        self.stats.offers += n;
    }
    fn page_for(r: &RuleRecord, serial: u64) -> Option<usize> {
        let j = r
            .pages
            .partition_point(|p| p.first <= serial)
            .checked_sub(1)?;
        (serial - r.pages[j].first < r.pages[j].n as u64).then_some(j)
    }
    fn winner(&mut self, rid: usize, serial: u64) {
        let Some(r) = self.rules.get_mut(&rid) else {
            return;
        };
        r.now.wins += 1;
        self.stats.committed += 1;
        if let Some(j) = Self::page_for(r, serial) {
            r.pages[j].wins += 1;
        }
    }
    fn take(&mut self, template: usize, rid: usize, serial: u64) -> Option<Claimed> {
        self.stats.fresh += 1;
        let Some(r) = self.rules.get_mut(&rid) else {
            self.stats.fallback += 1;
            return None;
        };
        r.now.fresh += 1;
        let page = Self::page_for(r, serial);
        if let Some(j) = page {
            r.pages[j].fresh += 1;
        }
        if r.template != template {
            self.stats.fallback += 1;
            return None;
        }
        let slot = if self.storage == Storage::Named {
            let Some(p) = page.and_then(|i| r.pages.get(i)) else {
                self.stats.fallback += 1;
                return None;
            };
            let lane = (serial - p.first) as usize;
            if lane >= p.granted {
                self.stats.underforecast += 1;
                self.stats.fallback += 1;
                return None;
            }
            let s = &mut self.slabs[p.span.slab][p.span.start + lane];
            if s.named != Some((self.epoch, serial)) {
                if s.named.is_none() {
                    self.stats.missing_named += 1
                } else {
                    self.stats.stale_named += 1
                }
                self.stats.fallback += 1;
                return None;
            }
            if !p
                .handle
                .as_ref()
                .and_then(|h| h.recipe(lane))
                .is_some_and(|h| crate::joint_root::same_staged_parent(&h))
            {
                self.stats.parent_mismatch += 1;
                self.stats.fallback += 1;
                return None;
            }
            s.named = None;
            s
        } else {
            let range = match self.timing {
                Timing::Run => &mut r.span,
                Timing::Page => {
                    let Some(j) = page else {
                        self.stats.fallback += 1;
                        return None;
                    };
                    &mut r.pages[j].span
                }
            };
            if range.taken >= range.len {
                self.stats.underforecast += 1;
                self.stats.fallback += 1;
                return None;
            }
            let i = range.start + range.taken;
            range.taken += 1;
            &mut self.slabs[range.slab][i]
        };
        let made = slot.frame.is_some();
        if !made {
            slot.frame = Some(Cell::private_layout(template, self.epoch, 0));
        }
        let frame = slot.frame.take().unwrap();
        debug_assert_eq!(frame.template, template);
        self.stats.used += 1;
        self.seen += 1;
        Some(Claimed {
            frame,
            early_ptr: slot.fact_ptr,
            preconstructed: made,
        })
    }
    fn finish(&mut self) {
        if self.epoch == 0 {
            return;
        }
        let history = self
            .history
            .entry(std::mem::take(&mut self.set))
            .or_default();
        for rid in self.order.drain(..) {
            let rec = self.rules.remove(&rid).unwrap();
            if self.capture {
                if matches!(self.timing, Timing::Run) {
                    self.samples.push(json!([
                        self.epoch,
                        rid,
                        rec.template,
                        rec.x,
                        rec.now.offers,
                        rec.now.wins,
                        rec.now.fresh
                    ]));
                } else {
                    for p in &rec.pages {
                        self.samples.push(json!([
                            self.epoch,
                            rid,
                            rec.template,
                            p.x,
                            p.n,
                            p.wins,
                            p.fresh
                        ]));
                    }
                }
                let granted = if matches!(self.timing, Timing::Run) {
                    rec.span.len
                } else {
                    rec.pages.iter().map(|p| p.cost).sum()
                };
                self.grants.push([
                    self.epoch as usize,
                    rid,
                    rec.request,
                    granted,
                    rec.now.wins,
                    rec.now.fresh,
                ]);
            }
            history.insert(rid, rec.now);
        }
        self.stats.unused += self.used_budget - self.seen;
        self.used_budget = 0;
        self.seen = 0;
        self.bytes = 0;
        self.slabs.clear();
        self.epoch = 0;
    }
    fn report(&mut self) -> J {
        self.finish();
        json!({"counts":self.stats,"samples":std::mem::take(&mut self.samples),"grants":std::mem::take(&mut self.grants)})
    }
}
impl Cell {
    fn private_layout(template: usize, epoch: u64, facts: usize) -> Self {
        Self {
            completed_prefix: 0,
            started_epoch: epoch,
            completed: false,
            template,
            parent: None,
            values: Default::default(),
            facts: crate::slots::FrameMap::stage_reserved(facts),
            recipe_depth: 0,
        }
    }
}
impl Graph {
    pub fn configure_spec_cells(&mut self, cfg: &J, audit: bool) -> Result<()> {
        let staging = Staging::configure(cfg, audit || cfg["audit"].as_bool() == Some(true))?;
        crate::joint_root::retain_staging_parent(staging.storage == Storage::Named);
        self.spec_cells = Some(std::cell::RefCell::new(staging));
        Ok(())
    }
    pub fn spec_cells_report(&self) -> J {
        self.spec_cells
            .as_ref()
            .map_or(J::Null, |v| v.borrow_mut().report())
    }
    pub(crate) fn spec_run(&self, set: &str, rules: &[usize]) {
        if let Some(s) = &self.spec_cells {
            s.borrow_mut().start(self, set, rules)
        }
    }
    pub(crate) fn spec_end_run(&self) {
        if let Some(s) = &self.spec_cells {
            s.borrow_mut().finish();
        }
    }
    pub(crate) fn spec_winner(&self) {
        if let Some(s) = &self.spec_cells
            && let Some((r, serial, _)) = crate::joint_root::staging_identity()
        {
            s.borrow_mut().winner(r, serial);
        }
    }
    pub(crate) fn spec_page(&self, rid: usize, first: u64, n: usize, h: Handle) {
        if let Some(s) = &self.spec_cells {
            s.borrow_mut().page(self, rid, first, n, h);
        }
    }
    pub(super) fn take_private(&self, t: usize) -> Option<Claimed> {
        let stage = self.spec_cells.as_ref()?;
        let (rid, serial, template) = crate::joint_root::staging_identity()?;
        if t != template {
            return None;
        }
        let result = stage.borrow_mut().take(t, rid, serial);
        result
    }
    pub(super) fn check_private(&self, id: u32, old_ptr: usize, early: bool, direct: bool) {
        let mut stage = self.spec_cells.as_ref().unwrap().borrow_mut();
        if direct {
            stage.stats.direct_fresh += 1;
        } else {
            stage.stats.promoted += 1;
        }
        if early {
            let stored = self.cells.get(&id).expect("published staged Cell");
            stage.stats.sampled_payloads += 1;
            if old_ptr == stored.facts.stage_allocation() {
                stage.stats.payload_identity += 1;
            } else if stage.audit && stored.facts.is_empty() {
                panic!("unused staged payload allocation replaced")
            }
        }
    }
    pub(crate) fn publish_private_temp(&mut self, id: u32, mut scratch: Cell) {
        if let Some(mut claimed) = self.take_private(scratch.template) {
            // Keep the staged header and the backing it reserved for facts. The
            // existing prefix/write code supplied a transient evaluation frame.
            let c = &mut claimed.frame;
            c.parent = scratch.parent;
            c.values = std::mem::take(&mut scratch.values);
            c.completed = scratch.completed;
            c.completed_prefix = scratch.completed_prefix;
            c.recipe_depth = scratch.recipe_depth;
            c.facts.stage_move_from(std::mem::take(&mut scratch.facts));
            self.store_cell(id, claimed.frame);
            self.check_private(id, claimed.early_ptr, claimed.preconstructed, false);
        } else {
            self.store_cell(id, scratch)
        }
    }
}
