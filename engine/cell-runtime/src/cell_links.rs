//! Static shared-column wiring of the original Cell query atoms. These links
//! are necessary conditions only; they never certify a match or current Eq.
use crate::program::{Arg, Atom, Call};
use std::collections::BTreeMap;

#[derive(Clone, Debug)]
pub(crate) struct Link {
    pub atom: usize,
    /// (binding slot, follower column, first matching source column).
    /// Keep the lowered slot address so partitioning need not decode Arg again.
    /// Repeated follower occurrences are kept for exact projection semantics.
    pub columns: Vec<(usize, usize, usize)>,
}
impl Link {
    /// One pair per shared slot, preserving the first follower occurrence.
    /// Sieve uses a set of slots; Free Join must keep every column occurrence.
    pub(crate) fn distinct(&self) -> impl Iterator<Item = (usize, usize)> + '_ {
        self.columns.iter().enumerate().filter_map(|(i, &(_, to, from))| {
            (!self.columns[..i].iter().any(|&(_, _, prior)| prior == from)).then_some((to, from))
        })
    }
}

#[derive(Clone, Debug, Default)]
pub(crate) struct QueryLinks(Vec<Vec<Link>>);
impl QueryLinks {
    pub(crate) fn compile(query: &[Atom]) -> Self {
        Self(query.iter().enumerate().map(|(source, driver)| {
            if !matches!(driver.call, Call::Table(_)) { return vec![]; }
            let mut slots = BTreeMap::new();
            for (column, arg) in driver.args.iter().enumerate() {
                if let Arg::Slot(slot) = arg { slots.entry(*slot).or_insert(column); }
            }
            query.iter().enumerate().filter_map(|(atom, follower)| {
                if source == atom || !matches!(follower.call, Call::Table(_)) { return None; }
                let columns = follower.args.iter().enumerate().filter_map(|(to, arg)| {
                    let Arg::Slot(slot) = arg else { return None; };
                    Some((*slot, to, *slots.get(slot)?))
                }).collect::<Vec<_>>();
                (!columns.is_empty()).then_some(Link { atom, columns })
            }).collect()
        }).collect())
    }
    pub(crate) fn from(&self, atom: usize) -> &[Link] { &self.0[atom] }
    pub(crate) fn between(&self, from: usize, to: usize) -> Option<&Link> {
        let links = self.from(from);
        links.binary_search_by_key(&to, |link| link.atom).ok().map(|i| &links[i])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::value::Value;
    #[test]
    fn repeated_columns_and_equal_literals_keep_distinct_roles() {
        let query = [
            Atom { call: Call::Table(0), args: vec![Arg::Slot(9), Arg::Slot(9), Arg::Slot(4), Arg::Literal(Value::Int(1))] },
            Atom { call: Call::Table(1), args: vec![Arg::Slot(4), Arg::Slot(9), Arg::Slot(4), Arg::Literal(Value::Int(1))] },
            Atom { call: Call::Primitive("+".into(), "i64".into()), args: vec![Arg::Slot(9), Arg::Slot(4), Arg::Slot(20)] },
        ];
        let links = QueryLinks::compile(&query);
        assert_eq!(links.from(0).len(), 1);
        assert_eq!(links.between(0, 1).unwrap().columns, [(4, 0, 2), (9, 1, 0), (4, 2, 2)]);
        assert_eq!(links.between(0, 1).unwrap().distinct().collect::<Vec<_>>(), [(0, 2), (1, 0)]);
        assert_eq!(links.between(1, 0).unwrap().columns, [(9, 0, 1), (9, 1, 1), (4, 2, 0)]);
        assert!(links.between(0, 2).is_none());
        assert!(links.from(2).is_empty());
    }
}
