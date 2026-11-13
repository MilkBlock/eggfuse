//! Read-only Eq-delta supervision using the executing Cell runtime's graph.
//! No shadow egraph, constructor rehash, copied bindings or Python closure.
//! Frames own only boundary metadata and can be sent to an asynchronous checker.
use crate::{
    graph::Graph,
    program::Program,
    slots::Slots,
    value::{self, Value},
};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    time::Instant,
};

struct Layout {
    slots: Vec<usize>,
    pairs: Vec<(usize, usize)>,
}
struct Port {
    id: u64,
    before: u64,
    after: u64,
}
struct Pending {
    binding: usize,
    rule: usize,
    start: usize,
    valid: bool,
}

#[derive(Default, Serialize)]
pub struct Stats {
    pub bindings: u64,
    pub ports: u64,
    pub missing_ports: u64,
    pub candidate_pairs: u64,
    pub new_equalities: u64,
    pub root_reads: u64,
    pub capture_seconds: f64,
    pub finish_seconds: f64,
    pub peak_pending_ports: usize,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Claim {
    pub binding: usize,
    pub rule: usize,
    pub left: usize,
    pub right: usize,
}
impl Claim {
    pub fn new(binding: usize, rule: usize, a: usize, b: usize) -> Self {
        Self {
            binding,
            rule,
            left: a.min(b),
            right: a.max(b),
        }
    }
    fn normalized(&self) -> Self {
        Self::new(self.binding, self.rule, self.left, self.right)
    }
}

#[derive(Serialize, Deserialize)]
pub struct Proposal {
    pub execution: u64,
    pub program: String,
    pub run: usize,
    pub epoch: u64,
    pub equalities: Vec<Claim>,
}
#[derive(Serialize)]
pub struct Outcome {
    pub claim: Claim,
    pub equal: bool,
}
#[derive(Serialize)]
pub struct Frame {
    pub execution: u64,
    pub program: String,
    pub run: usize,
    pub epoch: u64,
    pub complete: bool,
    pub bindings: usize,
    pub outcomes: Vec<Outcome>,
}
#[derive(Serialize)]
pub struct Correction {
    pub claim: Claim,
    pub equal: bool,
}
#[derive(Default, Serialize)]
pub struct Verdict {
    pub pass: bool,
    pub complete: bool,
    pub protocol_ok: bool,
    pub checked_pairs: usize,
    pub true_positives: usize,
    pub false_positives: usize,
    pub false_negatives: usize,
    pub invalid_claims: usize,
    pub corrections: Vec<Correction>,
}
impl Frame {
    /// Checks completeness as well as soundness. Empty proposals cannot hide
    /// missed equalities. Incorrect execution/Run/epoch tags never authorize use.
    pub fn check(&self, proposal: &Proposal) -> Verdict {
        let mut result = Verdict {
            complete: self.complete,
            protocol_ok: proposal.execution == self.execution
                && proposal.program == self.program
                && proposal.run == self.run
                && proposal.epoch == self.epoch,
            ..Verdict::default()
        };
        if !result.complete || !result.protocol_ok {
            return result;
        }
        let expected: BTreeMap<_, _> = self
            .outcomes
            .iter()
            .map(|o| (o.claim.clone(), o.equal))
            .collect();
        let mut seen = BTreeSet::new();
        for claim in &proposal.equalities {
            let claim = claim.normalized();
            if !seen.insert(claim.clone()) {
                result.invalid_claims += 1;
                continue;
            }
            match expected.get(&claim) {
                Some(true) => result.true_positives += 1,
                Some(false) => {
                    result.false_positives += 1;
                    result.corrections.push(Correction {
                        claim,
                        equal: false,
                    });
                }
                None => result.invalid_claims += 1,
            }
        }
        for (claim, equal) in expected {
            result.checked_pairs += 1;
            if equal && !seen.contains(&claim) {
                result.false_negatives += 1;
                result.corrections.push(Correction { claim, equal: true });
            }
        }
        result.pass = result.false_positives + result.false_negatives + result.invalid_claims == 0;
        result
    }
}

pub struct Audit {
    execution: u64,
    program: String,
    layouts: Vec<Layout>,
    pending: Vec<Pending>,
    ports: Vec<Port>,
    roots: BTreeMap<u64, u64>,
    pub stats: Stats,
}
impl Audit {
    /// The caller assigns a fresh execution tag for a live session. Explicit
    /// replay may reuse a tag, but must not be presented as freshness validation.
    pub fn new(program: &Program, execution: u64) -> Self {
        let layouts = program
            .rules
            .iter()
            .map(|rule| {
                let sorts = &program.templates[rule.template].sorts;
                let mut slots = rule
                    .inputs
                    .iter()
                    .copied()
                    .filter(|s| sorts[*s]["kind"] == "eq")
                    .collect::<Vec<_>>();
                slots.sort_unstable();
                let mut pairs = vec![];
                for i in 0..slots.len() {
                    for j in 0..i {
                        if sorts[slots[i]] == sorts[slots[j]] {
                            pairs.push((j, i));
                        }
                    }
                }
                Layout { slots, pairs }
            })
            .collect();
        Self {
            execution,
            program: program.artifact["sha256"].as_str().unwrap_or("").into(),
            layouts,
            pending: vec![],
            ports: vec![],
            roots: BTreeMap::new(),
            stats: Stats::default(),
        }
    }
    pub fn capture(&mut self, binding: usize, rule: usize, slots: &Slots, graph: &Graph) {
        let clock = Instant::now();
        let start = self.ports.len();
        let mut valid = true;
        for slot in &self.layouts[rule].slots {
            if let Some(Value::Eq(id)) = slots.get(slot) {
                let before = *self.roots.entry(*id).or_insert_with(|| {
                    self.stats.root_reads += 1;
                    value::root(&graph.parents, *id)
                });
                self.ports.push(Port {
                    id: *id,
                    before,
                    after: 0,
                });
                self.stats.ports += 1;
            } else {
                valid = false;
                self.stats.missing_ports += 1;
                self.ports.push(Port {
                    id: 0,
                    before: 0,
                    after: 0,
                });
            }
        }
        self.pending.push(Pending {
            binding,
            rule,
            start,
            valid,
        });
        self.stats.bindings += 1;
        self.stats.peak_pending_ports = self.stats.peak_pending_ports.max(self.ports.len());
        self.stats.capture_seconds += clock.elapsed().as_secs_f64();
    }
    pub fn finish(&mut self, run: usize, graph: &Graph) -> Frame {
        let clock = Instant::now();
        self.roots.clear();
        let mut complete = self.program.len() > 0
            && graph.pending_completion_tasks() == 0
            && graph.pending_unions.is_empty();
        for port in &mut self.ports {
            port.after = *self.roots.entry(port.id).or_insert_with(|| {
                self.stats.root_reads += 1;
                value::root(&graph.parents, port.id)
            });
        }
        let bindings = self.pending.len();
        let mut outcomes = vec![];
        for row in self.pending.drain(..) {
            if !row.valid {
                complete = false;
                continue;
            }
            let layout = &self.layouts[row.rule];
            for &(i, j) in &layout.pairs {
                let a = &self.ports[row.start + i];
                let b = &self.ports[row.start + j];
                if a.before == b.before {
                    continue;
                }
                let equal = a.after == b.after;
                self.stats.candidate_pairs += 1;
                self.stats.new_equalities += u64::from(equal);
                outcomes.push(Outcome {
                    claim: Claim::new(row.binding, row.rule, layout.slots[i], layout.slots[j]),
                    equal,
                });
            }
        }
        self.ports.clear();
        self.roots.clear();
        self.stats.finish_seconds += clock.elapsed().as_secs_f64();
        Frame {
            execution: self.execution,
            program: self.program.clone(),
            run,
            epoch: graph.epoch,
            complete,
            bindings,
            outcomes,
        }
    }
}
