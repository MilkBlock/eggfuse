//! Static, single-source suffixes for an explicitly issued composite token.
use super::{Address, Premise, Request};
use crate::program::{Call, Op, Program, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub(super) const INTERNAL: i64 = 1 << 61;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Recipe {
    pub root: usize,
    /// (actual return PC of previous step, consumer rule)
    pub hops: Vec<(usize, usize)>,
}

#[derive(Default, Serialize)]
pub struct Counts {
    pub issued_roots: usize,
    pub accepted_roots: usize,
    pub missing_exports: usize,
    pub issued_steps: usize,
    pub accepted_steps: usize,
    pub by_depth: BTreeMap<usize, usize>,
}

pub(super) struct Higher {
    recipes: Vec<Recipe>,
    // Accepted steps acquire their result version at the first sealed boundary.
    capture: Vec<(i64, usize, usize)>,
    waiting: BTreeMap<usize, Vec<(Premise, usize, usize)>>,
    next: i64,
    pub counts: Counts,
}

impl Higher {
    pub fn new(program: &Program, recipes: Vec<Recipe>) -> Result<Self> {
        for recipe in &recipes {
            let mut prior = recipe.root;
            if recipe.hops.is_empty() {
                return Err("empty higher token".into());
            }
            for &(pc, child) in &recipe.hops {
                let producer = program.rules.get(prior).ok_or("invalid producer rule")?;
                let ops = &program.templates[producer.template].ops;
                let table = match ops.get(pc) {
                    Some(Op::Let(_, Call::Table(t), _)) | Some(Op::Set(t, _, _)) => *t,
                    _ => return Err("higher edge needs a returned table port".into()),
                };
                let rule = program.rules.get(child).ok_or("invalid child rule")?;
                let mut inputs = rule.query.iter().filter_map(|a| match a.call {
                    Call::Table(t) => Some(t),
                    _ => None,
                });
                if inputs.next() != Some(table) || inputs.next().is_some() {
                    return Err(
                        "higher edge leaves an independent parent or disagrees on type".into(),
                    );
                }
                prior = child;
            }
        }
        Ok(Self {
            recipes,
            capture: vec![],
            waiting: BTreeMap::new(),
            next: INTERNAL,
            counts: Counts::default(),
        })
    }
    pub fn issue(&mut self, req: &Request) -> Result<()> {
        if let Some(unit) = req.unit {
            if self.recipes.get(unit).map(|r| r.root) != Some(req.rule) {
                return Err("higher template does not start at requested rule".into());
            }
            self.counts.issued_roots += 1;
        }
        Ok(())
    }
    pub fn accepted(&mut self, req: &Request) {
        if let Some(unit) = req.unit {
            if req.step == 0 {
                self.counts.accepted_roots += 1;
            } else {
                self.counts.accepted_steps += 1;
                *self.counts.by_depth.entry(req.step + 1).or_default() += 1;
            }
            if req.step < self.recipes[unit].hops.len() {
                self.capture.push((req.token, unit, req.step));
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
        for (token, unit, index) in self.capture.drain(..) {
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
                ));
            } else {
                self.counts.missing_exports += 1;
            }
        }
        for &(rule, _) in rules {
            for (parent, unit, step) in self.waiting.remove(&rule).unwrap_or_default() {
                if self.next >= i64::MAX / 2 {
                    return Err("higher token namespace exhausted".into());
                }
                queue.entry((run, rule)).or_default().push(Request {
                    token: self.next,
                    run,
                    rule,
                    parents: vec![parent],
                    unit: Some(unit),
                    step,
                });
                self.next += 1;
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
            recipes: vec![Recipe {
                root: 3,
                hops: vec![(2, 5), (0, 9)],
            }],
            capture: vec![],
            waiting: BTreeMap::new(),
            next: INTERNAL,
            counts: Counts::default(),
        };
        let mut root = Request {
            token: 4,
            run: 1,
            rule: 3,
            parents: vec![],
            unit: Some(0),
            step: 0,
        };
        state.issue(&root).unwrap();
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
        assert!(state.issue(&root).is_err());
    }
}
