//! One source Cell owns its continuation through individual effect boundaries.
//! The graph retains the original slot allocation; this owner keeps the existing
//! Cursor, witness demands and result buffer, never another binding or effect log.
use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Phase { Ready, Boundary, Complete, Stopped, Failed }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Frontier { Boundary(usize), Complete, Stopped }

#[derive(Default, Clone, Copy)]
pub(super) struct Work {
    pub facts: u64,
    pub updates: u64,
    pub constructors: u64,
    pub unions: u64,
}
impl Work {
    fn read(g: &Graph) -> Self {
        Self { facts: g.stats.logical_facts_created, updates: g.stats.function_updates,
            constructors: g.stats.constructor_requests, unions: g.stats.union_requests }
    }
    pub fn started(g: &Graph, facts: u64, updates: u64, stage: Option<(u64, u64, u64)>) -> Self {
        Self { facts: g.stats.logical_facts_created - facts,
            updates: g.stats.function_updates - updates,
            constructors: stage.map_or(0, |(c, _, _)| g.stats.constructor_requests - c),
            unions: stage.map_or(0, |(_, _, u)| g.stats.union_requests - u) }
    }
    fn add_since(&mut self, g: &Graph, before: Self) {
        let after = Self::read(g);
        self.facts += after.facts - before.facts;
        self.updates += after.updates - before.updates;
        self.constructors += after.constructors - before.constructors;
        self.unions += after.unions - before.unions;
    }
}

pub(super) struct Execution {
    pub rule: usize,
    pub cell: u32,
    pub phase: Phase,
    pub ops: std::sync::Arc<Vec<Op>>,
    pub aliases: Option<Rc<Vec<bool>>>,
    pub known: QueryFacts,
    pub cursor: Option<crate::stage_spine::Started>,
    pub effects: crate::cell::Effects,
    pub continuation: bool,
    pub work: Work,
    #[cfg(feature = "view-consumers")]
    pub view_source: Option<usize>,
    #[cfg(feature = "iterative-bake")]
    pub transfers: smallvec::SmallVec<[crate::result_handoff::Input; 4]>,
    #[cfg(feature = "iterative-bake")]
    pub transfer: usize,
    #[cfg(feature = "structural-depth")]
    pub proven: Vec<(usize, u8)>,
    #[cfg(all(feature = "rhs-work-audit", feature = "rhs-locals"))]
    pub inspect_births: (Option<Rc<crate::local_rhs::Block>>, bool),
}

impl Executor {
    /// Pure preparation may advance the existing slots. Repeatedly observing a
    /// boundary does not query, submit an effect or consume a handoff twice.
    pub(super) fn advance_cell(&mut self, execution: &mut Execution) -> Result<Frontier> {
        match execution.phase {
            Phase::Complete => return Ok(Frontier::Complete),
            Phase::Stopped => return Ok(Frontier::Stopped),
            Phase::Failed => return Err("cannot resume a failed Cell execution".into()),
            Phase::Boundary => return Ok(Frontier::Boundary(
                self.graph.rhs_frame(execution.cell).expect("executing Cell").completed_prefix)),
            Phase::Ready => (),
        }
        let cell = execution.cell;
        #[cfg(feature = "sparse-cells")]
        let rid = execution.rule;
        loop {
            #[cfg(feature = "sparse-cells")]
            let position = self.graph.rhs_frame(cell).expect("executing Cell").completed_prefix;
            #[cfg(feature = "sparse-cells")]
            if matches!(execution.ops.get(position), Some(Op::Let(_, Call::Primitive(..), _)))
                && self.graph.program.executions[rid].prepared_at(position,
                    &self.graph.program.templates[self.graph.program.rules[rid].template],
                    &self.graph.rhs_frame(cell).unwrap().values) {
                self.graph.stats.prepared_rhs_later_operations += 1;
                self.graph.rhs_frame_mut(cell).unwrap().completed_prefix = position + 1;
                continue;
            }
            #[cfg(feature = "sparse-cells")]
            if let Some(runtime) = &mut self.cell_execution
                && matches!(execution.ops.get(position), Some(Op::Let(_, Call::Primitive(..), _))) {
                use crate::cell::execution::runtime::Stop;
                let pool = self.query_workers.as_ref().and_then(|w| w.execution_pool());
                let result = self.graph.resume_cell(rid, cell, pool, runtime.grain);
                self.graph.stats.prepared_rhs_later_operations += result.counts.prepared_operations_consumed;
                runtime.counts.add(result.counts);
                match result.stop {
                    Stop::Failed(error) => { execution.phase = Phase::Failed; return Err(error); }
                    Stop::Complete | Stop::Boundary(_) | Stop::Operand => (),
                }
            }
            let position = self.graph.rhs_frame(cell).unwrap().completed_prefix;
            if position == execution.ops.len() {
                execution.phase = Phase::Complete;
                return Ok(Frontier::Complete);
            }
            execution.phase = Phase::Boundary;
            return Ok(Frontier::Boundary(position));
        }
    }

