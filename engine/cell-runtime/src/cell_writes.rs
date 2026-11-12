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
    pub owner_pool_calls: u64,
    pub owner_candidates: u64,
    pub worker_key_rows: u64,
    pub admission_probes: u64,
    pub new_key_rechecks: u64,
    pub owner_sort_rows: u64,
    pub owner_retired_rows: u64,
    pub owner_completion_groups: u64,
    pub owner_completion_early_groups: u64,
    pub owner_completion_bytes: u64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::rc::Rc;
    fn graph_with_merge(merge: J) -> Graph {
        let eq = json!({"kind":"eq","name":"E"});
        let int = json!({"kind":"i64"});
        let template = Template {
            name: "write-owner".into(),
            sorts: vec![eq.clone(), int.clone()],
            defs: Default::default(),
            parent_columns: Default::default(),
            ops: std::sync::Arc::new(vec![Op::Set(0, vec![Arg::Slot(0)], Arg::Slot(1))]),
        };
        let rule = Rule {
            template: 0,
            query: Rc::new(vec![]),
            inputs: vec![0, 1].into(),
            completion: Default::default(),
            seminaive: false,
            direct: None,
        };
        let mut p:Program = serde_json::from_value(json!({
            "multi_stage":crate::multistage::MultiStage::default(),
            "entry_schedule":crate::entry_schedule::Plan::default(),
            "tables":[{"name":"Score","schema":[eq,int],"constructor":false,"virtual_fact":false,
                "internal":false,"merge":merge}],
            "templates":[template],"rules":[rule],"sets":{},"control":[],"initial":[],"table_templates":[],"artifact":{}
        })).unwrap();
        p.physical = crate::physical_plan::Plan::derive(&p).into();
        p.writes = crate::row_kernel::writes(&p);
        Graph::new(p).unwrap()
    }
    fn graph() -> Graph {
        graph_with_merge(json!({"var":"old"}))
    }
    #[test]
    fn worker_completion_preserves_retained_writers_and_subscription_membership() {
        for workers in [1, 4] {
            let mut g = graph_with_merge(json!({"call":{"primitive":"max","sort":"i64"},
                "args":[{"var":"old"},{"var":"new"}]}));
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(workers)
                .build()
                .unwrap();
            let tasks = |base: i64| {
                (0..128)
                    .map(|i| {
                        Task::new(
                            [(0, Value::Eq(i as u64)), (1, Value::Int(base + i as i64))]
                                .into_iter()
                                .collect(),
                            Value::Int(0),
                            0,
                            None,
                            i,
                        )
                    })
                    .collect::<Vec<_>>()
            };
            let mut counts = Counts::default();
            g.write_cells(0, &mut tasks(0), &pool, &mut counts, Some(false))
                .unwrap();
            let old = g.functions[17].origin.unwrap();
            g.retain_reference(old);
            g.write_cells(0, &mut tasks(1000), &pool, &mut counts, Some(false))
                .unwrap();
            assert_eq!(g.slot(old.cell, 1).unwrap(), Value::Int(17));
            assert_eq!(g.functions[17].value, Value::Int(1017));
            assert!(g.writer_dir.get(old.cell).is_none());
            assert_eq!(g.writer_dir.promoted, 1);
            assert_eq!(g.members[0].len(), 128);
            assert_eq!(g.query_versions[0], 256);
            assert_eq!(g.maintenance_report()["stats"]["live_reverse_edges"], 128);
            assert_eq!(counts.owner_retired_rows, 256);
            assert_eq!(counts.owner_completion_groups, 4);
            g.release_reference(old);
            g.collect_garbage();
            assert!(g.slot(old.cell, 1).is_err());
        }
    }
    #[test]
    fn invalid_parallel_input_never_reserves_ids_or_changes_any_directory() {
        for workers in [1, 4] {
            let mut g = graph();
            let before = g.export().unwrap();
            let next = g.next_cell;
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(workers)
                .build()
                .unwrap();
            let mut tasks: Vec<_> = (0..128)
                .map(|i| {
                    let values = [
                        (
                            0,
                            if i == 17 || i == 97 {
                                Value::Int(9)
                            } else {
                                Value::Eq(i as u64)
                            },
                        ),
                        (1, Value::Int(i as i64)),
                    ]
                    .into_iter()
                    .collect();
                    Task::new(values, Value::Int(0), 0, None, i)
                })
                .collect();
            let mut counts = Counts::default();
            assert_eq!(
                g.write_cells(0, &mut tasks, &pool, &mut counts, Some(false))
                    .unwrap_err(),
                "invalid producer expression port"
            );
            assert_eq!(g.next_cell, next);
            assert!(g.functions.is_empty());
            assert!(g.function_decoded.is_empty());
            assert!(g.changes.is_empty());
            assert_eq!(g.export().unwrap(), before);
            assert_eq!(counts.owner_candidates, 0);
            assert_eq!(counts.row_writes, 0);
            assert_eq!(
                counts.admission_probes, 126,
                "charge valid probes even on failure"
            );
            assert_eq!(counts.worker_key_rows, 126);
            for task in tasks {
                assert!(g.function_index(0, &[task.key]).is_none());
            }
        }
    }
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

