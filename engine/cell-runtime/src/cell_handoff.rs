//! Apply an actual constructor witness to the original Cell instruction. The
//! same checks and bindings serve a live RHS and an uncommitted closed frame.
use super::{Effects, eval::{CellFrame, RhsCall}};
use crate::{graph::{Cell, Graph, Stats}, program::{Arg, Call, Op, Result},
    result_handoff::Input, slots::Slots, value::Value};
use smallvec::SmallVec;

pub(crate) trait HandoffFrame: CellFrame {
    fn union(&mut self, g: &mut Graph, a: Value, b: Value) -> Result<()>;
}
impl HandoffFrame for RhsCall<'_> {
    fn union(&mut self, g: &mut Graph, a: Value, b: Value) -> Result<()> { g.enqueue_union(a, b) }
}

/// Own only computed slots and deferred effects. Borrow the original matched
/// inputs; a failed preflight must not reserve an ID or enqueue any union.
pub(crate) struct Preflight<'a> {
    pub cell: u32,
    pub frame: Cell,
    pub inputs: &'a Slots,
    pub unions: SmallVec<[(Value, Value); 2]>,
}
impl CellFrame for Preflight<'_> {
    fn argument(&self, g: &Graph, arg: &Arg) -> Result<Value> {
        g.argument_in(self.cell, &self.frame, Some(self.inputs), arg)
    }
    fn arguments(&self, g: &Graph, args: &[Arg]) -> Result<SmallVec<[Value; 4]>> {
        g.frame_arguments(self.cell, &self.frame, Some(self.inputs), args)
    }
    fn assign(&mut self, _: &mut Graph, slot: usize, value: Value) -> Result<()> {
        self.frame.values.insert(slot, value);
        Ok(())
    }
}
impl HandoffFrame for Preflight<'_> {
    fn union(&mut self, _: &mut Graph, a: Value, b: Value) -> Result<()> {
        self.unions.push((a, b));
        Ok(())
    }
}

#[derive(Default)]
pub(crate) struct HandoffCounts { pub lets: u64, pub sets: u64, noop: u64, deep: u64 }
impl HandoffCounts {
    pub fn commit(self, stats: &mut Stats) {
        stats.handoff_lets += self.lets;
        stats.handoff_sets += self.sets;
        stats.handoff_noop_unions += self.noop;
        stats.handoff_deep += self.deep;
    }
}

/// Return None before applying this instruction when its receipt is absent or
/// no longer proves the complete current key. No lookup or second key buffer.
pub(crate) fn complete_handoff(g: &mut Graph, frame: &mut impl HandoffFrame,
    instruction: &Op, input: &Input, counts: &mut HandoffCounts) -> Result<Option<crate::graph::Dependency>> {
    let Some(fact) = input.fact else { return Ok(None); };
    let (table, args) = match instruction {
        Op::Let(_, Call::Table(t), args) | Op::Set(t, args, _) => (*t, args),
        _ => return Err("unexpected instruction in completed block".into()),
    };
    let Some(row) = g.live_handoff(fact, table)? else { return Ok(None); };
    let Some((value, fields)) = row.values.split_last() else { return Ok(None); };
    if fields.len() != args.len() { return Ok(None); }
    for (field, arg) in fields.iter().zip(args) {
        if *field != frame.argument(g, arg)? { return Ok(None); }
    }
    match instruction {
        Op::Let(dst, ..) => {
            frame.assign(g, *dst, value.clone())?;
            counts.lets += 1;
        }
        Op::Set(_, _, arg) => {
            let rhs = frame.argument(g, arg)?;
            if !matches!((value, &rhs), (Value::Eq(_), Value::Eq(_))) {
                return Err("non-equality constructor result".into());
            }
            if input.equal_output && value == &rhs { counts.noop += 1; }
            else { frame.union(g, value.clone(), rhs)?; }
            counts.sets += 1;
        }
        _ => unreachable!(),
    }
    counts.deep += u64::from(input.back > 1);
    Ok(Some(row.witness))
}

/// A live RHS can immediately commit a successful operation's receipt and
/// counters. A closed frame instead commits them only after its entire preflight.
pub(crate) fn apply_handoff(g: &mut Graph, cell: u32, receipts: &mut Effects,
    instruction: &Op, input: &Input) -> Result<bool> {
    let mut counts = HandoffCounts::default();
    g.stats.handoff_attempts += 1;
    if let Some(witness) = complete_handoff(g, &mut RhsCall { cell, receipts }, instruction, input, &mut counts)? {
        receipts.record(input.op, witness);
        counts.commit(&mut g.stats);
        Ok(true)
    } else {
        if input.fact.is_none() { g.stats.handoff_missing += 1; }
        else { g.stats.handoff_stale += 1; }
        Ok(false)
    }
}
