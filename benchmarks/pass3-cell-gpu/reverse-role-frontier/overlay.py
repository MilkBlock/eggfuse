from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def edit(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)

def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=edit(s,'struct Store {wave:', 'struct Store {frontier:Frontier,wave:')
    s=edit(s,'let s=Store{wave:', 'let s=Store{frontier:Default::default(),wave:')
    s=edit(s,'json!({"wave":s.wave.stats,','json!({"role_frontier":s.frontier.counts,"wave":s.wave.stats,')
    a='let (mut steps,mut slots)=s.compile_stack(&c)?;'
    s=edit(s,a,'let role_clock=s.frontier.phase.then(std::time::Instant::now);\n            '+a)
    a='            if s.forward.config.is_some() && steps.len()>=3{'
    s=edit(s,a,'''            s.frontier.current=None;
            if s.frontier.mode>0 && steps.iter().any(|d|d.frame.rows.is_empty()){
                s.frontier.counts.empty_calls+=1;
                s.frontier.counts.empty_root_rows+=steps.first().map_or(0,|p|p.frame.rows.len());
            }else{
'''+a)
    a='                s.emit_stack(&c,&steps,0,0,&mut vec![],&mut vec![None;slots],&mut raw)?;'
    s=edit(s,a,'''                let frontier_clock=s.frontier.phase.then(std::time::Instant::now);
                s.frontier.current=s.role_frontier(&steps);
                if let Some(t)=frontier_clock{s.frontier.counts.frontier_ms+=t.elapsed().as_secs_f64()*1000.;}
'''+a)
    a='        }else{s.descend(&c,0,p.clone(),&mut out,&mut raw)?;}'
    s=edit(s,a,'            }\n            if let Some(t)=role_clock{s.frontier.counts.issuer_ms+=t.elapsed().as_secs_f64()*1000.;}\n'+a)
    p.write_text(s+'\ninclude!("reverse_role_frontier.rs");\n')
    copyfile(HERE/'frontier.rs',src/'reverse_role_frontier.rs')
    p=src/'ordinary_shortlist.rs';s=p.read_text()
    s=edit(s,'let list=if let Some(&(col,slot))=d.shared.first(){','let list=if i==0 && self.frontier.current.is_some(){self.frontier.current.clone()}else if let Some(&(col,slot))=d.shared.first(){')
    a='let len=list.as_ref().map_or(d.frame.rows.len(),|v|v.len());'
    s=edit(s,a,a+'\n        if i==0{self.frontier.counts.root_loop_positions+=len;}')
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';s=p.read_text()
    a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(edit(s,a,'''        if let Some(n)=req["role_frontier"].as_u64(){ordinary_witness::configure_role_frontier(n,audit,req["role_phase"].as_bool()==Some(true))?;}
'''+a))
