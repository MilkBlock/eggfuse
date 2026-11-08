//! Source Runs retain finite matching snapshots. Pure constructor closure and
//! its shared publication contexts may cross an independent source occurrence.
//! Query scopes are complete before ready-set selection, including probes. In
//! port mode only matched rules contribute RHS demands after the snapshot seals.
use super::*;
use crate::{
    change_batch::ChangeBatch, completion_plan::Scope, graph::cell_ownership::completion::Forecast,
};

#[derive(Default, serde::Serialize)]
pub(super) struct Counts {
    pub ruleset_waits: u64,
    pub already_ready_waits: u64,
    pub eager_waits: u64,
    pub global_observation_fences: u64,
    pub compiler_full_completion_runs: u64,
    pub runs_with_unrelated_pending: u64,
    // Executed bindings are not committed mutations.
    pub executed_bindings_while_pending: u64,
    pub partial_publications: u64,
    pub published_tables_while_pending: u64,
    pub readiness_dependency_checks: u64,
    pub publication_table_checks: u64,
    pub unchanged_influence_reuses: u64,
    pub query_completions: u64,
    pub rhs_completions: u64,
    pub rhs_access_completions: u64,
    pub rhs_union_completions: u64,
    pub query_runs_while_pending: u64,
    pub query_bindings_while_pending: u64,
    pub rhs_empty_skips: u64,
    pub rhs_demand_probes: u64,
    pub rhs_demand_growths: u64,
    pub rhs_selected_rules: u64,
    pub peak_matched_origin_slots: usize,
    pub rhs_fact_births_while_pending: u64,
    pub rhs_function_updates_while_pending: u64,
    pub source_unions_while_pending: u64,
    pub bound_rhs_attempts: u64,
    pub bound_rhs_rule_checks: u64,
    pub bound_rhs_accepts: u64,
    pub bound_rhs_noop_accepts: u64,
    pub bound_rhs_bindings: u64,
    pub bound_rhs_ops: u64,
    pub bound_rhs_expression_steps: u64,
    pub bound_rhs_input_reads: u64,
    pub bound_rhs_key_reads: u64,
    pub bound_rhs_value_slots: u64,
    pub bound_rhs_scratch_growths: u64,
    pub bound_rhs_overlay_checks: u64,
    pub bound_rhs_source_pairs: u64,
    pub bound_rhs_birth_sites: u64,
    pub bound_rhs_budget_rejections: u64,
    pub deferred_rows_carried: u64,
    pub peak_retained_changes: usize,
    pub peak_retained_anchors: usize,
    pub peak_retained_contexts: usize,
    pub peak_retained_forwards: usize,
}
pub(super) struct State {
    can_defer: bool,
    port_scopes: bool,
    pub(super) forecast: Option<Forecast>,
    pub(super) pure_epochs: bool,
    matched: bool,
    rhs_demand: Vec<usize>,
    rhs_seen: Vec<bool>,
    eager: Scope,
    deferred: ChangeBatch,
    pub stats: Counts,
}
impl Executor {
    pub fn use_scoped_execution(&mut self) -> Result<()> {
        if self.completion.is_some() {
            return Ok(());
        }
        if !self.steps.is_empty() || !self.graph.changes.is_empty() {
            return Err("configure scoped execution before source Runs".into());
        }
        self.graph.use_scoped_completion()?;
        let plan = self.graph.program.completion_plan.as_ref().unwrap();
        let eager = plan.scope(
            &plan
                .deferrable
                .iter()
                .enumerate()
                .filter_map(|(t, &can_defer)| (!can_defer).then_some(t))
                .collect::<Vec<_>>(),
        )?;
        let can_defer = plan.deferrable.iter().any(|&yes| yes);
        let mut deferred = ChangeBatch::new(if can_defer {
            self.graph.program.tables.len()
        } else {
            0
        });
        if can_defer {
            deferred.enable_split();
            self.graph.changes.enable_split();
        }
        self.completion = Some(State {
            can_defer,
            port_scopes: false,
            forecast: None,
            pure_epochs: false,
            matched: false,
            rhs_demand: Vec::new(),
            rhs_seen: Vec::new(),
            eager,
            deferred,
            stats: Counts::default(),
        });
        Ok(())
    }
    pub fn use_port_scopes(&mut self) -> Result<()> {
        self.use_scoped_execution()?;
        if !self.steps.is_empty() {
            return Err("configure port scopes before source Runs".into());
        }
        self.graph.use_port_completion()?;
        let state = self.completion.as_mut().unwrap();
        if !state.can_defer {
            state.deferred = ChangeBatch::new(self.graph.program.tables.len());
            state.deferred.enable_split();
            self.graph.changes.enable_split();
        }
        state.can_defer = true;
        state.port_scopes = true;
        state
            .rhs_seen
            .resize(self.graph.program.tables.len(), false);
        Ok(())
    }
    pub fn use_pure_epochs(&mut self) -> Result<()> {
        self.use_port_scopes()?;
        if !self.completion.as_ref().unwrap().pure_epochs {
            self.graph.enable_pure_epochs();
            self.completion.as_mut().unwrap().pure_epochs = true;
        }
        Ok(())
    }
    pub fn use_unique_port_publication(&mut self) -> Result<()> {
        self.use_pure_epochs()?;
        self.graph.use_unique_port_publication()
    }
    fn global_completion_observer(&self) -> bool {
        let global = self.audit
            || cfg!(any(
                feature = "rhs-work-audit",
                feature = "family-replay",
                feature = "projection-semijoin"
            ));
        #[cfg(feature = "structural-depth")]
        let global = global || self.stage_spine.structural.depth > 0;
        global
    }
    pub fn scoped_execution_report(&self) -> J {
        let Some(state) = &self.completion else {
            return json!({"enabled":false});
        };
        let (anchors, contexts) = self.stage_spine.pending_publication_counts();
        json!({"enabled":true,"stats":state.stats,
            "compiler_admits_deferral":self.graph.program.completion_plan.as_ref().unwrap().deferrable.iter().any(|&v|v),
            "port_scopes":state.port_scopes,
            "pure_epochs":state.pure_epochs,
            "global_observer":self.global_completion_observer(),
            "pending_anchors":anchors,"retained_contexts":contexts,
            "retained_forwards":self.graph.receipt_forwards.len(),
            "unpublished_changes":self.graph.changes.tables().map(|(_, rows)|rows.len()).sum::<usize>(),
            "scope":"standalone single-thread Executor; conservative typed scopes, selective publication; no parallel workers"})
    }
    pub(super) fn wait_for_ruleset(&mut self, set: &str) -> Result<()> {
        if self
            .completion
            .as_ref()
            .is_none_or(|state| !state.can_defer)
        {
            return Ok(());
        }
        let plan = self.graph.program.completion_plan.as_ref().unwrap().clone();
        let scope = plan.rulesets.get(set).ok_or("unknown completion ruleset")?;
        self.completion.as_mut().unwrap().stats.ruleset_waits += 1;
        if self.graph.pending_completion_tasks() == 0 {
            return Ok(());
        }
        let global = self.global_completion_observer();
        if !global && self.completion.as_ref().unwrap().port_scopes {
            let demand = plan.query_demands.get(set).ok_or("unknown query demand")?;
            if self.wait_for_ports(demand, Some(set))? {
                self.completion.as_mut().unwrap().stats.query_completions += 1;
            }
            return Ok(());
        }
        if !global && self.graph.scope_ready(scope)? {
            self.completion.as_mut().unwrap().stats.already_ready_waits += 1;
            return Ok(());
        }
        let changed = self.graph.changed;
        let before = self.graph.stats.unions;
        if global {
            self.completion
                .as_mut()
                .unwrap()
                .stats
                .global_observation_fences += 1;
            self.graph.repair()?;
        } else {
            self.graph.complete_scope(scope)?;
        }
        self.publish_finished_tables(before)?;
        self.graph.changed = changed;
        Ok(())
    }
    fn wait_for_ports(&mut self, demand: &[usize], query_set: Option<&str>) -> Result<bool> {
        let forecast = match self.completion.as_mut().unwrap().forecast.take() {
            Some(f) => f,
            None => self.graph.forecast_port_completion()?,
        };
        let (allowed, checks) = forecast.select(demand, false);
        let changed = self.graph.changed;
        let before = self.graph.stats.unions;
        let diagnostic = (self.progress && query_set.is_some()).then(|| {
            (
                self.graph.query_versions.clone(),
                self.graph.stats.repair_collisions,
                self.graph.stats.repaired_dependencies,
                self.graph.pending_completion_tasks(),
            )
        });
        let completed = self.graph.complete_port_selection(&allowed, checks)?;
        if completed {
            if self.progress
                && let Some(set) = query_set
            {
                let plan = self.graph.program.completion_plan.as_ref().unwrap();
                let rules = self.graph.program.sets[set]
                    .iter()
                    .filter_map(|&rid| {
                        let conflicts = forecast.conflicts(&plan.rule_demands[rid].query);
                        (!conflicts.is_empty()).then(|| json!({"rule":rid,"conflicts":conflicts}))
                    })
                    .collect::<Vec<_>>();
                let (versions, collisions, repairs, pending) = diagnostic.unwrap();
                let changed_tables = self
                    .graph
                    .query_versions
                    .iter()
                    .zip(versions)
                    .enumerate()
                    .filter_map(|(table, (&after, before))| {
                        (after != before).then_some((table, after - before))
                    })
                    .collect::<Vec<_>>();
                eprintln!(
                    "[cell-cpu] completion-query {}",
                    json!({
                        "ordinal":self.steps.len()+1,"ruleset":set,"rules":rules,
                        "effective_unions":self.graph.stats.unions-before,
                        "constructor_collisions":self.graph.stats.repair_collisions-collisions,
                        "legacy_repairs":self.graph.stats.repaired_dependencies-repairs,
                        "table_version_advances":changed_tables,"pending_before":pending,
                        "pending_after":self.graph.pending_completion_tasks(),
                    })
                );
            }
            let next = self.graph.forecast_port_completion()?;
            let (ready, checks) = next.readiness(demand);
            self.completion
                .as_mut()
                .unwrap()
                .stats
                .readiness_dependency_checks += checks;
            if !ready {
                return Err("port influence did not close a demanded scope".into());
            }
            self.completion.as_mut().unwrap().forecast = Some(next);
            self.publish_finished_tables(before)?;
        } else {
            self.completion.as_mut().unwrap().stats.already_ready_waits += 1;
            self.completion.as_mut().unwrap().forecast = Some(forecast);
        }
        self.graph.changed = changed;
        Ok(completed)
    }
    pub(super) fn wait_for_matched(&mut self, patch: &StagePatch) -> Result<()> {
        if self.completion.as_ref().is_none_or(|s| !s.port_scopes)
            || self.global_completion_observer()
            || self.graph.pending_completion_tasks() == 0
        {
            return Ok(());
        }
        let plan = self.graph.program.completion_plan.as_ref().unwrap().clone();
        let state = self.completion.as_mut().unwrap();
        state.stats.query_runs_while_pending += 1;
        state.stats.query_bindings_while_pending += patch.len as u64;
        if patch.len == 0 {
            state.stats.rhs_empty_skips += 1;
            return Ok(());
        }
        if state.pure_epochs {
            if state.forecast.is_none() {
                state.forecast = Some(self.graph.forecast_port_completion()?);
            }
            if self.admit_pure_epoch(patch)? {
                return Ok(());
            }
        }
        let state = self.completion.as_mut().unwrap();
        for (rid, _) in &patch.groups {
            state.stats.rhs_selected_rules += 1;
            for &table in &plan.rule_demands[*rid].rhs {
                state.stats.rhs_demand_probes += 1;
                if !state.rhs_seen[table] {
                    state.rhs_seen[table] = true;
                    let before = state.rhs_demand.capacity();
                    state.rhs_demand.push(table);
                    state.stats.rhs_demand_growths +=
                        u64::from(before != state.rhs_demand.capacity());
                }
            }
        }
        let mut demand = std::mem::take(&mut state.rhs_demand);
        let forecast = match state.forecast.take() {
            Some(f) => f,
            None => self.graph.forecast_port_completion()?,
        };
        if self.progress {
            let rules = patch
                .groups
                .iter()
                .map(|(rid, bindings)| {
                    json!({
                        "rule":rid,"bindings":bindings.len(),
                        "access_conflicts":forecast.conflicts(&plan.rule_demands[*rid].accesses),
                        "all_conflicts":forecast.conflicts(&plan.rule_demands[*rid].rhs),
                    })
                })
                .collect::<Vec<_>>();
            eprintln!(
                "[cell-cpu] completion-rhs {}",
                json!({"ordinal":self.steps.len()+1,"ruleset":self.current_stage,"rules":rules})
            );
        }
        let mut access_ready = true;
        let mut checks = 0;
        for (rid, _) in &patch.groups {
            let (ready, cost) = forecast.readiness(&plan.rule_demands[*rid].accesses);
            checks += cost;
            if !ready {
                access_ready = false;
                break;
            }
        }
        let state = self.completion.as_mut().unwrap();
        state.forecast = Some(forecast);
        state.stats.readiness_dependency_checks += checks;
        state.matched = true;
        state.stats.peak_matched_origin_slots = state
            .stats
            .peak_matched_origin_slots
            .max(self.stage_spine.matched_origin_slots());
        self.stage_spine.retain_matched_origins(true);
        let result = self.wait_for_ports(&demand, None);
        self.stage_spine.retain_matched_origins(false);
        let state = self.completion.as_mut().unwrap();
        state.matched = false;
        for &table in &demand {
            state.rhs_seen[table] = false;
        }
        demand.clear();
        state.rhs_demand = demand;
        if result? {
            state.stats.rhs_completions += 1;
            if access_ready {
                state.stats.rhs_union_completions += 1;
            } else {
                state.stats.rhs_access_completions += 1;
            }
        }
        Ok(())
    }
    pub(super) fn complete_source_run(&mut self, rhs_started_with_pending: bool) -> Result<()> {
        if self.completion.is_none() || self.global_completion_observer() {
            if let Some(state) = &mut self.completion {
                state.stats.global_observation_fences += 1;
            }
            self.graph.repair()?;
        } else if self.completion.as_ref().unwrap().port_scopes {
            let before = self.graph.stats.unions;
            self.graph.commit_scoped_unions()?;
            if rhs_started_with_pending {
                self.completion
                    .as_mut()
                    .unwrap()
                    .stats
                    .source_unions_while_pending += self.graph.stats.unions - before;
            }
            if self.graph.pending_completion_tasks() == 0 {
                self.completion.as_mut().unwrap().forecast = None;
            } else if !self.graph.changed && self.completion.as_ref().unwrap().forecast.is_some() {
                self.completion
                    .as_mut()
                    .unwrap()
                    .stats
                    .unchanged_influence_reuses += 1;
            } else {
                let forecast = self.graph.forecast_port_completion()?;
                let (allowed, checks) = forecast.select(&[], true);
                let completed = self.graph.complete_port_selection(&allowed, checks)?;
                let forecast = if completed && self.graph.pending_completion_tasks() > 0 {
                    self.graph.forecast_port_completion()?
                } else {
                    forecast
                };
                if self.graph.pending_completion_tasks() > 0 {
                    if forecast.has_ordered_tasks() {
                        return Err("port influence left an ordered effect pending".into());
                    }
                    self.completion.as_mut().unwrap().forecast = Some(forecast);
                } else {
                    self.completion.as_mut().unwrap().forecast = None;
                }
            }
        } else if !self.completion.as_ref().unwrap().can_defer {
            // The checked plan admits no deferred tasks. Specialize away all
            // per-Run scope construction and membership probes for this case.
            self.completion
                .as_mut()
                .unwrap()
                .stats
                .compiler_full_completion_runs += 1;
            self.graph.repair()?;
        } else {
            self.graph.commit_scoped_unions()?;
            self.completion.as_mut().unwrap().stats.eager_waits += 1;
            self.graph
                .complete_eager_scope(&self.completion.as_ref().unwrap().eager)?;
        }
        if self.graph.pending_completion_tasks() == 0 {
            self.graph.ownership_barrier();
        }
        Ok(())
    }
    /// Complete final/global observations explicitly. A checkpoint intentionally
    /// retains outstanding work; callers can request this before inspecting it.
    pub fn finish_completion(&mut self) -> Result<()> {
        if self.completion.is_none() {
            return Ok(());
        }
        if self.graph.pending_completion_tasks() == 0
            && self.graph.changes.is_empty()
            && self.stage_spine.pending_publication_counts().0 == 0
        {
            return Ok(());
        }
        let before = self.graph.stats.unions;
        self.graph.repair()?;
        self.publish_finished_tables(before)?;
        Ok(())
    }
    pub(super) fn publish_finished_tables(&mut self, unions_before: u64) -> Result<(f64, f64)> {
        let partial = self.completion.is_some() && self.graph.pending_completion_tasks() > 0;
        let (ready, checks) = if partial {
            let (ready, checks) = if self.completion.as_ref().unwrap().port_scopes {
                self.completion
                    .as_ref()
                    .unwrap()
                    .forecast
                    .as_ref()
                    .ok_or("missing publication influence proof")?
                    .ready_tables()
            } else {
                self.graph.completion_ready_tables()
            };
            (Some(ready), checks)
        } else {
            (None, 0)
        };
        if let Some(ready) = &ready {
            let state = self.completion.as_mut().unwrap();
            state.stats.partial_publications += 1;
            state.stats.readiness_dependency_checks += checks;
            let (moved, checked) = self.graph.changes.defer_unready(ready, &mut state.deferred);
            state.stats.publication_table_checks += checked as u64;
            state.stats.deferred_rows_carried += moved as u64;
            state.stats.peak_retained_changes = state.stats.peak_retained_changes.max(moved);
            state.stats.published_tables_while_pending +=
                self.graph.changes.tables().count() as u64;
        }
        let result = self.publish_batch(ready.as_deref(), unions_before);
        if let Some(state) = &mut self.completion {
            if partial {
                std::mem::swap(&mut self.graph.changes, &mut state.deferred);
            }
            let (anchors, contexts) = self.stage_spine.pending_publication_counts();
            state.stats.peak_retained_anchors = state.stats.peak_retained_anchors.max(anchors);
            state.stats.peak_retained_contexts = state.stats.peak_retained_contexts.max(contexts);
            state.stats.peak_retained_forwards = state
                .stats
                .peak_retained_forwards
                .max(self.graph.receipt_forwards.len());
        }
        result
    }
    fn publish_batch(&mut self, ready: Option<&[bool]>, _unions_before: u64) -> Result<(f64, f64)> {
        let phase = Instant::now();
        if let Some(ready) = ready {
            self.stage_spine.publish_selected(
                &mut self.graph,
                #[cfg(feature = "sparse-cells")]
                &mut self.entry_schedule,
                ready,
            )?;
        } else {
            #[cfg(feature = "sparse-cells")]
            self.stage_spine
                .publish_to_entries(&mut self.graph, &mut self.entry_schedule)?;
            #[cfg(not(feature = "sparse-cells"))]
            self.stage_spine.publish(&mut self.graph)?;
        }
        #[cfg(feature = "structural-depth")]
        self.stage_spine.structural.publish(&mut self.graph)?;
        #[cfg(feature = "view-consumers")]
        self.entry_schedule
            .publish_except(&self.graph, |t| self.blocks.dedicated(t));
        #[cfg(not(feature = "view-consumers"))]
        self.entry_schedule.publish(&self.graph);
        #[cfg(feature = "sparse-cells")]
        self.stage_spine.refresh_entry_owners(&self.entry_schedule);
        let matched = self.completion.as_ref().is_some_and(|s| s.matched);
        if !matched && self.stage_spine.pending_publication_counts().0 == 0 {
            self.graph.receipt_forwards.clear();
        }
        self.publication.publish(
            #[cfg(feature = "family-survey")]
            (&mut self.survey, _unions_before != self.graph.stats.unions),
            &self.graph,
            &mut self.query_indexes,
            self.range_index.as_mut(),
            &mut self.neighbor,
            |_table, _changes, _indexed| {
                #[cfg(feature = "view-consumers")]
                self.blocks
                    .publish_table(&self.graph, _table, _changes, _indexed);
            },
        )?;
        #[cfg(feature = "projection-semijoin")]
        self.free_join
            .gates
            .publish(&self.graph, &self.query_indexes);
        self.sieve.publish(&mut self.query_indexes);
        let publication_end = Instant::now();
        let query_update_seconds = publication_end.duration_since(phase).as_secs_f64();
        let phase = publication_end;
        self.deliver();
        #[cfg(feature = "rhs-work-audit")]
        self.ledger.barrier(
            &self.graph,
            self.publication.index_writes(),
            self.entry_schedule.seed_deliveries(),
        );
        #[cfg(feature = "family-replay")]
        self.replay
            .publish(&self.graph, _unions_before != self.graph.stats.unions)?;
        self.graph.changes.clear();
        if !matched {
            self.graph.collect_garbage();
        }
        let end = Instant::now();
        let delivery_seconds = end.duration_since(phase).as_secs_f64();
        Ok((query_update_seconds, delivery_seconds))
    }
}
