//! Run-owned ready batches for fresh constructor cones. A dependent Cell can use
//! peer result slots or compute their pure nodes itself. Unproved dependencies
//! retain source completion; shared effects and publication remain ordered.
use super::*;
use crate::graph::{
    cell_births::{Completed, Job},
    rhs_ownership::Suspended,
};
#[path="runtime_cell_pipeline.rs"]
mod pipeline;

struct Parked {
    execution: owned_cell::Execution,
    context: Suspended,
    job: Option<Job>,
}
const READY_LIMIT: usize = 64;
#[derive(Default)]
struct Ready {
    owners: Vec<Parked>,
    operations: usize,
    shared: bool,
    roots: bool,
    flying:Option<pipeline::Flying>,
    spare:Vec<Parked>,
}
impl Ready {
    fn is_empty(&self)->bool {self.owners.is_empty() && self.flying.is_none()}
    fn mixed_rules(&self)->bool {
        let mut rules=self.owners.iter().filter(|p|p.job.is_some()).map(|p|p.execution.rule);
        let Some(first)=rules.next() else {return false;};
        rules.any(|r|r!=first)
    }
}
/// The original owner buffers and pending addresses survive compatible rule
/// groups. This scope still ends at the original sealed source Run boundary.
#[derive(Default)]
pub(super) struct RunQueue {ready:Ready,pending:Vec<u32>}
impl RunQueue {pub(super) fn has_pending(&self)->bool {!self.ready.is_empty()}}
pub(super) enum QueueBoundary {Outside,RunEnd,Error}

