//! Adopt proven terminal constructor rows in the existing Unit owner region.
//! The original Cell storage, indexes and reverse incidences have disjoint
//! owners. Source order opens only the prepared publication fragments; it does
//! not repeat row installation. An unadopted suffix is invalidated on error.
use super::*;

#[derive(Default)]
pub(crate) struct Publication {
    tables: smallvec::SmallVec<[(usize, u64, bool); 2]>,
}
pub(super) struct Group<'a> {
    pub cell: u32,
    pub first: usize,
    pub end: usize,
    pub rows: &'a Rows,
}
struct Installed {
    cell: u32,
    first: usize,
    end: usize,
    publication: Publication,
}
pub(super) struct Registration { installed: Vec<Installed>, next:usize }

pub(super) struct Owner<'a> {
    pub cells: &'a mut arena::Cells,
    pub intern: &'a mut HashMap<u64, crate::tiny_set::TinySet<FactRef>>,
    pub members: &'a mut [TableRows<u64>],
    pub changes: &'a mut crate::change_batch::ChangeBatch,
    pub uses: &'a mut HashMap<u64, UseSet>,
    pub dependencies: &'a mut HashMap<Dependency, smallvec::SmallVec<[u64; 3]>>,
    pub metrics: &'a mut maintenance::Metrics,
    pub parents: &'a Parents,
    pub columns: &'a [Option<Vec<usize>>],
    pub epoch: u64,
}
impl Owner<'_> {
    pub fn install(self, groups: &[Group<'_>], inline: bool) -> Registration {
        let Self { cells, intern, members, changes, uses, dependencies,
            metrics, parents, columns, epoch } = self;
        let rows = || groups.iter().map(|group| {
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
        let subscriptions = || {
            for group in groups { for row in group.rows {
                // The same typed footprint and sealed canonical fields used
                // by Graph::subscribe. No union or mutable read intervenes.
                let columns = columns[row.table].as_ref().expect("typed constructor footprint");
                maintenance::subscribe_canonical_constructor(uses,dependencies,metrics,parents,
                    Dependency::Fact(FactRef {cell:group.cell,op:row.operation as u32}),&row.fields,columns);
            }}
        };
        let installed = if inline { let mut rows=rows;let mut subscriptions=subscriptions;
            let result=rows();subscriptions();result
        } else { rayon::join(rows,subscriptions).0 };
        Registration {installed,next:0}
    }
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
    pub(super) fn publish_registered_births(&mut self, publication: Publication, count: usize) {
        self.stats.constructor_registry_fragments+=publication.tables.len() as u64;
        for (table,rows,activate) in publication.tables {
            if activate {self.changes.activate_prepared_table(table);}
            self.changes.finish_new_rows(table,rows);
            self.query_versions[table]+=rows;
        }
        self.stats.logical_facts_created+=count as u64;
        self.stats.constructor_registry_adopted+=count as u64;
        self.changed |= count!=0;
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
            let owner=Owner {cells:&mut g.cells,intern:&mut g.intern,members:&mut g.members,changes:&mut g.changes,
                uses:&mut g.uses,dependencies:&mut g.dependencies,metrics:&mut g.maintenance,
                parents:&g.parents,columns:&g.program.repair_ports.key_eq_columns,epoch:g.epoch};
            let mut registration=pool.install(||owner.install(&groups,false));drop(groups);
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
