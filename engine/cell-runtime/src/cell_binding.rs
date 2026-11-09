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

/// Project eligible local rows through the same Cell operands. The caller
/// supplies only rows from the selected operator and source boundary. Keep
/// source identity alongside bindings: equal bindings alone need not prove a
/// unique runtime witness. Rejected candidates never modify the input frame.
pub fn project_rows<'a, L: 'a, S: Copy + 'a, V: Clone + 'a,
    F: Bindings<S, V> + Clone + 'a, T: 'a>(
    fields: &'a [Operand<L, S>], base: &'a F,
    rows: impl Iterator<Item = (T, &'a [V])> + 'a,
    equal: impl Fn(&V, &V) -> bool + 'a,
    literal: impl Fn(&L, &V) -> bool + 'a,
) -> impl Iterator<Item = (T, F)> + 'a {
    rows.filter_map(move |(source, row)| {
        if fields.len() != row.len() { return None; }
        let mut frame = base.clone();
        fields.iter().zip(row)
            .all(|(field, value)| bind_operand(field, value, &mut frame, &equal, &literal))
            .then_some((source, frame))
    })
}

/// Keep the first equivalent candidate. Stop at the first distinct one: no
/// later candidate can restore uniqueness in this immutable local proof.
/// The caller chooses binding or source-row identity according to its proof.
pub fn unique_projection<T>(mut candidates: impl Iterator<Item = T>,
    same: impl Fn(&T, &T) -> bool) -> Option<T> {
    let first = candidates.next()?;
    for candidate in candidates {
        if !same(&first, &candidate) { return None; }
    }
    Some(first)
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

    #[test]
    fn projection_uniqueness_preserves_witness_identity_and_first_source() {
        let rows = [vec![2], vec![3], vec![4]];
        let fields = [Operand::<usize, &str>::Literal(2)];
        let base = BTreeMap::new();
        let same = |a: &usize, b: &usize| a / 2 == b / 2;
        let candidates = || project_rows(&fields, &base,
            rows.iter().enumerate().map(|(i, row)| (i, row.as_slice())), same, same);
        let by_binding = unique_projection(candidates(), |a, b| a.1 == b.1).unwrap();
        assert_eq!(by_binding.0, 0);
        assert!(by_binding.1.is_empty());
        assert!(unique_projection(candidates(), |a, b| rows[a.0] == rows[b.0]).is_none());
        assert!(base.is_empty());
        // Duplicate witnesses retain the first source; enumeration stops as
        // soon as an actual ambiguity is proved, without visiting the tail.
        let duplicates = [(0, 2), (1, 2)];
        assert_eq!(unique_projection(duplicates.into_iter(), |a, b| a.1 == b.1), Some((0, 2)));
        let ambiguous = [(0, 2), (1, 3)].into_iter()
            .chain(std::iter::from_fn(|| panic!("ambiguity must stop projection")));
        assert!(unique_projection(ambiguous, |a, b| a.1 == b.1).is_none());
        let wrong_width = [Operand::<usize, &str>::Slot("x"), Operand::Slot("y")];
        assert_eq!(project_rows(&wrong_width, &base,
            rows.iter().map(|row| ((), row.as_slice())), same, same).count(), 0);
    }
}
