//! Compiled Cell point queries borrow existing published Entry ranges. Only successful
//! instances recover a source Cursor; negative entries never allocate one.
use super::*;
use crate::ordered_run::OrderedRun;

pub(super) struct Range {
    node: usize,
    code: usize,
    watermark: u64,
    support: Option<(usize, usize, usize)>,
}
enum Members<'a> {
    Slice {
        rows: &'a [(u64, Dependency)],
        dead: &'a [u64],
        offset: usize,
    },
    Tree(&'a BTreeSet<(u64, Dependency)>),
}
pub(super) struct Task<'a> {
    pub(super) code: usize,
    rows: crate::entry_schedule::ReadEntries<'a>,
    members: Members<'a>,
    index: crate::query::snapshot::EntryHashes<'a>,
    filter: crate::sieve::EntryFilter<'a>,
    support: Option<crate::query::snapshot::KeySupport<'a>>,
    support_requested: bool,
}
pub(super) struct Done {
    pub code: usize,
    pub answers: Vec<(Dependency, Binding)>,
    pub error: Option<(Dependency, String)>,
    pub counts: Counts,
    pub probes: u64,
    pub rejected: u64,
    pub worker: Option<usize>,
}
impl Workers {
    pub(crate) fn admit_owned_pivot(&mut self, g: &Graph, rid: usize, pivot: usize) -> bool {
        if !self.expansion.enabled || !self.admit_spine_rule(g, rid) {
            return false;
        }
        if self.cell_plans[rid]
            .as_ref()
            .and_then(|p| p.entries[pivot])
            .is_none()
        {
            return false;
        }
        // A canonical, repaired graph has one live row per exact constructor
        // or function key. Valid cached witnesses name that same current row.
        // Local witness shortcuts remain excluded by CellPlan::compile.
        g.query_reads(&[], &mut self.stats.admission_table_checks)
            .is_some_and(|r| r.canonical_rows())
    }
    pub(crate) fn enqueue_owned_range(
        &mut self,
        g: &Graph,
        rid: usize,
        pivot: usize,
        node: usize,
        count: usize,
        watermark: u64,
        known: &QueryFacts,
        support: Option<(usize, usize, usize)>,
    ) {
        let first_source = self.next_source;
        self.next_source += count;
        let code = self.cell_plans[rid].as_ref().unwrap().entries[pivot].unwrap();
        if !self.prepare_first_read(g, code) {
            return;
        }
        self.rule_facts[rid].get_or_insert_with(|| RuleRun {
            facts: known.clone(),
            watermark,
            first_source,
        });
        self.owned_ranges.push(Range {
            node,
            code,
            watermark,
            support,
        });
        self.stats.owned_range_descriptors += 1;
    }
    pub(super) fn clear_owned_ranges(&mut self) {
        for r in self.owned_ranges.drain(..) {
            self.rule_facts[self.cell_codes[r.code].rule] = None;
        }
    }
}
pub(super) fn borrow<'a>(
    ranges: &[Range],
    codes: &[CellCode],
    scheduler: &'a crate::entry_schedule::Scheduler,
    index: &'a crate::query::QueryIndexes,
    sieve: &'a crate::sieve::Sieve,
    versions: &[u64],
    grain: usize,
) -> Vec<Task<'a>> {
    let mut tasks = Vec::new();
    for r in ranges {
        let code = &codes[r.code];
        let table = scheduler.range_table(r.node);
        let make = |members| Task {
            code: r.code,
            rows: scheduler.read_entries(r.node),
            members,
            index: index.read_entry_hashes(table),
            filter: sieve.entry_filter(code.rule, code.pivot),
            support: r.support.and_then(|s| index.read_key_support(versions, s)),
            support_requested: r.support.is_some(),
        };
        for run in scheduler.read_ranges(r.node, r.watermark) {
            match run {
                OrderedRun::Run { rows, dead, .. } => {
                    for (i, rows) in rows.chunks(grain).enumerate() {
                        tasks.push(make(Members::Slice {
                            rows,
                            dead,
                            offset: i * grain,
                        }));
                    }
                }
                OrderedRun::Tree(rows) => tasks.push(make(Members::Tree(rows))),
                OrderedRun::Held=>panic!("query cannot observe held Unit membership"),
            }
        }
    }
    tasks
}
pub(super) fn run(
    task: &Task<'_>,
    codes: &[CellCode],
    facts: &[Option<RuleRun>],
    reads: &crate::graph::query_reads::QueryReads<'_>,
    key_nodes: &J,
    local: &[crate::cell::execution::Plan],
    templates: &[Template],
    first_reads: &FirstReads,
    pooled: bool,
) -> Done {
    with_worker_frame(|frame| {
        let code = &codes[task.code];
        let known = facts[code.rule].as_ref().unwrap();
        let mut done = Done {
            code: task.code,
            answers: Vec::new(),
            error: None,
            counts: Counts {
                chunks: 1,
                ..Default::default()
            },
            probes: 0,
            rejected: 0,
            worker: pooled.then(rayon::current_thread_index).flatten(),
        };
        frame.prepare(code.slots, code.reads, &mut done.counts);
        let mut selection=Default::default();
        let mut visit = |w| {
            done.counts.owned_range_rows += 1;
            if !task
                .filter
                .allow(task.index.get(w), &mut done.probes, &mut done.rejected)
            {
                return;
            }
            let row = task.rows.row(w).expect("sealed owned Entry");
            if task.support_requested {
                done.counts.owned_support_checks += 1;
                if let Some(support) = &task.support {
                    if !support.present(row) {
                        done.counts.owned_support_rejections += 1;
                        return;
                    }
                } else {
                    done.counts.owned_support_unavailable += 1;
                }
            }
            done.counts.entries += 1;
            let entry = Entry {
                values: &row.values,
                epoch: row.epoch,
                witness: w,
            };
            let result = evaluate(
                &code.query,
                &entry,
                code.pivot,
                reads,
                key_nodes,
                true,
                code.first_read
                    .map(|id| first_reads.results[id].as_ref().unwrap()),
                &mut frame.values,
                &mut frame.witnesses,
                &mut frame.constructors,
                &mut done.counts,
                #[cfg(feature = "cell-query-sharing-audit")]
                None,
            );
            match result {
                Ok(Some(epoch)) if epoch >= known.watermark => {
                    let mut answer = Binding::matched(
                        local[code.rule].slots(
                            code.inputs
                                .iter()
                                .zip(&code.query.inputs)
                                .map(|(&slot, f)| {
                                    (
                                        slot,
                                        f.operand_in(
                                            reads.parents,
                                            |col| &entry.values[col],
                                            &frame.values,
                                            None,
                                        )
                                        .into_owned(),
                                    )
                                }),
                            &mut done.counts.execution,
                        ),
                        known.facts.with_rows(frame.witnesses.iter().copied()),
                        epoch,
                    );
                    local[code.rule].prepare_with_reads(
                        &templates[code.template],
                        &mut answer,
                        Some(reads),
                        &mut done.counts.execution,
                    );
                    if let Some(plan) = &local[code.rule].constructor {
                        plan.complete(
                            &mut answer,
                            Some(reads),
                            &mut frame.constructors,
                            &mut done.counts.constructors,
                            &mut done.counts.execution,
                            &mut selection,
                        );
                    }
                    done.counts.answers += 1;
                    if done.answers.len() == done.answers.capacity() {
                        done.counts.answer_buffer_allocations += 1;
                    }
                    done.answers.push((w, answer));
                }
                Err(error) => {
                    if done.error.as_ref().is_none_or(|(old, _)| w < *old) {
                        done.error = Some((w, error));
                    }
                }
                _ => (),
            }
        };
        match &task.members {
            Members::Slice { rows, dead, offset } => {
                for (i, &(_, w)) in rows.iter().enumerate() {
                    let at = offset + i;
                    if dead.get(at / 64).is_none_or(|b| b & (1 << (at % 64)) == 0) {
                        visit(w);
                    }
                }
            }
            Members::Tree(rows) => {
                for &(_, w) in *rows {
                    visit(w);
                }
            }
        }
        done.counts.completion_headers = done.answers.len() as u64;
        done.counts.output_buffer_capacity = done.answers.capacity() as u64;
        done.counts.frame_capacity_bytes = frame.bytes();
        done
    })
}
