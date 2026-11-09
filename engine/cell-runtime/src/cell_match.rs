//! Completed Cell query values and requested row evidence. This uses the
//! existing witness projection, never a second graph of maintained facts.
use crate::{
    graph::{Dependency, FactRef},
    value::Value,
};

pub(crate) struct Matched {
    pub values: Vec<Value>,
    pub facts: QueryFacts,
    pub epoch: u64,
}

/// Keep a single requested query witness inline.
#[derive(Clone, Debug, Default)]
pub(crate) enum QueryFacts {
    #[cfg(feature = "structural-depth")]
    Tracked(Box<QueryFacts>, Vec<Option<Dependency>>, u8),
    #[default]
    None,
    One(usize, Option<FactRef>),
    All(Vec<Option<FactRef>>),
    // Only enabled for a compiled query continuation demanding mutable rows.
    Ports(Vec<Option<Dependency>>),
}
impl QueryFacts {
    /// Complete the requested witness projection directly from matched Cell
    /// rows. The template may request one fact, all facts or mutable ports;
    /// materializing an intermediate query-width witness packet is unnecessary.
    /// Callers supply the rule's empty demand template, not a previous match.
    pub(crate) fn with_rows(&self, rows: impl IntoIterator<Item = (usize, Dependency)>) -> Self {
        let mut facts = self.clone();
        if !matches!(facts, Self::None) {
            for (atom, witness) in rows {
                facts.record(atom, Some(witness));
            }
        }
        facts
    }

    #[cfg(feature = "structural-depth")]
    pub fn tracked(&self, atom: usize) -> Option<Dependency> {
        match self {
            Self::Tracked(_, rows, _) => rows.get(atom).copied().flatten(),
            _ => self.get(atom).map(Dependency::Fact),
        }
    }
    #[cfg(feature = "structural-depth")]
    pub fn mark(&mut self, depth: u8) {
        if let Self::Tracked(_, _, d) = self {
            *d = depth
        }
    }
    #[cfg(feature = "structural-depth")]
    pub fn depth(&self) -> u8 {
        if let Self::Tracked(_, _, d) = self {
            *d
        } else {
            0
        }
    }
    pub fn record(&mut self, atom: usize, witness: Option<Dependency>) {
        let fact = match witness {
            Some(Dependency::Fact(f)) => Some(f),
            _ => None,
        };
        match self {
            #[cfg(feature = "structural-depth")]
            Self::Tracked(original, rows, _) => {
                original.record(atom, witness);
                rows[atom] = witness;
            }
            Self::One(source, slot) if *source == atom => *slot = fact,
            Self::All(rows) => rows[atom] = fact,
            Self::Ports(rows) => rows[atom] = witness,
            _ => {}
        }
    }
    pub fn get(&self, atom: usize) -> Option<FactRef> {
        match self {
            #[cfg(feature = "structural-depth")]
            Self::Tracked(original, _, _) => original.get(atom),
            Self::One(source, fact) if *source == atom => *fact,
            Self::All(rows) => rows[atom],
            Self::Ports(rows) => match rows[atom] {
                Some(Dependency::Fact(f)) => Some(f),
                _ => None,
            },
            _ => None,
        }
    }
    pub(crate) fn receipt(&self, atom: usize) -> Option<Dependency> {
        match self {
            #[cfg(feature = "structural-depth")]
            Self::Tracked(_, rows, _) => rows[atom],
            Self::Ports(rows) => rows[atom],
            _ => self.get(atom).map(Dependency::Fact),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn demanded_facts_do_not_retain_other_matches_or_mutable_values() {
        let fact = FactRef { cell: 7, op: 2 };
        let rows = [(0, Dependency::Function(9)), (2, Dependency::Fact(fact))];
        for template in [QueryFacts::One(2, None), QueryFacts::All(vec![None; 3])] {
            let matched = template.with_rows(rows);
            assert_eq!(matched.get(2), Some(fact));
            assert_eq!(matched.get(0), None);
            assert_eq!(template.with_rows([]).get(2), None);
        }
        let empty = QueryFacts::None.with_rows(std::iter::from_fn(|| {
            panic!("an unused fact projection must not visit rows")
        }));
        assert!(matches!(empty, QueryFacts::None));
    }

    #[test]
    fn requested_ports_preserve_mutable_row_identity() {
        let witness = Dependency::Function(9);
        let template = QueryFacts::Ports(vec![None; 3]);
        assert_eq!(template.with_rows([(1, witness)]).receipt(1), Some(witness));
        assert_eq!(template.with_rows([]).receipt(1), None);
        #[cfg(feature = "structural-depth")]
        {
            let template = QueryFacts::Tracked(Box::new(QueryFacts::One(1, None)), vec![None; 3], 4);
            let matched = template.with_rows([(1, witness)]);
            assert_eq!(matched.get(1), None);
            assert_eq!(matched.tracked(1), Some(witness));
            assert_eq!(matched.depth(), 4);
        }
    }
}
