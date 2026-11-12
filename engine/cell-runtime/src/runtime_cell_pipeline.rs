//! Pipeline bounded, proven terminal waves with source admission. Conflicting
//! effects and cross-wave result dependencies retain their existing fences.
use super::*;
use crate::{completion_events::Background,graph::cell_births};
use std::collections::VecDeque;

pub(super) struct Flying {
    owners:VecDeque<Parked>,
    producer:Background<Completed,cell_births::Counts>,
    ready:Vec<Completed>,
    clock:Instant,
    root_hashes:Vec<u64>,
    #[cfg(feature="cell-sync-diagnostics")] diagnostic:crate::sync_diagnostics::Clock,
}
impl Flying {
    pub fn unfinished(&self)->usize {self.producer.unfinished()}
    pub fn has_roots(&self)->bool {!self.root_hashes.is_empty()}
    pub fn contains_root(&self,hash:u64)->bool {self.root_hashes.binary_search(&hash).is_ok()}
    pub fn references(&self,key:&[Value],probes:&mut u64)->bool {
        key.iter().any(|v| { *probes+=1;match v {
            Value::Eq(id)=>self.owners.binary_search_by(|p| {*probes+=1;p.execution.cell.cmp(&((*id>>32) as u32))}).is_ok(),
            Value::Set(values)=>self.references(values,probes),_=>false,
        }})
    }
}

