//! Borrow existing membership after preparing only the typed query's columns.
//! No row/index clone or lazy cache mutation is performed on worker threads.
use super::*;
use smallvec::SmallVec;
pub(crate) struct Read<'a> {
    tables: SmallVec<[(usize, TableRead<'a>); 4]>,
    bits: u32,
}
struct TableRead<'a> {
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
    pub fn fingerprint(&self, value: &Value) -> u64 { fingerprint(value, self.bits) }
    pub fn domain(&self, table: usize, selectors: SmallVec<[(usize,u64);4]>) -> Domain<'a> {
        let read = &self.tables.iter().find(|(t,_)| *t == table).expect("compiled read table").1;
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
    pub(crate) fn read_columns<'a>(&'a mut self, graph: &Graph, layout: &[(usize,Vec<usize>)]) -> Result<Read<'a>> {
        for (table, columns) in layout { self.ensure_selected(graph, *table, columns.iter().copied())?; }
        let tables = layout.iter().map(|(table, columns)| {
            let index = &self.tables[table];
            (*table, TableRead { keys: &index.keys,
                columns: columns.iter().map(|&c| (c, index.column(c))).collect() })
        }).collect();
        Ok(Read { tables, bits: self.bits })
    }
}
