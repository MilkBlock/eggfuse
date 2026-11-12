//! Scalar Cell RHS ownership. Workers compute every candidate, including
//! duplicates, then mutate the authoritative function rows. A losing Cell's
//! private slots are discarded; no effect program returns for source replay.
//! Only the final writer is observable before the next Run. Source-position
//! receipts and logical improvements remain available for ordered publication.
use super::*;
use crate::{physical_plan::ScalarMerge, slots::Slots};
use rayon::prelude::*;

#[derive(Default, Serialize)]
pub(crate) struct Counts {
    pub batches: u64,
    pub direct_batches: u64,
    pub candidates: u64,
    pub duplicate_targets: u64,
    pub rows: u64,
    pub new_rows: u64,
    pub row_writes: u64,
    pub logical_improvements: u64,
    pub invalidated: u64,
    pub superseded_improvements: u64,
    pub worker_rows: u64,
    pub worker_candidates: u64,
    pub writer_allocations: u64,
    pub writer_reuses: u64,
    pub preparation_ns: u64,
    pub execution_ns: u64,
    pub boundary_ns: u64,
    pub source_completion_ns: u64,
    pub temporary_bytes: u64,
    pub fallback_batches: u64,
}
pub(crate) struct Task {
    pub values: Slots,
    pub parent: Option<FactRef>,
    pub key: Value,
    pub value: i64,
    pub destination: Option<usize>,
    pub cell: u32,
    pub index: usize,
    pub ordinal: usize,
    pub changed: bool,
    old: Option<i64>,
    #[cfg(feature = "slot-transfer-audit")]
    pub source: Option<(u64, usize)>,
}
impl Task {
    pub(crate) fn new(
        values: Slots,
        key: Value,
        value: i64,
        destination: Option<usize>,
        ordinal: usize,
    ) -> Self {
        Self {
            values,
            parent: None,
            key,
            value,
            destination,
            cell: 0,
            index: 0,
            ordinal,
            changed: false,
            old: None,
            #[cfg(feature = "slot-transfer-audit")]
            source: None,
        }
    }
    #[cfg(feature = "slot-transfer-audit")]
    pub(crate) fn audit(&self, epoch: u64, table: usize) -> Result<()> {
        crate::transfer_audit::restore_source(self.source);
        if self.changed {
            crate::transfer_audit::effective(
                epoch,
                table,
                self.index,
                std::slice::from_ref(&self.key),
                self.old.map(Value::Int).as_ref(),
                &Value::Int(self.value),
            )?;
        }
        Ok(())
    }
}
struct Finished {
    index: usize,
    new: bool,
    updates: u64,
    merges: u64,
    unchanged: u64,
    prior: Option<Previous>,
    reused: bool,
    worker: bool,
}
enum Previous {
    Retained(FactRef, Option<Box<writer_frames::Writer>>),
    Reused(FactRef, Option<FactRef>),
}

impl Graph {
    pub(crate) fn worker_write_capacity(&self, count: usize) -> bool {
        u32::try_from(count)
            .ok()
            .and_then(|n| self.next_cell.checked_add(n))
            .is_some()
            && self
                .functions
                .len()
                .checked_add(count)
                .is_some_and(|n| n < u32::MAX as usize)
    }
    pub(crate) fn worker_write_parent(&self, parent: Option<FactRef>) -> bool {
        // Constructor-backed parent fields are immutable throughout this
        // scalar-only batch. An inline mutable writer needs its source path.
        parent.is_none_or(|p| {
            self.writer_dir.get(p.cell).is_none() && self.cells.contains_key(&p.cell)
        })
    }
    pub(crate) fn worker_write_supported(&self, rid: usize) -> bool {
        self.scalar_merge
            && self.program.writes[rid].as_ref().is_some_and(|w| {
                w.ports.is_some()
                    && self.program.physical.merges[w.table].is_some()
                    && !self.units.owned[w.table]
            })
            && self.functions.len() < u32::MAX as usize
    }