impl Executor {
    pub(super) fn dispatch_cell_queue(&mut self,queue:&mut Ready,pending:&mut Vec<u32>)->Result<()> {
        // Two original owner buffers bound storage: one executing and one
        // being admitted. A full next buffer waits only for its older wave.
        while queue.flying.is_some() {self.poll_cell_queue(queue,pending,true)?;}
        let count=queue.owners.iter().filter(|p|p.job.is_some()).count();
        let supported=count>1 && self.graph.pipelined_births_ready()
            && queue.operations>=self.cell_execution.as_ref().unwrap().grain
            && queue.owners.iter().all(|p|p.job.as_ref().is_none_or(|j|j.terminal_at(p.execution.ops.len())));
        if !supported {
            self.cell_execution.as_mut().unwrap().counts.scheduler.admission_fence_fallbacks+=1;
            return self.drain_ready_queue(queue,pending);
        }
        let pool=self.query_workers.as_ref().unwrap().execution_pool_handle().unwrap();
        let mut tasks:Vec<_>=queue.owners.iter_mut().filter_map(|p|p.job.take()
            .map(|j|(j,std::mem::take(&mut p.execution.effects)))).collect();
        // Only absence certificates cross this admission boundary. The actual
        // bindings and result slots remain in their original worker jobs.
        let (root_hashes,counts)=cell_births::isolate_roots(&mut tasks);
        self.cell_execution.as_mut().unwrap().counts.births.add(counts);
        let shared=tasks.iter().any(|(job,_)|job.dependent());
        let parents=self.graph.parents.freeze();
        let stats=&mut self.cell_execution.as_mut().unwrap().counts;
        stats.births.root_snapshots+=1;stats.births.worker_batches+=1;
        stats.scheduler.batches+=1;stats.scheduler.jobs+=count as u64;
        stats.scheduler.max_ready=stats.scheduler.max_ready.max(count);
        stats.scheduler.queue_growths+=1;
        stats.scheduler.queue_bytes+=(tasks.capacity()*std::mem::size_of::<(Job,crate::cell::Effects)>()) as u64;
        stats.scheduler.admission_waves+=1;stats.scheduler.admission_jobs+=count as u64;
        #[cfg(feature="cell-sync-diagnostics")]
        let mut diagnostic=crate::sync_diagnostics::Clock::new();
        #[cfg(feature="cell-sync-diagnostics")] diagnostic.enter();
        let clock=Instant::now();
        let producer=Background::start(count,&pool,move |out| {
            let read=crate::value::parent_epoch::Read {base:&parents,delta:None};
            if shared {cell_births::produce_shared(tasks,read,|i,done|out.send(i,done))}
            else {
                use rayon::prelude::*;
                let grain=cell_births::execution_grain(&tasks,rayon::current_num_threads());
                tasks.into_par_iter().enumerate()
                    .fold_chunks(grain,cell_births::execution_group,|mut counts,(i,(job,mut effects))| {
                        let done=job.run(read,&mut effects.writer(),&mut counts);out.send(i,Completed {done,effects});counts
                    }).reduce(cell_births::Counts::default,|mut a,b| {a.add(b);a})
            }
        });
        let owners=std::mem::replace(&mut queue.owners,std::mem::take(&mut queue.spare));
        queue.flying=Some(Flying {owners:owners.into(),producer,
            ready:Vec::new(),clock,root_hashes,#[cfg(feature="cell-sync-diagnostics")] diagnostic});
        queue.operations=0;queue.shared=false;queue.roots=false;Ok(())
    }

    pub(super) fn poll_cell_queue(&mut self,queue:&mut Ready,pending:&mut Vec<u32>,wait:bool)->Result<()> {
        let Some(mut wave)=queue.flying.take() else {return Ok(());};
        self.cell_execution.as_mut().unwrap().counts.scheduler.admission_polls+=1;
        wave.producer.poll(wait,&mut wave.ready);
        self.cell_execution.as_mut().unwrap().counts.scheduler.admission_empty_polls+=u64::from(wave.ready.is_empty());
        let count=wave.ready.len();
        let pool=self.query_workers.as_ref().unwrap().execution_pool_handle().unwrap();
        let eligible=!wave.ready.is_empty() && wave.ready.iter().zip(wave.owners.iter()).all(|(done,owner)|
            done.done.cell()==owner.execution.cell && done.done.complete_at(owner.execution.ops.len()));
        let result=self.consume_cell_events(&mut wave.ready,eligible,&pool,|host,completed,mut registration| {
            for done in completed {
                loop {
                    let parked=wave.owners.pop_front().expect("source owner for completed job");
                    if parked.execution.cell==done.done.cell() {
                        let publication=registration.as_deref_mut().and_then(|r|r.take_births(done.done.cell()));
                        host.adopt_cell_event(parked,Some(done),publication)?;
                        host.cell_execution.as_mut().unwrap().counts.scheduler.event_completed_early+=
                            u64::from(wave.producer.unfinished()!=0);
                        break;
                    }
                    host.adopt_cell_event(parked,None,None)?;
                }
            }
            Ok(())
        });
        if result.is_ok() {pending.drain(..count);}
        if result.is_ok() && !wave.producer.finished() {queue.flying=Some(wave);return Ok(());}
        // Completion of the producer also joins its peer readers. A source
        // error waits for those private readers but never adopts later rows.
        let (shared,events)=wave.producer.finish();
        let work=self.graph.parents.thaw();
        let elapsed=wave.clock.elapsed().as_nanos() as u64;
        let stats=&mut self.cell_execution.as_mut().unwrap().counts;
        stats.births.add(shared);stats.births.root_writes+=work.writes;
        stats.births.root_growths+=work.growths;stats.births.root_merges+=work.merged_entries;
        stats.births.worker_wait_ns+=elapsed;stats.scheduler.wait_ns+=elapsed;
        stats.scheduler.event_waves+=events.waves;stats.scheduler.event_early_cells+=events.early;
        stats.scheduler.event_wait_ns+=events.wait_ns;stats.scheduler.event_bytes+=events.bytes;
        #[cfg(feature="cell-sync-diagnostics")] {
            wave.diagnostic.join();self.graph.stats.sync_diagnostics.constructors.record(
                wave.diagnostic,None,true,pool.current_num_threads());
        }
        if let Err(error)=result {
            queue.owners.clear();queue.operations=0;queue.shared=false;pending.clear();return Err(error);
        }
        for parked in wave.owners.drain(..) {self.adopt_cell_event(parked,None,None)?;}
        let spare:Vec<_>=wave.owners.into();
        if queue.owners.is_empty() && queue.owners.capacity()<spare.capacity() {queue.owners=spare;}
        else if queue.spare.capacity()<spare.capacity() {queue.spare=spare;}
        Ok(())
    }
}
