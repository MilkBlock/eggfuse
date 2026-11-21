from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def rep(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    src=crate/'src';path=src/'graph.rs';s=path.read_text()
    s=rep(s,'pub struct Graph {','pub struct Graph {\n    repair_reuse:RepairReuse,')
    s=rep(s,'        let mut g = Self {','        let mut g = Self {repair_reuse:Default::default(),')
    old='''            self.maintenance.reverse_merge_inserts += kept as u64;
            affected.extend(self.uses.get(&lo).into_iter().flatten().copied());
            self.uses.insert(lo, affected);'''
    s=rep(s,old,'''            self.repair_reuse.unions+=1;
            self.repair_reuse.displaced_edges+=displaced as u64;
            self.repair_reuse.survivor_edges+=kept as u64;
            if self.repair_reuse.mode & 1 !=0 {
                let expected=self.repair_reuse.audit.then(|| {
                    let mut combined=affected.clone();
                    if let Some(b)=self.uses.get(&lo){combined.extend(b.iter().copied());}
                    combined
                });
                let survivor=self.uses.entry(lo).or_default();
                if survivor.len()<affected.len(){std::mem::swap(survivor,&mut affected);}
                self.repair_reuse.merge_insertions+=affected.len() as u64;
                self.maintenance.reverse_merge_inserts+=affected.len() as u64;
                survivor.extend(affected);
                if let Some(expected)=expected {assert_eq!(&expected,survivor);self.repair_reuse.reverse_audits+=1;}
            }else{
                self.repair_reuse.merge_insertions+=kept as u64;
'''+old+'''
            }''')
    a=s.index('            if let Dependency::Function(i) = d {',s.index('    fn mark_affected('))
    b=s.index('            {\n                self.dirty.insert(*d);',a)
    s=s[:a]+'''            let deferred=self.repair_reuse.mode&32!=0 && !retained && self.defer_displaced_fact(*d);
            if !deferred && (self.repair_reuse.mode & 2 ==0 || retained || !self.update_displaced_fields(*d,table,from,to)){
'''+s[a:b]+'            }\n'+s[b:]
    old='''        if h.is_some() && let Some(bucket) = self.intern.get_mut(&old) {'''
    s=rep(s,old,'''        let keep_index=self.repair_reuse.mode & 4 !=0 && h==Some(old) && found.is_none()
            && self.intern.get(&old).is_some_and(|bucket|bucket.contains(&f));
        let retire_once=self.repair_reuse.mode & 4 !=0 && h.is_some() && found.is_some();
        self.repair_reuse.fact_kept_index+=u64::from(keep_index);
        self.repair_reuse.retired_index_once+=u64::from(retire_once);
        if !keep_index && !retire_once && h.is_some() && let Some(bucket) = self.intern.get_mut(&old) {''')
    s=rep(s,'            if let Some(h) = h { self.intern.entry(h).or_default().insert(f); }','            if !keep_index && let Some(h) = h { self.intern.entry(h).or_default().insert(f); }')
    old='''            self.retire(f)?;
        } else {
            self.end_local_ownership'''
    s=rep(s,old,'''            if retire_once {
                if self.repair_reuse.audit{
                    let existing=self.fact(f)?.ok_or("missing repair-retirement source")?;
                    assert_eq!((existing.table,existing.witness,existing.epoch,&existing.values),(r.table,r.witness,r.epoch,&r.values));
                    self.repair_reuse.index_audits+=1;
                }
                self.repair_reuse.retirement_row_reads_saved+=1;
                self.retire_in_table(f,r.table)?;
            }else{self.retire(f)?;}
        } else {
            self.end_local_ownership''')
    a=s.index('    fn retire(&mut self, f: FactRef) -> Result<()> {')
    b=s.index('    #[cfg(feature = "sparse-cells")]',s.index('        Ok(())\n    }',a))
    before=s[a:b];body=before.split('        if let Some(r) = self.fact(f)? {\n',1)[1].split('        }\n        Ok(())\n    }',1)[0]
    s=s[:a]+'''    fn retire(&mut self,f:FactRef)->Result<()>{
        if let Some(row)=self.fact(f)?{self.retire_in_table(f,row.table)?;}
        Ok(())
    }
    fn retire_in_table(&mut self,f:FactRef,table:usize)->Result<()>{
'''+body.replace('r.table','table')+'        Ok(())\n    }\n'+s[b:]
    a='''                    if !compressed && self.function_keys[row.table].get(oldkey) == Some(&i) {'''
    s=rep(s,a,'''                    let keep_index=self.repair_reuse.mode & 4 !=0 && !compressed && self.units.counts[row.table]==0
                        && *oldkey==key && self.function_keys[row.table].get(&key)==Some(&i);
                    self.repair_reuse.function_kept_index+=u64::from(keep_index);
                    if !keep_index && !compressed && self.function_keys[row.table].get(oldkey) == Some(&i) {''')
    s=rep(s,'                    if let Some(j) = self.function_index(row.table, &key) {','                    if !keep_index && let Some(j) = self.function_index(row.table, &key) {')
    s=rep(s,'                    self.function_keys[row.table].insert(&key, i);','                    if !keep_index{self.function_keys[row.table].insert(&key, i);}')
    s=rep(s,'                    self.function_keys[row.table].insert(key, i);','                    if !keep_index{self.function_keys[row.table].insert(key, i);}')
    s=rep(s,'                    self.functions[i].key = key.clone();','                    if !keep_index{self.functions[i].key=key.clone();}')
    s=rep(s,'} else { self.subscribe(r.table, d, &r.values); }','} else if !self.adopt_canonical_subscription(r.table,d,&r.values) { self.subscribe(r.table, d, &r.values); }')
    s=rep(s,'                    self.subscribe(row.table, d, &row.values);\n                    self.changes.touch(row.table, d);',
          '                    if compressed || self.units.counts[row.table]!=0 || !self.adopt_canonical_subscription(row.table,d,&row.values){self.subscribe(row.table,d,&row.values); }\n                    self.changes.touch(row.table,d);')
    start=s.index('    fn repair_selected(')
    a='                    let Some(r) = self.fact(f)? else { continue };'
    s=s[:start]+rep(s[start:],a,'                    if self.repair_reuse.mode&32!=0{self.consume_displaced_fact(f);}'+'\n'+a)
    a='    fn retire_in_table(&mut self,f:FactRef,table:usize)->Result<()>{'
    s=rep(s,a,a+'\n        if self.repair_reuse.mode&32!=0{self.repair_reuse.pending.remove(&f);}')
    path.write_text(s+'\ninclude!("repair_reuse.rs");\n');copyfile(HERE/'repair.rs',src/'repair_reuse.rs')
    p=crate/'examples/joint_witness_session.rs';s=p.read_text()
    marker='        let initial_cells = runtime.graph.stats.cells_created;'
    s=rep(s,marker,'''        if let Some(n)=req["ordered_repair"].as_u64(){runtime.graph.configure_repair_reuse(n,audit)?;}
'''+marker)
    s=rep(s,'        report["header_view"]=', '        if req.get("ordered_repair").is_some(){report["ordered_repair"]=runtime.graph.repair_reuse_report();}\n        report["header_view"]=')
    p.write_text(s)
