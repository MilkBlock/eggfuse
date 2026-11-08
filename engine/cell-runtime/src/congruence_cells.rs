//! Immutable application/equality expressions and monotone completion cells.
//! The union directory supplies connectivity, never constructor congruence.
//! Candidate discovery joins equal argument ports; it does not enumerate all
//! application pairs of a table. Expressions survive source Run boundaries.
use super::*;
use std::collections::VecDeque;

type Pair = (u64, u64);
fn pair(a: u64, b: u64) -> Pair {
    (a.min(b), a.max(b))
}

#[derive(Serialize)]
struct Application {
    table: usize,
    fields: RowFields,
    shape: usize,
}
#[derive(Serialize)]
struct Equality {
    endpoints: Pair,
    satisfied: bool,
    // A proposal is not a satisfied input. Only committed connectivity wakes
    // consumers, so a recursive cell cannot justify its own missing premise.
    proposed: bool,
    #[serde(skip)]
    waiters: Vec<usize>,
}
#[derive(Serialize)]
struct Cell {
    applications: (usize, usize),
    ports: Vec<usize>,
    output: usize,
    remaining: usize,
    born: u64,
    completed: Option<u64>,
}
#[derive(Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum Proof {
    Source { equality: usize, epoch: u64 },
    Congruence { cell: usize, epoch: u64 },
}
#[derive(Default, Serialize)]
struct Stats {
    source_requests: u64,
    argument_pair_candidates: u64,
    repeated_cell_candidates: u64,
    equality_reuses: u64,
    waiting_cells_created: u64,
    completed_cells: u64,
    completed_across_runs: u64,
    equality_wakes: u64,
    waiter_visits: u64,
    output_proposals: u64,
    port_pairs_examined: u64,
}

#[derive(Default)]
pub(super) struct Expressions {
    applications: Vec<Application>,
    shapes: HashMap<(usize, Vec<Value>), usize>,
    // Class -> (typed scalar shape, argument column) -> immutable applications.
    ports: HashMap<u64, BTreeMap<(usize, usize), Vec<usize>>>,
    scalar_applications: HashMap<usize, Vec<usize>>,
    equalities: Vec<Equality>,
    equality_index: HashMap<Pair, usize>,
    watchers: HashMap<u64, BTreeSet<usize>>,
    cells: Vec<Cell>,
    cell_index: HashMap<(usize, usize), usize>,
    ready: VecDeque<(usize, bool)>,
    proofs: Vec<Proof>,
    stats: Stats,
}

impl Expressions {
    fn equality(&mut self, a: u64, b: u64, parents: &Parents) -> usize {
        let endpoints = pair(a, b);
        if let Some(&id) = self.equality_index.get(&endpoints) {
            self.stats.equality_reuses += 1;
            return id;
        }
        let id = self.equalities.len();
        let (a, b) = (root(parents, a), root(parents, b));
        self.equalities.push(Equality {
            endpoints,
            satisfied: a == b,
            proposed: false,
            waiters: vec![],
        });
        self.equality_index.insert(endpoints, id);
        if a != b {
            self.watchers.entry(a).or_default().insert(id);
            self.watchers.entry(b).or_default().insert(id);
        }
        id
    }

    fn propose(&mut self, id: usize, derived: bool) {
        let e = &mut self.equalities[id];
        if !e.satisfied && !e.proposed {
            e.proposed = true;
            self.ready.push_back((id, derived));
            self.stats.output_proposals += u64::from(derived);
        }
    }

    pub fn source(&mut self, a: u64, b: u64, parents: &Parents, epoch: u64) {
        self.stats.source_requests += 1;
        let id = self.equality(a, b, parents);
        self.proofs.push(Proof::Source {
            equality: id,
            epoch,
        });
        self.propose(id, false);
    }

    pub fn pop(&mut self) -> Option<(u64, u64, bool)> {
        let (id, derived) = self.ready.pop_front()?;
        let (a, b) = self.equalities[id].endpoints;
        Some((a, b, derived))
    }

    fn complete(&mut self, id: usize, epoch: u64) {
        let c = &mut self.cells[id];
        debug_assert_eq!(c.remaining, 0);
        debug_assert!(c.completed.is_none());
        c.completed = Some(epoch);
        self.stats.completed_cells += 1;
        self.stats.completed_across_runs += u64::from(c.born < epoch);
        let output = c.output;
        self.proofs.push(Proof::Congruence { cell: id, epoch });
        self.propose(output, true);
    }