    /// Commit precisely the offered source instruction. The position and phase
    /// reject stale boundary deliveries; failed effects cannot be retried.
    pub(super) fn resolve_cell_boundary(&mut self, execution: &mut Execution, position: usize) -> Result<()> {
        if execution.phase != Phase::Boundary
            || self.graph.rhs_frame(execution.cell).expect("executing Cell").completed_prefix != position {
            return Err("stale Cell execution boundary".into());
        }
        execution.phase = Phase::Failed;
        let before = Work::read(&self.graph);
        let result = self.execute_cell_boundary(execution, position);
        execution.work.add_since(&self.graph, before);
        match result {
            Ok(live) => {
                self.graph.rhs_frame_mut(execution.cell).unwrap().completed_prefix = position + 1;
                execution.phase = if live { Phase::Ready } else { Phase::Stopped };
                Ok(())
            }
            Err(error) => Err(error),
        }
    }

    fn execute_cell_boundary(&mut self, execution: &mut Execution, position: usize) -> Result<bool> {
        let op = &execution.ops[position];
        #[cfg(feature = "sparse-cells")]
        if let Some(runtime) = &mut self.cell_execution {
            use crate::cell::execution::BoundaryKind as K;
            let kind = match op {
                Op::Let(_, Call::Table(t), _) => Some(if self.graph.program.tables[*t].virtual_fact { K::Constructor } else { K::MutableRead }),
                Op::Let(_, Call::Primitive(..), _) => Some(K::Primitive),
                Op::Set(..) => Some(K::Write), Op::Union(..) => Some(K::Union),
                Op::Hide(..) => Some(K::Visibility), Op::Panic => Some(K::Failure),
                Op::Copy(..) => None,
            };
            if let Some(kind) = kind { runtime.counts.boundary(kind); }
        }
        if self.graph.known_stats.elide_static(execution.aliases.as_deref().map(Vec::as_slice), position) {
            return Ok(true);
        }
        #[cfg(feature = "iterative-bake")]
        if let Some(input) = execution.transfers.get(execution.transfer).filter(|r| r.op == position) {
            execution.transfer += 1;
            if crate::cell::apply_handoff(&mut self.graph, execution.cell, &mut execution.effects, op, input)? {
                #[cfg(feature = "structural-depth")]
                if self.stage_spine.structural.execute && !execution.continuation
                    && let Some((_, depth)) = execution.proven.iter().find(|(op, _)| *op == position) {
                    self.stage_spine.structural.accepted(*depth as usize);
                }
                return Ok(true);
            }
        }
        #[cfg(feature = "view-consumers")]
        let source = execution.view_source;
        #[cfg(not(feature = "view-consumers"))]
        let source = None;
        (crate::cell::RhsFrame { cell: execution.cell, receipts: &mut execution.effects })
            .execute(&mut self.graph, position, op, source)
    }

