from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent

def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)

def install(crate):
    src=crate/'src'
    p=src/'ordinary_witness.rs'
    s=change(p.read_text(),'struct Store {','struct Store {root_domain:RootDomain,')
    s=change(s,'let s=Store{','let s=Store{root_domain:RootDomain::default(),')
    s=change(s,'"tier":s.tier.stats,','"root_domain":s.root_domain.stats,"tier":s.tier.stats,')
    s=change(s,'            s.issued_generations.clear();','''            s.root_domain.current=None;
            if s.root_domain.enabled && !s.forward.active.is_empty() && !s.forward.config.as_ref().unwrap().stale_control{
                s.select_root_domain(&c,&steps[0])?;
            }
            s.issued_generations.clear();''')
    p.write_text(s+'\ninclude!("reverse_fresh_root.rs");\n');shutil.copyfile(HERE/'root.rs',src/'reverse_fresh_root.rs')
    p=src/'forward_feasibility.rs';s=p.read_text()
    s=change(s,'struct PortDirectory {','struct PortDirectory {\n    fresh_keys: std::cell::OnceCell<Vec<(u64,u64)>>,')
    s=change(s,'let dir = Rc::new(PortDirectory {','let dir = Rc::new(PortDirectory {\n            fresh_keys:Default::default(),')
    p.write_text(s)
    p=src/'ordinary_shortlist.rs';s=p.read_text()
    s=change(s,'        }else{None};\n        let len=list.as_ref().map_or(d.frame.rows.len(),|v|v.len());',
        '''        }else if i==0{self.root_domain.current.clone()}else{None};
        let len=list.as_ref().map_or(d.frame.rows.len(),|v|v.len());''');p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if let Some(v)=req.get("reverse_fresh"){ordinary_witness::enable_reverse_root(v.clone())?;}
'''+a))
