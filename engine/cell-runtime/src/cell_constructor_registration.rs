//! Adopt proven terminal constructor rows in the existing Unit owner region.
//! The original Cell storage, indexes and reverse incidences have disjoint
//! owners. Source order opens only the prepared publication fragments; it does
//! not repeat row installation. An unadopted suffix is invalidated on error.
use super::*;

#[derive(Default)]
pub(crate) struct Publication {
    tables: smallvec::SmallVec<[(usize, u64, bool); 2]>,
}
#[derive(Clone,Copy)]
pub(super) struct Group<'a> {
    pub cell: u32,
    pub first: usize,
    pub end: usize,
    pub rows: &'a [Born],
}
struct Installed {
    cell: u32,
    first: usize,
    end: usize,
    publication: Publication,
}
pub(super) struct Registration { installed: Vec<Installed>, next:usize }

/// Transfer the existing directories, not a copy of the graph. No source Cell
/// may advance until this owner has returned. Unit table owners are disjoint
/// and may still be running when it returns.
pub(super) struct Owned {
    cells:arena::Cells,intern:HashMap<u64,crate::tiny_set::TinySet<FactRef>>,
    members:Vec<TableRows<u64>>,changes:crate::change_batch::ChangeBatch,
    epoch:u64,input:std::sync::Arc<Input>,installed:Option<Registration>,
}
pub(crate) struct Subscriptions {
    uses:HashMap<u64,UseSet>,dependencies:HashMap<Dependency,smallvec::SmallVec<[u64;3]>>,
    metrics:maintenance::Metrics,parents:Parents,columns:std::sync::Arc<[Option<Vec<usize>>]>,
    input:std::sync::Arc<Input>,
}
struct Input {groups:Vec<OwnedGroup>,rows:Vec<Born>}
struct OwnedGroup {cell:u32,first:usize,end:usize,rows:std::ops::Range<usize>}
impl Input {
    fn groups(&self)->impl Iterator<Item=Group<'_>>+Clone {
        self.groups.iter().map(|g|Group {cell:g.cell,first:g.first,end:g.end,rows:&self.rows[g.rows.clone()]})
    }
}
impl Owned {
    pub fn take(graph:&mut Graph,done:&mut [Completed])->(Self,Subscriptions) {
        let mut rows=Vec::with_capacity(done.iter().map(|d|d.done.piece.rows.len()).sum());
        let groups=done.iter_mut().map(|d| {
            let first=rows.len();rows.extend(d.done.piece.rows.drain(..));
            OwnedGroup {cell:d.done.cell,first:graph.cells[&d.done.cell].completed_prefix,
                end:d.done.piece.end,rows:first..rows.len()}
        }).collect();
        let input=std::sync::Arc::new(Input {groups,rows});
        let subscriptions=Subscriptions {uses:std::mem::take(&mut graph.uses),
            dependencies:std::mem::take(&mut graph.dependencies),metrics:std::mem::take(&mut graph.maintenance),
            parents:std::mem::take(&mut graph.parents),columns:graph.program.repair_ports.key_eq_columns.clone(),input:input.clone()};
        let rows=Self {cells:std::mem::take(&mut graph.cells),intern:std::mem::take(&mut graph.intern),
            members:std::mem::take(&mut graph.members),
            changes:std::mem::replace(&mut graph.changes,crate::change_batch::ChangeBatch::new(0)),
            epoch:graph.epoch,input,installed:None};
        (rows,subscriptions)
    }
    pub fn install(&mut self) {
        self.installed=Some(RowOwner {cells:&mut self.cells,intern:&mut self.intern,members:&mut self.members,
            changes:&mut self.changes,epoch:self.epoch}.install(self.input.groups()));
    }
    pub fn storage_bytes(&self)->usize {
        // Two tasks share the moved row headers; no binding or fields are copied.
        // Arc counters and both owner boxes are included once for this region.
        std::mem::size_of::<Self>()+std::mem::size_of::<Subscriptions>()+std::mem::size_of::<Input>()
            +2*std::mem::size_of::<usize>()+self.input.groups.capacity()*std::mem::size_of::<OwnedGroup>()
            +self.input.rows.capacity()*std::mem::size_of::<Born>()
            +self.installed.as_ref().map_or(0,Registration::storage_bytes)
    }
    pub fn restore(self,graph:&mut Graph)->Registration {
        assert!(graph.cells.is_empty() && graph.members.is_empty(),"no source access before structure completion");
        graph.cells=self.cells;graph.intern=self.intern;graph.members=self.members;graph.changes=self.changes;
        self.installed.expect("completed constructor owner")
    }
}
impl Subscriptions {
    pub fn install(&mut self) {
        subscribe_rows(&mut self.uses,&mut self.dependencies,&mut self.metrics,&self.parents,&self.columns,self.input.groups());
    }
    pub fn restore(self,graph:&mut Graph) {
        assert!(graph.uses.is_empty() && graph.dependencies.is_empty());
        graph.uses=self.uses;graph.dependencies=self.dependencies;graph.maintenance=self.metrics;graph.parents=self.parents;
    }
}
struct RowOwner<'a> {
    cells:&'a mut arena::Cells,intern:&'a mut HashMap<u64,crate::tiny_set::TinySet<FactRef>>,
    members:&'a mut [TableRows<u64>],changes:&'a mut crate::change_batch::ChangeBatch,epoch:u64,
}
impl RowOwner<'_> {
    fn install<'a>(self,groups:impl Iterator<Item=Group<'a>>)->Registration {
        let Self {cells,intern,members,changes,epoch}=self;
        let installed = groups.map(|group| {
            let mut publication = Publication::default();
            let facts = &mut cells.get_mut(&group.cell).expect("public constructor prefix").facts;
            for row in group.rows {
                let f = FactRef {cell:group.cell, op:row.operation as u32};
                assert!(facts.insert(f.op, FactState {
                    owned:false, local_union_owned:false,
                    #[cfg(feature="receipt-slots")] port_slot:0,
                    decoded:Some((row.table,row.fields.clone())), entry:None,
                    hidden:false, epoch, born:epoch, hash:row.hash,
                }).is_none(), "fresh constructor operation");
                intern.entry(row.hash).or_default().insert(f);
                members[row.table].insert(f.ordered_id());
                let activate = changes.prepare_new_row(row.table, Dependency::Fact(f));
                if let Some((_,count,_)) = publication.tables.iter_mut().find(|r|r.0==row.table) {
                    *count += 1;
                } else { publication.tables.push((row.table,1,activate)); }
            }
            Installed {cell:group.cell,first:group.first,end:group.end,publication}
        }).collect();
        Registration {installed,next:0}
    }
}
fn subscribe_rows<'a>(uses:&mut HashMap<u64,UseSet>,
    dependencies:&mut HashMap<Dependency,smallvec::SmallVec<[u64;3]>>,
    metrics:&mut maintenance::Metrics,parents:&Parents,columns:&[Option<Vec<usize>>],
    groups:impl Iterator<Item=Group<'a>>) {
    for group in groups {for row in group.rows {
        // The same typed footprint and sealed canonical fields used by Graph.
        let columns=columns[row.table].as_ref().expect("typed constructor footprint");
        maintenance::subscribe_canonical_constructor(uses,dependencies,metrics,parents,
            Dependency::Fact(FactRef {cell:group.cell,op:row.operation as u32}),&row.fields,columns);
    }}
}
impl Registration {
    pub fn storage_bytes(&self) -> usize {
        let mut bytes=self.installed.capacity()*std::mem::size_of::<Installed>();
        for installed in &self.installed {
            if installed.publication.tables.spilled() {
                bytes+=installed.publication.tables.capacity()*std::mem::size_of::<(usize,u64,bool)>();
            }
        }
        bytes
    }
    pub fn take(&mut self,cell:u32)->Publication {
        let installed=&mut self.installed[self.next];self.next+=1;
        assert_eq!(installed.cell,cell,"source-ordered constructor acceptance");
        std::mem::take(&mut installed.publication)
    }
    pub fn finish(self, graph: &mut Graph) {
        for installed in self.installed {
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
            if activate {self.changes.activate_prepared_table(table);}
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
            done.push(Completed {done:job.unwrap().run(g.parents.reader(),&mut effects.writer()),effects});
        }
        (g,done)
    }
    #[test]
    fn actual_indexes_and_subscriptions_keep_only_the_source_adopted_prefix() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(4).build().unwrap();
        for stop in [0,1,3,8] {
            let (mut g,done)=prepared();let (mut expected,reference)=prepared();
            let groups:Vec<_>=done.iter().map(|d|Group {cell:d.done.cell,
                first:g.cells[&d.done.cell].completed_prefix,end:d.done.piece.end,rows:&d.done.piece.rows}).collect();
            let pointers:Vec<_>=groups.iter().flat_map(|group|group.rows.iter().map(move |r|
                (FactRef {cell:group.cell,op:r.operation as u32},r.fields.as_ptr()))).collect();
            let row_owner=RowOwner {cells:&mut g.cells,intern:&mut g.intern,members:&mut g.members,
                changes:&mut g.changes,epoch:g.epoch};
            let mut registration=pool.install(||rayon::join(||row_owner.install(groups.iter().copied()),
                ||subscribe_rows(&mut g.uses,&mut g.dependencies,&mut g.maintenance,&g.parents,
                    &g.program.repair_ports.key_eq_columns,groups.iter().copied())).0);drop(groups);
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
            registration.finish(&mut g);
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            assert_eq!(g.query_versions,expected.query_versions);
            assert_eq!((g.changes.events,g.changes.distinct_events),(expected.changes.events,expected.changes.distinct_events));
            assert_eq!(g.dependencies,expected.dependencies);
            let uses=|g:&Graph|g.uses.iter().map(|(k,v)|(*k,v.iter().copied().collect::<BTreeSet<_>>())).collect::<BTreeMap<_,_>>();
            assert_eq!(uses(&g),uses(&expected));
            assert_eq!(g.stats.constructor_registry_adopted,2*stop as u64);
            assert_eq!(g.stats.constructor_registry_discarded,2*(8-stop) as u64);
            assert_eq!(g.maintenance_report()["stats"]["live_reverse_edges"],expected.maintenance_report()["stats"]["live_reverse_edges"]);
            for graph in [&mut g,&mut expected] {graph.union(100,101).unwrap();graph.repair().unwrap();}
            assert_eq!(g.export().unwrap(),expected.export().unwrap(),"later repair must not see invalidated rows");
        }
    }
}
