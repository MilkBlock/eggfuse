//! The canonical constructor directory is partitioned by its authoritative
//! table. A worker can own selected tables without hiding unrelated indexes.
//! A missing partition is a live lease, never evidence of key absence.
use super::*;

#[cfg(feature="sparse-cells")]
pub(super) type Bucket=crate::tiny_set::TinySet<FactRef>;
#[cfg(not(feature="sparse-cells"))]
pub(super) type Bucket=BTreeSet<FactRef>;
pub(super) type Table=HashMap<u64,Bucket>;

#[derive(Default)]
pub(super) struct Index {tables:Vec<Option<Table>>}
impl Index {
    pub fn new(tables:usize)->Self {Self {tables:(0..tables).map(|_|Some(Table::default())).collect()}}
    fn table(&self,table:usize)->&Table {self.tables[table].as_ref().expect("constructor table is owned by a worker")}
    fn table_mut(&mut self,table:usize)->&mut Table {self.tables[table].as_mut().expect("constructor table is owned by a worker")}
    pub fn require_available(&self,table:usize) {let _=self.table(table);}
    pub fn get(&self,table:usize,hash:&u64)->Option<&Bucket> {self.table(table).get(hash)}
    pub fn get_mut(&mut self,table:usize,hash:&u64)->Option<&mut Bucket> {self.table_mut(table).get_mut(hash)}
    pub fn entry(&mut self,table:usize,hash:u64)->std::collections::hash_map::Entry<'_,u64,Bucket> {self.table_mut(table).entry(hash)}
    pub fn remove(&mut self,table:usize,hash:&u64)->Option<Bucket> {self.table_mut(table).remove(hash)}
    pub fn contains_key(&self,table:usize,hash:&u64)->bool {self.table(table).contains_key(hash)}
    pub fn values(&self)->impl Iterator<Item=&Bucket> {self.tables.iter().flatten().flat_map(|t|t.values())}
    pub fn len(&self)->usize {self.tables.iter().flatten().map(|t|t.len()).sum()}
    pub fn capacity(&self)->usize {self.tables.iter().flatten().map(|t|t.capacity()).sum()}
    pub fn header_bytes(&self)->usize {self.tables.capacity()*std::mem::size_of::<Option<Table>>()}
    pub fn shrink_to_fit(&mut self) {for t in self.tables.iter_mut().flatten() {t.shrink_to_fit();}}
    #[cfg(feature="sparse-cells")]
    pub fn leased(&self,table:usize)->bool {self.tables[table].is_none()}
    #[cfg(feature="sparse-cells")]
    pub fn take(&mut self,table:usize)->Table {self.tables[table].take().expect("one owner per constructor table")}
    #[cfg(feature="sparse-cells")]
    pub fn restore(&mut self,table:usize,index:Table) {assert!(self.tables[table].replace(index).is_none(),"return the original table owner once");}
    #[cfg(test)]
    pub fn is_empty(&self)->bool {self.len()==0}
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn equal_hashes_preserve_order_and_retirement_in_each_table() {
        let mut index=Index::new(2);
        let a=FactRef {cell:1,op:0};let b=FactRef {cell:2,op:0};
        index.entry(0,0).or_default().insert(b);index.entry(0,0).or_default().insert(a);
        index.entry(1,0).or_default().insert(b);
        assert_eq!(index.get(0,&0).unwrap().iter().copied().collect::<Vec<_>>(),[a,b]);
        index.remove(1,&0);assert_eq!(index.get(0,&0).unwrap().len(),2);
        #[cfg(feature="sparse-cells")]
        {
            let owner=index.take(0);assert!(index.leased(0));
            assert!(std::panic::catch_unwind(||index.get(0,&0)).is_err(),"lease is not absence");
            index.entry(1,0).or_default().insert(a);
            index.restore(0,owner);
            assert_eq!(index.get(1,&0).unwrap().first(),Some(&a));
        }
    }
}
