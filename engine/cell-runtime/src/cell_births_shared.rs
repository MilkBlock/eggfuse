//! Batch-local actual result slots. Evaluation never holds a result-slot lock:
//! a peer can compute the same pure node and race to publish an identical result.
//! Only earlier source Cells/operations are candidates, so recursive helping is
//! acyclic. Public graph mutation and effect ordering remain with the owner.
use super::*;
use std::sync::{
    OnceLock,
    atomic::{AtomicU64, AtomicUsize, Ordering},
};

struct Resolved {
    witness: FactRef,
    fields: RowFields,
    hash: u64,
}
struct Results {
    nodes: Vec<OnceLock<Resolved>>,
    bloom: AtomicU64,
    complete: AtomicUsize,
    first_hash: u64,
}
struct Batch<'a> {
    jobs: &'a [Job],
    results: Vec<Results>,
    parents: Read<'a>,
    collide: bool,
    known: Vec<(u64, usize, usize)>,
    late: Vec<(usize, usize, usize)>,
    #[cfg(test)]
    race: Option<(usize, usize, &'a std::sync::Barrier)>,
}
fn mask(hash: u64) -> u64 {
    (1 << (hash & 63)) | (1 << ((hash >> 32) & 63))
}
impl<'a> Batch<'a> {
    fn new(jobs: &'a [Job], parents: Read<'a>, counts: &mut Counts) -> Self {
        static COLLIDE: OnceLock<bool> = OnceLock::new();
        let results: Vec<_> = jobs
            .iter()
            .map(|job| {
                let nodes: Vec<_> = (job.from..job.limit).map(|_| OnceLock::new()).collect();
                counts.shared_slots += nodes.len() as u64;
                counts.shared_bytes +=
                    (nodes.capacity() * std::mem::size_of::<OnceLock<Resolved>>()) as u64;
                counts.shared_growths += 1;
                counts.hashes += 1;
                Results {
                    first_hash: hashkey(job.plan.steps[job.from].table, &job.key),
                    nodes,
                    bloom: AtomicU64::new(0),
                    complete: AtomicUsize::new(0),
                }
            })
            .collect();
        counts.shared_growths += 1;
        counts.shared_bytes += (results.capacity() * std::mem::size_of::<Results>()) as u64;
        let collide = *COLLIDE
            .get_or_init(|| std::env::var("CELL_CPU_SIEVE_COLLISIONS").as_deref() == Ok("1"));
        // Address directory only: no copied keys, binding rows or consumer lists.
        // Prefix keys and first boundary keys are already known at admission.
        let capacity = jobs.len() + jobs.iter().map(|j| j.frame.facts.len()).sum::<usize>();
        let mut known = Vec::with_capacity(capacity);
        let mut late = Vec::with_capacity(jobs.iter().map(|j| j.operations() - 1).sum());
        for (i, job) in jobs.iter().enumerate() {
            known.push((if collide { 0 } else { results[i].first_hash }, i, job.from));
            for (operation, fields) in &job.frame.facts {
                let index = job
                    .plan
                    .steps
                    .binary_search_by_key(&(*operation as usize), |s| s.operation)
                    .unwrap();
                counts.hashes += 1;
                let hash = hashkey(job.plan.steps[index].table, &fields[..fields.len() - 1]);
                known.push((if collide { 0 } else { hash }, i, index));
            }
            late.extend(
                (job.from + 1..job.limit).map(|index| (job.plan.steps[index].table, i, index)),
            );
        }
        known.sort_unstable_by(|a, b| {
            counts.directory_checks += 1;
            a.cmp(b)
        });
        late.sort_unstable_by(|a, b| {
            counts.directory_checks += 1;
            a.cmp(b)
        });
        counts.shared_growths += u64::from(known.capacity() != 0) + u64::from(late.capacity() != 0);
        counts.shared_bytes += (known.capacity() * std::mem::size_of::<(u64, usize, usize)>()
            + late.capacity() * std::mem::size_of::<(usize, usize, usize)>())
            as u64;
        Self {
            jobs,
            results,
            parents,
            collide,
            known,
            late,
            #[cfg(test)]
            race: None,
        }
    }
    fn bloom_mask(&self, hash: u64) -> u64 {
        if self.collide { 1 } else { mask(hash) }
    }
    fn operand(&self, job: usize, index: usize, arg: &Arg, counts: &mut Counts) -> Value {
        counts.operand_reads += 1;
        let owner = &self.jobs[job];
        match arg {
            Arg::Literal(v) => self.parents.canon(v),
            Arg::Slot(slot) => {
                if let Some(v) = owner.frame.values.get(slot) {
                    return self.parents.canon(v);
                }
                let definition = owner
                    .plan
                    .definitions
                    .binary_search_by_key(slot, |&(s, _)| s)
                    .unwrap();
                let operation = owner.plan.definitions[definition].1;
                if let Ok(prior) = owner
                    .plan
                    .steps
                    .binary_search_by_key(&operation, |s| s.operation)
                    && prior >= owner.from
                {
                    assert!(prior < index, "Cell operands must precede their users");
                    return self
                        .resolve(job, prior, counts)
                        .fields
                        .last()
                        .unwrap()
                        .clone();
                }
                owner
                    .frame
                    .fields(operation)
                    .expect("admitted prefix operand")
                    .last()
                    .unwrap()
                    .clone()
            }
        }
    }
    fn equal(fields: &[Value], key: &[Value], counts: &mut Counts) -> bool {
        fields.len() == key.len() + 1
            && fields[..key.len()].iter().zip(key).all(|(a, b)| {
                counts.field_checks += 1;
                a == b
            })
    }
    fn resolve(&self, job: usize, index: usize, counts: &mut Counts) -> &Resolved {
        let owner = &self.jobs[job];
        let slot = &self.results[job].nodes[index - owner.from];
        counts.result_reads += 1;
        if let Some(value) = slot.get() {
            counts.result_hits += 1;
            return value;
        }
        #[cfg(test)]
        if let Some((j, i, gate)) = self.race
            && (j, i) == (job, index)
        {
            gate.wait();
        }
        counts.evaluations += 1;
        let step = &owner.plan.steps[index];
        let key: smallvec::SmallVec<[Value; 4]> = if index == owner.from {
            owner.key.clone()
        } else {
            step.keys
                .iter()
                .map(|a| self.operand(job, index, a, counts))
                .collect()
        };
        if key.spilled() {
            counts.shared_growths += 1;
            counts.shared_bytes += (key.capacity() * std::mem::size_of::<Value>()) as u64;
        }
        let hash = if index == owner.from {
            self.results[job].first_hash
        } else {
            counts.hashes += 1;
            hashkey(step.table, &key)
        };
        let mut reused = None;
        if !owner.isolated {
            // Known keys dispatch directly to exact candidates. Only genuinely
            // unknown later keys use the template's small operator-site group.
            // Merge both ranges in source order, preserving earliest ownership.
            counts.candidate_ranges += 2;
            let fingerprint = if self.collide { 0 } else { hash };
            let first = self.known.partition_point(|r| {
                counts.directory_checks += 1;
                r.0 < fingerprint
            });
            let end = first
                + self.known[first..].partition_point(|r| {
                    counts.directory_checks += 1;
                    r.0 == fingerprint
                });
            let mut known = self.known[first..end]
                .iter()
                .map(|&(_, j, i)| (j, i))
                .peekable();
            let first = self.late.partition_point(|r| {
                counts.directory_checks += 1;
                r.0 < step.table
            });
            let end = first
                + self.late[first..].partition_point(|r| {
                    counts.directory_checks += 1;
                    r.0 == step.table
                });
            let mut late = self.late[first..end]
                .iter()
                .map(|&(_, j, i)| (j, i))
                .peekable();
            let mut filtered = None;
            loop {
                let (next, is_late) = match (known.peek(), late.peek()) {
                    (Some(a), Some(b)) if a <= b => (known.next(), false),
                    (Some(_), Some(_)) => (late.next(), true),
                    (Some(_), None) => (known.next(), false),
                    (None, Some(_)) => (late.next(), true),
                    (None, None) => break,
                };
                let (previous, prior) = next.unwrap();
                if (previous, prior) >= (job, index) {
                    break;
                }
                let source = &self.jobs[previous];
                let state = &self.results[previous];
                debug_assert!(std::sync::Arc::ptr_eq(&owner.plan, &source.plan));
                counts.key_screens += 1;
                if source.plan.steps[prior].table != step.table {
                    continue;
                }
                if is_late {
                    if filtered.is_none_or(|(j, _)| j != previous) {
                        let absent = if state.complete.load(Ordering::Acquire) == state.nodes.len()
                        {
                            counts.bloom_checks += 1;
                            let absent = state.bloom.load(Ordering::Relaxed)
                                & self.bloom_mask(hash)
                                != self.bloom_mask(hash);
                            counts.bloom_skips += u64::from(absent);
                            absent
                        } else {
                            false
                        };
                        filtered = Some((previous, absent));
                    }
                    if filtered.unwrap().1 {
                        continue;
                    }
                }
                let operation = source.plan.steps[prior].operation;
                if prior < source.from {
                    let fields = source.frame.fields(operation).unwrap();
                    counts.candidate_probes += 1;
                    if Self::equal(fields, &key, counts) {
                        let fields = source
                            .frame
                            .facts
                            .iter()
                            .find(|r| r.0 as usize == operation)
                            .unwrap()
                            .1
                            .clone();
                        counts.result_handles += 1;
                        reused = Some(Resolved {
                            witness: FactRef {
                                cell: source.cell,
                                op: operation as u32,
                            },
                            fields,
                            hash,
                        });
                        break;
                    }
                } else {
                    let old = self.resolve(previous, prior, counts);
                    counts.candidate_probes += 1;
                    if (self.collide || old.hash == hash) && Self::equal(&old.fields, &key, counts)
                    {
                        counts.result_handles += 1;
                        reused = Some(Resolved {
                            witness: old.witness,
                            fields: old.fields.clone(),
                            hash,
                        });
                        break;
                    }
                }
            }
        }
        let value = reused.unwrap_or_else(|| {
            let value = Value::Eq(((owner.cell as u64) << 32) | (step.destination as u64 + 1));
            counts.identity_checks += 1;
            assert_eq!(
                self.parents.canon(&value),
                value,
                "unpublished identity must be fresh"
            );
            let fields = Graph::shared_fields(&key, &value);
            counts.row_fields += fields.len() as u64;
            Resolved {
                witness: FactRef {
                    cell: owner.cell,
                    op: step.operation as u32,
                },
                fields,
                hash,
            }
        });
        // The expensive computation is outside OnceLock. set() arbitrates only
        // an already-computed result, never blocks waiting for peer evaluation.
        if slot.set(value).is_ok() {
            self.results[job]
                .bloom
                .fetch_or(self.bloom_mask(hash), Ordering::Relaxed);
            counts.bloom_writes += 1;
            self.results[job].complete.fetch_add(1, Ordering::AcqRel);
        } else {
            counts.duplicate_evaluations += 1;
        }
        slot.get().unwrap()
    }
    fn finish(&self, job: usize, receipts: &mut EffectWriter<'_>) -> Done {
        let owner = &self.jobs[job];
        let mut piece = Piece {
            end: owner.frame.completed_prefix,
            rows: Rows::new(),
            units: Vec::new(),
            aliases: 0,
            counts: Counts::default(),
        };
        // This is another handle to the same sealed inputs, not a bindings copy.
        // Peers may retain this immutable prefix after its source owner resumes.
        let mut values = owner.frame.values.shared_suffix();
        piece.counts.frame_handles += 1;
        let capacity = values.capacity_bytes();
        for index in owner.from..owner.limit {
            let step = &owner.plan.steps[index];
            let value = self.resolve(job, index, &mut piece.counts);
            if value.witness
                == (FactRef {
                    cell: owner.cell,
                    op: step.operation as u32,
                })
            {
                let before = if piece.rows.spilled() {
                    piece.rows.capacity()
                } else {
                    0
                };
                piece.rows.push(Born {
                    operation: step.operation,
                    table: step.table,
                    fields: value.fields.clone(),
                    hash: value.hash,
                });
                piece.counts.result_handles += 1;
                let after = if piece.rows.spilled() {
                    piece.rows.capacity()
                } else {
                    0
                };
                piece.counts.pending_growths += u64::from(after != before);
                piece.counts.pending_bytes +=
                    ((after - before) * std::mem::size_of::<Born>()) as u64;
                piece.counts.local_births += 1;
                piece.counts.root_births += u64::from(owner.starts_root() && index==owner.from);
            } else {
                values.insert(step.destination, value.fields.last().unwrap().clone());
                piece.counts.value_writes += 1;
                piece.counts.local_reuses += 1;
                piece.counts.root_reuses += u64::from(owner.starts_root() && index==owner.from);
            }
            receipts.record(step.operation, Dependency::Fact(value.witness));
            piece.end = step.operation + 1;
            if index != owner.from {
                piece.aliases += step.skipped as u64;
            }
        }
        let growth = values.capacity_bytes().saturating_sub(capacity);
        piece.counts.slot_growths += u64::from(growth != 0);
        piece.counts.slot_bytes += growth as u64;
        let mut frame=Local { values, facts:Default::default(), completed_prefix:piece.end };
        if let Some(epoch)=owner.unit_epoch {
            frame.facts=owner.frame.facts.clone();
            piece.counts.prefix_handles+=frame.facts.len() as u64;
            owner.plan.prepare_units(owner.cell,epoch,&frame,owner.first,self.parents,&mut piece);
            frame.facts.clear();
            frame.completed_prefix=piece.end;
        }
        Done {
            cell: owner.cell,
            frame,
            piece,
            worker: rayon::current_thread_index(),
        }
    }
}