    fn candidate(&mut self, a: usize, b: usize, parents: &Parents, epoch: u64) {
        if a == b {
            return;
        }
        self.stats.argument_pair_candidates += 1;
        let key = (a.min(b), a.max(b));
        if self.cell_index.contains_key(&key) {
            self.stats.repeated_cell_candidates += 1;
            return;
        }
        let left = self.applications[a].fields.clone();
        let right = self.applications[b].fields.clone();
        debug_assert_eq!(self.applications[a].shape, self.applications[b].shape);
        let mut ports = vec![];
        for (a, b) in left[..left.len() - 1].iter().zip(&right[..right.len() - 1]) {
            match (a, b) {
                (Value::Eq(a), Value::Eq(b)) => ports.push(self.equality(*a, *b, parents)),
                _ => debug_assert_eq!(a, b),
            }
        }
        let (Value::Eq(a), Value::Eq(b)) = (left.last().unwrap(), right.last().unwrap()) else {
            unreachable!("only constructors enter congruence expressions")
        };
        let output = self.equality(*a, *b, parents);
        let id = self.cells.len();
        let missing: BTreeSet<_> = ports
            .iter()
            .copied()
            .filter(|i| !self.equalities[*i].satisfied)
            .collect();
        for &input in &missing {
            self.equalities[input].waiters.push(id);
        }
        let remaining = missing.len();
        self.cells.push(Cell {
            applications: key,
            ports,
            output,
            remaining,
            born: epoch,
            completed: None,
        });
        self.cell_index.insert(key, id);
        if remaining == 0 {
            self.complete(id, epoch);
        } else {
            self.stats.waiting_cells_created += 1;
        }
    }

    pub fn application(&mut self, table: usize, fields: RowFields, parents: &Parents, epoch: u64) {
        let key = &fields[..fields.len() - 1];
        // Scalar literals remain exact; Eq(0) is only a typed shape hole.
        let skeleton = key
            .iter()
            .map(|v| match v {
                Value::Eq(_) => Value::Eq(0),
                _ => v.clone(),
            })
            .collect::<Vec<_>>();
        let next_shape = self.shapes.len();
        let shape = *self.shapes.entry((table, skeleton)).or_insert(next_shape);
        let id = self.applications.len();
        let args: Vec<_> = key
            .iter()
            .enumerate()
            .filter_map(|(col, v)| {
                if let Value::Eq(x) = v {
                    Some((col, root(parents, *x)))
                } else {
                    None
                }
            })
            .collect();
        self.applications.push(Application {
            table,
            fields,
            shape,
        });
        let mut candidates = BTreeSet::new();
        for &(col, x) in &args {
            let bucket = self
                .ports
                .entry(x)
                .or_default()
                .entry((shape, col))
                .or_default();
            self.stats.port_pairs_examined += bucket.len() as u64;
            candidates.extend(bucket.iter().copied());
            bucket.push(id);
        }
        if args.is_empty() {
            let bucket = self.scalar_applications.entry(shape).or_default();
            candidates.extend(bucket.iter().copied());
            bucket.push(id);
        }
        for other in candidates {
            self.candidate(id, other, parents, epoch);
        }
    }

    /// Connectivity was just committed. Wake equality nodes, then discover
    /// cells whose first shared argument port became available in this event.
    pub fn merged(&mut self, from: u64, to: u64, parents: &Parents, epoch: u64) {
        let watchers = self.watchers.remove(&from).unwrap_or_default();
        for id in watchers {
            self.stats.waiter_visits += 1;
            let e = &mut self.equalities[id];
            if e.satisfied {
                continue;
            }
            if root(parents, e.endpoints.0) == root(parents, e.endpoints.1) {
                e.satisfied = true;
                self.stats.equality_wakes += 1;
                let consumers = std::mem::take(&mut e.waiters);
                if let Some(ws) = self.watchers.get_mut(&to) {
                    ws.remove(&id);
                }
                for c in consumers {
                    self.cells[c].remaining -= 1;
                    if self.cells[c].remaining == 0 {
                        self.complete(c, epoch);
                    }
                }
            } else {
                self.watchers.entry(to).or_default().insert(id);
            }
        }
        let moved = self.ports.remove(&from).unwrap_or_default();
        for (port, mut apps) in moved {
            let old = self
                .ports
                .get(&to)
                .and_then(|p| p.get(&port))
                .cloned()
                .unwrap_or_default();
            for &a in &apps {
                for &b in &old {
                    self.stats.port_pairs_examined += 1;
                    self.candidate(a, b, parents, epoch);
                }
            }
            self.ports
                .entry(to)
                .or_default()
                .entry(port)
                .or_default()
                .append(&mut apps);
        }
    }

    pub fn report(&self) -> J {
        json!({"enabled": true, "applications": self.applications.len(),
            "scalar_shapes": self.shapes.len(), "argument_postings": self.argument_postings(),
            "equalities": self.equalities.len(), "cells": self.cells.len(),
            "waiting_cells": self.cells.iter().filter(|c| c.completed.is_none()).count(),
            "pending_proposals": self.ready.len(), "stats": self.stats,
            "scope": "immutable constructor expressions; explicit equality premises; source Run publication retained"})
    }

    pub fn argument_postings(&self) -> usize {
        self.ports
            .values()
            .flat_map(|p| p.values())
            .map(Vec::len)
            .sum()
    }

    pub fn audit(&self) -> J {
        json!({"applications": self.applications, "equalities": self.equalities,
            "cells": self.cells, "proofs": self.proofs})
    }
}
