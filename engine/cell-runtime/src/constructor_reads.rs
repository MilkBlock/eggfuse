//! Complete, borrowed constructor queries at a settled source Run boundary.
//! Candidate domains and static wiring are authoritative existing storage.
//! No coordinator candidate pass, graph copy or new reverse index is needed.
use super::*;
use ports::guard;

#[derive(Default, Serialize)]
pub(crate) struct Work {
    pub canonical_lookups: u64,
    pub canonical_candidates: u64,
    pub canonical_field_checks: u64,
    pub canonical_result_reads: u64,
    pub lookups: u64,
    pub candidates: u64,
    pub hint_probes: u64,
    pub hint_hits: u64,
    pub domains: u64,
    pub signal_visits: u64,
    pub slice_steps: u64,
    pub column_checks: u64,
    pub type_guards: u64,
    pub type_rejections: u64,
    pub results: u64,
    pub class_probes: u64,
    pub class_jumps: u64,
    pub signal_root_lookups: u64,
    pub signal_parent_probes: u64,
    pub domain_key_fields: u64,
    pub metadata_reads: u64,
    pub candidate_pushes: u64,
    pub candidate_growths: u64,
    pub candidate_sort_comparisons: u64,
    pub reads: guard::Work,
}
impl Work {
    pub fn add(&mut self, other: &Self) {
        macro_rules! add { ($($f:ident),*) => { $(self.$f += other.$f;)* }; }
        add!(lookups, candidates, hint_probes, hint_hits, domains, signal_visits, slice_steps,
            column_checks, type_guards, type_rejections, results, class_probes, class_jumps,
            signal_root_lookups, signal_parent_probes, domain_key_fields, metadata_reads,
            candidate_pushes, candidate_growths, candidate_sort_comparisons);
        add!(canonical_lookups, canonical_candidates, canonical_field_checks, canonical_result_reads);
        self.reads.node_lookups += other.reads.node_lookups;
        self.reads.port_reads += other.reads.port_reads;
        self.reads.parent_probes += other.reads.parent_probes;
        self.reads.key_fields += other.reads.key_fields;
    }
}
#[derive(Default)]
pub(crate) struct Scratch { candidates: Vec<FactRef> }
impl Scratch {
    pub fn clear(&mut self) { self.candidates.clear(); }
    pub fn capacity_bytes(&self) -> usize { self.candidates.capacity() * std::mem::size_of::<FactRef>() }
}

