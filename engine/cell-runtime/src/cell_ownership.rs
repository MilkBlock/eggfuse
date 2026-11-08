//! Persistent, typed Cell ownership. Interior equality incidences have no
//! reverse subscriptions: shared symbolic programs route native results across
//! composed Cell frames. Foreign inputs and escaped aliases bind boundary ports.
use super::*;
use std::cell::Cell as Counter;
use std::rc::Rc;
#[path = "ownership_slices.rs"]
pub mod slices;
use slices::{Binding as SignalBinding, PortProgram, Signal};
#[path = "ownership_composition.rs"]
pub mod composition;

#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Plan {
    pub tables: Vec<bool>,
    pub markers: Vec<Marker>,
    pub programs: Vec<Rc<PortProgram>>,
    pub composition: composition::Plan,
    pub entries: Vec<Vec<usize>>,
    /// Shared publication table -> scheduled typed entry ports. Producer body
    /// operations reference these same table IDs; routes are shared, not
    /// expanded into a separate per-producer/per-consumer dependency graph.
    pub routes: Vec<Vec<(usize, usize)>>,
    pub max_continuation_facts: usize,
}
#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Marker {
    pub active: bool,
    pub bodies: Vec<bool>,
    pub unions: Vec<usize>,
    pub program_id: usize,
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
        let mut shared = BTreeMap::<PortProgram, (usize, Rc<PortProgram>)>::new();
        let markers = p
            .templates
            .iter()
            .map(|t| {
                let program = PortProgram::derive(p, t, &tables);
                let id=shared.len();
                let (program_id,program)=shared.entry(program.clone()).or_insert_with(|| (id,Rc::new(program))).clone();
                Marker {
                program, program_id,
                active: t.ops.iter().any(|op|matches!(op,Op::Let(_,Call::Table(table),_)|Op::Set(table,_,_) if tables[*table])),
                bodies: t
                    .ops
                    .iter()
                    .map(|op| matches!(op, Op::Let(_,Call::Table(table),_) | Op::Set(table,_,_) if tables[*table]))
                    .collect(),
                unions: t
                    .ops
                    .iter()
                    .enumerate()
                    .filter_map(|(i, op)| matches!(op, Op::Union(..)).then_some(i))
                    .collect(),
            }})
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
        let composition = composition::Plan::derive(p, &markers, &programs, &entries);
        let plan = Self {
            programs,
            composition,
            tables,
            markers,
            entries,
            routes,
            max_continuation_facts: 256,
        };
        if let Some(raw) = p.artifact.get("ownership_markers") {
            if *raw != plan.artifact(p) {
                return Err("ownership marker differs from typed entry/body wiring".into());
            }
        }
        Ok(plan)
    }
    pub fn artifact(&self, p: &Program) -> J {
        json!({"schema":"eggfuse-ownership-markers/v3", "recipe":p.artifact["recipe"]["sha256"],
            "entry_schedule":crate::checksum::artifact_digest(&p.artifact["entry_schedule"]),"plan":self,
            "contract":"checked scheduled bindings enter persistent scalar constructor owners; foreign roots are boundaries; no future union is assumed"})
    }
}
#[derive(Default, Serialize)]
struct Stats {
    marker_entries: u64,
    marker_anchor_reads: u64,
    marker_continuations: u64,
    cross_stage_continuations: u64,
    capacity_splits: u64,
    owners_created: u64,
    owners_retired: u64,
    owners_live: u64,
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
    carried_owners: u64,
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
    composition_missing_sources: u64,
    composition_foreign_inputs: u64,
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
    signal_bindings_created: u64,
    signal_bindings_retired: u64,
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
    domain_signal_visits: Counter<u64>,
    domain_slice_steps: Counter<u64>,
}
struct Owner {
    // Lifetime accounting only. Composed programs already describe all uses;
    // retaining a second destination set here adds birth/death maintenance.
    facts: usize,
    last_epoch: u64,
}
#[derive(Serialize)]
struct Barrier {
    epoch: u64,
    live_facts: u64,
    live_owners: u64,
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
    owners: Vec<Option<Owner>>,
    boundaries: HashMap<u64, BTreeSet<Signal>>,
    signals: HashMap<Signal, SignalBinding>,
    retire_owners: BTreeSet<u32>,
    pending: BTreeSet<FactRef>,
    pub(super) tables: Vec<usize>,
    entry: Option<u32>,
    stats: Stats,
    barriers: Vec<Barrier>,
}
impl Graph {
    pub fn ownership_enabled(&self) -> bool {
        self.ownership.is_some()
    }
    pub(super) fn ownership_settled(&self) -> bool {
        self.ownership
            .as_ref()
            .is_none_or(|m| m.pending.is_empty() && m.retire_owners.is_empty())
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
        self.ownership = Some(Runtime {
            composition: composition::Runtime::new(&self.program.cell_ownership.composition),
            owners: vec![],
            boundaries: HashMap::default(),
            signals: HashMap::default(),
            retire_owners: BTreeSet::new(),
            pending: BTreeSet::new(),
            tables: vec![0; self.program.tables.len()],
            entry: None,
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
            let owner = self.ensure_cell_owner(f.cell);
            self.subscribe_edges(Dependency::Fact(f), &[]);
            self.dependencies.remove(&Dependency::Fact(f));
            self.cells
                .get_mut(&f.cell)
                .unwrap()
                .facts
                .get_mut(&f.op)
                .unwrap()
                .owned_owner = Some(owner);
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
            m.owners[owner as usize].as_mut().unwrap().facts += 1;
            m.tables[row.table] += 1;
            m.stats.adopted_existing += 1;
            m.stats.owned_live += 1;
            self.attach_owned_signals(f, &row.values);
        }
        self.settle_owned_lifetimes()?;
        Ok(())
    }
    fn ensure_cell_owner(&mut self, cell: u32) -> u32 {
        let inherited = self.cells[&cell].owner;
        let m = self.ownership.as_mut().unwrap();
        if let Some(id) = inherited
            && m.owners.get(id as usize).is_some_and(Option::is_some)
        {
            if m.owners[id as usize].as_ref().unwrap().facts
                < self.program.cell_ownership.max_continuation_facts
            {
                return id;
            }
            m.stats.capacity_splits += 1;
        }
        let id = u32::try_from(m.owners.len()).expect("Cell owner capacity");
        m.owners.push(Some(Owner {
            facts: 0,
            last_epoch: self.epoch,
        }));
        m.stats.owners_created += 1;
        m.stats.owners_live += 1;
        self.cells.get_mut(&cell).unwrap().owner = Some(id);
        id
    }
    pub(crate) fn owner_entry(&self) -> Option<u32> {
        self.ownership.as_ref().and_then(|m| m.entry)
    }
    pub(crate) fn begin_owner_entry(&mut self, rid: usize, anchors: &[Option<Dependency>]) {
        let Some(m) = &mut self.ownership else { return };
        m.entry = None;
        m.stats.marker_entries += 1;
        for w in anchors.iter().copied().flatten() {
            m.stats.marker_anchor_reads += 1;
            let Dependency::Fact(f) = w else { continue };
            let Some(c) = self.cells.get(&f.cell) else {
                continue;
            };
            if !c.facts.get(&f.op).is_some_and(|s| s.owned) {
                continue;
            }
            let Some(owner) = c.facts[&f.op].owned_owner else {
                continue;
            };
            let Some(o) = m.owners[owner as usize].as_mut() else {
                continue;
            };
            if o.facts >= self.program.cell_ownership.max_continuation_facts {
                m.stats.capacity_splits += 1;
                continue;
            }
            m.stats.marker_continuations += 1;
            m.stats.cross_stage_continuations += u64::from(o.last_epoch != self.epoch);
            o.last_epoch = self.epoch;
            m.entry = Some(owner);
            break;
        }
        self.composition_entry(rid, anchors);
    }
    pub(crate) fn end_owner_entry(&mut self) {
        if let Some(m) = &mut self.ownership {
            m.entry = None;
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
        if !self.program.cell_ownership.markers[template].bodies[f.op as usize] {
            self.ownership.as_mut().unwrap().stats.uncovered_births += 1;
            return false;
        }
        self.ensure_cell_owner(f.cell);
        true
    }
    pub(super) fn publish_owned_birth(&mut self, f: FactRef, t: usize, fields: &[Value]) {
        let owner = self.cells[&f.cell].facts[&f.op].owned_owner.unwrap();
        let m = self.ownership.as_mut().unwrap();
        m.owners[owner as usize].as_mut().unwrap().facts += 1;
        m.tables[t] += 1;
        m.stats.owned_births += 1;
        m.stats.owned_live += 1;
        self.attach_owned_signals(f, fields);
    }
    fn signal_is_native(&self, signal: Signal, id: u64) -> bool {
        let cell = (id >> 32) as u32;
        let Some(slot) = (id as u32).checked_sub(1) else {
            return false;
        };
        let m = &self.ownership.as_ref().unwrap().composition;
        let Some(frame) = m.frames.get(&cell) else {
            return false;
        };
        if frame.component != signal.component {
            return false;
        }
        let Some(&local) = self.program.cell_ownership.programs[frame.program]
            .native
            .get(&(slot as usize))
        else {
            return false;
        };
        let c = m.components[frame.component as usize].as_ref().unwrap();
        m.shapes[c.shape].as_ref().unwrap().ports[frame.ordinal][local] == signal.symbol
    }
    fn native_signal(&self, id: u64) -> Option<Signal> {
        let cell = (id >> 32) as u32;
        let slot = (id as u32).checked_sub(1)? as usize;
        let m = self.ownership.as_ref()?;
        let frame = m.composition.frames.get(&cell)?;
        let local = *self.program.cell_ownership.programs[frame.program]
            .native
            .get(&slot)?;
        let signal = self.composed_signal(cell, local);
        m.signals.get(&signal).filter(|b| b.root == id)?;
        Some(signal)
    }
    fn boundary(&mut self, root: u64, signal: Signal) {
        let m = self.ownership.as_mut().unwrap();
        m.stats.boundary_insert_attempts += 1;
        if m.boundaries.entry(root).or_default().insert(signal) {
            m.stats.boundary_edges_created += 1;
            m.stats.boundary_live += 1;
        }
    }
    fn attach_owned_signals(&mut self, f: FactRef, fields: &[Value]) {
        self.ensure_composition_frame(f.cell);
        let m = self.ownership.as_mut().unwrap();
        let component = m.composition.frames[&f.cell].component;
        m.composition.components[component as usize]
            .as_mut()
            .unwrap()
            .live_facts += 1;
        let template = self.cells[&f.cell].template;
        let program = self.program.cell_ownership.markers[template]
            .program
            .clone();
        for (column, symbol) in program.fields[f.op as usize].iter().enumerate() {
            let Some(symbol) = *symbol else {
                continue;
            };
            let Value::Eq(id) = fields[column] else {
                panic!("typed equality port");
            };
            let signal = self.composed_signal(f.cell, symbol);
            let native = self.signal_is_native(signal, id);
            let m = self.ownership.as_mut().unwrap();
            m.stats.signal_port_attaches += 1;
            m.stats.signal_binding_reads += 1;
            m.stats.internal_ports_seen += u64::from(native);
            m.stats.boundary_ports_seen += u64::from(!native);
            if let Some(binding) = m.signals.get_mut(&signal) {
                assert_eq!(binding.root, id, "symbolic alias disagrees with live port");
                binding.live_ports += 1;
            } else {
                m.signals.insert(
                    signal,
                    SignalBinding {
                        root: id,
                        live_ports: 1,
                    },
                );
                m.stats.signal_bindings_created += 1;
                m.stats.signal_bindings_live += 1;
                if !native {
                    self.boundary(id, signal);
                }
            }
        }
    }
    fn detach_owned_signals(&mut self, f: FactRef) {
        let template = self.cells[&f.cell].template;
        let program = self.program.cell_ownership.markers[template]
            .program
            .clone();
        let m = self.ownership.as_mut().unwrap();
        let frame = m.composition.frames[&f.cell];
        let shape = m.composition.components[frame.component as usize]
            .as_ref()
            .unwrap()
            .shape;
        for &symbol in program.fields[f.op as usize].iter().flatten() {
            let signal = Signal {
                component: frame.component,
                symbol: m.composition.shapes[shape].as_ref().unwrap().ports[frame.ordinal][symbol],
            };
            m.stats.signal_port_detaches += 1;
            m.stats.signal_binding_reads += 1;
            let binding = m.signals.get_mut(&signal).unwrap();
            binding.live_ports -= 1;
            if binding.live_ports != 0 {
                continue;
            }
            let id = binding.root;
            m.signals.remove(&signal);
            m.stats.signal_bindings_retired += 1;
            m.stats.signal_bindings_live -= 1;
            if let Some(set) = m.boundaries.get_mut(&id) {
                if set.remove(&signal) {
                    m.stats.boundary_live -= 1;
                    m.stats.boundary_edges_removed += 1;
                }
                if set.is_empty() {
                    m.boundaries.remove(&id);
                }
            }
        }
    }
    /// Execute the marker's original union instruction at its source position.
    /// The resulting committed equality activates the shared signal programs;
    /// neither an unexecuted instruction nor a predicted congruence is a proof.
    pub(crate) fn enqueue_marker_union(&mut self, cell: u32, op: usize) -> Result<()> {
        let template = self.rhs_frame(cell).ok_or("missing union frame")?.template;
        let [a, b] = self.program.cell_ownership.markers[template].program.unions[op]
            .clone()
            .ok_or("missing union marker instruction")?;
        let a = self.argument(cell, &a)?;
        let b = self.argument(cell, &b)?;
        self.ownership.as_mut().unwrap().stats.marker_union_requests += 1;
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
    pub(super) fn propagate_owned_union(&mut self, from: u64, to: u64) {
        if self.ownership.is_none() {
            return;
        }
        let native = self.native_signal(from);
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
        for signal in signals.into_iter().chain(native) {
            let intrinsic = self.signal_is_native(signal, to);
            let m = self.ownership.as_mut().unwrap();
            m.stats.signal_activations += 1;
            m.signals.get_mut(&signal).unwrap().root = to;
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
            self.project_owned_ports(fact, &columns, from, to);
        }
        let m = self.ownership.as_mut().unwrap();
        m.stats.dispatch_scratch_bytes = heap.capacity()
            * std::mem::size_of::<composition::Cursor>()
            + columns.capacity() * std::mem::size_of::<usize>();
        m.composition.heap = heap;
        m.composition.columns = columns;
    }
    fn project_owned_ports(&mut self, f: FactRef, columns: &[usize], from: u64, to: u64) {
        let m = self.ownership.as_mut().unwrap();
        m.stats.body_visits += 1;
        let s = self
            .cells
            .get_mut(&f.cell)
            .unwrap()
            .facts
            .get_mut(&f.op)
            .unwrap();
        let (table, fields) = s.decoded.as_mut().expect("owned canonical body");
        let table = *table;
        let mut changed = false;
        let mut key = false;
        for &i in columns {
            m.stats.port_checks += 1;
            if fields[i] == Value::Eq(from) {
                m.stats.changed_ports += 1;
                m.stats.row_copies += u64::from(Rc::strong_count(fields) > 1);
                Rc::make_mut(fields)[i] = Value::Eq(to);
                changed = true;
                key |= i + 1 < fields.len();
            } else {
                m.stats.unchanged_port_checks += 1;
            }
        }
        if !changed {
            return;
        }
        let singleton = self
            .intern
            .get(&s.hash)
            .is_some_and(|b| b.len() == 1 && b.first() == Some(&f));
        if !key && singleton && !m.pending.contains(&f) {
            s.epoch = self.epoch;
            self.query_versions[table] += 1;
            self.changes.touch(table, Dependency::Fact(f));
            m.stats.result_publications += 1;
        } else {
            m.stats.key_enqueues += u64::from(m.pending.insert(f));
            self.dirty_facts[table].insert(f);
        }
    }
    pub(super) fn pop_owned_before(&mut self, next: Option<Dependency>) -> Option<FactRef> {
        let m = self.ownership.as_mut()?;
        let f = *m.pending.first()?;
        if next.is_some_and(|d| d < Dependency::Fact(f)) {
            return None;
        }
        m.pending.pop_first();
        Some(f)
    }
    pub(super) fn complete_owned_key(&mut self, f: FactRef) -> Result<()> {
        let Some(r) = self.fact(f)? else {
            return Ok(());
        };
        self.dirty_facts[r.table].remove(&f);
        self.ownership.as_mut().unwrap().stats.key_completions += 1;
        let h = hashkey(r.table, &r.values[..r.values.len() - 1]);
        let found = self.find_repair_collision(f, &r, h)?;
        if let Some(other) = &found {
            self.enqueue_union(
                r.values.last().unwrap().clone(),
                other.values.last().unwrap().clone(),
            )?;
        }
        self.commit_fact_repair(f, r, h, found)
    }
    pub(super) fn retire_owned(&mut self, f: FactRef, t: usize, _fields: &[Value]) -> bool {
        if !self.cells[&f.cell].facts[&f.op].owned {
            return false;
        }
        let owner = self.cells[&f.cell].facts[&f.op].owned_owner.unwrap();
        self.detach_owned_signals(f);
        self.composition_retire_fact(f.cell);
        let m = self.ownership.as_mut().unwrap();
        m.owners[owner as usize].as_mut().unwrap().facts -= 1;
        m.pending.remove(&f);
        m.retire_owners.insert(owner);
        m.tables[t] -= 1;
        m.stats.owned_live -= 1;
        m.stats.owned_retirements += 1;
        true
    }
    pub(super) fn settle_owned_lifetimes(&mut self) -> Result<()> {
        let Some(m) = &mut self.ownership else {
            return Ok(());
        };
        // Only release empty lifetime owners. Boundary membership is maintained
        // at signal birth/death/alias, never by traversing an owner's body.
        while let Some(owner) = m.retire_owners.pop_first() {
            if m.owners[owner as usize].as_ref().unwrap().facts == 0 {
                m.owners[owner as usize] = None;
                m.stats.owners_live -= 1;
                m.stats.owners_retired += 1;
            }
        }
        Ok(())
    }
    pub(crate) fn ownership_barrier(&mut self) {
        if let Some(m) = &mut self.ownership {
            assert!(
                m.pending.is_empty() && m.retire_owners.is_empty(),
                "unsettled owner at publication boundary"
            );
            m.stats.stage_barriers += 1;
            m.stats.carried_facts += m.stats.owned_live;
            m.stats.carried_owners += m.stats.owners_live;
            m.barriers.push(Barrier {
                epoch: self.epoch,
                live_facts: m.stats.owned_live,
                live_owners: m.stats.owners_live,
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
    fn signal_domain(&self, id: u64) -> BTreeSet<Signal> {
        let m = self.ownership.as_ref().unwrap();
        let mut signals = m.boundaries.get(&id).cloned().unwrap_or_default();
        if let Some(signal) = self.native_signal(id) {
            signals.insert(signal);
        }
        signals
    }
    fn smallest_signal_domain(
        &self,
        bound: &[Option<Value>],
    ) -> Option<(u64, BTreeSet<Signal>, usize)> {
        let m = self.ownership.as_ref()?;
        m.stats
            .domain_planning_calls
            .set(m.stats.domain_planning_calls.get() + 1);
        bound
            .iter()
            .filter_map(|v| {
                let Some(Value::Eq(id)) = v else {
                    return None;
                };
                let id = root(&self.parents, *id);
                let signals = self.signal_domain(id);
                m.stats
                    .domain_planning_signals
                    .set(m.stats.domain_planning_signals.get() + signals.len() as u64);
                let count = signals
                    .iter()
                    .map(|s| m.signals[s].live_ports)
                    .sum::<usize>()
                    + self.uses.get(&id).map_or(0, UseSet::len);
                Some((id, signals, count))
            })
            .min_by_key(|x| x.2)
    }
    pub(super) fn owned_candidate_count(&self, table: usize, bound: &[Option<Value>]) -> usize {
        self.smallest_signal_domain(bound)
            .map_or(self.witness_count(table), |(_, _, n)| {
                n.min(self.witness_count(table))
            })
    }
    pub(super) fn owned_candidates(
        &self,
        table: usize,
        bound: &[Option<Value>],
    ) -> Vec<Dependency> {
        let Some((id, signals, _)) = self.smallest_signal_domain(bound) else {
            let rows = self.witnesses(table);
            let s = &self.ownership.as_ref().unwrap().stats;
            s.unbound_query_calls.set(s.unbound_query_calls.get() + 1);
            s.unbound_query_rows
                .set(s.unbound_query_rows.get() + rows.len() as u64);
            return rows;
        };
        let s = &self.ownership.as_ref().unwrap().stats;
        s.domain_queries.set(s.domain_queries.get() + 1);
        let mut result = BTreeSet::new();
        for signal in signals {
            s.domain_signal_visits.set(s.domain_signal_visits.get() + 1);
            let m = &self.ownership.as_ref().unwrap().composition;
            let component = m.components[signal.component as usize].as_ref().unwrap();
            for step in m.shapes[component.shape].as_ref().unwrap().signals[signal.symbol].iter() {
                s.domain_slice_steps.set(s.domain_slice_steps.get() + 1);
                let cell = component.frames[step.frame];
                if self
                    .cells
                    .get(&cell)
                    .and_then(|c| c.facts.get(&step.op))
                    .is_some_and(|s| s.owned && s.decoded.as_ref().unwrap().0 == table)
                {
                    result.insert(Dependency::Fact(FactRef { cell, op: step.op }));
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
        let mut internal = 0u64;
        let mut boundary = 0u64;
        let mut across = 0u64;
        let mut largest = 0;
        let mut references = HashMap::<Signal, usize>::default();
        if let Some(m) = &self.ownership {
            assert_eq!(
                m.stats.boundary_live,
                m.boundaries.values().map(|x| x.len() as u64).sum::<u64>()
            );
            assert_eq!(m.stats.owned_live, m.tables.iter().sum::<usize>() as u64);
            assert_eq!(
                m.stats.owned_live,
                m.owners
                    .iter()
                    .flatten()
                    .map(|o| o.facts as u64)
                    .sum::<u64>()
            );
            assert_eq!(m.stats.signal_bindings_live, m.signals.len() as u64);
            assert_eq!(
                m.stats.components_live,
                m.composition.components.iter().flatten().count() as u64
            );
            assert_eq!(
                m.stats.owned_live,
                m.composition
                    .components
                    .iter()
                    .flatten()
                    .map(|c| c.live_facts as u64)
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
                    assert_eq!(m.signals[&signal].root, id);
                    assert!(!self.signal_is_native(signal, id));
                }
            }
            // Inventory reconstruction is outside inference. No live owner
            // maintains a redundant per-fact reverse index for these checks.
            let mut owner_facts = vec![0; m.owners.len()];
            for (&cell, c) in self.cells.iter() {
                for (&op, s) in c.facts.iter().filter(|(_, s)| s.owned) {
                    let f = FactRef { cell, op };
                    assert!(!self.dependencies.contains_key(&Dependency::Fact(f)));
                    owner_facts[s.owned_owner.unwrap() as usize] += 1;
                    across += u64::from(s.born < self.epoch);
                    let program =
                        &self.program.cell_ownership.markers[self.cells[&f.cell].template].program;
                    for (column, v) in s
                        .decoded
                        .as_ref()
                        .expect("settled owned body")
                        .1
                        .iter()
                        .enumerate()
                    {
                        if let Value::Eq(id) = v {
                            assert_eq!(*id, root(&self.parents, *id), "owned body is stale");
                            let signal = self.composed_signal(
                                f.cell,
                                program.fields[f.op as usize][column].unwrap(),
                            );
                            assert_eq!(m.signals[&signal].root, *id);
                            *references.entry(signal).or_default() += 1;
                            if self.signal_is_native(signal, *id) {
                                internal += 1;
                            } else {
                                boundary += 1;
                                assert!(
                                    m.boundaries.get(id).is_some_and(|b| b.contains(&signal)),
                                    "missing owner boundary"
                                );
                            }
                        }
                    }
                }
            }
            for (owner, count) in m.owners.iter().zip(owner_facts) {
                assert_eq!(owner.as_ref().map_or(0, |o| o.facts), count);
                largest = largest.max(count);
            }
        }
        if let Some(m) = &self.ownership {
            assert_eq!(references.len(), m.signals.len());
            for (signal, n) in references {
                assert_eq!(m.signals[&signal].live_ports, n);
            }
            assert_eq!(
                internal + boundary,
                m.signals.values().map(|b| b.live_ports as u64).sum::<u64>()
            );
        }
        let programs = self
            .program
            .cell_ownership
            .markers
            .iter()
            .map(|m| Rc::as_ptr(&m.program))
            .collect::<BTreeSet<_>>()
            .len();
        json!({"routing":"composed symbolic port programs; boundary edges count external component slots", "enabled":self.ownership.is_some(),"plan":self.program.cell_ownership.artifact(&self.program),
            "barriers":self.ownership.as_ref().map(|m|&m.barriers),
            "inventory":{"shared_port_programs":programs,"baked_composition_recipes":self.program.cell_ownership.composition.transitions.len(),"runtime_composition_shapes":self.ownership.as_ref().map_or(0,|m|m.composition.shapes.iter().flatten().count()),"internal_eq_ports":internal,"boundary_eq_ports":boundary,"cross_stage_live_facts":across,"largest_owner":largest,
                "eligible_live_facts":self.program.cell_ownership.tables.iter().enumerate().filter(|(_,ok)|**ok).map(|(t,_)|self.witness_count(t)).sum::<usize>(),
                "unsupported_live_rows":self.program.cell_ownership.tables.iter().enumerate().filter(|(_,ok)|!**ok).map(|(t,_)|self.witness_count(t)).sum::<usize>()},
            "stats":self.ownership.as_ref().map(|m|&m.stats),"pending_keys":self.ownership.as_ref().map_or(0,|m|m.pending.len())})
    }
}
