//! A closed source admission region lets its producer workers keep the actual
//! constructor directory through registration. Completion events carry the
//! original fact slots alongside the completed Cell, not a second row log.
use super::*;
use crate::completion_events::Continued;

pub(crate) struct Owner {
    directory:Owned,subscriptions:Option<Subscriptions>,
    frames:std::vec::IntoIter<CellReady>,rows:u64,
}
pub(crate) struct Ready {pub completed:Completed,frame:CellReady}
pub(crate) type Wave=Continued<Completed,Ready,Owner,Counts>;

impl Graph {
    pub(crate) fn constructor_table_leased(&self,table:usize)->bool {self.intern.leased(table)}
    pub(crate) fn prepare_pipelined_constructors(&mut self,tasks:&[(Job,crate::cell::Effects)])->Option<Owner> {
        // Source admission may still read any previously visible fact. Only
        // new frames can leave here; existing prefixes stay source-readable.
        // Ownership uses static ports, so no global reverse directory is leased.
        if self.ownership.is_none() || tasks.iter().any(|(j,_)|
            self.cells.get(&j.cell).is_none_or(|c|!c.facts.is_empty())) {return None;}
        let owner=self.prepare_constructor_region(tasks,true)?;
        self.stats.constructor_pipeline_regions+=1;
        self.stats.constructor_pipeline_cells+=tasks.len() as u64;
        Some(owner)
    }
    pub(crate) fn prepare_fused_constructors(&mut self,tasks:&[(Job,crate::cell::Effects)])->Option<Owner> {
        self.prepare_constructor_region(tasks,false)
    }
    fn prepare_constructor_region(&mut self,tasks:&[(Job,crate::cell::Effects)],readable:bool)->Option<Owner> {
        if !self.local_registration_supported() || !self.pipelined_births_ready()
            || crate::sync_diagnostics::registry_inline() || tasks.len()<2 {return None;}
        let operations:usize=tasks.iter().map(|(j,_)|j.operations()).sum();
        if operations<32 || !tasks.windows(2).all(|w|w[0].0.cell<w[1].0.cell) {return None;}
        // This preflight uses the already-admitted Cell plans. No effects,
        // missing fact slots or subscriptions may be invented by registration.
        let mut tables=BTreeSet::new();
        let owned=self.ownership.is_some();
        for (i,(job,_)) in tasks.iter().enumerate() {
            let frame=self.cells.get(&job.cell)?;
            let end=self.program.templates[frame.template].ops.len();
            if job.unit_epoch.is_some() || !job.terminal_at(end)
                || frame.parent.is_some_and(|p|tasks.binary_search_by_key(&p.cell,|t|t.0.cell).is_ok_and(|p|p>=i))
                || !job.plan.steps[job.from..job.limit].iter().all(|s|
                    s.operation>=frame.completed_prefix && !frame.facts.contains_key(&(s.operation as u32))
                    && self.program.repair_ports.key_eq_columns[s.table].is_some()
                    && (!owned || self.program.cell_ownership.markers[frame.template].program.covers(s.operation))) {return None;}
            tables.extend(job.plan.steps[job.from..job.limit].iter().map(|s|s.table));
        }
        let frames:Vec<_>=tasks.iter().map(|(job,_)| {
            let frame=self.cells.get_mut(&job.cell).unwrap();
            CellReady {facts:std::mem::take(&mut frame.facts),installed:Installed {
                cell:job.cell,first:frame.completed_prefix,end:job.plan.steps[job.limit-1].operation+1,owned,
                publication:Publication::default()}}
        }).collect();
        // The existing owners share this empty input header. Rows stay in each
        // producer's Piece; there is no flattened Input row buffer to refill.
        let input=std::sync::Arc::new(Input {groups:Vec::new(),rows:Vec::new(),owned});
        let directory=Owned {frames:Vec::new(),directory:Directory::take(self,tables.into_iter(),readable),
            epoch:self.epoch,input:input.clone()};
        let subscriptions=(!owned).then(||Subscriptions {uses:std::mem::take(&mut self.uses),
            metrics:std::mem::take(&mut self.maintenance),
            columns:self.program.repair_ports.key_eq_columns.clone(),input});
        self.stats.constructor_fused_regions+=1;self.stats.constructor_fused_cells+=tasks.len() as u64;
        self.stats.constructor_fused_planned_operations+=operations as u64;
        self.stats.constructor_registry_batches+=1;
        self.stats.constructor_registry_independent_batches+=1;
        self.stats.constructor_registry_functionless_batches+=1;
        self.stats.constructor_registry_bytes+=directory.storage_bytes() as u64;
        if readable {self.stats.constructor_registry_bytes+=(directory.directory.len()
            *(std::mem::size_of::<std::sync::RwLock<constructor_index::Table>>()+2*std::mem::size_of::<usize>())) as u64;}
        self.stats.constructor_registry_frame_bytes+=(frames.capacity()*std::mem::size_of::<CellReady>()) as u64;
        Some(Owner {directory,subscriptions,frames:frames.into_iter(),rows:0})
    }
}

