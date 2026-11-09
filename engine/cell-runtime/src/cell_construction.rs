//! Compile-time result propagation over a Cell's matched inputs and ordered
//! effects. Native source operands and typed SSA operands use the same proof;
//! neither this environment nor its aliases are retained by runtime instances.
use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Known<V, S> {
    pub value: V,
    pub source: S,
}

pub struct Construction<T, V, S> {
    aliases: BTreeMap<V, V>,
    known: BTreeMap<(T, Vec<V>), Known<V, S>>,
}
impl<T, V, S> Default for Construction<T, V, S> {
    fn default() -> Self { Self { aliases: BTreeMap::new(), known: BTreeMap::new() } }
}
impl<T: Ord + Clone, V: Ord + Clone, S: Clone> Construction<T, V, S> {
    /// Copy targets are fresh SSA operands. Source-language shadowing must be
    /// renamed by its frontend before introducing an alias here.
    pub fn copy(&mut self, target: V, source: &V) {
        let source = self.resolve(source);
        if target != source { self.aliases.insert(target, source); }
    }
    pub fn resolve(&self, value: &V) -> V {
        let mut value = value;
        while let Some(next) = self.aliases.get(value) { value = next; }
        value.clone()
    }
    /// Preserve the first witness and its actual result. A later alias must
    /// never replace it with the position of an operation that did not execute.
    pub fn matched(&mut self, table: T, inputs: Vec<V>, value: V, source: S) {
        self.known.entry((table, inputs)).or_insert(Known { value, source });
    }
    /// The host certifies that a fresh construction can execute here. Native
    /// emission may decline it when hoisting would cross an impure operand.
    /// The closure runs only on a miss, in the source effect order.
    pub fn construct(
        &mut self, table: T, inputs: impl IntoIterator<Item = V>,
        fresh: impl FnOnce() -> Option<Known<V, S>>,
    ) -> Option<(Known<V, S>, bool)> {
        let key = (table, inputs.into_iter().map(|value| {
            // Native operands already carry their lexical binding. Move an
            // unaliased operand into the key instead of cloning it again.
            match self.aliases.get(&value) {
                Some(next) => self.resolve(next),
                None => value,
            }
        }).collect());
        match self.known.entry(key) {
            std::collections::btree_map::Entry::Occupied(e) => Some((e.get().clone(), true)),
            std::collections::btree_map::Entry::Vacant(e) => {
                let known = fresh()?;
                e.insert(known.clone());
                Some((known, false))
            }
        }
    }
    pub fn forget(&mut self, table: &T) {
        self.known.retain(|(t, _), _| t != table);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_witness_survives_nested_aliases_and_ordered_invalidation() {
        let mut flow = Construction::default();
        flow.matched(3, vec![0], 1, "query");
        flow.matched(3, vec![0], 9, "later query");
        flow.copy(2, &0);
        let (known, reused) = flow.construct(3, [2], || panic!("known result must not execute")).unwrap();
        assert!(reused);
        assert_eq!(known, Known { value: 1, source: "query" });
        flow.copy(4, &known.value);
        flow.copy(5, &4);
        assert_eq!(flow.resolve(&5), 1);
        flow.forget(&3);
        assert!(flow.construct(3, [0], || None).is_none());
        let (known, reused) = flow.construct(3, [0], || Some(Known { value: 6, source: "effect" })).unwrap();
        assert!(!reused);
        assert_eq!(known.value, 6);
        assert_eq!(flow.construct(3, [2], || None).unwrap().0.source, "effect");
    }
}
