//! A source-Run borrow of authoritative function slots and Cell fields.
//! It owns no rows, bindings, indexes, snapshots or invalidation state.
use super::*;
pub(crate) use cell_ownership::query_read::{Scratch, Work};

pub(crate) struct QueryReads<'a> {
    keys: &'a [scalar_keys::FunctionKeys],
    functions: &'a [Function],
    constructors: Option<Constructors<'a>>,
    tables: &'a [Table],
    pub parents: &'a Parents,
}
enum Constructors<'a> {
    Canonical(Canonical<'a>),
    Ports(cell_ownership::query_read::Read<'a>),
}
struct Canonical<'a> {
    cells: &'a arena::Cells,
    intern: &'a HashMap<u64, crate::tiny_set::TinySet<FactRef>>,
    members: &'a [TableRows<u64>],
    hash_mask: u64,
}
impl Graph {
    pub(crate) fn query_reads(&self, tables: &[usize], checks: &mut u64) -> Option<QueryReads<'_>> {
        // Birth installs decoded fields; canonical repair replaces them or
        // retires the fact before this borrow. Only stable storage may omit
        // them at a settled boundary, and retains its existing coverage proof.
        let canonical = self.stable_ports.is_none();
        if !self.settled() || tables.iter().any(|&t| {
            *checks += 1;
            self.units.owned[t] || (self.program.tables[t].virtual_fact && !canonical && !self.constructor_query_table(t))
        }) {
            return None;
        }
        let constructors = if canonical {
            Some(Constructors::Canonical(Canonical { cells: &self.cells, intern: &self.intern,
                members: &self.members, hash_mask: self.constructor_hash_mask() }))
        } else { self.constructor_query_reader().map(Constructors::Ports) };
        Some(QueryReads { keys: &self.function_keys, functions: &self.functions, parents: &self.parents,
            constructors, tables: &self.program.tables })
    }
}
impl QueryReads<'_> {
    pub fn point(&self, table: usize, keys: &[Value], scratch: &mut Scratch, work: &mut Work)
        -> Result<Option<(Value, u64, Dependency)>> {
        if self.tables[table].virtual_fact {
            return match self.constructors.as_ref().ok_or("constructor query lacks complete coverage")? {
                Constructors::Canonical(read) => read.point(table, keys, work),
                Constructors::Ports(read) => read.point(table, keys, scratch, work),
            };
        }
        let Some(&index) = self.keys[table].get(keys) else { return Ok(None) };
        let Some(f) = self.functions.get(index).filter(|f| f.live && f.table == table) else { return Ok(None) };
        Ok(Some((canon(&f.value, self.parents), f.epoch, Dependency::Function(index))))
    }
}
impl Canonical<'_> {
    fn candidate(&self, fact: FactRef, table: usize, key: &[Value], work: &mut Work)
        -> Result<Option<(Value, u64, Dependency, bool)>> {
        work.canonical_candidates += 1;
        let Some(state) = self.cells.get(&fact.cell).and_then(|c| c.facts.get(&fact.op)) else {
            return Ok(None);
        };
        let (stored_table, fields) = state.decoded.as_ref()
            .ok_or("settled canonical Cell lacks decoded fields")?;
        if *stored_table != table || fields.len() != key.len() + 1 { return Ok(None); }
        for (actual, expected) in fields.iter().zip(key) {
            work.canonical_field_checks += 1;
            if actual != expected { return Ok(None); }
        }
        work.canonical_result_reads += 1;
        // Borrow the authoritative fields without building a Row or cloning
        // its Arc. Only the result needed by the query becomes owned.
        Ok(Some((fields.last().unwrap().clone(), state.epoch, Dependency::Fact(fact), state.hidden)))
    }
    fn point(&self, table: usize, key: &[Value], work: &mut Work)
        -> Result<Option<(Value, u64, Dependency)>> {
        work.canonical_lookups += 1;
        // Preserve the ordinary nullary lookup's direct member access.
        if key.is_empty() && self.members[table].len() <= 1 {
            let Some(&word) = self.members[table].iter().next() else { return Ok(None); };
            return Ok(self.candidate(FactRef::from_ordered_id(word), table, key, work)?
                .and_then(|(v, epoch, witness, hidden)| (!hidden).then_some((v, epoch, witness))));
        }
        // The existing intern bucket retains FactRef order, including forced
        // hash collisions. Test visibility only after choosing the first exact
        // candidate, like lookup_canonical followed by the query's row check.
        for &fact in self.intern.get(&(hashkey(table, key) & self.hash_mask)).into_iter().flatten() {
            if let Some((v, epoch, witness, hidden)) = self.candidate(fact, table, key, work)? {
                return Ok((!hidden).then_some((v, epoch, witness)));
            }
        }
        Ok(None)
    }
}
