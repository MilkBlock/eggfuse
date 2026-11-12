//! Entry membership stays in the scheduler's immutable epoch runs. A worker
//! enumerates its slice, reads the actual row and continues the compiled Cell.
//! No Rc, per-entry task header or copy of the input bindings is needed.
use super::*;
use crate::ordered_run::OrderedRun;

pub(super) struct Range {
    node: usize,
    code: usize,
    watermark: u64,
    source: usize,
    // Only addresses accepted by source routing. The original Entry rows and
    // bindings are not copied. None means the entire epoch membership range.
    selected: Option<std::ops::Range<usize>>,
}
enum Members<'a> {
    Slice {
        rows: &'a [(u64, Dependency)],
        dead: &'a [u64],
        offset: usize,
    },
    Tree(&'a std::collections::BTreeSet<(u64, Dependency)>),
    Selected(&'a [Dependency]),
}
pub(super) struct Chunk<'a> {
    range: &'a Range,
    source: usize,
    members: Members<'a>,
    rows: crate::entry_schedule::ReadEntries<'a>,
}
impl Chunk<'_> {
    pub(super) fn code(&self) -> usize {
        self.range.code
    }
    pub(super) fn len(&self) -> usize {
        match &self.members {
            Members::Slice { rows, .. } => rows.len(),
            Members::Tree(rows) => rows.len(),
            Members::Selected(rows) => rows.len(),
        }
    }
}
impl Workers {
    pub(super) fn active_partitioned_ranges(&self) -> bool {
        self.entry_ranges.iter().any(|r| r.selected.is_some())
    }
    pub(super) fn enqueue_entry_range(
        &mut self,
        code: usize,
        batch: crate::entry_schedule::Batch<'_>,
        watermark: u64,
        known: &QueryFacts,
    ) {
        let rid = self.cell_codes[code].rule;
        self.rule_facts[rid].get_or_insert_with(|| RuleRun {
            facts: known.clone(),
            watermark,
            first_source: self.next_source,
        });
        self.entry_ranges.push(Range {
            node: batch.range_node(),
            code,
            watermark,
            source: self.next_source,
            selected: None,
        });
        self.next_source += batch.range_len();
        self.stats.entry_range_descriptors += 1;
    }
    pub(super) fn enqueue_selected_entry(
        &mut self,
        code: usize,
        node: usize,
        watermark: u64,
        witness: Dependency,
        known: &QueryFacts,
    ) {
        let rid = self.cell_codes[code].rule;
        self.rule_facts[rid].get_or_insert_with(|| RuleRun {
            facts: known.clone(),
            watermark,
            first_source: self.next_source,
        });
        // One routing callback delivers a contiguous source interval. Never
        // join intervals separated by another query: source ordinals govern
        // stable winner and error selection.
        let append = self.entry_ranges.last().is_some_and(|r| {
            r.node == node
                && r.code == code
                && r.watermark == watermark
                && r.selected.as_ref().is_some_and(|s| {
                    r.source + s.len() == self.next_source
                        && s.end == self.selected_entry_rows.len()
                })
        });
        if !append {
            let start = self.selected_entry_rows.len();
            self.entry_ranges.push(Range {
                node,
                code,
                watermark,
                source: self.next_source,
                selected: Some(start..start),
            });
            self.stats.entry_range_descriptors += 1;
            self.stats.selected_range_descriptors += 1;
        }
        let rows = &mut self.selected_entry_rows;
        let capacity = rows.capacity();
        rows.push(witness);
        self.stats.selected_range_growths += u64::from(rows.capacity() != capacity);
        self.stats.selected_range_growth_bytes +=
            ((rows.capacity() - capacity) * std::mem::size_of::<Dependency>()) as u64;
        self.stats.selected_range_entries += 1;
        self.entry_ranges
            .last_mut()
            .unwrap()
            .selected
            .as_mut()
            .unwrap()
            .end = rows.len();
        self.next_source += 1;
    }
    pub(super) fn clear_entry_ranges(&mut self) {
        for r in self.entry_ranges.drain(..) {
            self.rule_facts[self.cell_codes[r.code].rule] = None;
        }
        self.selected_entry_rows.clear();
    }
}
pub(super) fn borrow<'a>(
    ranges: &'a [Range],
    scheduler: &'a crate::entry_schedule::Scheduler,
    selected: &'a [Dependency],
    grain: usize,
) -> Vec<Chunk<'a>> {
    let mut out = Vec::new();
    for range in ranges {
        let entries = scheduler.read_entries(range.node);
        if let Some(selection) = &range.selected {
            for (i, rows) in selected[selection.clone()].chunks(grain).enumerate() {
                out.push(Chunk {
                    range,
                    source: range.source + i * grain,
                    members: Members::Selected(rows),
                    rows: entries,
                });
            }
            continue;
        }
        let mut source = range.source;
        for run in scheduler.read_ranges(range.node, range.watermark) {
            match run {
                OrderedRun::Run { rows, dead, .. } => {
                    for (i, rows) in rows.chunks(grain).enumerate() {
                        let offset = i * grain;
                        out.push(Chunk {
                            range,
                            source: source + offset,
                            members: Members::Slice { rows, dead, offset },
                            rows: entries,
                        });
                    }
                }
                OrderedRun::Tree(rows) => out.push(Chunk {
                    range,
                    source,
                    members: Members::Tree(rows),
                    rows: entries,
                }),
                OrderedRun::Held => panic!("query cannot observe held Unit membership"),
            }
            source += run.span_len();
        }
    }
    out
}
pub(super) struct Completed {
    pub answers: Vec<(usize, Binding)>,
    // End position and compiled code for each nonempty answer span. No extra
    // code/source wrapper is copied into each successful instance.
    pub origins: smallvec::SmallVec<[(usize, usize); 4]>,
    pub error: Option<((usize, bool, Dependency, usize), String)>,
    pub counts: Counts,
    pub worker: Option<usize>,
    pub residual: expansion::ChunkWork,
    pub seconds: f64,
}
pub(super) fn run(
    jobs: &[Chunk<'_>],
    codes: &[CellCode],
    positions: &[usize],
    prepared: &[expansion::Prepared<'_>],
    reads: &crate::graph::query_reads::QueryReads<'_>,
    facts: &[Option<RuleRun>],
    local: &[crate::cell::execution::Plan],
    templates: &[Template],
    key_nodes: &J,
    pooled: bool,
) -> Completed {
    with_worker_frame(|frame| {
        let clock = Instant::now();
        let mut counts = Counts {
            chunks: 1,
            ..Default::default()
        };
        let (slots, reads_needed) = jobs.iter().fold((0, 0), |(slots, reads), job| {
            let code = &codes[job.code()];
            (slots.max(code.slots), reads.max(code.reads))
        });
        frame.prepare(slots, reads_needed, &mut counts);
        let mut residual = expansion::ChunkWork::default();
        let mut answers = Vec::new();
        let mut error = None;
        let mut origins = smallvec::SmallVec::<[(usize, usize); 4]>::new();
        for job in jobs {
            let code = &codes[job.range.code];
            let known = facts[code.rule].as_ref().expect("active range");
            let first = answers.len();
            let mut visit = |i, witness| {
                counts.entry_range_rows += 1;
                let source = job.source + i;
                let result = (|| {
                    // Refresh sealed this Entry before admission. Read that same
                    // row instead of decoding it again or cloning a SharedRow for
                    // each task. The scheduler cannot publish while it is borrowed.
                    let row = job
                        .rows
                        .row(witness)
                        .ok_or("Entry disappeared from sealed Run")?;
                    if row.hidden || row.epoch < job.range.watermark {
                        return Err("Entry visibility changed in sealed Run".into());
                    }
                    counts.entry_range_row_borrows += 1;
                    let q = QueryRead {
                        source,
                        order: source,
                        code,
                        row,
                        expansion: positions[job.range.code],
                        filter: job.range.selected.is_none(),
                        #[cfg(feature = "cell-query-sharing-audit")]
                        audit_cell: (code.template, witness),
                    };
                    prepared[q.expansion].evaluate(
                        &q,
                        reads,
                        key_nodes,
                        known,
                        frame,
                        &mut residual,
                        &mut answers,
                        &local[code.rule],
                        &templates[code.template],
                    )
                })();
                if let Err(e) = result {
                    let order = (known.first_source, true, Dependency::Function(source), 0);
                    if error.as_ref().is_none_or(|(old, _)| order < *old) {
                        error = Some((order, e));
                    }
                }
            };
            match &job.members {
                Members::Slice { rows, dead, offset } => {
                    for (i, &(_, w)) in rows.iter().enumerate() {
                        let at = offset + i;
                        if dead
                            .get(at / 64)
                            .is_none_or(|bits| bits & (1 << (at % 64)) == 0)
                        {
                            visit(i, w);
                        }
                    }
                }
                Members::Tree(rows) => {
                    for (i, &(_, w)) in rows.iter().enumerate() {
                        visit(i, w);
                    }
                }
                Members::Selected(rows) => {
                    for (i, &w) in rows.iter().enumerate() {
                        visit(i, w);
                    }
                }
            }
            if first != answers.len() {
                if let Some((end, _)) = origins
                    .last_mut()
                    .filter(|(_, code)| *code == job.range.code)
                {
                    *end = answers.len();
                } else {
                    origins.push((answers.len(), job.range.code));
                }
            }
        }
        counts.range_answer_span_bytes =
            (origins.capacity() * std::mem::size_of::<(usize, usize)>()) as u64;
        counts.range_answer_span_heap_bytes = if origins.spilled() {
            counts.range_answer_span_bytes
        } else {
            0
        };
        counts.completion_headers = answers.len() as u64;
        counts.output_buffer_capacity = answers.capacity() as u64;
        counts.frame_capacity_bytes = frame.bytes();
        residual.counts.frame_capacity_bytes = frame.bytes();
        Completed {
            answers,
            origins,
            error,
            counts,
            worker: pooled.then(rayon::current_thread_index).flatten(),
            residual,
            seconds: clock.elapsed().as_secs_f64(),
        }
    })
}
