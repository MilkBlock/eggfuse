//! Completion events return the actual registration owners. A source Cell
//! waits for its own Unit tables and the constructor/slot owner, not all tables.
use super::*;

struct Item {cell:usize,row:usize,source:usize,fields:RowFields}
struct NewRow {index:usize,fields:RowFields}
pub(crate) struct Owner {
    table:usize,keys:scalar_keys::FunctionKeys,members:TableRows<u64>,version:u64,
    changes:rustc_hash::FxHashMap<Dependency,crate::change_batch::Change>,added:Vec<NewRow>,
}
pub(crate) struct TableJob {owner:Owner,items:Vec<Item>,start:usize}
pub(crate) struct Structure {
    functions:Vec<Function>,decoded:Vec<Option<RowFields>>,end:usize,first_table:usize,
    constructors:Option<constructor_registration::Owned>,growth:usize,births:usize,
}
pub(crate) enum RegistrationTask {Table(TableJob),Structure(Box<Structure>),Subscriptions(Box<constructor_registration::Subscriptions>)}
pub(crate) struct Decision {cell:usize,row:usize,value:(usize,bool,bool)}
pub(crate) enum RegistrationEvent {Decisions(Vec<Decision>),Table(Owner),Structure(Box<Structure>),Subscriptions(Box<constructor_registration::Subscriptions>)}
impl RegistrationEvent {
    pub(crate) fn completes_owner(&self)->bool { !matches!(self,Self::Decisions(_)) }
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
                    decisions.push(Decision {cell:item.cell,row:item.row,value:(index,new,activate)});
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
                if let Some(owner)=&mut state.constructors {owner.install();}
                emit(RegistrationEvent::Structure(state));
            }
            Self::Subscriptions(mut owner)=> {owner.install();emit(RegistrationEvent::Subscriptions(owner));}
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
    structure_ready:bool,subscriptions_ready:bool,accepted:usize,
}
impl PendingRegistration {
    /// Restore all returned owners even after a source error. The source error
    /// only closes adoption; unfinished private work still has to give back
    /// its original index so finish_unit_registration can invalidate its suffix.
    pub fn accept(&mut self,graph:&mut Graph,done:&mut [Completed],event:RegistrationEvent) {
        match event {
            RegistrationEvent::Subscriptions(owner)=> {owner.restore(graph);self.subscriptions_ready=true;}
            RegistrationEvent::Structure(state)=> {
                assert!(graph.functions.is_empty() && graph.function_decoded.is_empty());
                let Structure {functions,decoded,constructors,growth,births,..}=*state;
                graph.functions=functions;graph.function_decoded=decoded;
                graph.stats.unit_registry_capacity_growth_bytes+=growth as u64;
                if let Some(owner)=constructors {
                    graph.stats.constructor_registry_bytes+=owner.storage_bytes() as u64;
                    graph.stats.constructor_registry_rows+=births as u64;
                    graph.stats.constructor_registry_worker_rows+=if crate::sync_diagnostics::registry_inline() {0}else{births as u64};
                    graph.stats.constructor_registry_batches+=1;
                    self.registration.constructors=Some(owner.restore(graph));
                }
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
                self.registration.owners.push(owner);
            }
        }
    }
    pub fn ready(&self,done:&[Completed])->usize {
        if !self.structure_ready || !self.subscriptions_ready {return 0;}
        done.iter().take_while(|d|d.done.piece.units.iter().all(|r|r.registered.is_some())).count()
    }
    pub fn advance(&mut self,count:usize) {self.accepted+=count;}
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
        let births=birth_count!=0 && self.local_jobs_supported() && done.iter().all(|d| {
            self.cells.get(&d.done.cell).is_some_and(|c|d.done.piece.rows.iter().all(|r|
                r.operation>=c.completed_prefix && !c.facts.contains_key(&(r.operation as u32))
                && self.program.repair_ports.key_eq_columns[r.table].is_some()))
        });
        let mut tables=BTreeMap::<usize,Vec<Item>>::new();let mut source=0;
        for (cell,d) in done.iter().enumerate() {for (row,r) in d.done.piece.units.iter().enumerate() {
            tables.entry(r.function.table).or_default().push(Item {cell,row,source,fields:r.fields.clone()});source+=1;
        }}
        self.stats.unit_registry_bytes+=tables.values().map(|v|v.capacity()*std::mem::size_of::<Item>()).sum::<usize>() as u64;
        let mut tasks:Vec<_>=tables.into_iter().map(|(table,items)|RegistrationTask::Table(TableJob {items,start,owner:Owner {
            table,keys:self.function_keys[table].take_owner(),members:self.members[table].take_owner(),
            version:self.query_versions[table],changes:self.changes.take_new_row_table(table),added:Vec::new(),
        }})).collect();
        let table_count=tasks.len();
        let constructors=births.then(|| {
            let (rows,subscriptions)=constructor_registration::Owned::take(self,done);
            tasks.insert(0,RegistrationTask::Subscriptions(Box::new(subscriptions)));rows
        });
        tasks.push(RegistrationTask::Structure(Box::new(Structure {
            functions:std::mem::take(&mut self.functions),decoded:std::mem::take(&mut self.function_decoded),
            end,first_table:first_table.unwrap(),constructors,growth:0,births:birth_count,
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
        Some(PendingRegistration {tasks,registration:Registration {owners,start,end,constructors:None},structure_ready:false,subscriptions_ready:!births,accepted:0})
    }

    #[cfg(test)]
    pub(crate) fn plan_unit_registration(&mut self,done:&mut [Completed],pool:&rayon::ThreadPool)->Option<Registration> {
        let mut pending=self.prepare_unit_registration(done)?;
        let tasks=std::mem::take(&mut pending.tasks);
        crate::completion_events::fragments(tasks,(!crate::sync_diagnostics::registry_inline()).then_some(pool),RegistrationTask::run,
            |ready| {for event in ready.drain(..) {pending.accept(self,done,event);}});
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
