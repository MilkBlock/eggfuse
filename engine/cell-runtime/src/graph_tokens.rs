//! A signed instruction DAG advances on the same sealed Run boundaries as its source rules.
use super::{Address, PortObservation, Premise, Request};
use crate::program::{Call, Op, Program, Result};
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
}

struct Plan {
    steps: Layout,
    groups: Vec<std::ops::Range<usize>>,
    boundary: Vec<usize>,
    exports: Vec<BTreeSet<usize>>,
}

impl Plan {
    fn compile(program: &Program, steps: Layout) -> Result<Self> {
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
                    let producer = &program.rules[steps[owner].0];
                    let output = program.templates[producer.template].ops.get(slot);
                    if !matches!(output,Some(Op::Let(_,Call::Table(t),_) | Op::Set(t,_,_)) if *t==table)
                    {
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
    boundary_reads: usize,
    issued_steps: usize,
    accepted_steps: usize,
    rejected_groups: usize,
    missing_returns: usize,
    issued_layouts: BTreeMap<usize, usize>,
    completed_layouts: BTreeMap<usize, usize>,
    completed_sizes: BTreeMap<usize, usize>,
}

pub(super) struct Receiver {
    plans: Vec<Plan>,
    instances: Vec<Instance>,
    next: i64,
    counts: Counts,
}

type Queue = BTreeMap<(usize, usize), Vec<Request>>;

impl Receiver {
    pub fn new(program: &Program, layouts: Vec<Layout>) -> Result<Self> {
        let plans = layouts
            .into_iter()
            .map(|layout| Plan::compile(program, layout))
            .collect::<Result<_>>()?;
        Ok(Self {
            plans,
            instances: vec![],
            next: super::higher::INTERNAL,
            counts: Counts::default(),
        })
    }
    pub fn report(&self) -> serde_json::Value {
        serde_json::json!({"counts":self.counts,"outstanding":self.instances.len()})
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
    ) -> Result<()> {
        let Some(cert) = req.graph.take() else {
            return Ok(());
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
                return Ok(());
            }
        }
        let mut inst = Instance {
            layout: cert.layout,
            group: 0,
            boundary: cert.boundary,
            sent: vec![(0, req.token)],
            returns: BTreeMap::new(),
        };
        for step in plan.groups[0].clone().skip(1) {
            Self::emit(plan, &mut inst, step, req.run, &mut self.next, queue)?;
            self.counts.issued_steps += 1;
        }
        *self.counts.issued_layouts.entry(inst.layout).or_default() += 1;
        self.instances.push(inst);
        Ok(())
    }
    pub fn advance(
        &mut self,
        visible: &BTreeMap<Address, PortObservation>,
        accepted: &[Request],
        run: usize,
        rules: &[(usize, u64)],
        queue: &mut Queue,
    ) -> Result<()> {
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
                        let Some(row) = visible.get(&address) else {
                            self.counts.missing_returns += 1;
                            continue 'instance;
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
            state.advance(&rows, &accepted, 2, &[], &mut queue).unwrap();
            rows.get_mut(&Address { token: 8, op: 1 }).unwrap().version = 8;
            state.advance(&rows, &[], 3, &[(2, 0)], &mut queue).unwrap();
            if peer_ok {
                let child = queue.remove(&(3, 2)).unwrap().pop().unwrap();
                assert_eq!(
                    child.parents.iter().map(|p| p.version).collect::<Vec<_>>(),
                    [2, 1, 3]
                );
                state.advance(&rows, &[child], 4, &[], &mut queue).unwrap();
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
}
