//! Graph storage census and opt-in capacity reclamation diagnostics.
use super::*;
impl Graph {
    /// Diagnostic memory-pressure operation at an idle source Run boundary.
    /// Logical IDs, facts and reads are preserved. Completed bindings may
    /// delegate to checked component symbols or existing recipe definitions.
    pub fn compact_retained_capacity(&mut self) -> Result<()> {
        if self.active_rhs.is_some() {
            return Err("cannot compact an active RHS".into());
        }
        self.take_over_parent_links()?;
        self.take_over_instance_slots();
        self.elide_reconstructible_slots();
        self.cells.compact_capacity();
        for function in &mut self.functions {
            if let Some(writer) = function.writer.as_deref_mut() {
                writer.values.compact_capacity();
            }
        }
        self.functions.shrink_to_fit();
        Ok(())
    }

    /// Remove completed bindings only when the existing typed recipe can
    /// reconstruct the same value without that binding. No new alias map.
    fn elide_reconstructible_slots(&mut self) {
        struct Without<'a> {
            values: &'a crate::slots::FrameSlots,
            slot: usize,
        }
        impl crate::slots::ReadSlots for Without<'_> {
            fn get(&self, slot: &usize) -> Option<&Value> {
                if *slot == self.slot {
                    None
                } else {
                    self.values.get(slot)
                }
            }
        }
        let ids = self
            .cells
            .iter()
            .filter(|(_, c)| c.completed)
            .map(|(&id, _)| id)
            .collect::<Vec<_>>();
        for id in ids {
            let slots = self.cells[&id].values.owned_slots();
            for slot in slots {
                let c = &self.cells[&id];
                let old = canon(c.values.get(&slot).unwrap(), &self.parents);
                let values = Without {
                    values: &c.values,
                    slot,
                };
                if self
                    .slot_fields(id, c.template, c.parent, &values, slot)
                    .ok()
                    .as_ref()
                    == Some(&old)
                {
                    self.cells.get_mut(&id).unwrap().values.remove(&slot);
                }
            }
        }
    }

    pub fn retained_cell_storage(&self) -> J {
        let (records, positions, outliers) = self.cells.storage_bytes();
        let mut frames = BTreeSet::new();
        let mut decoded = BTreeSet::new();
        let (mut slots, mut facts, mut rows, mut removals) = (0, 0, 0, 0);
        let mut arities = BTreeMap::<usize, usize>::new();
        let mut fact_count = 0;
        for cell in self.cells.values() {
            let (bytes, removed) = cell.values.storage_census(&mut frames);
            slots += bytes;
            removals += removed;
            facts += cell.facts.capacity_bytes();
            fact_count += cell.facts.len();
            *arities.entry(cell.facts.len()).or_default() += 1;
            for fact in cell.facts.values() {
                if let Some((_, fields)) = &fact.decoded {
                    if decoded.insert(fields.as_ptr() as usize) {
                        rows += std::mem::size_of_val(fields.as_ref())
                            + 2 * std::mem::size_of::<usize>();
                    }
                }
            }
        }
        let function_records = self.functions.capacity() * std::mem::size_of::<Function>();
        let function_rows = self.functions.iter().map(|f| {
            if decoded.insert(f.fields.as_ptr() as usize) {
                std::mem::size_of_val(f.fields.as_ref()) + 2 * std::mem::size_of::<usize>()
            } else { 0 }
        }).sum::<usize>();
        let mut degrees = BTreeMap::<usize, usize>::new();
        for uses in self.uses.values() {
            *degrees.entry(uses.len()).or_default() += 1;
        }
        let uses_header = self.uses.capacity() * std::mem::size_of::<(u64, UseSet)>();
        let uses_heap = self.uses.values().map(UseSet::heap_payload).sum::<usize>();
        let forward = self.dependencies.capacity()
            * std::mem::size_of::<(Dependency, smallvec::SmallVec<[u64; 3]>)>()
            + self
                .dependencies
                .values()
                .filter(|v| v.spilled())
                .map(|v| v.capacity() * 8)
                .sum::<usize>();
        let functions_index = self
            .function_keys
            .iter()
            .map(scalar_keys::FunctionKeys::storage_payload)
            .sum::<usize>();
        let intern = self.intern.capacity()
            * std::mem::size_of::<(u64, crate::tiny_set::TinySet<FactRef>)>();
        let mut member_arrays = self.members.capacity() * std::mem::size_of::<TableRows<u64>>();
        let mut member_tree_entries = 0;
        for members in &self.members {
            match members {
                TableRows::Run { rows, dead, .. } => {
                    member_arrays += rows.capacity() * 8 + dead.capacity() * 8
                }
                TableRows::Tree(t) => member_tree_entries += t.len(),
            }
        }
        let mut writer_slots = 0;
        let mut writer_count = 0;
        for writer in self.functions.iter().filter_map(|f| f.writer.as_deref()) {
            writer_count += 1;
            let (bytes, removed) = writer.values.storage_census(&mut frames);
            writer_slots += bytes;
            removals += removed;
        }
        let writer_records = writer_count * std::mem::size_of::<writer_frames::Writer>();
        let writers = writer_records + writer_slots + self.writer_dir.storage_bytes();
        let index_payload = uses_header + uses_heap + forward + functions_index + intern;
        json!({"scope":"graph-reachable Cell/function record and array capacities, shared owners counted once; NOT total egraph heap",
            "excluded":"allocator padding/control bytes, Value-owned payloads, BTree nodes, sparse ID outlier map, auxiliary caches, ownership backends, executor storage",
            "index_payload_estimate_bytes":index_payload,"reverse_index_header_payload":uses_header,
            "reverse_index_heap_payload":uses_heap,"reverse_degrees":degrees,
            "forward_index_payload":forward,"function_index_payload":functions_index,"constructor_index_header_payload":intern,
            "members_array_bytes":member_arrays,"members_tree_entries":member_tree_entries,
            "union_find":self.parents.storage_payload(),"writer_bytes":writers,"writer_count":writer_count,
            "accounting_note":"HashMap capacities measure entry payload only, not buckets/control allocation; estimates are separate from counted array bytes",
            "parent_links":self.cells.values().filter(|c|c.parent.is_some()).count(),"delegated_cell_frames":self.cells.values().filter(|c| c.symbolic_slots).count(),"explicit_cell_slots":self.cells.values().map(|c|c.values.len()).sum::<usize>(),
            "cell_records_bytes":records,"cell_positions_bytes":positions,"id_outliers":outliers,
            "cell_slot_bytes":slots,"shared_slot_owners":frames.len(),"removal_entries":removals,
            "fact_record_capacity_bytes":facts,"fact_record_live_bytes":fact_count*std::mem::size_of::<(u32,FactState)>(),
            "decoded_row_bytes":rows,"decoded_row_owners":decoded.len(),
            "function_records_bytes":function_records,"function_row_bytes":function_rows,
            "cell_fact_arities":arities,
            "counted_bytes":records+positions+slots+facts+rows+function_records+function_rows+writers+member_arrays})
    }
}

impl Graph {
    /// Destructive diagnostic: bytes released in field order. Shared allocations
    /// are charged to their last owner; this is not a compression operation.
    pub fn release_storage_by_field(
        self,
        live_bytes: impl Fn() -> usize,
        rows: &mut Vec<(&'static str, usize)>,
    ) -> Program {
        assert!(rows.capacity() - rows.len() >= 23);
        macro_rules! release {
            ($field:ident) => {{
                let before = live_bytes();
                drop(self.$field);
                rows.push((stringify!($field), before - live_bytes()));
            }};
        }
        release!(cells);
        release!(functions);
        release!(parents);
        release!(writer_dir);
        release!(local_unions);
        release!(ownership);
        release!(stable_ports);
        release!(repair_ports);
        release!(union_digest);
        release!(members);
        release!(intern);
        release!(function_keys);
        release!(uses);
        release!(dependencies);
        release!(changes);
        release!(anchors);
        release!(dirty);
        release!(dirty_markers);
        release!(dirty_facts);
        release!(parent_users);
        release!(garbage);
        release!(receipt_forwards);
        self.program
    }
}
