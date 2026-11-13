//! Authoritative stable fields for covered scalar constructors. Canonical
//! values are temporary read views; equality propagation never rewrites them
//! into the stored node. Optional port-key matching uses immutable birth hints
//! and complete symbolic domains; scoped completion remains a separate step.
use super::*;
use std::borrow::Cow;
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
#[derive(Clone, Debug)]
enum Field {
    Port(PortRef),
    Scalar(Value),
}
impl Field {
    fn value(&self, port: impl FnOnce(PortRef) -> Result<Value>) -> Result<Value> {
        match self {
            Self::Scalar(value) => Ok(value.clone()),
            Self::Port(p) => port(*p),
        }
    }
}
/// Only dynamic scalar values belong to an instance. Equality field locations
/// are shared Bake wiring; composition preserves its old prefix without copying.
#[derive(Clone, Debug)]
struct Fields {
    component: u32,
    operation: u32,
    frame: usize,
    scalars: Box<[Value]>,
}
/// A short borrowed projection of the existing Cell definition. Nodes do not
/// own per-fact copies of the program/port-map handles.
struct FieldView<'a> {
    component: u32,
    columns: &'a [Option<usize>],
    ports: &'a [usize],
    scalars: &'a [Value],
}
impl FieldView<'_> {
    fn len(&self) -> usize { self.columns.len() }
    fn get(&self, column: usize) -> Option<Field> {
        Some(match *self.columns.get(column)? {
            Some(local) => Field::Port(PortRef { component: self.component, symbol: self.ports[local] }),
            None => {
                let index = self.columns[..column].iter().filter(|s|s.is_none()).count();
                Field::Scalar(self.scalars[index].clone())
            }
        })
    }
    fn iter(&self) -> impl Iterator<Item = Field> + '_ {
        (0..self.len()).map(|i| self.get(i).unwrap())
    }
    fn last(&self) -> Option<Field> { self.get(self.len().checked_sub(1)?) }
}

