//! Completion events return the actual registration owners. A source Cell
//! waits for its own Unit decisions, Cell frame and slot reservation. Shared
//! directories and subscriptions return before the Run fence, not per Cell.
use super::*;

struct Item {cell:usize,row:usize,source:usize,fields:RowFields}
struct NewRow {index:usize,fields:RowFields}
pub(crate) struct Owner {
    table:usize,keys:scalar_keys::FunctionKeys,members:TableRows<u64>,version:u64,
    changes:rustc_hash::FxHashMap<Dependency,crate::change_batch::Change>,added:Vec<NewRow>,subscribed:bool,
}
pub(crate) struct TableJob {owner:Owner,items:Vec<Item>,start:usize,deferred:bool}
pub(crate) struct Structure {
    functions:Vec<Function>,decoded:Vec<Option<RowFields>>,end:usize,first_table:usize,
    constructors:Option<constructor_registration::Owned>,growth:usize,
}
pub(crate) enum RegistrationTask {Table(TableJob),Structure(Box<Structure>),Subscriptions(Box<constructor_registration::Subscriptions>),UnitSubscriptions(Box<constructor_registration::Subscriptions>,Vec<Owner>)}
pub(crate) struct Decision {cell:usize,row:usize,value:(usize,bool,bool,bool)}
pub(crate) enum RegistrationEvent {
    Decisions(Vec<Decision>),Table(Owner),Structure(Box<Structure>,bool),
    Cells(Vec<constructor_registration::CellReady>),Constructors(constructor_registration::Owned),
    Subscriptions(Box<constructor_registration::Subscriptions>),
    UnitSubscriptions(Box<constructor_registration::Subscriptions>,Vec<Owner>,u64),
}
impl RegistrationEvent {
    pub(crate) fn completes_owner(&self)->bool { !matches!(self,Self::Decisions(_)|Self::Cells(_)|Self::Structure(_,false)) }
}
impl RegistrationTask {
    pub(crate) fn run(self,emit:&(dyn Fn(RegistrationEvent)+Sync)) {
        match self {
            Self::Table(mut job)=> {
                let owner=&mut job.owner;let mut decisions=Vec::with_capacity(job.items.len().min(32));
                let mut items=job.items.into_iter();
                while let Some(item)=items.next() {
                    let key=&item.fields[..item.fields.len()-1];
                    let found=owner.keys.get(key).copied();
                    let (index,new)=found.map_or((job.start+item.source,true),|index|(index,false));
                    let activate=new && owner.changes.is_empty();
                    if new {
                        owner.keys.insert(key,index);owner.members.insert(index as u64);owner.version+=1;
                        assert!(owner.changes.insert(Dependency::Function(index),crate::change_batch::Change::Wake).is_none());
                        owner.added.push(NewRow {index,fields:item.fields});
                    }
                    decisions.push(Decision {cell:item.cell,row:item.row,value:(index,new,activate,job.deferred)});
                    if decisions.len()==32 || items.len()==0 {
                        emit(RegistrationEvent::Decisions(decisions));
                        decisions=Vec::with_capacity(items.len().min(32));
                    }
                }
                emit(RegistrationEvent::Table(job.owner));
            }
            Self::Structure(mut state)=> {
                let before=(state.functions.capacity(),state.decoded.capacity());
                state.functions.resize_with(state.end,||Function {writer:None,
                    #[cfg(feature="receipt-slots")] port_slot:0,
                    table:state.first_table,key:Vec::new(),value:Value::Int(0),epoch:0,live:false,origin:None});
                state.decoded.resize_with(state.end,||None);
                state.growth=(state.functions.capacity()-before.0)*std::mem::size_of::<Function>()
                    +(state.decoded.capacity()-before.1)*std::mem::size_of::<Option<RowFields>>();
                let constructors=state.constructors.take();
                emit(RegistrationEvent::Structure(state,constructors.is_none()));
                if let Some(mut owner)=constructors {
                    owner.install(&|cells|emit(RegistrationEvent::Cells(cells)));
                    emit(RegistrationEvent::Constructors(owner));
                }
            }
            Self::Subscriptions(mut owner)=> {owner.install();emit(RegistrationEvent::Subscriptions(owner));}
            Self::UnitSubscriptions(mut owner,mut tables)=> {
                let mut rows=0;
                for table in &mut tables {
                    for row in &table.added {owner.unit(row.index,&row.fields);rows+=1;}
                    table.subscribed=true;
                }
                emit(RegistrationEvent::UnitSubscriptions(owner,tables,rows));
            }
        }
    }
    #[cfg(test)]
    fn table(&self)->Option<usize> {match self {Self::Table(j)=>Some(j.owner.table),_=>None}}
}
#[must_use="all table owners must return even when source adoption fails"]
pub(crate) struct Registration {owners:Vec<Owner>,start:usize,end:usize,
    constructors:Option<constructor_registration::Registration>}
