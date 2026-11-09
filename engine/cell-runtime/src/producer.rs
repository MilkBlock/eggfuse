//! Access to the live producer of a committed fact.
use super::*;
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct WitnessMisses {
    pub cell_missing: u64,
    pub fact_missing: u64,
    pub receipt_missing: u64,
    pub hidden: u64,
    pub shape: u64,
    pub key: u64,
}
#[derive(Clone, Copy)]
pub struct Context {
    pub completed: bool,
    pub cell: u32,
    pub template: usize,
    pub depth: u32,
    pub op: usize,
}
impl Graph {
    pub(crate) fn context_witness_row(&self, context: Option<Context>,
        source: crate::known_results::Source, receipt: Option<Dependency>,
        table: usize, arity: usize, misses: &mut WitnessMisses, row_reads: &mut u64) -> Result<Option<Row>> {
        let witness = if let Some(w) = receipt { w }
            else if let (Some(c), crate::known_results::Source::Effect(op)) = (context, source) {
                Dependency::Fact(self.context_fact(c, op))
            } else { misses.receipt_missing += 1; return Ok(None) };
        *row_reads += 1;
        let Some(row) = self.row(witness)? else {
            if matches!(witness, Dependency::Fact(f) if !self.cells.contains_key(&f.cell)) {
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
    pub(super) fn retain_reference(&mut self, f: FactRef) {
        *self.parent_users.entry(f.cell).or_default() += 1;
    }
    pub(super) fn release_reference(&mut self, f: FactRef) {
        *self.parent_users.get_mut(&f.cell).expect("retained parent") -= 1;
        self.garbage.insert(f.cell);
    }
    pub fn continuation_context(&self, w: Dependency) -> Option<Context> {
        let actual = self.origin(w)?;
        #[cfg(feature = "sparse-cells")]
        if let Dependency::Function(i) = w
            && let Some(writer) = self.functions[i].writer.as_ref()
        {
            return Some(Context {
                completed: writer.completed,
                cell: actual.cell,
                template: writer.template,
                depth: writer.depth,
                op: actual.op as usize,
            });
        }
        let f = if let Dependency::Fact(f) = w {
            self.cells
                .get(&f.cell)?
                .facts
                .get(&f.op)?
                .entry
                .unwrap_or(f)
        } else {
            actual
        };
        let c = self.cells.get(&f.cell)?;
        Some(Context {
            completed: c.completed,
            cell: f.cell,
            template: c.template,
            depth: c.recipe_depth,
            op: f.op as usize,
        })
    }
    pub fn context_argument(&self, c: Context, a: &Arg) -> Result<Value> {
        self.argument(c.cell, a)
    }
    pub fn context_arguments(&self, c: Context, aa: &[Arg]) -> Result<Vec<Value>> {
        aa.iter().map(|a| self.context_argument(c, a)).collect()
    }
    pub fn context_fact(&self, c: Context, op: usize) -> FactRef {
        FactRef {
            cell: c.cell,
            op: op as u32,
        }
    }
}
