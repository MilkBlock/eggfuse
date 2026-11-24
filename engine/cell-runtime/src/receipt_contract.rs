//! Typed named-return layout shared by token history, Bake and graph certificates.
//! The original Recipe instructions remain the executable definitions.
use crate::program::{Arg, Call, Op, Program, Rule};
use serde_json::{Value as J, json};
use std::collections::BTreeMap;

/// Status of one named output, under the requested version. Consult history
/// only after publication and only on a miss in the current visible snapshot.
#[derive(Debug, PartialEq, Eq)]
pub enum PortState<T> {
    Pending,
    Available(T),
    Absent,
    Retired,
}

pub fn port_state<T>(
    published: bool,
    current: Option<T>,
    returned: impl FnOnce() -> bool,
) -> PortState<T> {
    if !published {
        PortState::Pending
    } else if let Some(row) = current {
        PortState::Available(row)
    } else if returned() {
        PortState::Retired
    } else {
        PortState::Absent
    }
}

pub struct Returns {
    pub merge_offsets: BTreeMap<usize, usize>,
    pub tables: BTreeMap<usize, usize>,
}

impl Returns {
    pub fn rule(p: &Program, rid: usize) -> Self {
        let ops = &p.templates[p.rules[rid].template].ops;
        let mut out = Self {
            merge_offsets: BTreeMap::new(),
            tables: BTreeMap::new(),
        };
        let mut next = ops.len();
        for (pc, op) in ops.iter().enumerate() {
            match op {
                Op::Set(table, _, _) | Op::Let(_, Call::Table(table), _) => {
                    out.tables.insert(pc, *table);
                }
                _ => {}
            }
            if let Op::Set(table, _, _) = op
                && let Some(merge) = p.merge_programs.merges.get(table)
            {
                out.merge_offsets.insert(pc, next);
                for (local, target) in merge_returns(p, &merge.operations) {
                    out.tables.insert(next + local, target);
                }
                // Primitive and read operations occupy positions even though
                // MergeFrame only emits a named receipt for construct().
                next += merge.operations.len();
            }
        }
        out
    }
}

fn merge_returns<'a>(p: &'a Program, ops: &'a [Op]) -> impl Iterator<Item = (usize, usize)> + 'a {
    ops.iter().enumerate().filter_map(|(pc, op)| match op {
        Op::Let(_, Call::Table(t), _) if p.tables[*t].virtual_fact => Some((pc, *t)),
        _ => None,
    })
}

// Each field is a column of a *named* input. This is also the type/provenance
// relation used to validate a CCP computation operand, never a row lookup.
fn table_inputs(r: &Rule) -> impl Iterator<Item = (usize, usize, &[Arg])> {
    r.query
        .iter()
        .enumerate()
        .filter_map(|(atom, q)| match q.call {
            Call::Table(t) => Some((atom, t, q.args.as_slice())),
            _ => None,
        })
}

fn field_sources<'a>(
    r: &'a Rule,
    arg: &'a Arg,
) -> impl Iterator<Item = (usize, usize, usize)> + 'a {
    table_inputs(r).flat_map(move |(atom, t, args)| {
        args.iter()
            .enumerate()
            .filter_map(move |(col, a)| (a == arg).then_some((atom, t, col)))
    })
}

pub(crate) fn accepts_field(r: &Rule, arg: &Arg, table: usize, col: usize) -> bool {
    table_inputs(r).any(|(_, t, args)| t == table && args.get(col) == Some(arg))
}

