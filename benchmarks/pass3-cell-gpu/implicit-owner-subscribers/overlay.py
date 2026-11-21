"""Keep all reverse-edge readers on the same logical view when a single physical address is encoded."""
from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def one(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    src=crate/'src';p=src/'graph.rs';s=p.read_text()
    s=one(s,'pub struct Graph {','pub struct Graph {\n    owner_directory:OwnerDirectory,')
    s=one(s,'        let mut g = Self {','        let mut g = Self {owner_directory:Default::default(),')
    s=one(s,'    fn bound_uses(&self, bound: &[Option<Value>]) -> Option<&UseSet> {','    fn bound_uses(&self, bound: &[Option<Value>]) -> Option<u64> {')
    i=s.index('        #[cfg(feature = "sparse-cells")]\n        static EMPTY: UseSet');j=s.index('        bound\n',i);s=s[:i]+s[j:]
    s=one(s,'Some(self.uses.get(&root(&self.parents, *id)).unwrap_or(&EMPTY))','Some(root(&self.parents,*id))')
    s=one(s,'.min_by_key(|uses| uses.len())','.min_by_key(|id|self.reverse_len(*id))')
    s=one(s,'.map_or(all, |uses| all.min(uses.len()))','.map_or(all,|id|all.min(self.reverse_len(id)))')
    s=one(s,'if let Some(uses) = self.bound_uses(bound) {','if let Some(class) = self.bound_uses(bound) {')
    s=one(s,'if uses.len() < self.witness_count(table) {','if self.reverse_len(class)<self.witness_count(table) {')
    s=one(s,'let rows: Vec<_> = uses\n                    .iter()\n                    .copied()','let rows: Vec<_> = self.reverse_members(class)')
    a='''            if !refs.contains(&id)
                && let Some(uses) = self.uses.get_mut(&id)
            {
                maintenance::remove(uses, &mut self.maintenance, d);
            }'''
    s=one(s,a,'''            if !refs.contains(&id){
                if self.owner_directory.mode!=0{self.reverse_remove(id,d);}
                else if let Some(uses)=self.uses.get_mut(&id){maintenance::remove(uses,&mut self.maintenance,d);}
            }''')
    anchor='''        for &id in &refs {
            maintenance::insert(&mut self.uses, &mut self.maintenance, id, d);
        }'''
    s=one(s,anchor,'''        for &id in &refs {
            if self.owner_directory.mode!=0{self.reverse_insert(id,d);}
            else{maintenance::insert(&mut self.uses,&mut self.maintenance,id,d);}
        }''')
    a='    fn subscribe_edges(&mut self, d: Dependency, values: &[Value]) {'
    start=s.index(a)
    s=s[:start]+s[start:].replace(a,a+'\n        if self.owner_directory.mode>=6{return self.subscribe_by_difference(d,values)}',1)
    a='        self.parents.insert(hi, lo);'
    s=one(s,a,'        let derived=(self.derived_member(hi),self.derived_member(lo));\n'+a)
    a='''        let mut affected = self.uses.remove(&hi).unwrap_or_default();'''
    s=one(s,a,'        if self.owner_directory.mode!=0 {self.reverse_union(hi,lo,derived);}else {\n'+a)
    a='        self.maintenance.live_reverse_edges -= coalesced;';s=one(s,a,a+'\n        }')
    a='''    fn mark_affected(&mut self, affected: &UseSet, from: u64, to: u64) {
        for d in affected.iter() {'''
    s=one(s,a,'''    fn mark_affected(&mut self,affected:&UseSet,from:u64,to:u64){
        self.mark_displaced_members(affected.iter().copied(),from,to)
    }
    fn mark_displaced_members(&mut self,affected:impl Iterator<Item=Dependency>,from:u64,to:u64){
        for row in affected {let d=&row;''')
    p.write_text(s+'\ninclude!("implicit_owner_subscribers.rs");\n');copyfile(HERE/'reverse.rs',src/'implicit_owner_subscribers.rs')
    p=src/'maintenance.rs';a='let observed = self.uses.values().map(|s| s.len() as u64).sum::<u64>();'
    p.write_text(one(p.read_text(),a,'let observed = self.uses.values().map(|s|s.len() as u64).sum::<u64>() + (self.owner_directory.masked+self.owner_directory.singles.len()+self.derived_census().0) as u64;'))
    for name,old,new in [
        ('pure_effects','for &dep in self.graph.uses.get(&id).into_iter().flat_map(|s| s.iter())','for dep in self.graph.reverse_members(id)'),
        ('port_completion','for &dependency in self.uses.get(&root).into_iter().flat_map(|s| s.iter())','for dependency in self.reverse_members(root)'),
        ('cell_ownership','self.uses.get(&id).map_or(0, UseSet::len)','self.reverse_len(id)'),
        ('cell_ownership','for &d in self.uses.get(&id).into_iter().flat_map(|s| s.iter())','for d in self.reverse_members(id)'),
        ('unique_port_publication','self.uses.get(&from).is_some_and(|s| !s.is_empty())','self.owner_directory.compact(from)||self.uses.get(&from).is_some_and(|s| !s.is_empty())')
    ]:
        p=src/(name+'.rs');p.write_text(one(p.read_text(),old,new))
    p=crate/'examples/joint_witness_session.rs';s=p.read_text()
    anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    s=one(s,anchor,'''        if let Some(m)=req["owner_directory"].as_u64(){runtime.graph.configure_owner_directory(m,audit)?;}
'''+anchor)
    anchor='        report["header_view"]='
    s=one(s,anchor,'''        if req.get("owner_directory").is_some(){report["owner_directory"]=runtime.graph.owner_directory_report();}
'''+anchor);p.write_text(s)
