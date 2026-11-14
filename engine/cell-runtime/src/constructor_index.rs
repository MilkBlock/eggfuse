//! The canonical constructor directory is partitioned by its authoritative
//! table. A worker can own selected tables without hiding unrelated indexes.
//! A missing partition is a live lease, never evidence of key absence.
use super::*;

#[cfg(feature="sparse-cells")]
pub(super) type Bucket=crate::tiny_set::TinySet<FactRef>;
#[cfg(not(feature="sparse-cells"))]
pub(super) type Bucket=BTreeSet<FactRef>;
pub(super) type Table=HashMap<u64,Bucket>;

enum Slot {
    Attached(Table),
    #[cfg(feature="sparse-cells")]
    Leased,
    #[cfg(feature="sparse-cells")]
    Shared(std::sync::Arc<std::sync::RwLock<Table>>),
}
#[cfg(feature="sparse-cells")]
pub(super) enum Lease {Exclusive(Table),Shared(std::sync::Arc<std::sync::RwLock<Table>>)}
#[cfg(feature="sparse-cells")]
impl Lease {
    pub fn insert(&mut self,hash:u64,fact:FactRef) {
        match self {
            Self::Exclusive(table)=>{table.entry(hash).or_default().insert(fact);},
            Self::Shared(table)=>{table.write().expect("constructor index writer").entry(hash).or_default().insert(fact);},
        }
    }
}
#[derive(Default)]
pub(super) struct Index {tables:Vec<Slot>}
impl Index {
    pub fn new(tables:usize)->Self {Self {tables:(0..tables).map(|_|Slot::Attached(Table::default())).collect()}}
    fn table(&self,table:usize)->&Table {match &self.tables[table] {Slot::Attached(t)=>t,#[cfg(feature="sparse-cells")] _=>panic!("constructor table is owned by a worker")}}
    fn table_mut(&mut self,table:usize)->&mut Table {match &mut self.tables[table] {Slot::Attached(t)=>t,#[cfg(feature="sparse-cells")] _=>panic!("constructor table is owned by a worker")}}
    pub fn require_available(&self,table:usize) {let _=self.table(table);}
    pub fn get(&self,table:usize,hash:&u64)->Option<&Bucket> {self.table(table).get(hash)}
    pub fn get_mut(&mut self,table:usize,hash:&u64)->Option<&mut Bucket> {self.table_mut(table).get_mut(hash)}
    pub fn entry(&mut self,table:usize,hash:u64)->std::collections::hash_map::Entry<'_,u64,Bucket> {self.table_mut(table).entry(hash)}
    pub fn remove(&mut self,table:usize,hash:&u64)->Option<Bucket> {self.table_mut(table).remove(hash)}
    pub fn contains_key(&self,table:usize,hash:&u64)->bool {self.table(table).contains_key(hash)}
    fn attached(&self)->impl Iterator<Item=&Table> {self.tables.iter().filter_map(|s|match s {Slot::Attached(t)=>Some(t),#[cfg(feature="sparse-cells")] _=>None})}
    pub fn values(&self)->impl Iterator<Item=&Bucket> {self.attached().flat_map(|t|t.values())}
    pub fn len(&self)->usize {self.attached().map(|t|t.len()).sum()}
    pub fn capacity(&self)->usize {self.attached().map(|t|t.capacity()).sum()}
    pub fn header_bytes(&self)->usize {self.tables.capacity()*std::mem::size_of::<Slot>()}
    pub fn shrink_to_fit(&mut self) {for slot in &mut self.tables {match slot {Slot::Attached(t)=>t.shrink_to_fit(),#[cfg(feature="sparse-cells")] _=>()}}}
    #[cfg(feature="sparse-cells")]
    pub fn leased(&self,table:usize)->bool {!matches!(self.tables[table],Slot::Attached(_))}
    #[cfg(feature="sparse-cells")]
    pub fn take(&mut self,table:usize,readable:bool)->Lease {
        let Slot::Attached(index)=std::mem::replace(&mut self.tables[table],Slot::Leased) else {panic!("one owner per constructor table")};
        if readable {
            let index=std::sync::Arc::new(std::sync::RwLock::new(index));
            self.tables[table]=Slot::Shared(index.clone());Lease::Shared(index)
        } else {Lease::Exclusive(index)}
    }
    #[cfg(feature="sparse-cells")]
    pub fn shared_bucket<R>(&self,table:usize,hash:u64,read:impl FnOnce(Option<&Bucket>)->R)->Option<R> {
        let Slot::Shared(index)=&self.tables[table] else {return None;};
        let index=index.read().expect("constructor index reader");
        Some(read(index.get(&hash)))
    }
    #[cfg(feature="sparse-cells")]
    pub fn restore(&mut self,table:usize,index:Lease) {
        let slot=std::mem::replace(&mut self.tables[table],Slot::Leased);
        let index=match (slot,index) {
            (Slot::Leased,Lease::Exclusive(index))=>index,
            (Slot::Shared(source),Lease::Shared(owner))=> {
                assert!(std::sync::Arc::ptr_eq(&source,&owner));drop(source);
                std::sync::Arc::try_unwrap(owner).unwrap_or_else(|_|panic!("return every index reader"))
                    .into_inner().expect("returned constructor index")
            },
            _=>panic!("return the original table owner once"),
        };
        self.tables[table]=Slot::Attached(index);
    }
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
            let owner=index.take(0,false);assert!(index.leased(0));
            assert!(std::panic::catch_unwind(||index.get(0,&0)).is_err(),"lease is not absence");
            index.entry(1,0).or_default().insert(a);
            index.restore(0,owner);
            assert_eq!(index.get(1,&0).unwrap().first(),Some(&a));
        }
    }
    #[cfg(feature="sparse-cells")]
    #[test]
    fn shared_lease_has_one_index_and_ordinary_access_still_requires_the_owner() {
        let mut index=Index::new(1);
        let a=FactRef {cell:1,op:0};let b=FactRef {cell:2,op:0};
        index.entry(0,7).or_default().insert(a);
        let mut owner=index.take(0,true);
        assert!(std::panic::catch_unwind(||index.get(0,&7)).is_err());
        assert_eq!(index.shared_bucket(0,7,|b|b.unwrap().first().copied()),Some(Some(a)));
        owner.insert(7,b);
        assert_eq!(index.shared_bucket(0,7,|b|b.unwrap().iter().copied().collect::<Vec<_>>()),Some(vec![a,b]));
        index.restore(0,owner);
        assert_eq!(index.get(0,&7).unwrap().len(),2);
    }
}
