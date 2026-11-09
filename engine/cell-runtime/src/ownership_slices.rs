//! Shared symbolic port programs. Only copies and unconditional constructor
//! congruence collapse symbols here. An explicit union remains an executable
//! instruction: no later RHS effect is an assumption about an earlier row.
use super::*;

#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub struct PortProgram {
    /// Cached once per shared wiring, rather than once per source marker.
    #[serde(skip)]
    pub(super) active: bool,
    /// Per live body column, its symbolic signal (non-equality columns are None).
    pub fields: Vec<Vec<Option<usize>>>,
    /// One immutable local instruction list per symbolic equality signal.
    pub signals: Vec<Vec<Step>>,
    /// Recipe result slot -> signal. This is an address, never an equality proof.
    pub native: BTreeMap<usize, usize>,
    pub slots: Vec<Option<usize>>,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub struct Step {
    pub op: u32,
    pub columns: Vec<usize>,
}
impl PortProgram {
    pub fn active(&self) -> bool { self.active }
    pub fn covers(&self, op: usize) -> bool { !self.fields[op].is_empty() }
    pub(super) fn derive(p: &Program, t: &Template, covered: &[bool]) -> Self {
        let mut symbols = crate::cell::Symbols::with_slots(t.sorts.len());
        let mut bodies = vec![Vec::new(); t.ops.len()];
        let mut native = Vec::new();
        let facts = symbols.source_constructors(t, |table| covered[table], |symbols, op, instruction| {
            if let Op::Set(table, args, result) = instruction && covered[*table] {
                // A Set's result equality can still be pending. Record its
                // incidences, but never use it as unconditional congruence.
                bodies[op] = args.iter().chain(std::iter::once(result)).enumerate()
                    .map(|(c, arg)| (p.tables[*table].schema[c]["kind"] == "eq")
                        .then(|| symbols.arg(arg, |i| i)))
                    .collect();
            }
        });
        // Deletion can create a new result for the same constructor key later
        // in this RHS. Reuse the old local-union analysis's lifetime boundary:
        // copies remain identities, but never close constructor witnesses over
        // a visibility mutation. Both incarnations get their own signal.
        if !t
            .ops
            .iter()
            .any(|op| matches!(op, Op::Hide(..) | Op::Panic))
        {
            symbols.close_constructors(facts.iter().map(|(_, table, ports)| (*table, &ports[..ports.len() - 1], *ports.last().unwrap())));
        }
        // Project each constructor once, after closure; the previous compiler
        // copied its complete port vector into a second body representation.
        for (op, table, ports) in facts {
            let dst = *ports.last().unwrap();
            native.push((dst, dst));
            bodies[op] = ports.into_iter().enumerate()
                .map(|(col, symbol)| (p.tables[table].schema[col]["kind"] == "eq").then_some(symbol))
                .collect();
        }
        let mut names = BTreeMap::new();
        for body in &mut bodies {
            for s in body.iter_mut().flatten() {
                let next = names.len();
                *s = *names.entry(symbols.root(*s)).or_insert(next);
            }
        }
        let mut signals = vec![Vec::new(); names.len()];
        for (op, body) in bodies.iter().enumerate() {
            let mut groups = BTreeMap::<usize, Vec<usize>>::new();
            for (column, &symbol) in body.iter().enumerate() {
                if let Some(symbol) = symbol {
                    groups.entry(symbol).or_default().push(column);
                }
            }
            for (symbol, columns) in groups {
                signals[symbol].push(Step {
                    op: op as u32,
                    columns,
                });
            }
        }
        Self {
            active: bodies.iter().any(|fields| !fields.is_empty()),
            fields: bodies,
            signals,
            native: native
                .into_iter()
                .map(|(slot, symbol)| (slot, names[&symbols.root(symbol)]))
                .collect(),
            slots: (0..t.sorts.len())
                .map(|slot| names.get(&symbols.root(slot)).copied())
                .collect(),
        }
    }
}

/// One binding per composed symbol, independent of its cross-frame use count.
/// Checked Entry substitutions share symbols within a component. Foreign inputs
/// and escaped aliases retain canonical-root boundary entries.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub(in crate::graph) struct Signal {
    /// Immutable possible-use class, derived from the origin's shared code.
    /// Class-first order permits skipping an incompatible tree range.
    pub class: u32,
    pub component: u32,
    pub symbol: usize,
}
