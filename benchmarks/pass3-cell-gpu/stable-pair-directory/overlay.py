import shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent

def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)

def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {','struct Store {stable_dirs:StableDirs,')
    s=change(s,'let s=Store{','let s=Store{stable_dirs:StableDirs::default(),')
    s=change(s,'"sparse_pairs":','"stable_dirs":s.stable_dirs.stats,"sparse_pairs":')
    s=change(s,'            if let Some(frame)=self.update_frame(g,t,version)?{return Ok(frame);}','''            let transition=if self.stable_dirs.mode==3 && self.stable_dirs.stores.keys().any(|(owner,_)|*owner==t){
                self.frames.get(&t).zip(self.frame_changes.get(&t))
                    .filter(|(_,pending)|pending.generation==version)
                    .map(|(f,pending)|(f.generation,pending.changed.iter().copied().collect::<Vec<_>>()))
            }else{None};
            if let Some(frame)=self.update_frame(g,t,version)?{
                if let Some((from,addresses))=transition{self.stable_dirs.frame_transition(t,from,version,&addresses);}
                return Ok(frame);
            }''')
    p.write_text(s+'\ninclude!("stable_dirs.rs");\n');shutil.copyfile(HERE/'dirs.rs',src/'stable_dirs.rs')
    p=src/'incremental_raw.rs';s=p.read_text()
    anchor='        if self.sparse_pairs.mode>0 && cut>0'
    s=change(s,anchor,'''        if self.stable_dirs.mode>0 && cut>0 && self.stable_pair(c,steps,cut,raw)?{return Ok(());}
'''+anchor)
    marker='        for (table, changes) in graph.changes.tables() {'
    s=change(s,marker,marker+'''
            if s.stable_dirs.mode==2{
                s.stable_dirs.note(table,graph.query_versions[table],changes.len(),changes.keys().copied());
            }''');p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if let Some(v)=req.get("stable_dirs"){ordinary_witness::enable_stable_dirs(v.clone())?;}
'''+a))
