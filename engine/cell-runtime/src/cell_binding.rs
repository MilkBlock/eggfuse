//! Bind a Cell operand in the caller's existing frame. Static source proofs,
//! typed projections and runtime queries differ in their equality evidence,
//! not in the meaning of a literal, an unbound slot or a repeated slot.
use crate::value::Value;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Operand<L, S> {
    Slot(S),
    Literal(L),
}

pub trait Bindings<S = usize, V = Value> {
    fn slot(&self, slot: S) -> Option<&V>;
    /// Called only after the shared binder proves the slot is unbound.
    fn bind_slot(&mut self, slot: S, value: V);
}
impl<S: Ord, V> Bindings<S, V> for BTreeMap<S, V> {
    #[inline]
    fn slot(&self, slot: S) -> Option<&V> { self.get(&slot) }
    #[inline]
    fn bind_slot(&mut self, slot: S, value: V) { self.insert(slot, value); }
}

/// A failed field leaves bindings unchanged. The caller owns rollback of
/// earlier successful fields when a whole candidate is rejected. Equality
/// callbacks must use evidence valid at the caller's current source boundary.
#[inline]
pub fn bind_operand<L, S: Copy, V: Clone, F: Bindings<S, V> + ?Sized>(
    operand: &Operand<L, S>, value: &V, frame: &mut F,
    equal: impl FnOnce(&V, &V) -> bool, literal: impl FnOnce(&L, &V) -> bool,
) -> bool {
    match operand {
        Operand::Literal(expected) => literal(expected, value),
        Operand::Slot(slot) => match frame.slot(*slot) {
            Some(old) => equal(old, value),
            None => { frame.bind_slot(*slot, value.clone()); true }
        },
    }
}

/// Compile or verify a producer-local projection from the authoritative typed
/// query. Structural equality here does not anticipate a future runtime union.
pub(crate) fn bind_relation(
    atom: &crate::program::Atom, table: usize, columns: &[crate::program::Arg],
    mapping: &mut BTreeMap<usize, crate::program::Arg>,
) -> crate::program::Result<()> {
    use crate::program::{Arg, Call};
    if !matches!(atom.call, Call::Table(t) if t == table) || atom.args.len() != columns.len() {
        return Err("continuation operator/arity differs".into());
    }
    for (to, from) in atom.args.iter().zip(columns) {
        if !bind_operand(to, from, mapping, PartialEq::eq,
            |literal, value| matches!(value, Arg::Literal(v) if v == literal)) {
            return Err(match to {
                Arg::Slot(_) => "continuation relative binding differs",
                Arg::Literal(_) => "continuation literal differs",
            }.into());
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_and_typed_proofs_keep_first_bindings_and_check_literals() {
        let mut frame = BTreeMap::new();
        // Two distinct source spellings with a proven common value. Retain
        // the first witness for emission rather than replacing it by its alias.
        let same = |a: &usize, b: &usize| a / 2 == b / 2;
        let x = Operand::<usize, _>::Slot("x");
        assert!(bind_operand(&x, &2, &mut frame, same, same));
        assert!(bind_operand(&x, &3, &mut frame, same, same));
        assert!(!bind_operand(&x, &4, &mut frame, same, same));
        assert_eq!(frame["x"], 2);
        assert!(!bind_operand(&Operand::Literal(4), &3, &mut frame, same, same));
        assert_eq!(frame.len(), 1);

        let mut projection = BTreeMap::new();
        let slot = Operand::Slot(0);
        let literal = |a: &i64, b: &Operand<i64, usize>| matches!(b, Operand::Literal(v) if v == a);
        assert!(bind_operand(&slot, &Operand::Slot(7), &mut projection, PartialEq::eq, literal));
        assert!(!bind_operand(&slot, &Operand::Slot(8), &mut projection, PartialEq::eq, literal));
        assert!(!bind_operand(&Operand::Literal(7), &Operand::Slot(7), &mut projection, PartialEq::eq, literal));
        assert!(bind_operand(&Operand::Literal(7), &Operand::Literal(7), &mut projection, PartialEq::eq, literal));
    }
}
