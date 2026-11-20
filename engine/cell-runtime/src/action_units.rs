//! Single-emission action-granularity trial on the native CPU Graph.
use crate::{
    cell::{Matched, QueryFacts, bind_query},
    graph::{Dependency, Graph, Row},
    program::{Arg, Call, Op, Result},
    slots::Slots,
};
use serde::Deserialize;
use serde_json::{Value as Json, json};
use std::collections::{BTreeMap, BTreeSet};
use std::rc::Rc;

#[derive(Deserialize)]
pub struct Plan {
    pub digest: String,
    pub root: Vec<f32>,
    pub head: Vec<f32>,
    pub joins: Vec<[usize; 4]>,
    pub entries: Vec<[i32; 3]>, // rule, pivot, table; absent transferred leaf has rule -1
    pub sets: Vec<String>,
    #[serde(default)]
    schedule: Option<RowSchedule>,
}

#[derive(Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Admission {
    Free,
    FreeOnce,
    Static,
    Transfer,
}

#[derive(Clone, Copy, Deserialize)]
struct RowSchedule {
    rows: usize,
    waves: usize,
    admission: Admission,
}

// Hash only the stable physical source and typed entrance. Ownership never uses a
// result value, source winner label or future update.
fn owner(observation: &[i64; 8], rows: usize) -> usize {
    let leaf = observation[0] as u64 / 8;
    let address = observation[1] as u64;
    (address
        .wrapping_mul(0x9e3779b1)
        .wrapping_add(leaf.wrapping_mul(0x85ebca77))
        % rows as u64) as usize
}

type Decision = ([f32; 12], Option<usize>, Option<usize>, [f32; 8]);

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum Kind {
    Census,
    Raw,
    Leaf,
    Macro,
}

#[derive(Clone)]
pub(crate) struct Raw {
    pub(crate) rows: Vec<(usize, Dependency)>,
    pub(crate) values: Slots,
}

#[derive(Clone)]
struct Issued {
    epoch: u64,
    lane: usize,
    leaf: usize,
    code: usize, // one discrete unit id, or source rule id for raw
    anchor: Dependency,
    raw: Option<Raw>,
    root_ordinal: usize,
    child_ordinal: usize,
    child_epoch: u64,
    root_verified: bool,
    child_verified: bool,
    produced: Option<Dependency>,
    address: usize,
    suffix_rank: i32,
}

pub(crate) struct Policy {
    p: Plan,
    pub(crate) kind: Kind,
    pub(crate) residual: bool,
    observe: bool,
    corrupt: bool,
    prev: Vec<[f32; 12]>,
    transfers: Vec<(u64, usize, usize, usize, usize, usize, u64, Dependency)>,
    handoff_scores: usize,
    idle_slots: usize,
    ids: BTreeMap<Dependency, usize>,
    published: BTreeMap<Dependency, (u64, usize)>,
    issued: Vec<Issued>,
    current: BTreeMap<(usize, usize, Dependency), Vec<usize>>,
    pending: BTreeMap<(usize, usize, Dependency), (usize, usize)>, // token, output port
    ordinal: usize,
    epoch: u64,
    observations: Vec<(usize, Vec<[i64; 8]>, Vec<[f32; 12]>)>,
    root_attempts: u64,
    child_attempts: u64,
    raw_rejections: u64,
    raw_field_count: usize,
    scored: usize,
    pub(crate) point_reads: [usize; 2],
    at_boundary: u64,
}

