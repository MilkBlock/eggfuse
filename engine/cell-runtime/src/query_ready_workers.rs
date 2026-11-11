//! Borrow already matched Cell instances into the source Run's query invocation.
//! The existing rule groups own their slots and source order throughout. These
//! jobs produce no answer vector, effects, Cursor mutations or graph reads.
use crate::{cell::{Instance, execution}, graph::Graph, program::Template};
use rayon::prelude::*;
use serde::Serialize;
use smallvec::SmallVec;

#[derive(Default, Serialize)]
pub(crate) struct Stats {
    pub rule_checks: u64,
    pub admission_instances: u64,
    pub groups: u64,
    pub deferred_groups: u64,
    pub deferred_instances: u64,
    pub deferred_operations: u64,
    pub header_growths: u64,
    pub header_capacity_bytes: u64,
    pub mixed_invocations: u64,
    pub matched_only_invocations: u64,
    pub instances: u64,
    pub chunks: u64,
    pub empty_chunks: u64,
    pub histogram_growths: u64,
    pub histogram_capacity_bytes: u64,
    pub worker_operations: u64,
    pub inline_operations: u64,
    // This is a subset of the enclosing query-worker execution accounting.
    pub execution: execution::Counts,
}

enum Rows<'a> {
    Matched(&'a mut [Instance]),
    Deferred(&'a mut [crate::stage_spine::Winner]),
}
trait Frame {
    fn frame(&self) -> &Instance;
    fn frame_mut(&mut self) -> &mut Instance;
}
impl Frame for Instance {
    fn frame(&self) -> &Instance { self }
    fn frame_mut(&mut self) -> &mut Instance { self }
}
impl Frame for crate::stage_spine::Winner {
    fn frame(&self) -> &Instance { &self.answer }
    fn frame_mut(&mut self) -> &mut Instance { &mut self.answer }
}
impl Rows<'_> {
    fn len(&self) -> usize {
        match self { Self::Matched(rows) => rows.len(), Self::Deferred(rows) => rows.len() }
    }
    fn any_pending(&self, code: &execution::Plan, checks: &mut u64) -> bool {
        fn pending<T: Frame>(rows: &[T], code: &execution::Plan, checks: &mut u64) -> bool {
            rows.iter().any(|row| { *checks += 1; code.needs_preparation(row.frame()) })
        }
        match self {
            Self::Matched(rows) => pending(rows, code, checks),
            Self::Deferred(rows) => pending(rows, code, checks),
        }
    }
}
pub(super) struct Group<'a> {
    code: &'a execution::Plan,
    template: &'a Template,
    rows: Rows<'a>,
}
pub(super) fn borrow<'a>(g: &'a Graph, matches: &'a mut [(usize, Vec<Instance>)],
    spine: &'a mut crate::stage_spine::Programs, stats: &mut Stats)
    -> Vec<Group<'a>> {
    let mut groups = Vec::new();
    let rows = matches.iter_mut().map(|(rule, rows)| (*rule, Rows::Matched(rows)))
        .chain(spine.deferred_frames().map(|(rule, rows)| (rule, Rows::Deferred(rows))));
    for (rule, rows) in rows {
        stats.rule_checks += 1;
        let code = &g.program.executions[rule];
        if !code.has_preparation() { continue; }
        let template = &g.program.templates[g.program.rules[rule].template];
        if !rows.any_pending(code, &mut stats.admission_instances) { continue; }
        stats.deferred_groups += u64::from(matches!(rows, Rows::Deferred(_)));
        stats.header_growths += u64::from(groups.len() == groups.capacity());
        groups.push(Group { code, template, rows });
    }
    stats.groups += groups.len() as u64;
    stats.header_capacity_bytes += (groups.capacity() * std::mem::size_of::<Group<'_>>()) as u64;
    groups
}
pub(super) fn instances(groups: &[Group<'_>]) -> usize {
    groups.iter().map(|g| g.rows.len()).sum()
}

#[derive(Default)]
pub(super) struct Work {
    pub execution: execution::Counts,
    pub instances: u64,
    pub deferred_instances: u64,
    pub deferred_operations: u64,
    pub chunks: u64,
    pub empty_chunks: u64,
    pub histogram_growths: u64,
    pub histogram_capacity_bytes: u64,
    // Reduction scratch, never a per-instance result packet. Up to eight
    // workers fit inline; larger pools use a charged bounded histogram.
    pub workers: SmallVec<[u64; 8]>,
}
impl Work {
    fn size_workers(&mut self, len: usize) {
        let before = if self.workers.spilled() { self.workers.capacity() } else { 0 };
        self.workers.resize(len, 0);
        let after = if self.workers.spilled() { self.workers.capacity() } else { 0 };
        self.histogram_growths += u64::from(after > before);
        self.histogram_capacity_bytes += (after.saturating_sub(before) * std::mem::size_of::<u64>()) as u64;
    }
    fn add(mut self, other: Self) -> Self {
        self.execution.add(&other.execution);
        self.instances += other.instances;
        self.deferred_instances += other.deferred_instances;
        self.deferred_operations += other.deferred_operations;
        self.chunks += other.chunks;
        self.empty_chunks += other.empty_chunks;
        self.histogram_growths += other.histogram_growths;
        self.histogram_capacity_bytes += other.histogram_capacity_bytes;
        self.size_workers(self.workers.len().max(other.workers.len()));
        for (to, from) in self.workers.iter_mut().zip(other.workers) { *to += from; }
        self
    }
    fn run<T: Frame>(code: &execution::Plan, template: &Template, rows: &mut [T], pooled: bool, deferred: bool) -> Self {
        let mut work = Self { instances: rows.len() as u64, chunks: 1, ..Default::default() };
        for row in rows { code.prepare(template, row.frame_mut(), &mut work.execution); }
        if deferred { work.deferred_instances = work.instances; work.deferred_operations = work.execution.operations; }
        work.empty_chunks = u64::from(work.execution.operations == 0);
        if pooled {
            let worker = rayon::current_thread_index().expect("Cell query pool");
            work.size_workers(worker + 1);
            work.workers[worker] = work.execution.operations;
        }
        work
    }
}
pub(super) fn parallel(groups: &mut [Group<'_>], grain: usize) -> Work {
    groups.par_iter_mut().map(|group| {
        let (code, template) = (group.code, group.template);
        match &mut group.rows {
            Rows::Matched(rows) => rows.par_chunks_mut(grain).map(|rows| Work::run(code, template, rows, true, false))
                .reduce(Work::default, Work::add),
            Rows::Deferred(rows) => rows.par_chunks_mut(grain).map(|rows| Work::run(code, template, rows, true, true))
                .reduce(Work::default, Work::add),
        }
    }).reduce(Work::default, Work::add)
}
pub(super) fn inline(groups: &mut [Group<'_>], grain: usize) -> Work {
    groups.iter_mut().map(|group| {
        let (code, template) = (group.code, group.template);
        match &mut group.rows {
            Rows::Matched(rows) => rows.chunks_mut(grain).map(|rows| Work::run(code, template, rows, false, false))
                .fold(Work::default(), Work::add),
            Rows::Deferred(rows) => rows.chunks_mut(grain).map(|rows| Work::run(code, template, rows, false, true))
                .fold(Work::default(), Work::add),
        }
    }).fold(Work::default(), Work::add)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{cell::QueryFacts, graph::FactRef, program::{Arg, Call, Op}, slots::Slots, value::Value};
    use std::{collections::BTreeMap, sync::Arc};

    #[test]
    fn a_worker_batch_mutates_existing_frames_in_place_and_keeps_prepared_instances() {
        let template = Template {
            name: "borrowed-matches".into(),
            sorts: vec![serde_json::json!({"kind":"eq","name":"E"}),
                serde_json::json!({"kind":"i64"}), serde_json::json!({"kind":"i64"}),
                serde_json::json!({"kind":"i64"})],
            defs: BTreeMap::from([(2, 0), (3, 2)]), parent_columns: BTreeMap::new(),
            ops: Arc::new(vec![
                Op::Let(2, Call::Primitive("+".into(), "i64".into()), vec![Arg::Slot(1), Arg::Slot(1)]),
                Op::Union(Arg::Slot(0), Arg::Slot(0)),
                Op::Let(3, Call::Primitive("+".into(), "i64".into()), vec![Arg::Slot(1), Arg::Slot(2)]),
            ]),
        };
        let code = execution::Plan::derive(&[], &template, &[0, 1]);
        let mut rows: Vec<_> = (0..64).map(|i| {
            let mut values = Slots::with_capacity(4);
            values.extend([(0, Value::Eq(9)), (1, Value::Int(i))]);
            let mut row = Instance::matched(values, QueryFacts::None, 17);
            row.parent = Some(FactRef { cell: 999, op: 4 });
            row.continuation = Some((2, false));
            if i % 2 == 0 { code.prepare(&template, &mut row, &mut Default::default()); }
            row
        }).collect();
        let allocations: Vec<_> = rows.iter().map(|r| std::ptr::from_ref(&r.values[&0])).collect();
        let row_array = rows.as_ptr();
        let pool = rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let mut groups = [Group { code: &code, template: &template, rows: Rows::Matched(&mut rows) }];
        let work = pool.install(|| parallel(&mut groups, 8));
        assert_eq!(work.execution.operations, 64);
        assert_eq!(work.execution.later_operations, 32);
        assert_eq!(work.workers.iter().sum::<u64>(), 64);
        assert_eq!(work.execution.frame_growths, 0);
        assert_eq!(work.histogram_growths, 0);
        assert_eq!(inline(&mut groups, 8).execution.operations, 0);
        assert_eq!(rows.as_ptr(), row_array);
        for (i, row) in rows.iter().enumerate() {
            assert_eq!(std::ptr::from_ref(&row.values[&0]), allocations[i]);
            assert_eq!(row.values[&3], Value::Int(3 * i as i64));
            assert_eq!(row.prepared, 1);
            assert_eq!(row.continuation, Some((2, false)));
        }
    }
}