    /// Shared key/identity allocation is the boundary. Duplicate keys join the
    /// same destination without rejecting the batch or waiting for computation.
    /// Keys are resolved before allocation; values run on workers either here
    /// or in the checked-arithmetic prepass.
    pub(crate) fn write_cells(
        &mut self,
        rid: usize,
        tasks: &mut [Task],
        pool: &rayon::ThreadPool,
        counts: &mut Counts,
        evaluate: Option<bool>,
    ) -> Result<()> {
        let boundary = std::time::Instant::now();
        let write = self.program.writes[rid].as_ref().unwrap();
        let (table, operation) = (write.table, write.op);
        let ports = write.ports.as_ref().unwrap();
        let template = self.program.rules[rid].template;
        let parent_columns = &self.program.templates[template].parent_columns;
        let merge = self.program.physical.merges[table].unwrap();
        let epoch = self.epoch;
        let length = u32::try_from(tasks.len()).map_err(|_| "Cell identity exhausted")?;
        let end = self
            .next_cell
            .checked_add(length)
            .ok_or("Cell identity exhausted")?;
        let first = self.next_cell;
        self.next_cell = end;
        for (ordinal, task) in tasks.iter_mut().enumerate() {
            task.cell = first + ordinal as u32;
            let key = std::slice::from_ref(&task.key);
            task.index = if let Some(i) = self.function_index(table, key) {
                i
            } else {
                let i = self.functions.len();
                self.function_keys[table].insert(key, i);
                // Reserved storage is exclusively held by this RHS batch. It
                // is never visible to queries or published before initialization.
                self.functions.push(Function {
                    writer: None,
                    #[cfg(feature = "receipt-slots")]
                    port_slot: 0,
                    table,
                    key: key.to_vec(),
                    value: Value::Int(0),
                    epoch,
                    live: false,
                    origin: None,
                });
                self.function_decoded.push(None);
                i
            };
        }
        tasks.sort_unstable_by_key(|task| (task.index, task.ordinal));
        let mut functions = self.functions.as_mut_slice();
        let mut decoded = self.function_decoded.as_mut_slice();
        let mut offset = 0;
        let mut targets = Vec::new();
        for group in tasks.chunk_by_mut(|a, b| a.index == b.index) {
            let skip = group[0].index - offset;
            functions = &mut functions[skip..];
            decoded = &mut decoded[skip..];
            let (f, rest) = functions.split_first_mut().unwrap();
            let (d, rest_d) = decoded.split_first_mut().unwrap();
            functions = rest;
            decoded = rest_d;
            offset = group[0].index + 1;
            let retained = f.origin.is_some_and(|origin| {
                self.parent_users.get(&origin.cell).copied().unwrap_or(0) != 0
            });
            targets.push((f, d, group, retained));
        }
        counts.rows += targets.len() as u64;
        counts.duplicate_targets += (length as usize - targets.len()) as u64;
        counts.temporary_bytes += (targets.capacity()
            * std::mem::size_of::<(&mut Function, &mut Option<RowFields>, &mut [Task], bool)>())
            as u64;
        counts.boundary_ns += boundary.elapsed().as_nanos() as u64;
        let clock = std::time::Instant::now();
        let done: Vec<_> = pool.install(|| {
            targets
                .into_par_iter()
                .with_min_len(16)
                .map(|(f, decoded, group, retained)| {
                    let new = !f.live;
                    let mut current = if new {
                        None
                    } else {
                        let Value::Int(v) = f.value else {
                            unreachable!("typed scalar Cell row")
                        };
                        Some(v)
                    };
                    let mut winner = None;
                    let mut updates = 0;
                    let mut merges = 0;
                    let mut unchanged = 0;
                    // Compute each candidate independently and resolve the short
                    // merge in source order, invalidating superseded private writers.
                    // No worker waits for another Cell's computation or replays RHSs.
                    for (position, task) in group.iter_mut().enumerate() {
                        if let Some(prepared) = evaluate {
                            // Either no arithmetic exists, or the query already
                            // established its result. The typed input read is total.
                            let (value, dst) = ports
                                .project_value(&task.values, prepared)
                                .expect("validated total scalar Cell input");
                            task.value = value;
                            task.destination = dst;
                        }
                        task.old = current;
                        let next = if let Some(old) = current {
                            merges += 1;
                            match merge {
                                ScalarMerge::Old => old,
                                ScalarMerge::Min => old.min(task.value),
                                ScalarMerge::Max => old.max(task.value),
                            }
                        } else {
                            task.value
                        };
                        task.changed = current != Some(next);
                        if task.changed {
                            current = Some(next);
                            winner = Some(position);
                            updates += 1;
                        } else {
                            unchanged += 1;
                        }
                    }
                    let mut reused = false;
                    let prior = if let Some(winner) = winner {
                        let mut old_box = None;
                        let prior = f.origin.take().map(|origin| {
                            let writer = f.writer.take();
                            if !retained && let Some(writer) = writer {
                                let parent = writer.parent;
                                old_box = Some(writer);
                                Previous::Reused(origin, parent)
                            } else {
                                Previous::Retained(origin, writer)
                            }
                        });
                        let task = &mut group[winner];
                        if let Some(dst) = task.destination {
                            task.values.insert(dst, Value::Int(task.value));
                        }
                        let parent = task.parent.filter(|_| !parent_columns.is_empty());
                        if parent.is_some() {
                            for slot in parent_columns.keys() {
                                task.values.remove(slot);
                            }
                        }
                        // Adopt the actual successful query's slot allocation directly.
                        let state = writer_frames::Writer::completed(
                            template,
                            std::mem::take(&mut task.values),
                            parent,
                            epoch,
                            operation + 1,
                        );
                        f.writer = Some(if let Some(mut writer) = old_box {
                            *writer = state;
                            reused = true;
                            writer
                        } else {
                            Box::new(state)
                        });
                        f.origin = Some(FactRef {
                            cell: task.cell,
                            op: operation as u32,
                        });
                        f.value = Value::Int(current.unwrap());
                        f.epoch = epoch;
                        f.live = true;
                        *decoded = Some(Self::shared_fields(&f.key, &f.value));
                        prior
                    } else {
                        None
                    };
                    for task in group.iter_mut() {
                        drop(std::mem::take(&mut task.values));
                    }
                    Finished {
                        index: group[0].index,
                        new,
                        updates,
                        merges,
                        unchanged,
                        prior,
                        reused,
                        worker: rayon::current_thread_index().is_some(),
                    }
                })
                .collect()
        });
        counts.execution_ns += clock.elapsed().as_nanos() as u64;
        counts.temporary_bytes += (done.capacity() * std::mem::size_of::<Finished>()) as u64;
        let boundary = std::time::Instant::now();
        let mut merges = 0;
        let mut unchanged = 0;
        let mut row_writes = 0;
        for result in done {
            merges += result.merges;
            unchanged += result.unchanged;
            counts.worker_rows += u64::from(result.worker);
            counts.new_rows += u64::from(result.new);
            if result.updates == 0 {
                continue;
            }
            row_writes += 1;
            counts.row_writes += 1;
            counts.logical_improvements += result.updates;
            counts.superseded_improvements += result.updates - 1;
            counts.writer_reuses += u64::from(result.reused);
            counts.writer_allocations += u64::from(!result.reused);
            match result.prior {
                Some(Previous::Retained(origin, writer)) => {
                    self.retire_writer(origin, writer);
                }
                Some(Previous::Reused(origin, parent)) => {
                    self.retire_unretained_writer(origin, parent);
                }
                None => (),
            }
            if let Some(parent) = self.functions[result.index].writer.as_ref().unwrap().parent {
                self.retain_reference(parent);
            }
            self.writer_dir
                .register(result.index, self.functions[result.index].origin.unwrap());
            self.changed = true;
            self.stats.function_updates += result.updates;
            self.changes
                .touch(table, Dependency::Function(result.index));
            if result.new {
                self.members[table].insert(result.index as u64);
                let row = self.function(result.index).unwrap();
                self.subscribe(table, row.witness, &row.values);
                self.query_versions[table] += result.updates - 1;
            } else {
                self.query_versions[table] += result.updates;
            }
        }
        self.stats.single_writes += length as u64;
        self.stats.merge_calls += merges;
        self.stats.scalar_merge_calls += merges;
        self.stats.scalar_unchanged += unchanged;
        if merge == ScalarMerge::Old {
            self.stats.scalar_old_projection += merges;
        }
        if let Some(kind) = &self.merge_kinds[table] {
            *self
                .stats
                .merge_contract_calls
                .entry(kind.clone())
                .or_default() += merges;
        }
        self.stats.transient_writes += unchanged;
        self.stats.rhs_frames_avoided += unchanged;
        counts.invalidated += length as u64 - row_writes;
        tasks.sort_unstable_by_key(|task| task.ordinal);
        counts.boundary_ns += boundary.elapsed().as_nanos() as u64;
        Ok(())
    }
}
