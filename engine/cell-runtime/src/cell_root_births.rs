//! Continue a compiled root using its admission key exactly once. An existing
//! exact result fills the instance directly; proven absence starts the fresh
//! cone on a worker. Peers resolve duplicate roots in their existing slots
//! before using the returned identity in downstream constructors.
use super::*;

/// Distinct root hashes prove distinct exact keys, never the converse. Such a
/// root's fresh cone cannot alias an old source-created anchor. If the compiler
/// also proves the local tail complete, omit peer slots and recursive helping.
pub(crate) fn isolate(tasks:&mut [(Job,crate::cell::Effects)]) -> (Vec<u64>,Counts) {
    let mut counts=Counts::default();
    let mut hashes:Vec<_>=tasks.iter().filter_map(|(job,_)|job.root_hash()).collect();
    counts.root_hash_bytes=(hashes.capacity()*std::mem::size_of::<u64>()) as u64;
    hashes.sort_unstable_by(|a,b| {counts.directory_checks+=1;a.cmp(b)});
    for (job,_) in tasks {
        let Some(hash)=job.root_hash() else {continue;};
        if job.from+1<job.limit && !job.plan.isolated[job.from+1] {continue;}
        let first=hashes.partition_point(|&h| {counts.directory_checks+=1;h<hash});
        if hashes.get(first+1)!=Some(&hash) {
            job.isolated=true;counts.root_isolated+=1;
        }
    }
    hashes.dedup();(hashes,counts)
}

