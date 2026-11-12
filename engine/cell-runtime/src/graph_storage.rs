//! Read-only census of graph-owned Cell/function storage, not cumulative writes.
use super::*;
impl Graph {
    pub fn retained_cell_storage(&self) -> J {
        let (records,positions,outliers)=self.cells.storage_bytes();
        let mut frames=BTreeSet::new();
        let mut decoded=BTreeSet::new();
        let (mut slots,mut facts,mut rows,mut removals)=(0,0,0,0);
        let mut arities=BTreeMap::<usize,usize>::new();
        let mut fact_count=0;
        for cell in self.cells.values() {
            let (bytes,removed)=cell.values.storage_census(&mut frames);
            slots+=bytes;removals+=removed;facts+=cell.facts.capacity_bytes();
            fact_count+=cell.facts.len();
            *arities.entry(cell.facts.len()).or_default()+=1;
            for fact in cell.facts.values() {
                if let Some((_,fields))=&fact.decoded {
                    if decoded.insert(fields.as_ptr() as usize) {
                        rows+=std::mem::size_of_val(fields.as_ref())+2*std::mem::size_of::<usize>();
                    }
                }
            }
        }
        for fields in self.function_decoded.iter().flatten() {
            if decoded.insert(fields.as_ptr() as usize) {
                rows+=std::mem::size_of_val(fields.as_ref())+2*std::mem::size_of::<usize>();
            }
        }
        let function_records=self.functions.capacity()*std::mem::size_of::<Function>();
        let function_keys=self.functions.iter().map(|f|f.key.capacity()*std::mem::size_of::<Value>()).sum::<usize>();
        let decoded_directory=self.function_decoded.capacity()*std::mem::size_of::<Option<RowFields>>();
        json!({"scope":"graph-reachable Cell/function record and array capacities, shared owners counted once; NOT total egraph heap",
            "excluded":"allocator padding, Value-owned payloads, graph indexes/union-find, removal BTree nodes, sparse ID outlier map, function writers, ownership backends, executor storage",
            "cell_records_bytes":records,"cell_positions_bytes":positions,"id_outliers":outliers,
            "cell_slot_bytes":slots,"shared_slot_owners":frames.len(),"removal_entries":removals,
            "fact_record_capacity_bytes":facts,"fact_record_live_bytes":fact_count*std::mem::size_of::<(u32,FactState)>(),
            "decoded_row_bytes":rows,"decoded_row_owners":decoded.len(),
            "function_records_bytes":function_records,"function_key_array_bytes":function_keys,
            "function_decoded_directory_bytes":decoded_directory,"cell_fact_arities":arities,
            "counted_bytes":records+positions+slots+facts+rows+function_records+function_keys+decoded_directory})
    }
}