fn computations(r: &Rule) -> Vec<J> {
    let mut result = Vec::new();
    for (pc, q) in r.query.iter().enumerate() {
        let Call::Primitive(..) = q.call else {
            continue;
        };
        let Some((output, args)) = q.args.split_last() else {
            continue;
        };
        let operands = args
            .iter()
            .enumerate()
            .map(|(col, arg)| match arg {
                Arg::Literal(_) => json!({"literal_operand":col}),
                Arg::Slot(s) => {
                    let fields = field_sources(r, arg)
                        .map(|(a, _, c)| [a, c])
                        .collect::<Vec<_>>();
                    let prior = r.query[..pc]
                        .iter()
                        .enumerate()
                        .filter_map(|(i, op)| {
                            (matches!(op.call, Call::Primitive(..)) && op.args.last() == Some(arg))
                                .then_some(i)
                        })
                        .collect::<Vec<_>>();
                    json!({"slot":s,"fields":fields,"local_results":prior})
                }
            })
            .collect::<Vec<_>>();
        let consumed = if matches!(output, Arg::Slot(_)) {
            field_sources(r, output)
                .map(|(a, _, c)| [a, c])
                .collect::<Vec<_>>()
        } else {
            vec![]
        };
        result.push(json!({"atom":pc,"operands":operands,"target_fields":consumed}));
    }
    result
}

pub fn describe(p: &Program) -> J {
    let rules = p
        .rules
        .iter()
        .enumerate()
        .map(|(rid, r)| {
            let returns = Returns::rule(p, rid);
            let ops = &p.templates[r.template].ops;
            let mut outputs = BTreeMap::new();
            for (&pc, &t) in returns.tables.range(..ops.len()) {
                outputs.insert(
                    pc,
                    json!({"table":t,"effect":pc,"producer":"effect","presence":"required_if_instruction_completes",
                        "inputs_at":"recipe.rules[recipe_rule].effects[effect]"}),
                );
            }
            for (&effect, &base) in &returns.merge_offsets {
                let Op::Set(table, _, _) = ops[effect] else {
                    unreachable!()
                };
                for (local, t) in merge_returns(p, &p.merge_programs.merges[&table].operations) {
                    outputs.insert(
                        base + local,
                        json!({"table":t,"effect":effect,"merge_table":table,"producer":"custom_merge",
                    "merge_op":local,"presence":"conditional","when":["set_encounters_existing_row",
                    "native_equal_inputs_policy_enters_merge","native_merge_reaches_operation","construct_returns_witness"],
                    "operands":p.merge_programs.merges[&table].operations[local],
                    "inputs_at":"enclosing Set plus merge old row and new value"}),
                    );
                }
            }
            let inputs = table_inputs(r).map(|(atom, t, _)| json!({"atom":atom,"table":t}))
                .collect::<Vec<_>>();
            let computations = computations(r);
            json!({"recipe_rule":rid,"query_conditions":"recipe.rules[recipe_rule].query","inputs":inputs,"computations":computations,"outputs":outputs})
        })
        .collect::<Vec<_>>();
    let repairs = p
        .merge_programs
        .merges
        .iter()
        .map(|(table, m)| {
            (
                table,
                merge_returns(p, &m.operations).collect::<BTreeMap<_, _>>(),
            )
        })
        .collect::<BTreeMap<_, _>>();
    json!({"schema":"eggfuse-recipe-receipts/v1","recipe_sha256":p.artifact["recipe"]["sha256"],
        "rules":rules,"repair_outputs":repairs,
        "availability":"actual_named_return_after_source_publication",
        "lifetime":"resolve_current_witness_check_visibility_and_requested_version",
        "repair_owner":"runtime_event","dependencies":"recipe query/effect operands; merge slots 0 and 1 are old and new",
        "schedule":"recipe.control and entry_schedule","equal_inputs":"merge_programs.programs[].equal_inputs"})
}

#[cfg(test)]
mod tests {
    use super::{PortState, port_state};

    #[test]
    fn publication_and_liveness_are_distinct_from_static_port_membership() {
        assert_eq!(port_state(false, Some(7), || panic!()), PortState::Pending);
        assert_eq!(
            port_state(true, Some(7), || panic!()),
            PortState::Available(7)
        );
        assert_eq!(port_state(true, None::<u64>, || false), PortState::Absent);
        assert_eq!(port_state(true, None::<u64>, || true), PortState::Retired);
    }
}