impl Registration {
    pub(crate) fn take_births(&mut self,cell:u32)->Option<constructor_registration::Publication> {
        self.constructors.as_mut().map(|r|r.take(cell))
    }
}
pub(crate) struct PendingRegistration {
    pub tasks:Vec<RegistrationTask>,pub registration:Registration,
    structure_ready:bool,subscriptions_expected:bool,accepted:usize,
    subscriptions:Option<Box<constructor_registration::Subscriptions>>,waiting:Vec<Owner>,
    constructor_finished:bool,
}
impl PendingRegistration {
    /// Restore all returned owners even after a source error. The source error
    /// only closes adoption; unfinished private work still has to give back
    /// its original index so finish_unit_registration can invalidate its suffix.
    pub fn accept(&mut self,graph:&mut Graph,done:&mut [Completed],event:RegistrationEvent) {
        match event {
            RegistrationEvent::Subscriptions(owner)=> {assert!(self.subscriptions.replace(owner).is_none());}
            RegistrationEvent::UnitSubscriptions(owner,tables,rows)=> {
                assert!(self.subscriptions.replace(owner).is_none());
                self.registration.owners.extend(tables);
                graph.stats.unit_registry_worker_subscriptions+=rows;
            }
            RegistrationEvent::Cells(ready)=>self.registration.constructors.as_mut().unwrap().receive(graph,ready),
            RegistrationEvent::Constructors(owner)=> {owner.restore(graph);self.constructor_finished=true;}
            RegistrationEvent::Structure(state,_)=> {
                assert!(graph.functions.is_empty() && graph.function_decoded.is_empty());
                let Structure {functions,decoded,growth,..}=*state;
                graph.functions=functions;graph.function_decoded=decoded;
                graph.stats.unit_registry_capacity_growth_bytes+=growth as u64;
                self.structure_ready=true;
            }
            RegistrationEvent::Decisions(items)=> {
                graph.stats.unit_registry_decision_bytes+=(items.capacity()*std::mem::size_of::<Decision>()) as u64;
                graph.stats.unit_registry_decision_fragments+=1;
                for item in items {
                    let row=&mut done[item.cell-self.accepted].done.piece.units[item.row];
                    assert!(row.registered.replace(item.value).is_none());
                }
            }
            RegistrationEvent::Table(owner)=> {
                graph.stats.unit_registry_bytes+=(owner.added.capacity()*std::mem::size_of::<NewRow>()) as u64;
                if self.subscriptions_expected {
                    let before=self.waiting.capacity();self.waiting.push(owner);
                    graph.stats.unit_registry_subscription_queue_bytes+=((self.waiting.capacity()-before)*std::mem::size_of::<Owner>()) as u64;
                } else {self.registration.owners.push(owner);}
            }
        }
    }
    pub fn ready(&self,done:&[Completed])->usize {
        if !self.structure_ready {return 0;}
        let constructors=self.registration.constructors.as_ref().map_or(done.len(),|r|r.ready()-self.accepted);
        done.iter().take(constructors).take_while(|d|d.done.piece.units.iter().all(|r|r.registered.is_some())).count()
    }
    pub fn advance(&mut self,count:usize) {self.accepted+=count;}
    pub fn constructor_directories_pending(&self)->bool {!self.constructor_finished}
    pub fn dispatch(&mut self,graph:&mut Graph,tasks:&mut Vec<RegistrationTask>) {
        if !self.waiting.is_empty() && let Some(owner)=self.subscriptions.take() {
            graph.stats.unit_registry_subscription_tasks+=1;
            tasks.push(RegistrationTask::UnitSubscriptions(owner,std::mem::take(&mut self.waiting)));
        }
    }
    pub fn restore_subscriptions(&mut self,graph:&mut Graph) {
        assert!(self.waiting.is_empty() && self.constructor_finished);
        if self.subscriptions_expected {self.subscriptions.take().expect("all subscription owners must return").restore(graph);}
    }
}