    /// Seal the existing actual-result storage once. Entry visibility is still
    /// opened by the original Run completion/publication path.
    pub(super) fn finish_cell(&mut self, execution: Execution) -> Result<()> {
        let completed = match execution.phase {
            Phase::Complete => true,
            Phase::Stopped => false,
            _ => return Err("cannot finish an incomplete Cell execution".into()),
        };
        let (rid, cell) = (execution.rule, execution.cell);
        self.graph.rhs_frame_mut(cell).unwrap().completed = completed;
        if execution.continuation {
            self.continuation_stats.published_facts += execution.work.facts;
            self.continuation_stats.function_updates += execution.work.updates;
        }
        if execution.cursor.is_some() {
            self.stage_spine.effects(execution.work.constructors, execution.work.updates, execution.work.unions);
        }
        #[cfg(feature = "structural-depth")]
        if completed {
            self.stage_spine.structural.capture(&self.graph, rid, &execution.known, &execution.effects);
        }
        if completed && let Some(cursor) = execution.cursor {
            self.stage_spine.complete(&self.graph, rid, cell, cursor, |i| execution.known.receipt(i),
                execution.effects, |args| self.graph.arguments(cell, args))?;
        } else if !completed {
            self.stage_spine.abort_effects(execution.effects);
        } else {
            self.stage_spine.finish_effects(execution.effects, false);
        }
        #[cfg(all(feature = "rhs-work-audit", feature = "rhs-locals"))]
        if let (Some(block), root) = execution.inspect_births {
            for &op in &block.intermediate_ops {
                if self.graph.rhs_frame(cell).unwrap().facts.contains_key(&(op as u32)) {
                    let fact = FactRef { cell, op: op as u32 };
                    let table = self.graph.live_table(Dependency::Fact(fact)).unwrap();
                    self.graph.rhs_births.insert(fact, rid, table, root, root && self.stage_spine.anchor_at(rid, op));
                }
            }
        }
        self.graph.release_empty(cell);
        Ok(())
    }
}

#[cfg(all(test, feature = "sparse-cells"))]
mod tests {
    use super::*;
    use crate::{cell::{CompletedEffects, EffectPlan, Effects}, slots::Slots};

    fn fixture(ops: Vec<Op>) -> (Executor, Execution) {
        let mut host = Executor::new(crate::query::test_projection_graph(), false);
        let template = Template {
            name: "owned-effect-boundaries".into(),
            sorts: vec![json!({"kind":"i64"}); 4],
            defs: ops.iter().enumerate().filter_map(|(i, op)|
                if let Op::Let(dst, ..) = op { Some((*dst, i)) } else { None }).collect(),
            parent_columns: BTreeMap::new(), ops: ops.into(),
        };
        host.graph.program.executions.push(crate::cell::execution::Plan::derive(
            &host.graph.program.tables, &template, &[0, 1]));
        host.graph.program.templates.push(template);
        host.graph.program.rules.push(Rule { template: 0, query: Rc::new(vec![]),
            inputs: vec![0, 1].into(), completion: Default::default(), seminaive: false, direct: None });
        let ops = host.graph.program.templates[0].ops.clone();
        host.graph.program.known_results.static_skip.push(Rc::new(vec![false; ops.len()]));
        let plan = Rc::new(EffectPlan::compile(&host.graph.program, 0, &[], 0, true));
        let mut values = Slots::with_capacity(8);
        values.extend([(0, Value::Int(1)), (1, Value::Int(2))]);
        let cell = host.graph.begin_transient(0, values, None).unwrap();
        host.cell_execution = Some(crate::cell::execution::runtime::State { grain: 64, counts: Default::default() });
        let execution = Execution {
            rule: 0, cell, phase: Phase::Ready, ops, aliases: None, known: QueryFacts::None,
            cursor: None, effects: Effects::begin(plan, vec![], false), continuation: true, work: Work::default(),
            #[cfg(feature = "view-consumers")]
            view_source: None,
            transfers: Default::default(), transfer: 0,
            #[cfg(feature = "structural-depth")]
            proven: vec![],
            #[cfg(all(feature = "rhs-work-audit", feature = "rhs-locals"))]
            inspect_births: (None, false),
        };
        (host, execution)
    }
    fn keys() -> Vec<Arg> { vec![Arg::Slot(0), Arg::Slot(1)] }