impl Graph {
    pub(crate) fn root_boundary_key(&self,cell:u32,table:usize,args:&[Arg],pending:&[u32])
        ->Result<(u64,bool,Counts)> {
        let key=self.inline_arguments(cell,args)?;
        let (probes,blocked)=super::blocked(&key,pending);
        Ok((self.constructor_hash(table,&key),blocked,Counts {
            root_boundary_probes:1,source_operand_reads:key.len() as u64,
            dependency_proofs:probes,..Counts::default()}))
    }
    /// An exact hit completes this source operation in the existing slots;
    /// otherwise return its worker cone or leave the frontier unchanged.
    /// No new graph row or publication is installed by the exact-hit path.
    pub(crate) fn take_root_job(&mut self,rule:usize,cell:u32,stop:usize,
        pending:&[u32],operations:usize,receipts:&mut EffectWriter<'_>,
        #[cfg(feature="storage-metrics")] known:&crate::cell::QueryFacts,
        unregistered:impl Fn(u64,&[Value])->bool)->Result<(Counts,Option<Job>)> {
        let mut counts=Counts::default();
        if !self.local_jobs_supported() || !self.pipelined_births_ready() {return Ok((counts,None));}
        let position=self.rhs_frame(cell).unwrap().completed_prefix;
        let Some(plan)=self.program.executions[rule].births.as_ref() else {return Ok((counts,None));};
        let Ok(from)=plan.steps.binary_search_by_key(&position,|s|s.operation) else {return Ok((counts,None));};
        if !plan.roots[from] || stop!=self.program.templates[self.rhs_frame(cell).unwrap().template].ops.len()
            || operations+plan.steps.len()-from>256 {return Ok((counts,None));}
        let step=&plan.steps[from];
        let key=self.inline_arguments(cell,&step.keys)?;
        counts.source_operand_reads+=key.len() as u64;
        let (probes,blocked)=super::blocked(&key,pending);
        counts.dependency_proofs+=probes;
        if blocked {return Ok((counts,None));}
        counts.root_bucket_probes+=1;
        let hash=self.constructor_hash(step.table,&key);
        if unregistered(hash,&key) {counts.root_pending+=1;return Ok((counts,None));}
        // The authoritative lookup consumes the already canonical key/hash.
        // A nonempty hash bucket alone proves neither presence nor absence.
        // This sealed region excludes union, deletion and mutable effects.
        let shared=self.intern.leased(step.table);
        let row=if shared {
            // Only this proven root admission may read a live worker index.
            // The caller excludes every in-flight root hash and every value
            // in its fresh cone, including already-adopted earlier Cells.
            // Thus absent leased fact slots cannot hide an exact candidate.
            #[cfg(feature="family-overlap")]
            let clock=crate::family_overlap::clock();
            let Some(row)=self.intern.shared_bucket(step.table,hash,|bucket| {
                if bucket.is_none() {return Ok(None);}
                counts.root_bucket_fallbacks+=1;
                self.key_lookup_calls.set(self.key_lookup_calls.get()+1);
                self.lookup_settled_constructor_bucket(step.table,&key,bucket)
            }) else {return Ok((counts,None));};
            #[cfg(feature="rhs-work-audit")]
            if let Ok(Some(r))=&row {self.rhs_births.read(r.witness);}
            #[cfg(feature="family-overlap")]
            crate::family_overlap::physical(step.table,0,clock,||key.iter().cloned().enumerate().collect());
            self.stats.constructor_pipeline_root_reads+=1;
            row?
        } else if self.intern.contains_key(step.table, &hash) {
            counts.root_bucket_fallbacks+=1;
            self.lookup_canonical_hashed(step.table,&key,Some(hash))?
        } else {None};
        if let Some(row)=row {
            let destination=step.destination;
            #[cfg(feature="storage-metrics")]
            let probe=crate::rhs_projection_trace::before(self,rule,cell,position,known);
            receipts.record(position,row.witness);
            self.composition_result_entry(cell,position,row.witness,!row.hidden);
            let frame=self.rhs_frame_mut(cell).unwrap();
            frame.values.insert(destination,row.values.last().unwrap().clone());
            frame.completed_prefix=position+1;
            self.stats.constructor_requests+=1;
            self.stats.constructor_reused+=1;
            #[cfg(feature="storage-metrics")]
            crate::rhs_projection_trace::after(self,probe,&crate::cell::SingleEffect(position,row.witness),true);
            counts.root_existing_reuses+=1;
            counts.root_existing_key_fields+=key.len() as u64;
            self.stats.constructor_pipeline_root_hits+=u64::from(shared);
            return Ok((counts,None));
        }
        counts.root_collision_misses+=u64::from(counts.root_bucket_fallbacks!=0);
        let value=Value::Eq(((cell as u64)<<32)|(step.destination as u64+1));
        if canon(&value,&self.parents)!=value {return Ok((counts,None));}
        let plan=plan.clone();counts.plan_handles+=1;
        // Keep any parent-projected inputs in the same instance. Results of
        // this region remain implicit addresses or actual peer result aliases.
        for arg in plan.steps[from..].iter().flat_map(|s|&s.keys).chain(
            plan.units.iter().flat_map(|u|u.sites.iter().flat_map(|s|&s.keys))) {
            let Arg::Slot(slot)=arg else {continue;};
            if !self.rhs_frame(cell).unwrap().values.contains_key(slot)
                && plan.definitions.binary_search_by_key(slot,|&(s,_)|s).ok()
                    .is_none_or(|i|plan.definitions[i].1<position) {
                let value=self.slot(cell,*slot)?;
                counts.captured_reads+=1;counts.captured_writes+=1;
                let values=&mut self.rhs_frame_mut(cell).unwrap().values;
                let before=values.capacity_bytes();values.insert(*slot,value);
                let growth=values.capacity_bytes()-before;
                counts.slot_growths+=u64::from(growth!=0);counts.slot_bytes+=growth as u64;
            }
        }
        self.promote_active();
        let (values,sealed)=self.rhs_frame_mut(cell).unwrap().values.lease();
        counts.slot_leases+=1;counts.slot_seals+=u64::from(sealed);
        counts.sealed_bytes+=u64::from(sealed)*crate::slots::FrameSlots::seal_bytes() as u64;
        counts.root_jobs+=1;
        self.stats.constructor_pipeline_root_jobs+=u64::from(shared);
        let unit_epoch=plan.units.as_ref().map(|_|self.epoch);
        let limit=plan.steps.len();
        Ok((counts,Some(Job {cell,plan,frame:Local {values,facts:Default::default(),completed_prefix:position},
            from,limit,first:position,anchor:position,key,isolated:false,fresh_root:Some(from),unit_epoch,root:Some(hash),
            owner_results:self.needs_worker_owner_results(rule,cell)})))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cell::Effects;
    use std::sync::atomic::AtomicUsize;

    #[test]
    fn shared_root_reads_keep_hidden_witnesses_and_reject_hash_collisions() {
        for hidden in [false,true] {
            let mut g=super::super::tests::graph();
            let (old,_,_)=super::super::tests::start(&mut g);
            if hidden {g.hide(0,&[Value::Eq(100)],false).unwrap();}
            let witness=FactRef {cell:old,op:0};
            let collision=g.constructor_hash(0,&[Value::Eq(200)]);
            assert!(!g.intern.contains_key(0,&collision));
            g.intern.entry(0,collision).or_default().insert(witness);
            let index=g.intern.take(0,true);
            let reuse=g.begin_transient(0,[(0,Value::Eq(100))].into_iter().collect(),None).unwrap();
            let mut effects=Effects::default();
            let (counts,job)=g.take_root_job(0,reuse,4,&[],0,&mut effects.writer(),
                #[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
            assert!(job.is_none());assert_eq!(counts.root_existing_reuses,1);
            assert_eq!(g.slot(reuse,1).unwrap(),g.slot(old,1).unwrap());
            assert_eq!(g.fact(witness).unwrap().unwrap().hidden,hidden);
            g.promote_active();
            let fresh=g.begin_transient(0,[(0,Value::Eq(200))].into_iter().collect(),None).unwrap();
            let (counts,job)=g.take_root_job(0,fresh,4,&[],0,&mut effects.writer(),
                #[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
            assert_eq!(counts.root_collision_misses,1);assert!(job.is_some());
            assert_eq!(g.stats.constructor_pipeline_root_hits,1);
            g.intern.restore(0,index);g.intern.remove(0,&collision);
            let done=job.unwrap().run(g.parents.reader(),&mut effects.writer(),&mut Counts::default());
            g.commit_local_job(done,&mut effects.writer()).unwrap();
            assert_ne!(g.slot(fresh,1).unwrap(),g.slot(old,1).unwrap());
        }
    }

    #[test]
    fn owned_pending_keys_cannot_prove_a_fresh_root() {
        let mut g=super::super::tests::graph();
        g.program.repair_ports=crate::graph::repair_ports::Plan::derive(&g.program);
        g.use_cell_ownership().unwrap();
        let (old,_,_)=super::super::tests::start(&mut g);
        g.repair().unwrap();
        // Commit equality without completing its owned keys. Unlike legacy
        // subscriptions, this pending work need not appear in graph.dirty.
        g.union(100,50).unwrap();
        assert!(g.pending_unions.is_empty() && g.dirty.is_empty() && g.dirty_markers.is_empty());
        assert!(!g.ownership_settled());
        let cell=g.begin_transient(0,[(0,Value::Eq(50))].into_iter().collect(),None).unwrap();
        let mut effects=Effects::default();
        let (counts,job)=g.take_root_job(0,cell,4,&[],0,&mut effects.writer(),
            #[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
        assert!(job.is_none());assert_eq!(counts.root_bucket_probes,0);
        g.repair().unwrap();
        let (counts,job)=g.take_root_job(0,cell,4,&[],0,&mut effects.writer(),
            #[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
        assert!(job.is_none());assert_eq!(counts.root_existing_reuses,1);
        assert_eq!(g.slot(cell,1).unwrap(),g.slot(old,1).unwrap());
    }

    #[test]
    fn disjoint_complete_roots_need_no_peer_slots_and_hash_collisions_keep_sharing() {
        for collide in [false,true] {
            let mut g=super::super::tests::graph();
            let template=&mut g.program.templates[0];
            std::sync::Arc::make_mut(&mut template.ops).remove(2);
            template.defs.remove(&3);template.defs.insert(4,2);
            g.program.known_results.static_skip[0]=std::rc::Rc::new(vec![false;3]);
            g.program.executions[0].births=Plan::derive(&g.program,0).map(std::sync::Arc::new);
            let mut tasks=Vec::new();
            for input in [100,200] {
                let cell=g.begin_transient(0,[(0,Value::Eq(input))].into_iter().collect(),None).unwrap();
                let (_,job)=g.take_root_job(0,cell,3,&[],tasks.len()*3,&mut crate::cell::Effects::default().writer(),#[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
                let mut job=job.unwrap();
                if collide {job.root=Some(0);}
                tasks.push((job,Effects::default()));
            }
            let (_,counts)=isolate(&mut tasks);
            assert_eq!(counts.root_isolated,if collide {0}else{2});
            assert!(tasks.iter().all(|(j,_)|j.dependent()==collide));
            if !collide {
                for (job,mut effects) in tasks {
                    let mut counts=Counts::default();
                    let done=job.run(g.parents.reader(),&mut effects.writer(),&mut counts);
                    counts.add(g.commit_local_job(done,&mut effects.writer()).unwrap());
                    assert_eq!(counts.root_births,1);assert_eq!(counts.local_births,3);
                    assert_eq!(counts.shared_slots,0);
                }
                assert_eq!(g.stats.logical_facts_created,6);
            }
        }
    }

    #[test]
    fn duplicate_roots_resolve_before_their_descendants_without_a_source_anchor() {
        for workers in [1,4] {
            let mut control=super::super::tests::graph();
            for _ in 0..8 {
                let cell=control.begin_transient(0,[(0,Value::Eq(100))].into_iter().collect(),None).unwrap();
                for (op,input,dst) in [(0,0,1),(1,1,2),(2,1,3),(3,2,4)] {
                    control.construct(cell,op,0,&[Arg::Slot(input)],dst).unwrap();
                }
                control.promote_active();
            }
            let mut g=super::super::tests::graph();let mut tasks=Vec::new();let mut pending=Vec::new();
            let mut counts=Counts::default();
            for _ in 0..8 {
                let cell=g.begin_transient(0,[(0,Value::Eq(100))].into_iter().collect(),None).unwrap();
                let (work,job)=g.take_root_job(0,cell,4,&pending,tasks.len()*4,&mut crate::cell::Effects::default().writer(),#[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();counts.add(work);
                let job=job.expect("empty authoritative root bucket");
                assert!(g.cells[&cell].facts.is_empty(),"source has not constructed an anchor");
                assert!(job.terminal_at(4),"disjoint root hashes may overlap the next admission wave");
                pending.push(cell);tasks.push((job,Effects::default()));
            }
            let parents=g.parents.freeze();let pool=rayon::ThreadPoolBuilder::new().num_threads(workers).build().unwrap();
            let unfinished=AtomicUsize::new(tasks.len());
            let ((result,_),work)=stream_shared(tasks,Read {base:&parents,delta:None},Some(&pool),&unfinished,|ready| {
                for mut d in ready.drain(..) {
                    counts.add(g.commit_local_job(d.done,&mut d.effects.writer())?);
                }
                Ok::<_,String>(())
            });
            result.unwrap();counts.add(work);drop(parents);g.parents.thaw();
            assert_eq!((counts.root_jobs,counts.root_births,counts.root_reuses),(8,1,7));
            assert_eq!((counts.local_births,counts.local_reuses),(3,29));
            assert_eq!(g.key_lookup_calls.get(),0,"no ordinary source constructor lookup");
            assert_eq!(g.export().unwrap(),control.export().unwrap());
            assert_eq!(g.stats.constructor_requests,control.stats.constructor_requests);
            assert_eq!(g.stats.constructor_reused,control.stats.constructor_reused);
            assert!(pending.iter().all(|c|g.slot(*c,1).unwrap()==g.slot(pending[0],1).unwrap()));
            let a=g.slot(pending[0],1).unwrap();let b=g.slot(pending[0],2).unwrap();
            g.enqueue_union(a.clone(),b.clone()).unwrap();control.enqueue_union(a,b).unwrap();
            g.repair().unwrap();control.repair().unwrap();
            assert_eq!(g.export().unwrap(),control.export().unwrap(),"later congruence repair");
        }
    }

    #[test]
    fn occupied_root_completes_once_and_pending_union_keeps_source_completion() {
        for hidden in [false,true] {
        let mut g=super::super::tests::graph();
        let (old,_,_)=super::super::tests::start(&mut g);
        g.epoch=1;
        if hidden {assert!(g.hide(0,&[Value::Eq(100)],false).unwrap());}
        let mut effects=Effects::begin(std::sync::Arc::new(crate::cell::EffectPlan::compile(
            &g.program,0,&[],0,true)),vec![],false);
        let before=(g.stats.constructor_requests,g.stats.constructor_reused,g.key_lookup_calls.get());
        let cell=g.begin_transient(0,[(0,Value::Eq(100))].into_iter().collect(),None).unwrap();
        #[cfg(feature="storage-metrics")]
        crate::rhs_projection_trace::start(8,&g.program);
        let (counts,job)=g.take_root_job(0,cell,4,&[],0,&mut effects.writer(),#[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
        assert!(job.is_none());assert_eq!(counts.root_bucket_fallbacks,1);
        assert_eq!(counts.root_existing_reuses,1);
        assert_eq!(counts.root_existing_key_fields,1);
        assert_eq!(g.rhs_frame(cell).unwrap().completed_prefix,1);
        assert_eq!(g.slot(cell,1).unwrap(),g.slot(old,1).unwrap());
        assert_eq!(crate::cell::CompletedEffects::get(&effects,0),Some(Dependency::Fact(FactRef{cell:old,op:0})));
        assert_eq!((g.stats.constructor_requests,g.stats.constructor_reused,g.key_lookup_calls.get()),
            (before.0+1,before.1+1,before.2+1));
        assert_eq!(g.fact(FactRef{cell:old,op:0}).unwrap().unwrap().hidden,hidden);
        #[cfg(feature="storage-metrics")]
        {
            let trace=crate::rhs_projection_trace::finish();
            assert_eq!(trace["trace"]["boundaries"].as_array().unwrap().len(),1);
            assert_eq!(trace["trace"]["boundaries"][0]["receipt"],
                serde_json::to_value(Dependency::Fact(FactRef{cell:old,op:0})).unwrap());
            assert_eq!(trace["trace"]["boundaries"][0]["success"],true);
        }
        g.promote_active();
        let cell=g.begin_transient(0,[(0,Value::Eq(200))].into_iter().collect(),None).unwrap();
        let (counts,job)=g.take_root_job(0,cell,4,&[],0,&mut crate::cell::Effects::default().writer(),#[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|true).unwrap();
        assert!(job.is_none());assert_eq!(counts.root_pending,1);
        assert_eq!(counts.slot_leases,0,"an in-flight hash is not proof of absence");
        g.enqueue_union(Value::Eq(100),Value::Eq(200)).unwrap();
        let (counts,job)=g.take_root_job(0,cell,4,&[],0,&mut crate::cell::Effects::default().writer(),#[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
        assert!(job.is_none());assert_eq!(counts.root_bucket_probes,0);
        }
    }

    #[test]
    fn unrelated_hash_candidates_prove_absence_without_reusing_the_wrong_result() {
        let mut g=super::super::tests::graph();
        let (old,_,_)=super::super::tests::start(&mut g);
        let candidate=FactRef {cell:old,op:0};
        let key=[Value::Eq(200)];let hash=g.constructor_hash(0,&key);
        // Inject an unrelated candidate exactly as a hash collision would.
        // The original bucket remains intact; remove this test incidence
        // after admission so later index maintenance has its normal topology.
        assert!(!g.intern.contains_key(0, &hash));
        g.intern.entry(0, hash).or_default().insert(candidate);
        let cell=g.begin_transient(0,[(0,key[0].clone())].into_iter().collect(),None).unwrap();
        let mut effects=Effects::default();
        let (mut counts,job)=g.take_root_job(0,cell,4,&[],0,&mut effects.writer(),#[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap();
        assert_eq!(counts.root_existing_reuses,0);
        assert_eq!(counts.root_collision_misses,1);
        let job=job.expect("exact miss admits the existing compiled worker cone");
        g.intern.remove(0, &hash);
        let done=job.run(g.parents.reader(),&mut effects.writer(),&mut counts);
        counts.add(g.commit_local_job(done,&mut effects.writer()).unwrap());
        assert_eq!(counts.root_births,1);
        assert_ne!(g.slot(cell,1).unwrap(),g.slot(old,1).unwrap());
        assert_eq!(g.lookup_canonical(0,&key).unwrap().unwrap().witness,Dependency::Fact(FactRef{cell,op:0}));
    }
}
