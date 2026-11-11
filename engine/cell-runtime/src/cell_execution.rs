//! Dependency cuts in authoritative Cell instructions. No instructions, graph
//! facts or instance bindings are copied into this plan. Runtime progress is
//! preparation only until the ordinary source-ordered executor consumes it.
use crate::{
    program::{Arg, Call, Op, Table, Template},
    value::Value,
};
use serde::Serialize;
use std::collections::BTreeSet;

#[cfg(feature = "sparse-cells")]
#[path = "cell_execution_runtime.rs"]
pub(crate) mod runtime;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub(crate) enum BoundaryKind {
    Constructor,
    MutableRead,
    Write,
    Union,
    Visibility,
    Failure,
    Primitive,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct Boundary {
    pub operation: usize,
    pub kind: BoundaryKind,
    pub table: Option<usize>,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct Segment {
    pub start: usize,
    pub end: usize,
    pub local_operations: usize,
    pub inputs: Vec<usize>,
    pub outputs: Vec<usize>,
    pub boundary: Option<Boundary>,
}
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize)]
pub(crate) struct Plan {
    pub segments: Vec<Segment>,
}

fn scalar(template: &Template, arg: &Arg) -> bool {
    match template.resolve_copy(arg) {
        Arg::Literal(Value::Int(_)) => true,
        Arg::Slot(s) => matches!(
            template.sorts[s]["kind"].as_str(),
            Some("i64" | "bool" | "Unit")
        ),
        _ => false,
    }
}
fn local(template: &Template, op: &Op) -> bool {
    match op {
        Op::Copy(..) => true,
        Op::Let(dst, Call::Primitive(name, sort), args) => {
            let arity = if name == "not" { 1 } else { 2 };
            matches!(
                name.as_str(),
                "+" | "-"
                    | "*"
                    | "/"
                    | "%"
                    | "min"
                    | "max"
                    | "="
                    | "!="
                    | "<"
                    | "<="
                    | ">"
                    | ">="
                    | "not"
                    | "and"
                    | "or"
                    | "xor"
                    | "implies"
            ) && matches!(sort.as_str(), "i64" | "bool" | "Unit")
                && scalar(template, &Arg::Slot(*dst))
                && args.len() == arity
                && args.iter().all(|a| scalar(template, a))
        }
        _ => false,
    }
}
impl Plan {
    pub fn derive(tables: &[Table], template: &Template, inputs: &[usize]) -> Self {
        let mut segments = Vec::new();
        let mut start = 0;
        for end in 0..=template.ops.len() {
            let instruction = template.ops.get(end);
            if instruction.is_some_and(|op| {
                local(template, op) && !matches!(op,Op::Let(dst,..) if inputs.contains(dst))
            }) {
                continue;
            }
            let boundary = instruction.map(|op| {
                let (kind, table) = match op {
                    Op::Let(_, Call::Table(t), _) => (
                        if tables[*t].virtual_fact {
                            BoundaryKind::Constructor
                        } else {
                            BoundaryKind::MutableRead
                        },
                        Some(*t),
                    ),
                    Op::Let(_, Call::Primitive(..), _) => (BoundaryKind::Primitive, None),
                    Op::Set(t, ..) => (BoundaryKind::Write, Some(*t)),
                    Op::Union(..) => (BoundaryKind::Union, None),
                    Op::Hide(t, ..) => (BoundaryKind::Visibility, Some(*t)),
                    Op::Panic => (BoundaryKind::Failure, None),
                    Op::Copy(..) => unreachable!(),
                };
                Boundary {
                    operation: end,
                    kind,
                    table,
                }
            });
            let mut inputs = BTreeSet::new();
            let mut outputs = BTreeSet::new();
            for (offset, op) in template.ops[start..end + usize::from(instruction.is_some())]
                .iter()
                .enumerate()
            {
                let mut column = 0;
                while let Some(a) = op.operand(column) {
                    if let Arg::Slot(s) = template.resolve_copy(a)
                        && !outputs.contains(&s)
                    {
                        inputs.insert(s);
                    }
                    column += 1;
                }
                // Boundary results are established only by its actual return.
                if start + offset < end
                    && let Op::Let(dst, ..) = op
                {
                    outputs.insert(*dst);
                }
            }
            let local_operations = template.ops[start..end]
                .iter()
                .filter(|op| matches!(op, Op::Let(..)))
                .count();
            segments.push(Segment {
                start,
                end,
                local_operations,
                inputs: inputs.into_iter().collect(),
                outputs: outputs.into_iter().collect(),
                boundary,
            });
            start = end + 1;
        }
        Self { segments }
    }
    pub fn storage_bytes(&self) -> usize {
        self.segments.capacity() * std::mem::size_of::<Segment>()
            + self
                .segments
                .iter()
                .map(|s| {
                    (s.inputs.capacity() + s.outputs.capacity()) * std::mem::size_of::<usize>()
                })
                .sum::<usize>()
    }
    pub fn wire(plans: &[Self]) -> serde_json::Value {
        serde_json::json!({"schema":"cell-execution-boundaries/v1","rules":plans})
    }
    #[cfg(feature = "sparse-cells")]
    pub fn slots(
        &self,
        fields: impl ExactSizeIterator<Item = (usize, Value)>,
        counts: &mut Counts,
    ) -> crate::slots::Slots {
        let extra = self.segments[0].outputs.len();
        let mut slots = crate::slots::Slots::with_capacity(fields.len() + extra);
        slots.extend(fields);
        counts.reserved_rhs_slot_bytes += (extra * std::mem::size_of::<(usize, Value)>()) as u64;
        slots
    }
    #[cfg(feature = "sparse-cells")]
    pub fn prepared_operations(&self, template: &Template, end: usize) -> usize {
        debug_assert!(end <= self.segments[0].end);
        template.ops[..end]
            .iter()
            .filter(|op| matches!(op, Op::Let(..)))
            .count()
    }
    #[cfg(feature = "sparse-cells")]
    pub fn prepare(
        &self,
        template: &Template,
        instance: &mut super::Instance,
        counts: &mut Counts,
    ) {
        let first = &self.segments[0];
        if first.local_operations == 0
            || instance.parent.is_some()
            || instance.continuation.is_some()
        {
            return;
        }
        debug_assert_eq!(instance.prepared, 0);
        counts.instances += 1;
        let bytes = instance.values.capacity_bytes();
        for (position, op) in template.ops[..first.end].iter().enumerate() {
            match op {
                Op::Copy(..) => (),
                Op::Let(dst, Call::Primitive(name, sort), args) => {
                    let args = args
                        .iter()
                        .map(|a| match template.resolve_copy(a) {
                            Arg::Literal(v) => Some(v),
                            Arg::Slot(s) => instance.values.get(&s).cloned(),
                        })
                        .collect::<Option<smallvec::SmallVec<[Value; 4]>>>();
                    let result = args.and_then(|args| {
                        crate::value::primitive(name, &args, sort, &serde_json::Value::Null)
                            .ok()
                            .flatten()
                    });
                    let Some(value) = result else {
                        counts.deferred_failures += 1;
                        break;
                    };
                    instance.values.insert(*dst, value);
                    counts.operations += 1;
                    counts.slot_writes += 1;
                }
                _ => unreachable!("typed local segment"),
            }
            instance.prepared = position + 1;
        }
        let growth = instance.values.capacity_bytes().saturating_sub(bytes);
        counts.capacity_growth_bytes += growth as u64;
        counts.frame_growths += u64::from(growth != 0);
    }
}
#[cfg(feature = "sparse-cells")]
#[derive(Default, Serialize)]
pub(crate) struct Counts {
    pub instances: u64,
    pub operations: u64,
    pub slot_writes: u64,
    pub deferred_failures: u64,
    pub reserved_rhs_slot_bytes: u64,
    pub capacity_growth_bytes: u64,
    pub frame_growths: u64,
}
#[cfg(feature = "sparse-cells")]
impl Counts {
    pub fn add(&mut self, other: &Self) {
        self.instances += other.instances;
        self.operations += other.operations;
        self.slot_writes += other.slot_writes;
        self.deferred_failures += other.deferred_failures;
        self.reserved_rhs_slot_bytes += other.reserved_rhs_slot_bytes;
        self.capacity_growth_bytes += other.capacity_growth_bytes;
        self.frame_growths += other.frame_growths;
    }
}

