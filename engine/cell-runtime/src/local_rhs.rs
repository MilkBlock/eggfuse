//! Compile a chain of virtual constructor reads with an optional terminal Set.
//! The ordinary graph owns every new fact. Existing results can live in the
//! current RHS frame until a miss needs that frame as its physical owner.
use crate::{known_results::Plans, program::*};
use serde::Serialize;
use std::rc::Rc;
#[derive(Clone, Debug)]
pub(crate) struct Step {
    pub op: usize,
    pub skip_before: u64,
}
#[derive(Clone, Debug)]
pub(crate) struct Block {
    pub steps: Vec<Step>,
    pub trailing_aliases: u64,
    pub intermediate_ops: Vec<usize>,
}
pub(crate) fn derive(p: &Program, known: &Plans) -> Vec<Option<Rc<Block>>> {
    p.rules
        .iter()
        .enumerate()
        .map(|(r, rule)| {
            let mut steps = vec![];
            let mut skipped = 0;
            let mut terminal = false;
            let mut origins = std::collections::BTreeMap::new();
            let mut consumed = std::collections::BTreeSet::new();
            for (op, ins) in p.templates[rule.template].ops.iter().enumerate() {
                if known.static_skip[r][op] {
                    if let Op::Let(dst, ..) = ins {
                        if let Some(Arg::Slot(source)) = &known.static_slots[r][*dst]
                            && let Some(&prior) = origins.get(source)
                        {
                            origins.insert(*dst, prior);
                        }
                    }
                    skipped += 1;
                    continue;
                }
                if let Op::Copy(dst, a) = ins {
                    if let Arg::Slot(s) = a
                        && let Some(&prior) = origins.get(s)
                    {
                        origins.insert(*dst, prior);
                    }
                    continue;
                }
                if terminal {
                    return None;
                }
                let (t, key, set_value) = match ins {
                    Op::Let(_, Call::Table(t), key) => (*t, key, None),
                    Op::Set(t, key, v) => {
                        terminal = true;
                        (*t, key, Some(v))
                    }
                    _ => return None,
                };
                if !p.tables[t].constructor || !p.tables[t].virtual_fact {
                    return None;
                }
                for a in key.iter().chain(set_value) {
                    if let Arg::Slot(s) = a
                        && let Some(&prior) = origins.get(s)
                    {
                        consumed.insert(prior);
                    }
                }
                if let Op::Let(dst, ..) = ins {
                    origins.insert(*dst, op);
                }
                steps.push(Step {
                    op,
                    skip_before: std::mem::take(&mut skipped),
                });
            }
            (!steps.is_empty()).then(|| {
                Rc::new(Block {
                    steps,
                    trailing_aliases: skipped,
                    intermediate_ops: consumed.into_iter().collect(),
                })
            })
        })
        .collect()
}

/// Compatibility artifact only: operands always come from the source Cell.
/// The runtime retains selection/skip metadata, not another effect program.
pub(crate) fn wire(p: &Program, blocks: &[Option<Rc<Block>>]) -> serde_json::Value {
    use serde_json::{Value as J, json};
    J::Array(blocks.iter().enumerate().map(|(rid, block)| {
        let Some(block) = block else { return J::Null };
        let ops = &p.templates[p.rules[rid].template].ops;
        let steps = block.steps.iter().map(|step| {
            let (table, key, result) = match &ops[step.op] {
                Op::Let(dst, Call::Table(t), args) => (*t, args, json!({"Let":dst})),
                Op::Set(t, args, value) => (*t, args, json!({"Set":value})),
                _ => unreachable!("validated local Cell operation"),
            };
            json!({"op":step.op,"table":table,"key":key,"result":result,"skip_before":step.skip_before})
        }).collect::<Vec<_>>();
        json!({"steps":steps,"trailing_aliases":block.trailing_aliases,"intermediate_ops":block.intermediate_ops})
    }).collect())
}
#[derive(Default, Serialize)]
pub(crate) struct Counts {
    pub enter: u64,
    pub local_complete: u64,
    pub promoted: u64,
    pub block_local_intermediates: u64,
    pub local_let_results: u64,
    pub prefix_lets_on_promotion: u64,
    pub no_op_unions: u64,
    pub ordered_unions: u64,
}

impl Program {
    /// Portable admission key. All argument wiring and effect legality are
    /// derived again from the target rule before the hint can select it.
    pub fn rhs_operator_shape(&self, rule: usize) -> Option<Vec<[String; 2]>> {
        Some(
            self.local_rhs
                .get(rule)?
                .as_ref()?
                .steps
                .iter()
                .map(|s| {
                    let (kind, table) = match &self.templates[self.rules[rule].template].ops[s.op] {
                        Op::Let(_, Call::Table(t), _) => ("Let", *t),
                        Op::Set(t, ..) => ("Set", *t),
                        _ => unreachable!("validated local Cell operation"),
                    };
                    [
                        kind.into(),
                        self.tables[table].name.clone(),
                    ]
                })
                .collect(),
        )
    }
}
