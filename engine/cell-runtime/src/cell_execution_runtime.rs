//! Continue the same Cell at a source-ordered dependency boundary. A worker
//! borrows its actual frame exclusively; it returns a frontier, never an effect
//! log or a second binding. The current scheduler retains global effect order.
use super::{BoundaryKind, Plan};
use crate::{
    graph::{Cell, Graph},
    program::{Arg, Call, Op, Template},
    value::Value,
};
use serde::Serialize;
use std::time::Instant;

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Stop {
    Boundary(BoundaryKind),
    Complete,
    // Parent projections and implicit results still use the graph operand
    // reader at this one instruction; no completed instruction is replayed.
    Operand,
    Failed(String),
}

#[derive(Default, Serialize)]
pub(crate) struct Counts {
    pub frames: u64,
    pub segments: u64,
    pub local_operations: u64,
    pub prepared_operations_consumed: u64,
    pub worker_segments: u64,
    pub worker_operations: u64,
    pub worker_wait_ns: u64,
    pub operand_boundaries: u64,
    pub failures: u64,
    pub slot_growths: u64,
    pub capacity_growth_bytes: u64,
    pub boundaries: [u64; 7],
}
impl Counts {
    pub(crate) fn boundary(&mut self, kind: BoundaryKind) {
        let index = match kind {
            BoundaryKind::Constructor => 0,
            BoundaryKind::MutableRead => 1,
            BoundaryKind::Write => 2,
            BoundaryKind::Union => 3,
            BoundaryKind::Visibility => 4,
            BoundaryKind::Failure => 5,
            BoundaryKind::Primitive => 6,
        };
        self.boundaries[index] += 1;
    }
    pub fn add(&mut self, other: Self) {
        self.frames += other.frames;
        self.segments += other.segments;
        self.local_operations += other.local_operations;
        self.prepared_operations_consumed += other.prepared_operations_consumed;
        self.worker_segments += other.worker_segments;
        self.worker_operations += other.worker_operations;
        self.worker_wait_ns += other.worker_wait_ns;
        self.operand_boundaries += other.operand_boundaries;
        self.failures += other.failures;
        self.slot_growths += other.slot_growths;
        self.capacity_growth_bytes += other.capacity_growth_bytes;
        for (a, b) in self.boundaries.iter_mut().zip(other.boundaries) {
            *a += b;
        }
    }
}
pub(crate) struct State {
    pub grain: usize,
    pub counts: Counts,
}
pub(crate) struct Yield {
    pub stop: Stop,
    pub counts: Counts,
}

impl Plan {
    fn resume(&self, template: &Template, frame: &mut Cell) -> Yield {
        let mut counts = Counts::default();
        let position = frame.completed_prefix;
        let Some(segment) = self
            .segments
            .get(self.segments.partition_point(|s| s.end < position))
        else {
            debug_assert_eq!(position, template.ops.len());
            return Yield {
                stop: Stop::Complete,
                counts,
            };
        };
        let capacity = frame.values.capacity_bytes();
        counts.segments += u64::from(position < segment.end);
        let mut stop = segment
            .boundary
            .as_ref()
            .map_or(Stop::Complete, |b| Stop::Boundary(b.kind));
        for position in position..segment.end {
            match &template.ops[position] {
                Op::Copy(..) => (),
                Op::Let(dst, Call::Primitive(name, sort), args) => {
                    if self.prepared_at(position, template, &frame.values) {
                        counts.prepared_operations_consumed += 1;
                        frame.completed_prefix = position + 1;
                        continue;
                    }
                    let args = args
                        .iter()
                        .map(|a| match template.resolve_copy(a) {
                            Arg::Literal(v) => Some(v),
                            Arg::Slot(s) => frame.values.get(&s).cloned(),
                        })
                        .collect::<Option<smallvec::SmallVec<[Value; 4]>>>();
                    let Some(args) = args else {
                        counts.operand_boundaries += 1;
                        stop = Stop::Operand;
                        break;
                    };
                    match crate::value::primitive(name, &args, sort, &serde_json::Value::Null) {
                        Ok(Some(v)) => {
                            frame.values.insert(*dst, v);
                            counts.local_operations += 1;
                        }
                        failure => {
                            counts.failures += 1;
                            stop = Stop::Failed(
                                failure
                                    .err()
                                    .unwrap_or_else(|| format!("RHS primitive failed: {name}")),
                            );
                            break;
                        }
                    }
                }
                _ => unreachable!("checked local Cell segment"),
            }
            frame.completed_prefix = position + 1;
        }
        let growth = frame.values.capacity_bytes().saturating_sub(capacity);
        counts.slot_growths += u64::from(growth != 0);
        counts.capacity_growth_bytes += growth as u64;
        Yield {
            stop,
            counts,
        }
    }

    fn remaining_local(&self, position: usize) -> usize {
        self.segments
            .get(self.segments.partition_point(|s| s.end < position))
            .filter(|s| position < s.end)
            .map_or(0, |s| s.local_operations)
    }
}

