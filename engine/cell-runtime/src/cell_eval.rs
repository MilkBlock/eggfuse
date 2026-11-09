//! Execute the existing Cell Let instruction. Storage and table capabilities
//! differ during ordered merge callbacks, but operand/call dispatch is shared.
use crate::{graph::{Cell, Graph}, program::{Arg, Call, Result}, value::{self, Value}};
use super::Effects;
use smallvec::SmallVec;

type Arguments = SmallVec<[Value; 4]>;

pub(crate) trait CallFrame {
    fn arguments(&self, g: &Graph, args: &[Arg]) -> Result<Arguments>;
    fn assign(&mut self, g: &mut Graph, slot: usize, value: Value) -> Result<()>;
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

pub(crate) struct RhsCall<'a> {
    pub cell: u32,
    pub receipts: &'a mut Effects,
}
impl CallFrame for RhsCall<'_> {
    fn arguments(&self, g: &Graph, args: &[Arg]) -> Result<Arguments> {
        g.inline_arguments(self.cell, args)
    }
    fn assign(&mut self, g: &mut Graph, slot: usize, value: Value) -> Result<()> {
        g.rhs_frame_mut(self.cell).expect("executing Cell").values.insert(slot, value);
        Ok(())
    }
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

/// A checked pure prefix uses the same Cell frame and call executor before the
/// writer is committed. It has no permission to create/read table facts.
pub(crate) struct LocalCall<'a> {
    pub cell: u32,
    pub frame: &'a mut Cell,
}
impl CallFrame for LocalCall<'_> {
    fn arguments(&self, g: &Graph, args: &[Arg]) -> Result<Arguments> {
        g.frame_arguments(self.cell, self.frame, None, args)
    }
    fn assign(&mut self, _: &mut Graph, slot: usize, value: Value) -> Result<()> {
        self.frame.values.insert(slot, value);
        Ok(())
    }
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
impl CallFrame for MergeFrame {
    fn arguments(&self, _: &Graph, args: &[Arg]) -> Result<Arguments> {
        Ok(args.iter().map(|a| self.operand(a)).collect())
    }
    fn assign(&mut self, _: &mut Graph, slot: usize, value: Value) -> Result<()> {
        if slot != self.values.len() { return Err("merge SSA order".into()); }
        self.values.push(value);
        Ok(())
    }
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
