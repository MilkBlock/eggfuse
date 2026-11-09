//! Compile-time equality over Cell operands. Callers supply only facts justified
//! at their current source boundary. No runtime facts or consumer lists live here.
use crate::{program::Arg, value::Value};
use smallvec::SmallVec;
use std::collections::BTreeMap;

/// Optional compiler-index invalidation. Plain local wiring carries no index
/// footprint; a cross-stage donor index observes key reads and displaced roots.
pub(crate) trait SymbolObserver {
    fn key(&mut self, _roots: &[usize]) {}
    fn merged(&mut self, _from: usize, _to: usize) {}
}
impl SymbolObserver for () {}

#[derive(Clone, Default)]
pub(crate) struct Symbols<W = ()> {
    parents: Vec<usize>,
    literals: BTreeMap<Value, usize>,
    pub observer: W,
}
impl Symbols {
    pub fn with_slots(slots: usize) -> Self {
        Self { parents: (0..slots).collect(), ..Self::default() }
    }
}
impl<W: SymbolObserver> Symbols<W> {
    pub fn len(&self) -> usize { self.parents.len() }
    pub fn fresh(&mut self) -> usize {
        let id = self.parents.len();
        self.parents.push(id);
        id
    }
    pub fn root(&self, mut id: usize) -> usize {
        while self.parents[id] != id { id = self.parents[id]; }
        id
    }
    pub fn equal(&mut self, a: usize, b: usize) -> bool {
        let (a, b) = (self.root(a), self.root(b));
        if a == b { return false; }
        let (from, to) = (a.max(b), a.min(b));
        self.observer.merged(from, to);
        self.parents[from] = to;
        true
    }
    pub fn arg(&mut self, arg: &Arg, slot: impl FnOnce(usize) -> usize) -> usize {
        match arg {
            Arg::Slot(id) => slot(*id),
            Arg::Literal(value) => {
                if let Some(&id) = self.literals.get(value) { return id; }
                let id = self.fresh();
                self.literals.insert(value.clone(), id);
                id
            }
        }
    }
    /// Reify a symbol from a single source Cell's slots/literals. Cross-stage
    /// callers retain their own source projection instead of using this method.
    pub fn source_arg(&self, id: usize, slots: usize) -> Arg {
        if id < slots { Arg::Slot(id) }
        else { Arg::Literal(self.literals.iter().find(|(_, i)| **i == id)
            .expect("source literal symbol").0.clone()) }
    }
    /// Borrow constructor keys/results from the caller's surviving facts. The
    /// table operator is part of the key; all parameters must be equal. Explicit
    /// unions take effect only when the caller invokes `equal` at its boundary.
    pub fn close_constructors<'a>(&mut self,
        facts: impl Iterator<Item = (usize, &'a [usize], usize)> + Clone) {
        loop {
            let mut keys = BTreeMap::new();
            let mut changed = false;
            for (table, args, result) in facts.clone() {
                let key = args.iter().map(|&s| self.root(s)).collect::<SmallVec<[usize; 4]>>();
                self.observer.key(&key);
                if let Some(other) = keys.insert((table, key), result) {
                    changed |= self.equal(other, result);
                }
            }
            if !changed { break; }
        }
    }
}