impl Owner {
    fn complete(&mut self,mut completed:Completed)->Ready {
        let mut frame=self.frames.next().expect("one fact owner per admitted Cell");
        let cell=completed.done.cell;
        assert_eq!(frame.installed.cell,cell);
        assert_eq!(completed.done.piece.end,frame.installed.end,"compiled terminal region must complete");
        assert!(completed.done.piece.units.is_empty());
        let directory=&mut self.directory;let rows=&completed.done.piece.rows;
        frame.installed.publication=install_cell(cell,&mut frame.facts,rows,directory.epoch,&mut directory.directory);
        if let Some(subscriptions)=&mut self.subscriptions {for row in rows {
            maintenance::subscribe_fresh(&mut subscriptions.uses,&mut subscriptions.metrics,
                Dependency::Fact(FactRef {cell,op:row.operation as u32}),&row.fields,
                Some(subscriptions.columns[row.table].as_ref().unwrap()));
        }}
        frame.installed.publication.owned=directory.input.owned;
        self.rows+=rows.len() as u64;
        // Actual field allocations now belong to the original fact slots.
        // Source adoption reads its publication certificate, without replay.
        if !directory.input.owned {completed.done.piece.rows.clear();}
        Ready {completed,frame}
    }
    pub(crate) fn start(self,tasks:Vec<(Job,crate::cell::Effects)>,parents:std::sync::Arc<crate::value::parent_epoch::Base>,pool:&rayon::ThreadPool)->Wave {
        Wave::start_continued(tasks.len(),pool,self,move |out| {
            Self::produce(tasks,Read {base:&parents,delta:None},|index,done|out.complete(index,done,Self::complete))
        })
    }
    fn produce(tasks:Vec<(Job,crate::cell::Effects)>,read:Read<'_>,emit:impl Fn(usize,Completed)+Sync)->Counts {
        if tasks.iter().any(|(j,_)|j.dependent()) {produce_shared(tasks,read,emit)} else {
            use rayon::prelude::*;
            let grain=execution_grain(&tasks,rayon::current_num_threads());
            tasks.into_par_iter().enumerate().fold_chunks(grain,execution_group,|mut counts,(i,(job,mut effects))| {
                let done=job.run(read,&mut effects.writer(),&mut counts);emit(i,Completed {done,effects});counts
            }).reduce(Counts::default,|mut a,b| {a.add(b);a})
        }
    }
    pub(crate) fn restore(self,graph:&mut Graph) {
        assert_eq!(self.frames.len(),0,"return every original fact owner");
        graph.stats.constructor_fused_rows+=self.rows;
        graph.stats.constructor_registry_independent_rows+=self.rows;
        graph.stats.constructor_registry_rows+=self.rows;
        graph.stats.constructor_registry_worker_rows+=self.rows;
        self.directory.restore(graph);
        if let Some(subscriptions)=self.subscriptions {subscriptions.restore(graph);}
    }
}

