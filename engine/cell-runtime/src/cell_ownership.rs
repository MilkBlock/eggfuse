//! Persistent, typed Cell ownership. Interior equality incidences have no
//! reverse subscriptions: shared symbolic programs route native results across
//! composed Cell frames. Foreign inputs and escaped aliases bind boundary ports.
use super::*;
use std::cell::Cell as Counter;
use std::rc::Rc;
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
#[path = "port_completion.rs"]
pub(crate) mod completion;

#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Plan {
    #[serde(skip)]
    format: wire::Format,
    pub tables: Vec<bool>,
    pub markers: Vec<Marker>,
    pub programs: Vec<Rc<PortProgram>>,
    /// Structure-of-arrays dispatch: native ports retain a compact pointer
    /// array; operator tags are compiled separately from source instructions.
    #[serde(skip)]
    pub code_programs: Vec<Rc<PortProgram>>,
    #[serde(skip)]
    pub code_operators: Vec<Vec<usize>>,
    #[serde(skip)]
    pub query_classes: Option<Rc<query_classes::Plan>>,
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
    pub program: Rc<PortProgram>,
}
impl Plan {
    pub(crate) fn derive(p: &Program) -> Result<Self> {
        let tables = p
            .repair_ports
            .key_eq_columns
            .iter()
            .map(Option::is_some)
            .collect::<Vec<_>>();
        let format = wire::Format::program(p)?;
        let mut shared = BTreeMap::new();
        let markers = p
            .templates
            .iter()
            .map(|t| {
                let program = Rc::new(PortProgram::derive(p, t, &tables));
                let legacy = (format == wire::Format::Legacy).then(|| wire::unions(t));
                let id = shared.len();
                let (program_id, program) = shared.entry((program.clone(), legacy))
                    .or_insert((id, program)).clone();
                Marker { program, program_id, code: 0 }
            })
            .collect::<Vec<_>>();
        let mut programs = vec![Rc::new(PortProgram::default()); shared.len()];
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
            programs,
            code_programs: vec![],
            code_operators: vec![],
            query_classes: None,
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
            plan.query_classes = Some(Rc::new(query_classes::Plan::validate(raw, p, &plan)?));
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
}
impl Graph {
    pub fn ownership_enabled(&self) -> bool {
        self.ownership.is_some()
    }
    pub(crate) fn needs_ownership_entry(&self, rid: usize) -> bool {
        self.ownership.as_ref().is_some_and(|m| {
            self.program.cell_ownership.markers[self.program.rules[rid].template].program.active()
                && (m.composition.training.is_some()
                    || self.program.cell_ownership.composition.active_rules[rid])
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
            self.subscribe_edges(Dependency::Fact(f), &[]);
            self.dependencies.remove(&Dependency::Fact(f));
            self.cells
                .get_mut(&f.cell)
                .unwrap()
                .facts
                .get_mut(&f.op)
                .unwrap()
                .owned = true;
            self.cells
                .get_mut(&f.cell)
                .unwrap()
                .facts
                .get_mut(&f.op)
                .unwrap()
                .decoded = Some((row.table, row.values.clone()));
            let m = self.ownership.as_mut().unwrap();
            m.tables[row.table] += 1;
            m.stats.adopted_existing += 1;
            m.stats.owned_live += 1;
            self.initialize_cell_fields::<true>(f, row.table, &row.values);
        }
        Ok(())
    }
    pub(crate) fn begin_owner_entry(&mut self, rid: usize, anchors: &[Option<Dependency>]) {
        if let Some(m) = &mut self.ownership {
            m.stats.marker_entries += 1;
        }
        self.composition_entry(rid, anchors);
    }
    pub(crate) fn end_owner_entry(&mut self) {
        if let Some(m) = &mut self.ownership {
            m.composition.entry_rule = None;
            m.composition.anchors.clear();
            m.composition.entry_template = None;
        }
    }
    pub(super) fn owns_birth(&mut self, f: FactRef) -> bool {
        if self.ownership.is_none() {
            return false;
        }
        let template = self.cells[&f.cell].template;
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
                            .cells
                            .get(&c.frames[step.frame])
                            .and_then(|cell| cell.facts.get(&step.op))
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
                .cells
                .get(&fact.cell)
                .and_then(|c| c.facts.get(&fact.op))
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
                let step = &m.composition.shapes[c.shape].as_ref().unwrap().signals
                    [cursor.signal.symbol][cursor.position];
                let old = columns.capacity();
                columns.extend_from_slice(&step.columns);
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
    pub(super) fn pop_owned_before(&mut self, next: Option<Dependency>, allowed: Option<&[bool]>) -> Option<FactRef> {
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
        if !self.cells[&f.cell].facts[&f.op].owned {
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
            m.barriers.push(Barrier {
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
            });
        }
    }
    fn smallest_signal_domain(&self, bound: &[Option<Value>]) -> Option<(usize, u64)> {
        let m = self.ownership.as_ref()?;
        m.stats
            .domain_planning_calls
            .set(m.stats.domain_planning_calls.get() + 1);
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
                    + self.uses.get(&id).map_or(0, UseSet::len);
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
        let Some((column, id)) = self.smallest_signal_domain(bound) else {
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
                // The instance selects concrete compiled code even when its
                // port layout is shared with other operators. Discriminate
                // with that code before probing any live node directory.
                let frame = m.frames[&fact.cell];
                let operator = self.program.cell_ownership.code_operators[frame.code][fact.op as usize];
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
                    self.cells.get(&fact.cell).and_then(|c| c.facts.get(&fact.op))
                        .is_some_and(|state| state.owned && state.decoded.as_ref().unwrap().0 == table)
                };
                if matches {
                    result.insert(Dependency::Fact(fact));
                }
            }
        }
        for &d in self.uses.get(&id).into_iter().flat_map(|s| s.iter()) {
            s.domain_legacy_visits.set(s.domain_legacy_visits.get() + 1);
            if self.dependency_table(d) == Some(table) {
                result.insert(d);
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
            for (&cell, c) in self.cells.iter() {
                for (&op, s) in c.facts.iter().filter(|(_, s)| s.owned) {
                    let f = FactRef { cell, op };
                    assert!(!self.dependencies.contains_key(&Dependency::Fact(f)));
                    across += u64::from(s.born < self.epoch);
                    let program =
                        &self.program.cell_ownership.markers[self.cells[&f.cell].template].program;
                    let values = if let Some(stored) = self.stable_ports.as_ref().and_then(|p| p.nodes.get(&f)) {
                        self.stable_values(stored, false).expect("read owned stable body")
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
            .map(|m| Rc::as_ptr(&m.program))
            .collect::<BTreeSet<_>>()
            .len();
        json!({"routing":"baked local fragments; unknown continuations retain external boundaries", "enabled":true,"plan_summary":{"schema":self.program.cell_ownership.format.marker_schema(),"port_programs":programs,"fragments":self.program.cell_ownership.composition.transitions.len(),"max_frames":self.program.cell_ownership.composition.max_frames},
            "barriers":self.ownership.as_ref().map(|m|&m.barriers),
            "inventory":{"component_lifetime_capacity_bytes":self.ownership.as_ref().unwrap().composition.live_facts.capacity()*std::mem::size_of::<usize>(),"allocated_signal_slots":self.ownership.as_ref().unwrap().composition.components.iter().flatten().map(|c|c.signals.capacity()).sum::<usize>(),"active_signal_bindings":active_bindings,"retained_inactive_signal_bindings":self.ownership.as_ref().unwrap().stats.signal_bindings_live - active_bindings as u64,"shared_port_programs":programs,"baked_composition_recipes":self.program.cell_ownership.composition.transitions.len(),"runtime_composition_shapes":self.ownership.as_ref().map_or(0,|m|m.composition.shapes.iter().flatten().count()),"internal_eq_ports":internal,"boundary_eq_ports":boundary,"cross_stage_live_facts":across,"largest_component_frames":self.ownership.as_ref().map_or(0,|m|m.composition.components.iter().flatten().map(|c|c.frames.len()).max().unwrap_or(0)),
                "eligible_live_facts":self.program.cell_ownership.tables.iter().enumerate().filter(|(_,ok)|**ok).map(|(t,_)|self.witness_count(t)).sum::<usize>(),
                "unsupported_live_rows":self.program.cell_ownership.tables.iter().enumerate().filter(|(_,ok)|!**ok).map(|(t,_)|self.witness_count(t)).sum::<usize>()},
            "stats":self.ownership.as_ref().map(|m|&m.stats),"pending_keys":self.ownership.as_ref().map_or(0,|m|m.pending.len())})
    }
}
