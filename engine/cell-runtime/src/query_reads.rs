//! A source-Run borrow of authoritative function slots and constructor domains.
//! It owns no rows, bindings, indexes, snapshots or invalidation state.
use super::*;
pub(crate) use cell_ownership::query_read::{Scratch, Work};

pub(crate) struct QueryReads<'a> {
    keys: &'a [scalar_keys::FunctionKeys],
    functions: &'a [Function],
    constructors: Option<cell_ownership::query_read::Read<'a>>,
    tables: &'a [Table],
    pub parents: &'a Parents,
}
impl Graph {
    pub(crate) fn query_reads(&self, tables: &[usize], checks: &mut u64) -> Option<QueryReads<'_>> {
        if !self.settled() || tables.iter().any(|&t| {
            *checks += 1;
            self.units.owned[t] || (self.program.tables[t].virtual_fact && !self.constructor_query_table(t))
        }) {
            return None;
        }
        Some(QueryReads { keys: &self.function_keys, functions: &self.functions, parents: &self.parents,
            constructors: self.constructor_query_reader(), tables: &self.program.tables })
    }
}
impl QueryReads<'_> {
    pub fn point(&self, table: usize, keys: &[Value], scratch: &mut Scratch, work: &mut Work)
        -> Result<Option<(Value, u64, Dependency)>> {
        if self.tables[table].virtual_fact {
            return self.constructors.as_ref().ok_or("constructor query lacks complete coverage")?
                .point(table, keys, scratch, work);
        }
        let Some(&index) = self.keys[table].get(keys) else { return Ok(None) };
        let Some(f) = self.functions.get(index).filter(|f| f.live && f.table == table) else { return Ok(None) };
        Ok(Some((canon(&f.value, self.parents), f.epoch, Dependency::Function(index))))
    }
}
