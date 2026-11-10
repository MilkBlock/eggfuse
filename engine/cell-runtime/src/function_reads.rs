//! A source-Run borrow of authoritative function slots and their existing keys.
//! It owns no rows, bindings, indexes, snapshots or invalidation state.
use super::*;

pub(crate) struct FunctionReads<'a> {
    keys: &'a [scalar_keys::FunctionKeys],
    functions: &'a [Function],
    pub parents: &'a Parents,
}
impl Graph {
    pub(crate) fn query_function_reads(&self, tables: &[usize], checks: &mut u64) -> Option<FunctionReads<'_>> {
        if !self.settled() || tables.iter().any(|&t| {
            *checks += 1;
            self.program.tables[t].virtual_fact || self.units.owned[t] || self.port_keys_enabled(t)
        }) {
            return None;
        }
        Some(FunctionReads { keys: &self.function_keys, functions: &self.functions, parents: &self.parents })
    }
}
impl FunctionReads<'_> {
    pub fn point(&self, table: usize, keys: &[Value]) -> Option<(Value, u64, Dependency)> {
        let &index = self.keys[table].get(keys)?;
        let f = self.functions.get(index).filter(|f| f.live && f.table == table)?;
        Some((canon(&f.value, self.parents), f.epoch, Dependency::Function(index)))
    }
}
