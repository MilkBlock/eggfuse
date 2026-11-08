//! Execute compiler-derived local congruence conditions. No satisfied-condition
//! cache or per-instance reverse graph is maintained. Each visit checks current
//! fact liveness; the queue contains facts, not stale condition incarnations.
use super::*;
use composition::conditions::{Condition, Plan};

#[derive(Default, Serialize)]
pub(super) struct Stats {
    pub attempts: u64,
    pub uncovered_shapes: u64,
    pub boundary_signals: u64,
    pub boundary_sites: u64,
    pub open_fallbacks: u64,
    pub closed_regions: u64,
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

impl Graph {
    pub fn new_with_local_congruence(p: Program) -> Result<Self> {
        let mut graph = Self::new_with_port_keys(p)?;
        graph.use_local_port_conditions()?;
        Ok(graph)
    }
    pub fn use_local_port_conditions(&mut self) -> Result<()> {
        self.use_port_constructor_matching()?;
        let plan = &mut self.program.cell_ownership;
        plan.composition.prepare_conditions(&plan.programs);
        self.stable_ports
            .as_mut()
            .unwrap()
            .conditions
            .get_or_insert_with(Stats::default);
        Ok(())
    }
    /// Some(None) proves that the complete local condition set has no collision.
    /// None means coverage is open; the complete port domain must still run.
    pub(super) fn local_port_collision(
        &mut self,
        f: FactRef,
        row: &Row,
    ) -> Result<Option<Option<Row>>> {
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
        let column = self.program.repair_ports.key_eq_columns[row.table]
            .as_ref()
            .unwrap()[0];
        let Value::Eq(id) = row.values[column] else {
            return Err("typed input port".into());
        };
        let (closed, signals, sites) =
            self.local_domain_closed(frame.component, row.table, column, id)?;
        self.local_condition_stats().boundary_signals += signals;
        self.local_condition_stats().boundary_sites += sites;
        if !closed {
            self.local_condition_stats().open_fallbacks += 1;
            return Ok(None);
        }
        self.local_condition_stats().closed_regions += 1;
        for &id in &plan.routes[site] {
            self.local_condition_stats().condition_visits += 1;
            let condition = &plan.conditions[id];
            let other = condition.sites[usize::from(condition.sites[0] == site)];
            let peer = &plan.sites[other];
            let cell = self.ownership.as_ref().unwrap().composition.components
                [frame.component as usize]
                .as_ref()
                .unwrap()
                .frames[peer.frame];
            let target = FactRef { cell, op: peer.op };
            let Some(state) = self.cells.get(&cell).and_then(|c| c.facts.get(&peer.op)) else {
                self.local_condition_stats().inactive_sites += 1;
                continue;
            };
            let Some(stored) = state.ports.clone() else {
                self.local_condition_stats().inactive_sites += 1;
                continue;
            };
            if self.ownership.as_ref().unwrap().pending.contains(&target) {
                self.local_condition_stats().pending_sites += 1;
                continue;
            }
            self.local_condition_stats().operator_guards += 1;
            if stored.table != row.table {
                continue;
            }
            if !self.local_condition_holds(frame.component, condition, &stored, row)? {
                continue;
            }
            self.local_condition_stats().completed_conditions += 1;
            self.local_condition_stats().cross_stage_conditions +=
                u64::from(self.cells[&f.cell].started_epoch != self.cells[&cell].started_epoch);
            // The logical commit consumes the result ports through the row
            // interface, preserving visibility, receipts and ordered retirement.
            let state = &self.cells[&cell].facts[&peer.op];
            return self
                .read_stable_fact(target, state, &stored)
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
    fn local_domain_closed(
        &self,
        component: u32,
        table: usize,
        column: usize,
        id: u64,
    ) -> Result<(bool, u64, u64)> {
        // Root-level boundary ownership already belongs to symbolic ports.
        // Probe shared code; no producer gets a runtime consumer list.
        let m = self.ownership.as_ref().unwrap();
        let signals = m
            .boundaries
            .get(&id)
            .into_iter()
            .flat_map(|s| s.iter().copied())
            .chain(self.native_signal(id));
        let mut signal_visits = 0;
        let mut site_visits = 0;
        for signal in signals {
            signal_visits += 1;
            if signal.component == component {
                continue;
            }
            let other = m.composition.components[signal.component as usize]
                .as_ref()
                .ok_or("expired boundary component")?;
            let Some(plan) = self
                .program
                .cell_ownership
                .composition
                .conditions
                .get(other.shape)
                .filter(|p| p.complete)
            else {
                return Ok((false, signal_visits, site_visits));
            };
            for &(site, input) in &plan.inputs[signal.symbol] {
                if input != column {
                    continue;
                }
                let body = &plan.sites[site];
                let cell = other.frames[body.frame];
                site_visits += 1;
                if self
                    .cells
                    .get(&cell)
                    .and_then(|c| c.facts.get(&body.op))
                    .and_then(|s| s.ports.as_ref())
                    .is_some_and(|s| s.table == table)
                {
                    return Ok((false, signal_visits, site_visits));
                }
            }
        }
        // Every fact in an admitted table is owned. Legacy reverse users must
        // belong to other tables and cannot be constructor-key candidates.
        Ok((true, signal_visits, site_visits))
    }
    fn local_condition_holds(
        &mut self,
        component: u32,
        c: &Condition,
        target: &Stored,
        source: &Row,
    ) -> Result<bool> {
        for &column in &c.scalar_columns {
            self.local_condition_stats().scalar_guards += 1;
            if self.stable_field_value(&target.fields[column], true)? != source.values[column] {
                return Ok(false);
            }
        }
        for &[a, b] in &c.equality_inputs {
            if a == b {
                self.local_condition_stats().shared_symbol_guards += 1;
                continue;
            }
            self.local_condition_stats().equality_guards += 1;
            if self.read_port(PortRef {
                component,
                symbol: a,
            })? != self.read_port(PortRef {
                component,
                symbol: b,
            })? {
                return Ok(false);
            }
        }
        Ok(true)
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
            "scope":"shared local all-input guards with exact boundary exclusion; global Run barrier remains"})
    }
}
