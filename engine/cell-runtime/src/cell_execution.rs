//! Dependency cuts in authoritative Cell instructions. No instructions, graph
//! facts or instance bindings are copied into this plan. Query-side preparation
//! does not advance source effects; the ordered executor consumes its results.
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
    /// Selected from validated aliases when experimental Cell execution is
    /// enabled. It is reconstructed, never trusted from an artifact hint.
    #[cfg(feature = "sparse-cells")]
    #[serde(skip)]
    pub constructor: Option<super::constructor_prepare::Plan>,
    #[cfg(feature = "sparse-cells")]
    #[serde(skip)]
    pub births: Option<std::sync::Arc<crate::graph::cell_births::Plan>>,
    /// Parent columns still reachable after completion, only when every one
    /// has a composed symbol. None rejects the template before runtime probing.
    #[cfg(all(feature = "sparse-cells",feature="storage-metrics"))]
    #[serde(skip)]
    pub parent_completion: Option<Box<[usize]>>,
    pub segments: Vec<Segment>,
    /// Source positions after the first boundary whose scalar operands are
    /// derived entirely from matched inputs. Outputs have unique SSA slots;
    /// their presence is the preparation evidence, not a per-instance log.
    pub input_ready: Vec<usize>,
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
        let mut ready = inputs.iter().copied().collect::<BTreeSet<_>>();
        let mut input_ready = Vec::new();
        // The ordinary operand reader gives captured input slots precedence
        // over Copy definitions. Decline this optimization on input rewrites
        // rather than treating a global Copy alias as the captured value.
        if inputs.iter().all(|s| !template.defs.contains_key(s)) {
            for (position, op) in template.ops.iter().enumerate() {
                if matches!(op, Op::Panic) { break; }
                if let Op::Let(dst, _, args) = op {
                    if local(template, op) && args.iter().all(|a| match template.resolve_copy(a) {
                        Arg::Literal(_) => true,
                        Arg::Slot(s) => ready.contains(&s),
                    }) {
                        ready.insert(*dst);
                        if position > segments[0].end { input_ready.push(position); }
                    } else { ready.remove(dst); }
                }
            }
        }
        Self { segments, input_ready,
            #[cfg(all(feature = "sparse-cells",feature="storage-metrics"))] parent_completion: None,
            #[cfg(feature = "sparse-cells")] constructor: None,
            #[cfg(feature = "sparse-cells")] births: None }
    }
    pub fn storage_bytes(&self) -> usize {
        let constructor = {
            #[cfg(feature = "sparse-cells")]
            { self.constructor.as_ref().map_or(0, |p| p.storage_bytes())
                + self.births.as_ref().map_or(0, |p| p.storage_bytes()) }
            #[cfg(not(feature = "sparse-cells"))]
            { 0 }
        };
        constructor
            + { #[cfg(all(feature="sparse-cells",feature="storage-metrics"))] {self.parent_completion.as_ref().map_or(0,|p|p.len()*std::mem::size_of::<usize>())}
                #[cfg(not(all(feature="sparse-cells",feature="storage-metrics")))] {0} }
            + self.input_ready.capacity() * std::mem::size_of::<usize>()
            + self.segments.capacity() * std::mem::size_of::<Segment>()
            + self
                .segments
                .iter()
                .map(|s| {
                    (s.inputs.capacity() + s.outputs.capacity()) * std::mem::size_of::<usize>()
                })
                .sum::<usize>()
    }
    pub fn wire(plans: &[Self]) -> serde_json::Value {
        serde_json::json!({"schema":"cell-execution-boundaries/v2","rules":plans})
    }
    pub fn checks_wire(plans: &[Self], raw: &serde_json::Value) -> bool {
        if raw["schema"] == "cell-execution-boundaries/v1" {
            // Old artifacts carry only cuts. New preparation eligibility is
            // always reconstructed from the same checked typed recipe.
            *raw == serde_json::json!({"schema":"cell-execution-boundaries/v1",
                "rules":plans.iter().map(|p|serde_json::json!({"segments":p.segments})).collect::<Vec<_>>()})
        } else { *raw == Self::wire(plans) }
    }
    #[cfg(feature = "sparse-cells")]
    pub fn slots(
        &self,
        fields: impl ExactSizeIterator<Item = (usize, Value)>,
        counts: &mut Counts,
    ) -> crate::slots::Slots {
        let extra = self.segments[0].outputs.len() + self.input_ready.len();
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
    pub fn prepared_at(&self, position: usize, template: &Template, values: &impl crate::slots::ReadSlots) -> bool {
        self.input_ready.binary_search(&position).is_ok()
            && matches!(&template.ops[position], Op::Let(dst,..) if values.contains_key(dst))
    }
    #[cfg(feature = "sparse-cells")]
    pub fn has_preparation(&self) -> bool {
        self.has_scalar_preparation() || self.constructor.is_some()
    }
    #[cfg(feature = "sparse-cells")]
    fn has_scalar_preparation(&self) -> bool {
        self.segments[0].local_operations > 0 || !self.input_ready.is_empty()
    }
    #[cfg(feature = "sparse-cells")]
    pub fn needs_preparation(&self, instance: &super::Instance) -> bool {
        (self.has_scalar_preparation() && !instance.preparation_attempted)
            || (self.constructor.is_some() && instance.constructor.pending())
    }
    #[cfg(feature = "sparse-cells")]
    pub fn prepare(
        &self,
        template: &Template,
        instance: &mut super::Instance,
        counts: &mut Counts,
    ) {
        let first = &self.segments[0];
        if !self.has_scalar_preparation() || instance.preparation_attempted { return; }
        instance.preparation_attempted = true;
        debug_assert_eq!(instance.prepared, 0);
        counts.instances += 1;
        let bytes = instance.values.capacity_bytes();
        // Completed matches may retain a parent or continuation provenance.
        // Only their owned scalar values are used here. Missing projections
        // stay deferred; no worker reads a parent or manipulates a Cursor.
        instance.values.reserve_exact(first.outputs.len() + self.input_ready.len());
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
        // Failure is observed at its original RHS position. A missing result
        // remains absent and uses the ordinary interpreter there. Stop further
        // preparation on failure; no error packet or operation log is needed.
        if instance.prepared == first.end {
            for &position in &self.input_ready {
                let Op::Let(dst, Call::Primitive(name, sort), args) = &template.ops[position]
                    else { unreachable!("typed input-ready scalar operation") };
                let args = args.iter().map(|a| match template.resolve_copy(a) {
                    Arg::Literal(v) => Some(v),
                    Arg::Slot(s) => instance.values.get(&s).cloned(),
                }).collect::<Option<smallvec::SmallVec<[Value; 4]>>>();
                let value = args.and_then(|args| crate::value::primitive(name, &args, sort,
                    &serde_json::Value::Null).ok().flatten());
                let Some(value) = value else {
                    counts.deferred_failures += 1;
                    counts.later_deferred_failures += 1;
                    break;
                };
                instance.values.insert(*dst, value);
                counts.operations += 1;
                counts.later_operations += 1;
                counts.slot_writes += 1;
            }
        }
        let growth = instance.values.capacity_bytes().saturating_sub(bytes);
        counts.capacity_growth_bytes += growth as u64;
        counts.frame_growths += u64::from(growth != 0);
    }
}
#[cfg(feature = "sparse-cells")]
#[derive(Default, Serialize)]
pub(crate) struct Counts {
    pub constructor: super::constructor_prepare::Counts,
    pub instances: u64,
    pub operations: u64,
    pub later_operations: u64,
    pub later_deferred_failures: u64,
    pub slot_writes: u64,
    pub deferred_failures: u64,
    pub reserved_rhs_slot_bytes: u64,
    pub capacity_growth_bytes: u64,
    pub frame_growths: u64,
}
#[cfg(feature = "sparse-cells")]
impl Counts {
    pub fn add(&mut self, other: &Self) {
        self.constructor.add(&other.constructor);
        self.instances += other.instances;
        self.operations += other.operations;
        self.later_operations += other.later_operations;
        self.later_deferred_failures += other.later_deferred_failures;
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
    fn captured_parent_preparation_keeps_partial_results_and_defers_missing_operands() {
        let t = template(vec![add(2, 0, 0), add(3, 2, 1),
            Op::Union(Arg::Slot(6), Arg::Slot(6)), add(4, 3, 1)]);
        let plan = Plan::derive(&[], &t, &[0, 1, 6]);
        let mut values = crate::slots::Slots::with_capacity(6);
        values.extend([(0, Value::Int(3)), (6, Value::Eq(9))]);
        let mut instance = super::super::Instance::matched(values, super::super::QueryFacts::None, 17);
        // No graph or parent is available to this computation. Captured owned
        // scalars remain sufficient even with source-continuation provenance.
        instance.parent = Some(crate::graph::FactRef { cell: 999, op: 4 });
        instance.continuation = Some((5, true));
        let mut first = Counts::default();
        plan.prepare(&t, &mut instance, &mut first);
        assert_eq!(first.operations, 1);
        assert_eq!(first.deferred_failures, 1);
        assert_eq!(instance.prepared, 1);
        assert_eq!(instance.values[&2], Value::Int(6));
        assert!(!instance.values.contains_key(&3));
        let mut repeated = Counts::default();
        plan.prepare(&t, &mut instance, &mut repeated);
        assert_eq!(repeated.instances, 0);
        assert_eq!(repeated.operations, 0);
        assert_eq!(repeated.deferred_failures, 0, "a Run batch must not retry failed preparation");
        assert_eq!(instance.prepared, 1, "the source executor resumes at the missing operand");
        assert_eq!(instance.values[&2], Value::Int(6));
        assert!(!instance.values.contains_key(&4));
        assert_eq!(instance.continuation, Some((5, true)));
    }
    #[test]
    fn ready_analysis_follows_copy_wiring_and_never_prepares_mutable_dependencies() {
        let t = template(vec![
            Op::Let(2, Call::Table(0), vec![Arg::Slot(0)]),
            Op::Copy(3, Arg::Slot(1)),
            add(4, 3, 1),
            add(5, 2, 4),
            Op::Panic,
            add(6, 1, 1),
        ]);
        let tables = [Table { name: "read".into(), schema: vec![], constructor: false,
            virtual_fact: false, merge: json!(null), internal: false }];
        let plan = Plan::derive(&tables, &t, &[0, 1]);
        assert_eq!(plan.input_ready, [2]);
        let mut counts = Counts::default();
        let values = plan.slots([(0, Value::Int(9)), (1, Value::Int(3))].into_iter(), &mut counts);
        let mut instance = super::super::Instance::matched(values, super::super::QueryFacts::None, 1);
        plan.prepare(&t, &mut instance, &mut counts);
        assert_eq!(instance.prepared, 0, "no source operation was completed");
        assert_eq!(instance.values[&4], Value::Int(6));
        assert!(!instance.values.contains_key(&2));
        assert!(!instance.values.contains_key(&5));
        assert!(!instance.values.contains_key(&6));
        assert_eq!(counts.frame_growths, 0);
        assert_eq!(counts.later_operations, 1);

        let rewritten = template(vec![Op::Copy(1, Arg::Slot(0)),
            Op::Let(2, Call::Table(0), vec![Arg::Slot(0)]), add(4, 1, 0)]);
        assert!(Plan::derive(&tables, &rewritten, &[0, 1]).input_ready.is_empty(),
            "captured input overwrite needs a stronger proof than Copy resolution");
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
