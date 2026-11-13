//! Move a rule's existing worker result arrays through the coordinator without
//! reopening each Cell instance. Origins are existing end/position spans.
use super::*;

type Ordered = ((usize, usize), Binding);
type Origins = SmallVec<[(usize, usize); 4]>;

enum Piece {
    Ordered(Vec<Ordered>),
    Range(Vec<(usize, Binding)>, Origins),
}
enum Storage {
    Ordered(Vec<Ordered>),
    Fragments(Vec<Piece>),
}
pub(crate) struct Answers {
    storage: Storage,
}
impl Default for Answers {
    fn default() -> Self {
        Self {
            storage: Storage::Ordered(Vec::new()),
        }
    }
}
#[derive(Default)]
pub(super) struct Gather {
    pub range_rows: u64,
    pub ordered_rows: u64,
    pub pieces: u64,
    pub header_capacity_bytes: u64,
    pub ordered_capacity_bytes: u64,
}
impl Piece {
    fn len(&self) -> usize {
        match self {
            Self::Ordered(rows) => rows.len(),
            Self::Range(rows, _) => rows.len(),
        }
    }
}
impl Answers {
    pub(crate) fn is_empty(&self) -> bool {
        match &self.storage {
            Storage::Ordered(rows) => rows.is_empty(),
            Storage::Fragments(pieces) => pieces.is_empty(),
        }
    }
    pub(crate) fn len(&self) -> usize {
        match &self.storage {
            Storage::Ordered(rows) => rows.len(),
            Storage::Fragments(pieces) => pieces.iter().map(Piece::len).sum(),
        }
    }
    /// The scheduler dispatches a rule's accumulated results, not one array.
    /// Once a rule qualifies, later fragments cannot make its task smaller.
    pub(crate) fn reaches_grain(&self, incoming: usize, grain: usize) -> bool {
        match &self.storage {
            Storage::Ordered(rows) => rows.len() + incoming >= grain,
            Storage::Fragments(_) => true,
        }
    }
    pub(crate) fn push(&mut self, row: Ordered) {
        match &mut self.storage {
            Storage::Ordered(rows) => rows.push(row),
            Storage::Fragments(pieces) => {
                if let Some(Piece::Ordered(rows)) = pieces.last_mut() {
                    rows.push(row);
                } else {
                    pieces.push(Piece::Ordered(vec![row]));
                }
            }
        }
    }
    pub(crate) fn range(&mut self, rows: Vec<(usize, Binding)>, origins: Origins) {
        if rows.is_empty() {
            return;
        }
        debug_assert_eq!(origins.last().map(|p| p.0), Some(rows.len()));
        let piece = Piece::Range(rows, origins);
        match &mut self.storage {
            Storage::Fragments(pieces) => pieces.push(piece),
            Storage::Ordered(rows) => {
                let mut pieces = Vec::with_capacity(2);
                if !rows.is_empty() {
                    pieces.push(Piece::Ordered(std::mem::take(rows)));
                }
                pieces.push(piece);
                self.storage = Storage::Fragments(pieces);
            }
        }
    }
    /// Called by the rule's finishing worker. Preserve arrival order between
    /// pieces as well as stable ties within one expansion. Serial answers are
    /// appended afterward by the existing source-ordered merge.
    pub(super) fn gather(self) -> (Vec<Ordered>, Gather) {
        match self.storage {
            Storage::Ordered(rows) => (rows, Gather::default()),
            Storage::Fragments(pieces) => {
                let mut work = Gather {
                    pieces: pieces.len() as u64,
                    header_capacity_bytes: (pieces.capacity() * std::mem::size_of::<Piece>())
                        as u64,
                    ..Default::default()
                };
                let mut out = Vec::with_capacity(pieces.iter().map(Piece::len).sum());
                for piece in pieces {
                    match piece {
                        Piece::Ordered(mut rows) => {
                            work.ordered_rows += rows.len() as u64;
                            work.ordered_capacity_bytes +=
                                (rows.capacity() * std::mem::size_of::<Ordered>()) as u64;
                            out.append(&mut rows);
                        }
                        Piece::Range(rows, origins) => {
                            work.range_rows += rows.len() as u64;
                            let mut origins = origins.into_iter();
                            let mut origin = origins.next().expect("nonempty result origins");
                            for (at, (source, answer)) in rows.into_iter().enumerate() {
                                while at >= origin.0 {
                                    origin = origins.next().expect("complete result origins");
                                }
                                out.push(((origin.1, source), answer));
                            }
                        }
                    }
                }
                (out, work)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn binding(epoch: u64) -> Binding {
        Binding::matched(
            [(0, Value::Int(1))].into_iter().collect(),
            QueryFacts::None,
            epoch,
        )
    }
    #[test]
    fn whole_result_array_keeps_its_storage_and_interleaved_source_ties() {
        let rows = vec![(7, binding(11)), (7, binding(12)), (8, binding(13))];
        let pointer = rows.as_ptr();
        let mut answers = Answers::default();
        answers.push(((0, 7), binding(10)));
        answers.range(rows, smallvec::smallvec![(2, 0), (3, 1)]);
        answers.push(((0, 7), binding(14)));
        answers.range(vec![(7, binding(15))], smallvec::smallvec![(1, 0)]);
        let Storage::Fragments(pieces) = &answers.storage else {
            panic!("fragment storage")
        };
        let Piece::Range(rows, _) = &pieces[1] else {
            panic!("original worker array")
        };
        assert_eq!(
            rows.as_ptr(),
            pointer,
            "coordinator transfers the original array"
        );
        assert_eq!(answers.len(), 6);
        let (mut rows, work) = answers.gather();
        assert_eq!(
            rows.iter()
                .map(|(order, b)| (*order, b.epoch))
                .collect::<Vec<_>>(),
            vec![
                ((0, 7), 10),
                ((0, 7), 11),
                ((0, 7), 12),
                ((1, 8), 13),
                ((0, 7), 14),
                ((0, 7), 15)
            ]
        );
        assert_eq!((work.range_rows, work.ordered_rows, work.pieces), (4, 2, 4));
        rows.sort_by_key(|(order, _)| *order);
        assert_eq!(
            rows.iter().map(|(_, b)| b.epoch).collect::<Vec<_>>(),
            [10, 11, 12, 14, 15, 13]
        );
    }
    #[test]
    fn ordinary_answers_keep_the_existing_buffer() {
        let mut answers = Answers::default();
        assert!(answers.is_empty());
        assert!(!answers.reaches_grain(1, 2));
        answers.range(Vec::new(), SmallVec::new());
        answers.push(((2, 3), binding(9)));
        assert!(answers.reaches_grain(1, 2));
        let Storage::Ordered(rows) = &answers.storage else {
            panic!("ordinary path")
        };
        let pointer = rows.as_ptr();
        let (rows, work) = answers.gather();
        assert_eq!(pointer, rows.as_ptr());
        assert_eq!(work.pieces, 0);
    }
}
