from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent
def edit(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)
def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=edit(s,'struct Store {pair_actor:', 'struct Store {family:Family,pair_actor:')
    s=edit(s,'let s=Store{pair_actor:', 'let s=Store{family:Default::default(),pair_actor:')
    s=edit(s,'json!({"pair_actor":','json!({"family_work":s.family.metrics,"family_origins":s.family.origins,"family_rules":s.family.rules,"family_examples":s.family.examples,"pair_actor":')
    a='                s.emit_two(&c,&steps,&mut raw)?;'
    s=edit(s,a,'''                if s.family.mode!=0 && s.wave.preparing && s.cap==usize::MAX && s.lazy_eq.mode==4 {
                    s.family_two(&c,&steps)?;
                }else{
                    let measured=s.family.phase.then(std::time::Instant::now);
'''+a+'\n                    if let Some(t)=measured{s.family.metrics.source_pair_ms+=t.elapsed().as_secs_f64()*1000.;}\n                }')
    a='            assert!(actions.next().is_none());'
    s=edit(s,a,a+'''\n            if let Some(pg)=s.family.ready.take(){
                if !pages.is_empty(){return Err("mixed external and family pages within a source rule".into())}
                tuples=pg.count();s.max_sealed_page=s.max_sealed_page.max(tuples);pages.push(pg);
            }''')
    p.write_text(s+'\ninclude!("learned_pair_family.rs");\n');copyfile(HERE/'family.rs',src/'learned_pair_family.rs')
    p=src/'multi_root_pages.rs';s=p.read_text()
    s=edit(s,'    bucket:Option<VerifiedBucket>,','    bucket:Option<VerifiedBucket>,\n    family:Option<FamilyRows>,')
    s=edit(s,'refs,bucket:None,','refs,bucket:None,family:None,')
    s=edit(s,'        if let Some(b)=&self.0.bucket{','        if let Some(b)=&self.0.family{return PageLane::Generated(b.at(slot))}\n        if let Some(b)=&self.0.bucket{')
    p.write_text(s+'\ninclude!("learned_family_page.rs");\n');copyfile(HERE/'page.rs',src/'learned_family_page.rs')
    p=src/'pair_bucket_page.rs';s=p.read_text()
    p.write_text(edit(s,'refs:vec![],bucket:Some(', 'refs:vec![],family:None,bucket:Some('))
    p=crate/'examples/joint_witness_session.rs';s=p.read_text();a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(edit(s,a,'        if let Some(v)=req.get("pair_family"){ordinary_witness::configure_family(v)?;}\n'+a))
