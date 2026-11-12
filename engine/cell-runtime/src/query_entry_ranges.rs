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
}
enum Members<'a> {
    Slice { rows: &'a [(u64, Dependency)], dead: &'a [u64], offset: usize },
    Tree(&'a std::collections::BTreeSet<(u64, Dependency)>),
}
pub(super) struct Chunk<'a> {
    range: &'a Range,
    source: usize,
    members: Members<'a>,
}
impl Workers {
    pub(super) fn enqueue_entry_range(&mut self, code: usize,
        batch: crate::entry_schedule::Batch<'_>, watermark: u64, known: &QueryFacts) {
        let rid = self.cell_codes[code].rule;
        self.rule_facts[rid].get_or_insert_with(|| RuleRun {
            facts: known.clone(), watermark, first_source: self.next_source,
        });
        self.entry_ranges.push(Range { node: batch.range_node(), code, watermark, source: self.next_source });
        self.next_source += batch.range_len();
        self.stats.entry_range_descriptors += 1;
    }
    pub(super) fn clear_entry_ranges(&mut self) {
        for r in self.entry_ranges.drain(..) { self.rule_facts[self.cell_codes[r.code].rule] = None; }
    }
}
pub(super) fn borrow<'a>(ranges: &'a [Range], scheduler: &'a crate::entry_schedule::Scheduler,
    grain: usize) -> Vec<Chunk<'a>> {
    let mut out = Vec::new();
    for range in ranges {
        let mut source = range.source;
        for run in scheduler.read_ranges(range.node, range.watermark) {
            match run {
                OrderedRun::Run { rows, dead, .. } => {
                    for (i, rows) in rows.chunks(grain).enumerate() {
                        let offset = i * grain;
                        out.push(Chunk { range, source: source + offset,
                            members: Members::Slice { rows, dead, offset } });
                    }
                }
                OrderedRun::Tree(rows) => out.push(Chunk { range, source, members: Members::Tree(rows) }),
            }
            source += run.span_len();
        }
    }
    out
}
type Completed = (Vec<(usize, Binding)>, Option<((usize, bool, Dependency, usize), String)>, Counts,
    Option<usize>, expansion::ChunkWork, f64, Option<usize>);
pub(super) fn run(job: &Chunk<'_>, codes: &[CellCode], positions: &[usize],
    prepared: &[expansion::Prepared<'_>], reads: &crate::graph::query_reads::QueryReads<'_>,
    facts: &[Option<RuleRun>], local: &[crate::cell::execution::Plan], templates: &[Template],
    key_nodes: &J, pooled: bool) -> Completed {
    with_worker_frame(|frame| {
        let clock = Instant::now();
        let code = &codes[job.range.code];
        let known = facts[code.rule].as_ref().expect("active range");
        let mut counts = Counts { chunks: 1, ..Default::default() };
        frame.prepare(code.slots, code.reads, &mut counts);
        let mut residual = expansion::ChunkWork::default();
        let mut answers = Vec::new();
        let mut error = None;
        let mut visit = |i, witness| {
            counts.entry_range_rows += 1;
            let source = job.source + i;
            let result = (|| {
                let row = reads.row(witness)?.ok_or("Entry disappeared from sealed Run")?;
                if row.hidden || row.epoch < job.range.watermark {
                    return Err("Entry visibility changed in sealed Run".into());
                }
                let q = QueryRead { source, order: source, code, row: &row,
                    expansion: positions[job.range.code], filter: true,
                    #[cfg(feature = "cell-query-sharing-audit")]
                    audit_cell: (code.template, witness),
                };
                prepared[q.expansion].evaluate(&q, reads, key_nodes, known, frame,
                    &mut residual, &mut answers, &local[code.rule], &templates[code.template])
            })();
            if let Err(e) = result {
                if error.is_none() { error = Some(((known.first_source, true, Dependency::Function(source),0), e)); }
            }
        };
        match &job.members {
            Members::Slice { rows, dead, offset } => {
                for (i, &(_, w)) in rows.iter().enumerate() {
                    let at = offset + i;
                    if dead.get(at / 64).is_none_or(|bits| bits & (1 << (at % 64)) == 0) { visit(i, w); }
                }
            }
            Members::Tree(rows) => { for (i, &(_, w)) in rows.iter().enumerate() { visit(i, w); } }
        }
        counts.completion_headers = answers.len() as u64;
        counts.output_buffer_capacity = answers.capacity() as u64;
        counts.frame_capacity_bytes = frame.bytes();
        residual.counts.frame_capacity_bytes = frame.bytes();
        (answers, error, counts, pooled.then(rayon::current_thread_index).flatten(), residual,
            clock.elapsed().as_secs_f64(), Some(job.range.code))
    })
}
