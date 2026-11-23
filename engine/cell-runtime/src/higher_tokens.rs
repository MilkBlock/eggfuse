//! Static suffixes for an explicitly issued composite token.
use super::{Address, Premise, Request};
use crate::program::{Call, Op, Program, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub(super) const INTERNAL: i64 = 1 << 61;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Recipe {
    pub root: usize,
    /// (actual return PC of previous step, consumer rule)
    pub hops: Vec<(usize, usize)>,
    /// Final internal pivot role and externally named side table.
    #[serde(default)]
    pub side: Option<(usize, usize)>,
}

#[derive(Default, Serialize)]
pub struct Counts {
    pub issued_roots: usize,
    pub accepted_roots: usize,
    pub missing_exports: usize,
    pub issued_steps: usize,
    pub accepted_steps: usize,
    pub side_reads_at_issue: usize,
    pub side_invalid_at_issue: usize,
    pub side_steps_issued: usize,
    pub side_watermark_skips: usize,
    pub forks_issued: usize,
    pub forks_accepted: usize,
    pub side_steps_accepted: usize,
    pub side_verdicts: BTreeMap<&'static str, usize>,
    pub by_depth: BTreeMap<usize, usize>,
}

pub(super) struct Higher {
    recipes: Vec<Recipe>,
    seminaive_sides: BTreeSet<usize>,
    // Accepted steps acquire their result version at the first sealed boundary.
    capture: Vec<(i64, usize, usize, Option<Premise>)>,
    waiting: BTreeMap<usize, Vec<(Premise, usize, usize, Option<Premise>)>>,
    next: i64,
    pub counts: Counts,
}

impl Higher {
    pub fn new(program: &Program, recipes: Vec<Recipe>) -> Result<Self> {
        let mut seminaive_sides = BTreeSet::new();
        for recipe in &recipes {
            let mut prior = recipe.root;
            if recipe.hops.is_empty() {
                return Err("empty higher token".into());
            }
            for (index, &(pc, child)) in recipe.hops.iter().enumerate() {
                let producer = program.rules.get(prior).ok_or("invalid producer rule")?;
                let ops = &program.templates[producer.template].ops;
                let table = match ops.get(pc) {
                    Some(Op::Let(_, Call::Table(t), _)) | Some(Op::Set(t, _, _)) => *t,
                    _ => return Err("higher edge needs a returned table port".into()),
                };
                let rule = program.rules.get(child).ok_or("invalid child rule")?;
                let inputs: Vec<_> = rule
                    .query
                    .iter()
                    .filter_map(|a| match a.call {
                        Call::Table(t) => Some(t),
                        _ => None,
                    })
                    .collect();
                let valid = match recipe.side.filter(|_| index + 1 == recipe.hops.len()) {
                    Some((pivot, side)) => {
                        if rule.seminaive {
                            seminaive_sides.insert(child);
                        }
                        pivot < 2
                            && inputs.len() == 2
                            && inputs[pivot] == table
                            && inputs[1 - pivot] == side
                    }
                    None => inputs == [table],
                };
                if !valid {
                    return Err(
                        "higher edge leaves an independent parent or disagrees on type".into(),
                    );
                }
                prior = child;
            }
        }
        Ok(Self {
            recipes,
            seminaive_sides,
            capture: vec![],
            waiting: BTreeMap::new(),
            next: INTERNAL,
            counts: Counts::default(),
        })
    }
    pub fn issue(
        &mut self,
        req: &mut Request,
        visible: &BTreeMap<Address, super::PortObservation>,
    ) -> Result<()> {
        if let Some(branch) = req.closed_branch {
            let closed = self.recipes.get(branch).ok_or("unknown closed branch")?;
            if closed.root != req.rule
                || closed.side.is_some()
                || req.side.is_none()
                || req.unit == Some(branch)
                || req.unit.is_none()
            {
                return Err("invalid signed fork".into());
            }
            self.counts.forks_issued += 1;
        }
        if let Some(unit) = req.unit {
            if self.recipes.get(unit).map(|r| r.root) != Some(req.rule) {
                return Err("higher template does not start at requested rule".into());
            }
            self.counts.issued_roots += 1;
            match (self.recipes[unit].side, &req.side) {
                (None, None) => (),
                (Some((_, table)), Some(side)) => {
                    self.counts.side_reads_at_issue += 1;
                    if !visible
                        .get(&side.address)
                        .is_some_and(|p| p.table == table && p.version == side.version)
                    {
                        self.counts.side_invalid_at_issue += 1;
                        req.unit = req.closed_branch.take();
                        req.side = None;
                    }
                }
                _ => return Err("higher root has incorrect side arity".into()),
            }
        }
        if req.unit.is_none() && req.side.is_some() {
            return Err("unexpected standalone side".into());
        }
        Ok(())
    }
    pub fn verdict(&mut self, req: &Request, reason: &'static str) {
        if let Some(recipe) = req.unit.map(|i| &self.recipes[i])
            && req.step == recipe.hops.len()
            && recipe.side.is_some()
        {
            *self.counts.side_verdicts.entry(reason).or_default() += 1;
        }
    }
    pub fn accepted(&mut self, req: &Request) {
        if let Some(unit) = req.unit {
            if req.step == 0 {
                self.counts.accepted_roots += 1;
                if let Some(branch) = req.closed_branch {
                    self.counts.forks_accepted += 1;
                    self.capture.push((req.token, branch, 0, None));
                }
            } else {
                self.counts.accepted_steps += 1;
                if req.step == self.recipes[unit].hops.len() && self.recipes[unit].side.is_some() {
                    self.counts.side_steps_accepted += 1;
                }
                *self.counts.by_depth.entry(req.step + 1).or_default() += 1;
            }
            if req.step < self.recipes[unit].hops.len() {
                self.capture
                    .push((req.token, unit, req.step, req.side.clone()));
            }
        }
    }
    pub fn remaining(&self) -> usize {
        self.capture.len() + self.waiting.values().map(Vec::len).sum::<usize>()
    }
    pub fn dispatch(
        &mut self,
        visible: &BTreeMap<Address, super::PortObservation>,
        run: usize,
        rules: &[(usize, u64)],
        queue: &mut BTreeMap<(usize, usize), Vec<Request>>,
    ) -> Result<()> {
        for (token, unit, index, side) in self.capture.drain(..) {
            let (op, child) = self.recipes[unit].hops[index];
            let address = Address { token, op };
            if let Some(row) = visible.get(&address) {
                self.waiting.entry(child).or_default().push((
                    Premise {
                        address,
                        version: row.version,
                    },
                    unit,
                    index + 1,
                    side,
                ));
            } else {
                self.counts.missing_exports += 1;
            }
        }
        for &(rule, watermark) in rules {
            for (parent, unit, step, mut side) in self.waiting.remove(&rule).unwrap_or_default() {
                if self.next >= i64::MAX / 2 {
                    return Err("higher token namespace exhausted".into());
                }
                let token = self.next;
                self.next += 1;
                let mut parents = vec![parent];
                if let Some((pivot, _)) = self.recipes[unit]
                    .side
                    .filter(|_| step == self.recipes[unit].hops.len())
                {
                    let external = side.take().ok_or("missing signed side")?;
                    // bind_named requires both versions unchanged. Even a still-live pair
                    // cannot supply a delta witness below the child's own watermark.
                    if self.seminaive_sides.contains(&rule)
                        && parents[0].version.max(external.version) < watermark
                    {
                        self.counts.side_watermark_skips += 1;
                        continue;
                    }
                    parents.insert(1 - pivot, external);
                    self.counts.side_steps_issued += 1;
                }
                queue.entry((run, rule)).or_default().push(Request {
                    token,
                    closed_branch: None,
                    graph: None,
                    run,
                    rule,
                    parents,
                    side,
                    unit: Some(unit),
                    step,
                });
                self.counts.issued_steps += 1;
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cell_tokens::PortObservation;

    #[test]
    fn delayed_consumer_verifies_the_first_sealed_version_and_never_retries_a_failed_step() {
        let mut state = Higher {
            seminaive_sides: BTreeSet::new(),
            recipes: vec![Recipe {
                root: 3,
                side: None,
                hops: vec![(2, 5), (0, 9)],
            }],
            capture: vec![],
            waiting: BTreeMap::new(),
            next: INTERNAL,
            counts: Counts::default(),
        };
        let mut root = Request {
            token: 4,
            closed_branch: None,
            graph: None,
            side: None,
            run: 1,
            rule: 3,
            parents: vec![],
            unit: Some(0),
            step: 0,
        };
        state.issue(&mut root, &BTreeMap::new()).unwrap();
        state.accepted(&root);
        root.token += 1;
        state.accepted(&root);
        let address = Address { token: 4, op: 2 };
        let mut rows = BTreeMap::from([(
            address,
            PortObservation {
                table: 1,
                version: 1,
                forwarded: false,
                hashes: vec![],
            },
        )]);
        let mut queue = BTreeMap::new();
        state.dispatch(&rows, 2, &[], &mut queue).unwrap();
        assert!(queue.is_empty());
        assert_eq!(state.counts.missing_exports, 1);
        rows.get_mut(&address).unwrap().version = 2;
        state.dispatch(&rows, 3, &[(5, 1)], &mut queue).unwrap();
        let child = &queue[&(3, 5)][0];
        assert_eq!(child.parents[0].version, 1);
        assert_eq!(child.parents[0].address, address);
        assert_eq!(child.token, INTERNAL);
        state
            .dispatch(&rows, 4, &[(5, 2), (9, 1)], &mut queue)
            .unwrap();
        assert_eq!(state.remaining(), 0);
        assert_eq!(queue.len(), 1);
        root.rule = 5;
        assert!(state.issue(&mut root, &BTreeMap::new()).is_err());
    }
    #[test]
    fn a_fork_freezes_its_side_at_the_root_and_keeps_the_other_branch_on_failure() {
        for (pivot, wm, sem) in [(0, 3, true), (1, 4, true), (1, 4, false)] {
            let mut state = Higher {
                seminaive_sides: if sem {
                    BTreeSet::from([5])
                } else {
                    BTreeSet::new()
                },
                recipes: vec![
                    Recipe {
                        root: 3,
                        hops: vec![(1, 4), (2, 5)],
                        side: Some((pivot, 8)),
                    },
                    Recipe {
                        root: 3,
                        hops: vec![(1, 6)],
                        side: None,
                    },
                ],
                capture: vec![],
                waiting: BTreeMap::new(),
                next: INTERNAL,
                counts: Counts::default(),
            };
            let side = Premise {
                address: Address { token: 7, op: 1 },
                version: 1,
            };
            let row = |table, version| PortObservation {
                table,
                version,
                forwarded: false,
                hashes: vec![],
            };
            let mut visible = BTreeMap::from([(side.address, row(8, 1))]);
            let mut root = Request {
                token: 8,
                run: 1,
                rule: 3,
                parents: vec![],
                unit: Some(0),
                step: 0,
                side: Some(side.clone()),
                closed_branch: Some(1),
                graph: None,
            };
            state.issue(&mut root, &visible).unwrap();
            state.accepted(&root);
            visible.insert(Address { token: 8, op: 1 }, row(9, 2));
            let mut queue = BTreeMap::new();
            state
                .dispatch(&visible, 2, &[(4, 0), (6, 0)], &mut queue)
                .unwrap();
            let mid = &queue[&(2, 4)][0];
            assert_eq!(mid.parents.len(), 1);
            assert!(queue[&(2, 6)][0].side.is_none());
            state.accepted(mid);
            visible.insert(
                Address {
                    token: mid.token,
                    op: 2,
                },
                row(9, 3),
            );
            visible.insert(side.address, row(8, 3));
            state.dispatch(&visible, 3, &[(5, wm)], &mut queue).unwrap();
            if sem && wm > 3 {
                assert!(!queue.contains_key(&(3, 5)));
                assert_eq!(state.counts.side_watermark_skips, 1);
                continue;
            }
            let child = &queue[&(3, 5)][0];
            assert_eq!(child.parents[1 - pivot].address, side.address);
            assert_eq!(child.parents[1 - pivot].version, 1);
            assert_eq!(child.parents[pivot].version, 3);
            assert_eq!(state.counts.side_steps_issued, 1);
            state.issue(&mut root, &visible).unwrap();
            assert_eq!(root.unit, Some(1));
            assert!(root.side.is_none() && root.closed_branch.is_none());
            assert_eq!(state.counts.side_invalid_at_issue, 1);
        }
    }
}