pub(crate) fn stream<E>(
    tasks: Vec<(Job, crate::cell::Effects)>, parents: Read<'_>,
    pool: Option<&rayon::ThreadPool>, unfinished:&std::sync::atomic::AtomicUsize, consume: impl FnMut(&mut Vec<Completed>) -> std::result::Result<(), E>,
) -> ((std::result::Result<(), E>, crate::completion_events::Work), Counts) {
    let (jobs, effects): (Vec<_>, Vec<_>) = tasks.into_iter().unzip();
    let mut counts = Counts::default();
    counts.shared_growths += 2;
    counts.shared_bytes += (jobs.capacity() * std::mem::size_of::<Job>()
        + effects.capacity() * std::mem::size_of::<crate::cell::Effects>()) as u64;
    let batch = Batch::new(&jobs, parents, &mut counts);
    // Peers retain immutable input handles. The owner can reattach and advance
    // its mutable suffix while these readers keep the admitted input snapshot.
    let tasks: Vec<_> = effects.into_iter().enumerate().collect();
    counts.shared_growths += 1;
    counts.shared_bytes += (tasks.capacity() * std::mem::size_of::<(usize, crate::cell::Effects)>()) as u64;
    let run = |(i, mut effects): (usize, crate::cell::Effects)| {
        let done = batch.finish(i, &mut effects.writer());
        unfinished.fetch_sub(1,std::sync::atomic::Ordering::AcqRel);
        Completed { done, effects }
    };
    (crate::completion_events::ordered(tasks, pool, run, consume), counts)
}

