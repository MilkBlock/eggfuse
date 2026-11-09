//! Shared static dispatch from a producer Cell output to a consumer Entry.
//! Dense ranges are bounded by route count; sparse ranges retain exact lookup.
//! There are no instance subscriptions or additional retained witness values.
use crate::{multistage::Continuation, program::Program};
use serde::{Deserialize, Serialize};
use std::{collections::HashMap, rc::Rc};

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub(crate) enum Dispatch {
    #[default]
    Empty,
    Dense {
        first: usize,
        slots: Vec<Option<Rc<Continuation>>>,
    },
    Sparse(Vec<(usize, Rc<Continuation>)>),
}
impl Dispatch {
    fn compile(mut routes: Vec<(usize, Rc<Continuation>)>) -> Self {
        if routes.is_empty() {
            return Self::Empty;
        }
        routes.sort_unstable_by_key(|(key, _)| *key);
        let first = routes[0].0;
        let width = routes.last().unwrap().0 - first + 1;
        // At most one empty slot per route. Do not allocate a global
        // producer-by-consumer matrix for a sparse Cell neighborhood.
        if width <= 2 * routes.len() {
            let mut slots = vec![None; width];
            for (key, route) in routes {
                slots[key - first] = Some(route);
            }
            Self::Dense { first, slots }
        } else {
            Self::Sparse(routes)
        }
    }
    /// The counters charge attempted direct probes and exact key comparisons.
    pub(crate) fn lookup(&self, key: usize) -> (Option<&Rc<Continuation>>, u64, u64) {
        match self {
            Self::Empty => (None, 0, 0),
            Self::Dense { first, slots } => {
                let route = key
                    .checked_sub(*first)
                    .and_then(|i| slots.get(i))
                    .and_then(Option::as_ref);
                (route, 1, 0)
            }
            Self::Sparse(routes) => {
                let mut comparisons = 0;
                let found = routes.binary_search_by_key(&key, |(key, _)| {
                    comparisons += 1;
                    *key
                });
                (found.ok().map(|i| &routes[i].1), 0, comparisons)
            }
        }
    }
    fn values(&self) -> impl Iterator<Item = &Rc<Continuation>> {
        let (dense, sparse): (&[_], &[_]) = match self {
            Self::Empty => (&[], &[]),
            Self::Dense { slots, .. } => (slots, &[]),
            Self::Sparse(rows) => (&[], rows),
        };
        dense
            .iter()
            .filter_map(Option::as_ref)
            .chain(sparse.iter().map(|(_, r)| r))
    }
    pub(crate) fn has_prefix(&self) -> bool {
        self.values().any(|r| r.prefix_len != 0)
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Routes {
    offsets: Vec<usize>,
    entries: Vec<Vec<Rc<Dispatch>>>,
}
impl Routes {
    pub(crate) fn compile(
        p: &Program,
        routes: HashMap<(usize, usize, usize, usize), Rc<Continuation>>,
    ) -> Self {
        let mut offsets = vec![0];
        for t in &p.templates {
            offsets.push(offsets.last().unwrap() + t.ops.len());
        }
        let mut entries = p
            .rules
            .iter()
            .map(|r| vec![Vec::new(); r.query.len()])
            .collect::<Vec<_>>();
        for ((template, operation, rule, atom), route) in routes {
            entries[rule][atom].push((offsets[template] + operation, route));
        }
        let empty = Rc::new(Dispatch::Empty);
        Self {
            offsets,
            entries: entries
                .into_iter()
                .map(|row| {
                    row.into_iter()
                        .map(|routes| {
                            if routes.is_empty() {
                                empty.clone()
                            } else {
                                Rc::new(Dispatch::compile(routes))
                            }
                        })
                        .collect()
                })
                .collect(),
        }
    }
    pub(crate) fn source(&self, template: usize, operation: usize) -> Option<usize> {
        let first = *self.offsets.get(template)?;
        if operation < self.offsets.get(template + 1)? - first {
            Some(first + operation)
        } else {
            None
        }
    }
    pub(crate) fn entry(&self, rule: usize, atom: usize) -> Option<&Rc<Dispatch>> {
        self.entries.get(rule)?.get(atom)
    }
    pub fn get(&self, key: &(usize, usize, usize, usize)) -> Option<&Rc<Continuation>> {
        self.lookup(key).0
    }
    pub(crate) fn lookup(
        &self,
        &(template, operation, rule, atom): &(usize, usize, usize, usize),
    ) -> (Option<&Rc<Continuation>>, u64, u64) {
        let Some(source) = self.source(template, operation) else {
            return (None, 0, 0);
        };
        self.entry(rule, atom)
            .map_or((None, 0, 0), |entry| entry.lookup(source))
    }
    pub fn contains_key(&self, key: &(usize, usize, usize, usize)) -> bool {
        self.get(key).is_some()
    }
    pub fn clear(&mut self) {
        *self = Self::default();
    }
    pub(crate) fn values(&self) -> impl Iterator<Item = &Rc<Continuation>> {
        self.entries.iter().flatten().flat_map(|d| d.values())
    }
    pub(crate) fn for_each_mut(&mut self, mut f: impl FnMut(&mut Rc<Continuation>)) {
        for entry in self.entries.iter_mut().flatten() {
            // Skip the shared empty sentinel without copying it.
            if matches!(entry.as_ref(), Dispatch::Empty) {
                continue;
            }
            match Rc::make_mut(entry) {
                Dispatch::Empty => unreachable!(),
                Dispatch::Dense { slots, .. } => {
                    for route in slots.iter_mut().flatten() {
                        f(route);
                    }
                }
                Dispatch::Sparse(rows) => {
                    for (_, route) in rows {
                        f(route);
                    }
                }
            }
        }
    }
    pub(crate) fn report(&self) -> serde_json::Value {
        let (mut direct, mut slots, mut sparse, mut routes, mut bytes) = (0, 0, 0, 0, 0);
        bytes += self.offsets.capacity() * std::mem::size_of::<usize>();
        bytes += self.entries.capacity() * std::mem::size_of::<Vec<Rc<Dispatch>>>();
        for entries in &self.entries {
            bytes += entries.capacity() * std::mem::size_of::<Rc<Dispatch>>();
            for entry in entries {
                match entry.as_ref() {
                    Dispatch::Empty => (),
                    Dispatch::Dense { slots: rows, .. } => {
                        direct += 1;
                        slots += rows.len();
                        routes += rows.iter().filter(|r| r.is_some()).count();
                        bytes += rows.capacity() * std::mem::size_of::<Option<Rc<Continuation>>>();
                    }
                    Dispatch::Sparse(rows) => {
                        sparse += 1;
                        routes += rows.len();
                        bytes += rows.capacity() * std::mem::size_of::<(usize, Rc<Continuation>)>();
                    }
                }
            }
        }
        serde_json::json!({"routes":routes,"direct_entries":direct,"direct_slots":slots,
            "sparse_entries":sparse,"vector_capacity_bytes":bytes,
            "read_index_slots":self.values().map(|r| r.read_positions.len()).sum::<usize>(),
            "read_index_capacity_bytes":self.values().map(|r| r.read_positions.capacity() * std::mem::size_of::<Option<std::num::NonZeroU32>>()).sum::<usize>(),
            "prefix_routes":self.values().filter(|r| r.prefix_len != 0).count(),
            "scope":"static Cell routing; vector capacities exclude Rc allocations and source continuations"})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn route() -> Rc<Continuation> {
        Rc::new(Continuation {
            producer: 0,
            consumer: 0,
            anchor: 0,
            reads: vec![],
            read_positions: vec![],
            prefix_len: 0,
        })
    }
    #[test]
    fn dispatch_distinguishes_holes_and_sparse_sources() {
        for keys in [vec![3, 5], vec![3, 500]] {
            let rows = keys.iter().map(|&key| (key, route())).collect::<Vec<_>>();
            let dispatch = Dispatch::compile(rows.clone());
            for key in [0, 2, 3, 4, 5, 6, 499, 500, 501, usize::MAX] {
                let (found, _, _) = dispatch.lookup(key);
                let expected = rows.iter().find(|(k, _)| *k == key).map(|(_, r)| r);
                assert_eq!(found.map(Rc::as_ptr), expected.map(Rc::as_ptr));
            }
        }
    }
    #[test]
    fn source_bounds_do_not_alias_an_adjacent_template() {
        let routes = Routes {
            offsets: vec![0, 2, 5],
            entries: vec![],
        };
        assert_eq!(routes.source(0, 1), Some(1));
        assert_eq!(routes.source(1, 2), Some(4));
        for address in [(0, 2), (1, 3), (0, usize::MAX), (2, 0), (usize::MAX, 0)] {
            assert_eq!(routes.source(address.0, address.1), None);
        }
    }
}