impl Graph {
    pub(crate) fn resume_cell(
        &mut self,
        rule: usize,
        cell: u32,
        pool: Option<&rayon::ThreadPool>,
        grain: usize,
    ) -> Yield {
        let position = self.rhs_frame(cell).expect("executing Cell").completed_prefix;
        if self.program.executions[rule].remaining_local(position) >= grain
            && let Some(pool) = pool
        {
            // The source-ordered owner cannot commit the next effect until
            // this frontier returns. Charge that wait; this is not a claim of
            // concurrent graph writes or removed scheduling barriers.
            let clock = Instant::now();
            let mut suspended = self.suspend_rhs(cell);
            let plan = &self.program.executions[rule];
            let template = &self.program.templates[self.program.rules[rule].template];
            let frame = match &mut suspended.private {
                Some(frame) => frame,
                None => self.cells.get_mut(&cell).expect("retained public Cell"),
            };
            let mut result = pool.install(|| {
                debug_assert!(rayon::current_thread_index().is_some());
                plan.resume(template, frame)
            });
            self.restore_rhs(suspended);
            result.counts.worker_segments += 1;
            result.counts.worker_operations += result.counts.local_operations;
            result.counts.worker_wait_ns += clock.elapsed().as_nanos() as u64;
            result
        } else {
            let (plan, template, frame) = self.execution_parts(rule, cell);
            plan.resume(template, frame)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        cell::{Effects, RhsFrame},
        program::Rule,
        slots::Slots,
    };
    use std::{collections::BTreeMap, rc::Rc, sync::Arc};

    #[test]
    fn mutable_result_is_resolved_at_its_boundary_then_the_same_frame_runs_on_a_worker() {
        let mut g = crate::query::test_projection_graph();
        let template = Template {
            name: "ordered-read".into(),
            sorts: vec![serde_json::json!({"kind":"i64"}); 7],
            defs: BTreeMap::from([(3, 0), (4, 1), (5, 2), (6, 3)]),
            parent_columns: BTreeMap::new(),
            ops: Arc::new(vec![
                Op::Let(3, Call::Table(0), vec![Arg::Slot(0), Arg::Slot(1)]),
                Op::Let(
                    4,
                    Call::Primitive("+".into(), "i64".into()),
                    vec![Arg::Slot(3), Arg::Literal(Value::Int(1))],
                ),
                Op::Let(5, Call::Primitive("+".into(), "i64".into()),
                    vec![Arg::Slot(0), Arg::Slot(1)]),
                Op::Let(6, Call::Primitive("+".into(), "i64".into()),
                    vec![Arg::Slot(4), Arg::Slot(5)]),
                Op::Set(1, vec![Arg::Slot(0), Arg::Slot(1)], Arg::Slot(6)),
            ]),
        };
        g.program
            .executions
            .push(Plan::derive(&g.program.tables, &template, &[0, 1]));
        g.program.templates.push(template);
        g.program.rules.push(Rule {
            template: 0,
            query: Rc::new(vec![]),
            inputs: vec![0, 1].into(),
            completion: Default::default(),
            seminaive: false,
            direct: None,
        });
        let key = [Value::Int(1), Value::Int(2)];
        g.set_function(0, key.to_vec(), Value::Int(5)).unwrap();
        let mut values = Slots::with_capacity(7);
        values.extend([(0, key[0].clone()), (1, key[1].clone())]);
        let allocation = std::ptr::from_ref(values.get(&0).unwrap());
        let mut instance = crate::cell::Instance::matched(values, Default::default(), 0);
        let mut preparation = super::super::Counts::default();
        g.program.executions[0].prepare(&g.program.templates[0], &mut instance, &mut preparation);
        assert_eq!(preparation.later_operations, 1);
        assert!(!instance.values.contains_key(&3), "mutable input remains unresolved");
        let cell = g.begin_transient(0, instance.values, None).unwrap();
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(2)
            .build()
            .unwrap();
        let reads = g.key_lookup_calls.get();
        let first = g.resume_cell(0, cell, Some(&pool), 1);
        assert_eq!(first.stop, Stop::Boundary(BoundaryKind::MutableRead));
        assert_eq!(first.counts.worker_segments, 0);
        assert_eq!(
            g.key_lookup_calls.get(),
            reads,
            "no speculative mutable read"
        );
        // An earlier source-ordered effect can change the value before this
        // boundary is resolved. Only the actual return authorizes continuation.
        g.set_function(0, key.to_vec(), Value::Int(9)).unwrap();
        let mut receipts = Effects::default();
        let instruction = g.program.templates[0].ops[0].clone();
        (RhsFrame {
            cell,
            receipts: &mut receipts,
        })
        .execute(&mut g, 0, &instruction, None)
        .unwrap();
        g.rhs_frame_mut(cell).unwrap().completed_prefix = 1;
        let next = g.resume_cell(0, cell, Some(&pool), 1);
        assert_eq!(next.stop, Stop::Boundary(BoundaryKind::Write));
        assert_eq!(next.counts.worker_operations, 2);
        assert_eq!(g.stats.rhs_context_suspends, 1);
        assert_eq!(g.stats.rhs_context_resumes, 1);
        assert_eq!(g.stats.rhs_suspend_private, 1);
        assert_eq!(g.stats.rhs_suspend_promotions, 0);
        assert_eq!(next.counts.prepared_operations_consumed, 1);
        assert_eq!(next.counts.slot_growths, 0);
        assert_eq!(g.rhs_frame(cell).unwrap().completed_prefix, 4);
        assert_eq!(g.slot(cell, 4).unwrap(), Value::Int(10));
        assert_eq!(g.slot(cell, 6).unwrap(), Value::Int(13));
        assert_eq!(
            std::ptr::from_ref(g.rhs_frame(cell).unwrap().values.get(&0).unwrap()),
            allocation
        );
        let instruction = g.program.templates[0].ops[4].clone();
        (RhsFrame {
            cell,
            receipts: &mut receipts,
        })
        .execute(&mut g, 4, &instruction, None)
        .unwrap();
        g.rhs_frame_mut(cell).unwrap().completed_prefix = 5;
        assert_eq!(g.resume_cell(0, cell, Some(&pool), 1).stop, Stop::Complete);
        assert_eq!(
            g.lookup_canonical(1, &key).unwrap().unwrap().values.last(),
            Some(&Value::Int(13))
        );
    }
}
