//! Access to the live producer of a committed fact.
use crate::graph::FactStates as _;
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
    pub(super) fn retain_reference(&mut self, f: FactRef) {
        self.retain_cell(f.cell);
    }
    pub(super) fn release_reference(&mut self, f: FactRef) {
        self.release_cell(f.cell);
    }
    pub(super) fn retain_cell(&mut self, cell: u32) {
        *self.parent_users.entry(cell).or_default() += 1;
    }
    pub(super) fn release_cell(&mut self, cell: u32) {
        *self.parent_users.get_mut(&cell).expect("retained Cell") -= 1;
        self.garbage.insert(cell);
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
            self.cells.fact_state(f)?
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
