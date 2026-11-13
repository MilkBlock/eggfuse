//! Persistent, typed Cell ownership. Interior equality incidences have no
//! reverse subscriptions: shared symbolic programs route native results across
//! composed Cell frames. Foreign inputs and escaped aliases bind boundary ports.
use super::*;
use std::cell::Cell as Counter;
use std::sync::Arc;
#[path = "ownership_slices.rs"]
pub mod slices;
use slices::{PortProgram, Signal};
#[path = "ownership_composition.rs"]
pub mod composition;
#[path = "stable_ports.rs"]
pub mod ports;
#[path = "ownership_query_classes.rs"]
pub mod query_classes;
#[path = "ownership_wire.rs"]
mod wire;
#[path = "ownership_pending.rs"]
mod ready;
#[cfg(feature = "sparse-cells")]
#[path = "constructor_reads.rs"]
pub(in crate::graph) mod query_read;
#[path = "port_completion.rs"]
pub(crate) mod completion;
#[path = "ownership_witnesses.rs"]
mod witnesses;

#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Plan {
    #[serde(skip)]
    format: wire::Format,
    #[serde(skip)]
    witnesses: witnesses::Routes,
    pub tables: Vec<bool>,
    pub markers: Vec<Marker>,
    pub programs: Arc<Vec<Arc<PortProgram>>>,
    /// Structure-of-arrays dispatch: native ports retain a compact pointer
    /// array; operator tags are compiled separately from source instructions.
    #[serde(skip)]
    pub code_programs: Vec<Arc<PortProgram>>,
    #[serde(skip)]
    pub code_operators: Vec<Vec<usize>>,
    /// Operator identity common to every concrete code sharing a port layout.
    /// MAX means ambiguous; runtime code remains authoritative there.
    #[serde(skip)]
    pub layout_operators: Vec<Vec<usize>>,
    #[serde(skip)]
    pub query_classes: Option<Arc<query_classes::Plan>>,
    pub composition: composition::Plan,
    pub entries: Vec<Vec<usize>>,
    /// Shared publication table -> scheduled typed entry ports. Producer body
    /// operations reference these same table IDs; routes are shared, not
    /// expanded into a separate per-producer/per-consumer dependency graph.
    pub routes: Vec<Vec<(usize, usize)>>,
}
#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Marker {
    pub program_id: usize,
    #[serde(skip)]
    pub code: usize,
    #[serde(skip)]
    pub program: Arc<PortProgram>,
}
impl Plan {
    #[cfg(feature = "storage-metrics")]
    pub(crate) fn release_storage_by_field(self, live_bytes: &impl Fn() -> usize, rows: &mut Vec<(&'static str, usize)>) {
        assert!(rows.capacity() - rows.len() >= 32);
        let before = live_bytes();
        drop(self.tables);
        rows.push(("ownership.tables", before - live_bytes()));
        let before = live_bytes();
        drop(self.markers);
        rows.push(("ownership.markers", before - live_bytes()));
        let before = live_bytes();
        drop(self.programs);
        rows.push(("ownership.programs", before - live_bytes()));
        let before = live_bytes();
        drop(self.code_programs);
        rows.push(("ownership.code_programs", before - live_bytes()));
        let before = live_bytes();
        drop(self.code_operators);
        rows.push(("ownership.code_operators", before - live_bytes()));
        let before = live_bytes();
        drop(self.layout_operators);
        rows.push(("ownership.layout_operators", before - live_bytes()));
        let before = live_bytes();
        drop(self.query_classes);
        rows.push(("ownership.query_classes", before - live_bytes()));
        let before = live_bytes();
        drop(self.witnesses);
        rows.push(("ownership.witnesses", before - live_bytes()));
        self.composition.release_storage_by_field(live_bytes, rows);
        let before = live_bytes();
        drop(self.entries);
        rows.push(("ownership.entries", before - live_bytes()));
        let before = live_bytes();
        drop(self.routes);
        rows.push(("ownership.routes", before - live_bytes()));
    }
    pub(crate) fn derive(p: &Program) -> Result<Self> {
        let tables = p
            .repair_ports
            .key_eq_columns
            .iter()
            .enumerate()
            .map(|(id,columns)| columns.is_some() || (p.artifact["unit_fact_ownership"]==true
                && p.tables[id].virtual_fact && !p.tables[id].constructor
                && p.tables[id].schema.last().is_some_and(|s|s["kind"]=="Unit")
                && p.tables[id].schema.iter().all(|s|matches!(s["kind"].as_str(),
                    Some("eq"|"i64"|"f64"|"String"|"bool"|"Unit"|"structural_key")))))
            .collect::<Vec<_>>();
        let format = wire::Format::program(p)?;
        let mut shared = BTreeMap::new();
        let markers = p
            .templates
            .iter()
            .map(|t| {
                let program = Arc::new(PortProgram::derive(p, t, &tables));
                let legacy = (format == wire::Format::Legacy).then(|| wire::unions(t));
                let id = shared.len();
                let (program_id, program) = shared.entry((program.clone(), legacy))
                    .or_insert((id, program)).clone();
                Marker { program, program_id, code: 0 }
            })
            .collect::<Vec<_>>();
        let mut programs = vec![Arc::new(PortProgram::default()); shared.len()];
        for (_, (id, program)) in shared {
            programs[id] = program;
        }
        let entries = p
            .rules
            .iter()
            .map(|r| {
                r.query
                    .iter()
                    .enumerate()
                    .filter_map(|(i, a)| matches!(a.call,Call::Table(t) if tables[t]).then_some(i))
                    .collect()
            })
            .collect::<Vec<_>>();
        let mut routes = vec![vec![]; p.tables.len()];
        for (rid, r) in p.rules.iter().enumerate() {
            for (atom, a) in r.query.iter().enumerate() {
                if let Call::Table(t) = a.call
                    && tables[t]
                {
                    routes[t].push((rid, atom));
                }
            }
        }
        let composition = composition::Plan::derive(p, &markers, &programs, &entries, format)?;
        let mut plan = Self {
            format,
            programs: Arc::new(programs),
            code_programs: vec![],
            code_operators: vec![],
            layout_operators: vec![],
            query_classes: None,
            witnesses: Default::default(),
            composition,
            tables,
            markers,
            entries,
            routes,
        };
        if let Some(raw) = p.artifact.get("ownership_markers") {
            if *raw != plan.artifact(p) {
                return Err("ownership marker differs from typed entry/body wiring".into());
            }
        }
        if let Some(raw) = p.artifact["ownership_fragments"].get("query_classes") {
            plan.prepare_codes(&p.templates);
            plan.query_classes = Some(Arc::new(if raw == &J::Bool(true) {
                query_classes::Plan::bake(p,&plan)
            } else {query_classes::Plan::validate(raw,p,&plan)?}));
        }
        if p.artifact.get("ownership_witnesses").is_some() {
            plan.prepare_codes(&p.templates);
            plan.witnesses = witnesses::Routes::compile(p, &plan)?;
        }
        Ok(plan)
    }
    fn prepare_codes(&mut self, templates: &[Template]) {
        if !self.code_programs.is_empty() { return; }
        let mut shared = BTreeMap::new();
        for (template, marker) in templates.iter().zip(&mut self.markers) {
            let operators = template.ops.iter().enumerate().map(|(op, instruction)| {
                if !marker.program.covers(op) { return usize::MAX; }
                match instruction {
                    Op::Let(_, Call::Table(t), _) | Op::Set(t, _, _) => *t,
                    _ => unreachable!("covered body must have a typed operator"),
                }
            }).collect::<Vec<_>>();
            let key = (marker.program_id, operators);
            marker.code = if let Some(&id) = shared.get(&key) { id } else {
                let id = self.code_programs.len();
                self.code_programs.push(marker.program.clone());
                self.code_operators.push(key.1.clone());
                shared.insert(key, id);
                id
            };
        }
        self.layout_operators = vec![Vec::new(); self.programs.len()];
        let mut initialized = vec![false; self.programs.len()];
        for marker in &self.markers {
            let target = &mut self.layout_operators[marker.program_id];
            let operators = &self.code_operators[marker.code];
            if !initialized[marker.program_id] {
                *target = operators.clone();
                initialized[marker.program_id] = true;
            } else {
                debug_assert_eq!(target.len(), operators.len());
                for (known, &actual) in target.iter_mut().zip(operators) {
                    if *known != actual { *known = usize::MAX; }
                }
            }
        }
    }
    pub fn fragment_schema(&self) -> &'static str { self.format.fragment_schema() }
    pub fn artifact(&self, p: &Program) -> J {
        json!({"schema":self.format.marker_schema(), "recipe":p.artifact["recipe"]["sha256"],
            "entry_schedule":crate::checksum::artifact_digest(&p.artifact["entry_schedule"]),"plan":wire::plan(self, p),
            "contract":"checked scheduled bindings enter persistent scalar constructor owners; foreign roots are boundaries; no future union is assumed"})
    }
}
#[derive(Default, Serialize)]
struct Stats {
    marker_entries: u64,
    marker_anchor_reads: u64,
    owned_births: u64,
    adopted_existing: u64,
    owned_retirements: u64,
    owned_live: u64,
    internal_ports_seen: u64,
    boundary_ports_seen: u64,
    boundary_insert_attempts: u64,
    boundary_edges_created: u64,
    boundary_edges_removed: u64,
    boundary_live: u64,
    boundary_probes: u64,
    native_owner_routes: u64,
    boundary_owner_routes: u64,
    owner_visits: u64,
    body_visits: u64,
    port_checks: u64,
    row_copies: u64,
    result_publications: u64,
    key_enqueues: u64,
    key_completions: u64,
    boundary_rebuilds: u64,
    boundary_body_reads: u64,
    stage_barriers: u64,
    carried_facts: u64,
    carried_components: u64,
    unbound_query_calls: Counter<u64>,
    unbound_query_rows: Counter<u64>,
    retired_result_boundaries: u64,
    domain_queries: Counter<u64>,
    domain_owner_visits: Counter<u64>,
    domain_body_visits: Counter<u64>,
    domain_legacy_visits: Counter<u64>,
    domain_results: Counter<u64>,
    uncovered_births: u64,
    components_created: u64,
    components_retired: u64,
    components_live: u64,
    composition_entry_reads: u64,
    composition_transition_probes: u64,
    composition_unbaked_fallbacks: u64,
    composition_cross_stage_joins: u64,
    composition_missing_sources: u64,
    composition_capacity_cuts: u64,
    composition_requests: u64,
    composition_substituted_ports: u64,
    composition_cache_hits: u64,
    composition_baked_hits: u64,
    composition_shape_builds: u64,
    composition_materializations: u64,
    composition_shape_steps: u64,
    composition_frames: u64,
    dispatch_heap_pushes: u64,
    dispatch_heap_pops: u64,
    dispatch_comparisons: u64,
    dispatch_scratch_growths: u64,
    dispatch_static_field_tests: u64,
    dispatch_scratch_bytes: usize,
    signal_binding_reads: u64,
    signal_root_queries: Counter<u64>,
    signal_parent_probes: Counter<u64>,
    component_lifetime_updates: u64,
    component_lifetime_growths: u64,
    signal_bindings_created: u64,
    signal_bindings_retired: u64,
    component_signal_retire_visits: u64,
    signal_bindings_live: u64,
    signal_port_attaches: u64,
    signal_port_detaches: u64,
    signal_activations: u64,
    slice_steps: u64,
    inactive_slice_steps: u64,
    coalesced_slice_steps: u64,
    changed_ports: u64,
    unchanged_port_checks: u64,
    marker_union_requests: u64,
    native_signal_routes: u64,
    boundary_signal_routes: u64,
    domain_planning_calls: Counter<u64>,
    domain_planning_signals: Counter<u64>,
    domain_planning_slice_steps: Counter<u64>,
    domain_signal_visits: Counter<u64>,
    domain_slice_steps: Counter<u64>,
    domain_route_probes: Counter<u64>,
    domain_column_checks: Counter<u64>,
    domain_legacy_fact_probes: Counter<u64>,
    domain_type_guards: Counter<u64>,
    domain_static_type_guards: Counter<u64>,
    domain_type_rejections: Counter<u64>,
    query_class_probes: Counter<u64>,
    query_class_range_jumps: Counter<u64>,
}
impl Stats {
    fn signal_root(&self, parents: &Parents, id: u64) -> u64 {
        let (id, probes) = parents.reader().root_counted(id);
        self.signal_root_queries.set(self.signal_root_queries.get() + 1);
        self.signal_parent_probes.set(self.signal_parent_probes.get() + probes);
        id
    }
}
#[derive(Serialize)]
struct Barrier {
    epoch: u64,
    live_facts: u64,
    live_components: u64,
    boundary_edges: u64,
    legacy_reverse_edges: u64,
    key_completions: u64,
    result_publications: u64,
    body_visits: u64,
    port_checks: u64,
    changed_ports: u64,
    slice_steps: u64,
    signal_bindings: u64,
}
pub(super) struct Runtime {
    composition: composition::Runtime,
    port_completion: Option<completion::Counts>,
    boundaries: HashMap<u64, crate::tiny_set::TinySet<Signal>>,
    pub(super) pending: ready::Pending,
    pub(super) tables: Vec<usize>,
    stats: Stats,
    barriers: Vec<Barrier>,
    keep_barrier_history:bool,
    barrier_history_start:u64,
}
impl Runtime {
    fn trace_barriers(&mut self) {
        if !self.keep_barrier_history {
            self.keep_barrier_history=true;
            self.barrier_history_start=self.stats.stage_barriers;
        }
    }
}
impl Graph {
    /// Retain future source-boundary observations explicitly. Ordinary execution
    /// keeps cumulative counters only; a late request reports its missing prefix.
    pub fn trace_ownership_barriers(&mut self)->Result<()> {
        self.ownership.as_mut().ok_or("enable ownership before barrier tracing")?.trace_barriers();
        Ok(())
    }
    /// Saved after execution for offline storage analysis. These are the
    /// existing owners, not an additional maintained fact/history graph.
    #[cfg(feature = "storage-metrics")]
    pub fn ownership_storage_trace(&self) -> J {
        let Some(m) = &self.ownership else { return J::Null; };
        let c = &m.composition;
        let components = c.components.iter().enumerate().filter_map(|(id,component)| {
            let component = component.as_ref()?;
            Some(json!({"id":id,"shape":component.shape,"frames":component.frames.as_slice(),
                "signals":component.signals,"live_facts":c.live_facts[id],
                "roots":component.signals.iter().map(|v|v.map(|id|root(&self.parents,id))).collect::<Vec<_>>(),
                "frame_codes":component.frames.iter().map(|id| c.frames[id].code).collect::<Vec<_>>()}))
        }).collect::<Vec<_>>();
        json!({"scope":"final live composition owners; diagnostic export after observation, not retained runtime state",
            "source_eq_bindings":self.cells.iter().map(|(&id,cell)| json!({
                "cell":id,"template":cell.template,"completed":cell.completed,
                "slots":(0..self.program.templates[cell.template].sorts.len()).filter_map(|slot|
                    match cell.values.get(&slot) { Some(Value::Eq(id))=>Some((slot,*id,root(&self.parents,*id))),_=>None }).collect::<Vec<_>>()
            })).collect::<Vec<_>>(),
            "components":components,"shapes":c.shapes,"programs":self.program.cell_ownership.programs,
            "operators":self.program.cell_ownership.code_operators,
            "fragments":self.program.cell_ownership.composition.fragments,
            "transitions":self.program.cell_ownership.composition.transitions})
    }
    pub fn ownership_enabled(&self) -> bool {
        self.ownership.is_some()
    }
    pub(crate) fn needs_ownership_entry(&self, rid: usize) -> bool {
        self.ownership.as_ref().is_some_and(|m| {
            self.program.cell_ownership.markers[self.program.rules[rid].template].program.active()
                && (m.composition.catalog_trace.is_some() || m.composition.training.is_some()
                    || self.program.cell_ownership.composition.active_rules[rid]
                    || self.program.cell_ownership.witnesses.0.get(rid).is_some_and(|r|!r.is_empty()))
        })
    }
    pub(super) fn ownership_settled(&self) -> bool {
        self.ownership.as_ref().is_none_or(|m| m.pending.is_empty())
    }
    pub fn new_with_cell_ownership(p: Program) -> Result<Self> {
        let mut g = Self::new_with_repair_ports(p)?;
        g.use_cell_ownership()?;
        Ok(g)
    }
    pub fn use_cell_ownership(&mut self) -> Result<()> {
        if self.ownership.is_some() {
            return Ok(());
        }
        if self.local_unions.is_some() || self.union_digest.is_some() || {
            #[cfg(feature = "spine-blocks")]
            {
                self.repair_cells.is_some()
            }
            #[cfg(not(feature = "spine-blocks"))]
            {
                false
            }
        } {
            return Err(
                "persistent Cell ownership requires its own ordered completion backend".into(),
            );
        }
        self.program.prepare_cell_ownership()?;
        self.program.cell_ownership.prepare_codes(&self.program.templates);
        self.ownership = Some(Runtime {
            composition: composition::Runtime::new(&self.program.cell_ownership.composition),
            boundaries: HashMap::default(),
            port_completion: None,
            pending: ready::Pending::default(),
            tables: vec![0; self.program.tables.len()],
            stats: Stats::default(),
            barriers: vec![],
            keep_barrier_history:false,
            barrier_history_start:0,
        });
        // Import is already settled. Adopt existing covered bodies, rather than
        // limiting ownership to rows born after activation.
        let facts = (0..self.program.tables.len())
            .flat_map(|t| self.witnesses(t))
            .filter_map(|w| {
                if let Dependency::Fact(f) = w {
                    Some(f)
                } else {
                    None
                }
            })
            .collect::<Vec<_>>();
        for f in facts {
            let Some(row) = self.fact(f)? else { continue };
            if !self.program.cell_ownership.tables[row.table] {
                continue;
            }
            self.replace_row_edges(Dependency::Fact(f), &row.values, &[]);
            #[cfg(not(feature = "sparse-cells"))]
            self.dependencies.remove(&Dependency::Fact(f));
            self.cells.fact_state_mut(f)
                .unwrap()
                .owned = true;
            self.cells.fact_state_mut(f)
                .unwrap()
                .decoded = Some((row.table, row.values.clone()));
            let m = self.ownership.as_mut().unwrap();
            m.tables[row.table] += 1;
            m.stats.adopted_existing += 1;
            m.stats.owned_live += 1;
            self.initialize_cell_fields::<true>(f, row.table, &row.values);
            #[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
            self.delegate_completed_slots(f.cell);
        }
        Ok(())
    }
    pub(crate) fn begin_owner_entry(&mut self, rid: usize, anchors: smallvec::SmallVec<[Option<Dependency>; 4]>) {
        if let Some(m) = &mut self.ownership {
            m.stats.marker_entries += 1;
        }
        self.composition_entry(rid, anchors);
    }
    pub(crate) fn end_owner_entry(&mut self) {
        if let Some(m) = &mut self.ownership {
            m.composition.entry = None;
        }
    }
    #[cfg(feature = "sparse-cells")]
    pub(super) fn take_owner_entry(&mut self) -> Option<composition::Entry> {
        self.ownership.as_mut().and_then(|m| m.composition.entry.take())
    }
    #[cfg(feature = "sparse-cells")]
    pub(super) fn restore_owner_entry(&mut self, entry: Option<composition::Entry>) {
        if let Some(m) = &mut self.ownership {
            assert!(m.composition.entry.is_none(), "finish or suspend the attached Entry first");
            m.composition.entry = entry;
        } else { assert!(entry.is_none(), "ownership runtime disappeared while an Entry was parked"); }
    }
    pub(super) fn owns_birth(&mut self, f: FactRef) -> bool {
        if self.ownership.is_none() {
            return false;
        }
        let template = self.cells.cell_metadata(f.cell).unwrap().template;
        if !self.program.cell_ownership.markers[template].program.covers(f.op as usize) {
            self.ownership.as_mut().unwrap().stats.uncovered_births += 1;
            return false;
        }
        true
    }
    pub(super) fn publish_owned_birth(&mut self, f: FactRef, t: usize, fields: &[Value]) {
        let m = self.ownership.as_mut().unwrap();
        m.tables[t] += 1;
        m.stats.owned_births += 1;
        m.stats.owned_live += 1;
        self.initialize_cell_fields::<true>(f, t, fields);
    }
    /// Resolve the address encoded by an equality ID. This is not an equality
    /// proof: native_signal still validates the actual retained symbol binding.
    #[inline]
    fn native_port(&self, id: u64, expected_component: Option<u32>) -> Option<ports::PortRef> {
        let cell = (id >> 32) as u32;
        let slot = (id as u32).checked_sub(1)? as usize;
        let m = self.ownership.as_ref()?;
        let frame = m.composition.frames.get(&cell)?;
        // Preserve the cheap foreign-component rejection before the local
        // native-slot map, as used by binding and union dispatch.
        if expected_component.is_some_and(|expected| frame.component != expected) {
            return None;
        }
        let local = *self.program.cell_ownership.code_programs[frame.code]
            .native
            .get(&slot)?;
        Some(m.composition.port(*frame, local))
    }
    fn signal_is_native(&self, signal: Signal, id: u64) -> bool {
        self.native_port(id, Some(signal.component))
            .is_some_and(|port| port.symbol == signal.symbol)
    }
    pub(super) fn native_signal(&self, id: u64) -> Option<Signal> {
        let port = self.native_port(id, None)?;
        let m = self.ownership.as_ref().unwrap();
        let bound = m.composition.components[port.component as usize]
            .as_ref()?
            .signals[port.symbol]?;
        if bound != id && m.stats.signal_root(&self.parents, bound) != id {
            return None;
        }
        Some(m.composition.signal(&self.program.cell_ownership, port.component, port.symbol))
    }
    fn boundary(&mut self, root: u64, signal: Signal) {
        let m = self.ownership.as_mut().unwrap();
        m.stats.boundary_insert_attempts += 1;
        if m.boundaries.entry(root).or_default().insert(signal) {
            m.stats.boundary_edges_created += 1;
            m.stats.boundary_live += 1;
        }
    }
    fn bind_cell_port(&mut self, f: FactRef, local: usize, port: ports::PortRef, id: u64) {
        let signal = self.ownership.as_ref().unwrap().composition.signal(
            &self.program.cell_ownership, port.component, port.symbol);
        let native = self.signal_is_native(signal, id);
        let m = self.ownership.as_mut().unwrap();
        m.stats.internal_ports_seen += u64::from(native);
        m.stats.boundary_ports_seen += u64::from(!native);
        m.stats.signal_port_attaches += 1;
        m.stats.signal_binding_reads += 1;
        let slot = m.composition.components[signal.component as usize]
            .as_ref()
            .unwrap()
            .signals[signal.symbol];
        if let Some(bound) = slot {
            assert!(bound == id || m.stats.signal_root(&self.parents, bound) == id,
                "symbolic alias disagrees with live port");
            if m.composition.training.is_some() {
                let frame = m.composition.frames[&f.cell];
                let c = m.composition.components[signal.component as usize]
                    .as_ref()
                    .unwrap();
                let shape = m.composition.shapes[c.shape].as_ref().unwrap();
                // A retained slot with no live producer is not an observed
                // cross-frame reuse. Profiling must still count real uses.
                if shape.signals[signal.symbol].iter().any(|step| {
                    step.frame < frame.ordinal
                        && self
                            .cells.fact_state(FactRef{cell:c.frames[step.frame],op:step.op})
                            .is_some_and(|fact| fact.owned)
                }) {
                    m.composition
                        .observe_shared_binding(f.cell, local, signal.symbol);
                }
            }
        } else {
            m.composition.components.local_mut(signal.component as usize)
                .as_mut().unwrap().signals[signal.symbol] = Some(id);
            m.stats.signal_bindings_created += 1;
            m.stats.signal_bindings_live += 1;
            if !native {
                self.boundary(id, signal);
            }
        }
    }
    /// An explicit union reaches ownership at the original Cell effect position.
    /// The caller already has its operands; the marker need not reload or clone
    /// a second instruction. Committed equality still activates shared signals.
    pub(crate) fn enqueue_source_union(&mut self, a: Value, b: Value) -> Result<()> {
        if let Some(ownership) = &mut self.ownership {
            ownership.stats.marker_union_requests += 1;
        }
        self.enqueue_union(a, b)
    }
    fn next_composed_step(
        &mut self,
        signal: Signal,
        mut position: usize,
    ) -> Option<composition::Cursor> {
        let m = self.ownership.as_mut().unwrap();
        let component = m.composition.components[signal.component as usize]
            .as_ref()
            .unwrap();
        let steps = &m.composition.shapes[component.shape]
            .as_ref()
            .unwrap()
            .signals[signal.symbol];
        while let Some(step) = steps.get(position) {
            m.stats.slice_steps += 1;
            let fact = FactRef {
                cell: component.frames[step.frame],
                op: step.op,
            };
            if self
                .cells.fact_state(fact)
                .is_some_and(|s| s.owned)
            {
                return Some(composition::Cursor {
                    signal,
                    position,
                    fact,
                });
            }
            m.stats.inactive_slice_steps += 1;
            position += 1;
        }
        None
    }
    fn dispatch_push(&mut self, heap: &mut Vec<composition::Cursor>, cursor: composition::Cursor) {
        let m = self.ownership.as_mut().unwrap();
        m.stats.dispatch_heap_pushes += 1;
        let old = heap.capacity();
        heap.push(cursor);
        m.stats.dispatch_scratch_growths += u64::from(old != heap.capacity());
        let mut i = heap.len() - 1;
        while i > 0 {
            let parent = (i - 1) / 2;
            m.stats.dispatch_comparisons += 1;
            if heap[parent].fact <= heap[i].fact {
                break;
            }
            heap.swap(parent, i);
            i = parent;
        }
    }
    fn dispatch_pop(&mut self, heap: &mut Vec<composition::Cursor>) -> Option<composition::Cursor> {
        let last = heap.pop()?;
        let stats = &mut self.ownership.as_mut().unwrap().stats;
        stats.dispatch_heap_pops += 1;
        if heap.is_empty() {
            return Some(last);
        }
        let out = std::mem::replace(&mut heap[0], last);
        let mut i = 0;
        while i * 2 + 1 < heap.len() {
            let mut child = i * 2 + 1;
            if child + 1 < heap.len() {
                stats.dispatch_comparisons += 1;
                if heap[child + 1].fact < heap[child].fact {
                    child += 1;
                }
            }
            stats.dispatch_comparisons += 1;
            if heap[i].fact <= heap[child].fact {
                break;
            }
            heap.swap(i, child);
            i = child;
        }
        Some(out)
    }
    pub(super) fn propagate_owned_union(&mut self, from: u64, to: u64, native: Option<Signal>) {
        if self.ownership.is_none() {
            return;
        }
        let m = self.ownership.as_mut().unwrap();
        m.stats.boundary_probes += 1;
        let signals = m.boundaries.remove(&from).unwrap_or_default();
        m.stats.boundary_signal_routes += signals.len() as u64;
        m.stats.boundary_live -= signals.len() as u64;
        m.stats.boundary_edges_removed += signals.len() as u64;
        m.stats.native_signal_routes += u64::from(native.is_some());
        let mut heap = std::mem::take(&mut m.composition.heap);
        let mut columns = std::mem::take(&mut m.composition.columns);
        debug_assert!(heap.is_empty());
        for signal in signals.iter().copied().chain(native) {
            let intrinsic = self.signal_is_native(signal, to);
            let m = self.ownership.as_mut().unwrap();
            m.stats.signal_activations += 1;
            // The initial binding remains stable. Only equality and boundary
            // routing change; shared signal programs still receive this event.
            if !intrinsic {
                self.boundary(to, signal);
            }
            if let Some(cursor) = self.next_composed_step(signal, 0) {
                self.dispatch_push(&mut heap, cursor);
            }
        }
        // Every slice is already ordered. Merge only active slices into reusable
        // scratch: no per-equality row map/set, destination sorting or dedup.
        // A body column belongs to exactly one composed symbol. Runtime aliases
        // therefore contribute disjoint columns when several signals activate.
        while let Some(mut cursor) = self.dispatch_pop(&mut heap) {
            let fact = cursor.fact;
            columns.clear();
            let mut pieces = 0;
            loop {
                let m = self.ownership.as_mut().unwrap();
                let c = m.composition.components[cursor.signal.component as usize]
                    .as_ref()
                    .unwrap();
                let shape = m.composition.shapes[c.shape].as_ref().unwrap();
                let step = &shape.signals[cursor.signal.symbol][cursor.position];
                let old = columns.capacity();
                m.stats.dispatch_static_field_tests += self.program.cell_ownership.programs[shape.programs[step.frame]]
                    .fields[step.op as usize].len() as u64;
                columns.extend(shape.columns(&self.program.cell_ownership.programs, cursor.signal.symbol, step));
                m.stats.dispatch_scratch_growths += u64::from(old != columns.capacity());
                pieces += 1;
                if let Some(next) = self.next_composed_step(cursor.signal, cursor.position + 1) {
                    self.dispatch_push(&mut heap, next);
                }
                if heap.first().is_some_and(|next| next.fact == fact) {
                    cursor = self.dispatch_pop(&mut heap).unwrap();
                } else {
                    break;
                }
            }
            self.ownership.as_mut().unwrap().stats.coalesced_slice_steps += pieces - 1;
            self.propagate_cell_fields(fact, &columns, from, to);
        }
        let m = self.ownership.as_mut().unwrap();
        m.stats.dispatch_scratch_bytes = heap.capacity()
            * std::mem::size_of::<composition::Cursor>()
            + columns.capacity() * std::mem::size_of::<usize>();
        m.composition.heap = heap;
        m.composition.columns = columns;
    }
    pub(super) fn pop_owned_before(&mut self, next: Option<Dependency>, allowed: Option<crate::table_mask::Selection<'_>>) -> Option<FactRef> {
        let m = self.ownership.as_mut()?;
        let (f,table) = m.pending.first(allowed)?;
        if next.is_some_and(|d| d < Dependency::Fact(f)) {
            return None;
        }
        if let Some(epoch) = m.pending.pop(f, table) { self.epoch = epoch; }
        Some(f)
    }
    pub(super) fn complete_owned_key(&mut self, f: FactRef) -> Result<()> {
        let Some(r) = self.fact(f)? else {
            return Ok(());
        };
        if self.port_keys_enabled(r.table) {
            return self.complete_port_key(f, r);
        }
        self.dirty_facts[r.table].remove(&f);
        self.ownership.as_mut().unwrap().stats.key_completions += 1;
        self.complete_canonical_cell(f, r)
    }
    pub(super) fn retire_owned(&mut self, f: FactRef, t: usize) -> bool {
        if !self.cells.fact_state(f).unwrap().owned {
            return false;
        }
        self.composition_retire_fact(f.cell);
        let m = self.ownership.as_mut().unwrap();
        m.pending.remove(t, &f);
        m.tables[t] -= 1;
        m.stats.owned_live -= 1;
        m.stats.owned_retirements += 1;
        true
    }
    pub(crate) fn ownership_barrier(&mut self) {
        if let Some(m) = &mut self.ownership {
            assert!(
                m.pending.is_empty(),
                "unsettled owner at publication boundary"
            );
            m.stats.stage_barriers += 1;
            m.stats.carried_facts += m.stats.owned_live;
            m.stats.carried_components += m.stats.components_live;
            if m.keep_barrier_history {m.barriers.push(Barrier {
                epoch: self.epoch,
                live_facts: m.stats.owned_live,
                live_components: m.stats.components_live,
                boundary_edges: m.stats.boundary_live,
                legacy_reverse_edges: self.maintenance.live_reverse_edges,
                key_completions: m.stats.key_completions,
                result_publications: m.stats.result_publications,
                body_visits: m.stats.body_visits,
                port_checks: m.stats.port_checks,
                changed_ports: m.stats.changed_ports,
                slice_steps: m.stats.slice_steps,
                signal_bindings: m.stats.signal_bindings_live,
            });}
        }
    }
    fn smallest_signal_domain(&self, table:usize, bound: &[Option<Value>]) -> Option<(usize, u64)> {
        let m = self.ownership.as_ref()?;
        m.stats
            .domain_planning_calls
            .set(m.stats.domain_planning_calls.get() + 1);
        let complete = m.tables[table] == self.witness_count(table);
        bound
            .iter()
            .enumerate()
            .filter_map(|(column, v)| {
                let Some(Value::Eq(id)) = v else {
                    return None;
                };
                let id = root(&self.parents, *id);
                // Choosing a domain is only a heuristic. Reading bucket sizes
                // avoids allocating and walking every losing domain just to
                // choose one. A signal may cover many fields, so this estimate
                // must never be used as a candidate-count upper bound.
                let count = m.boundaries.get(&id).map_or(0, |s| s.len())
                    + usize::from(self.native_signal(id).is_some())
                    + if complete {0} else {self.uses.get(&id).map_or(0, UseSet::len)};
                Some((column, id, count))
            })
            .min_by_key(|x| x.2)
            .map(|x| (x.0, x.1))
    }
    pub(super) fn owned_candidate_count(&self, table: usize, _bound: &[Option<Value>]) -> usize {
        // Keep the public upper-bound contract without enumerating signal
        // slices. The cheap domain-selection score is not a row count.
        self.witness_count(table)
    }
    pub(super) fn owned_candidates(
        &self,
        table: usize,
        bound: &[Option<Value>],
    ) -> Vec<Dependency> {
        let Some((column, id)) = self.smallest_signal_domain(table,bound) else {
            let rows = self.witnesses(table);
            let s = &self.ownership.as_ref().unwrap().stats;
            s.unbound_query_calls.set(s.unbound_query_calls.get() + 1);
            s.unbound_query_rows
                .set(s.unbound_query_rows.get() + rows.len() as u64);
            return rows;
        };
        let owner = self.ownership.as_ref().unwrap();
        let s = &owner.stats;
        s.domain_queries.set(s.domain_queries.get() + 1);
        let mut result = BTreeSet::new();
        // Jump over incompatible classes before touching any instance. The
        // result set still preserves witness order across all retained classes.
        for signal in self.query_signals(table, id) {
            s.domain_signal_visits.set(s.domain_signal_visits.get() + 1);
            let m = &self.ownership.as_ref().unwrap().composition;
            let uses = self.cell_field_uses(signal, column).expect("live query signal");
            s.domain_route_probes.set(s.domain_route_probes.get() + 1);
            for position in 0..uses.len() {
                s.domain_slice_steps.set(s.domain_slice_steps.get() + 1);
                if !uses.indexed() {
                    s.domain_column_checks.set(s.domain_column_checks.get() + 1);
                }
                let Some(fact) = uses.fact(position, false) else { continue; };
                // Shared layout proof replaces the instance-code read where
                // every concrete template agrees on the operator. Ambiguous
                // layouts still discriminate before probing the live node.
                let operator = if let Some(operator) = uses.known_operator(position) {
                    s.domain_static_type_guards.set(s.domain_static_type_guards.get() + 1);
                    operator
                } else {
                    let frame = m.frames[&fact.cell];
                    self.program.cell_ownership.code_operators[frame.code][fact.op as usize]
                };
                s.domain_type_guards.set(s.domain_type_guards.get() + 1);
                if operator != table {
                    s.domain_type_rejections.set(s.domain_type_rejections.get() + 1);
                    continue;
                }
                let matches = if self.stable_ports.is_some() {
                    // This is the authoritative live owned-fact directory:
                    // installation and retirement enforce the fact's lifetime.
                    // Do not re-read both legacy directories
                    // before asking the same node for its operator.
                    self.stable_node(fact).is_some_and(|node| node.table == table)
                } else {
                    s.domain_legacy_fact_probes.set(s.domain_legacy_fact_probes.get() + 1);
                    self.cells.fact_state(fact)
                        .is_some_and(|state| state.owned && state.decoded.as_ref().unwrap().0 == table)
                };
                if matches {
                    result.insert(Dependency::Fact(fact));
                }
            }
        }
        // Every live row is already represented by checked Cell wiring.
        // Foreign legacy uses cannot add a candidate to this table. Partial
        // coverage still requires the complete residual subscription path.
        if owner.tables[table] != self.witness_count(table) {
            for &d in self.uses.get(&id).into_iter().flat_map(|s| s.iter()) {
                s.domain_legacy_visits.set(s.domain_legacy_visits.get() + 1);
                if self.dependency_table(d) == Some(table) {
                    result.insert(d);
                }
            }
        }
        s.domain_results
            .set(s.domain_results.get() + result.len() as u64);
        result.into_iter().collect()
    }
    pub fn ownership_report(&self) -> J {
        if self.ownership.is_none() {
            return json!({"enabled":false,"plan_prepared":!self.program.cell_ownership.markers.is_empty(),"stats":null,"pending_keys":0});
        }
        let mut internal = 0u64;
        let mut boundary = 0u64;
        let mut across = 0u64;
        let mut references = HashMap::<Signal, usize>::default();
        if let Some(m) = &self.ownership {
            assert_eq!(
                m.stats.boundary_live,
                m.boundaries.values().map(|x| x.len() as u64).sum::<u64>()
            );
            assert_eq!(m.stats.owned_live, m.tables.iter().sum::<usize>() as u64);
            assert_eq!(
                m.stats.signal_bindings_live,
                m.composition
                    .components
                    .iter()
                    .flatten()
                    .map(|c| c.signals.iter().flatten().count() as u64)
                    .sum::<u64>()
            );
            assert_eq!(
                m.stats.components_live,
                m.composition.components.iter().flatten().count() as u64
            );
            assert_eq!(
                m.stats.owned_live,
                m.composition
                    .live_facts
                    .iter()
                    .map(|&n| n as u64)
                    .sum::<u64>()
            );
            assert_eq!(
                m.composition.frames.len(),
                m.composition
                    .components
                    .iter()
                    .flatten()
                    .map(|c| c.frames.len())
                    .sum::<usize>()
            );
            for (&id, signals) in &m.boundaries {
                for &signal in signals {
                    assert_eq!(
                        m.composition.components[signal.component as usize]
                            .as_ref()
                            .unwrap()
                            .signals[signal.symbol].map(|bound| root(&self.parents, bound)),
                        Some(id)
                    );
                    assert!(!self.signal_is_native(signal, id));
                }
            }
            for cell in self.cells.cell_ids() {
                for (f, s) in self.cells.fact_states(cell).filter(|(_, s)| s.owned) {
                    #[cfg(not(feature = "sparse-cells"))]
                    assert!(!self.dependencies.contains_key(&Dependency::Fact(f)));
                    across += u64::from(s.born < self.epoch);
                    let program =
                        &self.program.cell_ownership.markers[self.cells.cell_metadata(f.cell).unwrap().template].program;
                    let values = if let Some(stored) = self.stable_node_unmetered(f) {
                        self.stable_values(&stored, false).expect("read owned stable body")
                    } else { s.decoded.as_ref().expect("settled owned body").1.clone() };
                    for (column, v) in values.iter().enumerate() {
                        if let Value::Eq(id) = v {
                            assert_eq!(*id, root(&self.parents, *id), "owned body is stale");
                            let signal = self.composed_signal(
                                f.cell,
                                program.fields[f.op as usize][column].unwrap(),
                            );
                            assert_eq!(
                                m.composition.components[signal.component as usize]
                                    .as_ref()
                                    .unwrap()
                                    .signals[signal.symbol].map(|bound| root(&self.parents, bound)),
                                Some(*id)
                            );
                            *references.entry(signal).or_default() += 1;
                            if self.signal_is_native(signal, *id) {
                                internal += 1;
                            } else {
                                boundary += 1;
                                assert!(
                                    m.boundaries
                                        .get(id)
                                        .is_some_and(|b| b.contains(&signal)),
                                    "missing owner boundary"
                                );
                            }
                        }
                    }
                }
            }
        }
        assert_eq!(
            internal + boundary,
            references.values().sum::<usize>() as u64
        );
        let active_bindings = references.len();
        let programs = self
            .program
            .cell_ownership
            .markers
            .iter()
            .map(|m| Arc::as_ptr(&m.program))
            .collect::<BTreeSet<_>>()
            .len();
        json!({"routing":"baked local fragments; unknown continuations retain external boundaries", "enabled":true,"plan_summary":{"schema":self.program.cell_ownership.format.marker_schema(),"port_programs":programs,"fragments":self.program.cell_ownership.composition.transitions.len(),"max_frames":self.program.cell_ownership.composition.max_frames},
            "barriers":self.ownership.as_ref().map(|m|&m.barriers),
            "barrier_history":self.ownership.as_ref().map(|m|json!({"enabled":m.keep_barrier_history,
                "start_after_barriers":m.barrier_history_start,"retained_capacity_bytes":m.barriers.capacity()*std::mem::size_of::<Barrier>()})),
            "inventory":{"shared_field_layout_bytes":0,"component_lifetime_capacity_bytes":self.ownership.as_ref().unwrap().composition.live_facts.capacity()*std::mem::size_of::<usize>(),"allocated_signal_slots":self.ownership.as_ref().unwrap().composition.components.iter().flatten().map(|c|c.signals.capacity()).sum::<usize>(),"active_signal_bindings":active_bindings,"retained_inactive_signal_bindings":self.ownership.as_ref().unwrap().stats.signal_bindings_live - active_bindings as u64,"shared_port_programs":programs,"baked_composition_recipes":self.program.cell_ownership.composition.transitions.len(),"runtime_composition_shapes":self.ownership.as_ref().map_or(0,|m|m.composition.shapes.iter().flatten().count()),"internal_eq_ports":internal,"boundary_eq_ports":boundary,"cross_stage_live_facts":across,"largest_component_frames":self.ownership.as_ref().map_or(0,|m|m.composition.components.iter().flatten().map(|c|c.frames.len()).max().unwrap_or(0)),
                "eligible_live_facts":self.program.cell_ownership.tables.iter().enumerate().filter(|(_,ok)|**ok).map(|(t,_)|self.witness_count(t)).sum::<usize>(),
                "unsupported_live_rows":self.program.cell_ownership.tables.iter().enumerate().filter(|(_,ok)|!**ok).map(|(t,_)|self.witness_count(t)).sum::<usize>()},
            "stats":self.ownership.as_ref().map(|m|&m.stats),"pending_keys":self.ownership.as_ref().map_or(0,|m|m.pending.len())})
    }
}

impl Graph {
    pub(super) fn inherited_cell_slot(&self, cell: u32, template: usize, slot: usize) -> Option<Value> {
        let m = self.ownership.as_ref()?;
        let frame = m.composition.frames.get(&cell)?;
        let component = m.composition.components.get(frame.component as usize)?.as_ref()?;
        let local = self.program.cell_ownership.markers[template].program.slots.get(slot).copied().flatten()?;
        let symbol = m.composition.shapes[component.shape].as_ref()?.ports[frame.ordinal][local];
        Some(Value::Eq(root(&self.parents, component.signals[symbol]?)))
    }
    /// Transfer only completed, proven-equal slots to existing shared symbols.
    /// It does not introduce a binding table or retire externally visible facts.
    #[cfg(all(feature="sparse-cells", feature="storage-metrics"))]
    pub(super) fn take_over_instance_slots(&mut self) -> usize {
        let Some(m) = self.ownership.as_ref() else { return 0; };
        let mut saved = 0;
        let ids = self.cells.iter().map(|(&id,_)|id).collect::<Vec<_>>();
        for id in ids {
            let c = self.cells.get_mut(&id).unwrap();
            if !c.completed { continue; }
            let Some(frame) = m.composition.frames.get(&id) else { continue; };
            let component = m.composition.components[frame.component as usize].as_ref().unwrap();
            let ports = &m.composition.shapes[component.shape].as_ref().unwrap().ports[frame.ordinal];
            let slots = &self.program.cell_ownership.markers[c.template].program.slots;
            let removed = c.values.retain_owned(|slot, value| {
                let Value::Eq(value) = value else { return true; };
                let Some(local) = slots.get(*slot).copied().flatten() else { return true; };
                let Some(bound) = component.signals[ports[local]] else { return true; };
                root(&self.parents, *value) != root(&self.parents, bound)
            });
            if removed != 0 { c.symbolic_slots = true; }
            saved += removed;
        }
        saved
    }
    #[cfg(all(feature="sparse-cells", feature="storage-metrics"))]
    pub(super) fn take_over_parent_links(&mut self) -> Result<usize> {
        let ids = self.cells.iter().filter(|(_,c)| c.completed && c.parent.is_some())
            .map(|(&id,_)|id).collect::<Vec<_>>();
        let mut detached = 0;
        for id in ids {
            let c = &self.cells[&id];
            let template = c.template;
            let parent = c.parent.unwrap();
            // Compute the whole handoff before changing ownership. Failed or
            // uncovered projections keep the source frame's normal lifetime.
            let mut owned = Vec::new();
            let mut delegated = false;
            for &slot in self.program.templates[template].parent_columns.keys() {
                let value = self.slot(id, slot)?;
                if self.inherited_cell_slot(id, template, slot).as_ref() == Some(&value) {
                    delegated = true;
                } else {
                    owned.push((slot, value));
                }
            }
            let c = self.cells.get_mut(&id).unwrap();
            for (slot,value) in owned { c.values.insert(slot,value); }
            c.symbolic_slots |= delegated;
            c.parent = None;
            self.release_reference(parent);
            detached += 1;
        }
        self.collect_garbage();
        Ok(detached)
    }

}

#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
#[path="shared_owner_transfer.rs"]
mod shared_owner_transfer;

#[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
impl Runtime {
    /// Destructive observer only. Preserve last-owner accounting, and never
    /// allocate the output buffer while measuring a field release.
    pub(super) fn release_runtime_storage(self, live: &impl Fn()->usize, rows: &mut Vec<(&'static str,usize)>) {
        assert!(rows.capacity()-rows.len()>=17);
        macro_rules! release {
            ($name:literal,$value:expr)=>{{
                let before=live();drop($value);rows.push(($name,before-live()));
            }};
        }
        release!("ownership.components",self.composition.components);
        release!("ownership.live_facts",self.composition.live_facts);
        release!("ownership.frames",self.composition.frames);
        release!("ownership.shapes",self.composition.shapes);
        release!("ownership.transitions",self.composition.learned_transitions);
        release!("ownership.training",self.composition.training);
        release!("ownership.catalog_trace",self.composition.catalog_trace);
        release!("ownership.entry",self.composition.entry);
        release!("ownership.heap",self.composition.heap);
        release!("ownership.columns",self.composition.columns);
        release!("ownership.boundaries",self.boundaries);
        release!("ownership.port_completion",self.port_completion);
        release!("ownership.pending",self.pending);
        release!("ownership.tables",self.tables);
        release!("ownership.stats",self.stats);
        release!("ownership.barriers",self.barriers);
    }
}