    #[test]
    fn boundary_return_keeps_the_original_slots_receipts_and_source_position() {
        let (mut host, mut execution) = fixture(vec![
            Op::Let(2, Call::Table(0), keys()),
            Op::Let(3, Call::Primitive("+".into(), "i64".into()), vec![Arg::Slot(2), Arg::Literal(Value::Int(1))]),
            Op::Set(1, keys(), Arg::Slot(3)),
        ]);
        let key = vec![Value::Int(1), Value::Int(2)];
        host.graph.set_function(0, key.clone(), Value::Int(5)).unwrap();
        let cell = execution.cell;
        let allocation = std::ptr::from_ref(host.graph.rhs_frame(cell).unwrap().values.get(&0).unwrap());
        let reads = host.graph.key_lookup_calls.get();
        for _ in 0..3 { assert_eq!(host.advance_cell(&mut execution).unwrap(), Frontier::Boundary(0)); }
        assert_eq!(host.graph.key_lookup_calls.get(), reads, "offering a read does not execute it");
        // Return the complete execution owner to a caller. No live stack-local
        // transfer iterator, Cursor borrow or result buffer is required.
        let mut pending = Some(execution);
        host.graph.set_function(0, key.clone(), Value::Int(9)).unwrap();
        let mut execution = pending.take().unwrap();
        host.resolve_cell_boundary(&mut execution, 0).unwrap();
        let witness = host.graph.lookup_canonical(0, &key).unwrap().unwrap().witness;
        assert_eq!(execution.effects.get(0), Some(witness));
        assert_eq!(host.advance_cell(&mut execution).unwrap(), Frontier::Boundary(2));
        assert_eq!(host.graph.slot(cell, 3).unwrap(), Value::Int(10));
        assert_eq!(std::ptr::from_ref(host.graph.rhs_frame(cell).unwrap().values.get(&0).unwrap()), allocation);
        assert!(host.resolve_cell_boundary(&mut execution, 0).unwrap_err().contains("stale"));
        host.resolve_cell_boundary(&mut execution, 2).unwrap();
        let updates = host.graph.stats.function_updates;
        assert!(host.resolve_cell_boundary(&mut execution, 2).is_err());
        assert_eq!(host.graph.stats.function_updates, updates);
        assert_eq!(execution.work.updates, 1, "unrelated work while parked is not charged to this Cell");
        assert_eq!(execution.effects.get(0), Some(witness));
        assert_eq!(host.advance_cell(&mut execution).unwrap(), Frontier::Complete);
        host.finish_cell(execution).unwrap();
        assert_eq!(host.continuation_stats.function_updates, 1);
        assert_eq!(host.graph.lookup_canonical(1, &key).unwrap().unwrap().values.last(), Some(&Value::Int(10)));
    }

    #[test]
    fn failed_or_stopped_execution_cannot_commit_or_replay_a_later_effect() {
        for fail in [false, true] {
            let stop = if fail { Op::Panic } else { Op::Hide(0, keys(), true) };
            let (mut host, mut execution) = fixture(vec![
                Op::Set(1, keys(), Arg::Literal(Value::Int(7))), stop,
                Op::Set(1, keys(), Arg::Literal(Value::Int(99))),
            ]);
            assert_eq!(host.advance_cell(&mut execution).unwrap(), Frontier::Boundary(0));
            host.resolve_cell_boundary(&mut execution, 0).unwrap();
            assert_eq!(host.advance_cell(&mut execution).unwrap(), Frontier::Boundary(1));
            let result = host.resolve_cell_boundary(&mut execution, 1);
            if fail {
                assert_eq!(result.unwrap_err(), "source panic");
                assert_eq!(execution.phase, Phase::Failed);
                assert!(host.advance_cell(&mut execution).is_err());
                assert!(host.resolve_cell_boundary(&mut execution, 1).is_err());
                assert!(host.resolve_cell_boundary(&mut execution, 2).is_err());
                assert_eq!(host.graph.rhs_frame(execution.cell).unwrap().completed_prefix, 1);
            } else {
                result.unwrap();
                assert_eq!(host.advance_cell(&mut execution).unwrap(), Frontier::Stopped);
                assert!(host.resolve_cell_boundary(&mut execution, 2).is_err());
                assert_eq!(host.graph.rhs_frame(execution.cell).unwrap().completed_prefix, 2);
                host.finish_cell(execution).unwrap();
            }
            let row = host.graph.lookup_canonical(1, &[Value::Int(1), Value::Int(2)]).unwrap().unwrap();
            assert_eq!(row.values.last(), Some(&Value::Int(7)));
        }
    }
}
