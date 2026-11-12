//! One worker region owns exact Unit classification, compact identity prefix
//! and index/change preparation. Source adoption keeps actual row/effect order;
//! returning the original table owners then opens their prepared directories.
use super::*;
use rayon::prelude::*;
use crate::sync_diagnostics::{Clock,registry_inline};

#[derive(Clone,Copy)]
enum Choice {New,Existing(usize),Earlier(usize),Assigned(usize,bool)}
struct Item<'a> {source:usize,row:&'a mut units::Row,choice:Choice}
struct NewRow {index:usize,fields:RowFields}
struct Owner {
    table:usize,keys:scalar_keys::FunctionKeys,members:TableRows<u64>,version:u64,
    changes:rustc_hash::FxHashMap<Dependency,crate::change_batch::Change>,added:Vec<NewRow>,
}
struct TableJob<'a> {owner:Owner,items:Vec<Item<'a>>}
#[must_use="table owners must be returned even when source adoption fails"]
pub(crate) struct Registration {owners:Vec<Owner>,start:usize,end:usize}

impl Graph {
    /// The caller proves a complete terminal prefix: no intervening mutable
    /// reads, union, fallible suffix or other Function-producing operation.
    /// Leased directories/memberships reject access outside this proof.
    pub(crate) fn plan_unit_registration(&mut self,done:&mut [Completed],pool:&rayon::ThreadPool)->Option<Registration> {
        let mut diagnostic=Clock::new();
        if !self.pipelined_births_ready() {return None;}
        let count=done.iter().map(|d|d.done.piece.units.len()).sum::<usize>();
        if count<32 || done.iter().flat_map(|d|&d.done.piece.units).any(|r|self.units.owned[r.function.table]) {return None;}
        let mut tables=BTreeMap::<usize,Vec<Item<'_>>>::new();
        for (source,row) in done.iter_mut().flat_map(|d|&mut d.done.piece.units).enumerate() {
            tables.entry(row.function.table).or_default().push(Item {source,row,choice:Choice::New});
        }
        if tables.len()<2 {return None;}
        let mut jobs:Vec<_>=tables.into_iter().map(|(table,items)|TableJob {items,owner:Owner {
            table,keys:self.function_keys[table].take_owner(),members:self.members[table].take_owner(),
            version:self.query_versions[table],changes:self.changes.take_new_row_table(table),added:Vec::new(),
        }}).collect();
        let start=self.functions.len();let inline=registry_inline();
        let run=|jobs:&mut [TableJob<'_>]| {
            let classify=|job:&mut TableJob<'_>| {
                let mut seen=rustc_hash::FxHashMap::<&[Value],usize>::default();
                for item in &mut job.items {
                    item.choice=if let Some(&index)=job.owner.keys.get(&item.row.function.key) {Choice::Existing(index)}
                        else if let Some(&previous)=seen.get(item.row.function.key.as_slice()) {Choice::Earlier(previous)}
                        else {seen.insert(&item.row.function.key,item.source);Choice::New};
                }
                seen.capacity()*std::mem::size_of::<(&[Value],usize)>()
            };
            let scratch:usize=if inline {jobs.iter_mut().map(classify).sum()} else {jobs.par_iter_mut().map(classify).sum()};
            // The only cross-table obligation is this bounded source prefix.
            // It runs on a worker and does not move any binding or row fields.
            let mut choices=vec![Choice::New;count];
            for job in jobs.iter() {for item in &job.items {choices[item.source]=item.choice;}}
            let mut end=start;
            for source in 0..count {
                let assigned=match choices[source] {
                    Choice::New=>{let index=end;end+=1;(index,true)},
                    Choice::Existing(index)=>(index,false),
                    Choice::Earlier(previous)=>{
                        let Choice::Assigned(index,_)=choices[previous] else {unreachable!("earlier source identity")};
                        (index,false)
                    },
                    Choice::Assigned(..)=>unreachable!(),
                };
                choices[source]=Choice::Assigned(assigned.0,assigned.1);
            }
            let worker=rayon::current_thread_index().is_some();
            let install=|job:&mut TableJob<'_>| {
                let owner=&mut job.owner;
                for item in &mut job.items {
                    let Choice::Assigned(index,new)=choices[item.source] else {unreachable!()};
                    // Only the first new row of a previously inactive table
                    // asks source adoption to activate that table in order.
                    let activate=new && owner.changes.is_empty();
                    item.row.registered=Some((index,new,activate));
                    if !new {continue;}
                    owner.keys.insert(&item.row.function.key,index);
                    owner.members.insert(index as u64);owner.version+=1;
                    assert!(owner.changes.insert(Dependency::Function(index),crate::change_batch::Change::Wake).is_none());
                    // Retain the original fields only until source adoption.
                    // An error invalidates the unadopted suffix by exact key.
                    owner.added.push(NewRow {index,fields:item.row.fields.clone()});
                }
            };
            if inline {jobs.iter_mut().for_each(install);} else {jobs.par_iter_mut().for_each(install);}
            (end,worker,scratch+choices.capacity()*std::mem::size_of::<Choice>())
        };
        diagnostic.enter();
        let (end,worker,scratch)=if inline {run(&mut jobs)} else {pool.install(||run(&mut jobs))};
        diagnostic.join();
        let mut bytes=jobs.capacity()*std::mem::size_of::<TableJob<'_>>() + scratch;
        bytes+=jobs.iter().map(|j|j.items.capacity()*std::mem::size_of::<Item<'_>>()
            +j.owner.added.capacity()*std::mem::size_of::<NewRow>()).sum::<usize>();
        let owners:Vec<_>=jobs.into_iter().map(|job|job.owner).collect();
        bytes+=owners.capacity()*std::mem::size_of::<Owner>();
        self.stats.unit_registry_batches+=1;self.stats.unit_registry_candidates+=count as u64;
        self.stats.unit_registry_bytes+=bytes as u64;
        self.stats.unit_registry_pool_calls+=u64::from(!inline);
        self.stats.unit_registry_identity_rows+=count as u64;
        self.stats.unit_registry_worker_identity_rows+=if worker {count as u64} else {0};
        self.stats.unit_registry_owner_tables+=owners.len() as u64;
        #[cfg(feature="cell-sync-diagnostics")]
        self.stats.sync_diagnostics.registration.record(diagnostic,None,!inline,pool.current_num_threads());
        Some(Registration {owners,start,end})
    }

    /// No second pool invocation, table regrouping, key hashing or insertion
    /// on success. Restore the actual prepared maps after rows exist. Failure
    /// removes only identities beyond the source-adopted prefix first.
    pub(crate) fn finish_unit_registration(&mut self,registration:Registration) {
        let adopted=self.functions.len();
        assert!(registration.start<=adopted && adopted<=registration.end,"terminal Function prefix");
        for mut owner in registration.owners {
            let total=owner.added.len();
            let retained=owner.added.partition_point(|row|row.index<adopted);
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
    }
}