impl Graph {
    /// The caller proves a complete terminal prefix: no intervening mutable
    /// reads, union, fallible suffix or other Function-producing operation.
    /// Until the structure event returns, only registration event handling may
    /// touch Graph. Later, source adoption uses only its exact ready prefix.
    pub(crate) fn prepare_unit_registration(&mut self,done:&mut [Completed])->Option<PendingRegistration> {
        if !self.pipelined_births_ready() {return None;}
        let mut count=0;let mut first_table=None;let mut multiple_tables=false;
        for row in done.iter().flat_map(|d|&d.done.piece.units) {
            let table=row.function.table;if self.units.owned[table] {return None;}
            count+=1;
            if let Some(first)=first_table {multiple_tables|=table!=first;}else{first_table=Some(table);}
        }
        if count<32 || !multiple_tables {return None;}
        let start=self.functions.len();
        let end=start.checked_add(count).filter(|&end|end<u32::MAX as usize)?;
        let birth_count=done.iter().map(|d|d.done.piece.rows.len()).sum::<usize>();
        let ordered=done.windows(2).all(|w|w[0].done.cell<w[1].done.cell);
        let births=birth_count!=0 && self.local_jobs_supported() && ordered && done.iter().enumerate().all(|(i,d)| {
            self.cells.get(&d.done.cell).is_some_and(|c|
                c.parent.is_none_or(|parent|done.binary_search_by_key(&parent.cell,|d|d.done.cell).map_or(true,|p|p<i))
                && d.done.piece.rows.iter().all(|r|
                r.operation>=c.completed_prefix && !c.facts.contains_key(&(r.operation as u32))
                && self.program.repair_ports.key_eq_columns[r.table].is_some()))
        });
        let mut tables=BTreeMap::<usize,Vec<Item>>::new();let mut source=0;
        for (cell,d) in done.iter().enumerate() {for (row,r) in d.done.piece.units.iter().enumerate() {
            tables.entry(r.function.table).or_default().push(Item {cell,row,source,fields:r.fields.clone()});source+=1;
        }}
        self.stats.unit_registry_bytes+=tables.values().map(|v|v.capacity()*std::mem::size_of::<Item>()).sum::<usize>() as u64;
        let mut tasks:Vec<_>=tables.into_iter().map(|(table,items)|RegistrationTask::Table(TableJob {items,start,deferred:births,owner:Owner {
            table,keys:self.function_keys[table].take_owner(),members:self.members[table].take_owner(),
            version:self.query_versions[table],changes:self.changes.take_new_row_table(table),added:Vec::new(),subscribed:false,
        }})).collect();
        let table_count=tasks.len();
        let mut constructor_registration=None;
        let constructors=births.then(|| {
            let (rows,subscriptions,registration)=constructor_registration::Owned::take(self,done);
            constructor_registration=Some(registration);
            self.stats.constructor_registry_rows+=birth_count as u64;
            self.stats.constructor_registry_worker_rows+=if crate::sync_diagnostics::registry_inline() {0}else{birth_count as u64};
            self.stats.constructor_registry_batches+=1;
            tasks.insert(0,RegistrationTask::Subscriptions(Box::new(subscriptions)));rows
        });
        tasks.push(RegistrationTask::Structure(Box::new(Structure {
            functions:std::mem::take(&mut self.functions),decoded:std::mem::take(&mut self.function_decoded),
            end,first_table:first_table.unwrap(),constructors,growth:0,
        })));
        // The structure owner gates every Cell; submit it first. Table owners
        // still run independently and may return in any order.
        tasks.rotate_right(1);
        let owners=Vec::with_capacity(table_count);
        self.stats.unit_registry_batches+=1;self.stats.unit_registry_candidates+=count as u64;
        self.stats.unit_registry_bytes+=(tasks.capacity()*std::mem::size_of::<RegistrationTask>()
            +std::mem::size_of::<Structure>()+owners.capacity()*std::mem::size_of::<Owner>()) as u64;
        self.stats.unit_registry_field_handles+=count as u64;
        self.stats.unit_registry_pool_calls+=u64::from(!crate::sync_diagnostics::registry_inline());
        self.stats.unit_registry_identity_rows+=count as u64;
        self.stats.unit_registry_worker_identity_rows+=if crate::sync_diagnostics::registry_inline() {0}else{count as u64};
        self.stats.unit_registry_owner_tables+=table_count as u64;
        self.stats.unit_registry_reserved_slots+=count as u64;
        self.stats.unit_registry_reserved_bytes+=(count*(std::mem::size_of::<Function>()+std::mem::size_of::<Option<RowFields>>())) as u64;
        Some(PendingRegistration {tasks,registration:Registration {owners,start,end,constructors:constructor_registration},structure_ready:false,subscriptions_expected:births,accepted:0,subscriptions:None,waiting:Vec::new(),constructor_finished:!births})
    }

