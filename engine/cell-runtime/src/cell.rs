//! Structural access to the existing Cell definition. This module borrows the
//! typed rule and effect template; it owns no second fact graph or instance state.
//! A relation describes an operation's operands, not proof that it has executed,
//! remains visible, or won a mutable merge. Those obligations stay at its use.
use crate::program::{Arg, Call, Op, Program, Result, Rule, Table, Template};
use serde::{Deserialize, Serialize};
use std::{borrow::Cow, collections::BTreeSet};

#[path = "cell_construction.rs"]
pub mod construction;

#[path = "cell_binding.rs"]
mod binding;
pub use binding::{Bindings, Operand, bind_operand, project_rows, unique_projection};
pub(crate) use binding::Bindings as QueryFrame;
pub(crate) use binding::bind_relation;

#[cfg(feature = "iterative-bake")]
#[path = "cell_results.rs"]
mod results;
#[cfg(feature = "iterative-bake")]
pub(crate) use results::{Capture, ResultPort, Results, SlotLayout};

#[path = "cell_query.rs"]
mod query;
#[path = "cell_match.rs"]
mod matched;
pub(crate) use matched::{Matched, QueryFacts};
pub(crate) use query::{Access, Queries, Query, query_order};
pub(crate) use query::{bind_query, query_operand, ScopedStep};
#[path = "cell_links.rs"]
mod links;
pub(crate) use links::QueryLinks;
#[path = "cell_effects.rs"]
mod effects;
pub(crate) use effects::{CompletedEffects, EffectPlan, Effects, SingleEffect};
#[path = "cell_bound.rs"]
mod bound;
pub(crate) use bound::{BoundRhs, BoundValue};
#[path = "cell_routes.rs"]
mod routes;
pub use routes::Routes;
pub(crate) use routes::Dispatch as RouteDispatch;
#[path = "cell_producer.rs"]
mod producer;
pub(crate) use producer::Producer;
#[path = "cell_eval.rs"]
mod eval;
pub(crate) use eval::{LocalCall, MergeFrame, RhsFrame, evaluate_call};
#[path = "cell_symbols.rs"]
mod symbols;
pub use symbols::{Symbols, SymbolObserver};
#[cfg(feature = "iterative-bake")]
pub(crate) use symbols::SymbolKey;
#[cfg(feature = "iterative-bake")]
#[path = "cell_handoff.rs"]
mod handoff;
#[cfg(feature = "iterative-bake")]
pub(crate) use handoff::{HandoffCounts, CompletionFrame, apply_handoff, complete_handoff};
#[cfg(feature = "iterative-bake")]
pub(crate) use eval::CellFrame;
pub(crate) use query::Field;

/// Static selection from the source Cell and its existing alias proofs. This
/// replaces a separate constructor-only flag; it adds no instance state.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
pub(crate) enum Completion {
    #[default]
    Dynamic,
    Constructors,
    #[cfg(feature = "iterative-bake")]
    Matched,
}

/// A position in a Cell definition, never a physical address of its result.
/// Keep the wire representation shared by existing recipe and Bake artifacts.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize, Deserialize)]
pub enum Site {
    Query(usize),
    Effect(usize),
}
impl Site {
    pub fn parse(kind: &str, index: usize) -> Result<Self> {
        match kind {
            "query" => Ok(Self::Query(index)),
            "effect" => Ok(Self::Effect(index)),
            _ => Err("unknown Cell relation source".into()),
        }
    }
    pub fn coordinates(self) -> (&'static str, usize) {
        match self {
            Self::Query(i) => ("query", i),
            Self::Effect(i) => ("effect", i),
        }
    }
}

