//! Execute original Cell instructions. Calls share operand dispatch across
//! ordered merge callbacks, local scalar prefixes and the executing RHS.
use crate::{graph::{Cell, Graph}, program::{Arg, Call, Op, Result}, value::{self, Value}};
use super::Effects;
use smallvec::SmallVec;

type Arguments = SmallVec<[Value; 4]>;

pub(crate) trait CellFrame {
    fn argument(&self, g: &Graph, arg: &Arg) -> Result<Value>;
    fn arguments(&self, g: &Graph, args: &[Arg]) -> Result<Arguments>;
    fn assign(&mut self, g: &mut Graph, slot: usize, value: Value) -> Result<()>;
}

pub(crate) trait CallFrame: CellFrame {
    fn construct(&mut self, g: &mut Graph, op: usize, table: usize, args: &[Arg], dst: usize) -> Result<()>;
    fn read(&mut self, g: &mut Graph, op: usize, table: usize, args: &[Value]) -> Result<Value>;
    fn failed_primitive(&self, name: &str) -> String { format!("RHS primitive failed: {name}") }
}

pub(crate) fn evaluate_call(g: &mut Graph, frame: &mut impl CallFrame,
    op: usize, dst: usize, call: &Call, args: &[Arg]) -> Result<()> {
    if let Call::Table(t) = call && g.program.tables[*t].virtual_fact {
        // The owning RHS can synthesize a new result from its Cell address.
        // Do not force it to write that result back into its sparse bindings.
        return frame.construct(g, op, *t, args, dst);
    }
    let args = frame.arguments(g, args)?;
    let value = match call {
        Call::Table(t) => frame.read(g, op, *t, &args)?,
        Call::Primitive(name, sort) => {
            if name.starts_with("cell-key-") { g.stats.key_operations += 1; }
            value::primitive(name, &args, sort, g.program.key_nodes())?
                .ok_or_else(|| frame.failed_primitive(name))?
        }
    };
    frame.assign(g, dst, value)
}

pub(crate) struct RhsFrame<'a> {
    pub cell: u32,
    pub receipts: &'a mut Effects,
}
impl RhsFrame<'_> {
    /// Execute one source effect. False means a failed Hide stopped the RHS;
    /// effects from earlier instructions remain committed in source order.
    pub fn execute(&mut self, g: &mut Graph, op: usize, instruction: &Op,
        source: Option<usize>) -> Result<bool> {
        match instruction {
            Op::Copy(..) => {} // The common Cell operand reader projects copies lazily.
            Op::Let(dst, call, args) => evaluate_call(g, self, op, *dst, call, args)?,
            Op::Set(table, args, value) => {
                g.set_inner(self.cell, op, *table, args, value, None, self.receipts.slot(op), source)?;
            }
            Op::Union(a, b) => {
                let a = self.argument(g, a)?;
                let b = self.argument(g, b)?;
                g.enqueue_source_union(a, b)?;
            }
            Op::Hide(table, args, delete) => {
                let key = self.arguments(g, args)?;
                return g.hide(*table, &key, *delete);
            }
            Op::Panic => return Err("source panic".into()),
        }
        Ok(true)
    }
}
impl CellFrame for RhsFrame<'_> {
    fn argument(&self, g: &Graph, arg: &Arg) -> Result<Value> { g.argument(self.cell, arg) }
    fn arguments(&self, g: &Graph, args: &[Arg]) -> Result<Arguments> {
        g.inline_arguments(self.cell, args)
    }
    fn assign(&mut self, g: &mut Graph, slot: usize, value: Value) -> Result<()> {
        g.rhs_frame_mut(self.cell).expect("executing Cell").values.insert(slot, value);
        Ok(())
    }
}
impl CallFrame for RhsFrame<'_> {
    fn construct(&mut self, g: &mut Graph, op: usize, table: usize, args: &[Arg], dst: usize) -> Result<()> {
        if let Some(receipt) = self.receipts.slot(op) {
            g.construct_recorded(self.cell, op, table, args, dst, receipt, &mut false)?;
        } else {
            g.construct(self.cell, op, table, args, dst)?;
        }
        Ok(())
    }
    fn read(&mut self, g: &mut Graph, op: usize, table: usize, args: &[Value]) -> Result<Value> {
        let row = g.lookup_canonical(table, args)?.ok_or_else(|| {
            format!("missing function read {}", g.program.tables[table].name)
        })?;
        self.receipts.record(op, row.witness);
        Ok(row.values.last().unwrap().clone())
    }
}

/// Access to an exclusively owned frame before it is installed in the graph.
/// Completion writes actual returned values here. Its CallFrame implementation
/// allows pure calls only; it cannot create/read table facts on its own.
pub(crate) struct LocalCall<'a> {
    pub cell: u32,
    pub frame: &'a mut Cell,
}
impl CellFrame for LocalCall<'_> {
    fn argument(&self, g: &Graph, arg: &Arg) -> Result<Value> {
        g.argument_in(self.cell, self.frame, arg)
    }
    fn arguments(&self, g: &Graph, args: &[Arg]) -> Result<Arguments> {
        g.frame_arguments(self.cell, self.frame, args)
    }
    fn assign(&mut self, _: &mut Graph, slot: usize, value: Value) -> Result<()> {
        self.frame.values.insert(slot, value);
        Ok(())
    }
}
impl CallFrame for LocalCall<'_> {
    fn construct(&mut self, _: &mut Graph, _: usize, _: usize, _: &[Arg], _: usize) -> Result<()> {
        Err("constructor in scalar Cell prefix".into())
    }
    fn read(&mut self, _: &mut Graph, _: usize, _: usize, _: &[Value]) -> Result<Value> {
        Err("table read in scalar Cell prefix".into())
    }
}

pub(crate) struct MergeFrame {
    values: SmallVec<[Value; 4]>,
}
impl MergeFrame {
    pub fn new(old: Value, new: Value, operations: usize) -> Self {
        let mut values = SmallVec::with_capacity(2 + operations);
        values.extend([old, new]);
        Self { values }
    }
    pub fn operand(&self, arg: &Arg) -> Value {
        match arg { Arg::Slot(s) => self.values[*s].clone(), Arg::Literal(v) => v.clone() }
    }
}
impl CellFrame for MergeFrame {
    fn argument(&self, _: &Graph, arg: &Arg) -> Result<Value> { Ok(self.operand(arg)) }
    fn arguments(&self, _: &Graph, args: &[Arg]) -> Result<Arguments> {
        Ok(args.iter().map(|a| self.operand(a)).collect())
    }
    fn assign(&mut self, _: &mut Graph, slot: usize, value: Value) -> Result<()> {
        if slot != self.values.len() { return Err("merge SSA order".into()); }
        self.values.push(value);
        Ok(())
    }
}
impl CallFrame for MergeFrame {
    fn construct(&mut self, g: &mut Graph, _: usize, table: usize, args: &[Arg], dst: usize) -> Result<()> {
        let args = self.arguments(g, args)?;
        g.stats.merge_program_constructs += 1;
        let value = g.dynamic_construct(table, args)?;
        self.assign(g, dst, value)
    }
    fn read(&mut self, g: &mut Graph, _: usize, table: usize, args: &[Value]) -> Result<Value> {
        g.stats.merge_port_reads += 1;
        // The canonical hash directory may still have displaced keys during
        // repair. Preserve the complete visible port and lattice collision fold.
        g.read_merge_port(table, args)
    }
    fn failed_primitive(&self, _: &str) -> String { "merge arithmetic failed".into() }
}
