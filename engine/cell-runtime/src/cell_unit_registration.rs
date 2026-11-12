//! Each Unit table owner assigns stable candidate slots and installs its keys
//! in one pass. Source adoption keeps actual row/effect order;
//! returning the original table owners then opens their prepared directories.
use super::*;
use rayon::prelude::*;
use crate::sync_diagnostics::{Clock,registry_inline};

struct Item<'a> {source:usize,row:&'a mut units::Row}
struct NewRow {index:usize,fields:RowFields}
struct Owner {
    table:usize,keys:scalar_keys::FunctionKeys,members:TableRows<u64>,version:u64,
    changes:rustc_hash::FxHashMap<Dependency,crate::change_batch::Change>,added:Vec<NewRow>,
}
struct TableJob<'a> {owner:Owner,items:Vec<Item<'a>>}
#[must_use="table owners must be returned even when source adoption fails"]
pub(crate) struct Registration {owners:Vec<Owner>,start:usize,end:usize,
    constructors:Option<constructor_registration::Registration>}
impl Registration {
    pub(crate) fn take_births(&mut self,cell:u32)->Option<constructor_registration::Publication> {
        self.constructors.as_mut().map(|r|r.take(cell))
    }
}

impl Graph {
    /// The caller proves a complete terminal prefix: no intervening mutable
    /// reads, union, fallible suffix or other Function-producing operation.
    /// Leased directories/memberships reject access outside this proof.
    pub(crate) fn plan_unit_registration(&mut self,done:&mut [Completed],pool:&rayon::ThreadPool)->Option<Registration> {
        let mut diagnostic=Clock::new();
        if !self.pipelined_births_ready() {return None;}
        let mut count=0;let mut first_table=None;let mut multiple_tables=false;
        for row in done.iter().flat_map(|d|&d.done.piece.units) {
            let table=row.function.table;if self.units.owned[table] {return None;}
            count+=1;
            if let Some(first)=first_table {multiple_tables|=table!=first;} else {first_table=Some(table);}
        }
        // Reject small/single-table regions before constructing any new Cell
        // registration state. This reuses the existing owner admission limit.
        if count<32 || !multiple_tables {return None;}
        // A Unit Function ID is an internal witness, never an Eq result. Its
        // source candidate position gives a stable, order-preserving address
        // before any other table has finished classification.
        let start=self.functions.len();
        let end=start.checked_add(count).filter(|&end|end<u32::MAX as usize)?;
        let birth_count=done.iter().map(|d|d.done.piece.rows.len()).sum::<usize>();
        let births=birth_count!=0 && self.local_jobs_supported() && done.iter().all(|d| {
            self.cells.get(&d.done.cell).is_some_and(|c|d.done.piece.rows.iter().all(|r|
                r.operation>=c.completed_prefix && !c.facts.contains_key(&(r.operation as u32))
                && self.program.repair_ports.key_eq_columns[r.table].is_some()))
        });
        let mut groups=Vec::new();
        let mut tables=BTreeMap::<usize,Vec<Item<'_>>>::new();let mut source=0;
        for d in done.iter_mut() {
            if births {groups.push(constructor_registration::Group {cell:d.done.cell,
                first:self.cells[&d.done.cell].completed_prefix,end:d.done.piece.end,rows:&d.done.piece.rows});}
            for row in &mut d.done.piece.units {
                tables.entry(row.function.table).or_default().push(Item {source,row});source+=1;
            }
        }
        debug_assert!(tables.len()>=2);
        let mut jobs:Vec<_>=tables.into_iter().map(|(table,items)|TableJob {items,owner:Owner {
            table,keys:self.function_keys[table].take_owner(),members:self.members[table].take_owner(),
            version:self.query_versions[table],changes:self.changes.take_new_row_table(table),added:Vec::new(),
        }}).collect();
        let inline=registry_inline();
        let functions=&mut self.functions;let decoded=&mut self.function_decoded;
        let mut run=|jobs:&mut [TableJob<'_>]| {
            let worker=rayon::current_thread_index().is_some();
            let install=|job:&mut TableJob<'_>| {
                let owner=&mut job.owner;
                for item in &mut job.items {
                    // Earlier rows are already in this same authoritative
                    // index. No second seen map, global choice array, compact
                    // identity scan or second table pass is necessary.
                    let found=owner.keys.get(&item.row.function.key).copied();
                    let (index,new)=found.map_or((start+item.source,true),|index|(index,false));
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
            let install_tables=||if inline {jobs.iter_mut().for_each(install);} else {jobs.par_iter_mut().for_each(install);};
            let reserve=|| {
                let before=(functions.capacity(),decoded.capacity());
                functions.resize_with(end,||Function {writer:None,
                    #[cfg(feature="receipt-slots")] port_slot:0,
                    table:first_table.unwrap(),key:Vec::new(),value:Value::Int(0),
                    epoch:0,live:false,origin:None});
                decoded.resize_with(end,||None);
                (functions.capacity()-before.0)*std::mem::size_of::<Function>()
                    +(decoded.capacity()-before.1)*std::mem::size_of::<Option<RowFields>>()
            };
            let growth=if inline {let mut install_tables=install_tables;let mut reserve=reserve;
                install_tables();reserve()
            } else {rayon::join(install_tables,reserve).1};
            (worker,growth)
        };
        let constructors=births.then_some(constructor_registration::Owner {
            cells:&mut self.cells,intern:&mut self.intern,members:&mut self.members,changes:&mut self.changes,
            uses:&mut self.uses,dependencies:&mut self.dependencies,metrics:&mut self.maintenance,
            parents:&self.parents,columns:&self.program.repair_ports.key_eq_columns,epoch:self.epoch,
        });
        let install=||if let Some(owner)=constructors {
            if inline {(run(&mut jobs),Some(owner.install(&groups,true)))}
            else {let (unit,constructor)=rayon::join(||run(&mut jobs),||owner.install(&groups,false));
                (unit,Some(constructor))}
        } else {(run(&mut jobs),None)};
        diagnostic.enter();
        let ((worker,growth),constructors)=if inline {install()} else {pool.install(install)};
        diagnostic.join();
        let mut bytes=jobs.capacity()*std::mem::size_of::<TableJob<'_>>();
        bytes+=jobs.iter().map(|j|j.items.capacity()*std::mem::size_of::<Item<'_>>()
            +j.owner.added.capacity()*std::mem::size_of::<NewRow>()).sum::<usize>();
        let owners:Vec<_>=jobs.into_iter().map(|job|job.owner).collect();
        let group_bytes=groups.capacity()*std::mem::size_of::<constructor_registration::Group<'_>>();
        drop(groups);
        if let Some(constructors)=&constructors {
            self.stats.constructor_registry_bytes+=(group_bytes+constructors.storage_bytes()) as u64;
            self.stats.constructor_registry_rows+=birth_count as u64;
            self.stats.constructor_registry_worker_rows+=if worker {birth_count as u64}else{0};
            self.stats.constructor_registry_batches+=1;
        }
        bytes+=owners.capacity()*std::mem::size_of::<Owner>();
        self.stats.unit_registry_batches+=1;self.stats.unit_registry_candidates+=count as u64;
        self.stats.unit_registry_bytes+=bytes as u64;
        self.stats.unit_registry_pool_calls+=u64::from(!inline);
        self.stats.unit_registry_identity_rows+=count as u64;
        self.stats.unit_registry_worker_identity_rows+=if worker {count as u64} else {0};
        self.stats.unit_registry_owner_tables+=owners.len() as u64;
        self.stats.unit_registry_reserved_slots+=count as u64;
        self.stats.unit_registry_reserved_bytes+=(count*(std::mem::size_of::<Function>()+std::mem::size_of::<Option<RowFields>>())) as u64;
        self.stats.unit_registry_capacity_growth_bytes+=growth as u64;
        #[cfg(feature="cell-sync-diagnostics")]
        self.stats.sync_diagnostics.registration.record(diagnostic,None,!inline,pool.current_num_threads());
        Some(Registration {owners,start,end,constructors})
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