#[derive(Clone, Copy)]
pub struct Definition<'a> {
    pub rule: &'a Rule,
    pub template: &'a Template,
    tables: &'a [Table],
    aliases: &'a [Option<Arg>],
}
pub struct Relation<'a> {
    pub site: Site,
    pub table: usize,
    pub keys: &'a [Arg],
    pub result: Cow<'a, Arg>,
}
/// A shared projection of a Cell effect used by a later Entry. The operation
/// remains authoritative for its operands; this is not a second runtime fact.
#[derive(Clone, Copy)]
pub(crate) struct Output {
    pub operation: usize,
    pub table: usize,
    pub receipt_source: Option<Site>,
}
impl Output {
    /// Static aliases are skipped by every RHS executor. Read their actual
    /// donor directly, never probe the absent raw alias receipt first. A missing
    /// donor remains missing; this does not prove visibility or current Eq.
    pub(crate) fn receipt<T>(&self, query: impl FnOnce(usize) -> Option<T>,
        effect: impl FnOnce(usize) -> Option<T>) -> Option<T> {
        match self.receipt_source.unwrap_or(Site::Effect(self.operation)) {
            Site::Query(atom) => query(atom),
            Site::Effect(op) => effect(op),
        }
    }
    /// Lay out the completed Cell's retained prefix and transient boundaries.
    /// Exact constructor aliases share an actual query/effect receipt source;
    /// only their last publication can win. Eq values alone are not this proof.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn prepare(outputs: &mut Vec<Self>, retained: impl Fn(usize) -> bool) -> usize {
        if outputs.len() > 1 && outputs.iter().any(|o| retained(o.table) && o.receipt_source.is_some()) {
            outputs.sort_by_key(|o| std::cmp::Reverse(o.operation));
            let mut seen = BTreeSet::new();
            outputs.retain(|o| !retained(o.table)
                || seen.insert((o.table, o.receipt_source.unwrap_or(Site::Effect(o.operation)))));
        }
        // Original operation positions still determine the winning continuation
        // and the merge with boundary publications. No RHS effects are removed.
        outputs.sort_by_key(|o| (!retained(o.table), o.operation));
        outputs.iter().take_while(|o| retained(o.table)).count()
    }
}
impl Relation<'_> {
    pub fn columns(&self) -> impl Iterator<Item = &Arg> {
        self.keys
            .iter()
            .chain(std::iter::once(self.result.as_ref()))
    }
}
impl<'a> Definition<'a> {
    pub(crate) fn completion(&self, _aliases: &[bool]) -> Completion {
        #[cfg(feature = "iterative-bake")]
        if self.closes_with(_aliases, true, |_| false) {
            return Completion::Matched;
        }
        if self.template.ops.iter().all(|op| match op {
            Op::Copy(..) => true,
            Op::Let(_, Call::Table(t), _) => self.tables[*t].virtual_fact && self.tables[*t].constructor,
            _ => false,
        }) { Completion::Constructors } else { Completion::Dynamic }
    }

    /// Every source operation needs either an existing Cell alias proof, an
    /// allowed deferred effect, or a supplied result. The caller still validates
    /// supplied receipts and commits effects only at the original Run boundary.
    #[cfg(feature = "iterative-bake")]
    pub(crate) fn closes_with(&self, aliases: &[bool], unions: bool,
        supplied: impl Fn(usize) -> bool) -> bool {
        self.template.ops.iter().enumerate().all(|(op, instruction)| {
            aliases.get(op) == Some(&true) || matches!(instruction, Op::Copy(..))
                || (unions && matches!(instruction, Op::Union(..))) || supplied(op)
        })
    }