pub(in crate::graph) struct Read<'a> {
    owned_counts: &'a [usize],
    members: &'a [TableRows<u64>],
    cells: &'a arena::Cells,
    intern: &'a HashMap<u64, crate::tiny_set::TinySet<FactRef>>,
    hash_mask: u64,
    plan: &'a Plan,
    frames: &'a composition::Frames,
    components: crate::read_epoch::SlotsRead<'a, Option<composition::Component>>,
    shapes: &'a [Option<Arc<composition::Shape>>],
    boundaries: &'a HashMap<u64, crate::tiny_set::TinySet<Signal>>,
    classes: Option<&'a query_classes::Plan>,
    parents: &'a Parents,
    guard: guard::ReadView<'a>,
    key_columns: &'a [Option<Vec<usize>>],
    port_keys: bool,
}
impl Graph {
    pub(in crate::graph) fn constructor_query_table(&self, table: usize) -> bool {
        self.stable_ports.is_some() && self.program.tables[table].virtual_fact
            && self.ownership.as_ref().is_some_and(|o| o.tables[table] == self.witness_count(table))
            && self.program.cell_ownership.tables[table]
    }
    pub(in crate::graph) fn constructor_query_reader(&self) -> Option<Read<'_>> {
        let owner = self.ownership.as_ref()?;
        let guard = self.stable_port_reader().ok()?;
        Some(Read { owned_counts: &owner.tables, members: &self.members,
            cells: &self.cells, intern: &self.intern,
            hash_mask: self.constructor_hash_mask(),
            plan: &self.program.cell_ownership, frames: &owner.composition.frames,
            components: owner.composition.components.reader(), shapes: &owner.composition.shapes,
            boundaries: &owner.boundaries, parents: &self.parents, guard,
            classes: self.program.cell_ownership.query_classes.as_deref()
                .filter(|_| owner.composition.training.is_none()),
            key_columns: &self.program.repair_ports.key_eq_columns,
            port_keys: self.port_constructor_keys_active(),
        })
    }
    pub(crate) fn record_constructor_query_work(&self, w: &Work) {
        if w.lookups == 0 { return; }
        self.record_query_key_work(w);
        let s = &self.ownership.as_ref().unwrap().stats;
        macro_rules! add { ($f:ident, $v:expr) => { s.$f.set(s.$f.get() + $v); }; }
        add!(domain_planning_calls, w.domains); add!(domain_queries, w.domains);
        add!(domain_signal_visits, w.signal_visits); add!(domain_route_probes, w.signal_visits);
        add!(domain_slice_steps, w.slice_steps); add!(domain_column_checks, w.column_checks);
        add!(domain_type_guards, w.type_guards); add!(domain_type_rejections, w.type_rejections);
        add!(domain_results, w.results); add!(query_class_probes, w.class_probes);
        add!(query_class_range_jumps, w.class_jumps);
        add!(signal_root_queries, w.signal_root_lookups); add!(signal_parent_probes, w.signal_parent_probes);
    }
}
impl Read<'_> {
    pub fn complete_table(&self, table: usize) -> bool {
        self.plan.tables[table] && self.owned_counts[table] == self.members[table].len()
    }
    fn native_signal(&self, id: u64, w: &mut Work) -> Option<Signal> {
        let cell = (id >> 32) as u32;
        let slot = (id as u32).checked_sub(1)? as usize;
        let frame = self.frames.get(&cell)?;
        let local = *self.plan.code_programs[frame.code].native.get(&slot)?;
        let component = self.components.get(frame.component as usize)?.as_ref()?;
        let shape = self.shapes[component.shape].as_ref()?;
        let symbol = shape.ports[frame.ordinal][local];
        let bound = component.signals[symbol]?;
        if bound != id {
            let (current, probes) = self.parents.reader().root_counted(bound);
            w.signal_root_lookups += 1; w.signal_parent_probes += probes;
            if current != id { return None; }
        }
        let class = self.plan.query_classes.as_ref().map_or(0, |classes| {
            let (frame, local) = shape.origins[symbol];
            classes.symbols[self.frames[&component.frames[frame]].code][local]
        });
        Some(Signal { class, component: frame.component, symbol })
    }
    fn candidate(&self, fact: FactRef, table: usize, key: &[Value], w: &mut Work)
        -> Result<Option<(Value, u64, Dependency, bool)>> {
        w.candidates += 1;
        let Some(node) = self.guard.node(fact, &mut w.reads) else { return Ok(None) };
        if !self.guard.key_matches(node, table, key, &mut w.reads)? { return Ok(None); }
        w.metadata_reads += 1;
        let state = self.cells.get(&fact.cell).and_then(|c| c.facts.get(&fact.op))
            .ok_or("live stable constructor has no lifecycle state")?;
        Ok(Some((self.guard.result(node, &mut w.reads)?, state.epoch, Dependency::Fact(fact), state.hidden)))
    }
    pub fn point(&self, table: usize, key: &[Value], scratch: &mut Scratch, w: &mut Work)
        -> Result<Option<(Value, u64, Dependency)>> {
        w.lookups += 1;
        let port_key = self.port_keys && self.key_columns[table].as_ref().is_some_and(|c| !c.is_empty());
        w.hint_probes += u64::from(port_key);
        for &fact in self.intern.get(&(hashkey(table, key) & self.hash_mask)).into_iter().flatten() {
            if let Some((value, epoch, fact, hidden)) = self.candidate(fact, table, key, w)? {
                w.hint_hits += u64::from(port_key);
                // The ordinary query filters visibility after selecting its
                // ordered exact candidate; do not pick a different hidden tie.
                return Ok((!hidden).then_some((value, epoch, fact)));
            }
        }
        if !port_key { return Ok(None); }
        w.domains += 1;
        // Complete ownership is checked once at admission. Every constructor
        // use is in shared wiring; legacy reverse uses cannot add a live peer.
        let mut domain = None;
        for (column, value) in key.iter().enumerate() {
            w.domain_key_fields += 1;
            let Value::Eq(id) = value else { continue };
            let native = self.native_signal(*id, w);
            let count = self.boundaries.get(id).map_or(0, |s| s.len()) + usize::from(native.is_some());
            if domain.as_ref().is_none_or(|&(_, _, _, best)| count < best) {
                domain = Some((column, *id, native, count));
            }
        }
        let Some((column, id, native, _)) = domain else { return Ok(None); };
        let native = native.filter(|s| self.classes.is_none_or(|plan| {
            w.class_probes += 1; plan.contains(s.class, table)
        }));
        scratch.candidates.clear();
        let mut signals = query_classes::Signals::new(self.boundaries.get(&id), self.classes, table, None);
        for signal in signals.by_ref().filter(|s| Some(*s) != native).chain(native) {
            w.signal_visits += 1;
            let component = self.components.get(signal.component as usize).and_then(Option::as_ref)
                .ok_or("expired query component")?;
            let shape = self.shapes[component.shape].as_ref().ok_or("missing query shape")?;
            let uses = composition::queries::FieldUses::new(component, shape, self.plan, signal.symbol, column);
            for position in 0..uses.len() {
                w.slice_steps += 1; w.column_checks += u64::from(!uses.indexed());
                let Some(fact) = uses.fact(position, false) else { continue };
                w.type_guards += 1;
                if self.plan.code_operators[self.frames[&fact.cell].code][fact.op as usize] != table {
                    w.type_rejections += 1; continue;
                }
                if self.guard.node(fact, &mut w.reads).is_none_or(|node| node.table != table) { continue; }
                w.candidate_pushes += 1;
                if scratch.candidates.len() == scratch.candidates.capacity() { w.candidate_growths += 1; }
                scratch.candidates.push(fact);
            }
        }
        w.class_probes += signals.probes; w.class_jumps += signals.jumps;
        scratch.candidates.sort_unstable_by(|a,b| { w.candidate_sort_comparisons += 1; a.cmp(b) });
        scratch.candidates.dedup();
        w.results += scratch.candidates.len() as u64;
        for &fact in &scratch.candidates {
            if let Some((value, epoch, fact, hidden)) = self.candidate(fact, table, key, w)? {
                return Ok((!hidden).then_some((value, epoch, fact)));
            }
        }
        Ok(None)
    }
}
