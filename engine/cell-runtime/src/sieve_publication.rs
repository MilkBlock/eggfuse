//! Complete the existing condition DAG from child completion events. Each node
//! owns its original Summary; static guard links release only dependent nodes.
//! A Run joins once before making its updated query conditions visible.
use super::*;
use crate::query::snapshot::TableRead;
use std::sync::{Mutex, OnceLock, atomic::{AtomicUsize, Ordering}};
use std::time::Instant;
#[path = "sieve_table_events.rs"]
mod table_events;

#[derive(Default, serde::Serialize)]
struct Work {
    enabled:bool, attempts:u64, batches:u64, small_batches:u64, unavailable_calls:u64,
    pool_calls:u64, tasks:u64, inline_tasks:u64,
    event_nodes:u64, event_edges:u64, event_empty_nodes:u64, event_header_bytes:u64, event_inline_empty:u64,
    borrowed_rows:u64, group_headers:u64, prepared_columns:u64,
    direct_rows:u64, dependency_rows:u64, candidate_visits:u64, added_keys:u64,
    task_capacity_bytes:u64, row_header_capacity_bytes:u64, peak_scratch_bytes:u64,
    prepare_seconds:f64, execute_seconds:f64, restore_seconds:f64,
    worker_tasks:Vec<u64>, worker_rows:Vec<u64>, worker_seconds:Vec<f64>,
    table_events:table_events::Work,
}
#[derive(Default)]
pub(super) struct State {
    // Scheduling addresses derived from the existing Spec guards/influences.
    compiled:bool,
    valid:bool, group:Vec<usize>, table_groups:Vec<usize>,
    inputs:Vec<Vec<usize>>, pending:Vec<usize>, active:Vec<bool>,
    touched_groups:Vec<usize>, work:Work,
}
impl State {
    pub fn compile(specs:&[Spec], tables:&[Dispatch])->Self {
        let mut s=Self {compiled:true,..Self::default()};
        // Interning creates children first. Unknown/reconfigured graphs keep
        // the original queue instead of claiming an unproved execution layer.
        for (id,spec) in specs.iter().enumerate() {
            // Guards come from nonempty shared columns of connected Cell
            // atoms. A synthetic disconnected edge has no indexed wakeup
            // proof and must retain the ordinary path.
            if spec.guards.iter().any(|g|g.child>=id || g.cols.is_empty()) {return Self {compiled:true,..Self::default()};}
        }
        s.valid=true;
        s.group=vec![0;specs.len()];
        for table in tables {
            s.table_groups.push(s.inputs.len());
            for group in &table.groups {
                for &id in &table.members[group.members.clone()] {s.group[id]=s.inputs.len();}
                s.inputs.push(Vec::new());
            }
        }
        s.active=vec![false;specs.len()];
        s
    }
    fn schedule(&mut self,id:usize) {
        if !self.active[id] {self.active[id]=true;self.pending.push(id);}
    }
    fn scratch_bytes(&self)->usize {
        self.inputs.iter().map(|v|v.capacity()*std::mem::size_of::<usize>()).sum::<usize>()
        + (self.pending.capacity()+self.touched_groups.capacity())*std::mem::size_of::<usize>()
    }
    pub fn report(&self)->serde_json::Value {
        serde_json::json!({"organization":"cell-table-condition-events/v3", "compiled":self.compiled, "valid":self.valid,
            "execute_seconds_scope":"includes overlapped table publication in fused batches; do not add to publication.parallel.execute_seconds",
            "early_nodes_scope":"condition completed before all changed index owners were ready; excludes independent Entry work; not worker utilization",
            "plan_payload_bytes":(self.group.capacity()+self.table_groups.capacity())*std::mem::size_of::<usize>()
                + self.active.capacity()*std::mem::size_of::<bool>()
                + self.inputs.capacity()*std::mem::size_of::<Vec<usize>>(),
            "scratch_capacity_bytes":self.scratch_bytes(),
            "pending_group_rows":self.inputs.iter().map(Vec::len).sum::<usize>(),
            "pending_support_keys":0, // retired layer output scratch
            "pending_tasks":self.pending.len(),"stats":self.work})
    }
}
struct Task<'a> {
    id:usize, spec:&'a Spec, state:Summary, added:Vec<Projection>,
    direct:&'a [usize], read:Option<TableRead<'a>>,
    dependency_rows:u64, candidate_visits:u64, worker:Option<usize>, seconds:f64,
}
impl Task<'_> {
    fn run<'a>(&mut self, rows:&[&[u64]], child:impl Fn(usize)->(&'a Summary,&'a [Projection]), collide:bool, pooled:bool) {
        self.worker=pooled.then(rayon::current_thread_index).flatten();
        let clock=Instant::now();
        let (dependency_rows,candidate_visits)=complete_condition(
            self.spec,&mut self.state,&mut self.added,self.direct.iter().map(|&p|rows[p]),
            self.read.as_ref(),child,collide);
        self.dependency_rows+=dependency_rows;self.candidate_visits+=candidate_visits;
        self.seconds=clock.elapsed().as_secs_f64();
    }
}

