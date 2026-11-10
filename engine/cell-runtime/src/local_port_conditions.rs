//! Execute compiler-derived local congruence conditions. No persistent satisfied-
//! condition cache or per-instance reverse graph is maintained. Each visit checks current
//! fact liveness; the queue contains facts, not stale condition incarnations.
use super::*;
use composition::conditions::Plan;
#[path = "completion_read_batches.rs"]
pub(super) mod batches;
#[path = "parallel_port_guards.rs"]
pub(super) mod parallel;

#[derive(Default, Serialize)]
pub(super) struct Stats {
    pub attempts: u64,
    pub uncovered_shapes: u64,
    pub boundary_signals: u64,
    pub boundary_sites: u64,
    pub anchor_probes: u64,
    pub boundary_uncompiled_steps: u64,
    pub boundary_indexed_steps: u64,
    pub open_domains: u64,
    pub closed_domain_probes: u64,
    pub local_candidates: u64,
    pub boundary_candidates: u64,
    pub candidate_buffer_growths: u64,
    pub candidate_buffer_spills: u64,
    pub candidate_sort_comparisons: u64,
    pub boundary_collisions: u64,
    pub condition_visits: u64,
    pub inactive_sites: u64,
    pub pending_sites: u64,
    pub operator_guards: u64,
    pub scalar_guards: u64,
    pub equality_guards: u64,
    pub shared_symbol_guards: u64,
    pub completed_conditions: u64,
    pub cross_stage_conditions: u64,
}

#[derive(Clone, Copy)]
struct Candidate {
    fact: FactRef,
    condition: Option<usize>,
}
type Candidates = smallvec::SmallVec<[Candidate; 16]>;
struct CandidateSet {
    component: u32,
    plan: Arc<Plan>,
    candidates: Candidates,
}
#[derive(Default)]
struct BoundaryWork {
    signals: u64,
    sites: u64,
    uncompiled_steps: u64,
    indexed_steps: u64,
    growths: u64,
}
fn push_candidate(out: &mut Candidates, fact: FactRef, condition: Option<usize>) -> u64 {
    let old = out.capacity();
    out.push(Candidate { fact, condition });
    u64::from(old != out.capacity())
}