impl Policy {
    pub(crate) fn new(
        p: Plan,
        g: &Graph,
        kind: &str,
        residual: bool,
        observe: bool,
        corrupt: bool,
    ) -> Result<Self> {
        let kind = match kind {
            "census" if residual && observe => Kind::Census,
            "raw" => Kind::Raw,
            "leaf" => Kind::Leaf,
            "macro" => Kind::Macro,
            _ => return Err("unknown action representation".into()),
        };
        if p.entries.len() != 32
            || p.root.len() != 783
            || p.head.len() != 19 * p.joins.len() + 2 + 64 + 2048
            || p.root.iter().chain(&p.head).any(|x| !x.is_finite())
        {
            return Err("incompatible action weights".into());
        }
        for &[rid, pivot, t] in &p.entries {
            if rid < 0 {
                continue;
            }
            let rule = g
                .program
                .rules
                .get(rid as usize)
                .ok_or("unknown action rule")?;
            if !(1..=2).contains(&rule.query.len())
                || !rule.query.iter().all(|a| matches!(a.call, Call::Table(_)))
                || !matches!(rule.query.get(pivot as usize).map(|a|&a.call),Some(Call::Table(table)) if *table==t as usize)
                || g.program
                    .cell_queries
                    .get(rid as usize, pivot as usize)
                    .is_none()
            {
                return Err("invalid action entry".into());
            }
        }
        let mut codes = BTreeSet::new();
        for &[id, left, port, right] in &p.joins {
            if id < 32 || left >= 32 || right >= 32 || !codes.insert(id) {
                return Err("invalid or duplicate macro unit".into());
            }
            if p.entries[left][0] < 0 || p.entries[right][0] < 0 {
                continue;
            }
            let parent = &g.program.rules[p.entries[left][0] as usize];
            if !matches!(g.program.templates[parent.template].ops.get(port),Some(Op::Let(_,Call::Table(t),_)|Op::Set(t,..)) if *t==p.entries[right][2] as usize)
            {
                return Err("macro output disagrees with certified next entrance".into());
            }
        }
        if kind == Kind::Census && p.schedule.is_some() {
            return Err("census has one exhaustive issuance".into());
        }
        let rows = p.schedule.map_or(2, |s| s.rows);
        if let Some(s) = p.schedule {
            if !(1..=4).contains(&rows) || !(1..=8).contains(&s.waves) {
                return Err("unsupported row/wave dimensions".into());
            }
        }
        Ok(Self {
            p,
            kind,
            residual,
            observe,
            corrupt,
            prev: vec![[0.; 12]; rows],
            transfers: Vec::new(),
            handoff_scores: 0,
            idle_slots: 0,
            ids: BTreeMap::new(),
            published: BTreeMap::new(),
            issued: vec![],
            current: BTreeMap::new(),
            pending: BTreeMap::new(),
            ordinal: 0,
            epoch: 0,
            observations: vec![],
            root_attempts: 0,
            child_attempts: 0,
            raw_rejections: 0,
            raw_field_count: 0,
            scored: 0,
            point_reads: [0; 2],
            at_boundary: 0,
        })
    }
    pub(crate) fn start_rhs(&mut self) {
        self.ordinal += 1;
    }
    pub(crate) fn commit(&mut self, id: usize, child: bool, values: &Slots) {
        let v = &mut self.issued[id];
        if child {
            assert!(v.root_ordinal > 0 && v.child_ordinal == 0);
            v.child_ordinal = self.ordinal;
            v.child_epoch = self.epoch;
        } else {
            assert_eq!(v.root_ordinal, 0);
            v.root_ordinal = self.ordinal;
            if let Some(raw) = &v.raw {
                assert!(
                    raw.values
                        .iter()
                        .all(|(slot, value)| values.get(slot) == Some(value))
                );
            }
        }
    }
    pub(crate) fn publish(
        &mut self,
        w: Dependency,
        depth: usize,
        source: Option<usize>,
        producer: usize,
        effect: usize,
    ) {
        self.published.insert(w, (self.epoch, depth));
        if self.kind != Kind::Macro {
            return;
        }
        let Some(id) = source else { return };
        let v = &mut self.issued[id];
        if v.root_ordinal == 0 || v.produced.is_some() {
            return;
        }
        if let Some(&[_, left, output, right]) = self.p.joins.iter().find(|j| j[0] == v.code) {
            let [rid, pivot, _] = self.p.entries[right];
            if producer == self.p.entries[left][0] as usize && effect == output && rid >= 0 {
                v.produced = Some(w);
                self.pending
                    .insert((rid as usize, pivot as usize, w), (id, output));
            }
        }
    }
    pub(crate) fn claims(
        &mut self,
        rid: usize,
        pivot: usize,
        w: Dependency,
        source: Option<usize>,
        effect: usize,
    ) -> smallvec::SmallVec<[(usize, bool); 3]> {
        let key = (rid, pivot, w);
        let mut result = smallvec::SmallVec::new();
        if let Some(ids) = self.current.get(&key) {
            for &id in ids {
                self.root_attempts += 1;
                result.push((id, false));
            }
        }
        if let Some(&(id, expected)) = self.pending.get(&key) {
            if source == Some(id) && effect == expected && self.issued[id].child_ordinal == 0 {
                self.child_attempts += 1;
                result.push((id, true));
            }
        }
        result
    }
    pub(crate) fn validated(&mut self, id: usize, child: bool) {
        if child {
            self.issued[id].child_verified = true;
        } else {
            self.issued[id].root_verified = true;
        }
    }
    pub(crate) fn candidate_refs(&self, rid: usize) -> Vec<(usize, Dependency)> {
        self.current
            .keys()
            .chain(self.pending.keys())
            .filter_map(|&(r, p, w)| (r == rid).then_some((p, w)))
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect()
    }
    pub(crate) fn raw(&self, id: usize) -> Option<&Raw> {
        self.issued[id].raw.as_ref()
    }
    fn native_rows(g: &Graph, table: usize) -> Result<Vec<Rc<Row>>> {
        Ok(g.witnesses(table)
            .into_iter()
            .rev()
            .take(8)
            .filter_map(|w| g.row(w).transpose())
            .collect::<Result<Vec<_>>>()?
            .into_iter()
            .map(Rc::new)
            .collect())
    }
    pub(crate) fn begin(
        &mut self,
        g: &Graph,
        set: &str,
        watermarks: &[u64],
        epoch: u64,
    ) -> Result<()> {
        self.epoch = epoch;
        self.at_boundary += 1;
        self.current.clear();
        let set_id = self
            .p
            .sets
            .iter()
            .position(|s| s == set)
            .ok_or("unknown set for CPU policy")?;
        let rules = g.program.sets.get(set).ok_or("unknown action schedule")?;
        let mut bank = BTreeMap::new();
        let mut obs = Vec::new();
        let mut physical = Vec::new();
        for (l, &[r, _, t]) in self.p.entries.iter().enumerate() {
            if r < 0 || !rules.contains(&(r as usize)) {
                continue;
            }
            if !bank.contains_key(&t) {
                bank.insert(t, Self::native_rows(g, t as usize)?);
            }
            let wm = watermarks[r as usize] as i64;
            for (rank, row) in bank[&t].iter().enumerate() {
                let next = self.ids.len();
                let address = *self.ids.entry(row.witness).or_insert(next);
                let (age, depth) = self.published.get(&row.witness).map_or((32, 0), |&(e, d)| {
                    ((epoch.saturating_sub(e)).min(32) as i64, d.min(16) as i64)
                });
                obs.push([
                    (l * 8 + rank) as i64,
                    address as i64,
                    epoch.saturating_sub(row.epoch).min(32) as i64,
                    (row.epoch as i64 - wm).clamp(-32, 32),
                    row.hidden as i64,
                    depth,
                    age,
                    row.values.len().min(16) as i64,
                ]);
                physical.push(row.clone());
            }
        }
        let schedule = self.p.schedule.unwrap_or(RowSchedule {
            rows: 2,
            waves: 1,
            admission: Admission::Free,
        });
        let mut reserved = vec![false; obs.len()];
        for wave in 0..schedule.waves {
            let mut decisions = Vec::with_capacity(schedule.rows);
            if self.kind == Kind::Census {
                // Training-only exact opportunity scan. These candidates never count as learned emissions.
                decisions.extend((0..obs.len()).map(|i| ([0.; 12], Some(i), None, [0.; 8])));
            }
            for lane in 0..if self.kind == Kind::Census {
                0
            } else {
                schedule.rows
            } {
                let mut scores = 0;
                let decision = self.forward(lane, set_id, &obs, |i| {
                    let eligible = match schedule.admission {
                        Admission::Free => true,
                        Admission::FreeOnce => !reserved[i],
                        Admission::Static | Admission::Transfer => {
                            !reserved[i] && owner(&obs[i], schedule.rows) == lane
                        }
                    };
                    scores += usize::from(eligible);
                    eligible
                });
                self.scored += scores;
                decisions.push(decision);
            }
            // Publish reservations only after all simultaneous proposals. A free
            // wave may contain duplicate claims; the source verifier deduplicates them.
            for decision in &decisions {
                if let Some(i) = decision.1 {
                    reserved[i] = true;
                }
            }
            if schedule.admission == Admission::Transfer {
                let busy: Vec<_> = decisions.iter().map(|d| d.1.is_some()).collect();
                for lane in 0..schedule.rows {
                    if busy[lane] {
                        continue;
                    }
                    let mut scores = 0;
                    let borrowed = self.forward(lane, set_id, &obs, |i| {
                        let eligible = !reserved[i] && busy[owner(&obs[i], schedule.rows)];
                        scores += usize::from(eligible);
                        eligible
                    });
                    self.scored += scores;
                    self.handoff_scores += scores;
                    if let Some(i) = borrowed.1 {
                        reserved[i] = true;
                        self.transfers.push((
                            epoch,
                            wave,
                            owner(&obs[i], schedule.rows),
                            lane,
                            obs[i][0] as usize / 8,
                            obs[i][1] as usize,
                            physical[i].epoch,
                            physical[i].witness,
                        ));
                        decisions[lane] = borrowed;
                    }
                }
            }
            for (lane, (next, winning, unit, wanted_rank)) in decisions.into_iter().enumerate() {
                if self.kind != Kind::Census {
                    self.prev[lane] = next;
                }
                self.idle_slots += usize::from(winning.is_none());
                let Some(index) = winning else { continue };
                let action = obs[index][0] as usize;
                let leaf = action / 8;
                let [rid, pivot, _] = self.p.entries[leaf];
                let anchor = &physical[index];
                let rule = &g.program.rules[rid as usize];
                let code = match self.kind {
                    Kind::Raw => rid as usize,
                    Kind::Census | Kind::Leaf => leaf,
                    Kind::Macro => unit.unwrap_or(leaf),
                };
                let mut raw = None;
                let mut suffix_rank = -1;
                if self.kind == Kind::Raw {
                    let mut rows = vec![(pivot as usize, anchor.clone())];
                    if rule.query.len() == 2 {
                        let pos = 1 - pivot as usize;
                        let Call::Table(t) = rule.query[pos].call else {
                            unreachable!()
                        };
                        if !bank.contains_key(&(t as i32)) {
                            bank.insert(t as i32, Self::native_rows(g, t)?);
                        }
                        let candidates = &bank[&(t as i32)];
                        if !candidates.is_empty() && !self.corrupt {
                            let pick = (0..candidates.len())
                                .max_by(|&i, &j| {
                                    wanted_rank[i].total_cmp(&wanted_rank[j]).then(j.cmp(&i))
                                })
                                .unwrap();
                            suffix_rank = pick as i32;
                            rows.push((pos, candidates[pick].clone()));
                        }
                    }
                    // Project the *proposed* fields with first definition wins. No key lookup and no LHS test here.
                    let mut env = BTreeMap::new();
                    for (pos, row) in &rows {
                        for (arg, value) in rule.query[*pos].args.iter().zip(row.values.iter()) {
                            if let Arg::Slot(s) = arg {
                                env.entry(*s).or_insert_with(|| value.clone());
                            }
                        }
                    }
                    let vals = rule
                        .inputs
                        .iter()
                        .filter_map(|s| env.get(s).map(|v| (*s, v.clone())))
                        .collect();
                    self.raw_field_count += rule.inputs.len();
                    raw = Some(Raw {
                        rows: rows
                            .into_iter()
                            .map(|(pos, row)| (pos, row.witness))
                            .collect(),
                        values: vals,
                    });
                }
                let id = self.issued.len();
                self.issued.push(Issued {
                    epoch,
                    lane: wave * schedule.rows + lane,
                    leaf,
                    code,
                    anchor: anchor.witness,
                    raw,
                    root_ordinal: 0,
                    child_ordinal: 0,
                    child_epoch: 0,
                    root_verified: false,
                    child_verified: false,
                    produced: None,
                    address: obs[index][1] as usize,
                    suffix_rank,
                });
                // Discharge the submitted envelope itself. A macro supplies no separate root token:
                // its library id decodes to both the first entrance and the later output-port instruction.
                let (entry_rule, entry_pivot) = match self.kind {
                    Kind::Raw => (code, self.issued[id].raw.as_ref().unwrap().rows[0].0),
                    Kind::Census | Kind::Leaf | Kind::Macro => {
                        let initial = if code < 32 {
                            code
                        } else {
                            self.p.joins.iter().find(|j| j[0] == code).unwrap()[1]
                        };
                        let [r, p, _] = self.p.entries[initial];
                        (r as usize, p as usize)
                    }
                };
                self.current
                    .entry((entry_rule, entry_pivot, anchor.witness))
                    .or_default()
                    .push(id);
            }
        }
        if self.observe {
            self.observations.push((set_id, obs, self.prev.clone()));
        }
        Ok(())
    }
    fn forward(
        &self,
        lane: usize,
        stage: usize,
        obs: &[[i64; 8]],
        mut eligible: impl FnMut(usize) -> bool,
    ) -> Decision {
        let w = &self.p.root;
        let h = &self.p.head;
        let prev = self.prev[lane];
        let lane = lane % 2; // Tie the learned row roles when expanding the frozen two-row policy.
        let jcount = self.p.joins.len();
        let mut state = [0f32; 8];
        let mut token = [0f32; 12];
        for i in 0..8 {
            let mut x = w[344 + 8 * lane + i]
                + w[88 + 8 * (stage % 32) + i]
                + w[360 + 8 * prev[8] as usize + i];
            for j in 0..8 {
                x += w[8 * i + j] * prev[j];
            }
            x += w[64 + 3 * i] * prev[9] / 16384.;
            x += w[65 + 3 * i] * prev[10] / 8.;
            x += w[66 + 3 * i] * prev[11];
            state[i] = x.tanh();
        }
        let mut best = w[782];
        for i in 0..8 {
            best += state[i] * w[774 + i];
        }
        let mut winner = None;
        let mut keys = [0f32; 8];
        for (n, f) in obs.iter().enumerate() {
            if !eligible(n) {
                continue;
            }
            let action = f[0] as usize;
            let l = action / 8;
            let rank = action % 8;
            let x = [
                f[2] as f32 / 32.,
                f[3] as f32 / 32.,
                f[4] as f32 / 2.,
                f[5] as f32 / 16.,
                f[6] as f32 / 32.,
                f[7] as f32 / 16.,
            ];
            let mut score = w[736 + l];
            let mut k = [0f32; 8];
            for i in 0..6 {
                score += w[768 + i] * x[i];
            }
            for i in 0..8 {
                let mut value = w[360 + (l + 1) * 8 + i] + w[624 + rank * 8 + i];
                for c in 0..6 {
                    value += w[688 + i * 6 + c] * x[c];
                }
                k[i] = value.tanh();
                score += state[i] * k[i];
            }
            if score > best {
                best = score;
                winner = Some(n);
                keys = k;
            }
        }
        for i in 0..8 {
            token[i] = (state[i] + keys[i]).tanh();
        }
        let mut join = None;
        let mut suffix = [0f32; 8];
        if let Some(n) = winner {
            let leaf = obs[n][0] as usize / 8;
            let rank = obs[n][0] as usize % 8;
            token[8] = (leaf + 1) as f32;
            token[9] = (obs[n][1] + 1) as f32;
            token[10] = (rank + 1) as f32;
            token[11] = 1.;
            let mut best = h[19 * jcount + lane];
            for (i, j) in self.p.joins.iter().enumerate() {
                if j[1] != leaf || self.p.entries[j[3]][0] < 0 {
                    continue;
                }
                let mut score = h[8 * jcount + i] + h[9 * jcount + lane * jcount + i];
                for x in 0..8 {
                    score += h[i * 8 + x] * token[x];
                }
                if score > best {
                    best = score;
                    join = Some(i);
                }
            }
            for r in 0..8 {
                let base = 19 * jcount + 2;
                let mut score = h[base + 64 + (leaf * 8 + rank) * 8 + r];
                for x in 0..8 {
                    score += h[base + r * 8 + x] * token[x];
                }
                suffix[r] = score;
            }
        }
        for i in 0..8 {
            token[i] = (token[i] + join.map_or(0., |j| h[11 * jcount + 8 * j + i])).tanh();
        }
        (token, winner, join.map(|j| self.p.joins[j][0]), suffix)
    }
    pub(crate) fn verify_raw(
        &mut self,
        id: usize,
        g: &Graph,
        rid: usize,
        facts: &QueryFacts,
        watermark: u64,
    ) -> Result<Option<Matched>> {
        let claim = self.raw(id).expect("raw claim");
        let rule = &g.program.rules[rid];
        let mut env = BTreeMap::new();
        let mut epoch = 0;
        let mut accepted = claim.rows.len() == rule.query.len();
        for &(pos, w) in &claim.rows {
            let Some(r) = g.row(w)? else {
                accepted = false;
                break;
            };
            let a = &rule.query[pos];
            if r.hidden
                || !matches!(a.call,Call::Table(t) if t==r.table)
                || !a
                    .args
                    .iter()
                    .zip(r.values.iter())
                    .all(|(a, v)| bind_query(a, v, &mut env, g))
            {
                accepted = false;
                break;
            }
            epoch = epoch.max(r.epoch);
        }
        if accepted
            && epoch >= watermark
            && rule
                .inputs
                .iter()
                .all(|s| env.get(s).is_some_and(|v| Some(v) == claim.values.get(s)))
        {
            Ok(Some(Matched::matched(
                claim.values.clone(),
                facts.with_rows(claim.rows.iter().copied()),
                epoch,
            )))
        } else {
            self.raw_rejections += 1;
            Ok(None)
        }
    }
    pub(crate) fn report(&self) -> Json {
        let records = self
            .issued
            .iter()
            .map(|v| {
                json!([
                    v.epoch,
                    v.lane,
                    v.leaf,
                    v.code,
                    v.address,
                    v.suffix_rank,
                    v.root_ordinal,
                    v.child_ordinal,
                    v.child_epoch,
                    v.root_verified,
                    v.child_verified
                ])
            })
            .collect::<Vec<_>>();
        let raw: Vec<_> = if self.observe {
            self.issued
                .iter()
                .enumerate()
                .filter_map(|(id, v)| v.raw.as_ref().map(|r| json!([id, r.rows, r.values])))
                .collect()
        } else {
            vec![]
        };
        let provenance: Vec<_> = self
            .issued
            .iter()
            .enumerate()
            .filter(|(_, v)| v.child_ordinal > 0)
            .map(|(id, v)| json!([id, v.anchor, v.produced]))
            .collect();
        json!({"handoffs":self.transfers,"handoff_scores":self.handoff_scores,"idle_slots":self.idle_slots,"issued":records,"raw_payloads":raw,"provenance":provenance,"actions_scored":self.scored,"point_reads":self.point_reads,"kind":format!("{:?}",self.kind),"residual":self.residual,"source_runs":self.at_boundary,
               "root_attempts":self.root_attempts,"child_attempts":self.child_attempts,"raw_rejections":self.raw_rejections,
               "explicit_fields":self.raw_field_count,"rhs":self.ordinal,"observations":self.observations})
    }
}
