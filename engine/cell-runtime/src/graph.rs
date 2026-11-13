//! Rows are temporary views of shared recipes, never a constructor row store.
#[path = "union_digest.rs"]
mod union_digest;
#[path = "repair_ports.rs"]
pub(crate) mod repair_ports;
#[cfg(feature = "spine-blocks")]
#[path = "repair_cells.rs"]
pub mod repair_cells;
#[path = "maintenance.rs"]
pub mod maintenance;
#[path = "local_union_cells.rs"]
pub mod local_union_cells;
#[path = "cell_ownership.rs"]
pub mod cell_ownership;
#[path="fact_states.rs"]
mod fact_states;
pub(crate) use fact_states::FactStates;
use crate::program::*;
use crate::value::{self, Parents, Value, canon, exported, root};
use rustc_hash::FxHashMap as HashMap;
use serde::{Deserialize, Serialize};
use serde_json::{Value as J, json};
use std::collections::{BTreeMap, BTreeSet};
use std::hash::{Hash, Hasher};

#[cfg(feature = "sparse-cells")]
pub type RowFields = std::sync::Arc<[Value]>;
#[cfg(feature = "sparse-cells")]
use crate::ordered_run::OrderedRun as TableRows;
#[cfg(not(feature = "sparse-cells"))]
type TableRows<T> = BTreeSet<T>;
#[cfg(not(feature = "sparse-cells"))]
pub type RowFields = std::rc::Rc<Vec<Value>>;
pub(crate) fn row_fields(v: Vec<Value>) -> RowFields {
    #[cfg(feature = "sparse-cells")]
    {
        v.into()
    }
    #[cfg(not(feature = "sparse-cells"))]
    {
        std::rc::Rc::new(v)
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct FactRef {
    pub cell: u32,
    pub op: u32,
}
impl FactRef {
    fn ordered_id(self) -> u64 {
        (u64::from(self.cell) << 32) | u64::from(self.op)
    }
    fn from_ordered_id(word: u64) -> Self {
        Self { cell: (word >> 32) as u32, op: word as u32 }
    }
}
/// Copied fields only need source-owner identities for containment candidates.
/// Provider projection additionally needs atom/operation coordinates.

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FactState {
    #[serde(skip)]
    owned: bool,
    #[serde(skip)]
    local_union_owned: bool,
    #[cfg(feature = "receipt-slots")]
    #[serde(skip)]
    port_slot: u32,
    // Canonicalized on read, like an explicit Unit-function key. Reconstructed
    // from the checked recipe on checkpoint restore; never trusted serialized data.

    // Snapshot of the ordinary recipe's fields. Ordinary repair clears it;
    // digest matching updates the shared fields with copy-on-write instead.
    // Never checkpoint it.
    #[serde(skip)]
    decoded: Option<(usize, RowFields)>,
    #[serde(default)]
    pub entry: Option<FactRef>,
    pub hidden: bool,
    pub epoch: u64,
    pub born: u64,
    pub hash: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Cell {
    /// Equality slots delegated to this instance's existing composed symbols.
    #[serde(default)]
    pub symbolic_slots: bool,
    #[serde(default)]
    pub completed_prefix: usize,
    #[serde(default)]
    pub started_epoch: u64,
    #[serde(default)]
    pub completed: bool,

    pub template: usize,
    pub parent: Option<FactRef>,
    pub values: crate::slots::FrameSlots,
    pub facts: crate::slots::FrameMap<u32, FactState>,
    #[serde(default)]
    pub recipe_depth: u32,
}
#[derive(Clone,Copy)]
pub(crate) struct CellMetadata {
    pub template:usize,
    pub started_epoch:u64,
    pub completed_prefix:usize,
    pub recipe_depth:u32,
    pub completed:bool,
    pub symbolic_slots:bool,
}
impl From<&Cell> for CellMetadata {
    fn from(c:&Cell)->Self {Self{template:c.template,started_epoch:c.started_epoch,
        completed_prefix:c.completed_prefix,recipe_depth:c.recipe_depth,completed:c.completed,symbolic_slots:c.symbolic_slots}}
}
#[cfg(feature = "sparse-cells")]
#[path = "cell_births.rs"]
pub(crate) mod cell_births;
#[path = "function_row.rs"]
mod function_row;
#[derive(Clone, Debug)]
pub struct Function {
    #[cfg(feature = "sparse-cells")]
    writer: Option<Box<writer_frames::Writer>>,
    #[cfg(feature = "receipt-slots")]
    port_slot: u32,
    pub table: usize,
    fields: RowFields,
    canonical: bool,
    projected: bool,
    pub epoch: u64,
    pub live: bool,
    pub origin: Option<FactRef>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub enum Dependency {
    Fact(FactRef),
    Function(usize),
}
#[cfg(not(feature = "sparse-cells"))]
type UseSet = BTreeSet<Dependency>;

#[cfg(feature = "sparse-cells")]
#[path = "reverse_uses.rs"]
mod reverse_uses;
#[cfg(feature = "sparse-cells")]
use reverse_uses::UseSet;
#[derive(Clone, Debug)]
pub struct Row {
    pub table: usize,
    pub values: RowFields,
    pub hidden: bool,
    pub epoch: u64,
    pub witness: Dependency,
}
/// A complete-key Cell query already owns its inputs. Carry only the returned
/// value and the original row's validity/ownership metadata into its suffix.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Point {
    pub value: Value,
    pub hidden: bool,
    pub epoch: u64,
    pub witness: Dependency,
}
impl From<&Row> for Point {
    fn from(row: &Row) -> Self {
        Self { value: row.values.last().expect("query row result").clone(),
            hidden: row.hidden, epoch: row.epoch, witness: row.witness }
    }
}
#[cfg(test)]
#[path = "point_results_test.rs"]
mod point_results_test;
#[derive(Default, Clone, Debug, Serialize, Deserialize)]
pub struct Stats {
    #[serde(default)]
    pub rhs_pending_probes:u64,
    #[serde(default)]
    pub rhs_pending_stops:u64,
    #[serde(default)]
    pub rhs_pending_key_spills:u64,
    #[serde(default)]
    pub rhs_pending_key_bytes:u64,
    #[serde(default)]
    pub constructor_prefix_checks: u64,
    #[serde(default)]
    pub constructor_prefix_table_checks: u64,
    #[serde(default)]
    pub constructor_prefix_rejected: u64,
    #[serde(default)]
    pub constructor_prefix_discarded_slots: u64,
    #[serde(default)]
    pub constructor_prefix_frames: u64,
    #[serde(default)]
    pub constructor_prefix_operations: u64,
    #[serde(default)]
    pub constructor_prefix_receipt_writes: u64,
    #[serde(default)]
    pub rhs_context_suspends: u64,
    #[serde(default)]
    pub constructor_prepared_inputs: u64,
    #[serde(default)]
    pub constructor_cell_route_probes: u64,
    pub constructor_cell_route_witnesses: u64,
    pub constructor_cell_route_accepted: u64,
    #[serde(default)]
    pub constructor_cell_route_key_proved:u64,
    #[serde(default)]
    pub constructor_cell_route_source_checks:u64,
    #[serde(default)]
    pub constructor_cell_route_proof_admissions:u64,
    #[serde(default)]
    pub constructor_cell_route_key_fields_avoided:u64,
    pub constructor_prepared_checks: u64,
    #[serde(default)]
    pub constructor_prepared_fields: u64,
    #[serde(default)]
    pub constructor_prepared_accepted: u64,
    #[serde(default)]
    pub constructor_prepared_rejected: u64,
    #[serde(default)]
    pub constructor_prepared_certificates: u64,
    #[serde(default)]
    pub constructor_prepared_liveness_checks: u64,
    #[serde(default)]
    pub constructor_prepared_result_reads: u64,
    #[serde(default)]
    pub constructor_prepared_sealed: u64,
    #[serde(default)]
    pub constructor_prepared_key_fields_avoided: u64,
    #[serde(default)]
    pub rhs_context_resumes: u64,
    #[serde(default)]
    pub rhs_suspend_private: u64,
    #[serde(default)]
    pub rhs_suspend_public: u64,
    #[serde(default)]
    pub rhs_suspend_promotions: u64,
    #[serde(default)]
    pub rhs_suspend_holds: u64,
    #[serde(default)]
    pub rhs_suspend_releases: u64,
    #[serde(default)]
    pub rhs_suspend_invalidated: u64,
    #[serde(default)]
    pub function_point_reads: u64,
    #[serde(default)]
    pub merge_program_calls: u64,
    #[serde(default)]
    pub scalar_merge_calls: u64,
    #[serde(default)]
    pub scalar_unchanged: u64,
    #[serde(default)]
    pub scalar_old_projection: u64,
    #[serde(default)]
    pub merge_program_operations: u64,
    #[serde(default)]
    pub merge_program_constructs: u64,
    pub constructor_requests: u64,
    pub constructor_reused: u64,
    pub logical_facts_created: u64,
    pub function_updates: u64,
    pub merge_calls: u64,
    #[serde(default)]
    pub key_operations: u64,
    #[serde(default)]
    pub merge_port_reads: u64,
    #[serde(default)]
    pub merge_contract_calls: BTreeMap<String, u64>,
    pub unions: u64,
    pub repaired_dependencies: u64,
    #[serde(default)]
    pub decoded_rows: u64,
    pub residual_candidates: u64,
    pub bindings: u64,
    #[serde(default)]
    pub handoff_attempts: u64,
    #[serde(default)]
    pub handoff_missing: u64,
    #[serde(default)]
    pub handoff_stale: u64,
    #[serde(default)]
    pub handoff_lets: u64,
    #[serde(default)]
    pub handoff_sets: u64,
    #[serde(default)]
    pub handoff_noop_unions: u64,
    #[serde(default)]
    pub handoff_deep: u64,
    #[serde(default)]
    pub handoff_closed: u64,
    /// Cells completed from matched inputs and static aliases alone. Coverage,
    /// not an additional work credit: rhs_frames_avoided includes these Cells.
    #[serde(default)]
    pub matched_cells_completed: u64,
    #[serde(default)]
    pub handoff_closed_fallback: u64,
    #[serde(default)]
    pub register_seeds: u64,
    /// Actual computed result stores, including the prefix subset. Entry and
    /// expansion row fields are borrowed and do not need register assignments.
    #[serde(default)]
    pub register_result_writes: u64,
    #[serde(default)]
    pub register_expansion_rows: u64,
    #[serde(default)]
    pub register_prefix: crate::row_kernel::PrefixStats,
    #[serde(default)]
    pub idle_scheduled_runs: u64,
    #[serde(default)]
    pub shared_point_requests: u64,
    #[serde(default)]
    pub shared_point_hits: u64,
    #[serde(default)]
    pub shared_negative_hits: u64,
    #[serde(default)]
    pub sum_index_reads: u64,
    #[serde(default)]
    pub sum_index_skips: u64,
    #[serde(default)]
    pub register_answers: u64,
    #[serde(default)]
    pub single_writes: u64,
    #[serde(default)]
    pub prepared_rhs_operations: u64,
    #[serde(default)]
    pub prepared_rhs_later_operations: u64,
    #[serde(default)]
    pub completion_frame_result_writes: u64,
    #[serde(default)]
    pub completion_frame_growths: u64,
    #[serde(default)]
    pub completion_frame_growth_bytes: u64,
    #[serde(default)]
    pub completion_promoted_result_slots: u64,
    #[serde(default)]
    pub transient_writes: u64,
    pub direct_bindings: u64,
    #[serde(default)]
    pub direct_candidates: u64,
    pub cells_created: u64,
    #[serde(default)]
    pub rhs_frames_avoided: u64,
    pub empty_frames_released: u64,
    #[serde(default)]
    pub shared_owner_slots_delegated:u64,
    #[serde(default)]
    pub shared_owner_segment_extensions:u64,
    #[serde(default)]
    pub shared_owner_segments_reused:u64,
    #[serde(default)]
    pub completed_symbolic_slot_checks:u64,
    #[serde(default)]
    pub completed_symbolic_slots_elided:u64,
    #[serde(default)]
    pub completed_scalar_slots_elided:u64,
    #[serde(default)]
    pub completed_scalar_slots_restored:u64,
    #[serde(default)]
    pub shared_owner_frames_restored:u64,
    #[serde(default)]
    pub shared_owner_inherited_frames:u64,
    #[serde(default)]
    pub shared_owner_extensions:u64,
    #[serde(default)]
    pub shared_owner_referenced_frames:u64,
    #[serde(default)]
    pub shared_owner_extension_frames:u64,
    #[serde(default)]
    pub shared_owner_merged_owners:u64,
    #[serde(default)]
    pub shared_owner_slot_entries_moved:u64,
    #[serde(default)]
    pub shared_owner_fact_entries_moved:u64,
    #[serde(default)]
    pub shared_owner_dead_slots_elided:u64,
    #[serde(default)]
    pub completed_dead_slots_elided:u64,
    #[serde(default)]
    pub completed_dead_frames_compacted:u64,
    #[serde(default)]
    pub completed_parent_candidates: u64,
    #[serde(default)]
    pub completed_parent_slot_checks: u64,
    #[serde(default)]
    pub completed_parent_detachments: u64,
    #[serde(default)]
    pub completed_parent_slots_delegated: u64,
    #[serde(default)]
    pub completed_parent_residual_slots: u64,
    #[serde(default)]
    pub completed_parent_residual_capacity_bytes: u64,
    pub native_table_reads: u64,
    pub native_table_writes: u64,
    pub native_free_join_calls: u64,
    #[serde(default)]
    pub delivery_events: u64,
    #[serde(default)]
    pub distinct_delivery_events: u64,
    #[serde(default)]
    pub union_requests: u64,
    #[serde(default)]
    pub repair_key_hash_changes: u64,
    #[serde(default)]
    pub repair_collisions: u64,
}

#[cfg(feature = "sparse-cells")]
#[path = "cell_arena.rs"]
pub mod arena;
#[path = "scoped_completion.rs"]
mod scoped_completion;
#[cfg(feature = "sparse-cells")]
#[path = "scalar_keys.rs"]
mod scalar_keys;
/// All lanes share the same Run barrier. The last three are timing controls.

#[cfg(feature = "sparse-cells")]
#[path = "writer_frames.rs"]
mod writer_frames;
#[cfg(feature = "sparse-cells")]
#[path = "rhs_ownership.rs"]
pub(crate) mod rhs_ownership;
pub struct Graph {
    #[cfg(feature = "sparse-cells")]
    pub(crate) sealed_generation: Option<u64>,
    #[cfg(feature = "sparse-cells")]
    pub(crate) sealed_input_cell: Option<u32>,
    #[cfg(feature = "sparse-cells")]
    sealed_reads: std::cell::Cell<u64>,
    #[cfg(feature = "sparse-cells")]
    visibility_tainted: Vec<bool>,
    #[cfg(feature = "sparse-cells")]
    active_origin: Option<usize>,
    #[cfg(feature = "sparse-cells")]
    active_rhs: Option<(u32, Cell)>,
    #[cfg(feature = "sparse-cells")]
    writer_dir: writer_frames::Directory,
    #[cfg(feature = "keeper-proof")]
    pub(crate) proof: crate::prefix_proof::Proof,
    #[cfg(feature = "rhs-work-audit")]
    pub(crate) rhs_births: crate::rhs_work::Births,
    units: unit_ports::Units,
    pub known_stats: crate::known_results::Stats,
    pub merge_programs_enabled: bool,
    scalar_merge: bool,
    merge_kinds: Vec<Option<String>>,
    equal_keeps_old: Vec<bool>,
    pub key_lookup_calls: std::cell::Cell<u64>,
    pub fact_decode_calls: std::cell::Cell<u64>,
    pub fact_decode_ports: std::cell::Cell<u64>,
    pub program: Program,

    #[cfg(not(feature = "sparse-cells"))]
    pub cells: rustc_hash::FxHashMap<u32, Cell>,
    #[cfg(feature = "sparse-cells")]
    pub cells: arena::Cells,
    pub functions: Vec<Function>,
    pub parents: Parents,
    pub epoch: u64,
    pub changed: bool,
    pub stats: Stats,
    pub maintenance: maintenance::Metrics,
    local_unions: Option<local_union_cells::Runtime>,
    ownership: Option<cell_ownership::Runtime>,
    stable_ports: Option<cell_ownership::ports::Runtime>,
    pub pending_unions: Vec<(u64, u64)>,
    union_digest: Option<union_digest::Matcher>,
    repair_ports: Option<repair_ports::Runtime>,
    #[cfg(feature = "spine-blocks")]
    repair_cells: Option<repair_cells::Runtime>,

    pub(crate) changes: crate::change_batch::ChangeBatch,
    pub anchors: Vec<(String, String, u64)>,
    pub next_cell: u32,
    pub query_versions: Vec<u64>,
    // Transient commit-boundary receipts, never part of a checkpoint.
    #[cfg(feature = "receipt-slots")]
    pub(crate) retired_port_slots: HashMap<Dependency, u32>,
    pub receipt_tracking: bool,
    pub(crate) port_birth_hints: bool,
    pub receipt_forwards: HashMap<Dependency, Dependency>,

    // A table's kind supplies the witness tag for every member.
    members: Vec<TableRows<u64>>,
    #[cfg(not(feature = "sparse-cells"))]
    intern: HashMap<u64, BTreeSet<FactRef>>,
    #[cfg(feature = "sparse-cells")]
    intern: HashMap<u64, crate::tiny_set::TinySet<FactRef>>,
    #[cfg(not(feature = "sparse-cells"))]
    function_keys: Vec<HashMap<Vec<Value>, usize>>,
    #[cfg(feature = "sparse-cells")]
    function_keys: Vec<scalar_keys::FunctionKeys>,
    uses: rustc_hash::FxHashMap<u64, UseSet>,
    #[cfg(not(feature = "sparse-cells"))]
    dependencies: HashMap<Dependency, BTreeSet<u64>>,
    dirty: BTreeSet<Dependency>,
    dirty_markers: BTreeSet<FactRef>,
    dirty_facts: Vec<BTreeSet<FactRef>>,
    deletion_epochs: Vec<u64>,
    parent_users: rustc_hash::FxHashMap<u32, usize>,
    garbage: BTreeSet<u32>,
}
#[path = "cell_prefix.rs"]
pub(crate) mod cell_prefix;
#[cfg(feature = "sparse-cells")]
#[path = "query_reads.rs"]
pub(crate) mod query_reads;
#[cfg(all(feature = "sparse-cells", feature = "storage-metrics"))]
#[path = "graph_storage.rs"]
mod storage;
#[cfg(all(feature = "sparse-cells",feature="storage-metrics"))]
#[path = "completed_parent.rs"]
mod completed_parent;
#[path = "unit_ports.rs"]
mod unit_ports;
fn hashkey(table: usize, key: &[Value]) -> u64 {
    let mut h = rustc_hash::FxHasher::default();
    table.hash(&mut h);
    key.hash(&mut h);
    h.finish()
}
impl Graph {
    /// Only the frame being executed may read its sealed inputs without
    /// canonicalizing them again. A real union invalidates that permission.
    #[cfg(feature = "sparse-cells")]
    fn trust_sealed_frame(&mut self, id: u32) {
        self.sealed_input_cell = (self.sealed_generation == Some(self.stats.unions)).then_some(id);
    }

    #[cfg(feature = "storage-metrics")]
    fn sealed_read_count(&self) -> u64 {
        #[cfg(feature = "sparse-cells")]
        { self.sealed_reads.get() }
        #[cfg(not(feature = "sparse-cells"))]
        { 0 }
    }

    #[cfg(feature = "receipt-slots")]
    pub(crate) fn current_port_slot(&self, w: Dependency) -> Option<u32> {
        match w {
            Dependency::Fact(f) => self
                .cells.fact_state(f)
                .map(|f| f.port_slot),
            Dependency::Function(i) => self.functions.get(i).map(|f| f.port_slot),
        }
    }
    #[cfg(feature = "receipt-slots")]
    pub(crate) fn previous_port_slot(&self, w: Dependency) -> u32 {
        let id = self.current_port_slot(w).unwrap_or(0);
        if id == 0 && !self.retired_port_slots.is_empty() {
            self.retired_port_slots.get(&w).copied().unwrap_or(0)
        } else {
            id
        }
    }
    #[cfg(feature = "receipt-slots")]
    pub(crate) fn set_port_slot(&mut self, w: Dependency, id: u32) {
        match w {
            Dependency::Fact(f) => {
                self.cells.fact_state_mut(f)
                    .unwrap()
                    .port_slot = id
            }
            Dependency::Function(i) => self.functions[i].port_slot = id,
        }
    }
    #[cfg(feature = "storage-metrics")]
    pub fn storage_sample(&self) -> J {
        let mut arity = [0usize; 5];
        for c in self.cells.values() {
            arity[c.facts.len().min(4)] += 1;
        }
        let mut buckets = [0usize; 4];
        for set in self.intern.values() {
            buckets[set.len().min(3)] += 1;
        }
        #[cfg(feature = "sparse-cells")]
        let writers = json!({"live":self.writer_dir.live,"peak":self.writer_dir.peak,"installed":self.writer_dir.installations,"promoted":self.writer_dir.promoted,"from_general_rhs":self.writer_dir.general});
        #[cfg(not(feature = "sparse-cells"))]
        let writers = J::Null;
        json!({"sealed_slot_reads": self.sealed_read_count(), "embedded_writers":writers,"full_cells":self.cells.len(),"cell_fact_arity_0_1_2_3_4plus":arity,"intern_sizes_0_1_2_3plus":buckets,"intern_headers":self.intern.len(),"forward_dependency_headers":self.forward_dependency_size().0,"reverse_dependency_headers":self.uses.len(),"dependency_edges":self.forward_dependency_size().1,"live_functions":self.functions.iter().filter(|f|f.live).count(),"function_slots":self.functions.len(),"cell_id_high_water":self.next_cell})
    }
    /// Follow only storage relocation and proved same-key coalescence in this
    /// commit. Equal result classes alone never establish a row receipt.
    /// A receipt's key was checked by its query/action. Keys only change by
    /// canonicalization; receipt forwarding preserves that same-key relation.
    /// Check liveness/visibility here without decoding the recipe again.
    pub fn receipt_visible(&self, w: Dependency, table: usize) -> bool {
        match w {
            Dependency::Fact(f) => {
                self.live_table(w) == Some(table)
                    && self
                        .cells.fact_state(f)
                        .is_some_and(|s| !s.hidden)
            }
            Dependency::Function(i) => self
                .functions
                .get(i)
                .is_some_and(|f| f.live && f.table == table),
        }
    }
    fn forward_receipt(&mut self,from:Dependency,to:Dependency) {
        #[cfg(all(feature="storage-metrics",feature="sparse-cells"))]
        crate::receipt_trace::forward(from,to,self.epoch);
        self.receipt_forwards.insert(from,to);
    }
    pub(crate) fn clear_receipt_forwards(&mut self) {
        #[cfg(all(feature="storage-metrics",feature="sparse-cells"))]
        { self.trace_forwarded_parents(); crate::receipt_trace::clear(self.epoch,self.receipt_forwards.len()); }
        self.receipt_forwards.clear();
    }
    pub fn resolve_receipt(&self, w: Dependency) -> Dependency { self.resolve_receipt_origin(w).0 }
    #[inline(always)]
    fn resolve_receipt_origin(&self, mut w: Dependency) -> (Dependency,bool) {
        let mut original=true;
        loop {
            if let Some(next) = self.receipt_forwards.get(&w) {
                original=false;
                w = *next;
            } else {
                return (w,original);
            }
        }
    }

    pub fn new(program: Program) -> Result<Self> {
        Self::new_mode(program, None)
    }
    pub fn new_with_union_digest(program: Program, hash_bits: u32) -> Result<Self> {
        let matcher = union_digest::Matcher::new(&program, hash_bits)?;
        Self::new_mode(program, Some(matcher))
    }
    pub fn new_with_congruence_cells(program: Program, hash_bits: u32) -> Result<Self> {
        let matcher = union_digest::Matcher::with_cells(&program, hash_bits)?;
        Self::new_mode(program, Some(matcher))
    }
    fn new_mode(program: Program, union_digest: Option<union_digest::Matcher>) -> Result<Self> {
        let n = program.tables.len();
        let initial = program.initial.clone();

        let merge_kinds = program
            .tables
            .iter()
            .enumerate()
            .map(|(t, _)| {
                program.artifact["merge_contracts"]["tables"][t]["kind"]
                    .as_str()
                    .map(str::to_owned)
            })
            .collect();
        let equal_keeps_old = program
            .tables
            .iter()
            .enumerate()
            .map(|(t, v)| {
                if program.artifact["merge_contracts"].is_null() {
                    v.merge["call"]["table"].is_string()
                } else {
                    program.artifact["merge_contracts"]["tables"][t]["equal_inputs"] == "return_old"
                }
            })
            .collect();
        #[cfg(feature = "sparse-cells")]
        let typed_keys = program
            .tables
            .iter()
            .map(scalar_keys::FunctionKeys::new)
            .collect();
        let mut g = Self {
            #[cfg(feature = "sparse-cells")]
            sealed_generation: None,
            #[cfg(feature = "sparse-cells")]
            sealed_input_cell: None,
            #[cfg(feature = "sparse-cells")]
            sealed_reads: Default::default(),
            #[cfg(feature = "sparse-cells")]
            visibility_tainted: vec![false; n],
            #[cfg(feature = "sparse-cells")]
            active_origin: None,
            #[cfg(feature = "sparse-cells")]
            active_rhs: None,
            #[cfg(feature = "sparse-cells")]
            writer_dir: Default::default(),
            #[cfg(feature = "rhs-work-audit")]
            rhs_births: Default::default(),
            #[cfg(feature = "keeper-proof")]
            proof: Default::default(),
            units: unit_ports::Units::new(&program),
            merge_kinds,
            equal_keeps_old,

            fact_decode_calls: std::cell::Cell::new(0),
            fact_decode_ports: std::cell::Cell::new(0),
            key_lookup_calls: std::cell::Cell::new(0),

            program,
            cells: Default::default(),
            functions: vec![],
            parents: Default::default(),
            epoch: 0,
            changed: false,
            stats: Stats::default(),
            maintenance: Default::default(),
            local_unions: None,
            ownership: None,
            stable_ports: None,

            known_stats: Default::default(),
            scalar_merge: cfg!(feature = "sparse-cells"),
            merge_programs_enabled: true,
            pending_unions: vec![],
            union_digest,
            repair_ports: None,
            #[cfg(feature = "spine-blocks")]
            repair_cells: None,

            changes: crate::change_batch::ChangeBatch::new(n),
            anchors: vec![],
            next_cell: 1,
            query_versions: vec![0; n],
            receipt_tracking: false,
            #[cfg(feature = "receipt-slots")]
            retired_port_slots: HashMap::default(),
            receipt_forwards: HashMap::default(),
            port_birth_hints: true,

            members: vec![TableRows::default(); n],
            intern: HashMap::default(),
            #[cfg(not(feature = "sparse-cells"))]
            function_keys: vec![Default::default(); n],
            #[cfg(feature = "sparse-cells")]
            function_keys: typed_keys,
            uses: Default::default(),
            #[cfg(not(feature = "sparse-cells"))]
            dependencies: Default::default(),
            dirty: BTreeSet::new(),
            dirty_markers: BTreeSet::new(),
            dirty_facts: vec![BTreeSet::new(); n],
            deletion_epochs: vec![0; n],
            parent_users: Default::default(),
            garbage: BTreeSet::new(),
        };
        let mut ids = BTreeMap::new();
        for r in &initial {
            let table = g
                .program
                .tables
                .iter()
                .position(|t| r["table"] == t.name)
                .ok_or("unknown initial operator")?;
            let vals = array(&r["values"])?
                .iter()
                .map(|v| Self::import(v, &mut ids))
                .collect::<Result<Vec<_>>>()?;
            if vals.len() != g.program.tables[table].schema.len() {
                return Err("initial arity".into());
            }
            let key = vals[..vals.len() - 1].to_vec();
            let val = vals.last().unwrap().clone();
            if g.program.tables[table].virtual_fact {
                let template = g.program.table_templates[table];
                let cell = g.frame(template, (0..vals.len()).zip(vals).collect())?;
                g.activate(
                    FactRef { cell, op: 0 },
                    table,
                    &key,
                    val,
                    r["subsumed"].as_bool().unwrap_or(false),
                )?;
            } else {
                g.set_function(table, key, val)?;
            }
        }
        g.anchors = ids
            .into_iter()
            .map(|((sort, old), id)| (sort, old, id))
            .collect();
        g.repair()?;
        g.changed = false;
        Ok(g)
    }
    fn import(j: &J, ids: &mut BTreeMap<(String, String), u64>) -> Result<Value> {
        if j.get("key").is_some() {
            return Ok(Value::Key(eggfuse_structural_key::Key::from_wire(
                serde_json::from_value(j["key"].clone()).map_err(|e| e.to_string())?,
            )?));
        }
        if let Some(eq) = j["eq"].as_str() {
            let next = ids.len() as u64 + 1;
            if next >= 1u64 << 32 {
                return Err("initial identity capacity".into());
            }
            return Ok(Value::Eq(
                *ids.entry((string(&j["sort"])?.into(), eq.into()))
                    .or_insert(next),
            ));
        }
        if let Some(xs) = j["elements"].as_array() {
            let mut xs = xs
                .iter()
                .map(|x| Self::import(x, ids))
                .collect::<Result<Vec<_>>>()?;
            xs.sort();
            xs.dedup();
            return Ok(Value::Set(xs.into()));
        }
        Ok(match string(&j["sort"])? {
            "String" => Value::Text(string(&j["value"])?.to_owned().into()),
            "f64" => Value::Float(j["value"].as_i64().ok_or("f64 bits")?),
            _ => Value::Int(
                j["value"]
                    .as_i64()
                    .or_else(|| j["value"].as_str().and_then(|s| s.parse().ok()))
                    .ok_or("initial scalar")?,
            ),
        })
    }
    fn reserve_cell_id(&mut self) -> Result<u32> {
        let id = self.next_cell;
        self.next_cell = id.checked_add(1).ok_or("Cell identity exhausted")?;
        Ok(id)
    }
    #[cfg(feature = "cell-absorption")]
    pub(crate) fn reserve_absorbed_cells(&mut self, count: usize) -> Result<()> {
        // Preserve later constructor IDs across this experiment. These are
        // unused identity positions, not committed operations or live Cells.
        let count = u32::try_from(count).map_err(|_| "Cell identity exhausted")?;
        self.next_cell = self.next_cell.checked_add(count).ok_or("Cell identity exhausted")?;
        Ok(())
    }
    #[cfg(feature = "cell-absorption")]
    pub(crate) fn absorption_value(&self, table: usize, key: &Value) -> Option<(usize, i64)> {
        let index = self.function_index(table, std::slice::from_ref(key))?;
        self.absorption_rejection(table, index).map(|value| (index, value))
    }
    #[cfg(feature = "cell-absorption")]
    pub(crate) fn absorption_rejection(&self, table: usize, index: usize) -> Option<i64> {
        let f = self.functions.get(index)?;
        match f.value() { Value::Int(v) if f.live && f.table == table => Some(*v), _ => None }
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn reserve_completed_cell(&mut self) -> Result<u32> {
        // Source identity order remains identical to ordinary closed RHS
        // execution, but no physical frame or computed value slots are made.
        let id=self.reserve_cell_id()?;
        self.stats.rhs_frames_avoided+=1;
        Ok(id)
    }
    fn new_cell(
        &self,
        template: usize,
        mut values: crate::slots::Slots,
        parent: Option<FactRef>,
    ) -> Cell {
        let columns = &self.program.templates[template].parent_columns;
        let parent = parent.filter(|_| !columns.is_empty());
        // The owned control retains the very same parents, with a copy of
        // each projected parameter available in the existing owned slot map.
        if parent.is_some() {
            for slot in columns.keys() {
                values.remove(slot);
            }
        }

        Cell {
            symbolic_slots: false,
            template,
            values:values.into(),
            parent,

            completed_prefix: 0,
            started_epoch: self.epoch,
            completed: false,

            facts: Default::default(),
            recipe_depth: 0,
        }
    }
    fn store_cell(&mut self, id: u32, cell: Cell) {
        if let Some(parent) = cell.parent {
            self.retain_reference(parent);
        }
        self.cells.insert(id, cell);
        self.stats.cells_created += 1;
    }
    pub fn frame(&mut self, template: usize, values: BTreeMap<usize, Value>) -> Result<u32> {
        self.linked_frame(template, values, None)
    }
    pub fn linked_frame(
        &mut self,
        template: usize,
        values: BTreeMap<usize, Value>,
        parent: Option<FactRef>,
    ) -> Result<u32> {
        self.linked_slots(template, values.into_iter().collect(), parent)
    }
    pub(crate) fn linked_slots(
        &mut self,
        template: usize,
        values: crate::slots::Slots,
        parent: Option<FactRef>,
    ) -> Result<u32> {
        let id = self.reserve_cell_id()?;
        let frame = self.new_cell(template, values, parent);
        self.store_cell(id, frame);
        Ok(id)
    }
    pub(crate) fn apply_write(
        &mut self,
        rule: usize,
        values: crate::slots::Slots,
        parent: Option<FactRef>,
        write: &crate::row_kernel::Write,
        keep_key: bool,
        #[cfg(feature="sparse-cells")] prepared:usize,
    ) -> Result<(u32, usize, Option<Vec<Value>>, bool)> {
        let template = self.program.rules[rule].template;
        let id = self.reserve_cell_id()?;
        #[cfg(feature = "sparse-cells")]
        self.trust_sealed_frame(id);
        self.stats.single_writes += 1;
        let before = self.stats.function_updates;
        #[cfg(feature="sparse-cells")]
        if parent.is_none() && let Some(ports)=&write.ports {
            let (key,value,dst)=ports.project(&values,&self.parents,write.prefix.last().is_some_and(|&op|op<prepared))?;
            let i=self.set_function_canonical(write.table,std::slice::from_ref(&key),Value::Int(value))?;
            let changed=self.stats.function_updates!=before;
            if changed{
                let mut frame=self.new_cell(template,values,None);
                if let Some(dst)=dst{frame.values.insert(dst,Value::Int(value));}
                self.keep_writer(i,id,write.op,frame);
            }else{self.stats.rhs_frames_avoided+=1;self.stats.transient_writes+=1;}
            return Ok((id, i, keep_key.then(|| vec![key]), changed));
        }
        let mut frame = self.new_cell(template, values, parent);
        let ops = self.program.templates[template].ops.clone();
        for &op in &write.prefix {
            #[cfg(feature="sparse-cells")]
            if op<prepared {continue;}
            #[cfg(feature="sparse-cells")]
            if self.program.executions[rule].prepared_at(op,
                &self.program.templates[template], &frame.values) {
                self.stats.prepared_rhs_later_operations += 1;
                continue;
            }
            let Op::Let(dst, call, args) = &ops[op] else { unreachable!("validated scalar Cell prefix") };
            crate::cell::evaluate_call(self, &mut crate::cell::LocalCall { cell: id, frame: &mut frame },
                op, *dst, call, args)?;
        }
        let key = write
            .key
            .iter()
            .map(|a| self.argument_in(id, &frame, a))
            .collect::<Result<Vec<_>>>()?;
        let value = self.argument_in(id, &frame, &write.value)?;
        let i=self.set_function_canonical(write.table,&key,value)?;
        let changed=self.stats.function_updates!=before;
        if changed {
            self.keep_writer(i,id,write.op,frame);
        } else {
            self.stats.rhs_frames_avoided += 1;
            self.stats.transient_writes += 1;
        }
        Ok((id, i, keep_key.then_some(key), changed))
    }
    fn keep_writer(&mut self,i:usize,id:u32,op:usize,mut frame:Cell){
        frame.completed=true;
        frame.completed_prefix=op+1;
        #[cfg(feature="sparse-cells")]
        if i<u32::MAX as usize {self.inline_writer(i,id,op,frame);return;}
        self.store_cell(id,frame);
        self.function_origin(i,Some(FactRef{cell:id,op:op as u32}));
    }
    pub fn argument(&self, cell: u32, a: &Arg) -> Result<Value> {
        match a {
            Arg::Literal(v) => Ok(canon(v, &self.parents)),
            Arg::Slot(i) => self.slot(cell, *i),
        }
    }
    pub fn slot(&self, cell: u32, i: usize) -> Result<Value> {
        if let Some(c) = self.rhs_frame(cell) {
            return self.slot_in(cell, c, i);
        }
        #[cfg(feature = "sparse-cells")]
        if let Some(w) = self.writer(cell) {
            return self.slot_fields(cell, w.template, w.parent, &w.values, i);
        }
        #[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
        if let Some(meta)=self.cells.completed_meta(cell) {
            return self.slot_fields(cell,meta.template,None,&self.cells.completed_slots(cell).unwrap(),i);
        }
        Err("expired Cell reference".into())
    }
    #[inline]
    pub(crate) fn rhs_frame(&self, id: u32) -> Option<&Cell> {
        #[cfg(feature = "sparse-cells")]
        if let Some((current, c)) = &self.active_rhs
            && *current == id
        {
            return Some(c);
        }
        self.cells.get(&id)
    }
    #[inline]
    pub(crate) fn rhs_frame_mut(&mut self, id: u32) -> Option<&mut Cell> {
        #[cfg(feature = "sparse-cells")]
        if let Some((current, c)) = &mut self.active_rhs
            && *current == id
        {
            return Some(c);
        }
        self.cells.get_mut(&id)
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn execution_parts(&mut self, rule: usize, cell: u32)
        -> (&crate::cell::execution::Plan, &crate::program::Template, &mut Cell) {
        let template = &self.program.templates[self.program.rules[rule].template];
        let frame = match &mut self.active_rhs {
            Some((id, frame)) if *id == cell => frame,
            _ => self.cells.get_mut(&cell).expect("owned executing Cell"),
        };
        debug_assert_eq!(frame.template, self.program.rules[rule].template);
        (&self.program.executions[rule], template, frame)
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn begin_transient(
        &mut self,
        template: usize,
        values: crate::slots::Slots,
        parent: Option<FactRef>,
    ) -> Result<u32> {
        debug_assert!(self.active_rhs.is_none());
        #[cfg(feature = "sparse-cells")]
        {
            self.active_origin = None;
        }
        let id = self.reserve_cell_id()?;
        #[cfg(feature = "sparse-cells")]
        self.trust_sealed_frame(id);
        self.active_rhs = Some((id, self.new_cell(template, values, parent)));
        Ok(id)
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn promote_active(&mut self) {
        if let Some((id, c)) = self.active_rhs.take() {
            self.store_cell(id, c);
        }
    }
    #[cfg(feature = "sparse-cells")]
    fn promote_owner(&mut self, id: u32) {
        if self
            .active_rhs
            .as_ref()
            .is_some_and(|(active, _)| *active == id)
        {
            self.promote_active();
        }
    }
    pub(crate) fn argument_in(&self, cell: u32, c: &Cell, a: &Arg) -> Result<Value> {
        match a {
            Arg::Literal(v) => Ok(canon(v, &self.parents)),
            Arg::Slot(i) => self.slot_fields(cell, c.template, c.parent, &c.values, *i),
        }
    }
    fn slot_in(&self, cell: u32, c: &Cell, i: usize) -> Result<Value> {
        self.slot_fields(cell, c.template, c.parent, &c.values, i)
    }
    fn slot_fields(
        &self,
        cell: u32,
        template: usize,
        parent: Option<FactRef>,
        values: &impl crate::slots::ReadSlots,
        i: usize,
    ) -> Result<Value> {
        if let Some(v) = values.get(&i) {
            #[cfg(feature = "sparse-cells")]
            if self.sealed_input_cell == Some(cell) {
                self.sealed_reads.set(self.sealed_reads.get()+1);
                return Ok(v.clone());
            }
            return Ok(canon(v, &self.parents));
        }
        if self.cells.cell_metadata(cell).is_some_and(|c| c.symbolic_slots) {
            #[cfg(all(feature="storage-metrics",feature="sparse-cells"))]
            if let Some(value)=self.completed_scalar_slot(cell,template,i,None) {return Ok(value);}
            if let Some(value) = self.inherited_cell_slot(cell, template, i) {
                return Ok(value);
            }
        }
        let arg = |a: &Arg| match a {
            Arg::Literal(v) => Ok(canon(v, &self.parents)),
            Arg::Slot(s) => self.slot_fields(cell, template, parent, values, *s),
        };
        if let Some(a) = self
            .program
            .known_results
            .static_slots
            .get(template)
            .and_then(|s| s.get(i))
            .and_then(Option::as_ref)
        {
            return arg(a);
        }
        let t = &self.program.templates[template];
        if let (Some(p), Some(&col)) = (parent, t.parent_columns.get(&i)) {
            return self.fact_column(p, col);
        }
        let op = &t.ops[*t.defs.get(&i).ok_or("unready slot")?];
        match op {
            Op::Copy(_, a) => arg(a),
            Op::Let(_, Call::Table(t), _) if self.program.tables[*t].virtual_fact => {
                Ok(if self.program.tables[*t].constructor {
                    Value::Eq(root(&self.parents, ((cell as u64) << 32) | (i as u64 + 1)))
                } else {
                    Value::Int(0)
                })
            }
            _ => Err("unready computed/function slot".into()),
        }
    }
    fn fact_column(&self, f: FactRef, col: usize) -> Result<Value> {
        if let Some(stored) = self.stable_node(f) {
            return self.read_stable_column(stored, col);
        }
        // Recipe parameters are immutable even after this fact is hidden/deleted.
        // Derived Cells can keep their binding without copying the parent's fields.
        let template = self.cells.cell_metadata(f.cell).map(|c| c.template);
        #[cfg(feature = "sparse-cells")]
        let template = template.or_else(|| self.writer(f.cell).map(|w| w.template));
        match self.program.templates[template.ok_or("expired parent Cell")?]
            .ops
            .get(f.op as usize)
            .ok_or("invalid retained fact position")?
        {
            Op::Let(dst, Call::Table(_), args) => {
                if col == args.len() {
                    self.slot(f.cell, *dst)
                } else {
                    self.argument(f.cell, args.get(col).ok_or("parent column")?)
                }
            }
            Op::Set(_, args, v) => self.argument(
                f.cell,
                if col == args.len() {
                    v
                } else {
                    args.get(col).ok_or("parent column")?
                },
            ),
            _ => Err("invalid parent fact".into()),
        }
    }
    /// Stored, local and completing Cells read their one owned slot map.
    pub(crate) fn frame_arguments<C: FromIterator<Value>>(&self, cell: u32, frame: &Cell,
        args: &[Arg]) -> Result<C> {
        args.iter().map(|arg| self.argument_in(cell, frame, arg)).collect()
    }
    fn collect_arguments<C: FromIterator<Value>>(&self, cell: u32, args: &[Arg]) -> Result<C> {
        if let Some(frame) = self.rhs_frame(cell) {
            self.frame_arguments(cell, frame, args)
        } else {
            args.iter().map(|arg| self.argument(cell, arg)).collect()
        }
    }
    pub fn arguments(&self, cell: u32, args: &[Arg]) -> Result<Vec<Value>> {
        self.collect_arguments(cell, args)
    }
    pub(crate) fn inline_arguments(&self, cell: u32, args: &[Arg]) -> Result<smallvec::SmallVec<[Value; 4]>> {
        self.collect_arguments(cell, args)
    }
    #[inline]
    pub fn fact(&self, f: FactRef) -> Result<Option<Row>> {
        let Some(s) = self.cells.fact_state(f) else {
            return Ok(None);
        };
        if let Some(stored) = self.stable_node(f) {
            return self.read_stable_fact(f, s, stored).map(Some);
        }
        if let Some((table, values)) = &s.decoded {
            return Ok(Some(Row {
                table: *table,
                values: values.clone(),
                hidden: s.hidden,
                epoch: s.epoch,
                witness: Dependency::Fact(f),
            }));
        }

        // Stable fields and cached rows need only the fact's logical identity.
        // The ordinary recipe fallback still requires the original frame.
        let c = self.cells.cell_metadata(f.cell).ok_or("live fact lacks recipe owner")?;
        self.decode_fact(f, c.template, s).map(Some)
    }

    #[inline(never)]
    fn decode_fact(&self, f: FactRef, template:usize, s: fact_states::FactRead<'_>) -> Result<Row> {
        self.fact_decode_calls.set(self.fact_decode_calls.get() + 1);
        let op = self.program.templates[template]
            .ops
            .get(f.op as usize)
            .ok_or("invalid live fact position")?;
        let (table, args, result) = match op {
            Op::Let(dst, Call::Table(t), args) => (*t, args, Arg::Slot(*dst)),
            Op::Set(t, args, value) => (*t, args, value.clone()),
            _ => return Err("invalid fact recipe position".into()),
        };
        self.fact_decode_ports.set(self.fact_decode_ports.get() + args.len() as u64 + 1);
        let mut values = Vec::with_capacity(args.len() + 1);
        for arg in args {
            values.push(self.argument(f.cell, arg)?);
        }
        values.push(self.argument(f.cell, &result)?);
        Ok(Row {
            table,
            values: row_fields(values),
            hidden: s.hidden,
            epoch: s.epoch,
            witness: Dependency::Fact(f),
        })
    }
    fn shared_fields(key: &[Value], v: &Value) -> RowFields {
        #[cfg(feature = "sparse-cells")]
        {
            key.iter()
                .cloned()
                .chain(std::iter::once(v.clone()))
                .collect()
        }
        #[cfg(not(feature = "sparse-cells"))]
        {
            let mut fields = Vec::with_capacity(key.len() + 1);
            fields.extend_from_slice(key);
            fields.push(v.clone());
            std::rc::Rc::new(fields)
        }
    }
    fn indexed_function(&self, t: usize, key: &[Value]) -> Option<usize> {
        #[cfg(feature = "sparse-cells")]
        { self.function_keys[t].get(key, &self.functions).copied() }
        #[cfg(not(feature = "sparse-cells"))]
        { self.function_keys[t].get(key).copied() }
    }
    fn function_index(&self, t: usize, key: &[Value]) -> Option<usize> {
        self.indexed_function(t, key).or_else(|| self.units.lookup(t, key))
    }
    #[cfg(feature = "view-consumers")]
    pub(crate) fn published_view(&self, i: usize) -> Option<crate::view_plan::Tuple> {
        let f = self.functions.get(i).filter(|f| f.live)?;
        if f.canonical {
            let fields = &f.fields;
            return Some(crate::view_plan::Tuple {
                witness: Dependency::Function(i),
                epoch: f.epoch,
                fields: fields.clone(),
                columns: None,
            });
        }
        self.units
            .payload(i, f.epoch, &self.parents)
            .or_else(|| self.function(i).map(|r| crate::view_plan::Tuple::flat(&r)))
    }
    #[cfg(feature = "view-storage")]
    pub(crate) fn has_view_plan(&self, t: usize) -> bool {
        self.units.owned[t]
    }
    pub(crate) fn unit_stats(&self) -> serde_json::Value {
        self.units.report()
    }
    #[inline]
    pub fn function(&self, i: usize) -> Option<Row> {
        let f = self.functions.get(i)?;
        if !f.live {
            return None;
        }
        let values = if f.canonical { f.fields.clone() } else { self.decode_function(i, f) };
        Some(Row {
            table: f.table,
            values,
            hidden: false,
            epoch: f.epoch,
            witness: Dependency::Function(i),
        })
    }
    #[inline(never)]
    fn decode_function(&self, i: usize, f: &Function) -> RowFields {
        if f.key().is_empty()
            && self.units.counts[f.table] > 0
            && let Some(values) = self.units.values(i, &self.parents, f.value())
        {
            return values;
        }
        let mut values = Vec::with_capacity(f.key().len() + 1);
        values.extend(f.key().iter().map(|v| canon(v, &self.parents)));
        values.push(canon(f.value(), &self.parents));
        row_fields(values)
    }
    #[inline]
    pub fn row(&self, w: Dependency) -> Result<Option<Row>> {
        match w {
            Dependency::Fact(f) => self.fact(f),
            Dependency::Function(i) => Ok(self.function(i)),
        }
    }
    pub(crate) fn visible_epoch(&self, w: Dependency) -> Option<u64> {
        match w {
            Dependency::Fact(f) => self
                .cells.fact_state(f)
                .filter(|s| !s.hidden)
                .map(|s| s.epoch),
            Dependency::Function(i) => self.functions.get(i).filter(|f| f.live).map(|f| f.epoch),
        }
    }
    /// Delivery only needs liveness and the table, not the decoded binding.
    pub fn live_table(&self, w: Dependency) -> Option<usize> {
        match w {
            Dependency::Function(i) => self.functions.get(i).filter(|f| f.live).map(|f| f.table),
            Dependency::Fact(f) => {
                let c = self.cells.cell_metadata(f.cell)?;
                self.cells.fact_state(f)?;

                match self.program.templates[c.template].ops.get(f.op as usize)? {
                    Op::Let(_, Call::Table(t), _) | Op::Set(t, _, _) => Some(*t),
                    _ => None,
                }
            }
        }
    }
    pub fn origin(&self, w: Dependency) -> Option<FactRef> {
        match w {
            Dependency::Fact(f) => Some(f),
            Dependency::Function(i) => self
                .functions
                .get(i)
                .filter(|f| f.live)
                .and_then(|f| f.origin),
        }
    }
    fn function_origin(&mut self, index: usize, origin: Option<FactRef>) {
        if self.functions[index].origin == origin {
            return;
        }
        #[cfg(feature = "sparse-cells")]
        {
            self.detach_origin(index);
        }
        #[cfg(not(feature = "sparse-cells"))]
        if let Some(old) = self.functions[index].origin.take() {
            *self
                .parent_users
                .get_mut(&old.cell)
                .expect("function producer reference") -= 1;
            self.garbage.insert(old.cell);
        }
        if let Some(new) = origin {
            *self.parent_users.entry(new.cell).or_default() += 1;
        }
        self.functions[index].origin = origin;
    }
    pub(crate) fn dependency_table(&self, w: Dependency) -> Option<usize> {
        match w {
            Dependency::Function(i) => self.functions.get(i).map(|f| f.table),
            Dependency::Fact(f) => {
                let c = self.cells.cell_metadata(f.cell)?;

                match self.program.templates[c.template].ops.get(f.op as usize)? {
                    Op::Let(_, Call::Table(t), _) | Op::Set(t, _, _) => Some(*t),
                    _ => None,
                }
            }
        }
    }
    pub fn witnesses(&self, table: usize) -> Vec<Dependency> {
        let ids = self.members[table].iter().copied();
        if self.program.tables[table].virtual_fact {
            ids.map(|id| Dependency::Fact(FactRef::from_ordered_id(id))).collect()
        } else {
            ids.map(|id| Dependency::Function(id as usize)).collect()
        }
    }
    pub fn witness_count(&self, table: usize) -> usize {
        self.members[table].len()
    }
    fn bound_uses(&self, bound: &[Option<Value>]) -> Option<&UseSet> {
        #[cfg(feature = "sparse-cells")]
        static EMPTY: UseSet = UseSet::Empty;
        #[cfg(not(feature = "sparse-cells"))]
        static EMPTY: UseSet = UseSet::new();
        bound
            .iter()
            .filter_map(|v| match v {
                Some(Value::Eq(id)) => {
                    Some(self.uses.get(&root(&self.parents, *id)).unwrap_or(&EMPTY))
                }
                _ => None,
            })
            .min_by_key(|uses| uses.len())
    }
    pub fn candidate_count(&self, table: usize, bound: &[Option<Value>]) -> usize {
        let all = self.witness_count(table);
        if self.ownership.as_ref().is_some_and(|m|m.tables[table]>0) {return self.owned_candidate_count(table,bound);}
        if self.local_unions.as_ref().is_some_and(|m|m.untracked_tables[table] > 0) { return all; }
        self.bound_uses(bound)
            .map_or(all, |uses| all.min(uses.len()))
    }
    pub fn candidates(&self, table: usize, bound: &[Option<Value>]) -> Vec<Dependency> {
        if self.ownership.as_ref().is_some_and(|m|m.tables[table]>0) {
            return self.owned_candidates(table,bound);
        }
        if let Some(m)=&self.local_unions && m.untracked_tables[table] > 0 {
            m.fallback_queries.set(m.fallback_queries.get()+1);
            let rows=self.witnesses(table);
            m.fallback_rows.set(m.fallback_rows.get()+rows.len() as u64);
            return rows;
        }
        if let Some(uses) = self.bound_uses(bound) {
            if uses.len() < self.witness_count(table) {
                let rows: Vec<_> = uses
                    .iter()
                    .copied()
                    .filter(|w| match w {
                        Dependency::Fact(f) => {
                            self.cells.cell_metadata(f.cell).is_some_and(|c| {
                                match &self.program.templates[c.template].ops[f.op as usize] {
                                    Op::Let(_, Call::Table(t), _) | Op::Set(t, _, _) => *t == table,
                                    _ => false,
                                }
                            })
                        }
                        Dependency::Function(i) => {
                            self.functions[*i].live && self.functions[*i].table == table
                        }
                    })
                    .collect();
                #[cfg(feature = "sparse-cells")]
                let rows = {
                    let mut sorted = rows;
                    sorted.sort_unstable();
                    sorted
                };
                return rows;
            }
        }
        self.witnesses(table)
    }
    pub fn lookup(&self, table: usize, key: &[Value]) -> Result<Option<Row>> {
        let key = key
            .iter()
            .map(|v| canon(v, &self.parents))
            .collect::<Vec<_>>();
        self.lookup_canonical(table, &key)
    }
    pub(crate) fn lookup_canonical(&self, table: usize, key: &[Value]) -> Result<Option<Row>> {
        #[cfg(feature = "family-overlap")]
        let clock = crate::family_overlap::clock();
        let result = self.lookup_canonical_inner(table, key);
        #[cfg(feature = "rhs-work-audit")]
        if let Ok(Some(r)) = &result {
            self.rhs_births.read(r.witness);
        }
        #[cfg(feature = "family-overlap")]
        crate::family_overlap::physical(table, 0, clock, || {
            key.iter().cloned().enumerate().collect()
        });
        result
    }
    pub(crate) fn lookup_point(&mut self, table: usize, key: &[Value]) -> Result<Option<Point>> {
        // Research observers keep their ordinary lookup instrumentation. The
        // general constructor path also retains exact candidates and hidden-row
        // selection; only its receiving cache projects the result.
        #[cfg(all(feature = "sparse-cells", not(any(feature = "family-overlap", feature = "rhs-work-audit"))))]
        if !self.program.tables[table].virtual_fact && !self.port_keys_enabled(table) {
            self.key_lookup_calls.set(self.key_lookup_calls.get() + 1);
            let index = if key.is_empty() && self.program.tables[table].schema.len() == 1
                && self.members[table].len() <= 1 {
                self.members[table].iter().next().map(|&word| word as usize)
            } else { self.function_index(table, key) };
            let point = index.and_then(|i| {
                let f = self.functions.get(i).filter(|f| f.live)?;
                // Match function() exactly even at a scoped completion boundary:
                // a retained decoded row is authoritative until invalidated.
                let value = if f.canonical { f.value().clone() } else { canon(f.value(), &self.parents) };
                Some(Point { value, hidden: false, epoch: f.epoch, witness: Dependency::Function(i) })
            });
            self.stats.function_point_reads += u64::from(point.is_some());
            return Ok(point);
        }
        Ok(self.lookup_canonical(table, key)?.as_ref().map(Point::from))
    }
    #[inline]
    fn lookup_canonical_inner(&self, table: usize, key: &[Value]) -> Result<Option<Row>> {
        self.key_lookup_calls.set(self.key_lookup_calls.get() + 1);
        if self.port_keys_enabled(table) {
            return self.lookup_port_key(table, key, None);
        }
        if key.is_empty() && self.program.tables[table].schema.len() == 1 {
            let members = &self.members[table];
            if members.len() <= 1 {
                let Some(&word) = members.iter().next() else { return Ok(None); };
                return if self.program.tables[table].virtual_fact {
                    self.fact(FactRef::from_ordered_id(word))
                } else { Ok(self.function(word as usize)) };
            }
        }
        if !self.program.tables[table].virtual_fact {
            return Ok(self
                .function_index(table, key)
                .and_then(|i| self.function(i)));
        }
        let h = self.constructor_hash(table, key);
        if self.dirty_facts[table].is_empty() {
            // Matching observes a repaired snapshot. Avoid allocating/copying
            // a set on every keyed read; retain the original FactRef order.
            for &f in self.intern.get(&h).into_iter().flatten() {
                if let Some(r) = self.fact(f)? {
                    if r.table == table && r.values[..key.len()] == *key {
                        return Ok(Some(r));
                    }
                }
            }
            return Ok(None);
        }
        #[cfg(not(feature = "sparse-cells"))]
        let mut refs = self.intern.get(&h).cloned().unwrap_or_default();
        #[cfg(feature = "sparse-cells")]
        let mut refs: BTreeSet<_> = self.intern.get(&h).into_iter().flatten().copied().collect();
        // A merge callback may request a constructor whose old key is dirty. Include
        // only affected references until repair catches up, not all graph rows.
        refs.extend(self.dirty_facts[table].iter().copied());
        for f in refs {
            if let Some(r) = self.fact(f)? {
                if r.table == table && r.values[..key.len()] == *key {
                    return Ok(Some(r));
                }
            }
        }
        Ok(None)
    }
    #[cfg(not(feature = "sparse-cells"))]
    fn refs(v: &Value, out: &mut BTreeSet<u64>, visits: &mut u64) {
        *visits += 1;
        match v {
            Value::Eq(i) => {
                out.insert(*i);
            }
            Value::Set(xs) => {
                for x in xs.iter() {
                    Self::refs(x, out, visits)
                }
            }
            _ => {}
        }
    }
    fn forward_dependency_size(&self) -> (usize, usize) {
        #[cfg(feature = "sparse-cells")]
        { (0, 0) }
        #[cfg(not(feature = "sparse-cells"))]
        { (self.dependencies.len(), self.dependencies.values().map(|v| v.len()).sum()) }
    }
    /// Rows already own the Eq operands. Derive the old/new footprint at an
    /// explicit lifecycle boundary, rather than storing another binding set.
    fn subscribe_rows(&mut self, table: usize, d: Dependency, old: &[Value], new: &[Value]) {
        self.query_versions[table] += 1;
        self.replace_row_edges(d, old, new);
    }
    fn subscribe_function(&mut self, table: usize, index: usize, old: &[Value], new: &[Value]) {
        self.subscribe_rows(table, Dependency::Function(index), old, new);
    }
    fn replace_row_edges(&mut self, d: Dependency, old: &[Value], new: &[Value]) {
        #[cfg(not(feature = "sparse-cells"))]
        { let _ = old; self.subscribe_edges(d, new); }
        #[cfg(feature = "sparse-cells")]
        {
            self.maintenance.subscription_calls += 1;
            // Ordinary fact/function repair only canonicalizes an immutable
            // row. union() has already moved all of its reverse incidences.
            if std::ptr::eq(old, new) {
                self.maintenance.subscription_rows_reused += 1;
                return;
            }
            let old = self.subscription_refs(old);
            let new = self.subscription_refs(new);
            for id in &old {
                if !new.contains(id) && let Some(bucket) = self.uses.get_mut(id) {
                    maintenance::remove(bucket, &mut self.maintenance, d);
                    if bucket.is_empty() { self.uses.remove(id); }
                }
            }
            for id in new {
                if !old.contains(&id) { maintenance::insert(&mut self.uses, &mut self.maintenance, id, d); }
            }
        }
    }
    #[cfg(not(feature = "sparse-cells"))]
    fn subscribe_edges(&mut self, d: Dependency, values: &[Value]) {
        self.maintenance.subscription_calls += 1;
        let mut refs = BTreeSet::new();
        for v in values {
            Self::refs(v, &mut refs, &mut self.maintenance.subscription_value_visits);
        }
        if refs.iter().any(|v| self.parents.contains_key(v)) {
            refs = refs.into_iter().map(|id| root(&self.parents, id)).collect();
        }
        if self.dependencies.get(&d) == Some(&refs) {
            return;
        }
        let old = self.dependencies.remove(&d).unwrap_or_default();
        for id in old {
            let id = root(&self.parents, id);
            if !refs.contains(&id)
                && let Some(uses) = self.uses.get_mut(&id)
            {
                maintenance::remove(uses, &mut self.maintenance, d);
            }
        }
        for &id in &refs {
            maintenance::insert(&mut self.uses, &mut self.maintenance, id, d);
        }
        self.dependencies.insert(d, refs);
    }
    #[cfg(feature = "sparse-cells")]
    fn subscription_refs(&mut self, values: &[Value]) -> smallvec::SmallVec<[u64; 3]> {
        type Refs = smallvec::SmallVec<[u64; 3]>;
        fn collect(v: &Value, p: &Parents, out: &mut Refs, visits: &mut u64) {
            *visits += 1;
            match v {
                Value::Eq(i) => out.push(root(p, *i)),
                Value::Set(xs) => {
                    for x in xs.iter() {
                        collect(x, p, out, visits);
                    }
                }
                _ => (),
            }
        }
        let mut refs = Refs::new();
        for v in values {
            collect(v, &self.parents, &mut refs, &mut self.maintenance.subscription_value_visits);
        }
        refs.sort_unstable();
        refs.dedup();
        refs
    }
    fn activate(
        &mut self,
        f: FactRef,
        t: usize,
        key: &[Value],
        v: Value,
        hidden: bool,
    ) -> Result<()> {
        #[cfg(feature = "keeper-proof")]
        if let Some(pair) = self.proof.expects(f) {
            let old = self.fact(pair.keeper)?.ok_or("keeper missing at birth")?;
            if old.table != t || old.hidden {
                return Err("keeper table or visibility differs".into());
            }
            self.proof.at_birth(
                pair,
                self.epoch,
                key,
                &old.values[..old.values.len() - 1],
                &self.parents,
                &self.pending_unions,
            )?;
        }
        #[cfg(feature = "sparse-cells")]
        if hidden {
            self.visibility_tainted[t] = true;
        }
        // In port-key mode this is an immutable birth hint, not a promise
        // that the hash follows future canonical representatives.
        let h = self.constructor_hash(t, key);
        let vs = Self::shared_fields(key, &v);
        self.activate_fields(f,t,vs,h,hidden)
    }
    /// Adopt the actual row allocation. Local Cell construction has already
    /// computed its canonical fields/hash; source registration remains ordered.
    fn activate_fields(&mut self, f:FactRef, t:usize, vs:RowFields, h:u64, hidden:bool) -> Result<()> {
        #[cfg(feature="slot-transfer-audit")]
        if !self.program.tables[t].constructor {
            let (value,key)=vs.split_last().ok_or("membership result")?;
            crate::transfer_audit::logical_write(self.epoch,t,key,None,value)?;
        }
        let port_key = self.port_keys_enabled(t);
        #[cfg(feature = "sparse-cells")]
        self.promote_owner(f.cell);
        let local_union_owned = self.defer_local_birth(f, t);
        let owned = self.owns_birth(f);
        assert!(!port_key || owned, "port-key constructor lacks shared-template coverage");
        self.cells.insert_fact_state(
            f,
            FactState {
                owned,
                local_union_owned,
                #[cfg(feature = "receipt-slots")]
                port_slot: 0,
                decoded: Some((t, vs.clone())),

                entry: None,
                hidden,
                epoch: self.epoch,
                born: self.epoch,
                hash: h,
            },
        );
        self.members[t].insert(f.ordered_id());
        if self.constructor_hint_enabled(t) {self.intern.entry(h).or_default().insert(f);}
        if owned { self.query_versions[t] += 1; self.publish_owned_birth(f,t,&vs); }
        else if local_union_owned { self.query_versions[t] += 1; }
        else { self.subscribe_rows(t, Dependency::Fact(f), &[], &vs); }
        self.changes.touch(t, Dependency::Fact(f));
        self.stats.logical_facts_created += 1;

        if self.union_digest.is_some() {
            self.register_digest(f)?;
        }

        self.changed = true;
        Ok(())
    }
    /// Complete a Cell from matched inputs and any required witnesses. On the first miss, retain its frame,
    /// receipts and ordered effects and resume the original RHS at that op.
    #[cfg(feature = "iterative-bake")]
    pub(crate) fn start_completion(
        &mut self,
        rule: usize,
        values: crate::slots::Slots,
        parent: Option<FactRef>,
        transfers: &[crate::result_handoff::Input],
        receipts: &mut crate::cell::Effects,
    ) -> Result<(cell_prefix::Start, u64)> {
        use crate::cell::{CellFrame, HandoffCounts, LocalCall, complete_handoff};
        let template = self.program.rules[rule].template;
        let ops = self.program.templates[template].ops.clone();
        let aliases = self.program.known_results.static_skip[rule].clone();
        let cell = self.next_cell;
        #[cfg(feature = "sparse-cells")]
        self.trust_sealed_frame(cell);
        let before_unions = self.stats.union_requests;
        // The matched allocation is the execution frame. Reused results are
        // written here once, including when a later receipt fails validation.
        // Keep captured inputs until promotion; only then may the ordinary
        // parent projection replace input fields, exactly as on the old path.
        let mut frame = self.new_cell(template, values, None);
        let before_capacity = frame.values.capacity_bytes();
        let mut pending = LocalCall { cell, frame: &mut frame };
        let mut transfers = transfers.iter().peekable();
        let mut counts = HandoffCounts::default();
        let mut skipped = 0;
        let mut first_miss = None;
        for (op, instruction) in ops.iter().enumerate() {
            if aliases[op] {
                // The common Cell operand reader already projects this alias.
                // Structural proposals may include a redundant alias transfer;
                // it cannot become an extra read or a fabricated raw receipt.
                if transfers.peek().is_some_and(|input| input.op == op) { transfers.next(); }
                skipped += 1;
                continue;
            }
            match instruction {
                Op::Copy(..) => {} // The same lazy projection as the ordinary Cell RHS.
                Op::Union(a, b) => {
                    let a = pending.argument(self, a)?;
                    let b = pending.argument(self, b)?;
                    self.enqueue_source_union(a, b)?;
                }
                Op::Let(_, Call::Table(_), _) | Op::Set(..) => {
                    let Some(input) = transfers.next() else { first_miss = Some(op); break; };
                    if input.op != op { return Err("invalid completed block order".into()); }
                    self.stats.handoff_attempts += 1;
                    let Some((witness, original)) = complete_handoff(self, &mut pending, instruction, input, &mut counts)?
                        else {
                            if input.fact.is_none() { self.stats.handoff_missing += 1; }
                            else { self.stats.handoff_stale += 1; }
                            first_miss = Some(op);
                            break;
                        };
                    receipts.record_handoff(op, witness, input, original, self.program.iterative.tracks_slots());
                }
                _ => return Err("unexpected instruction in completed block".into()),
            }
        }
        let reserved = self.reserve_cell_id()?;
        debug_assert_eq!(cell, reserved);
        let growth = frame.values.capacity_bytes().saturating_sub(before_capacity);
        self.stats.completion_frame_growth_bytes += growth as u64;
        self.stats.completion_frame_growths += u64::from(growth != 0);
        self.stats.completion_frame_result_writes += counts.lets;
        let result_slots = counts.lets;
        let count = self.stats.union_requests - before_unions;
        counts.commit(&mut self.stats);
        // The completed prefix will not run again, even after a later miss.
        self.known_stats.static_eliminated += skipped;
        self.known_stats.avoided_lookups += skipped;
        let start = if let Some(next_op) = first_miss {
            // Parent fields used to be removed from the input map before the
            // separate computed map was merged back. Keep exactly that policy
            // while retaining one allocation and already completed results.
            let t = &self.program.templates[template];
            frame.parent = parent.filter(|_| !t.parent_columns.is_empty());
            if frame.parent.is_some() {
                for slot in t.parent_columns.keys() {
                    let computed = t.defs.get(slot).is_some_and(|&op|
                        op < next_op && !aliases[op] && matches!(ops[op], Op::Let(..)));
                    if !computed { frame.values.remove(slot); }
                }
            }
            self.stats.completion_promoted_result_slots += result_slots;
            #[cfg(feature = "sparse-cells")]
            {
                debug_assert!(self.active_rhs.is_none());
                self.active_origin = None;
                self.trust_sealed_frame(cell);
                self.active_rhs = Some((cell, frame));
            }
            #[cfg(not(feature = "sparse-cells"))]
            self.store_cell(cell, frame);
            cell_prefix::Start::Resume { cell, next_op }
        } else {
            self.stats.rhs_frames_avoided += 1;
            cell_prefix::Start::Complete { cell, frame }
        };
        Ok((start, count))
    }
    #[cfg(feature = "structural-depth")]
    pub(crate) fn checked_constructor(
        &self,
        f: FactRef,
        table: usize,
        key: &[Value],
    ) -> Result<Option<Row>> {
        Ok(self
            .live_handoff(f, table)?
            .filter(|r| r.values.split_last().is_some_and(|(_, k)| k == key)))
    }
    #[cfg(feature = "iterative-bake")]
    pub(crate) fn live_handoff(&self, f: FactRef, table: usize) -> Result<Option<Row>> {
        Ok(self.live_handoff_origin(f,table)?.map(|(row,_)|row))
    }
    #[cfg(feature = "iterative-bake")]
    pub(crate) fn live_handoff_origin(&self, f: FactRef, table: usize) -> Result<Option<(Row,bool)>> {
        if !self.dirty_facts[table].is_empty() { return Ok(None); }
        // The existing forwarding walk already proves whether the returned
        // receipt is the original source. Carry that proof with the handoff.
        let (witness,original)=self.resolve_receipt_origin(Dependency::Fact(f));
        Ok(self.row(witness)?.filter(|r|r.table==table && !r.hidden).map(|row|(row,original)))
    }
    pub fn construct(
        &mut self,
        cell: u32,
        op: usize,
        t: usize,
        aa: &[Arg],
        dst: usize,
    ) -> Result<Value> {
        self.construct_inner(cell, op, t, aa, dst, None, None, None)
    }
    pub fn construct_visible(
        &mut self,
        cell: u32,
        op: usize,
        t: usize,
        aa: &[Arg],
        dst: usize,
        visible: &mut bool,
    ) -> Result<Value> {
        self.construct_inner(cell, op, t, aa, dst, Some(visible), None, None)
    }
    pub fn construct_recorded(
        &mut self,
        cell: u32,
        op: usize,
        t: usize,
        aa: &[Arg],
        dst: usize,
        receipt: &mut Option<Dependency>,
        visible: &mut bool,
    ) -> Result<Value> {
        self.construct_inner(cell, op, t, aa, dst, Some(visible), Some(receipt), None)
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn construct_prepared(&mut self, cell: u32, op: usize, table: usize,
        args: &[Arg], dst: usize, receipt: Option<&mut Option<Dependency>>, witness: FactRef) -> Result<Value> {
        self.construct_inner(cell, op, table, args, dst, None, receipt, Some(witness))
    }
    /// The checked preparation plan uses immutable captured inputs and their
    /// scalar descendants. An unchanged source-Run union certificate therefore
    /// preserves its already checked key. Only the original live incarnation is
    /// admitted here; forwarding, dirty tables and invalid certificates retain
    /// the ordinary exact-key check. Callers must consume the prepared witness
    /// at its selected source operation, never treat arbitrary receipts this way.
    #[cfg(feature = "sparse-cells")]
    fn sealed_constructor_result(&mut self, cell: u32, table: usize, witness: FactRef) -> Result<Option<Point>> {
        self.stats.constructor_prepared_certificates += 1;
        if self.sealed_input_cell != Some(cell)
            || self.sealed_generation != Some(self.stats.unions)
            || !self.dirty_facts[table].is_empty() {
            return Ok(None);
        }
        self.stats.constructor_prepared_liveness_checks += 1;
        if self.receipt_forwards.contains_key(&Dependency::Fact(witness)) { return Ok(None); }
        let Some(frame) = self.cells.cell_metadata(witness.cell) else { return Ok(None); };
        let Some(state) = self.cells.fact_state(witness).filter(|s| !s.hidden) else { return Ok(None); };
        let (actual, args, result) = match &self.program.templates[frame.template].ops[witness.op as usize] {
            Op::Let(dst, Call::Table(t), args) => (*t, args, Arg::Slot(*dst)),
            Op::Set(t, args, value) => (*t, args, value.clone()),
            _ => return Ok(None),
        };
        if actual != table { return Ok(None); }
        // Match fact()'s precedence without materializing its key columns.
        let value = if let Some(stored) = self.stable_node(witness) {
            self.read_stable_column(stored, args.len())?
        } else if let Some((_, values)) = &state.decoded {
            values.last().expect("constructor result").clone()
        } else {
            self.argument(witness.cell, &result)?
        };
        let point = Point { value, hidden: false, epoch: state.epoch, witness: Dependency::Fact(witness) };
        self.stats.constructor_prepared_checks += 1;
        self.stats.constructor_prepared_accepted += 1;
        self.stats.constructor_prepared_sealed += 1;
        self.stats.constructor_prepared_result_reads += 1;
        self.stats.constructor_prepared_key_fields_avoided += args.len() as u64;
        Ok(Some(point))
    }
    /// Bake proved the key from a successful immutable query anchor and shared
    /// ports. This proof survives equality growth, but never authorizes a dead,
    /// hidden or currently dirty constructor. Return the actual stored result.
    #[cfg(feature="sparse-cells")]
    fn cell_witness_result(&mut self,table:usize,witness:FactRef)->Result<Option<Point>> {
        self.stats.constructor_cell_route_proof_admissions+=1;
        if !self.dirty_facts[table].is_empty() || self.receipt_forwards.contains_key(&Dependency::Fact(witness)) {return Ok(None);}
        let Some(state)=self.cells.fact_state(witness).filter(|s|s.owned && !s.hidden) else {return Ok(None);};
        let Some(stored)=self.stable_node(witness) else {return Ok(None);};
        if self.dependency_table(Dependency::Fact(witness))!=Some(table) {return Ok(None);}
        let width=self.program.tables[table].schema.len()-1;
        let value=self.read_stable_column(stored,width)?;
        Ok(Some(Point{value,hidden:false,epoch:state.epoch,witness:Dependency::Fact(witness)}))
    }
    /// A prepared witness is evidence for this one source lookup, never an
    /// assigned Eq value. Invalid evidence uses the very same current key.
    pub(crate) fn lookup_prepared_constructor(&mut self, table: usize, key: &[Value],
        witness: Option<FactRef>) -> Result<Option<Row>> {
        #[cfg(feature = "sparse-cells")]
        if let Some(witness) = witness {
            self.stats.constructor_prepared_checks += 1;
            if let Some((row, _)) = self.live_handoff_origin(witness, table)? {
                let fields = &row.values[..row.values.len() - 1];
                let equal = fields.len() == key.len() && fields.iter().zip(key).all(|(a,b)| {
                    self.stats.constructor_prepared_fields += 1;
                    a == b
                });
                if equal {
                    self.stats.constructor_prepared_accepted += 1;
                    return Ok(Some(row));
                }
            }
            self.stats.constructor_prepared_rejected += 1;
        }
        #[cfg(not(feature = "sparse-cells"))]
        let _ = witness;
        self.lookup_canonical(table, key)
    }
    fn construct_inner(
        &mut self,
        cell: u32,
        op: usize,
        t: usize,
        aa: &[Arg],
        dst: usize,
        visible: Option<&mut bool>,
        receipt: Option<&mut Option<Dependency>>,
        witness: Option<FactRef>,
    ) -> Result<Value> {
        self.stats.constructor_requests += 1;
        #[cfg(feature = "sparse-cells")]
        if let Some(witness) = witness
            && let Some(point) = self.sealed_constructor_result(cell, t, witness)? {
            if let Some(receipt) = receipt { *receipt = Some(point.witness); }
            if let Some(visible) = visible { *visible = true; }
            self.stats.constructor_reused += 1;
            self.rhs_frame_mut(cell).unwrap().values.insert(dst, point.value.clone());
            return Ok(point.value);
        }
        #[cfg(feature = "sparse-cells")]
        let route = if witness.is_none() { self.cell_constructor_witness(cell, op) } else { None };
        #[cfg(feature = "sparse-cells")]
        if let Some((target,true))=route && let Some(point)=self.cell_witness_result(t,target)? {
            if let Some(receipt)=receipt {*receipt=Some(point.witness);}
            if let Some(visible)=visible {*visible=true;}
            self.stats.constructor_reused+=1;
            self.stats.constructor_cell_route_accepted+=1;
            self.stats.constructor_cell_route_key_proved+=1;
            self.stats.constructor_cell_route_key_fields_avoided+=aa.len() as u64;
            self.rhs_frame_mut(cell).unwrap().values.insert(dst,point.value.clone());
            return Ok(point.value);
        }
        let key = self.inline_arguments(cell, aa)?;
        #[cfg(feature = "sparse-cells")]
        let direct=route.map(|(fact,_)|fact);
        #[cfg(not(feature = "sparse-cells"))]
        let direct = None;
        let accepted = self.stats.constructor_prepared_accepted;
        let row = self.lookup_prepared_constructor(t, &key, witness.or(direct))?;
        if direct.is_some() { self.stats.constructor_cell_route_accepted += self.stats.constructor_prepared_accepted - accepted; }
        if let Some(row) = row {
            if let Some(receipt) = receipt {
                *receipt = Some(row.witness);
            }
            if let Some(visible) = visible {
                *visible = !row.hidden;
            }
            self.stats.constructor_reused += 1;

            let value = row.values.last().unwrap().clone();
            self.rhs_frame_mut(cell)
                .unwrap()
                .values
                .insert(dst, value.clone());
            return Ok(value);
        }
        let value = self.insert_constructor(cell, op, t, &key, dst)?;

        if let Some(receipt) = receipt {
            *receipt = Some(Dependency::Fact(FactRef {
                cell,
                op: op as u32,
            }));
        }
        if let Some(visible) = visible {
            *visible = true;
        }
        Ok(value)
    }
    fn insert_constructor(
        &mut self,
        cell: u32,
        op: usize,
        t: usize,
        key: &[Value],
        dst: usize,
    ) -> Result<Value> {
        let value = self.slot(cell, dst)?;
        self.activate(
            FactRef {
                cell,
                op: op as u32,
            },
            t,
            key,
            value.clone(),
            false,
        )?;
        Ok(value)
    }

    pub fn dynamic_construct(&mut self, t: usize, args: impl AsRef<[Value]> + IntoIterator<Item = Value>) -> Result<Value> {
        let key = args.as_ref()
            .iter()
            .map(|v| canon(v, &self.parents))
            .collect::<smallvec::SmallVec<[Value; 4]>>();
        if let Some(row) = self.lookup_canonical(t, &key)? {
            return Ok(row.values.last().unwrap().clone());
        }
        let dst = args.as_ref().len();
        let cell = self.linked_slots(
            self.program.table_templates[t],
            args.into_iter().enumerate().collect(),
            None,
        )?;
        // Creating this empty frame changes neither Parents nor the constructor
        // index. The lookup miss above still proves that this canonical key is
        // absent; do not repeat the (potentially expensive) port-domain lookup.
        // As before, dynamic hits do not enter the RHS constructor path.
        self.stats.constructor_requests += 1;
        self.insert_constructor(cell, 0, t, &key, dst)
    }
    pub fn enqueue_union(&mut self, a: Value, b: Value) -> Result<()> {
        self.stats.union_requests += 1;
        let (Value::Eq(a), Value::Eq(b)) = (a, b) else {
            return Err("union requires equality values".into());
        };
        self.pending_unions.push((a, b));

        Ok(())
    }
    fn union(&mut self, a: u64, b: u64) -> Result<()> {
        let a = root(&self.parents, a);
        let b = root(&self.parents, b);
        if a == b {
            return Ok(());
        }
        let (lo, hi) = (a.min(b), a.max(b));

        #[cfg(feature = "sparse-cells")]
        { self.sealed_input_cell = None; }
        // Capture the old native domain while hi is still a root. Stable
        // signal bindings resolve through Parents and must not see this link.
        let native = self.native_signal(hi);
        self.parents.insert(hi, lo);
        self.unique_union_frontier(hi);
        self.propagate_owned_union(hi, lo, native);
        self.maintenance.union_frontier_probes += 1;
        let mut affected = self.uses.remove(&hi).unwrap_or_default();
        let displaced = affected.len();
        let kept = self.uses.get(&lo).map_or(0, |s|s.len());
        self.maintenance.union_wake_visits += displaced as u64;
        self.maintenance.union_redirected_edges += displaced as u64;
        // Only displaced identities change row fields. Re-stamping the already
        // canonical side can re-run an unchanged LHS and create extra custom
        // merge nodes (e.g. a repeated default ExtractedExpr write).
        if self.union_digest.is_some() {
            self.match_equality_digest(hi, lo, &affected)?;
        } else {
            self.mark_affected(&affected, hi, lo);
        }
        #[cfg(not(feature = "sparse-cells"))]
        {
            self.maintenance.reverse_merge_inserts += kept as u64;
            affected.extend(self.uses.get(&lo).into_iter().flatten().copied());
            self.uses.insert(lo, affected);
        }
        #[cfg(feature = "sparse-cells")]
        if !affected.is_empty() {
            let keep = self.uses.entry(lo).or_default();
            if keep.len() < affected.len() {
                std::mem::swap(keep, &mut affected);
            }
            self.maintenance.reverse_merge_inserts += affected.len() as u64;
            for &dependency in affected.iter() {
                keep.insert(dependency);
            }
        }
        let merged = self.uses.get(&lo).map_or(0, |s|s.len());
        let coalesced = (displaced + kept - merged) as u64;
        self.maintenance.reverse_edges_coalesced += coalesced;
        self.maintenance.live_reverse_edges -= coalesced;
        self.stats.unions += 1;
        self.changed = true;
        if self.union_digest.is_some() {
            self.retire_digest_duplicates()?;
        }
        Ok(())
    }
    /// Complete visible scalar equality incidences from the existing reverse
    /// dependency index, including non-root argument positions.

    fn mark_affected(&mut self, affected: &UseSet, from: u64, to: u64) {
        for d in affected.iter() {
            #[cfg(feature = "spine-blocks")]
            let mut retained = false;
            #[cfg(not(feature = "spine-blocks"))]
            let retained = false;
            #[cfg(feature = "spine-blocks")]
            if self.repair_cells.is_some() && let Dependency::Fact(f) = d {
                match self.match_repair_delta(*f, from, to) {
                    repair_cells::Delta::Published => continue,
                    repair_cells::Delta::Deferred => retained = true,
                    repair_cells::Delta::Uncovered => (),
                }
            }
            if !retained && self.repair_ports.is_some()
                && let Dependency::Fact(f) = d
                && self.finish_result_port(*f, from, to)
            {
                continue;
            }
            let table = self.dependency_table(*d);
            if let Dependency::Function(i) = d {
                self.functions[*i].canonical = false;
            }
            if !retained && let Dependency::Fact(f) = d
                && let Some(mut state) = self
                    .cells.fact_state_mut(*f)
            {
                state.decoded = None;
            }
            {
                self.dirty.insert(*d);
            }
            if let Dependency::Fact(f) = d {
                if let Some(table) = table {
                    self.dirty_facts[table].insert(*f);
                }
            }
        }
    }

    pub fn set(&mut self, cell: u32, op: usize, t: usize, aa: &[Arg], v: &Arg) -> Result<()> {
        self.set_inner(cell, op, t, aa, v, None, None, None)
    }
    pub fn set_visible(
        &mut self,
        cell: u32,
        op: usize,
        t: usize,
        aa: &[Arg],
        v: &Arg,
        visible: &mut bool,
    ) -> Result<()> {
        self.set_inner(cell, op, t, aa, v, Some(visible), None, None)
    }
    pub fn set_recorded(
        &mut self,
        cell: u32,
        op: usize,
        t: usize,
        aa: &[Arg],
        v: &Arg,
        receipt: &mut Option<Dependency>,
        visible: &mut bool,
    ) -> Result<()> {
        self.set_inner(cell, op, t, aa, v, Some(visible), Some(receipt), None)
    }
    pub(crate) fn set_inner(
        &mut self,
        cell: u32,
        op: usize,
        t: usize,
        aa: &[Arg],
        v: &Arg,
        visible: Option<&mut bool>,
        receipt: Option<&mut Option<Dependency>>,
        source: Option<usize>,
    ) -> Result<()> {
        let key = self.inline_arguments(cell, aa)?;
        let value = self.argument(cell, v)?;
        if !self.program.tables[t].virtual_fact {
            let before = self.stats.function_updates;
            let index = self.set_function_from(t, &key, value, Some((cell, op, source)))?;
            if let Some(receipt) = receipt {
                *receipt = Some(Dependency::Function(index));
            }
            if self.stats.function_updates != before {
                #[cfg(feature = "sparse-cells")]
                if self.active_rhs.as_ref().is_some_and(|(id, _)| *id == cell) {
                    self.active_origin = Some(index);
                }
                self.function_origin(
                    index,
                    Some(FactRef {
                        cell,
                        op: op as u32,
                    }),
                );
            }
            if let Some(visible) = visible {
                *visible = true;
            }
            return Ok(());
        }
        if let Some(old) = self.lookup_canonical(t, &key)? {
            if let Some(receipt) = receipt {
                *receipt = Some(old.witness);
            }
            if let Some(visible) = visible {
                *visible = !old.hidden
                    && (!self.program.tables[t].constructor || old.values.last() == Some(&value));
            }
            if self.program.tables[t].constructor {
                self.enqueue_union(old.values.last().unwrap().clone(), value)?
            } else if old.values.last() != Some(&value) {
                return Err("relation output conflict".into());
            }
        } else {
            if let Some(receipt) = receipt {
                *receipt = Some(Dependency::Fact(FactRef {
                    cell,
                    op: op as u32,
                }));
            }
            if let Some(visible) = visible {
                *visible = true;
            }
            self.activate(
                FactRef {
                    cell,
                    op: op as u32,
                },
                t,
                &key,
                value,
                false,
            )?;
        }
        Ok(())
    }
    fn merge_expression(&mut self, e: &J, old: &Value, new: &Value) -> Result<Value> {
        // Native ResolvedMergeFn::Function returns old on identical arguments.
        // Primitive merges do NOT have this shortcut: (+ old new) must execute.
        if let Some(v) = e["var"].as_str() {
            return match v {
                "old" => Ok(old.clone()),
                "new" => Ok(new.clone()),
                _ => Err("unknown merge variable".into()),
            };
        }
        if !e["literal"].is_null() {
            return value::literal(e);
        }
        let aa = array(&e["args"])?
            .iter()
            .map(|a| self.merge_expression(a, old, new))
            .collect::<Result<Vec<_>>>()?;
        if let Some(name) = e["call"]["table"].as_str() {
            let t = self
                .program
                .tables
                .iter()
                .position(|t| t.name == name)
                .ok_or("merge operator")?;
            if !self.program.tables[t].virtual_fact {
                self.stats.merge_port_reads += 1;
                return self.read_merge_port(t, &aa);
            }
            self.dynamic_construct(t, aa)
        } else {
            if e["call"]["primitive"]
                .as_str()
                .is_some_and(|n| n.starts_with("cell-key-"))
            {
                self.stats.key_operations += 1;
            }
            value::primitive(
                string(&e["call"]["primitive"])?,
                &aa,
                string(&e["call"]["output"])?,
                self.program.key_nodes(),
            )?
            .ok_or("merge arithmetic failed".into())
        }
    }
    fn merge_value(&mut self, t: usize, old: Value, new: Value) -> Result<Value> {
        self.stats.merge_calls += 1;
        if let Some(kind) = &self.merge_kinds[t] {
            if let Some(n) = self.stats.merge_contract_calls.get_mut(kind) {
                *n += 1;
            } else {
                self.stats.merge_contract_calls.insert(kind.clone(), 1);
            }
        }
        if self.scalar_merge
            && let Some(plan) = self.program.physical.merges.get(t).copied().flatten()
        {
            use crate::physical_plan::ScalarMerge;
            let keep_old = match (plan, &old, &new) {
                (ScalarMerge::Old, _, _) => {
                    self.stats.scalar_old_projection += 1;
                    true
                }
                (ScalarMerge::Min, Value::Int(a), Value::Int(b)) => a <= b,
                (ScalarMerge::Max, Value::Int(a), Value::Int(b)) => a >= b,
                _ => return Err("unexpected scalar merge value".into()),
            };
            self.stats.scalar_merge_calls += 1;
            self.stats.scalar_unchanged += u64::from(keep_old);
            return Ok(if keep_old { old } else { new });
        }
        let expr = &self.program.tables[t].merge;
        if old == new && self.equal_keeps_old[t] {
            return Ok(old);
        }
        if expr.is_null() {
            return if old == new {
                Ok(old)
            } else {
                Err(format!(
                    "conflicting function {} without merge",
                    self.program.tables[t].name
                ))
            };
        }
        if self.merge_programs_enabled {
            let m = self
                .program
                .merge_programs
                .merges
                .get(&t)
                .cloned()
                .ok_or("missing compiled merge")?;
            self.stats.merge_program_calls += 1;
            if m.operations.is_empty() {
                return Ok(match &m.result {
                    Arg::Slot(0) => old,
                    Arg::Slot(1) => new,
                    Arg::Literal(v) => v.clone(),
                    _ => return Err("merge result slot".into()),
                });
            }
            let mut frame = crate::cell::MergeFrame::new(old, new, m.operations.len());
            for (i, op) in m.operations.iter().enumerate() {
                let Op::Let(dst, call, args) = op else {
                    return Err("invalid merge instruction".into());
                };
                crate::cell::evaluate_call(self, &mut frame, i, *dst, call, args)?;
                self.stats.merge_program_operations += 1;
            }
            Ok(frame.operand(&m.result))
        } else {
            let expr = expr.clone();
            self.merge_expression(&expr, &old, &new)
        }
    }
    pub(crate) fn read_merge_port(&mut self, t: usize, args: &[Value]) -> Result<Value> {
        let key = args
            .iter()
            .map(|v| canon(v, &self.parents))
            .collect::<Vec<_>>();
        let mut result: Option<Value> = None;
        // During repair the ordinary key directory may still contain displaced
        // keys. Resolve the complete canonical port, including pending pure
        // lattice collisions; never pick an arbitrary stale entry.
        for &id in self.members[t].iter() {
            let i = id as usize;
            let Some(row) = self.function(i) else {
                continue;
            };
            if row.values[..key.len()] != key {
                continue;
            }
            let value = row.values.last().unwrap().clone();
            if let Some(old) = result.as_ref() {
                if *old == value {
                    continue;
                }
                let e = &self.program.tables[t].merge;
                let Some(op) = e["call"]["primitive"]
                    .as_str()
                    .filter(|op| matches!(*op, "min" | "max" | "or" | "and" | "cell-key-min"))
                else {
                    return Err("ambiguous non-lattice merge read".into());
                };
                let a = e["args"].as_array().ok_or("invalid lattice merge")?;
                if a.len() != 2
                    || !((a[0]["var"] == "old" && a[1]["var"] == "new")
                        || (a[0]["var"] == "new" && a[1]["var"] == "old"))
                {
                    return Err("ambiguous merge port requires a pure lattice contract".into());
                }
                result = value::primitive(
                    op,
                    &[old.clone(), value],
                    self.program.tables[t].schema.last().unwrap()["name"]
                        .as_str()
                        .unwrap(),
                    self.program.key_nodes(),
                )?;
            } else {
                result = Some(value);
            }
        }
        result.ok_or_else(|| format!("unready merge port {}", self.program.tables[t].name))
    }
    pub fn set_function(&mut self, t: usize, key: Vec<Value>, value: Value) -> Result<()> {
        self.set_function_inner(t, key, value).map(|_| ())
    }
    fn set_function_inner(&mut self, t: usize, key: Vec<Value>, value: Value) -> Result<usize> {
        let key = key
            .into_iter()
            .map(|v| canon(&v, &self.parents))
            .collect::<Vec<_>>();
        let value = canon(&value, &self.parents);
        self.set_function_canonical(t, &key, value)
    }
    fn set_function_canonical(&mut self, t: usize, key: &[Value], value: Value) -> Result<usize> {
        self.set_function_from(t, key, value, None)
    }
    fn set_function_from(
        &mut self,
        t: usize,
        key: &[Value],
        value: Value,
        site: Option<(u32, usize, Option<usize>)>,
    ) -> Result<usize> {
        let index = self.function_index(t, key);
        if let Some(i) = index {
            let old = canon(self.functions[i].value(), &self.parents);
            let next = self.merge_value(t, old.clone(), value)?;
            if next != old {
                let changes_refs = matches!(old, Value::Eq(_) | Value::Set(_))
                    || matches!(next, Value::Eq(_) | Value::Set(_));
                let previous = changes_refs.then(|| self.function(i).unwrap().values);
                self.functions[i].set_fields(Self::shared_fields(key, &next));
                #[cfg(feature = "slot-transfer-audit")]
                crate::transfer_audit::effective(self.epoch, t, i, key, Some(&old), &next)?;
                self.functions[i].epoch = self.epoch;
                self.changed = true;
                self.stats.function_updates += 1;
                self.changes.touch(t, Dependency::Function(i));
                // A scalar result change preserves every subscribed eclass.
                // Publish the row version without rebuilding its reverse uses.
                if !changes_refs {
                    self.query_versions[t] += 1;
                } else {
                    let row = self.function(i).unwrap();
                    self.subscribe_function(row.table, i, previous.as_deref().unwrap(), &row.values);
                }
            }
            Ok(i)
        } else {
            let i = self.functions.len();
            #[cfg(feature = "slot-transfer-audit")]
            crate::transfer_audit::effective(self.epoch, t, i, key, None, &value)?;
            let compact = if cfg!(feature = "view-storage")
                && self.units.owned[t]
                && value == Value::Int(0)
            {
                self.try_view_projection(t, i, key, site)?
            } else {
                false
            };
            let fields = if compact {
                Self::shared_fields(&[], &value)
            } else {
                #[cfg(feature = "sparse-cells")]
                self.function_keys[t].insert(key, i);
                #[cfg(not(feature = "sparse-cells"))]
                self.function_keys[t].insert(key.to_vec(), i);
                Self::shared_fields(key, &value)
            };
            self.functions.push(Function {
                #[cfg(feature = "sparse-cells")]
                writer: None,
                #[cfg(feature = "receipt-slots")]
                port_slot: 0,
                table: t,
                fields,
                canonical: !compact,
                projected: compact,
                epoch: self.epoch,
                live: true,
                origin: None,
            });
            self.members[t].insert(i as u64);
            self.changed = true;
            self.stats.function_updates += 1;
            self.changes.touch(t, Dependency::Function(i));
            if compact {
                // Unit contributes no equality dependency.
                self.subscribe_function(t, i, &[], key);
            } else {
                let row = self.function(i).unwrap();
                self.subscribe_function(row.table, i, &[], &row.values);
            }
            Ok(i)
        }
    }
    fn retire(&mut self, f: FactRef) -> Result<()> {
        if let Some(r) = self.fact(f)? {
            #[cfg(all(feature="storage-metrics",feature="sparse-cells"))]
            if crate::receipt_trace::enabled() {
                crate::receipt_trace::retire(Dependency::Fact(f),r.table,self.cells.cell_metadata(f.cell).map(|c|c.template),self.receipt_tracking);
            }
            #[cfg(all(feature="storage-metrics",feature="sparse-cells"))]
            self.preserve_completed_scalars(f);
            let owned=self.retire_owned(f,r.table);
            let local = self.cells.fact_state(f).unwrap().local_union_owned;
            self.end_local_ownership(f, r.table, true);
            if let Some(matcher) = self.union_digest.as_mut() {
                matcher.removed(f);
            }
            self.changes.retire(r.table, Dependency::Fact(f));
            self.query_versions[r.table] += 1;
            let s = self
                .cells.remove_fact_state(f)
                .unwrap();
            self.retire_stable_node(f);
            #[cfg(feature = "receipt-slots")]
            if s.port_slot != 0 {
                self.retired_port_slots
                    .insert(Dependency::Fact(f), s.port_slot);
            }
            self.members[r.table].remove(&f.ordered_id());
            if self.constructor_hint_enabled(r.table) && let Some(b) = self.intern.get_mut(&s.hash) {
                b.remove(&f);
                #[cfg(feature = "sparse-cells")]
                if b.is_empty() {
                    self.intern.remove(&s.hash);
                }
            }
            if local || owned { self.query_versions[r.table] += 1; }
            else { self.subscribe_rows(r.table, Dependency::Fact(f), &r.values, &[]); }
            self.garbage.insert(f.cell);
        }
        Ok(())
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn has_visibility_changes(&self, t: usize) -> bool {
        self.visibility_tainted[t]
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn constructor_prefix_table_ready(&self, table: usize) -> bool {
        !self.visibility_tainted[table] && self.dirty_facts[table].is_empty()
    }
    pub fn hide(&mut self, t: usize, key: &[Value], delete: bool) -> Result<bool> {
        if self.union_digest.is_some() {
            return Err("union digest does not support deletion or subsumption".into());
        }
        #[cfg(feature = "sparse-cells")]
        {
            self.visibility_tainted[t] = true;
        }
        if delete {
            self.deletion_epochs[t] = self.epoch;
        }
        let row = self.lookup(t, key)?;
        let Some(row) = row else {
            return if delete {
                Ok(false)
            } else {
                let v = self.dynamic_construct(t, key.to_vec())?;
                let _ = v;
                self.hide(t, key, false)?;
                Ok(false)
            };
        };
        match row.witness {
            Dependency::Fact(f) => {
                let born = self.cells.fact_state(f).unwrap().born;
                if delete {
                    self.retire(f)?;
                    self.changed = true;
                } else {
                    let mut s_guard = self
                        .cells.fact_state_mut(f)
                        .unwrap();
                    let s = &mut *s_guard;
                    if !s.hidden {
                        self.query_versions[t] += 1;
                        #[cfg(feature = "receipt-slots")]
                        if s.port_slot != 0 {
                            self.retired_port_slots
                                .insert(row.witness, std::mem::take(&mut s.port_slot));
                        }
                        s.hidden = true;
                        s.epoch = self.epoch;
                        self.changed = true;
                        self.changes.touch(t, row.witness);
                    }
                }
                Ok(born < self.epoch)
            }
            Dependency::Function(i) => {
                if !delete {
                    return Err("function subsume unsupported".into());
                }
                #[cfg(feature = "receipt-slots")]
                if self.functions[i].port_slot != 0 {
                    self.retired_port_slots.insert(
                        Dependency::Function(i),
                        std::mem::take(&mut self.functions[i].port_slot),
                    );
                }
                self.functions[i].live = false;
                self.changes.retire(t, row.witness);
                self.function_origin(i, None);
                self.query_versions[t] += 1;
                self.members[t].remove(&(i as u64));
                if self.units.remove(i) {
                    self.units.stats.deleted += 1;
                } else {
                    #[cfg(feature = "sparse-cells")]
                    self.function_keys[t].remove(key, i);
                    #[cfg(not(feature = "sparse-cells"))]
                    self.function_keys[t].remove(key);
                }
                self.subscribe_function(row.table, i, &row.values, &[]);
                self.changed = true;
                Ok(true)
            }
        }
    }
    pub(crate) fn settled(&self)->bool {
        self.changes.is_empty() && self.pending_unions.is_empty() && self.dirty.is_empty()
            && self.dirty_markers.is_empty() && self.garbage.is_empty() && self.ownership_settled()
    }
    // Both bucket implementations iterate in witness order. Skipping self
    // before the read-only probe preserves remove-self-then-probe ordering;
    // no bucket clone or mutation is needed until the terminal effect.
    fn find_repair_collision(&mut self, f: FactRef, r: &Row, h: u64) -> Result<Option<Row>> {
        self.maintenance.repair_key_probes += 1;
        let key = &r.values[..r.values.len() - 1];
        for &other in self.intern.get(&h).into_iter().flatten() {
            if other == f { continue; }
            self.maintenance.repair_candidate_checks += 1;
            if let Some(row) = self.fact(other)? {
                if row.table == r.table && row.values[..key.len()] == *key { return Ok(Some(row)); }
            }
        }
        Ok(None)
    }
    fn complete_canonical_cell(&mut self, f: FactRef, row: Row) -> Result<()> {
        let hash = hashkey(row.table, &row.values[..row.values.len() - 1]);
        let found = self.find_repair_collision(f, &row, hash)?;
        self.complete_cell_collision(f, row, Some(hash), found, None)
    }
    /// A completed Cell lookup supplies the surviving witness. Canonical keys,
    /// exact port guards and prefetched guards share the same ordered effects.
    /// `result` is the current output when a batch reused only the input fields;
    /// it must not be replaced by the output retained in that older row view.
    fn complete_cell_collision(
        &mut self,
        f: FactRef,
        row: Row,
        hash: Option<u64>,
        found: Option<Row>,
        result: Option<Value>,
    ) -> Result<()> {
        self.join_constructor_epoch(&row, found.as_ref());
        // Port-key coverage already proves this is a constructor. Canonical
        // repair also serves relation facts, whose outputs must not be unioned.
        if let Some(other) = &found
            && (hash.is_none() || self.program.tables[row.table].constructor)
        {
            self.enqueue_union(
                result.unwrap_or_else(|| row.values.last().unwrap().clone()),
                other.values.last().unwrap().clone(),
            )?;
        }
        // No hash means stable fields: do not rewrite or reindex a birth hint.
        self.commit_constructor_collision(f, row, hash, found)
    }
    fn commit_constructor_collision(&mut self, f: FactRef, r: Row, h: Option<u64>, found: Option<Row>) -> Result<()> {
        let d = Dependency::Fact(f);
        let old = self.cells.fact_state(f).unwrap().hash;
        self.stats.repair_key_hash_changes += u64::from(h.is_some_and(|h|h != old));
        if h.is_some() && let Some(bucket) = self.intern.get_mut(&old) {
            bucket.remove(&f);
            #[cfg(feature = "sparse-cells")]
            if bucket.is_empty() { self.intern.remove(&old); }
        }
        if let Some(other) = found {
            self.note_local_collision(f);
            self.stats.repair_collisions += 1;
            if let Dependency::Fact(keep) = other.witness {
                self.query_versions[r.table] += 1;
                let mut target_guard = self
                    .cells.fact_state_mut(keep)
                    .unwrap();
                let target = &mut *target_guard;
                #[cfg(feature = "receipt-slots")]
                if r.hidden && target.port_slot != 0 {
                    self.retired_port_slots
                        .insert(other.witness, std::mem::take(&mut target.port_slot));
                }
                // Retiring a duplicate does not itself change the surviving
                // row. Its output union is queued above and will publish any
                // actual Eq change through the ordinary completion path.
                // A synthetic delta here can replay a nonmonotone source RHS.
                if r.hidden && !target.hidden {
                    target.hidden = true;
                    target.epoch = self.epoch;
                    self.changes.touch(r.table, other.witness);
                }
            }
            if self.receipt_tracking {
                self.forward_receipt(Dependency::Fact(f), other.witness);
            }
            self.retire(f)?;
        } else {
            let was_local = self.cells.fact_state(f).unwrap().local_union_owned;
            self.end_local_ownership(f, r.table, false);
            if let Some(h) = h { self.intern.entry(h).or_default().insert(f); }
            let mut s_guard = self
                .cells.fact_state_mut(f)
                .unwrap();
            let s = &mut *s_guard;

            s.decoded = if self.stable_ports.is_none() || !s.owned { Some((r.table, r.values.clone())) } else { None };
            if let Some(h) = h { s.hash = h; }
            s.epoch = self.epoch;
            drop(s_guard);
            if self.cells.fact_state(f).unwrap().owned {
                self.query_versions[r.table]+=1;
            } else { self.subscribe_rows(r.table, d, if was_local { &[] } else { &r.values }, &r.values); }
            self.changes.touch(r.table, d);
        }
        Ok(())
    }

    pub fn repair(&mut self) -> Result<()> {
        let epoch = self.epoch;
        let result = self.repair_selected(None);
        self.epoch = epoch;
        result
    }
    fn repair_selected(&mut self, allowed: Option<crate::table_mask::Selection<'_>>) -> Result<()> {
        if self.union_digest.is_some() {
            return self.propagate_union_digests();
        }
        let mut local_completion = Vec::new();
        loop {
            if allowed.is_some_and(|mask|self.pending_opaque_completion(mask)) {
                self.note_opaque_completion();
                return self.repair_selected(None);
            }
            if self.local_unions.as_ref().is_some_and(|m|!m.pending.is_empty()) {
                local_completion.extend(self.prepare_local_completion());
            }
            if !self.pending_unions.is_empty() {
                let pairs = std::mem::take(&mut self.pending_unions);
                self.commit_union_batch(pairs)?;
                local_completion = self.finish_local_completion(local_completion, false)?;
                continue;
            }

            let next = self.next_scoped_dirty(allowed);
            if self.complete_port_read_batch(next, allowed)? { continue; }
            if let Some(f)=self.pop_owned_before(next, allowed) {
                self.complete_owned_key(f)?;
                continue;
            }
            let Some((d, from_dirty)) = next.map(|d|(d,true))
                .or_else(|| self.next_scoped_marker(allowed).map(|f|(Dependency::Fact(f),false)))
            else {
                if !local_completion.is_empty() {
                    local_completion = self.finish_local_completion(local_completion, true)?;
                    continue;
                }
                break;
            };
            if from_dirty { self.dirty.remove(&d); }
            else if let Dependency::Fact(f) = d { self.dirty_markers.remove(&f); }
            if let Dependency::Fact(f) = d {
                if let Some(table) = self.dependency_table(d) {
                    self.dirty_facts[table].remove(&f);
                }
            }
            self.stats.repaired_dependencies += 1;

            match d {
                Dependency::Fact(f) => {
                    #[cfg(feature = "spine-blocks")]
                    if self.repair_cells.is_some() && self.match_repair_key(f)? { continue; }
                    let Some(r) = self.fact(f)? else { continue };
                    self.complete_canonical_cell(f, r)?;
                }
                Dependency::Function(i) => {
                    let Some(row) = self.function(i) else {
                        continue;
                    };
                    let key = row.values[..row.values.len() - 1].to_vec();
                    let compressed = self.units.remove(i);
                    let oldkey = self.functions[i].key();
                    if !compressed && self.indexed_function(row.table, oldkey) == Some(i) {
                        #[cfg(feature = "sparse-cells")]
                        self.function_keys[row.table].remove(oldkey, i);
                        #[cfg(not(feature = "sparse-cells"))]
                        self.function_keys[row.table].remove(oldkey);
                    }
                    if let Some(j) = self.function_index(row.table, &key) {
                        if j != i {
                            if compressed {
                                self.units.stats.lost += 1;
                            }

                            // The key directory selected the exact survivor. Its Unit
                            // value and canonical key keep all reverse subscriptions valid.
                            let shared_unit = cfg!(feature = "view-storage")
                                && self.units.owned[row.table]
                                && row.values.last() == Some(&Value::Int(0))
                                && *self.functions[j].value() == Value::Int(0)
                                && (self.functions[j].key() == key
                                    || self.units.change_block(j, &row.values));
                            let previous_target = (!shared_unit).then(|| self.function(j).unwrap().values);
                            let value_changed = if shared_unit {
                                self.functions[j].set_fields(row.values.clone());
                                self.units.stats.fast_merges += 1;
                                false
                            } else {
                                let old = canon(self.functions[j].value(), &self.parents);
                                #[cfg(feature = "slot-transfer-audit")]
                                let before = old.clone();
                                let next = self.merge_value(
                                    row.table,
                                    old.clone(),
                                    row.values.last().unwrap().clone(),
                                )?;
                                #[cfg(feature = "slot-transfer-audit")]
                                if before != next {
                                    crate::transfer_audit::effective(
                                        self.epoch,
                                        row.table,
                                        j,
                                        &key,
                                        Some(&before),
                                        &next,
                                    )?;
                                }
                                let changed = old != next;
                                if changed {
                                    self.functions[j].set_value(next);
                                }
                                changed
                            };
                            // Match normal set/merge semantics: an absorbed
                            // value retires its old key without refreshing the
                            // survivor's semi-naive timestamp.
                            if value_changed {
                                self.functions[j].epoch = self.epoch;
                                self.changes.touch(row.table, Dependency::Function(j));
                            }
                            #[cfg(feature = "receipt-slots")]
                            if self.functions[i].port_slot != 0 {
                                self.retired_port_slots.insert(
                                    Dependency::Function(i),
                                    std::mem::take(&mut self.functions[i].port_slot),
                                );
                            }
                            self.functions[i].live = false;
                            self.changes.retire(row.table, d);
                            if self.receipt_tracking {
                                self.forward_receipt(Dependency::Function(i), Dependency::Function(j));
                            }
                            self.function_origin(i, None);
                            self.members[row.table].remove(&(i as u64));
                            self.subscribe_function(row.table, i, &row.values, &[]);
                            if shared_unit {
                                self.query_versions[row.table] += 1;
                            } else {
                                let target = self.function(j).unwrap();
                                self.subscribe_function(target.table, j, previous_target.as_deref().unwrap(), &target.values);
                            }
                            continue;
                        }
                    }
                    if compressed {
                        self.units.stats.promoted += 1;
                    }
                    self.functions[i].projected = false;
                    self.functions[i].set_fields(row.values.clone());
                    self.functions[i].epoch = self.epoch;
                    #[cfg(feature = "sparse-cells")]
                    self.function_keys[row.table].insert(&key, i);
                    #[cfg(not(feature = "sparse-cells"))]
                    self.function_keys[row.table].insert(key, i);
                    self.subscribe_function(row.table, i, &row.values, &row.values);
                    self.changes.touch(row.table, d);
                }
            }
        }

        Ok(())
    }

    pub fn union_digest_report(&self) -> J {
        self.union_digest
            .as_ref()
            .map(|m| m.report())
            .unwrap_or_else(|| json!({"enabled": false}))
    }

    pub fn release_empty(&mut self, cell: u32) {
        #[cfg(feature = "sparse-cells")]
        if self.active_rhs.as_ref().is_some_and(|(id, _)| *id == cell) {
            #[cfg(feature = "sparse-cells")]
            if let Some(&n) = self.parent_users.get(&cell)
                && n > 0
            {
                if n == 1
                    && let Some(index) = self.active_origin
                    && index < u32::MAX as usize
                    && let Some(f) = self.functions[index].origin
                    && f.cell == cell
                {
                    self.parent_users.remove(&cell);
                    let (_, frame) = self.active_rhs.take().unwrap();
                    self.install_writer(index, f, frame, None);
                    self.writer_dir.general += 1;
                    return;
                }
                self.promote_active();
                return;
            }
            self.active_rhs = None;
            self.stats.rhs_frames_avoided += 1;
            return;
        }
        // Only the newly executed frame is retired here. Ancestors are kept
        // until the Run boundary: later bindings in this Run may still use them.
        self.retire_empty(cell);
    }
    fn retire_empty(&mut self, cell: u32) {
        if self.parent_users.get(&cell).copied().unwrap_or(0) == 0
            && self.cells.fact_count(cell)==Some(0)
        {
            if let Some(c) = self.cells.remove(&cell) {
                if let Some(p) = c.parent {
                    self.release_reference(p);
                }
            }
            #[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
            self.cells.retire_completed(cell);
            self.parent_users.remove(&cell);
            self.stats.empty_frames_released += 1;
        }
    }
    pub fn collect_garbage(&mut self) {
        while let Some(cell) = self.garbage.pop_first() {
            self.retire_empty(cell);
        }
    }
    pub fn export(&self) -> Result<J> {
        let mut rows = vec![];
        for t in 0..self.program.tables.len() {
            for w in self.witnesses(t) {
                if let Some(r) = self.row(w)? {
                    rows.push(json!({"table":self.program.tables[t].name,"values":r.values.iter().zip(&self.program.tables[t].schema).map(|(v,s)|exported(v,s)).collect::<Vec<_>>(),"subsumed":r.hidden}));
                }
            }
        }
        let anchors=self.anchors.iter().map(|(sort,old,id)|json!({"sort":sort,"old":old,"now":format!("Cell({})",root(&self.parents,*id))})).collect::<Vec<_>>();
        Ok(json!({"rows":rows,"anchors":anchors}))
    }
    /// Stream diagnostics without allocating a second complete row graph.
    pub fn write_export(&self, writer: impl std::io::Write) -> Result<()> {
        use serde::ser::{SerializeSeq, SerializeStruct};
        struct Rows<'a>(&'a Graph);
        impl Serialize for Rows<'_> {
            fn serialize<S: serde::Serializer>(
                &self,
                serializer: S,
            ) -> std::result::Result<S::Ok, S::Error> {
                let mut seq = serializer.serialize_seq(None)?;
                for table in 0..self.0.program.tables.len() {
                    for witness in self.0.witnesses(table) {
                        if let Some(row) = self.0.row(witness).map_err(serde::ser::Error::custom)? {
                            let table = &self.0.program.tables[row.table];
                            seq.serialize_element(&json!({"table":table.name,"values":row.values.iter().zip(&table.schema).map(|(v,s)|exported(v,s)).collect::<Vec<_>>(),"subsumed":row.hidden}))?;
                        }
                    }
                }
                seq.end()
            }
        }
        struct Export<'a>(&'a Graph);
        impl Serialize for Export<'_> {
            fn serialize<S: serde::Serializer>(
                &self,
                serializer: S,
            ) -> std::result::Result<S::Ok, S::Error> {
                let mut result = serializer.serialize_struct("Graph", 2)?;
                result.serialize_field("rows", &Rows(self.0))?;
                let anchors=self.0.anchors.iter().map(|(sort,old,id)|json!({"sort":sort,"old":old,"now":format!("Cell({})",root(&self.0.parents,*id))})).collect::<Vec<_>>();
                result.serialize_field("anchors", &anchors)?;
                result.end()
            }
        }
        serde_json::to_writer(writer, &Export(self)).map_err(|e| e.to_string())
    }
}

#[path = "producer.rs"]
pub(crate) mod producer;

#[cfg(all(test, feature="sparse-cells", feature="projection-stamps"))]
mod sealed_input_tests {
    use super::*;
    #[test]
    fn a_union_invalidates_the_active_frame_certificate() {
        let mut graph=crate::query::test_projection_graph();
        let values=std::iter::once((0,Value::Eq(9))).collect();
        graph.sealed_generation=Some(graph.stats.unions);
        graph.trust_sealed_frame(42);
        assert_eq!(graph.slot_fields(42,0,None,&values,0).unwrap(),Value::Eq(9));
        graph.union(9,2).unwrap();
        assert_eq!(graph.sealed_input_cell,None);
        assert_eq!(graph.slot_fields(42,0,None,&values,0).unwrap(),Value::Eq(2));
        graph.trust_sealed_frame(43);
        assert_eq!(graph.sealed_input_cell,None);
    }
}

#[cfg(all(test, feature="sparse-cells"))]
#[path = "cell_completion_owned_test.rs"]
mod owned_completion_tests;
