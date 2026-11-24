//! A signed instruction DAG advances on the same sealed Run boundaries as its source rules.
use super::{Address, PortObservation, Premise, Request};
use crate::program::{Call, Program, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

/// Rule, relative source Run group, and one source per table atom.
/// Source (-1, slot) names the external boundary. Other sources name earlier returns.
pub type Layout = Vec<(usize, usize, Vec<(i64, usize)>)>;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Certificate {
    pub layout: usize,
    pub boundary: Vec<Premise>,
    /// An already signed internal step at this sealed boundary.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub owner: Option<i64>,
}

struct Plan {
    steps: Layout,
    groups: Vec<std::ops::Range<usize>>,
    boundary: Vec<usize>,
    exports: Vec<BTreeSet<usize>>,
}

impl Plan {
    fn compile(program: &Program, steps: Layout, returns: &[crate::receipt_contract::Returns]) -> Result<Self> {
        if steps.len() < 2 {
            return Err("a composite layout requires at least two steps".into());
        }
        let mut groups: Vec<std::ops::Range<usize>> = vec![];
        let mut boundary = vec![];
        let mut exports = vec![BTreeSet::new(); steps.len()];
        for (i, (rid, group, inputs)) in steps.iter().enumerate() {
            if *group == groups.len() {
                groups.push(i..i + 1);
            } else if group.checked_add(1) == Some(groups.len()) {
                groups[*group].end = i + 1;
            } else {
                return Err("out-of-order layout group".into());
            }
            let rule = program.rules.get(*rid).ok_or("unknown layout rule")?;
            let tables: Vec<_> = rule
                .query
                .iter()
                .filter_map(|atom| match atom.call {
                    Call::Table(t) => Some(t),
                    _ => None,
                })
                .collect();
            if inputs.len() != tables.len() {
                return Err("incomplete layout inputs".into());
            }
            for (&(source, slot), table) in inputs.iter().zip(tables) {
                if source == -1 {
                    if slot == boundary.len() {
                        boundary.push(table);
                    }
                    if boundary.get(slot) != Some(&table) {
                        return Err("invalid or inconsistent boundary type".into());
                    }
                } else {
                    let owner = usize::try_from(source).map_err(|_| "invalid layout source")?;
                    if owner >= i || steps[owner].1 >= *group {
                        return Err("layout reads an unsealed result".into());
                    }
                    if returns[steps[owner].0].tables.get(&slot) != Some(&table) {
                        return Err("invalid layout return type".into());
                    }
                    exports[owner].insert(slot);
                }
            }
        }
        Ok(Self {
            steps,
            groups,
            boundary,
            exports,
        })
    }
    fn scheduled(&self, group: usize, rules: &[(usize, u64)]) -> bool {
        self.groups[group]
            .clone()
            .all(|step| rules.iter().any(|&(r, _)| r == self.steps[step].0))
    }
}

struct Instance {
    root: i64,
    layout: usize,
    group: usize,
    boundary: Vec<Premise>,
    sent: Vec<(usize, i64)>,
    returns: BTreeMap<(usize, usize), Premise>,
}

#[derive(Default, Serialize)]
struct Counts {
    signed_layouts: usize,
    invalid_boundary: usize,
    attached_roots: usize,
    boundary_reads: usize,
    issued_steps: usize,
    accepted_steps: usize,
    rejected_groups: usize,
    missing_returns: usize,
    absent_returns: usize,
    retired_returns: usize,
    issued_layouts: BTreeMap<usize, usize>,
    completed_layouts: BTreeMap<usize, usize>,
    completed_sizes: BTreeMap<usize, usize>,
}

pub(super) struct Receiver {
    plans: Vec<Plan>,
    instances: Vec<Instance>,
    next: i64,
    /// Only enabled for ownership feedback. Entries live for one source Run.
    feedback: bool,
    origins: BTreeMap<i64, i64>,
    advertised: BTreeMap<i64, (usize, usize)>,
    outcomes: Vec<(i64, i64, &'static str)>,
    counts: Counts,
}

type Queue = BTreeMap<(usize, usize), Vec<Request>>;

impl Receiver {
    pub fn new(program: &Program, layouts: Vec<Layout>) -> Result<Self> {
        let returns = (0..program.rules.len())
            .map(|rid| crate::receipt_contract::Returns::rule(program, rid)).collect::<Vec<_>>();
        let plans = layouts
            .into_iter()
            .map(|layout| Plan::compile(program, layout, &returns))
            .collect::<Result<_>>()?;
        Ok(Self {
            plans,
            instances: vec![],
            feedback: false,
            origins: BTreeMap::new(),
            advertised: BTreeMap::new(),
            outcomes: Vec::new(),
            next: super::higher::INTERNAL,
            counts: Counts::default(),
        })
    }
    pub fn report(&self) -> serde_json::Value {
        serde_json::json!({"counts":self.counts,"outstanding":self.instances.len()})
    }
    pub fn enable_feedback(&mut self) {
        self.feedback = true;
    }

    pub fn completed_step(&mut self, token: i64, verdict: &'static str) {
        if self.feedback {
            if let Some(&root) = self.origins.get(&token) {
                self.outcomes.push((root, token, verdict));
            }
        }
    }

    pub fn snapshot(&mut self, run: usize, queue: &Queue) -> Option<serde_json::Value> {
        if !self.feedback {
            return None;
        }
        // These requests have already been signed. No lookup of candidate facts occurs here.
        self.advertised.clear();
        let mut claims = vec![];
        for (&(_, rule), requests) in queue.range((run, 0)..=(run, usize::MAX)) {
            for (index, r) in requests.iter().enumerate() {
                if let Some(root) = self.origins.get(&r.token) {
                    self.advertised.insert(r.token, (rule, index));
                    claims.push((root, r.token, rule, &r.parents));
                }
            }
        }
        Some(serde_json::json!({"claims":claims,"outcomes":std::mem::take(&mut self.outcomes)}))
    }
    fn emit(
        plan: &Plan,
        inst: &mut Instance,
        step: usize,
        run: usize,
        next: &mut i64,
        queue: &mut Queue,
    ) -> Result<()> {
        let (rule, _, wires) = &plan.steps[step];
        let parents = wires
            .iter()
            .map(|&(src, pos)| {
                if src == -1 {
                    Ok(inst.boundary[pos].clone())
                } else {
                    inst.returns
                        .get(&(src as usize, pos))
                        .cloned()
                        .ok_or("missing signed return".into())
                }
            })
            .collect::<Result<_>>()?;
        let token = *next;
        if token >= i64::MAX / 2 {
            return Err("exhausted internal token ids".into());
        }
        *next += 1;
        inst.sent.push((step, token));
        queue.entry((run, *rule)).or_default().push(Request {
            rule: *rule,
            run,
            token,
            parents,
            graph: None,
            side: None,
            unit: None,
            closed_branch: None,
            step: 0,
        });
        Ok(())
    }
    pub fn issue(
        &mut self,
        req: &mut Request,
        visible: &BTreeMap<Address, PortObservation>,
        rules: &[(usize, u64)],
        queue: &mut Queue,
    ) -> Result<bool> {
        let Some(cert) = req.graph.take() else {
            return Ok(false);
        };
        let plan = self
            .plans
            .get(cert.layout)
            .ok_or("unknown signed graph layout")?;
        if plan.steps[0].0 != req.rule
            || cert.boundary.len() != plan.boundary.len()
            || !plan.scheduled(0, rules)
            || req.parents.len() != plan.steps[0].2.len()
        {
            return Err("malformed signed graph root".into());
        }
        for (ref_, &(_, slot)) in req.parents.iter().zip(&plan.steps[0].2) {
            if ref_.address != cert.boundary[slot].address
                || ref_.version != cert.boundary[slot].version
            {
                return Err("root differs from signed graph boundary".into());
            }
        }
        self.counts.signed_layouts += 1;
        for (premise, table) in cert.boundary.iter().zip(&plan.boundary) {
            self.counts.boundary_reads += 1;
            if !visible
                .get(&premise.address)
                .is_some_and(|p| p.table == *table && p.version == premise.version)
            {
                self.counts.invalid_boundary += 1;
                return Ok(false);
            }
        }
        if let Some(owner) = cert.owner {
            let (rid, index) = self
                .advertised
                .get(&owner)
                .copied()
                .ok_or("unadvertised layout owner")?;
            let signed = queue
                .get(&(req.run, rid))
                .and_then(|q| q.get(index))
                .ok_or("expired layout owner")?;
            if rid != req.rule || signed.token != owner || signed.parents != req.parents {
                return Err("layout owner names different premises".into());
            }
            self.counts.attached_roots += 1;
            self.outcomes
                .push((self.origins[&owner], owner, "external_alternative"));
        }
        let mut inst = Instance {
            root: req.token,
            layout: cert.layout,
            group: 0,
            boundary: cert.boundary,
            sent: vec![(0, cert.owner.unwrap_or(req.token))],
            returns: BTreeMap::new(),
        };
        for step in plan.groups[0].clone().skip(1) {
            if self.feedback {
                self.origins.insert(self.next, inst.root);
            }
            Self::emit(plan, &mut inst, step, req.run, &mut self.next, queue)?;
            self.counts.issued_steps += 1;
        }
        *self.counts.issued_layouts.entry(inst.layout).or_default() += 1;
        self.instances.push(inst);
        Ok(cert.owner.is_some())
    }
    pub fn advance(
        &mut self,
        visible: &BTreeMap<Address, PortObservation>,
        returned: impl Fn(&Address) -> bool,
        accepted: &[Request],
        run: usize,
        rules: &[(usize, u64)],
        queue: &mut Queue,
    ) -> Result<()> {
        self.origins.clear();
        if self.instances.is_empty() {
            return Ok(());
        }
        let accepted: BTreeSet<_> = accepted.iter().map(|r| r.token).collect();
        let mut keep = Vec::with_capacity(self.instances.len());
        'instance: for mut inst in self.instances.drain(..) {
            let plan = &self.plans[inst.layout];
            if !inst.sent.is_empty() {
                self.counts.accepted_steps += inst
                    .sent
                    .iter()
                    .filter(|(i, t)| *i != 0 && accepted.contains(t))
                    .count();
                if inst.sent.iter().any(|(_, t)| !accepted.contains(t)) {
                    self.counts.rejected_groups += 1;
                    continue;
                }
                inst.group += 1;
                if inst.group == plan.groups.len() {
                    *self
                        .counts
                        .completed_layouts
                        .entry(inst.layout)
                        .or_default() += 1;
                    *self
                        .counts
                        .completed_sizes
                        .entry(plan.steps.len())
                        .or_default() += 1;
                    continue;
                }
                for (step, token) in inst.sent.drain(..) {
                    for &op in &plan.exports[step] {
                        let address = Address { token, op };
                        use crate::receipt_contract::{port_state, PortState};
                        let row = match port_state(true, visible.get(&address), || returned(&address)) {
                            PortState::Available(row) => row,
                            PortState::Absent => {
                                self.counts.absent_returns += 1;
                                self.counts.missing_returns += 1;
                                continue 'instance;
                            }
                            PortState::Retired => {
                                self.counts.retired_returns += 1;
                                self.counts.missing_returns += 1;
                                continue 'instance;
                            }
                            PortState::Pending => unreachable!("step already published"),
                        };
                        inst.returns.insert(
                            (step, op),
                            Premise {
                                address,
                                version: row.version,
                            },
                        );
                    }
                }
            }
            if plan.scheduled(inst.group, rules) {
                for step in plan.groups[inst.group].clone() {
                    if self.feedback {
                        self.origins.insert(self.next, inst.root);
                    }
                    Self::emit(plan, &mut inst, step, run, &mut self.next, queue)?;
                    self.counts.issued_steps += 1;
                }
            }
            keep.push(inst);
        }
        self.instances = keep;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn root(version: u64) -> Request {
        let p = Premise {
            address: Address { token: 7, op: 0 },
            version,
        };
        Request {
            token: 8,
            run: 1,
            rule: 0,
            parents: vec![p.clone()],
            graph: Some(Certificate {
                layout: 0,
                owner: None,
                boundary: vec![p],
            }),
            unit: None,
            side: None,
            closed_branch: None,
            step: 0,
        }
    }
    fn receiver() -> Receiver {
        // Two independently checked first-group steps feed a three-input child.
        let plan = Plan {
            steps: vec![
                (0, 0, vec![(-1, 0)]),
                (1, 0, vec![(-1, 0)]),
                (2, 1, vec![(0, 1), (-1, 0), (1, 3)]),
            ],
            groups: vec![0..2, 2..3],
            boundary: vec![5],
            exports: vec![[1].into(), [3].into(), BTreeSet::new()],
        };
        Receiver {
            plans: vec![plan],
            instances: vec![],
            feedback: false,
            origins: BTreeMap::new(),
            advertised: BTreeMap::new(),
            outcomes: Vec::new(),
            next: super::super::higher::INTERNAL,
            counts: Counts::default(),
        }
    }
    fn row(table: usize, version: u64) -> PortObservation {
        PortObservation {
            table,
            version,
            forwarded: false,
            hashes: vec![],
        }
    }
    #[test]
    fn signed_dag_freezes_actual_join_inputs_and_retires_failed_group() {
        for peer_ok in [false, true] {
            let mut state = receiver();
            let mut rows = BTreeMap::from([(Address { token: 7, op: 0 }, row(5, 1))]);
            let mut base = root(1);
            let mut queue = Queue::new();
            state
                .issue(&mut base, &rows, &[(0, 0), (1, 0)], &mut queue)
                .unwrap();
            let peer = queue.remove(&(1, 1)).unwrap().pop().unwrap();
            let mut accepted = vec![base];
            rows.insert(Address { token: 8, op: 1 }, row(3, 2));
            rows.insert(
                Address {
                    token: peer.token,
                    op: 3,
                },
                row(3, 3),
            );
            if peer_ok {
                accepted.push(peer);
            }
            state.advance(&rows, |_| false, &accepted, 2, &[], &mut queue).unwrap();
            rows.get_mut(&Address { token: 8, op: 1 }).unwrap().version = 8;
            state.advance(&rows, |_| false, &[], 3, &[(2, 0)], &mut queue).unwrap();
            if peer_ok {
                let child = queue.remove(&(3, 2)).unwrap().pop().unwrap();
                assert_eq!(
                    child.parents.iter().map(|p| p.version).collect::<Vec<_>>(),
                    [2, 1, 3]
                );
                state.advance(&rows, |_| false, &[child], 4, &[], &mut queue).unwrap();
                assert_eq!(state.counts.completed_sizes[&3], 1);
            } else {
                assert!(queue.is_empty());
                assert_eq!(state.counts.rejected_groups, 1);
            }
            assert!(state.instances.is_empty());
        }
    }
    #[test]
    fn stale_external_slot_cannot_arm_a_certificate() {
        let mut r = receiver();
        let rows = BTreeMap::from([(Address { token: 7, op: 0 }, row(5, 2))]);
        let mut queue = Queue::new();
        r.issue(&mut root(1), &rows, &[(0, 0), (1, 0)], &mut queue)
            .unwrap();
        assert_eq!(r.counts.invalid_boundary, 1);
        assert!(queue.is_empty());
        assert!(r.instances.is_empty());
    }
    #[test]
    fn attached_graph_uses_the_actual_owners_return_and_keeps_its_own_credit() {
        let mut receiver = receiver();
        receiver.enable_feedback();
        receiver.plans = vec![Plan {
            steps: vec![(0, 0, vec![(-1, 0)]), (0, 1, vec![(0, 0)])],
            groups: vec![0..1, 1..2],
            boundary: vec![5],
            exports: vec![[0].into(), BTreeSet::new()],
        }];
        let mut queue = Queue::new();
        let mut first = root(1);
        let mut visible = BTreeMap::from([(first.parents[0].address, row(5, 1))]);
        assert!(
            !receiver
                .issue(&mut first, &visible, &[(0, 0)], &mut queue)
                .unwrap()
        );
        let returned = Address {
            token: first.token,
            op: 0,
        };
        visible.insert(returned, row(5, 2));
        receiver
            .advance(&visible, |_| false, &[first], 2, &[(0, 0)], &mut queue)
            .unwrap();
        let owner = queue[&(2, 0)][0].clone();
        receiver.snapshot(2, &queue);
        let mut wrong = root(1);
        wrong.token = 9;
        wrong.run = 2;
        wrong.graph.as_mut().unwrap().owner = Some(owner.token);
        assert!(
            receiver
                .issue(&mut wrong, &visible, &[(0, 0)], &mut queue)
                .is_err()
        );
        let mut extension = root(2);
        extension.token = 10;
        extension.run = 2;
        extension.parents = owner.parents.clone();
        extension.graph = Some(Certificate {
            layout: 0,
            boundary: owner.parents.clone(),
            owner: Some(owner.token),
        });
        assert!(
            receiver
                .issue(&mut extension, &visible, &[(0, 0)], &mut queue)
                .unwrap()
        );
        let actual = Address {
            token: owner.token,
            op: 0,
        };
        visible.insert(actual, row(5, 3));
        receiver.completed_step(owner.token, "accepted");
        receiver
            .advance(&visible, |_| false, &[owner], 3, &[(0, 0)], &mut queue)
            .unwrap();
        let next = &queue[&(3, 0)][0];
        assert_eq!(next.parents[0].address, actual);
        assert_eq!(next.parents[0].version, 3);
        assert_eq!(receiver.origins[&next.token], extension.token);
        assert_eq!(receiver.counts.attached_roots, 1);
        assert_eq!(receiver.counts.accepted_steps, 1);
    }
}