#[derive(Default)]
pub(crate) struct Acceptance {registration:Registration}
impl Acceptance {
    pub(crate) fn accept(&mut self,graph:&mut Graph,ready:Ready,adopt:bool)->(Completed,Option<Publication>) {
        let Ready {completed,mut frame}=ready;
        self.registration.restore_cell(graph,&mut frame);
        graph.stats.constructor_registry_frame_transfers+=1;
        let publication=if adopt {Some(self.registration.offer(frame.installed))} else {
            // Only a source error retains an unadopted suffix. Successful
            // delivery has no second vector of certificates or Cell owners.
            let before=self.registration.ready.capacity();
            self.registration.ready.push_back(vec![frame].into_iter());
            graph.stats.constructor_registry_bytes+=(((self.registration.ready.capacity()-before)
                *std::mem::size_of::<std::vec::IntoIter<CellReady>>())+std::mem::size_of::<CellReady>()) as u64;
            None
        };
        (completed,publication)
    }
    pub(crate) fn finish(self,graph:&mut Graph) {self.registration.finish(graph);}
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture()->(Graph,Vec<(Job,crate::cell::Effects)>) {
        fixture_with_ownership(false)
    }
    fn fixture_with_ownership(owned:bool)->(Graph,Vec<(Job,crate::cell::Effects)>) {
        let mut g=super::super::super::tests::graph();
        g.program.repair_ports=repair_ports::Plan::derive(&g.program);
        if owned {g.use_cell_ownership().unwrap();}
        let mut tasks=Vec::new();
        for i in 0..64 {
            let cell=g.begin_transient(0,[(0,Value::Eq(100+i/2))].into_iter().collect(),None).unwrap();
            let (_,job)=g.take_root_job(0,cell,4,&[],tasks.len()*4,&mut crate::cell::Effects::default().writer(),#[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
            tasks.push((job.unwrap(),crate::cell::Effects::default()));
        }
        (g,tasks)
    }
    #[test]
    fn producer_registration_keeps_actual_results_and_rolls_back_only_unaccepted_cells() {
        for owned in [false,true] {for workers in [1,4] {for stop in [0,1,2,31,64] {for offered in [false,true] {
            let (mut g,tasks)=fixture_with_ownership(owned);let (mut expected,reference)=fixture_with_ownership(owned);
            let pool=rayon::ThreadPoolBuilder::new().num_threads(workers).build().unwrap();
            let owner=g.prepare_fused_constructors(&tasks).unwrap();
            let parents=g.parents.freeze();let mut wave=owner.start(tasks,parents.clone(),&pool);
            let mut accept=Acceptance::default();let mut ready=Vec::new();let mut position=0;
            loop {
                wave.poll(true,&mut ready);
                for event in ready.drain(..) {
                    let (mut d,publication)=accept.accept(&mut g,event,position<stop || offered && position==stop);
                    if position<stop {
                        let cell=d.done.cell;g.commit_registered_local_job(d.done,&mut d.effects.writer(),publication).unwrap();
                        g.release_empty(cell);
                    }
                    position+=1;
                }
                if wave.finished() {break;}
            }
            let ((owner,_,work),_)=wave.finish();owner.restore(&mut g);accept.finish(&mut g);
            assert_eq!(work.waves,64);drop(parents);g.parents.thaw();
            let unfinished=std::sync::atomic::AtomicUsize::new(reference.len());let mut done=Vec::new();
            let ((result,_),_)=stream_shared(reference,expected.parents.reader(),None,&unfinished,|ready| {
                done.append(ready);Ok::<_,String>(())
            });result.unwrap();
            for mut d in done.into_iter().take(stop) {
                let cell=d.done.cell;expected.commit_local_job(d.done,&mut d.effects.writer()).unwrap();expected.release_empty(cell);
            }
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            assert_eq!(g.forward_dependency_size(),expected.forward_dependency_size());assert_eq!(g.query_versions,expected.query_versions);
            assert_eq!((g.changes.events,g.changes.distinct_events),(expected.changes.events,expected.changes.distinct_events));
            assert_eq!(g.stats.constructor_registry_adopted,3*stop.div_ceil(2) as u64);
            assert_eq!(g.stats.constructor_registry_adopted+g.stats.constructor_registry_discarded,96);
            if owned {
                assert_eq!(g.stats.constructor_registry_owned_rows,g.stats.constructor_registry_adopted);
                assert_eq!(g.ownership_report(),expected.ownership_report(),"unaccepted rows never bind owned ports");
                assert!(g.uses.is_empty(),"owned constructors have no reverse subscriptions");
            }
            for graph in [&mut g,&mut expected] {graph.union(100,101).unwrap();graph.repair().unwrap();}
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
        }}}}
    }
    #[test]
    fn unproved_or_small_regions_leave_the_existing_owners_attached() {
        for reason in 0..5 {
            let (mut g,mut tasks)=fixture();
            match reason {
                0=>tasks.truncate(7),
                1=>tasks.swap(0,1),
                2=>std::sync::Arc::make_mut(&mut tasks[0].0.plan).no_unions=false,
                3=>g.program.repair_ports.key_eq_columns=vec![None].into(),
                _=>g.enqueue_union(Value::Eq(100),Value::Eq(101)).unwrap(),
            }
            assert!(g.prepare_fused_constructors(&tasks).is_none());
            assert_eq!(g.members.len(),g.program.tables.len());
            assert_eq!(g.stats.constructor_fused_regions,0);
        }
    }
    #[test]
    fn source_completes_a_cell_before_the_producer_releases_its_directories() {
        use std::{sync::{mpsc,Mutex},time::Duration};
        let (mut g,tasks)=fixture();let pool=rayon::ThreadPoolBuilder::new().num_threads(1).build().unwrap();
        let owner=g.prepare_fused_constructors(&tasks).unwrap();let parents=g.parents.freeze();let read=parents.clone();
        let (tx,rx)=mpsc::channel();let rx=Mutex::new(rx);
        let mut wave=Wave::start_continued(tasks.len(),&pool,owner,move |out|Owner::produce(tasks,Read {base:&read,delta:None},|index,done| {
            out.complete(index,done,Owner::complete);
            if index==0 {rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();}
        }));
        let mut accept=Acceptance::default();let mut ready=Vec::new();wave.poll(true,&mut ready);
        assert_eq!(ready.len(),1);assert_eq!(wave.unfinished(),63);
        assert!(g.intern.is_empty() && g.uses.is_empty(),"the producer still owns the actual directories");
        let (mut done,publication)=accept.accept(&mut g,ready.pop().unwrap(),true);
        g.commit_registered_local_job(done.done,&mut done.effects.writer(),publication).unwrap();
        assert_eq!(g.stats.logical_facts_created,3);tx.send(()).unwrap();
        loop {
            wave.poll(true,&mut ready);
            for event in ready.drain(..) {let _=accept.accept(&mut g,event,false);}
            if wave.finished() {break;}
        }
        let ((owner,_,_),_)=wave.finish();owner.restore(&mut g);accept.finish(&mut g);
        drop(parents);g.parents.thaw();assert_eq!(g.stats.constructor_registry_discarded,93);
    }
    #[test]
    fn source_can_construct_in_another_table_while_registration_is_paused() {
        use std::{sync::{mpsc,Mutex},time::Duration};
        let mut p=super::super::super::tests::graph().program;
        let mut table=p.tables[0].clone();table.name="Other".into();p.tables.push(table);
        let mut template=p.templates[0].clone();template.name="other".into();
        for op in std::sync::Arc::make_mut(&mut template.ops) {if let Op::Let(_,Call::Table(t),_)=op {*t=1;}}
        p.templates.push(template);p.table_templates.push(1);
        let mut g=Graph::new(p).unwrap();
        g.program.repair_ports=repair_ports::Plan::derive(&g.program);g.use_cell_ownership().unwrap();
        let old=g.begin_transient(0,[(0,Value::Eq(900))].into_iter().collect(),None).unwrap();
        let old_result=g.construct(old,0,0,&[Arg::Slot(0)],1).unwrap();g.promote_active();
        let mut tasks=Vec::new();
        for i in 0..64 {
            let cell=g.begin_transient(0,[(0,Value::Eq(100+i))].into_iter().collect(),None).unwrap();
            let (_,job)=g.take_root_job(0,cell,4,&[],tasks.len()*4,&mut crate::cell::Effects::default().writer(),
                #[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
            tasks.push((job.unwrap(),crate::cell::Effects::default()));
        }
        let owner=g.prepare_pipelined_constructors(&tasks).unwrap();
        assert!(g.intern.leased(0));assert!(!g.intern.leased(1));
        let pool=rayon::ThreadPoolBuilder::new().num_threads(1).build().unwrap();
        let parents=g.parents.freeze();let read=parents.clone();
        let (tx,rx)=mpsc::channel();let rx=Mutex::new(rx);
        let mut wave=Wave::start_continued(tasks.len(),&pool,owner,move |out|Owner::produce(tasks,Read {base:&read,delta:None},|index,done| {
            out.complete(index,done,Owner::complete);
            if index==0 {rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();}
        }));
        let mut ready=Vec::new();wave.poll(true,&mut ready);
        assert_eq!(ready.len(),1);assert_eq!(wave.unfinished(),63);
        let cell=g.begin_transient(1,[(0,Value::Eq(900))].into_iter().collect(),None).unwrap();
        let result=g.construct(cell,0,1,&[Arg::Slot(0)],1).unwrap();
        assert_eq!(g.lookup(1,&[Value::Eq(900)]).unwrap().unwrap().values.last(),Some(&result));
        assert_eq!(g.members[1].len(),1);assert!(g.intern.leased(0));
        g.promote_active();
        let mut effects=crate::cell::Effects::default();
        let reuse=g.begin_transient(0,[(0,Value::Eq(900))].into_iter().collect(),None).unwrap();
        let (counts,job)=g.take_root_job(0,reuse,4,&[],0,&mut effects.writer(),
            #[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
        assert!(job.is_none());assert_eq!(counts.root_existing_reuses,1);
        assert_eq!(g.slot(reuse,1).unwrap(),old_result,"reuse the actual foreign result while its index is leased");
        g.promote_active();
        let next=g.begin_transient(0,[(0,Value::Eq(999))].into_iter().collect(),None).unwrap();
        let (_,next_job)=g.take_root_job(0,next,4,&[],0,&mut effects.writer(),
            #[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
        let next_job=next_job.expect("an unrelated root need not join the current producer");
        assert_eq!(g.stats.constructor_pipeline_root_reads,2);
        assert_eq!(g.stats.constructor_pipeline_root_hits,1);
        assert_eq!(g.stats.constructor_pipeline_root_jobs,1);
        assert_eq!(wave.unfinished(),63,"both same-table admissions precede releasing the worker");
        let mut acceptance=Acceptance::default();
        for event in ready.drain(..) {let (mut done,publication)=acceptance.accept(&mut g,event,true);
            g.commit_registered_local_job(done.done,&mut done.effects.writer(),publication).unwrap();}
        tx.send(()).unwrap();
        loop {
            wave.poll(true,&mut ready);
            for event in ready.drain(..) {acceptance.accept(&mut g,event,false);}
            if wave.finished() {break;}
        }
        let ((owner,_,_),_)=wave.finish();owner.restore(&mut g);acceptance.finish(&mut g);
        drop(parents);g.parents.thaw();
        assert!(!g.intern.leased(0));assert_eq!(g.members[0].len(),4);assert_eq!(g.members[1].len(),1);
        let done=next_job.run(g.parents.reader(),&mut effects.writer(),&mut Counts::default());
        g.commit_local_job(done,&mut effects.writer()).unwrap();
        assert!(g.lookup(0,&[Value::Eq(999)]).unwrap().is_some());
        assert_eq!(g.lookup(1,&[Value::Eq(900)]).unwrap().unwrap().values.last(),Some(&result));
        g.union(100,900).unwrap();g.repair().unwrap();
        assert!(g.lookup(1,&[Value::Eq(100)]).unwrap().is_some());
    }
}