struct Target<'a> {
    function: &'a mut Function,
    decoded: &'a mut Option<RowFields>,
    group: &'a mut [Task],
    retained: bool,
    finished: Option<Finished>,
}
struct Completion<'a> {
    lifecycle: writer_frames::Owner<'a>,
    uses: &'a mut HashMap<u64, UseSet>,
    dependencies: &'a mut HashMap<Dependency, smallvec::SmallVec<[u64; 3]>>,
    maintenance: &'a mut maintenance::Metrics,
    members: &'a mut TableRows<u64>,
    version: &'a mut u64,
    changes: &'a mut crate::change_batch::ChangeBatch,
    changed: &'a mut bool,
    parents: &'a Parents,
    counts: &'a mut Counts,
    table: usize,
    merges: u64,
    unchanged: u64,
    row_writes: u64,
}
impl Completion<'_> {
    fn accept(&mut self, target: &mut Target<'_>) {
        let result = target.finished.take().unwrap();
        let index = target.group[0].index;
        self.merges += result.merges;
        self.unchanged += result.unchanged;
        self.counts.worker_rows += u64::from(result.worker);
        self.counts.owner_retired_rows += 1;
        self.counts.new_rows += u64::from(result.new);
        if result.updates == 0 {
            return;
        }
        self.row_writes += 1;
        self.counts.row_writes += 1;
        self.counts.logical_improvements += result.updates;
        self.counts.superseded_improvements += result.updates - 1;
        self.counts.writer_reuses += u64::from(result.reused);
        self.counts.writer_allocations += u64::from(!result.reused);
        match result.prior {
            Some(Previous::Retained(origin, writer)) => {
                self.lifecycle.retire(origin, writer);
            }
            Some(Previous::Reused(origin, parent)) => {
                self.lifecycle.retire_unretained(origin, parent)
            }
            None => (),
        }
        let f = &*target.function;
        self.lifecycle
            .install(index, f.origin.unwrap(), f.writer.as_ref().unwrap().parent);
        *self.changed = true;
        self.lifecycle.stats.function_updates += result.updates;
        let witness = Dependency::Function(index);
        self.changes.touch(self.table, witness);
        if result.new {
            self.members.insert(index as u64);
            // The authoritative PortWrite proof is Eq -> i64. The input key
            // was canonicalized in this same read epoch; no union can intervene.
            // Reuse ordinary subscription replacement without scanning the
            // scalar output or rereading this row through Graph::function.
            let [Value::Eq(id)] = f.key.as_slice() else {
                unreachable!("typed scalar key")
            };
            self.maintenance.subscription_calls += 1;
            self.maintenance.canonical_subscription_calls += 1;
            self.maintenance.subscription_value_visits += 1;
            self.maintenance.subscription_scalar_fields_skipped += 1;
            self.maintenance.subscription_root_reads_omitted += 1;
            maintenance::replace_subscriptions(
                self.uses,
                self.dependencies,
                self.maintenance,
                self.parents,
                witness,
                smallvec::smallvec![*id],
            );
        }
        *self.version += result.updates;
    }
    fn finish(&mut self, length: u64, merge: ScalarMerge, kind: Option<&str>) {
        let stats = &mut self.lifecycle.stats;
        stats.single_writes += length;
        stats.merge_calls += self.merges;
        stats.scalar_merge_calls += self.merges;
        stats.scalar_unchanged += self.unchanged;
        if merge == ScalarMerge::Old {
            stats.scalar_old_projection += self.merges;
        }
        if let Some(kind) = kind {
            *stats.merge_contract_calls.entry(kind.into()).or_default() += self.merges;
        }
        stats.transient_writes += self.unchanged;
        stats.rhs_frames_avoided += self.unchanged;
        self.counts.invalidated += length - self.row_writes;
    }
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

    /// The table owner projects and looks up keys on workers, then resolves
    /// missing identities in source order before parallel row writes. Existing
    /// instances and authoritative rows stay in this one worker region.
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
        let next_cell = &mut self.next_cell;
        let keys = &mut self.function_keys[table];
        let functions = &mut self.functions;
        let decoded = &mut self.function_decoded;
        let parent_users = &mut self.parent_users;
        let directory = &mut self.writer_dir;
        let cells = &mut self.cells;
        let garbage = &mut self.garbage;
        let stats = &mut self.stats;
        let uses = &mut self.uses;
        let dependencies = &mut self.dependencies;
        let maintenance = &mut self.maintenance;
        let members = &mut self.members[table];
        let version = &mut self.query_versions[table];
        let changes = &mut self.changes;
        let changed = &mut self.changed;
        let parent_directory = &self.parents;
        let merge_kind = self.merge_kinds[table].as_deref();
        let parents = self.parents.reader();
        counts.boundary_ns += boundary.elapsed().as_nanos() as u64;
        let clock = std::time::Instant::now();
        counts.owner_pool_calls += 1;
        pool.install(|| -> Result<()> {
            // No identity or shared row is changed until all input keys are valid.
            // If malformed inputs fail on different workers, retain the first
            // source error, independent of completion order.
            let (error, probes) = tasks
                .par_iter_mut()
                .with_min_len(32)
                .map(|task| {
                    task.cell = first + task.ordinal as u32;
                    if evaluate.is_some() {
                        match ports.project_key(&task.values, parents) {
                            Ok(key) => task.key = key,
                            Err(error) => return (Some((task.ordinal, error)), 0),
                        }
                    }
                    // The checked Eq-to-i64 plan excludes compact Unit aliases.
                    task.index = keys
                        .get(std::slice::from_ref(&task.key))
                        .copied()
                        .unwrap_or(usize::MAX);
                    (None, 1)
                })
                .reduce(
                    || (None, 0),
                    |(a, left), (b, right)| {
                        (
                            match (a, b) {
                                (Some(a), Some(b)) => Some(if a.0 <= b.0 { a } else { b }),
                                (a, b) => a.or(b),
                            },
                            left + right,
                        )
                    },
                );
            counts.admission_probes += probes;
            counts.worker_key_rows += u64::from(evaluate.is_some()) * probes;
            if let Some((_, error)) = error {
                return Err(error);
            }
            counts.owner_candidates += length as u64;
            *next_cell = end;
            // Existing identities need no second directory lookup. Only misses
            // recheck the evolving directory, so equal new keys share one row.
            // The scan itself remains ordered; it is not claimed as parallel work.
            for task in tasks.iter_mut().filter(|task| task.index == usize::MAX) {
                counts.new_key_rechecks += 1;
                let key = std::slice::from_ref(&task.key);
                task.index = if let Some(&i) = keys.get(key) {
                    i
                } else {
                    let i = functions.len();
                    keys.insert(key, i);
                    // Reserved storage is exclusively held by this RHS batch. It
                    // is never visible to queries or published before initialization.
                    functions.push(Function {
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
                    decoded.push(None);
                    i
                };
            }
            tasks.par_sort_unstable_by_key(|task| (task.index, task.ordinal));
            counts.owner_sort_rows += length as u64;
            let mut functions = functions.as_mut_slice();
            let mut decoded = decoded.as_mut_slice();
            let mut offset = 0;
            let mut targets = Vec::with_capacity(tasks.len());
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
                    parent_users.get(&origin.cell).copied().unwrap_or(0) != 0
                });
                targets.push(Target {
                    function: f,
                    decoded: d,
                    group,
                    retained,
                    finished: None,
                });
            }
            counts.rows += targets.len() as u64;
            counts.duplicate_targets += (length as usize - targets.len()) as u64;
            counts.temporary_bytes +=
                (targets.capacity() * std::mem::size_of::<Target<'_>>()) as u64;
            let chunks: Vec<_> = targets.chunks_mut(64).collect();
            let completion = Completion {
                lifecycle: writer_frames::Owner {
                    directory,
                    cells,
                    users: parent_users,
                    garbage,
                    stats,
                },
                uses,
                dependencies,
                maintenance,
                members,
                version,
                changes,
                changed,
                parents: parent_directory,
                counts,
                table,
                merges: 0,
                unchanged: 0,
                row_writes: 0,
            };
            let (mut completion, events) = crate::completion_events::owned_prefix(
                chunks,
                completion,
                |chunk| {
                    for target in chunk.iter_mut() {
                        target.write(
                            ports,
                            evaluate,
                            merge,
                            parent_columns,
                            template,
                            epoch,
                            operation,
                        );
                    }
                    chunk
                },
                |owner, chunk| {
                    for target in chunk {
                        owner.accept(target);
                    }
                },
            );
            completion.counts.owner_completion_groups += events.waves;
            completion.counts.owner_completion_early_groups += events.early;
            completion.counts.owner_completion_bytes += events.bytes;
            completion.counts.temporary_bytes += events.bytes;
            completion.finish(length as u64, merge, merge_kind);
            drop(completion);
            drop(targets);
            // Source publication consumes original ordinals. Restore that order
            // here without a second pool call or a source sorting pass.
            tasks.par_sort_unstable_by_key(|task| task.ordinal);
            counts.owner_sort_rows += length as u64;
            Ok(())
        })?;
        counts.execution_ns += clock.elapsed().as_nanos() as u64;
        Ok(())
    }
}

impl Target<'_> {
    fn write(
        &mut self,
        ports: &crate::row_kernel::PortWrite,
        evaluate: Option<bool>,
        merge: ScalarMerge,
        parent_columns: &BTreeMap<usize, usize>,
        template: usize,
        epoch: u64,
        operation: usize,
    ) {
        let f = &mut *self.function;
        let decoded = &mut *self.decoded;
        let group = &mut *self.group;
        let retained = self.retained;

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
            *decoded = Some(Graph::shared_fields(&f.key, &f.value));
            prior
        } else {
            None
        };
        for task in group.iter_mut() {
            drop(std::mem::take(&mut task.values));
        }
        self.finished = Some(Finished {
            new,
            updates,
            merges,
            unchanged,
            prior,
            reused,
            worker: rayon::current_thread_index().is_some(),
        });
    }
}