impl Graph {
    pub fn new_with_local_congruence(p: Program) -> Result<Self> {
        let mut graph = Self::new_with_port_keys(p)?;
        graph.use_local_port_conditions()?;
        Ok(graph)
    }
    pub fn use_local_port_conditions(&mut self) -> Result<()> {
        self.use_port_constructor_matching()?;
        let plan = &mut self.program.cell_ownership;
        plan.composition.prepare_conditions(&plan.programs, &self.program.templates, &plan.markers);
        self.stable_ports
            .as_mut()
            .unwrap()
            .conditions
            .get_or_insert_with(Stats::default);
        Ok(())
    }
    /// Shared conditions cover the local component. One input domain supplies
    /// foreign candidates. Their ordered union is complete, even when open.
    /// None is reserved for an uncovered source shape.
    fn local_port_candidates(&mut self, f: FactRef, row: &Row) -> Result<Option<CandidateSet>> {
        if self.stable_ports.as_ref().unwrap().conditions.is_none() {
            return Ok(None);
        }
        self.local_condition_stats().attempts += 1;
        let frame = self.ownership.as_ref().unwrap().composition.frames[&f.cell];
        let shape = self.ownership.as_ref().unwrap().composition.components
            [frame.component as usize]
            .as_ref()
            .ok_or("expired source component")?
            .shape;
        let Some(plan) = self
            .program
            .cell_ownership
            .composition
            .conditions
            .get(shape)
            .cloned()
            .filter(|p| p.complete)
        else {
            self.local_condition_stats().uncovered_shapes += 1;
            return Ok(None);
        };
        let Some(site) = plan.site(frame.ordinal, f.op) else {
            return Err("complete local condition plan omits a covered source".into());
        };
        let mut candidates = Candidates::new();
        for &id in &plan.routes[site] {
            let condition = &plan.conditions[id];
            let other = condition.sites[usize::from(condition.sites[0] == site)];
            let peer = &plan.sites[other];
            let cell = self.ownership.as_ref().unwrap().composition.components
                [frame.component as usize]
                .as_ref()
                .unwrap()
                .frames[peer.frame];
            let target = FactRef { cell, op: peer.op };
            self.local_condition_stats().candidate_buffer_growths +=
                push_candidate(&mut candidates, target, Some(id));
        }
        let locals = candidates.len();
        let (column, id, probes) = self.condition_anchor(row)?;
        let work = self.external_condition_candidates(
            frame.component,
            row.table,
            column,
            id,
            &mut candidates,
        )?;
        let stats = self.local_condition_stats();
        stats.local_candidates += locals as u64;
        stats.boundary_candidates += (candidates.len() - locals) as u64;
        stats.candidate_buffer_growths += work.growths;
        stats.candidate_buffer_spills += u64::from(candidates.spilled());
        stats.anchor_probes += probes;
        stats.boundary_signals += work.signals;
        stats.boundary_sites += work.sites;
        stats.boundary_uncompiled_steps += work.uncompiled_steps;
        stats.boundary_indexed_steps += work.indexed_steps;
        if candidates.len() == locals {
            stats.closed_domain_probes += 1;
        } else {
            stats.open_domains += 1;
        }
        // Local routes are already ordered. Foreign candidates use root-domain
        // order, so merge through charged scratch (16 inline entries, measured
        // heap growth beyond that). No persistent candidate index is built.
        if candidates.len() > locals {
            candidates.sort_unstable_by(|a, b| {
                stats.candidate_sort_comparisons += 1;
                a.fact.cmp(&b.fact)
            });
            candidates.dedup_by_key(|c| c.fact);
        }
        Ok(Some(CandidateSet {
            component: frame.component,
            plan,
            candidates,
        }))
    }
    pub(super) fn local_port_collision(
        &mut self,
        f: FactRef,
        row: &Row,
    ) -> Result<Option<Option<Row>>> {
        let Some(CandidateSet {
            component,
            plan,
            candidates,
        }) = self.local_port_candidates(f, row)?
        else {
            return Ok(None);
        };
        if self.dispatch_port_guards(candidates.len()) {
            return self.parallel_port_collision(f, row, &plan, component, &candidates);
        }
        for candidate in candidates {
            let target = candidate.fact;
            if self
                .dependency_table(Dependency::Fact(target))
                .is_some_and(|t| {
                    self.ownership
                        .as_ref()
                        .unwrap()
                        .pending
                        .contains(t, &target)
                })
            {
                self.local_condition_stats().pending_sites += 1;
                continue;
            }
            let Some(id) = candidate.condition else {
                if let Some(found) = self.exact_port_candidate(
                    target,
                    row.table,
                    &row.values[..row.values.len() - 1],
                )? {
                    self.local_condition_stats().boundary_collisions += 1;
                    return Ok(Some(Some(found)));
                }
                continue;
            };
            self.local_condition_stats().condition_visits += 1;
            let condition = &plan.conditions[id];
            let FactRef { cell, op } = target;
            let Some(stored) = self.stable_node(target) else {
                self.local_condition_stats().inactive_sites += 1;
                continue;
            };
            let mut work = guard::Work::default();
            let matched = if stored.table != row.table {
                Ok(false)
            } else {
                self.stable_port_reader()?.condition_matches(
                    component,
                    condition,
                    stored,
                    &row.values,
                    &mut work,
                )
            };
            self.record_guard_reads(&work);
            let stats = self.local_condition_stats();
            stats.operator_guards += 1;
            stats.scalar_guards += work.scalar_guards;
            stats.equality_guards += work.equality_guards;
            stats.shared_symbol_guards += work.shared_symbol_guards;
            if !matched? {
                continue;
            }
            self.local_condition_stats().completed_conditions += 1;
            self.local_condition_stats().cross_stage_conditions +=
                u64::from(self.cells[&f.cell].started_epoch != self.cells[&cell].started_epoch);
            // The logical commit consumes the result ports through the row
            // interface, preserving visibility, receipts and ordered retirement.
            let state = &self.cells[&cell].facts[&op];
            return self
                .read_stable_fact(target, state, self.stable_node(target).unwrap())
                .map(|r| Some(Some(r)));
        }
        Ok(Some(None))
    }
    fn local_condition_stats(&mut self) -> &mut Stats {
        self.stable_ports
            .as_mut()
            .unwrap()
            .conditions
            .as_mut()
            .unwrap()
    }
    fn condition_anchor(&self, row: &Row) -> Result<(usize, u64, u64)> {
        let columns = self.program.repair_ports.key_eq_columns[row.table]
            .as_ref()
            .unwrap();
        let m = self.ownership.as_ref().unwrap();
        let mut best = None;
        for &column in columns {
            let Value::Eq(id) = row.values[column] else {
                return Err("typed input port".into());
            };
            // Signal cardinality is a cheap choice heuristic. It does not
            // inspect every consumer of every possible anchor just to plan.
            let count = m.boundaries.get(&id).map_or(0, |s| s.len())
                + usize::from(self.native_signal(id).is_some());
            if best.is_none_or(|(_, _, cost)| count < cost) {
                best = Some((column, id, count));
            }
        }
        let (column, id, _) = best.ok_or("constructor has no input port")?;
        Ok((column, id, columns.len() as u64))
    }
    fn external_condition_candidates(
        &self,
        component: u32,
        table: usize,
        column: usize,
        id: u64,
        out: &mut Candidates,
    ) -> Result<BoundaryWork> {
        // Root-level boundary ownership already belongs to symbolic ports.
        // Probe shared code; no producer gets a runtime consumer list.
        let mut work = BoundaryWork::default();
        for signal in self.query_signals(table, id) {
            work.signals += 1;
            if signal.component == component {
                continue;
            }
            // Field-use indexing is independent of the bounded pair-condition
            // plan. Oversized shapes keep the same complete input domain.
            let uses = self.cell_field_uses(signal, column)?;
            for position in 0..uses.len() {
                if uses.indexed() {
                    work.indexed_steps += 1;
                } else {
                    work.uncompiled_steps += 1;
                }
                let Some(fact) = uses.fact(position, true) else { continue; };
                work.sites += 1;
                if self.condition_candidate_table(fact) == Some(table) {
                    work.growths += push_candidate(out, fact, None);
                }
            }
        }
        // Every fact in an admitted table is owned. Legacy reverse users must
        // belong to other tables and cannot be constructor-key candidates.
        Ok(work)
    }
    fn condition_candidate_table(&self, fact: FactRef) -> Option<usize> {
        self.stable_node(fact).map(|s| s.table)
    }
    pub(super) fn local_condition_report(&self) -> J {
        let Some(stats) = self
            .stable_ports
            .as_ref()
            .and_then(|s| s.conditions.as_ref())
        else {
            return json!({"enabled":false});
        };
        let plans = &self.program.cell_ownership.composition.conditions;
        json!({"enabled":true,"stats":stats,"max_sites":Plan::MAX_SITES,
            "covered_shapes":plans.iter().filter(|p|p.complete).count(),
            "uncovered_shapes":plans.iter().filter(|p|!p.complete).count(),
            "shared_conditions":plans.iter().map(|p|p.conditions.len()).sum::<usize>(),
            "operator_pairs_elided":plans.iter().map(|p|p.operator_pairs_elided).sum::<usize>(),
            "reflexive_inputs_elided":plans.iter().map(|p|p.reflexive_inputs_elided).sum::<usize>(),
            "duplicate_inputs_elided":plans.iter().map(|p|p.duplicate_inputs_elided).sum::<usize>(),
            "shared_typed_codes":self.program.cell_ownership.code_programs.len(),
            "query_classes":self.program.cell_ownership.query_classes.as_ref().map(|p|p.report()),
            "shared_operator_slots":self.program.cell_ownership.code_operators.iter().map(Vec::len).sum::<usize>(),
            "shared_query_routes":self.program.cell_ownership.composition.queries.iter()
                .flat_map(|p|&p.columns).map(Vec::len).sum::<usize>(),
            "shared_query_positions":self.program.cell_ownership.composition.queries.iter()
                .flat_map(|p|&p.columns).flatten().map(Vec::len).sum::<usize>(),
            "scope":"shared local all-input guards plus one complete foreign input domain; global Run barrier remains"})
    }
}