// Both table-ready and already-published paths execute the same condition.
fn complete_condition<'a,'b>(spec:&Spec,state:&mut Summary,added:&mut Vec<Projection>,
    direct:impl Iterator<Item=&'b [u64]>,read:Option<&TableRead<'_>>,
    child:impl Fn(usize)->(&'a Summary,&'a [Projection]),collide:bool)->(u64,u64) {
        let (mut dependency_rows,mut candidate_visits)=(0,0);
        let mut admit=|keys:&[u64]| {
            if spec.guards.iter().all(|g| child(g.child).0.allows(keys,&g.cols)) {
                // Multiple child routes may produce the same candidate. The
                // original exact support insertion adopts it only once.
                if let Some(key)=state.insert::<false>(spec,keys,collide) {added.push(key);}
            }
        };
        for keys in direct {admit(keys);}
        if let Some(read)=read {
            for guard in &spec.guards {
                if guard.cols.is_empty() {continue;}
                for key in child(guard.child).1 {
                    let domain=read.domain(guard.cols.iter().copied().zip(key.iter().copied()).collect());
                    for witness in domain.iter() {dependency_rows+=1;admit(read.hashes(witness));}
                    candidate_visits+=domain.take_examined();
                }
            }
        }
        (dependency_rows,candidate_visits)
}

