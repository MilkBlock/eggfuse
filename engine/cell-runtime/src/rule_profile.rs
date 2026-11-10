//! Optional attribution at existing rule-batch boundaries. No per-instance
//! history, extra table read, or inference-time graph representation.
use crate::graph::Stats;

pub(super) struct Snapshot {
    single: u64,
    unchanged: u64,
    updates: u64,
    constructors: u64,
    reused: u64,
    facts: u64,
    unions: u64,
    completions: u64,
}
impl Snapshot {
    pub(super) fn new(s: &Stats, completions: u64) -> Self {
        Self { single: s.single_writes, unchanged: s.transient_writes,
            updates: s.function_updates, constructors: s.constructor_requests,
            reused: s.constructor_reused, facts: s.logical_facts_created,
            unions: s.union_requests, completions }
    }
}

#[derive(Default, Clone, serde::Serialize)]
pub(super) struct Rhs {
    batches: u64,
    bindings: u64,
    seconds: f64,
    single_writes: u64,
    unchanged_single_writes: u64,
    function_updates: u64,
    constructor_requests: u64,
    constructor_reused: u64,
    facts_created: u64,
    union_requests: u64,
    completed_steps: u64,
}
impl Rhs {
    pub(super) fn record(&mut self, before: Snapshot, after: Snapshot, bindings: usize, seconds: f64) {
        self.batches += 1;
        self.bindings += bindings as u64;
        self.seconds += seconds;
        self.single_writes += after.single - before.single;
        self.unchanged_single_writes += after.unchanged - before.unchanged;
        self.function_updates += after.updates - before.updates;
        self.constructor_requests += after.constructors - before.constructors;
        self.constructor_reused += after.reused - before.reused;
        self.facts_created += after.facts - before.facts;
        self.union_requests += after.unions - before.unions;
        self.completed_steps += after.completions - before.completions;
    }
}