#[derive(Clone, Debug)]
pub struct Stored {
    pub(super) table: usize,
    fields: Fields,
}
#[derive(Default, Serialize)]
pub(in crate::graph) struct Runtime {
    keys: bool,
    pub(super) template_fields: bool,
    /// Materialized stable fields. Template projection leaves only scalar-bearing
    /// records here; its borrowed workers use the existing sparse Cell lifecycle.
    #[serde(skip)]
    pub(super) nodes: crate::read_epoch::Map<FactRef, Stored>,
    node_lookups: Counter<u64>,
    template_node_projections: Counter<u64>,
    field_layout_reads: Counter<u64>,
    node_retirement_probes: u64,
    nodes_retired: u64,
    #[serde(skip)]
    unique: Option<publication::Counts>,
    #[serde(skip)]
    conditions: Option<conditions::Stats>,
    #[serde(skip)]
    parallel: Option<conditions::parallel::Runtime>,
    #[serde(skip)]
    batches: Option<conditions::batches::Runtime>,
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
    root_parent_probes: Counter<u64>,
    notifications: u64,
    notified_columns: u64,
    legacy_key_enqueues: u64,
    result_publications: u64,
}
impl Graph {
    /// Experimental direct projection. Plain borrowed workers are supported;
    /// overlapping mutation requires an independent frozen lifecycle view.
    #[cfg(feature="sparse-cells")]
    pub fn use_template_stable_fields(&mut self) -> Result<()> {
        self.use_stable_port_fields()?;
        if self.active_rhs.is_some() || !self.ownership_settled() || !self.pending_unions.is_empty() || !self.dirty.is_empty() {
            return Err("template fields require a settled source boundary".into());
        }
        let runtime = self.stable_ports.as_ref().unwrap();
        if runtime.batches.is_some() { return Err("template fields do not yet support completion batches".into()); }
        if runtime.template_fields { return Ok(()); }
        let remove = self.cells.cell_ids().flat_map(|id| self.cells.fact_states(id).map(|(f,_)|f))
            .filter(|f| runtime.nodes.get(f).is_some_and(|node|node.fields.scalars.is_empty()))
            .collect::<Vec<_>>();
        let runtime = self.stable_ports.as_mut().unwrap();
        for fact in remove { runtime.nodes.remove(&fact); }
        runtime.nodes.compact();
        runtime.template_fields = true;
        Ok(())
    }
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
            .flat_map(|(&cell, _)| self.cells.fact_states(cell)
                .filter(|(_,s)|s.owned).map(|(f,_)|f))
            .collect::<Vec<_>>();
        for f in facts {
            let row = self.fact(f)?.ok_or("missing initial owned fact")?;
            self.initialize_cell_fields::<false>(f, row.table, &row.values);
        }
        Ok(())
    }
    /// A new owned fact binds its shared symbols and installs its fields in one
    /// pass. Enabling stable representation projects the same layout without
    /// binding those symbols or advancing the component lifetime again.
    pub(super) fn initialize_cell_fields<const BIND: bool>(
        &mut self,
        f: FactRef,
        table: usize,
        values: &[Value],
    ) {
        if BIND {
            self.ensure_composition_frame(f.cell);
        }
        let owner = self.ownership.as_mut().unwrap();
        let frame = owner.composition.frames[&f.cell];
        if BIND {
            owner.composition.live_facts[frame.component as usize] += 1;
            owner.stats.component_lifetime_updates += 1;
        }
        let component = owner.composition.components[frame.component as usize]
            .as_ref().unwrap();
        // Clone only shared code handles so binding can mutate the instance.
        // The frame/shape map is resolved once, not once per equality column.
        let ports = owner.composition.shapes[component.shape].as_ref().unwrap().ports
            [frame.ordinal].clone();
        let program = self.program.cell_ownership.code_programs[frame.code].clone();
        let symbols = &program.fields[f.op as usize];
        assert_eq!(symbols.len(), values.len());
        let mut scalars = self.stable_ports.as_ref().map(|_| Vec::new());
        let mut count = 0;
        for (value, symbol) in values.iter().zip(symbols) {
            if let Some(&local) = symbol.as_ref() {
                let Value::Eq(id) = value else { panic!("typed equality field") };
                let port = PortRef { component: frame.component, symbol: ports[local] };
                if BIND {
                    self.bind_cell_port(f, local, port, *id);
                }
                if scalars.is_some() { count += 1; }
            } else if let Some(scalars) = &mut scalars {
                assert!(
                    !matches!(value, Value::Eq(_) | Value::Set(_)),
                    "scalar ownership field"
                );
                scalars.push(value.clone());
            }
        }
        let Some(scalars) = scalars else { return; };
        let fields = Fields { component: frame.component, frame: frame.ordinal, operation: f.op, scalars: scalars.into_boxed_slice() };
        let mut state_guard = self
            .cells.fact_state_mut(f)
            .unwrap();
        let state = &mut *state_guard;
        state.decoded = None;
        let stats = self.stable_ports.as_mut().unwrap();
        if !stats.template_fields || !fields.scalars.is_empty() {
            assert!(stats.nodes.insert(f, Stored { table, fields }).is_none(),
                "stable representation installed once per fact incarnation");
        }
        stats.rows_installed += 1;
        stats.ports_installed += count;
    }
    pub(in crate::graph) fn stable_node(&self, f: FactRef) -> Option<Cow<'_, Stored>> {
        let runtime = self.stable_ports.as_ref()?;
        runtime.node_lookups.set(runtime.node_lookups.get() + 1);
        let node = self.stable_node_unmetered(f)?;
        if matches!(&node, Cow::Owned(_)) {
            runtime.template_node_projections.set(runtime.template_node_projections.get()+1);
        }
        Some(node)
    }
    pub(in crate::graph) fn stable_node_unmetered(&self, f: FactRef) -> Option<Cow<'_, Stored>> {
        let runtime = self.stable_ports.as_ref()?;
        if let Some(node) = runtime.nodes.get(&f) { return Some(Cow::Borrowed(node)); }
        #[cfg(feature="sparse-cells")]
        if runtime.template_fields {
            return self.stable_port_reader().ok()?.project_node(f).map(Cow::Owned);
        }
        None
    }
    pub(in crate::graph) fn retire_stable_node(&mut self, f: FactRef, owned: bool) {
        if let Some(runtime) = self.stable_ports.as_mut() {
            runtime.node_retirement_probes += 1;
            let removed = runtime.nodes.remove(&f);
            runtime.nodes_retired += u64::from(removed || (runtime.template_fields && owned));
        }
    }
    pub fn read_port(&self, port: PortRef) -> Result<Value> {
        let (value, probes) = self.stable_port_reader()?.read_port_counted(port)?;
        self.record_port_reads(1, probes);
        Ok(value)
    }
    fn stable_field_view<'a>(&'a self, stored: &'a Stored) -> Result<FieldView<'a>> {
        let runtime = self.stable_ports.as_ref().ok_or("stable fields disabled")?;
        runtime.field_layout_reads.set(runtime.field_layout_reads.get() + 1);
        self.stable_port_reader()?.fields(stored)
    }
    pub fn fact_port(&self, f: FactRef, column: usize) -> Option<PortRef> {
        let node = self.stable_node(f)?;
        let fields = self.stable_field_view(&node).ok()?;
        match fields.get(column)? {
            Field::Port(p) => Some(p),
            Field::Scalar(_) => None,
        }
    }
    pub(in crate::graph) fn read_stable_column(
        &self,
        stored: &Stored,
        col: usize,
    ) -> Result<Value> {
        self.stable_field_view(stored)?
            .get(col)
            .ok_or("stable field column")?
            .value(|port| self.read_port(port))
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
        // One immutable Cell read view serves the entire row, as it does a
        // worker guard. Accumulate counters locally instead of updating three
        // interior counters and reborrowing the graph for every equality field.
        let view = self.stable_port_reader()?;
        let mut work = guard::Work::default();
        let fields = self.stable_field_view(stored)?;
        let result = fields
            .iter()
            .map(|field| view.field_value(&field, meter, &mut work))
            .collect::<Result<Vec<_>>>();
        // Preserve successful-prefix work even when a later port has expired.
        if meter && work.port_reads != 0 {
            self.record_port_reads(work.port_reads, work.parent_probes);
        }
        result.map(row_fields)
    }
    pub(in crate::graph) fn read_stable_fact(
        &self,
        f: FactRef,
        state: crate::graph::fact_states::FactRead<'_>,
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
    /// Shared Cell slices identify the affected columns. Stable fields already
    /// observe the equality; decoded compatibility rows still need projection.
    /// Both representations use the same publication and completion boundary.
    pub(super) fn propagate_cell_fields(
        &mut self,
        f: FactRef,
        columns: &[usize],
        from: u64,
        to: u64,
    ) {
        // Several signals may contribute disjoint, unsorted column slices.
        let stable = self.stable_node(f).map(|stored| {
            let width = self.stable_field_view(&stored).expect("live stable layout").len();
            (stored.table, columns.iter().any(|&i| i + 1 < width))
        });
        if stable.is_some() && columns.is_empty() {
            return;
        }
        let port_key = stable.is_some_and(|(table, _)| self.port_keys_enabled(table));
        let unique = port_key && stable.unwrap().1 && self.unique_port_input(f, columns);
        let m = self.ownership.as_mut().unwrap();
        let mut state_guard = self
            .cells.fact_state_mut(f)
            .unwrap();
        let state = &mut *state_guard;
        let mut stats = stable.map(|_| self.stable_ports.as_mut().unwrap());
        let (table, key) = if let Some((table, key)) = stable {
            let stats = stats.as_mut().unwrap();
            stats.notifications += 1;
            stats.notified_columns += columns.len() as u64;
            (table, key)
        } else {
            m.stats.body_visits += 1;
            let (table, fields) = state.decoded.as_mut().expect("owned canonical body");
            let mut changed = false;
            let mut key = false;
            for &i in columns {
                m.stats.port_checks += 1;
                if fields[i] == Value::Eq(from) {
                    m.stats.changed_ports += 1;
                    m.stats.row_copies += u64::from(RowFields::strong_count(fields) > 1);
                    RowFields::make_mut(fields)[i] = Value::Eq(to);
                    changed = true;
                    key |= i + 1 < fields.len();
                } else {
                    m.stats.unchanged_port_checks += 1;
                }
            }
            if !changed {
                return;
            }
            (*table, key)
        };
        // A changed input needs completion unless uniqueness was proved. Its
        // canonical hash bucket cannot affect this decision, so do not probe it.
        let publish = unique
            || (!key
                && (port_key
                    || self.intern.get(&state.hash)
                        .is_some_and(|b| b.len() == 1 && b.first() == Some(&f)))
                && !m.pending.contains(table, &f));
        if publish {
            state.epoch = if unique {
                // Bypassing the queue must retain its causal epoch join.
                m.pending.completion_epoch(self.epoch, state.epoch, None)
            } else {
                self.epoch
            };
            self.query_versions[table] += 1;
            self.changes.touch(table, Dependency::Fact(f));
            if unique {
                stats.unwrap().unique.as_mut().unwrap().publications += 1;
            } else {
                m.stats.result_publications += 1;
                if let Some(stats) = stats {
                    stats.result_publications += 1;
                }
            }
        } else {
            let added = u64::from(m.pending.insert(table, f, self.epoch));
            m.stats.key_enqueues += added;
            if let Some(stats) = stats {
                m.pending.cause(table, to);
                if port_key {
                    stats.equality_enqueues += added;
                } else {
                    stats.legacy_key_enqueues += added;
                }
            }
            self.dirty_facts[table].insert(f);
        }
    }
    pub fn stable_port_report(&self) -> J {
        let Some(stats) = &self.stable_ports else {
            return json!({"enabled":false});
        };
        let mut nodes = 0;
        let mut ports = 0;
        for cell_id in self.cells.cell_ids() {
            for (id, fact) in self.cells.fact_states(cell_id) {
                if let Some(row) = self.stable_node_unmetered(id) {
                    assert!(fact.owned && fact.decoded.is_none());
                    nodes += 1;
                    let view = self.stable_port_reader().unwrap();
                    ports += view.fields(&row).expect("live stable layout")
                        .iter()
                        .filter(|f| matches!(f, Field::Port(_)))
                        .count();
                } else {
                    assert!(!fact.owned, "owned fact lacks its stable representation");
                }
            }
        }
        assert_eq!(
            nodes,
            if stats.template_fields { (stats.rows_installed - stats.nodes_retired) as usize } else { stats.nodes.len() },
            "stable directory contains only live facts"
        );
        assert_eq!(stats.rows_installed - stats.nodes_retired, nodes as u64);
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
            indexed_port_keys, if self.port_birth_hints {port_key_facts} else {0},
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
            "stats":stats,"unique_publication":self.unique_publication_report(),"local_conditions":self.local_condition_report(),"parallel_guards":self.parallel_guard_report(),"completion_batches":self.completion_batch_report(),"live_stable_nodes":nodes,"materialized_stable_nodes":stats.nodes.len(),"template_projected_nodes":nodes-stats.nodes.len(),"live_port_fields":ports,
            "birth_hints_enabled":self.port_birth_hints,"birth_indexed_port_keys":indexed_port_keys,"port_key_matching":stats.keys,
            "pending_canonical_keys":pending_canonical_keys,
            "pending_port_equality_checks":self.ownership.as_ref().unwrap().pending.len()-pending_canonical_keys})
    }
}