/// The original finite peer directory stays with this owned wave. Source
/// admission can continue while these readers share or redundantly evaluate
/// pure nodes; no Cursor or public graph mutation crosses to the pool.
pub(crate) fn produce(tasks:Vec<(Job,crate::cell::Effects)>,parents:Read<'_>,
    emit:impl Fn(usize,Completed)+Sync)->Counts {
    use rayon::prelude::*;
    let (jobs,effects):(Vec<_>,Vec<_>)=tasks.into_iter().unzip();
    let mut counts=Counts::default();counts.shared_growths+=2;
    counts.shared_bytes+=(jobs.capacity()*std::mem::size_of::<Job>()
        +effects.capacity()*std::mem::size_of::<crate::cell::Effects>()) as u64;
    let batch=Batch::new(&jobs,parents,&mut counts);
    effects.into_par_iter().enumerate().for_each(|(i,mut effects)| {
        let done=batch.finish(i,&mut effects.writer());emit(i,Completed {done,effects});
    });
    counts
}

impl Graph {
    pub(crate) fn take_dependent_job<'a>(
        &mut self,
        rule: usize,
        cell: u32,
        stop: usize,
        key: smallvec::SmallVec<[Value; 4]>,
        pending_operations: usize,
        lookup: impl Fn(u32) -> (u64, Option<&'a Job>),
    ) -> Result<(Counts, Option<Job>)> {
        let mut counts = Counts::default();
        let position = self.rhs_frame(cell).unwrap().completed_prefix;
        let Some(plan) = self.program.executions[rule].births.as_ref() else {
            return Ok((counts, None));
        };
        let Ok(from) = plan.steps.binary_search_by_key(&position, |s| s.operation) else {
            return Ok((counts, None));
        };
        counts.attempts += 1;
        if !plan.batch_rule || plan.steps.last().unwrap().operation >= stop {
            return Ok((counts, None));
        }
        // Bound recursive helping and temporary slots. Later independent jobs
        // cannot be dependencies of this one; a later dependent admission must
        // prove this bound again. Large cones keep the iterative source executor.
        if plan.steps.len() - from + pending_operations > 256 {
            return Ok((counts, None));
        }
        let step = &plan.steps[from];
        let proved = plan.lineage[from].iter().any(|seed| {
            let value = step
                .keys
                .iter()
                .zip(&key)
                .find_map(|(a, v)| (a == &Arg::Slot(*seed)).then_some(v))
                .unwrap();
            let Value::Eq(id) = value else {
                return false;
            };
            let (probes, job) = lookup((*id >> 32) as u32);
            counts.dependency_proofs += probes;
            let Some(job) = job else {
                return false;
            };
            // Address selects a candidate, never proves identity or freshness.
            if !std::sync::Arc::ptr_eq(plan, &job.plan) {
                return false;
            }
            let Some(root) = job.fresh_root else {
                return false;
            };
            let root = &job.plan.steps[root];
            root.region == step.region
                && value == &Value::Eq(((job.cell as u64) << 32) | (root.destination as u64 + 1))
                && job.frame.fields(root.operation).and_then(|f| f.last()) == Some(value)
                && self.parents.reader().canon(value) == *value
        });
        if !proved {
            return Ok((counts, None));
        }
        let plan = plan.clone();
        counts.plan_handles += 1;
        let unit_epoch=plan.units.as_ref().is_some_and(|u|
            u.sites.iter().all(|s|!self.units.owned[s.table] || self.pending_unions.is_empty()))
            .then_some(self.epoch);
        let first = plan
            .steps
            .iter()
            .find(|s| s.region == step.region)
            .unwrap()
            .operation;
        // Only external/preceding values are captured; internal dependencies
        // remain static slot references into this plan's shared result slots.
        for arg in plan.steps[from..].iter().flat_map(|s| &s.keys).chain(
            plan.units.iter().filter(|_|unit_epoch.is_some()).flat_map(|u|u.sites.iter().flat_map(|s|&s.keys))) {
            let Arg::Slot(slot) = arg else {
                continue;
            };
            let internal = plan
                .definitions
                .binary_search_by_key(slot, |&(s, _)| s)
                .ok()
                .is_some_and(|i| plan.definitions[i].1 >= position);
            if !internal && !self.rhs_frame(cell).unwrap().values.contains_key(slot) {
                let value = self.slot(cell, *slot)?;
                counts.captured_reads += 1;
                counts.captured_writes += 1;
                let values = &mut self.rhs_frame_mut(cell).unwrap().values;
                let before = values.capacity_bytes();
                values.insert(*slot, value);
                let growth = values.capacity_bytes() - before;
                counts.slot_growths += u64::from(growth != 0);
                counts.slot_bytes += growth as u64;
            }
        }
        let mut facts = smallvec::SmallVec::new();
        for (&op, fact) in self
            .rhs_frame(cell)
            .unwrap()
            .facts
            .iter()
            .filter(|(op, _)| **op as usize >= first)
        {
            counts.prefix_reads += 1;
            let Some((_, fields)) = &fact.decoded else {
                counts.prefix_unavailable += 1;
                return Ok((counts, None));
            };
            let before = if facts.spilled() { facts.capacity() } else { 0 };
            facts.push((op, fields.clone()));
            counts.prefix_handles += 1;
            let after = if facts.spilled() { facts.capacity() } else { 0 };
            counts.prefix_growths += u64::from(before != after);
            counts.prefix_bytes +=
                ((after - before) * std::mem::size_of::<(u32, RowFields)>()) as u64;
        }
        let (values, sealed) = self.rhs_frame_mut(cell).unwrap().values.lease();
        counts.slot_seals += u64::from(sealed);
        counts.slot_leases += 1;
        counts.sealed_bytes += u64::from(sealed) * crate::slots::FrameSlots::seal_bytes() as u64;
        let limit = plan.steps.len();
        Ok((
            counts,
            Some(Job {
                cell,
                unit_epoch,
                plan,
                frame: Local {
                    values,
                    facts,
                    completed_prefix: position,
                },
                from,
                limit,
                first,
                anchor: first,
                key,
                isolated: false,
                fresh_root: None,
                root: None,
            }),
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cell::Effects;
    #[test]
    fn competing_evaluators_publish_one_exact_result_and_downstream_uses_that_slot() {
        let mut g = super::super::tests::graph();
        let (cell, _, mut window) = super::super::tests::start(&mut g);
        let (_, job) = g.take_local_job(0, cell, &mut window, 4, false).unwrap();
        let jobs = vec![job.unwrap()];
        let mut allocations = Counts::default();
        let gate = std::sync::Barrier::new(2);
        let mut batch = Batch::new(&jobs, g.parents.reader(), &mut allocations);
        batch.race = Some((0, 1, &gate));
        let totals = std::thread::scope(|scope| {
            let a = scope.spawn(|| {
                let mut c = Counts::default();
                let r = batch.resolve(0, 1, &mut c);
                (r.witness, c)
            });
            let b = scope.spawn(|| {
                let mut c = Counts::default();
                let r = batch.resolve(0, 1, &mut c);
                (r.witness, c)
            });
            let (a, mut ca) = a.join().unwrap();
            let (b, cb) = b.join().unwrap();
            assert_eq!(a, b);
            ca.add(cb);
            ca
        });
        assert_eq!(totals.evaluations, 2);
        assert_eq!(totals.duplicate_evaluations, 1);
        assert_eq!(totals.row_fields, 4, "both private allocations are charged");
        assert_eq!(batch.results[0].complete.load(Ordering::Acquire), 1);
        let done = batch.finish(0, &mut Effects::default().writer());
        assert_eq!(done.piece.counts.local_births, 2);
        assert_eq!(done.piece.counts.local_reuses, 1);
        drop(batch);
        drop(jobs);
        g.commit_local_job(done,&mut crate::cell::Effects::default().writer()).unwrap();
        assert_eq!(g.slot(cell, 2).unwrap(), g.slot(cell, 3).unwrap());
        let mut control = super::super::tests::graph();
        let (c, _, _) = super::super::tests::start(&mut control);
        for (op, input, dst) in [(1, 1, 2), (2, 1, 3), (3, 2, 4)] {
            control
                .construct(c, op, 0, &[Arg::Slot(input)], dst)
                .unwrap();
        }
        assert_eq!(g.export().unwrap(), control.export().unwrap());
    }
    #[test]
    fn an_older_result_in_a_pending_cell_does_not_prove_the_new_root_cone() {
        let mut g = super::super::tests::graph();
        let (a, u, _) = super::super::tests::start(&mut g);
        let v = g.construct(a, 1, 0, &[Arg::Slot(1)], 2).unwrap();
        let mut window = Window::seed(&g, a, 2);
        assert_eq!(g.construct(a, 2, 0, &[Arg::Slot(1)], 3).unwrap(), v);
        g.rhs_frame_mut(a).unwrap().completed_prefix = 3;
        let (_, job) = g.take_local_job(0, a, &mut window, 4, true).unwrap();
        let job = job.unwrap();
        let b = g
            .begin_transient(0, [(0, Value::Eq(100))].into_iter().collect(), None)
            .unwrap();
        assert_eq!(g.construct(b, 0, 0, &[Arg::Slot(0)], 1).unwrap(), u);
        g.rhs_frame_mut(b).unwrap().completed_prefix = 1;
        let (_, candidate) = g
            .take_dependent_job(0, b, 4, smallvec::smallvec![u], job.operations(), |id| {
                (1, (id == a).then_some(&job))
            })
            .unwrap();
        assert!(
            candidate.is_none(),
            "same Cell ID cannot certify its older root"
        );
        assert_eq!(g.construct(b, 1, 0, &[Arg::Slot(1)], 2).unwrap(), v);
    }
    #[test]
    fn an_empty_bloom_does_not_exclude_an_unfinished_predecessor() {
        let mut g = super::super::tests::graph();
        let (cell, _, mut window) = super::super::tests::start(&mut g);
        let (_, job) = g.take_local_job(0, cell, &mut window, 4, false).unwrap();
        let jobs = vec![job.unwrap()];
        let mut c = Counts::default();
        let batch = Batch::new(&jobs, g.parents.reader(), &mut c);
        assert_eq!(batch.results[0].bloom.load(Ordering::Relaxed), 0);
        let r = batch.resolve(0, 2, &mut c);
        assert_eq!(r.witness, FactRef { cell, op: 1 });
        assert_eq!(c.bloom_skips, 0);
        assert_eq!(c.evaluations, 2);
        assert_eq!(batch.results[0].complete.load(Ordering::Acquire), 2);
    }
}
