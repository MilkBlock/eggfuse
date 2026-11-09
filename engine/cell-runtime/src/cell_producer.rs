//! Transient source of an Entry's witnesses. A published Cell address selects
//! static wiring; only an actual result reference proves where a row resides.
use super::Site;
use crate::{
    graph::{Dependency, Graph, Row, producer::{Context, WitnessMisses}},
    program::Result,
};

pub(crate) struct Producer {
    anchor: Dependency,
    address: Option<(usize, usize)>,
    context: Option<Option<Context>>,
}
impl Producer {
    pub(crate) fn new(anchor: Dependency, published: Option<(usize, usize)>) -> Self {
        Self { anchor, address: published, context: None }
    }
    fn context(&mut self, graph: &Graph, reads: &mut u64) -> Option<Context> {
        *self.context.get_or_insert_with(|| {
            *reads += 1;
            graph.continuation_context(self.anchor)
        })
    }
    pub(crate) fn address(&mut self, graph: &Graph, reads: &mut u64) -> Option<(usize, usize)> {
        if self.address.is_none() {
            self.address = self.context(graph, reads).map(|c| (c.template, c.op));
        }
        self.address
    }
    /// Receipts may point into another Cell. Recover the physical producer only
    /// for an uncovered effect, once per Entry evaluation (including misses).
    /// Neither a stale receipt nor an absent query receipt permits that fallback.
    pub(crate) fn row(&mut self, graph: &Graph, source: Site, receipt: Option<Dependency>,
        table: usize, arity: usize, misses: &mut WitnessMisses,
        context_reads: &mut u64, row_reads: &mut u64) -> Result<Option<Row>> {
        let witness = if let Some(w) = receipt { w }
            else if let Site::Effect(op) = source {
                let Some(c) = self.context(graph, context_reads)
                    .filter(|c| Some((c.template, c.op)) == self.address)
                else { misses.receipt_missing += 1; return Ok(None) };
                Dependency::Fact(graph.context_fact(c, op))
            } else { misses.receipt_missing += 1; return Ok(None) };
        *row_reads += 1;
        let Some(row) = graph.row(witness)? else {
            if matches!(witness, Dependency::Fact(f) if !graph.cells.contains_key(&f.cell)) {
                misses.cell_missing += 1;
            } else { misses.fact_missing += 1; }
            return Ok(None);
        };
        if row.hidden { misses.hidden += 1; return Ok(None); }
        if row.table != table || row.values.len() != arity {
            misses.shape += 1;
            return Ok(None);
        }
        Ok(Some(row))
    }
}
