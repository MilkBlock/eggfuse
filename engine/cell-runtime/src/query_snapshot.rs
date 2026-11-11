//! Borrow existing membership after preparing only the typed query's columns.
//! No row/index clone or lazy cache mutation is performed on worker threads.
use super::*;
use smallvec::SmallVec;
pub(crate) struct Read<'a> {
    tables: SmallVec<[(usize, TableRead<'a>); 4]>,
    entry_keys: Option<&'a HashMap<Dependency, SmallVec<[u64; 4]>>>,
    bits: u32,
}
pub(crate) struct TableRead<'a> {
    keys: &'a HashMap<Dependency, SmallVec<[u64; 4]>>,
    columns: SmallVec<[(usize, &'a HashMap<u64, Bucket>); 4]>,
}
pub(crate) struct Domain<'a> {
    rows: Option<&'a crate::tiny_set::TinySet<Dependency>>,
    keys: &'a HashMap<Dependency, SmallVec<[u64; 4]>>,
    selectors: SmallVec<[(usize, u64); 4]>,
    examined: std::cell::Cell<u64>,
}
impl Domain<'_> {
    pub fn iter(&self) -> impl Iterator<Item = Dependency> + '_ {
        self.rows.into_iter().flat_map(|rows| rows.iter()).copied().inspect(|_| self.examined.set(self.examined.get()+1)).filter(|w|
            self.selectors.len() == 1 || self.selectors.iter().all(|(c,k)| self.keys[w][*c] == *k))
    }
    pub fn take_examined(&self) -> u64 { self.examined.replace(0) }
}
impl<'a> Read<'a> {
    pub fn entry_hashes(&self, witness: Dependency) -> Option<&[u64]> {
        self.entry_keys?.get(&witness).map(|v| v.as_slice())
    }
    pub fn fingerprint(&self, value: &Value) -> u64 { fingerprint(value, self.bits) }
    pub fn domain(&self, table: usize, selectors: SmallVec<[(usize,u64);4]>) -> Domain<'a> {
        let read = &self.tables.iter().find(|(t,_)| *t == table).expect("compiled read table").1;
        read.domain(selectors)
    }
}
impl<'a> TableRead<'a> {
    #[cfg(feature = "parallel-publication")]
    pub fn hashes(&self, witness: Dependency) -> &[u64] { &self.keys[&witness] }
    pub fn domain(&self, selectors: SmallVec<[(usize,u64);4]>) -> Domain<'a> {
        let read = self;
        let mut best: Option<&Bucket> = None;
        for &(column, hash) in &selectors {
            let map = read.columns.iter().find(|(c,_)| *c == column).expect("compiled read column").1;
            let Some(bucket) = map.get(&hash) else {
                return Domain { rows: None, keys: read.keys, selectors, examined:Default::default() };
            };
            if best.is_none_or(|old| bucket.facts.len() < old.facts.len()) { best = Some(bucket); }
        }
        Domain { rows: Some(&best.expect("connected expansion").facts), keys: read.keys, selectors, examined:Default::default() }
    }
}
impl QueryIndexes {
    /// Called on the coordinator before borrowing only the finished columns.
    /// The Summary already owns a built table; no new table or row is created.
    #[cfg(feature = "parallel-publication")]
    pub(crate) fn publication_support(&self, table:usize, columns:&[usize]) -> TableRead<'_> {
        let index=&self.tables[&table];
        TableRead {keys:&index.keys,columns:columns.iter().map(|&c|(c,index.column(c))).collect()}
    }
    pub(crate) fn prepare_columns(&mut self, graph:&Graph, layout:&[(usize,Vec<usize>)]) -> Result<()> {
        for (table,columns) in layout {
            self.ensure_selected(graph,*table,columns.iter().copied())?;
            // An existing table can still have lazy, uninitialized columns.
            // Finish those on the coordinator before creating worker borrows.
            for &column in columns { self.tables[table].column(column); }
        }
        Ok(())
    }
    pub(crate) fn read_columns<'a>(&'a self, layout:&[(usize,Vec<usize>)], entry_table:usize) -> Read<'a> {
        let tables=layout.iter().map(|(table,columns)| {
            let index=&self.tables[table];
            (*table,TableRead {keys:&index.keys,columns:columns.iter().map(|&c|
                (c,index.values[c].get().expect("prepared Run column"))).collect()})
        }).collect();
        Read {tables,bits:self.bits,entry_keys:self.tables.get(&entry_table).map(|i|&i.keys)}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn run_borrows_finish_lazy_columns_of_existing_tables() {
        let mut graph=crate::query::test_projection_graph();
        graph.set_function(0,vec![Value::Int(1),Value::Int(2)],Value::Int(3)).unwrap();
        let mut index=QueryIndexes::default();
        index.ensure_selected(&graph,0,[0]).unwrap();
        assert!(index.tables[&0].values[1].get().is_none());
        index.prepare_columns(&graph,&[(0,vec![1])]).unwrap();
        assert!(index.tables[&0].values[1].get().is_some());
        let read=index.read_columns(&[(0,vec![1])],0);
        let key=read.fingerprint(&Value::Int(2));
        let domain=read.domain(0,smallvec::smallvec![(1,key)]);
        assert_eq!(domain.iter().count(),1);
        assert_eq!(index.builds,1,"preparing another column reuses the table");
    }

    #[cfg(feature = "parallel-publication")]
    #[test]
    fn publication_moves_existing_columns_and_reuses_only_empty_change_storage() {
        let mut graph=crate::query::test_projection_graph();
        graph.set_function(0,vec![Value::Int(1),Value::Int(2)],Value::Int(3)).unwrap();
        let mut index=QueryIndexes::default();
        index.track_changes=true;
        index.ensure_selected(&graph,0,[0]).unwrap();
        let row=graph.row(graph.witnesses(0)[0]).unwrap().unwrap();
        let mut task=index.take_publication(0,graph.query_versions[0]).unwrap();
        assert!(!index.tables.contains_key(&0));
        task.update(row.witness,None);
        task.update(row.witness,Some(&row));
        task.finish(graph.query_versions[0]);
        let bytes=task.buffer_bytes();assert!(bytes>0);
        index.restore_publication(task);
        assert_eq!(index.publication_buffer_bytes(),bytes);
        assert!(index.tables[&0].values[0].get().is_some());
        assert_eq!(index.changes,[(row.witness,0,u64::MAX)]);
        let task=index.take_publication(0,graph.query_versions[0]).unwrap();
        assert_eq!(task.buffer_growths(),0);
        assert_eq!(task.buffer_bytes(),bytes);
        index.restore_publication(task);
        assert_eq!(index.changes.len(),1,"scratch retains capacity, never notifications");
        // A selective update must carry its field mask through the worker's
        // moved buffer; Sieve uses it to skip unrelated Cell projections.
        index.changes.clear();
        graph.set_function(0,vec![Value::Int(1),Value::Int(2)],Value::Int(4)).unwrap();
        let row=graph.row(row.witness).unwrap().unwrap();
        let mut task=index.take_publication(0,graph.query_versions[0]).unwrap();
        task.update(row.witness,Some(&row));
        task.finish(graph.query_versions[0]);
        index.restore_publication(task);
        assert_eq!(index.changes,[(row.witness,0,super::super::column_bit(2))]);
        index.clear();assert_eq!(index.publication_buffer_bytes(),0);
    }

    #[cfg(feature = "parallel-publication")]
    #[test]
    fn publication_reads_require_repair_but_keep_unpublished_changes() {
        let mut graph=crate::query::test_projection_graph();
        graph.set_function(0,vec![Value::Int(1),Value::Int(2)],Value::Int(3)).unwrap();
        graph.repair().unwrap();
        assert!(!graph.changes.is_empty());
        assert!(graph.query_reads(&[0],&mut 0).is_none(),"next Run is not yet published");
        let witness=graph.witnesses(0)[0];
        let read=graph.publication_reads([0].into_iter()).unwrap();
        assert_eq!(read.row(witness).unwrap().unwrap().values,graph.row(witness).unwrap().unwrap().values);
        graph.enqueue_union(Value::Eq(1),Value::Eq(2)).unwrap();
        assert!(graph.publication_reads([0].into_iter()).is_none(),"pending equality forbids the borrow");
        graph.repair().unwrap();
        assert!(graph.publication_reads([0].into_iter()).is_some());
    }
}