impl Executor {
    pub(super) fn finish_cell_queue(&mut self,queue:&mut RunQueue,boundary:QueueBoundary)->Result<()> {
        if queue.ready.is_empty() {return Ok(());}
        let stats=&mut self.cell_execution.as_mut().unwrap().counts.scheduler;
        match boundary {
            QueueBoundary::Outside=>stats.outside_group_fences+=1,
            QueueBoundary::RunEnd=>stats.run_end_fences+=1,
            QueueBoundary::Error=>stats.error_fences+=1,
        }
        self.drain_cell_queue(&mut queue.ready,&mut queue.pending)
    }
    fn consume_cell_events(&mut self,completed:&mut Vec<Completed>,eligible:bool,pool:&rayon::ThreadPool,
        mut consume:impl FnMut(&mut Self,std::vec::Drain<'_,Completed>,
            Option<&mut crate::graph::cell_births::Registration>)->Result<()>)->Result<()> {
        let mut diagnostic=crate::sync_diagnostics::Clock::new();
        let Some(mut pending)=eligible.then(||self.graph.prepare_cell_registration(completed)).flatten() else {
            #[cfg(feature="cell-sync-diagnostics")] let start=Instant::now();
            let result=consume(self,completed.drain(..),None);
            #[cfg(feature="cell-sync-diagnostics")] {
                let stats=&mut self.graph.stats.sync_diagnostics;
                stats.source_batches+=1;stats.source_adoption_ns+=start.elapsed().as_nanos() as u64;
            }
            return result;
        };
        let tasks=std::mem::take(&mut pending.tasks);
        let unfinished=std::sync::atomic::AtomicUsize::new(tasks.len());
        let inline=crate::sync_diagnostics::registry_inline();
        let mut result=Ok(());
        diagnostic.enter();
        let events=crate::completion_events::fragments_with_followups(tasks,(!inline).then_some(pool),|task,emit| {
            task.run(&|event| {
                // Registration has already finished before its final owner
                // event is queued. Do not count a delayed task epilogue as
                // overlap with unfinished registration work.
                if event.completes_owner() {unfinished.fetch_sub(1,std::sync::atomic::Ordering::AcqRel);}
                emit(event);
            });
        },|ready,tasks| {
            for event in ready.drain(..) {pending.accept(&mut self.graph,completed,event);}
            pending.dispatch(&mut self.graph,tasks);
            unfinished.fetch_add(tasks.len(),std::sync::atomic::Ordering::AcqRel);
            if result.is_ok() {
                let count=pending.ready(completed);
                if count!=0 {
                    pending.advance(count);
                    #[cfg(feature="cell-sync-diagnostics")] let start=Instant::now();
                    result=consume(self,completed.drain(..count),Some(&mut pending.registration));
                    self.graph.stats.unit_registry_ready_prefixes+=1;
                    if result.is_ok() {self.graph.stats.unit_registry_accepted_cells+=count as u64;}
                    if result.is_ok() && unfinished.load(std::sync::atomic::Ordering::Acquire)!=0 {
                        self.graph.stats.unit_registry_early_cells+=count as u64;
                    }
                    if result.is_ok() && pending.constructor_directories_pending() {
                        // The owner may already have emitted its final event.
                        // This measures return independence, not worker CPU use.
                        self.graph.stats.constructor_registry_pre_return_cells+=count as u64;
                    }
                    #[cfg(feature="cell-sync-diagnostics")] {
                        let elapsed=start.elapsed().as_nanos() as u64;
                        let stats=&mut self.graph.stats.sync_diagnostics;
                        stats.source_batches+=1;stats.source_adoption_ns+=elapsed;
                        stats.registered_source_batches+=1;stats.registered_source_adoption_ns+=elapsed;
                    }
                }
            }
            // A source error must not discard late owner events: return every
            // original directory before rolling back the unadopted suffix.
        });
        diagnostic.join();
        self.graph.stats.unit_registry_event_bytes+=events.bytes;
        self.graph.stats.unit_registry_event_wait_ns+=events.wait_ns;
        pending.restore_subscriptions(&mut self.graph);
        self.graph.finish_cell_registration(pending.registration);
        #[cfg(feature="cell-sync-diagnostics")]
        self.graph.stats.sync_diagnostics.registration.record(diagnostic,None,!inline,pool.current_num_threads());
        debug_assert!(result.is_err() || completed.is_empty(),"every ready Cell must be adopted");
        result
    }
    pub(super) fn batch_cell_rule(&self, rid: usize, rows: usize, pending:bool) -> bool {
        rows != 0 && (rows > 1 || pending)
            && self.cell_execution.is_some()
            && self
                .query_workers
                .as_ref()
                .and_then(|w| w.execution_pool())
                .is_some()
            && self.graph.local_jobs_supported()
            && self.graph.program.executions[rid]
                .births
                .as_ref()
                .is_some_and(|p| p.batch_rule())
            && !self.profile_queries
            && !cfg!(feature = "structural-depth")
            && !cfg!(feature = "family-survey")
    }
    fn finish_attached_cell(&mut self, mut execution: owned_cell::Execution) -> Result<()> {
        let result = (|| loop {
            match self.advance_cell(&mut execution)? {
                owned_cell::Frontier::Boundary(op) => {
                    self.resolve_cell_boundary(&mut execution, op)?
                }
                owned_cell::Frontier::Complete | owned_cell::Frontier::Stopped => {
                    return self.finish_cell(execution);
                }
            }
        })();
        self.graph.end_owner_entry();
        result
    }
    /// The original read snapshot already proved this constructor's key. A
    /// live foreign witness cannot depend on a root still being born by a peer.
    /// Consume that proof at its source position, before preparing conflict keys.
    fn resume_prepared_cell(&mut self, execution: &mut owned_cell::Execution, position: usize) -> Result<bool> {
        use crate::graph::ConstructorWitness;
        let Some(ConstructorWitness::Snapshot(witness)) = execution.constructor else { return Ok(false); };
        if execution.births.is_some() || witness.cell == execution.cell
            || execution.aliases.as_ref().is_some_and(|a|a[position])
            || execution.transfers.get(execution.transfer).is_some_and(|t|t.op==position)
            || !self.graph.program.executions[execution.rule].constructor.as_ref()
                .is_some_and(|p|p.operation==position)
            || !self.graph.pipelined_births_ready() { return Ok(false); }
        let Op::Let(dst,Call::Table(table),_) = &execution.ops[position]
            else { unreachable!("checked constructor preparation"); };
        let Some(point) = self.graph.sealed_constructor_result(execution.cell,*table,witness)? else {
            execution.constructor=Some(ConstructorWitness::Key(witness));
            self.cell_execution.as_mut().unwrap().counts.scheduler.prepared_key_fallbacks+=1;
            return Ok(false);
        };
        #[cfg(feature="storage-metrics")]
        let probe=crate::rhs_projection_trace::before(&self.graph,execution.rule,execution.cell,position,&execution.known);
        execution.effects.writer().record(position,point.witness);
        self.graph.composition_result_entry(execution.cell,position,point.witness,true);
        let frame=self.graph.rhs_frame_mut(execution.cell).unwrap();
        frame.values.insert(*dst,point.value);
        frame.completed_prefix=position+1;
        execution.constructor=None;
        execution.work.constructors+=1;
        self.graph.stats.constructor_requests+=1;
        self.graph.stats.constructor_reused+=1;
        self.cell_execution.as_mut().unwrap().counts.scheduler.prepared_resumptions+=1;
        #[cfg(feature="storage-metrics")]
        crate::rhs_projection_trace::after(&self.graph,probe,&crate::cell::SingleEffect(position,point.witness),true);
        Ok(true)
    }
    fn adopt_cell_event(&mut self, parked: Parked, completed: Option<Completed>,
        publication:Option<crate::graph::cell_births::Publication>) -> Result<()> {
        let mut execution = parked.execution;
        self.graph.restore_rhs(parked.context);
        if let Some(Completed { done, effects }) = completed {
            debug_assert_eq!(done.cell(), execution.cell);
            execution.effects = effects;
            if let Some(worker) = done.worker {
                let stats = &mut self.cell_execution.as_mut().unwrap().counts.scheduler;
                if stats.worker_jobs.len() <= worker {
                    let before = stats.worker_jobs.capacity();
                    stats.worker_jobs.resize(worker + 1, 0);
                    stats.queue_growths += u64::from(before != stats.worker_jobs.capacity());
                    stats.queue_bytes += ((stats.worker_jobs.capacity() - before) * std::mem::size_of::<u64>()) as u64;
                }
                stats.worker_jobs[worker] += 1;
            }
            let worker = done.worker.is_some();
            let mut counts = self.graph.commit_registered_local_job(done, &mut execution.effects.writer(),publication)?;
            execution.work.facts += counts.committed_rows;
            execution.work.updates += counts.unit_inserts;
            execution.work.constructors += counts.local_births + counts.local_reuses;
            if worker { counts.worker_operations += counts.local_births + counts.local_reuses; }
            self.cell_execution.as_mut().unwrap().counts.births.add(counts);
        }
        self.finish_attached_cell(execution)?;
        self.graph.sealed_input_cell = None;
        self.graph.sealed_generation = None;
        Ok(())
    }
    fn consume_fused_constructors(&mut self,owner:crate::graph::cell_births::fused::Owner,
        tasks:Vec<(Job,crate::cell::Effects)>,parents:std::sync::Arc<crate::value::parent_epoch::Base>,
        pool:&rayon::ThreadPool,owners:&mut std::vec::Drain<'_,Parked>)
        ->(Result<()>,crate::completion_events::Work,Option<crate::graph::cell_births::Counts>) {
        let mut wave=owner.start(tasks,parents,pool);
        let mut acceptance=crate::graph::cell_births::fused::Acceptance::default();
        let mut ready=Vec::new();let mut result=Ok(());
        loop {
            wave.poll(true,&mut ready);
            for event in ready.drain(..) {
                let (done,publication)=acceptance.accept(&mut self.graph,event,result.is_ok());
                if result.is_ok() {
                    #[cfg(feature="cell-sync-diagnostics")] let start=Instant::now();
                    result=(|| {
                        loop {
                            let parked=owners.next().expect("one source owner per registered Cell");
                            if parked.execution.cell==done.done.cell() {
                                self.adopt_cell_event(parked,Some(done),publication)?;
                                self.cell_execution.as_mut().unwrap().counts.scheduler.event_completed_early+=u64::from(wave.unfinished()!=0);
                                break;
                            }
                            self.adopt_cell_event(parked,None,None)?;
                        }
                        Ok(())
                    })();
                    #[cfg(feature="cell-sync-diagnostics")] {
                        let elapsed=start.elapsed().as_nanos() as u64;let stats=&mut self.graph.stats.sync_diagnostics;
                        stats.source_batches+=1;stats.source_adoption_ns+=elapsed;
                        stats.registered_source_batches+=1;stats.registered_source_adoption_ns+=elapsed;
                    }
                }
            }
            // Even a source error must drain the original fact slots before
            // the directories return and invalidate the unadopted suffix.
            if wave.finished() {break;}
        }
        let ((owner,counts,prefix),events)=wave.finish();
        self.graph.stats.constructor_fused_staging_bytes+=prefix.bytes;
        self.graph.stats.constructor_fused_early_cells+=prefix.early;
        owner.restore(&mut self.graph);acceptance.finish(&mut self.graph);
        (result,events,Some(counts))
    }
    fn drain_cell_queue(&mut self, queue: &mut Ready, pending: &mut Vec<u32>) -> Result<()> {
        while queue.flying.is_some() {self.poll_cell_queue(queue,pending,true)?;}
        self.drain_ready_queue(queue,pending)
    }
    fn drain_ready_queue(&mut self, queue: &mut Ready, pending: &mut Vec<u32>) -> Result<()> {
        if queue.owners.is_empty() { return Ok(()); }
        let mixed=queue.mixed_rules();
        let pool = self.query_workers.as_ref().unwrap().execution_pool_handle().unwrap();
        let mut tasks: Vec<_> = queue.owners.iter_mut().filter_map(|p| p.job.take()
            .map(|job| (job, std::mem::take(&mut p.execution.effects)))).collect();
        let (_,counts)=crate::graph::cell_births::isolate_roots(&mut tasks);
        self.cell_execution.as_mut().unwrap().counts.births.add(counts);
        let count = tasks.len();
        let mut owners = queue.owners.drain(..);
        let result = if count != 0 {
            #[cfg(feature="cell-sync-diagnostics")]
            let mut diagnostic = crate::sync_diagnostics::Clock::new();
            // Only the parent snapshot crosses workers. Source writes go to
            // its existing epoch overlay until all borrowed readers leave.
            let parents = self.graph.parents.freeze();
            let grain = self.cell_execution.as_ref().unwrap().grain;
            let stats = &mut self.cell_execution.as_mut().unwrap().counts;
            stats.births.root_snapshots += 1;
            stats.scheduler.queue_growths += 1;
            stats.scheduler.queue_bytes += (tasks.capacity() * std::mem::size_of::<(Job, crate::cell::Effects)>()) as u64;
            stats.scheduler.batches += 1;
            stats.scheduler.mixed_rule_batches += u64::from(mixed);
            stats.scheduler.jobs += count as u64;
            stats.scheduler.max_ready = stats.scheduler.max_ready.max(count);
            let parallel = count > 1 && tasks.iter().map(|(job, _)| job.operations()).sum::<usize>() >= grain;
            let read = crate::value::parent_epoch::Read { base: &parents, delta: None };
            let unfinished=std::sync::atomic::AtomicUsize::new(count);
            let fused=if parallel && owners.as_slice().iter().all(|p|
                match tasks.binary_search_by_key(&p.execution.cell,|t|t.0.cell()) {
                    Ok(i)=>tasks[i].0.terminal_at(p.execution.ops.len()),
                    Err(_)=>matches!(p.execution.phase,owned_cell::Phase::Complete|owned_cell::Phase::Stopped),
                }) {
                self.graph.prepare_fused_constructors(&tasks)
            } else {None};
            let clock = Instant::now();
            #[cfg(feature="cell-sync-diagnostics")] diagnostic.enter();
            let (result,events,shared)=if let Some(owner)=fused {
                self.consume_fused_constructors(owner,tasks,parents.clone(),&pool,&mut owners)
            } else {
                let consume = |completed: &mut Vec<Completed>| {
                    // A ready prefix may retain table ownership. No wait for a
                    // larger batch: small prefixes use ordinary exact validation.
                    let eligible = completed.len() <= owners.len()
                        && completed.iter().zip(owners.as_slice()).all(|(done, owner)|
                            done.done.cell() == owner.execution.cell && done.done.complete_at(owner.execution.ops.len()));
                    self.consume_cell_events(completed,eligible,&pool,|host,completed,mut registration| {
                        for done in completed {
                            loop {
                                let parked = owners.next().expect("one owner per completion");
                                if parked.execution.cell == done.done.cell() {
                                    let publication=registration.as_deref_mut().and_then(|r|r.take_births(done.done.cell()));
                                    host.adopt_cell_event(parked, Some(done),publication)?;
                                    host.cell_execution.as_mut().unwrap().counts.scheduler.event_completed_early +=
                                        u64::from(unfinished.load(std::sync::atomic::Ordering::Acquire)!=0);
                                    break;
                                }
                                // Already-complete Cells parked behind this source
                                // prefix carry no worker result, but keep effect order.
                                host.adopt_cell_event(parked, None,None)?;
                            }
                        }
                        Ok(())
                    })
                };
                if tasks.iter().any(|(job, _)| job.dependent()) {
                    let ((result, events), shared) = crate::graph::cell_births::stream_shared(
                        tasks, read, parallel.then_some(pool.as_ref()), &unfinished, consume);
                    (result, events, Some(shared))
                } else {
                    use crate::graph::cell_births::{execution_grain,execution_group,Counts};
                    let grain=execution_grain(&tasks,pool.current_num_threads());
                    let (result, events, counts) = crate::completion_events::ordered_fold(tasks,parallel.then_some(pool.as_ref()),grain,
                        execution_group,|(job, mut effects),counts| { let done = job.run(read,&mut effects.writer(),counts);
                            unfinished.fetch_sub(1,std::sync::atomic::Ordering::AcqRel);Completed { done, effects } },Counts::add,consume);
                    (result, events, Some(counts))
                }
            };
            #[cfg(feature="cell-sync-diagnostics")] diagnostic.join();
            let elapsed = clock.elapsed().as_nanos() as u64;
            drop(parents);
            let work = self.graph.parents.thaw();
            let stats = &mut self.cell_execution.as_mut().unwrap().counts;
            stats.scheduler.wait_ns += elapsed; // scope span, including source adoption
            stats.scheduler.event_waves += events.waves;
            stats.scheduler.event_early_cells += events.early;
            stats.scheduler.event_wait_ns += events.wait_ns;
            stats.scheduler.event_bytes += events.bytes;
            if let Some(shared) = shared { stats.births.add(shared); }
            if parallel { stats.births.worker_batches += 1; stats.births.worker_wait_ns += elapsed; }
            stats.births.root_writes += work.writes;
            stats.births.root_growths += work.growths;
            stats.births.root_merges += work.merged_entries;
            #[cfg(feature="cell-sync-diagnostics")]
            self.graph.stats.sync_diagnostics.constructors.record(diagnostic,None,parallel,pool.current_num_threads());
            result
        } else { Ok(()) };
        let result = result.and_then(|()| { for parked in owners { self.adopt_cell_event(parked, None,None)?; } Ok(()) });
        pending.clear(); queue.operations = 0; queue.shared = false; queue.roots = false;
        result
    }
    pub(super) fn apply_cell_batch(
        &mut self,
        rid: usize,
        rows: Vec<Binding>,
        generation: u64,
        run:&mut RunQueue,
    ) -> Result<()> {
        self.cell_execution
            .as_mut()
            .unwrap()
            .counts
            .scheduler
            .rule_groups += 1;
        let (queue,pending)=(&mut run.ready,&mut run.pending);
        self.cell_execution.as_mut().unwrap().counts.scheduler.rule_group_carries+=u64::from(!queue.is_empty());
        let roots=self.graph.program.executions[rid].births.as_ref().is_some_and(|p|p.has_roots());
        let result = (|| {
            for binding in rows {
                // The same inherited Cursor travels with the execution. When
                // older tails are pending, start_cell_execution leaves early
                // completion to this queue's source-ordered drain.
                self.graph.sealed_generation = Some(generation);
                self.begin_cell_entry(rid, &binding);
                let started = self.start_cell_execution(
                    rid,
                    binding,
                    &pending,
                    // Preserve the existing all-hit source prefix when no
                    // peer roots are outstanding. Once a group is open, its
                    // remaining instances can start on workers themselves.
                    roots && !pending.is_empty(),
                    #[cfg(feature = "structural-depth")]
                    None,
                )?;
                let Some(mut execution) = started else {
                    self.graph.end_owner_entry();
                    self.graph.sealed_input_cell = None;
                    self.graph.sealed_generation = None;
                    continue;
                };
                if queue.flying.as_ref().is_some_and(|wave|wave.unfinished()!=0) {
                    self.cell_execution.as_mut().unwrap().counts.scheduler.admission_overlap_instances+=1;
                }
                self.cell_execution
                    .as_mut()
                    .unwrap()
                    .counts
                    .scheduler
                    .instances += 1;
                loop {
                    let position = self
                        .graph
                        .rhs_frame(execution.cell)
                        .unwrap()
                        .completed_prefix;
                    if position == execution.ops.len() {
                        // No newly written fact, source effect or Cursor owns a
                        // publication here. Finishing only releases this instance;
                        // it need not wait behind unrelated infallible worker tails.
                        let release = execution.cursor.is_none()
                            && self.graph.program.rules[rid].completion == crate::cell::Completion::Constructors
                            && execution.work.facts == 0 && execution.work.updates == 0 && execution.work.unions == 0;
                        if queue.is_empty() || release {
                            if !queue.is_empty() {self.cell_execution.as_mut().unwrap().counts.scheduler.completed_without_queue+=1;}
                            self.finish_attached_cell(execution)?;
                        } else {
                            self.park_cell(queue, execution, None);
                        }
                        break;
                    }
                    if matches!(&execution.ops[position], Op::Let(_, Call::Primitive(..), _))
                        && self.graph.program.executions[rid].prepared_at(position,
                            &self.graph.program.templates[self.graph.program.rules[rid].template],
                            &self.graph.rhs_frame(execution.cell).unwrap().values) {
                        self.graph.stats.prepared_rhs_later_operations += 1;
                        self.graph.rhs_frame_mut(execution.cell).unwrap().completed_prefix = position + 1;
                        continue;
                    }
                    if self.resume_prepared_cell(&mut execution,position)? {continue;}
                    let prepared_root=execution.constructor.is_some() && self.graph.program.executions[rid]
                        .constructor.as_ref().is_some_and(|plan|plan.operation==position);
                    if roots && execution.births.is_none() && !prepared_root {
                        let stop=execution.transfers[execution.transfer..].iter().find(|t|t.op>=position)
                            .map_or(execution.ops.len(),|t|t.op);
                        let (counts,job)=self.graph.take_root_job(rid,execution.cell,stop,&pending,queue.operations,
                            &mut execution.effects.writer(),
                            #[cfg(feature="storage-metrics")] &execution.known,
                            |hash|queue.flying.as_ref().is_some_and(|w|w.contains_root(hash)))?;
                        execution.work.constructors+=counts.root_existing_reuses;
                        self.cell_execution.as_mut().unwrap().counts.births.add(counts);
                        if self.graph.rhs_frame(execution.cell).unwrap().completed_prefix!=position {continue;}
                        if let Some(job)=job {
                            let before=pending.capacity();pending.push(execution.cell);
                            let stats=&mut self.cell_execution.as_mut().unwrap().counts.scheduler;
                            stats.queue_growths+=u64::from(before!=pending.capacity());
                            stats.queue_bytes+=((pending.capacity()-before)*std::mem::size_of::<u32>()) as u64;
                            self.park_cell(queue,execution,Some(job));break;
                        }
                    }
                    // Only an unresolved root key or value dependency requires
                    // this fence. Other constructors may keep admitting while
                    // workers fill unrelated roots. Shared effects stay ordered.
                    if (queue.roots || queue.flying.as_ref().is_some_and(|w|w.has_roots()))
                        && !matches!(&execution.ops[position],Op::Copy(..))
                        && !execution.aliases.as_ref().is_some_and(|a|a[position]) {
                        let conflict=match &execution.ops[position] {
                            Op::Let(_,Call::Table(table),args) if self.graph.program.tables[*table].virtual_fact => {
                                    let (hash,blocked,counts)=self.graph.root_boundary_key(execution.cell,*table,args,&pending)?;
                                    self.cell_execution.as_mut().unwrap().counts.births.add(counts);
                                    blocked || queue.flying.as_ref().is_some_and(|w|w.contains_root(hash))
                                        || queue.owners.iter().any(|p|p.job.as_ref().and_then(Job::root_hash)==Some(hash))
                            }
                            Op::Let(_,Call::Primitive(..),_)=>false,
                            _=>true,
                        };
                        if conflict {
                            let state=self.graph.suspend_rhs(execution.cell);
                            self.drain_cell_queue(queue,pending)?;
                            self.graph.restore_rhs(state);
                            if let Some(window)=&mut execution.births {window.after_ready_batch(&self.graph);}
                        }
                    }
                    if execution.births.is_some() {
                        let stop = execution.transfers[execution.transfer..]
                            .iter()
                            .find(|t| t.op >= position)
                            .map_or(execution.ops.len(), |t| t.op);
                        let (counts, job) = self.graph.take_local_job(
                            rid,
                            execution.cell,
                            &mut execution.births,
                            stop,
                            true,
                        )?;
                        self.cell_execution
                            .as_mut()
                            .unwrap()
                            .counts
                            .births
                            .add(counts);
                        if let Some(job) = job {
                            let shared = job.dependent() || queue.shared;
                            self.cell_execution
                                .as_mut()
                                .unwrap()
                                .counts
                                .scheduler
                                .budget_checks += 1;
                            if shared {
                                let work = job.operations() + queue.operations;
                                self.cell_execution
                                    .as_mut()
                                    .unwrap()
                                    .counts
                                    .scheduler
                                    .budget_checks += 1;
                                if work > 256 {
                                    let counts = self.graph.commit_local_job(job.unstarted(),&mut execution.effects.writer())?;
                                    self.cell_execution
                                        .as_mut()
                                        .unwrap()
                                        .counts
                                        .births
                                        .add(counts);
                                    self.cell_execution
                                        .as_mut()
                                        .unwrap()
                                        .counts
                                        .scheduler
                                        .budget_flushes += 1;
                                    let state = self.graph.suspend_rhs(execution.cell);
                                    self.drain_cell_queue(queue, pending)?;
                                    self.graph.restore_rhs(state);
                                    if let Some(window) = &mut execution.births {
                                        window.after_ready_batch(&self.graph);
                                        self.cell_execution
                                            .as_mut()
                                            .unwrap()
                                            .counts
                                            .scheduler
                                            .revalidations += 1;
                                    }
                                    self.finish_attached_cell(execution)?;
                                    break;
                                }
                            }
                            let before = pending.capacity();
                            pending.push(execution.cell);
                            let stats = &mut self.cell_execution.as_mut().unwrap().counts.scheduler;
                            stats.queue_growths += u64::from(before != pending.capacity());
                            stats.queue_bytes +=
                                ((pending.capacity() - before) * std::mem::size_of::<u32>()) as u64;
                            self.park_cell(queue, execution, Some(job));
                            break;
                        }
                        if matches!(&execution.ops[position], Op::Let(_, Call::Table(_), _))
                            && !execution.aliases.as_ref().is_some_and(|a| a[position])
                        {
                            // Retain the ordinary local-dedup path when isolation is
                            // unproved. It can still reuse equal dynamic keys inside
                            // this one Cell; the queue must not replace it with replays.
                            if !queue.is_empty() {
                                let state = self.graph.suspend_rhs(execution.cell);
                                self.drain_cell_queue(queue, pending)?;
                                self.graph.restore_rhs(state);
                                if let Some(window) = &mut execution.births {
                                    window.after_ready_batch(&self.graph);
                                    self.cell_execution
                                        .as_mut()
                                        .unwrap()
                                        .counts
                                        .scheduler
                                        .revalidations += 1;
                                }
                            }
                            self.finish_attached_cell(execution)?;
                            break;
                        }
                    }
                    if !pending.is_empty()
                        && let Op::Let(_, Call::Table(_), args) = &execution.ops[position]
                    {
                        let key = self.graph.inline_arguments(execution.cell, args)?;
                        self.cell_execution
                            .as_mut()
                            .unwrap()
                            .counts
                            .scheduler
                            .operand_reads += key.len() as u64;
                        if key.spilled() {
                            let stats = &mut self.cell_execution.as_mut().unwrap().counts.scheduler;
                            stats.queue_growths += 1;
                            stats.queue_bytes +=
                                (key.capacity() * std::mem::size_of::<Value>()) as u64;
                        }
                        let (probes, mut blocked) = crate::graph::cell_births::blocked(&key, &pending);
                        self.graph.stats.rhs_pending_probes += probes;
                        let mut wave_probes=0;
                        let mut wave_dependency=blocked && queue.flying.as_ref().is_some_and(|wave|wave.references(&key,&mut wave_probes));
                        self.cell_execution.as_mut().unwrap().counts.scheduler.admission_dependency_probes+=wave_probes;
                        if wave_dependency {
                            self.cell_execution.as_mut().unwrap().counts.scheduler.admission_dependency_waits+=1;
                            let state=self.graph.suspend_rhs(execution.cell);
                            while wave_dependency {
                                self.poll_cell_queue(queue,pending,true)?;
                                wave_probes=0;
                                wave_dependency=queue.flying.as_ref().is_some_and(|wave|wave.references(&key,&mut wave_probes));
                                self.cell_execution.as_mut().unwrap().counts.scheduler.admission_dependency_probes+=wave_probes;
                            }
                            self.graph.restore_rhs(state);
                            self.cell_execution.as_mut().unwrap().counts.scheduler.admission_dependency_early+=
                                u64::from(queue.flying.as_ref().is_some_and(|wave|wave.unfinished()!=0));
                            let (probes,still_blocked)=crate::graph::cell_births::blocked(&key,&pending);
                            self.graph.stats.rhs_pending_probes+=probes;blocked=still_blocked;
                        }
                        if blocked {
                            self.graph.stats.rhs_pending_stops += 1;
                            let stop = execution.transfers[execution.transfer..]
                                .iter()
                                .find(|t| t.op >= position)
                                .map_or(execution.ops.len(), |t| t.op);
                            let (counts, job) = self.graph.take_dependent_job(
                                rid,
                                execution.cell,
                                stop,
                                key,
                                queue.operations,
                                |id| {
                                    let mut probes = 0;
                                    let at = queue
                                        .owners
                                        .binary_search_by(|p| {
                                            probes += 1;
                                            p.execution.cell.cmp(&id)
                                        })
                                        .ok();
                                    (probes, at.and_then(|at| queue.owners[at].job.as_ref()))
                                },
                            )?;
                            self.cell_execution
                                .as_mut()
                                .unwrap()
                                .counts
                                .births
                                .add(counts);
                            if let Some(job) = job {
                                let before = pending.capacity();
                                pending.push(execution.cell);
                                let stats =
                                    &mut self.cell_execution.as_mut().unwrap().counts.scheduler;
                                stats.dependency_admissions += 1;
                                stats.queue_growths += u64::from(before != pending.capacity());
                                stats.queue_bytes += ((pending.capacity() - before)
                                    * std::mem::size_of::<u32>())
                                    as u64;
                                self.park_cell(queue, execution, Some(job));
                                break;
                            }
                            self.cell_execution
                                .as_mut()
                                .unwrap()
                                .counts
                                .scheduler
                                .dependency_flushes += 1;
                            let state = self.graph.suspend_rhs(execution.cell);
                            self.drain_cell_queue(queue, pending)?;
                            self.graph.restore_rhs(state);
                        }
                    }
                    if !pending.is_empty()
                        && matches!(&execution.ops[position], Op::Set(..) | Op::Union(..))
                    {
                        self.cell_execution
                            .as_mut()
                            .unwrap()
                            .counts
                            .scheduler
                            .effect_flushes += 1;
                        let state = self.graph.suspend_rhs(execution.cell);
                        self.drain_cell_queue(queue, pending)?;
                        self.graph.restore_rhs(state);
                    }
                    execution.phase = owned_cell::Phase::Boundary;
                    self.resolve_cell_boundary(&mut execution, position)?;
                }
                self.graph.end_owner_entry();
                self.poll_cell_queue(queue,pending,false)?;
                if queue.owners.len() >= READY_LIMIT {self.dispatch_cell_queue(queue,pending)?;}
                self.graph.sealed_input_cell = None;
                self.graph.sealed_generation = None;
            }
            Ok(())
        })();
        // Earlier infallible tails must finish even when admission of a later
        // source instance fails (for example, exhausted Cell identities).
        if result.is_err() {
            self.graph.promote_active();
            self.graph.end_owner_entry();
        }
        if result.is_err() {
            if !queue.is_empty() {self.cell_execution.as_mut().unwrap().counts.scheduler.error_fences+=1;}
            self.drain_cell_queue(queue,pending)?;
        }
        result
    }
    fn park_cell(&mut self, queue: &mut Ready, execution: owned_cell::Execution, job: Option<Job>) {
        let context = self.graph.suspend_rhs(execution.cell);
        let before = queue.owners.capacity();
        if let Some(job) = &job {
            queue.operations += job.operations();
            queue.shared |= job.dependent();
            queue.roots |= job.starts_root();
        }
        queue.owners.push(Parked {
            execution,
            context,
            job,
        });
        let stats = &mut self.cell_execution.as_mut().unwrap().counts.scheduler;
        stats.queue_growths += u64::from(before != queue.owners.capacity());
        stats.queue_bytes +=
            ((queue.owners.capacity() - before) * std::mem::size_of::<Parked>()) as u64;
    }
}
