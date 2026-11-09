//! Authoritative stable fields for covered scalar constructors. Canonical
//! values are temporary read views; equality propagation never rewrites them
//! into the stored node. Optional port-key matching uses immutable birth hints
//! and complete symbolic domains; scoped completion remains a separate step.
use super::*;
#[path = "local_port_conditions.rs"]
mod conditions;
#[path = "port_guard.rs"]
pub mod guard;
#[path = "port_keys.rs"]
mod keys;
#[path = "unique_port_publication.rs"]
mod publication;

/// A shared symbolic address. Component IDs are monotonic and never recycled;
/// a retired address is rejected rather than rebound to a later instance.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct PortRef {
    pub component: u32,
    pub symbol: usize,
}
impl From<Signal> for PortRef {
    fn from(s: Signal) -> Self {
        Self {
            component: s.component,
            symbol: s.symbol,
        }
    }
}
impl From<PortRef> for Signal {
    fn from(p: PortRef) -> Self {
        Self {
            component: p.component,
            symbol: p.symbol,
        }
    }
}
#[derive(Clone, Debug)]
enum Field {
    Port(PortRef),
    Scalar(Value),
}
#[derive(Clone, Debug)]
pub struct Stored {
    pub(super) table: usize,
    fields: Vec<Field>,
}
#[derive(Default, Serialize)]
pub(in crate::graph) struct Runtime {
    keys: bool,
    #[serde(skip)]
    unique: Option<publication::Counts>,
    #[serde(skip)]
    conditions: Option<conditions::Stats>,
    #[serde(skip)]
    parallel: Option<conditions::parallel::Runtime>,
    key_lookups: Counter<u64>,
    key_candidates: Counter<u64>,
    key_field_comparisons: Counter<u64>,
    pending_candidate_skips: Counter<u64>,
    birth_hint_probes: Counter<u64>,
    birth_hint_hits: Counter<u64>,
    port_domain_probes: Counter<u64>,
    equality_enqueues: u64,
    equality_completions: u64,
    rows_installed: u64,
    ports_installed: u64,
    row_views: Counter<u64>,
    port_reads: Counter<u64>,
    root_resolutions: Counter<u64>,
    notifications: u64,
    notified_columns: u64,
    legacy_key_enqueues: u64,
    result_publications: u64,
}
impl Graph {
    pub fn new_with_stable_ports(p: Program) -> Result<Self> {
        let mut g = Self::new_with_cell_ownership(p)?;
        g.use_stable_port_fields()?;
        Ok(g)
    }
    pub fn use_stable_port_fields(&mut self) -> Result<()> {
        if self.stable_ports.is_some() {
            return Ok(());
        }
        if !self.ownership_enabled() {
            return Err("stable fields require Cell ownership".into());
        }
        if !self.ownership_settled() || !self.pending_unions.is_empty() || !self.dirty.is_empty() {
            return Err("enable stable fields at a settled boundary".into());
        }
        self.stable_ports = Some(Runtime::default());
        let facts = self
            .cells
            .iter()
            .flat_map(|(&cell, c)| {
                c.facts
                    .iter()
                    .filter(|(_, s)| s.owned)
                    .map(move |(&op, _)| FactRef { cell, op })
            })
            .collect::<Vec<_>>();
        for f in facts {
            let row = self.fact(f)?.ok_or("missing initial owned fact")?;
            self.store_stable_fields(f, row.table, &row.values);
        }
        Ok(())
    }
    pub(in crate::graph) fn store_stable_fields(
        &mut self,
        f: FactRef,
        table: usize,
        values: &[Value],
    ) {
        if self.stable_ports.is_none() {
            return;
        }
        let template = self.cells[&f.cell].template;
        let symbols = &self.program.cell_ownership.markers[template].program.fields[f.op as usize];
        let mut count = 0;
        let fields = values
            .iter()
            .zip(symbols)
            .map(|(v, symbol)| {
                if let Some(symbol) = symbol {
                    assert!(matches!(v, Value::Eq(_)), "typed equality field");
                    count += 1;
                    Field::Port(self.composed_signal(f.cell, *symbol).into())
                } else {
                    assert!(
                        !matches!(v, Value::Eq(_) | Value::Set(_)),
                        "scalar ownership field"
                    );
                    Field::Scalar(v.clone())
                }
            })
            .collect::<Vec<_>>();
        assert_eq!(fields.len(), values.len());
        let state = self
            .cells
            .get_mut(&f.cell)
            .unwrap()
            .facts
            .get_mut(&f.op)
            .unwrap();
        assert!(
            state.ports.is_none(),
            "stable representation installed once per fact incarnation"
        );
        state.ports = Some(Rc::new(Stored { table, fields }));
        state.decoded = None;
        let stats = self.stable_ports.as_mut().unwrap();
        stats.rows_installed += 1;
        stats.ports_installed += count;
    }
    fn port_value(&self, port: PortRef, meter: bool) -> Result<Value> {
        let binding = self
            .ownership
            .as_ref()
            .and_then(|m| m.composition.components.get(port.component as usize))
            .and_then(Option::as_ref)
            .and_then(|c| c.signals.get(port.symbol))
            .copied()
            .flatten()
            .ok_or("expired stable port")?;
        if meter {
            let stats = self.stable_ports.as_ref().ok_or("stable fields disabled")?;
            stats.port_reads.set(stats.port_reads.get() + 1);
            stats.root_resolutions.set(stats.root_resolutions.get() + 1);
        }
        Ok(Value::Eq(root(&self.parents, binding)))
    }
    pub fn read_port(&self, port: PortRef) -> Result<Value> {
        self.port_value(port, true)
    }
    pub fn fact_port(&self, f: FactRef, column: usize) -> Option<PortRef> {
        let fields = &self
            .cells
            .get(&f.cell)?
            .facts
            .get(&f.op)?
            .ports
            .as_ref()?
            .fields;
        match fields.get(column)? {
            Field::Port(p) => Some(*p),
            Field::Scalar(_) => None,
        }
    }
    fn stable_field_value(&self, field: &Field, meter: bool) -> Result<Value> {
        match field {
            Field::Port(p) => self.port_value(*p, meter),
            Field::Scalar(v) => Ok(v.clone()),
        }
    }
    pub(in crate::graph) fn read_stable_column(
        &self,
        stored: &Stored,
        col: usize,
    ) -> Result<Value> {
        self.stable_field_value(stored.fields.get(col).ok_or("stable field column")?, true)
    }
    pub(in crate::graph) fn stable_values(
        &self,
        stored: &Stored,
        meter: bool,
    ) -> Result<RowFields> {
        if meter {
            let stats = self.stable_ports.as_ref().ok_or("stable fields disabled")?;
            stats.row_views.set(stats.row_views.get() + 1);
        }
        stored
            .fields
            .iter()
            .map(|field| self.stable_field_value(field, meter))
            .collect::<Result<Vec<_>>>()
            .map(row_fields)
    }
    pub(in crate::graph) fn read_stable_fact(
        &self,
        f: FactRef,
        state: &FactState,
        stored: &Stored,
    ) -> Result<Row> {
        Ok(Row {
            table: stored.table,
            values: self.stable_values(stored, true)?,
            hidden: state.hidden,
            epoch: state.epoch,
            witness: Dependency::Fact(f),
        })
    }
    /// Existing shared slices identify the changed columns. No stored field
    /// needs an Eq(from) comparison or an Eq(to) write. Changed inputs enqueue
    /// either canonical key work or an exact port-equality obligation.
    pub(in crate::graph) fn notify_stable_fields(
        &mut self,
        f: FactRef,
        columns: &[usize],
        changed_root: u64,
    ) -> bool {
        let Some(stored) = self
            .cells
            .get(&f.cell)
            .and_then(|c| c.facts.get(&f.op))
            .and_then(|s| s.ports.as_ref())
        else {
            return false;
        };
        if columns.is_empty() {
            return true;
        }
        let table = stored.table;
        let port_key = self.port_keys_enabled(table);
        // Dispatch coalesces disjoint columns from several signals, so their
        // concatenation need not be sorted.
        let key = columns.iter().any(|&i| i + 1 < stored.fields.len());
        if port_key && key && self.unique_port_input(f, columns) {
            let stats = self.stable_ports.as_mut().unwrap();
            stats.notifications += 1;
            stats.notified_columns += columns.len() as u64;
            self.publish_unique_port(f, table);
            return true;
        }
        let state = self
            .cells
            .get_mut(&f.cell)
            .unwrap()
            .facts
            .get_mut(&f.op)
            .unwrap();
        let singleton = !port_key
            && self
                .intern
                .get(&state.hash)
                .is_some_and(|bucket| bucket.len() == 1 && bucket.first() == Some(&f));
        let m = self.ownership.as_mut().unwrap();
        let stats = self.stable_ports.as_mut().unwrap();
        stats.notifications += 1;
        stats.notified_columns += columns.len() as u64;
        if !key && (port_key || singleton) && !m.pending.contains(table, &f) {
            state.epoch = self.epoch;
            self.query_versions[table] += 1;
            self.changes.touch(table, Dependency::Fact(f));
            m.stats.result_publications += 1;
            stats.result_publications += 1;
        } else {
            let added = u64::from(m.pending.insert(table, f, self.epoch));
            m.pending.cause(table, changed_root);
            m.stats.key_enqueues += added;
            if port_key {
                stats.equality_enqueues += added;
            } else {
                stats.legacy_key_enqueues += added;
            }
            self.dirty_facts[table].insert(f);
        }
        true
    }
    pub fn stable_port_report(&self) -> J {
        let Some(stats) = &self.stable_ports else {
            return json!({"enabled":false});
        };
        let mut nodes = 0;
        let mut ports = 0;
        for (_, cell) in self.cells.iter() {
            for (_, fact) in cell.facts.iter() {
                if let Some(row) = &fact.ports {
                    assert!(fact.owned && fact.decoded.is_none());
                    nodes += 1;
                    ports += row
                        .fields
                        .iter()
                        .filter(|f| matches!(f, Field::Port(_)))
                        .count();
                } else {
                    assert!(!fact.owned, "owned fact lacks its stable representation");
                }
            }
        }
        let indexed_port_keys = self
            .intern
            .values()
            .flat_map(|b| b.iter())
            .filter(|&&f| {
                self.dependency_table(Dependency::Fact(f))
                    .is_some_and(|t| self.port_keys_enabled(t))
            })
            .count();
        let port_key_facts = self
            .program
            .tables
            .iter()
            .enumerate()
            .filter(|(t, _)| self.port_keys_enabled(*t))
            .map(|(t, _)| self.witness_count(t))
            .sum::<usize>();
        assert_eq!(
            indexed_port_keys, port_key_facts,
            "immutable birth hints follow fact lifetime only"
        );
        let pending_canonical_keys = self
            .ownership
            .as_ref()
            .unwrap()
            .pending
            .iter()
            .filter(|&&f| {
                self.dependency_table(Dependency::Fact(f))
                    .is_some_and(|t| !self.port_keys_enabled(t))
            })
            .count();
        json!({"enabled":true,"scope":"standalone Cell CPU; stable stored fields; global Run barrier still enabled",
            "stats":stats,"unique_publication":self.unique_publication_report(),"local_conditions":self.local_condition_report(),"parallel_guards":self.parallel_guard_report(),"live_stable_nodes":nodes,"live_port_fields":ports,
            "birth_indexed_port_keys":indexed_port_keys,"port_key_matching":stats.keys,
            "pending_canonical_keys":pending_canonical_keys,
            "pending_port_equality_checks":self.ownership.as_ref().unwrap().pending.len()-pending_canonical_keys})
    }
}
