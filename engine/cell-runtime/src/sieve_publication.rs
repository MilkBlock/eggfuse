//! Complete the existing Cell condition DAG in dependency order. Workers own
//! distinct Summary values; children and published index columns stay borrowed.
//! No locks, copied support sets or per-instance consumer lists are introduced.
use super::*;
use crate::query::snapshot::TableRead;
use rayon::prelude::*;
use std::time::Instant;

#[derive(Default, serde::Serialize)]
struct Work {
    enabled:bool, attempts:u64, batches:u64, small_batches:u64, unavailable_calls:u64,
    levels:u64, pool_calls:u64, tasks:u64, inline_tasks:u64,
    borrowed_rows:u64, group_headers:u64, prepared_columns:u64,
    direct_rows:u64, dependency_rows:u64, candidate_visits:u64, added_keys:u64,
    task_capacity_bytes:u64, row_header_capacity_bytes:u64, peak_scratch_bytes:u64,
    prepare_seconds:f64, execute_seconds:f64, restore_seconds:f64,
    worker_tasks:Vec<u64>, worker_rows:Vec<u64>, worker_seconds:Vec<f64>,
}
#[derive(Default)]
pub(super) struct State {
    // Scheduling addresses derived from the existing Spec guards/influences.
    compiled:bool,
    depth:Vec<usize>, group:Vec<usize>, table_groups:Vec<usize>,
    inputs:Vec<Vec<usize>>, outputs:Vec<Vec<Projection>>,
    pending:Vec<Vec<usize>>, active:Vec<bool>, touched_groups:Vec<usize>,
    touched_outputs:Vec<usize>, work:Work,
}
impl State {
    pub fn compile(specs:&[Spec], tables:&[Dispatch])->Self {
        let mut s=Self {compiled:true,..Self::default()};
        // Interning creates children first. Unknown/reconfigured graphs keep
        // the original queue instead of claiming an unproved execution layer.
        for (id,spec) in specs.iter().enumerate() {
            if spec.guards.iter().any(|g|g.child>=id) {return Self {compiled:true,..Self::default()};}
            s.depth.push(spec.guards.iter().map(|g|s.depth[g.child]+1).max().unwrap_or(0));
        }
        s.pending=(0..s.depth.iter().max().map_or(0,|d|d+1)).map(|_|Vec::new()).collect();
        s.group=vec![0;specs.len()];
        for table in tables {
            s.table_groups.push(s.inputs.len());
            for group in &table.groups {
                for &id in &table.members[group.members.clone()] {s.group[id]=s.inputs.len();}
                s.inputs.push(Vec::new());
            }
        }
        s.active=vec![false;specs.len()];
        s.outputs=(0..specs.len()).map(|_|Vec::new()).collect();
        s
    }
    fn schedule(&mut self,id:usize) {
        if !self.active[id] {self.active[id]=true;self.pending[self.depth[id]].push(id);}
    }
    fn scratch_bytes(&self)->usize {
        self.inputs.iter().map(|v|v.capacity()*std::mem::size_of::<usize>()).sum::<usize>()
        + self.outputs.iter().map(|v|v.capacity()*std::mem::size_of::<Projection>()).sum::<usize>()
        + self.pending.iter().map(|v|v.capacity()*std::mem::size_of::<usize>()).sum::<usize>()
        + (self.touched_groups.capacity()+self.touched_outputs.capacity())*std::mem::size_of::<usize>()
    }
    pub fn report(&self)->serde_json::Value {
        serde_json::json!({"organization":"cell-condition-layers/v1", "compiled":self.compiled, "levels":self.pending.len(),
            "plan_payload_bytes":(self.depth.capacity()+self.group.capacity()+self.table_groups.capacity())*std::mem::size_of::<usize>()
                + self.active.capacity()*std::mem::size_of::<bool>()
                + (self.inputs.capacity()+self.pending.capacity())*std::mem::size_of::<Vec<usize>>()
                + self.outputs.capacity()*std::mem::size_of::<Vec<Projection>>(),
            "scratch_capacity_bytes":self.scratch_bytes(),
            "pending_group_rows":self.inputs.iter().map(Vec::len).sum::<usize>(),
            "pending_support_keys":self.outputs.iter().map(Vec::len).sum::<usize>(),
            "pending_tasks":self.pending.iter().map(Vec::len).sum::<usize>(),"stats":self.work})
    }
}
struct Task<'a> {
    id:usize, spec:&'a Spec, state:Summary, added:Vec<Projection>,
    direct:&'a [usize], read:Option<TableRead<'a>>, estimate:usize,
    dependency_rows:u64, candidate_visits:u64, worker:Option<usize>, seconds:f64,
}
impl Task<'_> {
    fn admit(&mut self,keys:&[u64],states:&[Summary],collide:bool) {
        if self.spec.guards.iter().all(|g|states[g.child].allows(keys,&g.cols)) {
            if let Some(k)=self.state.insert::<false>(self.spec,keys,collide) {self.added.push(k);}
        }
    }
    fn run(&mut self,rows:&[&[u64]],states:&[Summary],outputs:&[Vec<Projection>],collide:bool,pooled:bool) {
        self.worker=pooled.then(rayon::current_thread_index).flatten();
        let clock=Instant::now();
        for &position in self.direct {self.admit(rows[position],states,collide);}
        // These are the same static parent/guard links as queue propagation.
        // Columns are finished on the coordinator; workers borrow membership
        // directly, removing hash_candidates' temporary witness vectors.
        let read=self.read.take();
        if let Some(read)=&read {
            for guard in &self.spec.guards {
                if guard.cols.is_empty() {continue;}
                for key in &outputs[guard.child] {
                    let domain=read.domain(guard.cols.iter().copied().zip(key.iter().copied()).collect());
                    for witness in domain.iter() {
                        self.dependency_rows+=1;
                        self.admit(read.hashes(witness),states,collide);
                    }
                    self.candidate_visits+=domain.take_examined();
                }
            }
        }
        self.read=read;
        self.seconds=clock.elapsed().as_secs_f64();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::value::Value;

    #[test]
    fn layered_publication_matches_queue_with_late_children_field_masks_and_collisions() {
        fn fixture(g:&Graph,index:&mut QueryIndexes,collide:bool)->Sieve {
            let mut s=Sieve::new(&g.program);
            s.specs=vec![
                Spec::new(1,vec![0],vec![]),
                Spec::new(0,vec![0],vec![Guard {cols:vec![1],child:0}]),
                Spec::new(0,vec![2],vec![Guard {cols:vec![0],child:1}]),
                Spec::new(0,vec![],vec![]),
                Spec::new(1,vec![0,1],vec![]),
                Spec::new(0,vec![0,1,2],vec![Guard {cols:vec![1],child:0}]),
                Spec::new(1,vec![2],vec![Guard {cols:vec![0],child:1}]),
                Spec::new(0,vec![2],vec![Guard {cols:vec![0],child:6}]),
                Spec::new(1,vec![2],vec![Guard {cols:vec![0,1,2],child:5}]),
            ];
            s.states=(0..s.specs.len()).map(|_|Summary::default()).collect();
            s.parents=vec![vec![];s.specs.len()];
            for (parent,spec) in s.specs.iter().enumerate() {
                for (gid,g) in spec.guards.iter().enumerate() {s.parents[g.child].push((parent,gid));}
            }
            s.collide=collide;s.compile_influence();
            assert!(!s.publication.compiled);
            for id in 0..8 {s.ensure(id,g,index).unwrap();}
            s
        }
        let pool=rayon::ThreadPoolBuilder::new().num_threads(4).build().unwrap();
        for (bits,collide) in [(64,false),(0,false),(64,true)] {
            let mut graph=crate::query::test_projection_graph();
            let mut a=crate::query::test_projection_indexes(bits);a.track_changes=true;
            let mut b=crate::query::test_projection_indexes(bits);b.track_changes=true;
            let mut serial=fixture(&graph,&mut a,collide);
            let mut staged=fixture(&graph,&mut b,collide);
            for stage in 0..5 {
                for i in 0..512 {
                    let (table,key,value)=match stage {
                        0=>(0,vec![Value::Int(i),Value::Int(i+1000)],Value::Int(i+2000)),
                        1=>(1,vec![Value::Int(i+1000),Value::Int(i)],Value::Int(i)),
                        2=>(0,vec![Value::Int(i),Value::Int(i+1000)],Value::Int(i+3000)),
                        3=>(1,vec![Value::Int(i),Value::Int(i+1000)],Value::Int(i+3000)),
                        _=>(0,vec![Value::Int(i+512),Value::Int(i)],Value::Int(i+4000)),
                    };
                    graph.set_function(table,key,value).unwrap();
                }
                a.update(&mut graph).unwrap();b.update(&mut graph).unwrap();
                if stage==3 {serial.ensure(8,&graph,&mut a).unwrap();staged.ensure(8,&graph,&mut b).unwrap();}
                serial.publish(&mut a);
                if !staged.publish_staged(&mut b,Some(&pool),16) {staged.publish(&mut b);}
                for (x,y) in serial.states.iter().zip(&staged.states) {
                    let keys=|s:&Summary| {let mut k=s.keys.iter().map(<[u64]>::to_vec).collect::<Vec<_>>();k.sort();k};
                    assert_eq!(keys(x),keys(y),"stage {stage}, bits {bits}, Bloom collisions {collide}");
                    assert_eq!(x.built,y.built);
                }
                assert!(staged.publication.inputs.iter().all(Vec::is_empty));
                assert!(staged.publication.outputs.iter().all(Vec::is_empty));
                assert!(staged.publication.pending.iter().all(Vec::is_empty));
                assert!(staged.publication.active.iter().all(|a|!*a));
                graph.changes.clear();
            }
            assert!(staged.publication.work.pool_calls>0);
            assert!(staged.publication.work.worker_rows.iter().sum::<u64>()>0);
            assert_eq!(serial.stats.added_keys,staged.stats.added_keys);
            assert_eq!(serial.stats.update_rows,staged.stats.update_rows);
            assert_eq!(serial.stats.column_checks,staged.stats.column_checks);
            assert_eq!(serial.stats.unchanged_column_rows,staged.stats.unchanged_column_rows);
            if bits!=0 {assert!(staged.publication.work.dependency_rows>0);}
            staged.invalidate();
            for id in 0..staged.states.len() {staged.ensure(id,&graph,&mut b).unwrap();}
            assert!(staged.states.iter().all(|s|s.built));
        }
    }
}
impl Sieve {
    pub(crate) fn publish_staged(&mut self,index:&mut QueryIndexes,pool:Option<&rayon::ThreadPool>,grain:usize)->bool {
        self.publication.work.enabled=true;
        self.publication.work.attempts+=1;
        if !self.enabled {
            self.publication.work.unavailable_calls+=1;
            return false;
        }
        if index.changes.len()<grain.max(256) {
            self.publication.work.small_batches+=1;
            return false;
        }
        let clock=Instant::now();
        // Short executions and disabled publication never allocate a plan.
        // The first large batch charges its one-time preparation here.
        if !self.publication.compiled {
            let work=std::mem::take(&mut self.publication.work);
            self.publication=State::compile(&self.specs,&self.by_table);
            self.publication.work=work;
        }
        if self.publication.depth.len()!=self.specs.len() {
            self.publication.work.unavailable_calls+=1;
            return false;
        }
        let mut changes=std::mem::take(&mut index.changes);
        changes.sort_unstable();
        let plan=&mut self.publication;
        let mut rows=Vec::new();
        for &(w,table,fields) in &changes {
            self.stats.publication_dispatches+=1;
            let dispatch=&self.by_table[table];
            if dispatch.built==0 {self.stats.inactive_publications+=1;continue;}
            let Some(keys)=index.hashes(table,w) else {continue};
            let position=rows.len();rows.push(keys);
            for (offset,group) in dispatch.groups.iter().enumerate() {
                if group.built==0 {continue;}
                if fields!=u64::MAX {
                    self.stats.column_checks+=1;
                    if fields&group.columns==0 {self.stats.unchanged_column_rows+=group.built as u64;continue;}
                }
                let group_id=plan.table_groups[table]+offset;
                if plan.inputs[group_id].is_empty() {
                    plan.touched_groups.push(group_id);
                    for &id in &dispatch.members[group.members.clone()] {
                        if self.states[id].built {plan.schedule(id);}
                    }
                }
                plan.inputs[group_id].push(position);
                plan.work.group_headers+=1;
            }
        }
        plan.work.batches+=1;
        plan.work.borrowed_rows+=rows.len() as u64;
        plan.work.row_header_capacity_bytes+=(rows.capacity()*std::mem::size_of::<&[u64]>()) as u64;
        plan.work.prepare_seconds+=clock.elapsed().as_secs_f64();
        let workers=pool.map_or(1,rayon::ThreadPool::current_num_threads);
        plan.work.worker_tasks.resize(workers,0);plan.work.worker_rows.resize(workers,0);plan.work.worker_seconds.resize(workers,0.0);
        for level in 0..plan.pending.len() {
            if plan.pending[level].is_empty() {continue;}
            let clock=Instant::now();
            let mut ids=std::mem::take(&mut plan.pending[level]);
            let mut tasks=Vec::with_capacity(ids.len());
            for &id in &ids {
                let spec=&self.specs[id];
                let direct=&plan.inputs[plan.group[id]];
                let mut columns=smallvec::SmallVec::<[usize;4]>::new();
                let mut estimate=direct.len();
                for guard in &spec.guards {
                    let added=&plan.outputs[guard.child];
                    estimate+=added.len();
                    if !added.is_empty() {columns.extend(guard.cols.iter().copied());}
                }
                columns.sort_unstable();columns.dedup();
                plan.work.prepared_columns+=columns.len() as u64;
                let read=(!columns.is_empty()).then(||index.publication_support(spec.table,&columns));
                tasks.push(Task {id,spec,state:std::mem::take(&mut self.states[id]),
                    added:std::mem::take(&mut plan.outputs[id]),direct,read,estimate,
                    dependency_rows:0,candidate_visits:0,worker:None,seconds:0.0});
            }
            plan.work.prepare_seconds+=clock.elapsed().as_secs_f64();
            let pooled=pool.is_some() && tasks.len()>1
                && tasks.iter().map(|t|t.estimate).sum::<usize>()>=grain.saturating_mul(workers).max(256);
            let clock=Instant::now();
            let run=|task:&mut Task<'_>|task.run(&rows,&self.states,&plan.outputs,self.collide,pooled);
            if pooled {pool.unwrap().install(||tasks.par_iter_mut().for_each(run));}
            else {tasks.iter_mut().for_each(run);}
            plan.work.execute_seconds+=clock.elapsed().as_secs_f64();
            plan.work.pool_calls+=u64::from(pooled);plan.work.levels+=1;
            plan.work.task_capacity_bytes+=(tasks.capacity()*std::mem::size_of::<Task<'_>>()) as u64;
            let clock=Instant::now();
            // End all borrows of group inputs before scheduling any parent.
            for task in tasks {
                let added=task.added.len() as u64;
                let direct=task.direct.len() as u64;
                self.stats.update_rows+=direct;self.stats.dependency_rows+=task.dependency_rows;self.stats.added_keys+=added;
                plan.work.tasks+=1;plan.work.direct_rows+=direct;plan.work.dependency_rows+=task.dependency_rows;
                plan.work.candidate_visits+=task.candidate_visits;plan.work.added_keys+=added;
                if let Some(worker)=task.worker {
                    plan.work.worker_tasks[worker]+=1;plan.work.worker_rows[worker]+=direct+task.dependency_rows;
                    plan.work.worker_seconds[worker]+=task.seconds;
                } else {plan.work.inline_tasks+=1;}
                self.states[task.id]=task.state;plan.outputs[task.id]=task.added;plan.active[task.id]=false;
            }
            for &id in &ids {
                if plan.outputs[id].is_empty() {continue;}
                plan.touched_outputs.push(id);
                for &(parent,_) in &self.parents[id] {if self.states[parent].built {plan.schedule(parent);}}
            }
            ids.clear();plan.pending[level]=ids;
            plan.work.restore_seconds+=clock.elapsed().as_secs_f64();
        }
        plan.work.peak_scratch_bytes=plan.work.peak_scratch_bytes.max(plan.scratch_bytes() as u64);
        for id in plan.touched_outputs.drain(..) {plan.outputs[id].clear();}
        for group in plan.touched_groups.drain(..) {plan.inputs[group].clear();}
        changes.clear();index.changes=changes;
        true
    }
}
