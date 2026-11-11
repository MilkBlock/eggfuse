//! Completed Cell query values and requested row evidence. This uses the
//! existing witness projection, never a second graph of maintained facts.
use crate::{
    graph::{Dependency, FactRef},
    slots::Slots,
};

/// Owned execution state shared by query completion, winner selection and RHS.
/// No graph identity is allocated until the ordinary ordered commit path.
#[derive(Debug)]
pub(crate) struct Instance {
    #[cfg(feature = "sparse-cells")]
    pub constructor: super::constructor_prepare::Prepared,
    #[cfg(feature = "view-consumers")]
    pub view_source: Option<usize>,
    // The existing move-only continuation token follows its winning match.
    // Its lifetime remains owned by the source Run, not a second fact graph.
    #[cfg(feature = "iterative-bake")]
    pub direct: Option<crate::stage_spine::DirectOrigin>,
    // Query completion writes the RHS's owned slot storage directly. Winner
    // selection borrows its values; it must not assemble a second binding.
    pub values: Slots,
    // Prepared local prefix, not a committed effect position.
    #[cfg(feature="sparse-cells")]
    pub prepared: usize,
    pub known: QueryFacts,
    pub epoch: u64,
    pub parent: Option<FactRef>,
    pub continuation: Option<(u32, bool)>,
    // Captured inputs do not change between query completion and the Run's
    // worker batch. A failed/missing speculative result must not be retried
    // there; the source RHS remains responsible at its original position.
    #[cfg(feature="sparse-cells")]
    pub preparation_attempted: bool,
    pub compiled: bool,
}
pub(crate) struct InputView<'a> { instance:&'a Instance, inputs:&'a [usize] }
impl serde::Serialize for InputView<'_> {
    fn serialize<S:serde::Serializer>(&self,s:S)->Result<S::Ok,S::Error> {
        s.collect_map(self.inputs.iter().map(|slot|(slot,&self.instance.values[slot])))
    }
}
impl Instance {
    pub(crate) fn input_view<'a>(&'a self,inputs:&'a [usize])->InputView<'a> {InputView{instance:self,inputs}}
    /// Match identity is the source Cell's input projection. Computed RHS
    /// slots remain owned by the same instance but cannot select a different
    /// winner or change the continuation lookup key.
    pub(crate) fn input_values<'a>(&'a self, inputs: &'a [usize]) -> impl Iterator<Item = &'a crate::value::Value> {
        inputs.iter().map(|slot| &self.values[slot])
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn compare_inputs(&self, other: &Self, inputs: &[usize]) -> std::cmp::Ordering {
        // Query completion supplies every input in source slot order. Keep
        // its contiguous comparison when neither instance has added outputs.
        if self.values.len() == inputs.len() && other.values.len() == inputs.len() {
            self.values.cmp(&other.values)
        } else {
            self.input_values(inputs).cmp(other.input_values(inputs))
        }
    }
    pub fn matched(values: Slots, known: QueryFacts, epoch: u64) -> Self {
        Self {
            #[cfg(feature = "sparse-cells")]
            constructor: Default::default(),
            #[cfg(feature = "view-consumers")]
            view_source: None,
            #[cfg(feature = "iterative-bake")]
            direct: None,
            #[cfg(feature="sparse-cells")]
            prepared: 0,
            #[cfg(feature="sparse-cells")]
            preparation_attempted: false,
            values, known, epoch, parent: None, continuation: None, compiled: true,
        }
    }
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

    #[cfg(feature = "sparse-cells")]
    #[test]
    fn prepared_results_do_not_change_match_identity_or_legacy_origin_key() {
        use crate::value::Value;
        use std::cmp::Ordering;
        let inputs = [1, 1000];
        let make = |x| Instance::matched([(1, Value::Int(x)), (1000, Value::Eq(9))].into_iter().collect(),
            QueryFacts::None, 11);
        let query = make(7);
        let mut completed = make(7);
        // An output can lie between sparse input addresses. No contiguous
        // prefix assumption is sufficient for general checked Cell layouts.
        completed.values.insert(15, Value::Int(123));
        completed.values.insert(2000, Value::Eq(91));
        assert_ne!(query.values, completed.values);
        assert_eq!(query.compare_inputs(&completed, &inputs), Ordering::Equal);
        assert_eq!(completed.compare_inputs(&make(8), &inputs), Ordering::Less);
        assert_eq!(query.input_values(&inputs).collect::<Vec<_>>(), completed.input_values(&inputs).collect::<Vec<_>>());
        let address = std::ptr::from_ref(completed.values.get(&15).unwrap());
        let mut candidates = vec![(query, 2), (completed, 5), (make(7), 5)];
        candidates.sort_by(|(a, depth_a), (b, depth_b)| a.compare_inputs(b, &inputs).then_with(|| depth_b.cmp(depth_a)));
        candidates.dedup_by(|(a, _), (b, _)| a.compare_inputs(b, &inputs).is_eq());
        assert_eq!(candidates.len(), 1);
        assert_eq!(candidates[0].1, 5);
        assert_eq!(std::ptr::from_ref(candidates[0].0.values.get(&15).unwrap()), address,
            "stable winner selection keeps the original prepared instance");
    }

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
