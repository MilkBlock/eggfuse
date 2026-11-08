//! Completion waits are explicit, compiler-checked scopes. Connectivity commits
//! remain monotone; a false readiness answer means unknown, not inequality.
use super::*;
use crate::completion_plan::{Plan, Scope};
use std::rc::Rc;

impl Graph {
    pub fn new_with_scoped_completion(program: Program) -> Result<Self> {
        let mut graph = Self::new_with_local_congruence(program)?;
        graph.use_scoped_completion()?;
        Ok(graph)
    }
    pub fn use_scoped_completion(&mut self) -> Result<()> {
        self.use_local_port_conditions()?;
        if self.ownership.as_ref().unwrap().pending.scoped() {
            return Ok(());
        }
        if !self.pending_unions.is_empty()
            || !self.dirty.is_empty()
            || !self.dirty_markers.is_empty()
            || !self.ownership_settled()
        {
            return Err("enable scoped completion at a settled boundary".into());
        }
        self.program.completion_plan = Some(Rc::new(Plan::derive(&self.program)?));
        self.ownership
            .as_mut()
            .unwrap()
            .pending
            .enable_scopes(self.program.tables.len());
        Ok(())
    }
    pub fn completion_scope(&self, tables: &[usize]) -> Result<Scope> {
        self.program
            .completion_plan
            .as_ref()
            .ok_or("scoped completion disabled")?
            .scope(tables)
    }
    pub fn scope_ready(&self, scope: &Scope) -> Result<bool> {
        self.program
            .completion_plan
            .as_ref()
            .ok_or("scoped completion disabled")?
            .validate(scope)?;
        if !self.pending_unions.is_empty() {
            return Ok(false);
        }
        if self
            .ownership
            .as_ref()
            .unwrap()
            .pending
            .first(Some(&scope.predecessors))
            .is_some()
        {
            return Ok(false);
        }
        Ok(!self
            .dirty
            .iter()
            .copied()
            .chain(self.dirty_markers.iter().copied().map(Dependency::Fact))
            .any(|d| {
                self.dependency_table(d)
                    .is_none_or(|t| scope.predecessors[t])
            }))
    }
    pub fn complete_scope(&mut self, scope: &Scope) -> Result<()> {
        self.program
            .completion_plan
            .as_ref()
            .ok_or("scoped completion disabled")?
            .validate(scope)?;
        self.ownership
            .as_mut()
            .unwrap()
            .pending
            .counts
            .scope_requests += 1;
        let epoch = self.epoch;
        let result = self.repair_selected(Some(&scope.predecessors));
        self.epoch = epoch;
        result?;
        assert!(
            self.scope_ready(scope)?,
            "scoped completion left an influencing obligation"
        );
        let remaining = self.pending_completion_tasks() as u64;
        self.ownership
            .as_mut()
            .unwrap()
            .pending
            .counts
            .bypassed_tasks += remaining;
        Ok(())
    }
    /// Commit explicit source connectivity without draining constructor work.
    /// The caller must require readiness before any dependent observation.
    pub fn commit_scoped_unions(&mut self) -> Result<()> {
        if !self.ownership.as_ref().is_some_and(|m| m.pending.scoped()) {
            return Err("scoped completion disabled".into());
        }
        for (a, b) in std::mem::take(&mut self.pending_unions) {
            self.union(a, b)?;
        }
        Ok(())
    }
    pub(crate) fn complete_eager_scope(&mut self, eager: &Scope) -> Result<()> {
        // Legacy tasks do not carry an originating epoch. Complete their full
        // dependency footprint before crossing a source occurrence.
        if self.dirty.is_empty() && self.dirty_markers.is_empty() {
            return self.complete_scope(eager);
        }
        let mut tables = eager.tables().to_vec();
        tables.extend(
            self.dirty
                .iter()
                .copied()
                .chain(self.dirty_markers.iter().copied().map(Dependency::Fact))
                .filter_map(|d| self.dependency_table(d)),
        );
        tables.sort_unstable();
        tables.dedup();
        let scope = self.completion_scope(&tables)?;
        self.complete_scope(&scope)
    }
    pub fn pending_completion_tasks(&self) -> usize {
        self.pending_unions.len()
            + self.dirty.len()
            + self.dirty_markers.len()
            + self.ownership.as_ref().map_or(0, |m| m.pending.len())
    }
    /// A table is publishable only if no outstanding task can affect it.
    /// Compute this from table heads and compiler reachability, not fact scans.
    pub(crate) fn completion_ready_tables(&self) -> (Vec<bool>, u64) {
        assert!(self.pending_unions.is_empty());
        let plan = self.program.completion_plan.as_ref().unwrap();
        let mut ready = vec![true; self.program.tables.len()];
        let mut checks = 0;
        for t in self
            .ownership
            .as_ref()
            .unwrap()
            .pending
            .active_tables()
            .chain(
                self.dirty
                    .iter()
                    .copied()
                    .chain(self.dirty_markers.iter().copied().map(Dependency::Fact))
                    .filter_map(|d| self.dependency_table(d)),
            )
        {
            for (other, yes) in ready.iter_mut().enumerate() {
                checks += 1;
                *yes &= !plan.affects(t, other);
            }
        }
        (ready, checks)
    }
    pub fn scoped_completion_report(&self) -> J {
        let Some(plan) = &self.program.completion_plan else {
            return json!({"enabled":false});
        };
        let pending = &self.ownership.as_ref().unwrap().pending;
        json!({"enabled":true,"plan":plan.report(),"stats":pending.counts,
            "pending_tasks":self.pending_completion_tasks(),
            "pending_owned_tables":pending.active_tables().collect::<Vec<_>>(),
            "scope":"compiler-scoped Graph completion; Executor mode reported separately"})
    }
    pub(super) fn next_scoped_dirty(&mut self, allowed: Option<&[bool]>) -> Option<Dependency> {
        let Some(allowed) = allowed else {
            return self.dirty.first().copied();
        };
        let mut probes = 0;
        let next = self.dirty.iter().copied().find(|&d| {
            probes += 1;
            self.dependency_table(d).is_none_or(|t| allowed[t])
        });
        self.ownership
            .as_mut()
            .unwrap()
            .pending
            .counts
            .legacy_frontier_probes += probes;
        next
    }
    pub(super) fn pending_opaque_completion(&self, allowed: &[bool]) -> bool {
        let opaque = &self.program.completion_plan.as_ref().unwrap().opaque_tables;
        self.dirty
            .iter()
            .copied()
            .chain(self.dirty_markers.iter().copied().map(Dependency::Fact))
            .filter_map(|d| self.dependency_table(d))
            .any(|t| allowed[t] && opaque.contains(&t))
            || self
                .ownership
                .as_ref()
                .unwrap()
                .pending
                .active_tables()
                .any(|t| allowed[t] && opaque.contains(&t))
    }
    pub(super) fn note_opaque_completion(&mut self) {
        self.ownership
            .as_mut()
            .unwrap()
            .pending
            .counts
            .opaque_full_completions += 1;
    }
    pub(super) fn next_scoped_marker(&mut self, allowed: Option<&[bool]>) -> Option<FactRef> {
        let Some(allowed) = allowed else {
            return self.dirty_markers.first().copied();
        };
        let mut probes = 0;
        let next = self.dirty_markers.iter().copied().find(|&f| {
            probes += 1;
            self.dependency_table(Dependency::Fact(f))
                .is_none_or(|t| allowed[t])
        });
        self.ownership
            .as_mut()
            .unwrap()
            .pending
            .counts
            .legacy_frontier_probes += probes;
        next
    }
}