struct Events<'a,'b> {
    tasks:&'a [Mutex<Option<Task<'b>>>], finished:&'a [OnceLock<Task<'b>>],
    remaining:&'a [AtomicUsize], positions:&'a [usize], parents:&'a [Vec<(usize,usize)>],
    states:&'a [Summary], rows:&'a [&'b [u64]], collide:bool, inline_empty:AtomicUsize,
    #[cfg(test)] before:Option<&'a (dyn Fn(usize)+Sync)>,
}
impl<'a,'b> Events<'a,'b> {
    fn complete<'scope>(&'scope self,position:usize,scope:Option<&rayon::Scope<'scope>>)
        where 'a:'scope, 'b:'scope {
        let mut task=self.tasks[position].lock().unwrap().take().expect("one condition owner");
        #[cfg(test)] if let Some(before)=self.before {before(task.id);}
        task.run(self.rows,|child| {
            let position=self.positions[child];
            if position==usize::MAX {(&self.states[child],&[])}
            else {let task=self.finished[position].get().expect("ready child");(&task.state,task.added.as_slice())}
        },self.collide,scope.is_some());
        let id=task.id;
        assert!(self.finished[position].set(task).is_ok());
        for &(parent,_) in &self.parents[id] {
            let next=self.positions[parent];
            if next!=usize::MAX && self.remaining[next].fetch_sub(1,Ordering::AcqRel)==1 {
                let has_work={
                    let next_task=self.tasks[next].lock().unwrap();let next_task=next_task.as_ref().unwrap();
                    !next_task.direct.is_empty() || next_task.spec.guards.iter().any(|g| {
                        let position=self.positions[g.child];
                        !g.cols.is_empty() && position!=usize::MAX && !self.finished[position].get().unwrap().added.is_empty()
                    })
                };
                if let Some(scope)=scope.filter(|_|has_work) {scope.spawn(move |scope|self.complete(next,Some(scope)));}
                else {
                    if !has_work {self.inline_empty.fetch_add(1,Ordering::Relaxed);}
                    self.complete(next,scope);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::value::Value;

    #[test]
    fn a_child_completion_releases_parent_before_unrelated_root() {
        use std::{sync::mpsc, time::Duration};
        let specs=[Spec::new(0,vec![0],vec![]),Spec::new(0,vec![0],vec![]),
            Spec::new(0,vec![0],vec![Guard {cols:vec![0],child:0}])];
        let tasks:Vec<_>=specs.iter().enumerate().map(|(id,spec)|Mutex::new(Some(Task {
            id,spec,state:Summary::default(),added:vec![],direct:&[],read:None,
            dependency_rows:0,candidate_visits:0,worker:None,seconds:0.0,
        }))).collect();
        let finished:Vec<_>=(0..3).map(|_|OnceLock::new()).collect();
        let (tx,rx)=mpsc::channel();let rx=Mutex::new(rx);
        let before=|id| {
            if id==1 {rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();}
            if id==2 {tx.send(()).unwrap();}
        };
        let remaining=[AtomicUsize::new(0),AtomicUsize::new(0),AtomicUsize::new(1)];
        let parents=[vec![(2,0)],vec![],vec![]];
        let states:Vec<_>=(0..3).map(|_|Summary::default()).collect();
        let events=Events {tasks:&tasks,finished:&finished,remaining:&remaining,positions:&[0,1,2],
            parents:&parents,states:&states,rows:&[],collide:false,inline_empty:AtomicUsize::new(0),before:Some(&before)};
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        pool.scope(|scope| {
            let events=&events;
            scope.spawn(move |scope|events.complete(0,Some(scope)));
            scope.spawn(move |scope|events.complete(1,Some(scope)));
        });
        assert!(finished.iter().all(|s|s.get().is_some()));
    }

    #[test]
    fn event_publication_matches_queue_with_late_children_field_masks_and_collisions() {
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
                assert!(staged.publication.pending.is_empty());
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
        if !self.publication.valid {
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
        let workers=pool.map_or(1,rayon::ThreadPool::current_num_threads).max(plan.work.worker_tasks.len());
        plan.work.worker_tasks.resize(workers,0);plan.work.worker_rows.resize(workers,0);plan.work.worker_seconds.resize(workers,0.0);
        let clock=Instant::now();
        let mut ids:Vec<_>=plan.pending.drain(..).collect();
        // Determine only the potentially affected closure. These are the
        // existing compiled parent links, never producer subscriptions.
        let mut head=0;
        while head<ids.len() {
            for &(parent,_) in &self.parents[ids[head]] {
                if self.states[parent].built && !plan.active[parent] {
                    plan.active[parent]=true;ids.push(parent);
                }
            }
            head+=1;
        }
        let mut positions=vec![usize::MAX;self.specs.len()];
        for (position,&id) in ids.iter().enumerate() {positions[id]=position;}
        let mut tasks=Vec::with_capacity(ids.len());
        let mut roots=Vec::new();
        let mut remaining=Vec::with_capacity(ids.len());
        for (position,&id) in ids.iter().enumerate() {
            let spec=&self.specs[id];
            let direct=&plan.inputs[plan.group[id]];
            let mut columns=smallvec::SmallVec::<[usize;4]>::new();
            let mut dependencies=0;
            for guard in &spec.guards {
                if positions[guard.child]!=usize::MAX {
                    dependencies+=1;columns.extend(guard.cols.iter().copied());
                }
            }
            plan.work.event_edges+=dependencies as u64;
            if dependencies==0 {roots.push(position);}
            remaining.push(AtomicUsize::new(dependencies));
            columns.sort_unstable();columns.dedup();
            plan.work.prepared_columns+=columns.len() as u64;
            let read=(!columns.is_empty()).then(||index.publication_support(spec.table,&columns));
            tasks.push(Mutex::new(Some(Task {id,spec,state:std::mem::take(&mut self.states[id]),
                added:Vec::new(),direct,read,
                dependency_rows:0,candidate_visits:0,worker:None,seconds:0.0})));
        }
        let finished:Vec<OnceLock<Task<'_>>>=(0..ids.len()).map(|_|OnceLock::new()).collect();
        let pooled=pool.is_some() && ids.len()>1 && rows.len()>=grain.saturating_mul(workers).max(256);
        let events=Events {tasks:&tasks,finished:&finished,remaining:&remaining,positions:&positions,
            parents:&self.parents,states:&self.states,rows:&rows,collide:self.collide,inline_empty:AtomicUsize::new(0),
            #[cfg(test)] before:None};
        plan.work.event_nodes+=ids.len() as u64;
        plan.work.event_header_bytes+=(tasks.capacity()*std::mem::size_of::<Mutex<Option<Task<'_>>>>()
            + finished.capacity()*std::mem::size_of::<OnceLock<Task<'_>>>()
            + remaining.capacity()*std::mem::size_of::<AtomicUsize>()
            + (ids.capacity()+positions.capacity()+roots.capacity())*std::mem::size_of::<usize>()) as u64;
        plan.work.prepare_seconds+=clock.elapsed().as_secs_f64();
        let clock=Instant::now();
        if pooled {
            pool.unwrap().scope(|scope| {
                let events=&events;
                for &root in &roots {scope.spawn(move |scope|events.complete(root,Some(scope)));}
            });
        } else { for root in roots {events.complete(root,None);} }
        plan.work.pool_calls+=u64::from(pooled);
        plan.work.execute_seconds+=clock.elapsed().as_secs_f64();
        let clock=Instant::now();
        plan.work.event_inline_empty+=events.inline_empty.load(Ordering::Relaxed) as u64;
        drop(events);drop(tasks);
        for (position,result) in finished.into_iter().enumerate() {
            let task=result.into_inner().expect("every affected condition completed");
            let direct=task.direct.len() as u64;
            self.stats.update_rows+=direct;self.stats.dependency_rows+=task.dependency_rows;
            self.stats.added_keys+=task.added.len() as u64;
            plan.work.tasks+=1;plan.work.direct_rows+=direct;plan.work.dependency_rows+=task.dependency_rows;
            plan.work.candidate_visits+=task.candidate_visits;plan.work.added_keys+=task.added.len() as u64;
            plan.work.event_empty_nodes+=u64::from(direct==0 && task.dependency_rows==0);
            if let Some(worker)=task.worker {
                plan.work.worker_tasks[worker]+=1;plan.work.worker_rows[worker]+=direct+task.dependency_rows;
                plan.work.worker_seconds[worker]+=task.seconds;
            } else {plan.work.inline_tasks+=1;}
            self.states[task.id]=task.state;plan.active[ids[position]]=false;
        }
        plan.work.restore_seconds+=clock.elapsed().as_secs_f64();
        plan.work.peak_scratch_bytes=plan.work.peak_scratch_bytes.max(plan.scratch_bytes() as u64);
        for group in plan.touched_groups.drain(..) {plan.inputs[group].clear();}
        changes.clear();index.changes=changes;
        true
    }
}
