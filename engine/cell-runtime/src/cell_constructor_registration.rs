//! Adopt proven terminal constructor rows in the existing Unit owner region.
//! The original Cell storage, indexes and reverse incidences have disjoint
//! owners. Source order opens only the prepared publication fragments; it does
//! not repeat row installation. An unadopted suffix is invalidated on error.
use super::*;
use std::collections::VecDeque;
#[path="cell_constructor_fused.rs"]
pub(crate) mod fused;

#[derive(Default)]
pub(crate) struct Publication {
    tables: smallvec::SmallVec<[(usize, u64, bool); 2]>,
}
struct Installed {
    cell: u32,
    first: usize,
    end: usize,
    publication: Publication,
}
#[derive(Default)]
pub(super) struct Registration {
    ready:VecDeque<std::vec::IntoIter<CellReady>>,received:usize,
    // A source error stops adoption before the next take. Earlier certificates
    // can retire; this last offered Cell and the untouched suffix remain live.
    offered:Option<Installed>,
}

/// Only the original fact slots leave the instance. Its values, parent and
/// physical arena position stay in place while registration fills those slots.
pub(crate) struct Owned {
    frames:Vec<Vec<CellReady>>,intern:HashMap<u64,crate::tiny_set::TinySet<FactRef>>,
    members:Vec<TableRows<u64>>,changes:BTreeMap<usize,HashMap<Dependency,crate::change_batch::Change>>,
    epoch:u64,input:std::sync::Arc<Input>,
}
pub(crate) struct Subscriptions {
    uses:HashMap<u64,UseSet>,dependencies:HashMap<Dependency,smallvec::SmallVec<[u64;3]>>,
    metrics:maintenance::Metrics,columns:std::sync::Arc<[Option<Vec<usize>>]>,
    input:std::sync::Arc<Input>,
}
pub(crate) struct CellReady {facts:crate::slots::FrameMap<u32,FactState>,installed:Installed}
struct Input {groups:Vec<OwnedGroup>,rows:Vec<Born>}
struct OwnedGroup {cell:u32,rows:std::ops::Range<usize>}
impl Owned {
    pub(super) fn take(graph:&mut Graph,done:&mut [Completed])->(Self,Subscriptions,Registration) {
        let mut rows=Vec::with_capacity(done.iter().map(|d|d.done.piece.rows.len()).sum());
        let groups=done.iter_mut().map(|d| {
            let first=rows.len();rows.extend(d.done.piece.rows.drain(..));
            OwnedGroup {cell:d.done.cell,rows:first..rows.len()}
        }).collect();
        let input=std::sync::Arc::new(Input {groups,rows});
        let changes=input.rows.iter().map(|r|r.table).collect::<BTreeSet<_>>().into_iter()
            .map(|table|(table,graph.changes.take_new_row_table(table))).collect();
        // Lease only the slots this worker writes. The original arena layout
        // and all Cell input/continuation state stay in place.
        let frames=input.groups.chunks(16).enumerate().map(|(chunk,groups)|groups.iter().enumerate().map(|(i,g)| {
            let frame=graph.cells.get_mut(&g.cell).unwrap();
            let installed=Installed {cell:g.cell,first:frame.completed_prefix,
                end:done[chunk*16+i].done.piece.end,publication:Publication::default()};
            CellReady {facts:std::mem::take(&mut frame.facts),installed}
        }).collect()).collect();
        let subscriptions=Subscriptions {uses:std::mem::take(&mut graph.uses),
            dependencies:std::mem::take(&mut graph.dependencies),metrics:std::mem::take(&mut graph.maintenance),
            columns:graph.program.repair_ports.key_eq_columns.clone(),input:input.clone()};
        let rows=Self {frames,intern:std::mem::take(&mut graph.intern),members:std::mem::take(&mut graph.members),
            changes,epoch:graph.epoch,input};
        graph.stats.constructor_registry_bytes+=rows.storage_bytes() as u64;
        (rows,subscriptions,Registration::default())
    }
    pub fn install(&mut self,emit:&(dyn Fn(Vec<CellReady>)+Sync)) {
        let mut i=0;
        for mut ready in std::mem::take(&mut self.frames) {
            for cell in &mut ready {
                let group=&self.input.groups[i];i+=1;assert_eq!(cell.installed.cell,group.cell);
                let changes=&mut self.changes;
                cell.installed.publication=install_cell(cell.installed.cell,&mut cell.facts,
                    &self.input.rows[group.rows.clone()],self.epoch,&mut self.intern,&mut self.members,
                    |table,witness| {
                        let rows=changes.get_mut(&table).unwrap();let activate=rows.is_empty();
                        assert!(rows.insert(witness,crate::change_batch::Change::Wake).is_none());activate
                    });
            }
            emit(ready);
        }
    }
    fn storage_bytes(&self)->usize {
        std::mem::size_of::<Self>()+std::mem::size_of::<Subscriptions>()+std::mem::size_of::<Input>()
            +2*std::mem::size_of::<usize>()+self.input.groups.capacity()*std::mem::size_of::<OwnedGroup>()
            +self.input.rows.capacity()*std::mem::size_of::<Born>()
            +self.frames.capacity()*std::mem::size_of::<Vec<CellReady>>()
    }
    pub fn restore(self,graph:&mut Graph) {
        assert!(graph.members.is_empty() && graph.intern.is_empty(),"no constructor lookup inside terminal registration");
        graph.intern=self.intern;graph.members=self.members;
        for (table,rows) in self.changes {graph.changes.restore_new_row_table(table,rows);}
    }
}
impl Subscriptions {
    pub fn install(&mut self) {
        for group in &self.input.groups {for row in &self.input.rows[group.rows.clone()] {
            maintenance::subscribe_fresh(&mut self.uses,&mut self.dependencies,&mut self.metrics,
                Dependency::Fact(FactRef {cell:group.cell,op:row.operation as u32}),&row.fields,
                Some(self.columns[row.table].as_ref().unwrap()));
        }}
    }
    pub fn unit(&mut self,index:usize,fields:&[Value]) {
        maintenance::subscribe_fresh(&mut self.uses,&mut self.dependencies,&mut self.metrics,
            Dependency::Function(index),fields,None);
    }
    pub fn restore(self,graph:&mut Graph) {
        assert!(graph.uses.is_empty() && graph.dependencies.is_empty());
        graph.uses=self.uses;graph.dependencies=self.dependencies;graph.maintenance=self.metrics;
    }
}
fn install_cell(cell:u32,facts:&mut crate::slots::FrameMap<u32,FactState>,rows:&[Born],epoch:u64,
    intern:&mut HashMap<u64,crate::tiny_set::TinySet<FactRef>>,members:&mut [TableRows<u64>],
    mut prepare:impl FnMut(usize,Dependency)->bool)->Publication {
    let mut publication=Publication::default();
    for row in rows {
        let f=FactRef {cell,op:row.operation as u32};
        assert!(facts.insert(f.op,FactState {owned:false,local_union_owned:false,
            #[cfg(feature="receipt-slots")] port_slot:0,
            decoded:Some((row.table,row.fields.clone())),entry:None,hidden:false,epoch,born:epoch,hash:row.hash,
        }).is_none(),"fresh constructor operation");
        intern.entry(row.hash).or_default().insert(f);members[row.table].insert(f.ordered_id());
        let activate=prepare(row.table,Dependency::Fact(f));
        if let Some((_,count,_))=publication.tables.iter_mut().find(|r|r.0==row.table) {*count+=1;}
        else {publication.tables.push((row.table,1,activate));}
    }
    publication
}
impl Registration {
    fn restore_cell(&mut self,graph:&mut Graph,ready:&mut CellReady) {
        let CellReady {facts,installed}=ready;
        if installed.publication.tables.spilled() {
            graph.stats.constructor_registry_bytes+=(installed.publication.tables.capacity()*std::mem::size_of::<(usize,u64,bool)>()) as u64;
        }
        let frame=graph.cells.get_mut(&installed.cell).expect("the original instance stays in place");
        assert!(frame.facts.is_empty(),"return original fact slots once");
        frame.facts=std::mem::take(facts);
    }
    fn offer(&mut self,mut installed:Installed)->Publication {
        let publication=std::mem::take(&mut installed.publication);
        // All-reuse Cells can retire immediately; they have nothing to revoke.
        self.offered=(!publication.tables.is_empty()).then_some(installed);publication
    }
    pub fn receive(&mut self,graph:&mut Graph,mut ready:Vec<CellReady>) {
        graph.stats.constructor_registry_frame_bytes+=(ready.capacity()*std::mem::size_of::<CellReady>()) as u64;
        graph.stats.constructor_registry_frame_events+=1;
        graph.stats.constructor_registry_frame_transfers+=ready.len() as u64;
        self.received+=ready.len();
        for cell in &mut ready {self.restore_cell(graph,cell);}
        // Keep the original completion buffer until its certificates are used;
        // there is no second all-Cell Installed vector or successful-prefix log.
        let before=self.ready.capacity();self.ready.push_back(ready.into_iter());
        graph.stats.constructor_registry_bytes+=((self.ready.capacity()-before)*std::mem::size_of::<std::vec::IntoIter<CellReady>>()) as u64;
    }
    pub fn ready(&self)->usize {self.received}
    /// The caller completes each offered Cell before taking the next one, or
    /// stops on its source error and drains owners without further adoption.
    pub fn take(&mut self,cell:u32)->Publication {
        let chunk=self.ready.front_mut().expect("ready constructor fragment");
        let installed=chunk.next().expect("nonempty fragment").installed;
        if chunk.len()==0 {self.ready.pop_front();}
        assert_eq!(installed.cell,cell,"source-ordered constructor acceptance");
        self.offer(installed)
    }
    pub fn finish(self, graph: &mut Graph) {
        for installed in self.offered.into_iter().chain(self.ready.into_iter().flatten()
            .filter(|c|!c.installed.publication.tables.is_empty()).map(|c|c.installed)) {
            graph.stats.constructor_registry_retirement_checks+=1;
            if graph.cells[&installed.cell].completed_prefix >= installed.end {continue;}
            // Only a failed source prefix reaches here. Earlier adopted rows
            // and their original publication order are left intact.
            let discarded:Vec<_>=graph.cells[&installed.cell].facts.iter()
                .filter(|(op,_)|**op as usize>=installed.first)
                .map(|(&op,state)|(FactRef {cell:installed.cell,op},state.hash,state.decoded.as_ref().unwrap().0))
                .collect();
            for (f,hash,table) in discarded {
                graph.cells.get_mut(&f.cell).unwrap().facts.remove(&f.op);
                let bucket=graph.intern.get_mut(&hash).unwrap();bucket.remove(&f);
                if bucket.is_empty() {graph.intern.remove(&hash);}
                assert!(graph.members[table].remove(&f.ordered_id()));
                graph.changes.discard_prepared_row(table,Dependency::Fact(f));
                maintenance::replace_subscriptions(&mut graph.uses,&mut graph.dependencies,
                    &mut graph.maintenance,&graph.parents,Dependency::Fact(f),Default::default());
                graph.stats.constructor_registry_discarded+=1;
            }
        }
    }
}
impl Graph {
    pub(super) fn publish_registered_births(&mut self, publication: Publication) -> usize {
        let count=publication.tables.iter().map(|(_,n,_)|*n as usize).sum::<usize>();
        self.stats.constructor_registry_fragments+=publication.tables.len() as u64;
        for (table,rows,activate) in publication.tables {
            if activate {self.changes.activate_registered_table(table);}
            self.changes.finish_new_rows(table,rows);
            self.query_versions[table]+=rows;
        }
        self.stats.logical_facts_created+=count as u64;
        self.stats.constructor_registry_adopted+=count as u64;
        self.changed |= count!=0;
        count
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn publication_fragments_preserve_intervening_function_table_order() {
        let mut changes=crate::change_batch::ChangeBatch::new(3);
        changes.enable_split();
        let a=Dependency::Fact(FactRef {cell:1,op:0});
        let b=Dependency::Fact(FactRef {cell:2,op:0});
        assert!(changes.prepare_new_row(0,a));
        assert!(changes.prepare_new_row(2,b));
        assert!(changes.is_empty(),"preparation must not open either table");
        changes.activate_prepared_table(0);changes.finish_new_rows(0,1);
        changes.touch(1,Dependency::Function(0));
        changes.activate_prepared_table(2);changes.finish_new_rows(2,1);
        assert_eq!(changes.tables().map(|(t,_)|t).collect::<Vec<_>>(),[0,1,2]);
        assert_eq!((changes.events,changes.distinct_events),(3,3));
        let mut deferred=crate::change_batch::ChangeBatch::new(3);deferred.enable_split();
        changes.defer_unready(&[false,true,false],&mut deferred);
        assert_eq!((changes.events,deferred.events),(1,2));
    }
    fn prepared() -> (Graph,Vec<Completed>) {
        let mut g=super::super::tests::graph();
        g.program.repair_ports=repair_ports::Plan::derive(&g.program);
        let mut done=Vec::new();
        for i in 0..8 {
            let cell=g.begin_transient(0,[(0,Value::Eq(100+i))].into_iter().collect(),None).unwrap();
            g.construct(cell,0,0,&[Arg::Slot(0)],1).unwrap();
            g.rhs_frame_mut(cell).unwrap().completed_prefix=1;
            let mut window=Window::seed(&g,cell,1);
            let (_,job)=g.take_local_job(0,cell,&mut window,4,false).unwrap();
            let mut effects=crate::cell::Effects::default();
            done.push(Completed {done:job.unwrap().run(g.parents.reader(),&mut effects.writer(),&mut Counts::default()),effects});
        }
        (g,done)
    }
    #[test]
    fn actual_indexes_and_subscriptions_keep_only_the_source_adopted_prefix() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(4).build().unwrap();
        for stop in [0,1,3,8] {for fail_after_offer in [false,true] {
            let (mut g,mut done)=prepared();let (mut expected,reference)=prepared();
            let cells:Vec<_>=done.iter().map(|d|d.done.cell).collect();
            let pointers:Vec<_>=done.iter().flat_map(|d|d.done.piece.rows.iter().map(move |r|
                (FactRef {cell:d.done.cell,op:r.operation as u32},r.fields.as_ptr()))).collect();
            let layout=|g:&Graph|g.cells.iter().map(|(id,c)|(*id,c as *const Cell as usize)).collect::<Vec<_>>();
            let before=layout(&g);
            let (mut owner,mut subscriptions,mut registration)=Owned::take(&mut g,&mut done);
            assert_eq!(layout(&g),before,"leasing fact slots must not relocate the arena");
            let returned=std::sync::Mutex::new(Vec::new());
            pool.install(||rayon::join(||owner.install(&|ready|returned.lock().unwrap().push(ready)),
                ||subscriptions.install()));
            for ready in returned.into_inner().unwrap() {registration.receive(&mut g,ready);}
            owner.restore(&mut g);subscriptions.restore(&mut g);
            assert_eq!(layout(&g),before,"fact return must preserve instance identity and position");
            for (f,pointer) in pointers {assert_eq!(g.cells[&f.cell].facts[&f.op].decoded.as_ref().unwrap().1.as_ptr(),pointer);}
            // Prepared rows do not count as source-applied mutations or open
            // a Run publication. Only source acceptance advances those counts.
            assert_eq!(g.stats.logical_facts_created,expected.stats.logical_facts_created);
            assert_eq!(g.changes.events,expected.changes.events);
            for (mut a,mut b) in done.into_iter().zip(reference).take(stop) {
                let publication=registration.take(a.done.cell);
                g.commit_registered_local_job(a.done,&mut a.effects.writer(),Some(publication)).unwrap();
                expected.commit_local_job(b.done,&mut b.effects.writer()).unwrap();
            }
            if fail_after_offer && stop<cells.len() {
                // A source error may occur after the certificate was taken but
                // before its Cell's prefix was committed. It must not be lost.
                drop(registration.take(cells[stop]));
            }
            registration.finish(&mut g);
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            assert_eq!(g.query_versions,expected.query_versions);
            assert_eq!((g.changes.events,g.changes.distinct_events),(expected.changes.events,expected.changes.distinct_events));
            assert_eq!(g.dependencies,expected.dependencies);
            let uses=|g:&Graph|g.uses.iter().map(|(k,v)|(*k,v.iter().copied().collect::<BTreeSet<_>>())).collect::<BTreeMap<_,_>>();
            assert_eq!(uses(&g),uses(&expected));
            assert_eq!(g.stats.constructor_registry_adopted,2*stop as u64);
            assert_eq!(g.stats.constructor_registry_discarded,2*(8-stop) as u64);
            if stop==8 {assert_eq!(g.stats.constructor_registry_retirement_checks,1,"no successful-prefix rescan");}
            assert_eq!(g.maintenance_report()["stats"]["live_reverse_edges"],expected.maintenance_report()["stats"]["live_reverse_edges"]);
            for graph in [&mut g,&mut expected] {graph.union(100,101).unwrap();graph.repair().unwrap();}
            assert_eq!(g.export().unwrap(),expected.export().unwrap(),"later repair must not see invalidated rows");
        }}
    }
}