    #[cfg(test)]
    pub(crate) fn plan_unit_registration(&mut self,done:&mut [Completed],pool:&rayon::ThreadPool)->Option<Registration> {
        let mut pending=self.prepare_unit_registration(done)?;
        let tasks=std::mem::take(&mut pending.tasks);
        crate::completion_events::fragments_with_followups(tasks,(!crate::sync_diagnostics::registry_inline()).then_some(pool),RegistrationTask::run,
            |ready,tasks| {for event in ready.drain(..) {pending.accept(self,done,event);}pending.dispatch(self,tasks);});
        pending.restore_subscriptions(self);
        Some(pending.registration)
    }

    /// No second pool invocation, table regrouping, key hashing or insertion
    /// on success. Restore the actual prepared maps after rows exist. Failure
    /// removes only identities beyond the source-adopted prefix first.
    pub(crate) fn finish_unit_registration(&mut self,registration:Registration) {
        if let Some(constructors)=registration.constructors {constructors.finish(self);}
        assert_eq!(self.functions.len(),registration.end,"no intervening Function allocation");
        // Unused suffix slots never escaped as witnesses. Interior invalid
        // slots remain stable; live winners and their relative order never move.
        while self.functions.len()>registration.start && !self.functions.last().unwrap().live {
            self.functions.pop();self.function_decoded.pop();
            self.stats.unit_registry_trimmed_slots+=1;
        }
        let adopted=self.functions.len();
        assert!(registration.start<=adopted && adopted<=registration.end,"terminal Function prefix");
        let mut installed=0;
        for mut owner in registration.owners {
            let total=owner.added.len();
            let retained=owner.added.partition_point(|row|row.index<adopted);
            debug_assert!(owner.added[..retained].iter().all(|row|self.functions[row.index].live),
                "source adoption must be a prefix, not an arbitrary subset");
            installed+=retained;
            for row in &owner.added[retained..] {
                owner.keys.remove(&row.fields[..row.fields.len()-1]);
                assert!(owner.members.remove(&(row.index as u64)));
                assert!(owner.changes.remove(&Dependency::Function(row.index)).is_some());
                if owner.subscribed {self.replace_subscriptions(Dependency::Function(row.index),Default::default());}
            }
            assert_eq!(self.query_versions[owner.table],owner.version-total as u64,"no intervening table effects");
            self.function_keys[owner.table]=owner.keys;self.members[owner.table]=owner.members;
            self.query_versions[owner.table]=owner.version-(total-retained) as u64;
            self.changes.restore_new_row_table(owner.table,owner.changes);
            self.changes.finish_new_rows(owner.table,retained as u64);
            self.stats.unit_registry_tables+=u64::from(retained!=0);
            self.stats.unit_registry_installs+=retained as u64;
            self.stats.unit_registry_discarded+=(total-retained) as u64;
        }
        self.stats.unit_registry_retained_holes+=(adopted-registration.start-installed) as u64;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sync_diagnostics::registry_inline;
    fn graph(scalar:bool)->Graph {
        let mut g=crate::query::test_projection_graph();
        for table in 0..2 {
            let t=&mut g.program.tables[table];
            t.schema=vec![json!({"kind":"i64"});if scalar {1} else {2}];
            t.schema.push(json!({"kind":"Unit"}));
            t.merge=json!({"var":if table==0 {"old"} else {"new"}});
            g.function_keys[table]=scalar_keys::FunctionKeys::new(t);
        }
        g
    }
    fn key(n:usize,scalar:bool)->Vec<Value> {
        let mut key=vec![Value::Int(n as i64)];if !scalar {key.push(Value::Int(7));}key
    }
    fn completed(rows:Vec<units::Row>)->Completed {
        Completed {effects:Default::default(),done:Done {cell:0,worker:None,
            frame:Local {values:Default::default(),facts:Default::default(),completed_prefix:0},
            piece:Piece {end:0,rows:Default::default(),units:rows,aliases:0,counts:Default::default()}}}
    }
    fn constructor_units()->(Graph,Vec<Completed>) {
        use std::sync::Arc;
        let mut p=super::super::tests::graph().program;
        for i in 0..2 {
            let mut table=p.tables[0].clone();table.name=format!("unit-{i}");
            table.constructor=false;table.virtual_fact=false;table.schema[1]=json!({"kind":"Unit"});
            table.merge=json!({"var":if i==0 {"old"}else{"new"}});p.tables.push(table);p.table_templates.push(0);
            p.merge_programs.merges.insert(1+i,std::rc::Rc::new(crate::merge_programs::Merge {
                operations:vec![],result:Arg::Slot(i)}));
        }
        let mut ops=p.templates[0].ops.to_vec();
        ops.push(Op::Set(1,vec![Arg::Slot(4)],Arg::Literal(Value::Int(0))));
        ops.push(Op::Set(2,vec![Arg::Literal(Value::Eq(900))],Arg::Literal(Value::Int(0))));
        p.templates[0].ops=Arc::new(ops);p.known_results.static_skip[0]=std::rc::Rc::new(vec![false;6]);
        p.executions[0]=crate::cell::execution::Plan::derive(&p.tables,&p.templates[0],&[0]);
        p.executions[0].births=Plan::derive(&p,0).map(Arc::new);p.repair_ports=repair_ports::Plan::derive(&p);
        let mut g=Graph::new(p).unwrap();let mut done=Vec::new();
        for i in 0..64 {
            let cell=g.begin_transient(0,[(0,Value::Eq(100+i))].into_iter().collect(),None).unwrap();
            g.construct(cell,0,0,&[Arg::Slot(0)],1).unwrap();g.rhs_frame_mut(cell).unwrap().completed_prefix=1;
            let mut window=Window::seed(&g,cell,1);
            let (_,job)=g.take_local_job(0,cell,&mut window,6,true).unwrap();
            let mut effects=crate::cell::Effects::default();
            done.push(Completed {done:job.unwrap().run(g.parents.reader(),&mut effects.writer()),effects});
        }
        (g,done)
    }
    #[test]
    fn cell_completion_does_not_wait_for_constructor_directories_or_subscriptions() {
        use std::{sync::{Mutex,mpsc},time::Duration};
        let pool=rayon::ThreadPoolBuilder::new().num_threads(4).build().unwrap();
        for stop in [0,1,15,16,33,64] {
            let (mut g,mut done)=constructor_units();let (mut expected,reference)=constructor_units();
            let layout=|g:&Graph|g.cells.iter().map(|(id,c)|(*id,c as *const Cell as usize)).collect::<Vec<_>>();
            let before=layout(&g);
            let mut pending=g.prepare_unit_registration(&mut done).unwrap();
            assert!(pending.registration.constructors.is_some());
            assert_eq!(layout(&g),before);
            let tasks=std::mem::take(&mut pending.tasks);
            let (row_tx,row_rx)=mpsc::channel();let row_rx=Mutex::new(row_rx);
            let (sub_tx,sub_rx)=mpsc::channel();let sub_rx=Mutex::new(sub_rx);
            let mut adopted=0;let mut failed=false;let mut released=false;
            crate::completion_events::fragments_with_followups(tasks,Some(&pool),|task,emit| {
                if matches!(&task,RegistrationTask::Subscriptions(_)) {
                    sub_rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();
                }
                let first=std::sync::atomic::AtomicBool::new(true);
                task.run(&|event| {
                    let pause=matches!(&event,RegistrationEvent::Cells(_))
                        && first.swap(false,std::sync::atomic::Ordering::AcqRel);
                    emit(event);
                    if pause {row_rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();}
                });
            },|events,tasks| {
                for event in events.drain(..) {pending.accept(&mut g,&mut done,event);}
                pending.dispatch(&mut g,tasks);
                if !failed {
                    let n=pending.ready(&done);
                    if n!=0 {
                        pending.advance(n);
                        for mut d in done.drain(..n) {
                            if adopted==stop {failed=true;break;}
                            let publication=pending.registration.take_births(d.done.cell);
                            g.commit_registered_local_job(d.done,&mut d.effects.writer(),publication).unwrap();adopted+=1;
                        }
                        if !released {
                            assert_eq!(n,16);assert!(pending.constructor_directories_pending());
                            assert_eq!(layout(&g),before,"partial acceptance never relocates sibling instances");
                            assert!(g.members.is_empty() && g.uses.is_empty(),"source completion cannot borrow the leased directories");
                            row_tx.send(()).unwrap();sub_tx.send(()).unwrap();released=true;
                        }
                    }
                }
            });
            assert!(released);assert_eq!(adopted,stop);
            pending.restore_subscriptions(&mut g);g.finish_unit_registration(pending.registration);
            for mut d in reference.into_iter().take(stop) {expected.commit_local_job(d.done,&mut d.effects.writer()).unwrap();}
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            assert_eq!(g.query_versions,expected.query_versions);
            assert_eq!((g.changes.events,g.changes.distinct_events),(expected.changes.events,expected.changes.distinct_events));
            assert_eq!(g.maintenance.live_reverse_edges,expected.maintenance.live_reverse_edges);
            assert!(g.stats.unit_registry_worker_subscriptions>0);
            for graph in [&mut g,&mut expected] {graph.union(100,101).unwrap();graph.repair().unwrap();}
            assert_eq!(g.export().unwrap(),expected.export().unwrap(),"later repair sees only the adopted facts and Unit rows");
        }
    }
    #[test]
    fn source_cells_finish_before_their_table_owner_finishes_and_errors_restore_late_owners() {
        use std::{sync::{Mutex,mpsc,atomic::{AtomicBool,Ordering}},time::Duration};
        let pool=rayon::ThreadPoolBuilder::new().num_threads(4).build().unwrap();
        for stop in [0,1,31,32,63,64] {
            let mut g=graph(true);let mut expected=graph(true);
            let mut done:Vec<_>=(0..64).map(|cell|completed((0..2).map(|table|
                units::Row::prepared(table,key(cell%19,true))).collect())).collect();
            let mut pending=g.prepare_unit_registration(&mut done).unwrap();
            let tasks=std::mem::take(&mut pending.tasks);
            let (continue_tx,continue_rx)=mpsc::channel();let continue_rx=Mutex::new(continue_rx);
            let finished=AtomicBool::new(false);let mut released=false;let mut adopted=0;let mut failed=false;
            crate::completion_events::fragments(tasks,Some(&pool),|task,emit| {
                let block=task.table()==Some(1);
                task.run(&|event| {
                    let pause=block && matches!(&event,RegistrationEvent::Decisions(v) if v.last().unwrap().cell==31);
                    emit(event);
                    if pause {continue_rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();}
                });
                if block {finished.store(true,Ordering::Release);}
            },|events| {
                for event in events.drain(..) {pending.accept(&mut g,&mut done,event);}
                if !failed {
                    let n=pending.ready(&done);
                    if n!=0 {
                        pending.advance(n);
                        for d in done.drain(..n) {
                            if adopted==stop {failed=true;break;}
                            for row in d.done.piece.units {g.commit_unit_row(row).unwrap();}
                            adopted+=1;
                        }
                        if !released {
                            assert!(!finished.load(Ordering::Acquire),"source prefix must run inside the owner's lifetime");
                            assert_eq!(n,32,"all Cells use both tables, yet the first fragment can advance");
                            continue_tx.send(()).unwrap();released=true;
                        }
                    }
                }
            });
            assert!(released && finished.load(Ordering::Acquire));assert_eq!(adopted,stop);
            g.finish_unit_registration(pending.registration);
            for cell in 0..stop {for table in 0..2 {expected.commit_unit_row(units::Row::prepared(table,key(cell%19,true))).unwrap();}}
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            assert_eq!(g.query_versions,expected.query_versions);
            assert_eq!((g.changes.events,g.changes.distinct_events),(expected.changes.events,expected.changes.distinct_events));
            for graph in [&mut g,&mut expected] {graph.set_function(1,key(99,true),Value::Int(0)).unwrap();}
            assert_eq!(g.export().unwrap(),expected.export().unwrap(),"late owners must restore indexes after a source error");
        }
    }
    #[test]
    fn table_owners_preserve_ordered_witness_mapping_changes_and_row_allocations_on_abort() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(3).build().unwrap();
        for scalar in [false,true] {for preexisting in [false,true] {for stop in [0,1,2,5,19,64] {
            let mut g=graph(scalar);let mut expected=graph(scalar);
            if preexisting {for graph in [&mut g,&mut expected] {graph.set_function(0,key(0,scalar),Value::Int(0)).unwrap();}}
            let rows:Vec<_>=(0..64).map(|i|units::Row::prepared(i%2,key((i/2)%9,scalar))).collect();
            let fields:Vec<_>=rows.iter().map(|r|std::sync::Arc::downgrade(&r.fields)).collect();
            let mut done=vec![completed(rows)];
            let registration=g.plan_unit_registration(&mut done,&pool).unwrap();
            let mut actual=Vec::new();let mut reference=Vec::new();
            let mut identities=BTreeMap::new();
            if preexisting {identities.insert(0,0);}
            for (i,row) in done.pop().unwrap().done.piece.units.into_iter().enumerate() {
                if i>=stop {drop(row);continue;}
                let pointer=row.fields.as_ptr();let (index,new)=g.commit_unit_row(row).unwrap();
                if new {assert_eq!(g.function_decoded[index].as_ref().unwrap().as_ptr(),pointer,"adopt the worker's row allocation");}
                actual.push((index,new));
                reference.push(expected.commit_unit_row(units::Row::prepared(i%2,key((i/2)%9,scalar))).unwrap());
            }
            // This is also the normal error path: restore only the committed
            // prefix and invalidate the prepared suffix, without a worker join.
            g.finish_unit_registration(registration);
            for ((actual,new),(reference,expected_new)) in actual.iter().zip(&reference) {
                assert_eq!(new,expected_new);
                if let Some(previous)=identities.insert(*actual,*reference) {assert_eq!(previous,*reference,"stable winner alias");}
            }
            let ordered:Vec<_>=identities.values().copied().collect();
            assert!(ordered.windows(2).all(|pair|pair[0]<pair[1]),"witness renaming is injective and preserves source order");
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            assert_eq!(g.query_versions,expected.query_versions);
            assert_eq!((g.changes.events,g.changes.distinct_events),(expected.changes.events,expected.changes.distinct_events));
            let changes=|g:&Graph,rename:bool|g.changes.tables().map(|(t,rows)| {
                let rows:BTreeSet<_>=rows.iter().map(|(w,c)| {
                    let witness=if rename {match w {Dependency::Function(i)=>Dependency::Function(identities[i]),_=>*w}}else{*w};
                    (witness,matches!(c,crate::change_batch::Change::Wake))
                }).collect();(t,rows)
            }).collect::<Vec<_>>();
            assert_eq!(changes(&g,true),changes(&expected,false),"source table activation and coalesced changes under the verified address map");
            assert!(fields[stop..].iter().all(|w|w.upgrade().is_none()),"no retained unadopted row fields");
            assert_eq!(g.stats.unit_registry_pool_calls,u64::from(!registry_inline()));
            assert_eq!(g.stats.unit_registry_worker_identity_rows,if registry_inline() {0} else {64});
            assert_eq!(g.stats.function_updates,expected.stats.function_updates);
            let vacant=g.functions.iter().enumerate().filter(|(_,f)|!f.live).count();
            assert_eq!(vacant as u64,g.stats.unit_registry_retained_holes);
            for (i,f) in g.functions.iter().enumerate().filter(|(_,f)|!f.live) {
                assert!(g.function(i).is_none() && g.function_decoded[i].is_none());
                assert!(f.origin.is_none() && !g.dependencies.contains_key(&Dependency::Function(i)));
            }
            // Deleted reserved identities can be reused by the next ordinary
            // write; there must be no dangling index or membership left.
            for graph in [&mut g,&mut expected] {graph.set_function(1,key(99,scalar),Value::Int(0)).unwrap();}
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            let values=|g:&Graph|g.witnesses(1).into_iter().map(|w|g.row(w).unwrap().unwrap().values.to_vec()).collect::<Vec<_>>();
            assert_eq!(values(&g),values(&expected),"subsequent allocation keeps witness encounter order");
        }}}
    }
    #[test]
    fn held_tables_cannot_be_read_as_empty_or_as_unallocated_rows() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let mut g=graph(true);g.set_function(0,key(0,true),Value::Int(0)).unwrap();
        let mut done=vec![completed((0..40).map(|i|units::Row::prepared(i%2,key(i,true))).collect())];
        let registration=g.plan_unit_registration(&mut done,&pool).unwrap();
        assert!((registration.start..registration.end).all(|i|g.function(i).is_none()),
            "reserved slots never impersonate committed rows");
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(||g.function_index(0,&key(0,true)))).is_err());
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(||g.witnesses(0))).is_err());
        g.finish_unit_registration(registration);
        assert_eq!(g.function_index(0,&key(0,true)),Some(0));
        assert_eq!(g.witnesses(0),[Dependency::Function(0)]);
        assert_eq!(g.function_index(1,&key(1,true)),None);
    }
}