#[cfg(all(test, feature = "sparse-cells"))]
mod tests {
    use super::*;
    use serde_json::json;
    use std::{collections::BTreeMap, sync::Arc};
    fn template(ops: Vec<Op>) -> Template {
        let defs = ops
            .iter()
            .enumerate()
            .filter_map(|(i, op)| match op {
                Op::Copy(dst, _) | Op::Let(dst, ..) => Some((*dst, i)),
                _ => None,
            })
            .collect();
        Template {
            name: "cuts".into(),
            sorts: (0..8).map(|_| json!({"kind":"i64"})).collect(),
            defs,
            ops: Arc::new(ops),
            parent_columns: BTreeMap::new(),
        }
    }
    fn add(dst: usize, a: usize, b: usize) -> Op {
        Op::Let(
            dst,
            Call::Primitive("+".into(), "i64".into()),
            vec![Arg::Slot(a), Arg::Slot(b)],
        )
    }
    #[test]
    fn local_completion_stops_at_mutable_read_and_records_exact_slot_cuts() {
        let t = template(vec![
            Op::Copy(2, Arg::Slot(1)),
            add(3, 1, 2),
            Op::Let(4, Call::Table(0), vec![Arg::Slot(0)]),
            add(5, 3, 4),
            Op::Union(Arg::Slot(0), Arg::Slot(6)),
            Op::Hide(0, vec![Arg::Slot(0)], true),
            Op::Panic,
        ]);
        let tables = [Table {
            name: "Current".into(),
            schema: vec![],
            constructor: false,
            virtual_fact: false,
            merge: json!(null),
            internal: false,
        }];
        let plan = Plan::derive(&tables, &t, &[0, 1, 6]);
        assert_eq!(
            plan.segments[0].boundary.as_ref().unwrap().kind,
            BoundaryKind::MutableRead
        );
        assert_eq!(plan.segments[0].inputs, vec![0, 1]);
        assert_eq!(plan.segments[0].outputs, vec![3]);
        assert_eq!(plan.segments[1].inputs, vec![0, 3, 4, 6]);
        assert_eq!(plan.segments[1].outputs, vec![5]);
        assert_eq!(
            plan.segments
                .iter()
                .filter_map(|s| s.boundary.as_ref().map(|b| b.kind))
                .collect::<Vec<_>>(),
            vec![
                BoundaryKind::MutableRead,
                BoundaryKind::Union,
                BoundaryKind::Visibility,
                BoundaryKind::Failure
            ]
        );
        let mut instance = super::super::Instance::matched(
            [(0, Value::Eq(7)), (1, Value::Int(5)), (6, Value::Eq(9))]
                .into_iter()
                .collect(),
            super::super::QueryFacts::None,
            1,
        );
        let mut counts = Counts::default();
        plan.prepare(&t, &mut instance, &mut counts);
        assert_eq!(instance.prepared, 2);
        assert_eq!(instance.values[&3], Value::Int(10));
        assert!(!instance.values.contains_key(&4));
        assert!(!instance.values.contains_key(&5));
        assert_eq!(counts.operations, 1);
    }
    #[test]
    fn equality_sensitive_primitives_and_input_overwrites_are_boundaries() {
        let mut t = template(vec![add(2, 0, 1)]);
        t.sorts[0] = json!({"kind":"eq"});
        assert_eq!(Plan::derive(&[], &t, &[0, 1]).segments[0].end, 0);
        let t = template(vec![add(1, 0, 1)]);
        assert_eq!(Plan::derive(&[], &t, &[0, 1]).segments[0].end, 0);
    }
}