    pub fn new(program: &'a Program, rule: usize) -> Result<Self> {
        let aliases = program.known_results.static_slots.get(rule).map_or(&[][..], Vec::as_slice);
        let rule = program.rules.get(rule).ok_or("Cell rule index")?;
        Ok(Self {
            rule,
            template: &program.templates[rule.template],
            tables: &program.tables,
            aliases,
        })
    }
    /// Bootstrap compilation derives these same proofs before installing Plans.
    /// Borrow that result; do not build a second alias environment for routing.
    pub(crate) fn with_aliases(mut self, aliases: &'a [Option<Arg>]) -> Self {
        self.aliases = aliases;
        self
    }
    /// Exact source values, using Copy and the existing ordered constructor
    /// proof. This never treats a pending union as an established equality.
    pub(crate) fn value(&self, arg: &Arg) -> Arg {
        self.template.resolve_with(arg, self.aliases)
    }
    pub fn relation(&self, site: Site) -> Option<Relation<'a>> {
        let (table, keys, result) = match site {
            Site::Query(i) => {
                let atom = self.rule.query.get(i)?;
                let Call::Table(table) = atom.call else {
                    return None;
                };
                let (result, keys) = atom.args.split_last()?;
                (table, keys, Cow::Borrowed(result))
            }
            Site::Effect(i) => match self.template.ops.get(i)? {
                Op::Let(dst, Call::Table(table), keys) => {
                    (*table, keys.as_slice(), Cow::Owned(Arg::Slot(*dst)))
                }
                Op::Set(table, keys, result) => (*table, keys.as_slice(), Cow::Borrowed(result)),
                _ => return None,
            },
        };
        Some(Relation {
            site,
            table,
            keys,
            result,
        })
    }
    pub fn relations(&self) -> impl Iterator<Item = Relation<'a>> + '_ {
        (0..self.rule.query.len())
            .map(Site::Query)
            .chain((0..self.template.ops.len()).map(Site::Effect))
            .filter_map(|site| self.relation(site))
    }
    /// Receipt-based local projections may use any matched row, a virtual
    /// constructor result, or a write. An ordinary function read is still a
    /// relation, but does not gain publication authority by sharing this API.
    pub fn local_relation(&self, site: Site) -> Option<Relation<'a>> {
        let relation = self.relation(site)?;
        self.local(&relation).then_some(relation)
    }
    fn local(&self, relation: &Relation<'_>) -> bool {
        !matches!(relation.site, Site::Effect(i)
            if !self.tables[relation.table].virtual_fact && matches!(self.template.ops[i], Op::Let(..)))
    }
    pub fn local_relations(&self) -> impl Iterator<Item = Relation<'a>> + '_ {
        self.relations().filter(|r| self.local(r))
    }
    pub fn local_columns(&self, site: Site) -> Result<(usize, Vec<Arg>)> {
        let relation = self
            .local_relation(site)
            .ok_or("Cell site cannot provide a local relation")?;
        Ok((
            relation.table,
            relation
                .columns()
                .map(|a| self.template.resolve_copy(a))
                .collect(),
        ))
    }
    pub(crate) fn outputs(&self, demanded: &BTreeSet<usize>, sources: &[Option<Site>]) -> Vec<Output> {
        let outputs = (0..self.template.ops.len()).filter_map(|operation| {
            let relation = self.relation(Site::Effect(operation))?;
            demanded.contains(&relation.table).then(|| Output {
                operation, table: relation.table,
                receipt_source: sources.get(operation).copied().flatten(),
            })
        }).collect::<Vec<_>>();
        // An ordinary function read can accompany a producing Cell, but alone
        // it does not authorize a continuation, matching the original contract.
        if outputs.iter().any(|o| self.local_relation(Site::Effect(o.operation)).is_some()) {
            outputs
        } else { Vec::new() }
    }
}

