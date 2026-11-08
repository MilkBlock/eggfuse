//! Shared symbolic port programs. Only copies and unconditional constructor
//! congruence collapse symbols here. An explicit union remains an executable
//! instruction: no later RHS effect is an assumption about an earlier row.
use super::*;

#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub struct PortProgram {
    /// Per live body column, its symbolic signal (non-equality columns are None).
    pub fields: Vec<Vec<Option<usize>>>,
    /// One immutable local instruction list per symbolic equality signal.
    pub signals: Vec<Vec<Step>>,
    /// Recipe result slot -> signal. This is an address, never an equality proof.
    pub native: BTreeMap<usize, usize>,
    pub slots: Vec<Option<usize>>,
    /// Source-ordered union instructions, evaluated only when their RHS runs.
    pub unions: Vec<Option<[Arg; 2]>>,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub struct Step {
    pub op: u32,
    pub columns: Vec<usize>,
}
impl PortProgram {
    pub(super) fn derive(p: &Program, t: &Template, covered: &[bool]) -> Self {
        let mut symbols = super::super::local_union_cells::Symbols::default();
        symbols.parents = (0..t.sorts.len()).collect();
        let mut facts = Vec::new();
        let mut bodies = vec![Vec::new(); t.ops.len()];
        let mut native = Vec::new();
        let mut unions = vec![None; t.ops.len()];
        for (op, instruction) in t.ops.iter().enumerate() {
            match instruction {
                Op::Copy(dst, a) => {
                    let a = symbols.arg(a);
                    symbols.union(*dst, a);
                }
                Op::Union(a, b) => unions[op] = Some([a.clone(), b.clone()]),
                Op::Let(dst, Call::Table(table), args) if covered[*table] => {
                    let mut ports = args.iter().map(|a| symbols.arg(a)).collect::<Vec<_>>();
                    ports.push(*dst);
                    facts.push((op, *table, ports.clone()));
                    bodies[op] = ports
                        .into_iter()
                        .enumerate()
                        .map(|(c, s)| (p.tables[*table].schema[c]["kind"] == "eq").then_some(s))
                        .collect();
                    native.push((*dst, *dst));
                }
                Op::Set(table, args, result) if covered[*table] => {
                    // A Set's result equality can still be pending. Do not
                    // include its result in unconditional symbolic congruence.
                    bodies[op] = args
                        .iter()
                        .chain(std::iter::once(result))
                        .enumerate()
                        .map(|(c, a)| {
                            (p.tables[*table].schema[c]["kind"] == "eq").then(|| symbols.arg(a))
                        })
                        .collect();
                }
                _ => (),
            }
        }
        // Deletion can create a new result for the same constructor key later
        // in this RHS. Reuse the old local-union analysis's lifetime boundary:
        // copies remain identities, but never close constructor witnesses over
        // a visibility mutation. Both incarnations get their own signal.
        if !t
            .ops
            .iter()
            .any(|op| matches!(op, Op::Hide(..) | Op::Panic))
        {
            symbols.close(&facts);
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
            fields: bodies,
            signals,
            unions,
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
pub(super) struct Signal {
    pub component: u32,
    pub symbol: usize,
}
pub(super) struct Binding {
    pub root: u64,
    pub live_ports: usize,
}