#[cfg(test)]
mod tests {
    use super::*;
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
    fn table_owners_preserve_exact_prefix_ids_changes_and_row_allocations_on_abort() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(3).build().unwrap();
        for scalar in [false,true] {for preexisting in [false,true] {for stop in [0,1,2,5,19,64] {
            let mut g=graph(scalar);let mut expected=graph(scalar);
            if preexisting {for graph in [&mut g,&mut expected] {graph.set_function(0,key(0,scalar),Value::Int(0)).unwrap();}}
            let rows:Vec<_>=(0..64).map(|i|units::Row::prepared(i%2,key((i/2)%9,scalar))).collect();
            let fields:Vec<_>=rows.iter().map(|r|std::sync::Arc::downgrade(&r.fields)).collect();
            let mut done=vec![completed(rows)];
            let registration=g.plan_unit_registration(&mut done,&pool).unwrap();
            let mut actual=Vec::new();let mut reference=Vec::new();
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
            assert_eq!(actual,reference);
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            assert_eq!(g.query_versions,expected.query_versions);
            assert_eq!((g.changes.events,g.changes.distinct_events),(expected.changes.events,expected.changes.distinct_events));
            let changes=|g:&Graph|g.changes.tables().map(|(t,rows)| {
                let rows:BTreeSet<_>=rows.iter().map(|(w,c)|(*w,matches!(c,crate::change_batch::Change::Wake))).collect();(t,rows)
            }).collect::<Vec<_>>();
            assert_eq!(changes(&g),changes(&expected),"source table activation and coalesced changes");
            assert!(fields[stop..].iter().all(|w|w.upgrade().is_none()),"no retained unadopted row fields");
            assert_eq!(g.stats.unit_registry_pool_calls,u64::from(!registry_inline()));
            assert_eq!(g.stats.unit_registry_worker_identity_rows,if registry_inline() {0} else {64});
            assert_eq!(g.stats.function_updates,expected.stats.function_updates);
            // Deleted reserved identities can be reused by the next ordinary
            // write; there must be no dangling index or membership left.
            for graph in [&mut g,&mut expected] {graph.set_function(1,key(99,scalar),Value::Int(0)).unwrap();}
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            assert_eq!(g.witnesses(1),expected.witnesses(1));
        }}}
    }
    #[test]
    fn held_tables_cannot_be_read_as_empty_or_as_unallocated_rows() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let mut g=graph(true);g.set_function(0,key(0,true),Value::Int(0)).unwrap();
        let mut done=vec![completed((0..40).map(|i|units::Row::prepared(i%2,key(i,true))).collect())];
        let registration=g.plan_unit_registration(&mut done,&pool).unwrap();
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(||g.function_index(0,&key(0,true)))).is_err());
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(||g.witnesses(0))).is_err());
        g.finish_unit_registration(registration);
        assert_eq!(g.function_index(0,&key(0,true)),Some(0));
        assert_eq!(g.witnesses(0),[Dependency::Function(0)]);
        assert_eq!(g.function_index(1,&key(1,true)),None);
    }
}
