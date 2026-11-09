use super::*;
use crate::local_rhs::{Block, Counts};

pub(crate) enum Start {
    Complete { cell: u32, frame: Cell },
    Promoted { cell: u32, next_op: usize },
}
impl Graph {
    pub(crate) fn local_rhs(
        &mut self,
        template: usize,
        values: crate::slots::Slots,
        parent: Option<FactRef>,
        plan: &Block,
        receipts: &mut crate::cell::Effects,
        stats: &mut Counts,
    ) -> Result<Start> {
        let cell = self.reserve_cell_id()?;
        let mut frame = self.new_cell(template, values, parent);
        let mut local_lets = 0;
        let ops = self.program.templates[template].ops.clone();
        stats.enter += 1;
        for step in &plan.steps {
            self.known_stats.static_eliminated += step.skip_before;
            self.known_stats.avoided_lookups += step.skip_before;
            let instruction = &ops[step.op];
            let (table, args) = match instruction {
                Op::Let(_, Call::Table(t), args) | Op::Set(t, args, _) => (*t, args),
                _ => unreachable!("validated local Cell operation"),
            };
            let key: smallvec::SmallVec<[Value; 4]> = self.frame_arguments(cell, &frame, None, args)?;
            if matches!(instruction, Op::Let(..)) {
                self.stats.constructor_requests += 1;
            }
            let assigned = if let Op::Set(_, _, v) = instruction {
                Some(self.argument_in(cell, &frame, None, v)?)
            } else {
                None
            };
            if let Some(row) = self.lookup_canonical(table, &key)? {
                let value = row.values.last().unwrap();
                match instruction {
                    Op::Let(s, ..) => {
                        frame.values.insert(*s, value.clone());
                        self.stats.constructor_reused += 1;
                        local_lets += 1;
                        stats.local_let_results += 1;
                    }
                    Op::Set(..) => {
                        let rhs = assigned.unwrap();
                        if *value == rhs {
                            stats.no_op_unions += 1;
                        } else {
                            self.enqueue_union(value.clone(), rhs)?;
                            stats.ordered_unions += 1;
                        }
                    }
                    _ => unreachable!("validated local Cell operation"),
                }
                receipts.record(step.op, row.witness);
            } else {
                self.store_cell(cell, frame);
                let fact = FactRef {
                    cell,
                    op: step.op as u32,
                };
                match instruction {
                    Op::Let(s, ..) => {
                        self.insert_constructor(cell, step.op, table, &key, *s)?;
                    }
                    Op::Set(..) => {
                        self.activate(fact, table, &key, assigned.unwrap(), false)?;
                    }
                    _ => unreachable!("validated local Cell operation"),
                }
                receipts.record(step.op, Dependency::Fact(fact));
                stats.promoted += 1;
                stats.prefix_lets_on_promotion += local_lets;
                return Ok(Start::Promoted {
                    cell,
                    next_op: step.op + 1,
                });
            }
        }
        self.known_stats.static_eliminated += plan.trailing_aliases;
        self.known_stats.avoided_lookups += plan.trailing_aliases;
        stats.local_complete += 1;
        stats.block_local_intermediates += plan.intermediate_ops.len() as u64;
        self.stats.rhs_frames_avoided += 1;
        Ok(Start::Complete { cell, frame })
    }
}