fn resolve<'a>(mut arg: &'a Arg, lookup: impl Fn(usize) -> Option<&'a Arg>) -> Arg {
    while let Arg::Slot(slot) = arg {
        let Some(next) = lookup(*slot) else { break };
        arg = next;
    }
    arg.clone()
}
impl Template {
    /// Only SSA Copy definitions are aliases here. Union is visible according
    /// to the original schedule and must not rewrite an earlier query or read.
    pub fn resolve_copy(&self, arg: &Arg) -> Arg {
        self.resolve_with(arg, &[])
    }
    fn resolve_with(&self, arg: &Arg, aliases: &[Option<Arg>]) -> Arg {
        resolve(arg, |slot| {
            aliases.get(slot).and_then(Option::as_ref).or_else(|| match self.defs.get(&slot).and_then(|&op| self.ops.get(op)) {
                Some(Op::Copy(_, from)) => Some(from),
                _ => None,
            })
        })
    }
}
impl Op {
    /// Borrow source operands in call/key order, followed by a Set's value.
    /// Layouts may address these columns without copying the operation.
    pub(crate) fn operand(&self, column: usize) -> Option<&Arg> {
        match self {
            Self::Copy(_, arg) => (column == 0).then_some(arg),
            Self::Union(a, b) => match column { 0 => Some(a), 1 => Some(b), _ => None },
            Self::Let(_, _, args) | Self::Hide(_, args, _) => args.get(column),
            Self::Set(_, args, value) => {
                if column == args.len() { Some(value) } else { args.get(column) }
            }
            Self::Panic => None,
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::{program::Atom, value::Value};
    use std::{collections::BTreeMap, rc::Rc};

    #[cfg(feature = "sparse-cells")]
    #[test]
    fn output_layout_keeps_last_exact_source_and_every_boundary() {
        let mut outputs = vec![
            Output { operation: 0, table: 0, receipt_source: None },
            Output { operation: 1, table: 1, receipt_source: Some(Site::Query(0)) },
            Output { operation: 2, table: 0, receipt_source: Some(Site::Effect(0)) },
            Output { operation: 3, table: 1, receipt_source: Some(Site::Query(0)) },
            Output { operation: 4, table: 0, receipt_source: Some(Site::Query(0)) },
            Output { operation: 5, table: 0, receipt_source: Some(Site::Effect(0)) },
            Output { operation: 6, table: 0, receipt_source: None },
        ];
        for _ in 0..2 {
            assert_eq!(Output::prepare(&mut outputs, |t| t == 0), 3);
            assert_eq!(outputs.iter().map(|o| o.operation).collect::<Vec<_>>(), [4, 5, 6, 1, 3]);
        }
    }

    #[test]
    fn copies_do_not_make_queued_union_visible() {
        let template = Template {
            name: "ordered".into(),
            sorts: vec![],
            parent_columns: BTreeMap::new(),
            defs: BTreeMap::from([(1, 0), (2, 1)]),
            ops: Rc::new(vec![
                Op::Copy(1, Arg::Slot(0)),
                Op::Copy(2, Arg::Slot(1)),
                Op::Union(Arg::Slot(0), Arg::Slot(3)),
            ]),
        };
        assert_eq!(template.resolve_copy(&Arg::Slot(2)), Arg::Slot(0));
        assert_eq!(template.resolve_copy(&Arg::Slot(3)), Arg::Slot(3));
    }

    #[test]
    fn mutable_reads_and_merge_proposals_keep_distinct_authority() {
        let rule = Rule {
            completion: Default::default(),
            template: 0,
            query: Rc::new(vec![Atom {
                call: Call::Table(0),
                args: vec![Arg::Slot(0), Arg::Slot(1)],
            }]),
            inputs: Rc::new(vec![0, 1]),
            seminaive: true,
            direct: Some(0),
        };
        let template = Template {
            name: "mutable".into(),
            sorts: vec![],
            defs: BTreeMap::from([(2, 0)]),
            parent_columns: BTreeMap::new(),
            ops: Rc::new(vec![
                Op::Let(2, Call::Table(0), vec![Arg::Slot(0)]),
                Op::Set(0, vec![Arg::Slot(0)], Arg::Literal(Value::Int(7))),
                Op::Hide(0, vec![Arg::Slot(0)], true),
            ]),
        };
        let tables = vec![Table {
            name: "cost".into(),
            schema: vec![],
            constructor: false,
            virtual_fact: false,
            merge: serde_json::json!({"var":"old"}),
            internal: false,
        }];
        let cell = Definition {
            rule: &rule,
            template: &template,
            tables: &tables,
            aliases: &[],
        };
        assert!(cell.local_relation(Site::Query(0)).is_some());
        assert!(cell.relation(Site::Effect(0)).is_some());
        assert!(cell.local_relation(Site::Effect(0)).is_none());
        // The write exposes the proposed operand, never a fictitious merged result.
        assert_eq!(
            *cell.relation(Site::Effect(1)).unwrap().result,
            Arg::Literal(Value::Int(7))
        );
        assert!(cell.relation(Site::Effect(2)).is_none());
        assert_eq!(
            cell.local_relations().map(|r| r.site).collect::<Vec<_>>(),
            vec![Site::Query(0), Site::Effect(1)]
        );
    }
}

#[cfg(test)]
mod output_receipt_tests {
    use super::{Output, Site};

    #[test]
    fn static_source_reads_only_actual_donor_even_when_missing() {
        let mut output = Output { operation: 9, table: 0, receipt_source: Some(Site::Effect(2)) };
        let receipt = output.receipt::<usize>(|_| panic!("effect donor is not a query"), |op| {
            assert_eq!(op, 2, "never probe skipped operation 9");
            None
        });
        assert_eq!(receipt, None, "a missing donor does not fabricate an output");
        output.receipt_source = Some(Site::Query(3));
        assert_eq!(output.receipt(|atom| { assert_eq!(atom, 3); Some(42) },
            |_| panic!("query alias must not read any effect slot")), Some(42));
        output.receipt_source = None;
        assert_eq!(output.receipt(|_| panic!("ordinary effect has no query donor"),
            |op| { assert_eq!(op, 9); Some(17) }), Some(17));
    }
}
