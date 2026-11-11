//! Apply an actual constructor witness to the original Cell instruction. The
//! same checks and bindings serve a live RHS and an uncommitted closed frame.
use super::{Effects, eval::{CellFrame, RhsFrame}};
use crate::{graph::{Graph, Stats}, program::{Call, Op, Result},
    result_handoff::Input, value::Value};

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
pub(crate) fn complete_handoff(g: &mut Graph, frame: &mut impl CellFrame,
    instruction: &Op, input: &Input, counts: &mut HandoffCounts) -> Result<Option<(crate::graph::Dependency,bool)>> {
    let Some(fact) = input.fact else { return Ok(None); };
    let (table, args) = match instruction {
        Op::Let(_, Call::Table(t), args) | Op::Set(t, args, _) => (*t, args),
        _ => return Err("unexpected instruction in completed block".into()),
    };
    let Some((row, original)) = g.live_handoff_origin(fact, table)? else { return Ok(None); };
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
            else { g.enqueue_union(value.clone(), rhs)?; }
            counts.sets += 1;
        }
        _ => unreachable!(),
    }
    counts.deep += u64::from(input.back > 1);
    Ok(Some((row.witness,original)))
}

/// A live RHS can immediately commit a successful operation's receipt and
/// counters. A witnessed prefix commits them at completion or first-miss promotion.
pub(crate) fn apply_handoff(g: &mut Graph, cell: u32, receipts: &mut Effects,
    instruction: &Op, input: &Input) -> Result<bool> {
    let mut counts = HandoffCounts::default();
    g.stats.handoff_attempts += 1;
    if let Some((witness, original)) = complete_handoff(g, &mut RhsFrame { cell, receipts }, instruction, input, &mut counts)? {
        receipts.record_handoff(input.op, witness, input, original, g.program.iterative.tracks_slots());
        counts.commit(&mut g.stats);
        Ok(true)
    } else {
        if input.fact.is_none() { g.stats.handoff_missing += 1; }
        else { g.stats.handoff_stale += 1; }
        Ok(false)
    }
}
