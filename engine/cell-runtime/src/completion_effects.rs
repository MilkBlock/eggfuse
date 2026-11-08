//! Effects of the independently checked merge bytecode. Constructor calls read
//! their key domain and may create a fact; function calls only read a port.
use super::*;

#[derive(Clone, Debug, Default, Serialize)]
pub struct Merge {
    pub reads: Vec<usize>,
    pub births: Vec<usize>,
    pub opaque: bool,
}
impl Merge {
    pub fn derive(p: &Program, table: usize) -> Self {
        if p.tables[table].constructor || p.tables[table].merge.is_null() {
            return Self::default();
        }
        let Some(code) = p.merge_programs.merges.get(&table) else {
            return Self {
                opaque: true,
                ..Self::default()
            };
        };
        let mut reads = BTreeSet::new();
        let mut births = BTreeSet::new();
        let mut opaque = opaque_literal(&code.result);
        for op in &code.operations {
            if let Op::Let(_, call, args) = op {
                opaque |= args.iter().any(opaque_literal);
                if let Call::Table(t) = call {
                    reads.insert(*t);
                    if p.tables[*t].virtual_fact {
                        births.insert(*t);
                    }
                }
            } else {
                // The bytecode currently admits only Let instructions. Keep
                // an explicit boundary if the compiler grows new operations.
                opaque = true;
            }
        }
        Self {
            reads: reads.into_iter().collect(),
            births: births.into_iter().collect(),
            opaque,
        }
    }
}
