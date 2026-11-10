//! Conservative influence of outstanding congruence through actual port roots.
//! Shared wiring describes all live uses. No per-producer consumer list, key
//! comparison or guessed equality is installed by the pending influence proof.
use super::*;
use rustc_hash::FxHashSet;

#[path = "pure_effects.rs"]
mod pure_effects;
pub(crate) use pure_effects::{Batch, Birth};

const MAX_VISITS: u64 = 4096;
#[derive(Default, Serialize)]
pub(crate) struct Counts {
    forecasts: u64,
    groups: u64,
    pure_groups: u64,
    seed_roots: u64,
    seed_candidates: u64,
    root_visits: u64,
    signal_visits: u64,
    static_steps: u64,
    inactive_steps: u64,
    output_reads: u64,
    legacy_boundaries: u64,
    typed_fallbacks: u64,
    pending_global_shortcuts: u64,
    boundary_global_shortcuts: u64,
    forest_global_shortcuts: u64,
    global_boundaries_by_table: BTreeMap<usize, u64>,
    pending_global_by_table: BTreeMap<usize, u64>,
    peak_group_visits: u64,
    membership_checks: u64,
    scratch_growths: u64,
    scope_completions: u64,
    bypassed_tasks: u64,
    pure_epoch_proofs: u64,
    pure_epoch_accepts: u64,
    pure_epoch_boundary_rejections: u64,
    pure_epoch_boundary_tables: BTreeMap<usize, u64>,
    pure_epoch_budget_rejections: u64,
    pure_epoch_peak_visits: u64,
    pure_epoch_source_steps: u64,
    pure_epoch_displaced_roots: u64,
    pure_epoch_peer_candidates: u64,
    pure_epoch_birth_checks: u64,
    pure_epoch_order_checks: u64,
    pure_epoch_order_refinements: u64,
    pure_epoch_order_disjoint: u64,
    pure_epoch_frontier_roots: u64,
    pure_epoch_frontier_checks: u64,
    pure_epoch_frontier_unknown: u64,
    pure_epoch_frontier_conflicts: u64,
    pure_epoch_order_rejections: u64,
    pure_epoch_order_tables: BTreeMap<usize, u64>,
    peak_retained_frontier_roots: usize,
}
struct Influence {
    // Complete conservative output frontier. None denotes a typed fallback;
    // a new constructor must then assume its input may change.
    roots: Option<FxHashSet<u64>>,
    table: usize,
    tables: Vec<bool>,
    reads: Vec<usize>,
    pure: bool,
    global: bool,
}
pub(crate) struct Forecast {
    tables: usize,
    groups: Vec<Influence>,
}
impl Forecast {
    /// Optional progress diagnostics; this is not part of the scope proof.
    pub(crate) fn conflicts(&self, demand: impl Iterator<Item=usize> + Clone) -> Vec<(usize, usize)> {
        self.groups
            .iter()
            .flat_map(|g| {
                demand
                    .clone()
                    .filter(|&t| g.tables[t])
                    .map(move |t| (g.table, t))
            })
            .collect()
    }
    /// Selecting one table also selects every pending group stored in that
    /// table. Close over their complete future effects before running repair.
    pub(crate) fn select(&self, demand: impl Iterator<Item=usize> + Clone, eager: bool) -> (Vec<bool>, u64) {
        let mut selected = vec![false; self.tables];
        let mut chosen = vec![false; self.groups.len()];
        let mut required = smallvec::SmallVec::<[usize; 8]>::new();
        let mut read = vec![false; self.tables];
        let mut checks = 0;
        loop {
            let mut progress = false;
            for (i, group) in self.groups.iter().enumerate() {
                checks += 1;
                if chosen[i] {
                    continue;
                }
                let needed = (eager && !group.pure)
                    || selected[group.table]
                    || demand.clone().chain(required.iter().copied()).any(|t| {
                        checks += 1;
                        group.tables[t]
                    });
                if needed {
                    chosen[i] = true;
                    if group.global {
                        selected.fill(true);
                        return (selected, checks + self.tables as u64);
                    }
                    for (out, &input) in selected.iter_mut().zip(&group.tables) {
                        checks += 1;
                        *out |= input;
                    }
                    for &table in &group.reads {
                        checks += 1;
                        if !read[table] {
                            read[table] = true;
                            required.push(table);
                        }
                    }
                    progress = true;
                }
            }
            if !progress {
                break;
            }
        }
        (selected, checks)
    }
    pub(crate) fn ready_tables(&self) -> (Vec<bool>, u64) {
        let mut ready = vec![true; self.tables];
        let mut checks = 0;
        for group in &self.groups {
            for (r, &pending) in ready.iter_mut().zip(&group.tables) {
                checks += 1;
                *r &= !pending;
            }
        }
        (ready, checks)
    }
    pub(crate) fn has_ordered_tasks(&self) -> bool {
        self.groups.iter().any(|g| !g.pure)
    }
    pub(crate) fn readiness(&self, demand: impl Iterator<Item=usize> + Clone) -> (bool, u64) {
        let mut checks = 0;
        let ready = self.groups.iter().all(|g| {
            demand.clone().all(|t| {
                checks += 1;
                !g.tables[t]
            })
        });
        (ready, checks)
    }
}
impl Graph {
    pub(crate) fn enable_pure_epochs(&mut self) {
        let mut plan = self.program.completion_plan.take().unwrap();
        Rc::make_mut(&mut plan).prepare_pure_rhs(&self.program);
        self.program.completion_plan = Some(plan);
        self.ownership
            .as_mut()
            .unwrap()
            .pending
            .enable_mixed_epochs();
    }
    pub(crate) fn use_port_completion(&mut self) -> Result<()> {
        self.use_scoped_completion()?;
        if self.ownership.as_ref().unwrap().port_completion.is_some() {
            return Ok(());
        }
        if self.pending_completion_tasks() != 0 {
            return Err("enable port scopes at a completed boundary".into());
        }
        let plan = &mut self.program.cell_ownership;
        plan.composition.prepare_effects(&plan.programs);
        let runtime = self.ownership.as_mut().unwrap();
        runtime.pending.enable_causes();
        runtime.port_completion = Some(Counts::default());
        Ok(())
    }
    fn typed_influence(&self, table: usize) -> Influence {
        let plan = self.program.completion_plan.as_ref().unwrap();
        Influence {
            roots: None,
            table,
            tables: (0..self.program.tables.len())
                .map(|t| plan.affects(table, t))
                .collect(),
            reads: plan.completion_reads[table].to_vec(),
            pure: plan.deferrable[table],
            global: plan.global_effects(table),
        }
    }
    fn port_influence(&self, table: usize, counts: &mut Counts) -> Result<Influence> {
        let runtime = self.ownership.as_ref().unwrap();
        let seeds = runtime.pending.causes(table);
        if seeds.is_empty() {
            counts.typed_fallbacks += 1;
            return Ok(self.typed_influence(table));
        }
        let mut influence = Influence {
            roots: None,
            table,
            tables: vec![false; self.program.tables.len()],
            reads: Vec::new(),
            pure: true,
            global: false,
        };
        influence.tables[table] = true;
        counts.scratch_growths += 1;
        let mut roots = smallvec::SmallVec::<[u64; 16]>::new();
        let mut causes = smallvec::SmallVec::<[u64; 16]>::new();
        let mut seen = FxHashSet::default();
        for &seed in seeds {
            counts.seed_roots += 1;
            offer(root(&self.parents, seed), &mut causes, &mut seen, counts);
        }
        seen.clear();
        let plan = &self.program.cell_ownership.composition;
        let before = visits(counts);
        // The input union has already notified every current user. This group
        // owns only future equalities produced by its table's pending keys.
        // Every possible collision peer shares a changed key port with one of
        // those keys, so the existing complete signal domain covers both result
        // endpoints without pulling sibling constructors into this group.
        for cause in causes {
            if visits(counts) - before >= MAX_VISITS {
                counts.typed_fallbacks += 1;
                return Ok(self.typed_influence(table));
            }
            counts.root_visits += 1;
            for signal in runtime
                .boundaries
                .get(&cause)
                .into_iter()
                .flat_map(|s| s.iter().copied())
                .chain(self.native_signal(cause))
            {
                if visits(counts) - before >= MAX_VISITS {
                    counts.typed_fallbacks += 1;
                    return Ok(self.typed_influence(table));
                }
                counts.signal_visits += 1;
                let component = runtime.composition.components[signal.component as usize]
                    .as_ref()
                    .ok_or("expired seed component")?;
                let Some(code) = plan.effects.get(component.shape) else {
                    counts.typed_fallbacks += 1;
                    return Ok(self.typed_influence(table));
                };
                for step in &code.signals[signal.symbol] {
                    if visits(counts) - before >= MAX_VISITS {
                        counts.typed_fallbacks += 1;
                        return Ok(self.typed_influence(table));
                    }
                    counts.static_steps += 1;
                    let Some(output) = step.output else { continue };
                    let fact = FactRef {
                        cell: component.frames[step.frame],
                        op: step.op,
                    };
                    let Some(stored) = self.stable_node(fact) else {
                        counts.inactive_steps += 1;
                        continue;
                    };
                    if stored.table != table {
                        continue;
                    }
                    counts.seed_candidates += 1;
                    counts.output_reads += 1;
                    let value =
                        component.signals[output].ok_or("live seed lacks output binding")?;
                    offer(
                        runtime.stats.signal_root(&self.parents, value),
                        &mut roots,
                        &mut seen,
                        counts,
                    );
                }
            }
        }
        let mut boundary_tables = BTreeSet::new();
        let mut next = 0;
        while next < roots.len() {
            if visits(counts) - before >= MAX_VISITS {
                counts.typed_fallbacks += 1;
                return Ok(self.typed_influence(table));
            }
            let root = roots[next];
            next += 1;
            counts.root_visits += 1;
            // Uncovered/mutable users are explicit boundaries, using the old
            // boundary ownership that already exists. Add no new subscription.
            for &dependency in self.uses.get(&root).into_iter().flat_map(|s| s.iter()) {
                if visits(counts) - before >= MAX_VISITS {
                    counts.typed_fallbacks += 1;
                    return Ok(self.typed_influence(table));
                }
                counts.legacy_boundaries += 1;
                if let Some(t) = self.dependency_table(dependency) {
                    influence.pure = false;
                    let types = self.program.completion_plan.as_ref().unwrap();
                    if types.global_effects(t) {
                        counts.boundary_global_shortcuts += 1;
                        *counts.global_boundaries_by_table.entry(t).or_default() += 1;
                        influence.global = true;
                        influence.tables.fill(true);
                        return Ok(influence);
                    }
                    if !boundary_tables.insert(t) {
                        continue;
                    }
                    influence.reads.extend(types.completion_reads[t].iter());
                    for (other, affected) in influence.tables.iter_mut().enumerate() {
                        counts.membership_checks += 1;
                        *affected |= types.affects(t, other);
                    }
                }
            }
            for signal in runtime
                .boundaries
                .get(&root)
                .into_iter()
                .flat_map(|s| s.iter().copied())
                .chain(self.native_signal(root))
            {
                if visits(counts) - before >= MAX_VISITS {
                    counts.typed_fallbacks += 1;
                    return Ok(self.typed_influence(table));
                }
                counts.signal_visits += 1;
                let component = runtime.composition.components[signal.component as usize]
                    .as_ref()
                    .ok_or("expired influence component")?;
                let Some(code) = plan.effects.get(component.shape) else {
                    counts.typed_fallbacks += 1;
                    return Ok(self.typed_influence(table));
                };
                for step in &code.signals[signal.symbol] {
                    if visits(counts) - before >= MAX_VISITS {
                        counts.typed_fallbacks += 1;
                        return Ok(self.typed_influence(table));
                    }
                    counts.static_steps += 1;
                    let fact = FactRef {
                        cell: component.frames[step.frame],
                        op: step.op,
                    };
                    let Some(stored) = self.stable_node(fact) else {
                        counts.inactive_steps += 1;
                        continue;
                    };
                    influence.tables[stored.table] = true;
                    if let Some(output) = step.output {
                        counts.output_reads += 1;
                        let value =
                            component.signals[output].ok_or("live output lacks signal binding")?;
                        offer(
                            runtime.stats.signal_root(&self.parents, value),
                            &mut roots,
                            &mut seen,
                            counts,
                        );
                    }
                }
            }
        }
        influence.reads.sort_unstable();
        influence.reads.dedup();
        if runtime.pending.mixed_epochs() {
            influence.roots = Some(seen);
        }
        Ok(influence)
    }
    pub(crate) fn forecast_port_completion(&mut self) -> Result<Forecast> {
        assert!(self.pending_unions.is_empty());
        let mut counts = self
            .ownership
            .as_mut()
            .unwrap()
            .port_completion
            .take()
            .ok_or("port scopes disabled")?;
        counts.forecasts += 1;
        let mut groups = Vec::new();
        let outcome = (|| {
            let legacy = self
                .dirty
                .iter()
                .copied()
                .chain(self.dirty_markers.iter().copied().map(Dependency::Fact))
                .filter_map(|d| self.dependency_table(d))
                .collect::<BTreeSet<_>>();
            if let Some(&table) = legacy.iter().find(|&&t| {
                self.program
                    .completion_plan
                    .as_ref()
                    .unwrap()
                    .global_effects(t)
            }) {
                counts.pending_global_shortcuts += 1;
                *counts.pending_global_by_table.entry(table).or_default() += 1;
                counts.groups += 1;
                groups.push(Influence {
                    roots: None,
                    table,
                    tables: vec![true; self.program.tables.len()],
                    reads: Vec::new(),
                    pure: false,
                    global: true,
                });
                return Ok(Forecast {
                    tables: self.program.tables.len(),
                    groups,
                });
            }
            for table in self.ownership.as_ref().unwrap().pending.active_tables() {
                let before = visits(&counts);
                let influence = self.port_influence(table, &mut counts)?;
                counts.peak_group_visits = counts.peak_group_visits.max(visits(&counts) - before);
                counts.pure_groups += u64::from(influence.pure);
                if influence.global && !influence.pure {
                    counts.forest_global_shortcuts += 1;
                    counts.groups += 1;
                    return Ok(Forecast {
                        tables: self.program.tables.len(),
                        groups: vec![influence],
                    });
                }
                groups.push(influence);
            }
            // Legacy tasks cannot cross source epochs. Their typed footprint
            // preserves ordered merge effects, including opaque global reads.
            for table in legacy {
                let mut influence = self.typed_influence(table);
                influence.pure = false;
                groups.push(influence);
            }
            counts.groups += groups.len() as u64;
            counts.peak_retained_frontier_roots = counts.peak_retained_frontier_roots.max(
                groups
                    .iter()
                    .filter_map(|g| g.roots.as_ref())
                    .map(FxHashSet::len)
                    .sum(),
            );
            Ok(Forecast {
                tables: self.program.tables.len(),
                groups,
            })
        })();
        self.ownership.as_mut().unwrap().port_completion = Some(counts);
        outcome
    }
    pub(crate) fn complete_port_selection(
        &mut self,
        allowed: &[bool],
        checks: u64,
    ) -> Result<bool> {
        let counts = self
            .ownership
            .as_mut()
            .unwrap()
            .port_completion
            .as_mut()
            .unwrap();
        counts.membership_checks += checks;
        if !allowed.iter().any(|&yes| yes) {
            return Ok(false);
        }
        counts.scope_completions += 1;
        let epoch = self.epoch;
        let result = self.repair_selected(Some(crate::table_mask::Selection::Flags(allowed)));
        self.epoch = epoch;
        result?;
        let remaining = self.pending_completion_tasks();
        self.ownership
            .as_mut()
            .unwrap()
            .port_completion
            .as_mut()
            .unwrap()
            .bypassed_tasks += remaining as u64;
        Ok(true)
    }
    pub fn port_completion_report(&self) -> J {
        let Some(counts) = self
            .ownership
            .as_ref()
            .and_then(|r| r.port_completion.as_ref())
        else {
            return json!({"enabled":false});
        };
        let plans = &self.program.cell_ownership.composition.effects;
        json!({"enabled":true,"stats":counts,"shared_plans":plans.len(),
            "shared_steps":plans.iter().flat_map(|p|p.signals.iter()).map(Vec::len).sum::<usize>(),
            "visit_budget_per_group":MAX_VISITS,
            "scope":"conservative concrete-port influence; static shared wiring and existing boundaries; table-granular pending groups"})
    }
}
fn offer(
    root: u64,
    roots: &mut smallvec::SmallVec<[u64; 16]>,
    seen: &mut FxHashSet<u64>,
    counts: &mut Counts,
) {
    counts.membership_checks += 1;
    let before = seen.capacity();
    let added = seen.insert(root);
    counts.scratch_growths += u64::from(before != seen.capacity());
    if added {
        let before = roots.capacity();
        roots.push(root);
        counts.scratch_growths += u64::from(before != roots.capacity());
    }
}

fn visits(counts: &Counts) -> u64 {
    counts.root_visits + counts.signal_visits + counts.static_steps + counts.legacy_boundaries
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_ordered_reader_selects_a_pure_producer_without_claiming_to_write_its_table() {
        let forecast = Forecast {
            tables: 3,
            groups: vec![
                Influence {
                    roots: None,
                    table: 0,
                    tables: vec![true, false, true],
                    reads: vec![],
                    pure: true,
                    global: false,
                },
                Influence {
                    roots: None,
                    table: 1,
                    tables: vec![false, true, false],
                    reads: vec![2],
                    pure: false,
                    global: false,
                },
            ],
        };
        assert!(!forecast.groups[1].tables[2]);
        let (allowed, _) = forecast.select(std::iter::empty(), true);
        assert_eq!(allowed, vec![true, true, true]);
    }
}
