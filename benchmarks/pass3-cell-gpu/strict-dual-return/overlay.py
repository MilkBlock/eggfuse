from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent
def change(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)
def edit(p,a,b):p.write_text(change(p.read_text(),a,b))
def install(crate):
    src=crate/'src';copyfile(HERE/'dual.rs',src/'dual_return.rs')
    p=src/'lib.rs';p.write_text(p.read_text()+'\npub mod dual_return;\n')
    ex=crate/'examples/joint_witness_session.rs'
    a='        let ingest_start=Instant::now();'
    edit(ex,a,'        eggfuse_cell_runtime::dual_return::configure(&req["strict_dual"],&program,&program_bytes,audit)?;\n'+a)
    a='        report["pre_post_ms"]=';edit(ex,a,'        report["strict_dual"]=eggfuse_cell_runtime::dual_return::report();\n'+a)
    j=src/'joint_root.rs'
    edit(j,'struct Decoded{serial:u64,','struct Decoded{signed_dual:bool,serial:u64,')
    for a in ('Some(Decoded{serial,origin,run,','Decoded{serial:state.serial,'):
        edit(j,a,a.replace('Decoded{','Decoded{signed_dual:false,'))
    p=src/'adaptive_root_page.rs';edit(p,'        Some(Decoded {','        Some(Decoded {signed_dual:false,')
    p=src/'multi_root_pages.rs'
    edit(p,'        Some(Decoded {','        Some(Decoded {signed_dual:(p.template>>32)==1,')
    edit(p,'            template: p.template,','            template:p.template&0xffffffff,')
    edit(p,'        let first_serial = st.serial.checked_add(1).ok_or("root serial overflow")?;', '        crate::dual_return::check_external(run,rid,&refs,width);\n        let first_serial = st.serial.checked_add(1).ok_or("root serial overflow")?;')
    edit(p,'        let invalid_version = st.mode','        let template=crate::dual_return::tag(rid,template,count);\n        let invalid_version = st.mode')
    edit(j,'        state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));','''        crate::dual_return::begin(r.serial,rid,epoch,&r.refs,r.signed_dual)?;
        state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));''')
    edit(j,'            s.allocated+=1;','            crate::dual_return::fresh(id);s.allocated+=1;')
    edit(j,'pub(crate) fn end(){STATE.with_borrow_mut','pub(crate) fn end(){crate::dual_return::end();STATE.with_borrow_mut')
    g=src/'graph.rs'
    edit(g,'        self.stats.logical_facts_created += 1;','        crate::dual_return::birth(self,f,t,&v);\n        self.stats.logical_facts_created += 1;')
    edit(g,'        self.parents.insert(hi, lo);','        crate::dual_return::union(hi,lo);\n        self.parents.insert(hi, lo);')
    with p.open('a') as f:f.write('''
pub(crate) fn explicit_child(run:u64,rid:usize,p:&crate::dual_return::Pair)->Result<MultiPage>{
    STATE.with_borrow_mut(|c|{
        let s=c.as_mut().ok_or("missing explicit composite root")?;let layout=s.layout[rid].clone();
        let first_serial=s.serial.checked_add(1).ok_or("root serial overflow")?;s.serial=first_serial;
        Ok(MultiPage(Rc::new(MultiPageData{seal:mint_local_seal(s.redemption!=0),run,first_serial,width:2,count:1,template:layout.template,layout,
            refs:vec![p.left.clone(),p.right.clone()],withheld:false,invalid_version:false})))
    })
}
''')
    p=src/'ordinary_witness.rs'
    edit(p,'struct Store {wave:', 'struct Store {dual_queue:Vec<(usize,crate::dual_return::Pair)>,wave:')
    edit(p,'let s=Store{wave:', 'let s=Store{dual_queue:vec![],wave:')
    a='''            for refs in groups{
                let bank=crate::joint_root::multi_page(g.epoch,rid,c.pick_count,refs,s.page_fault)?;'''
    edit(p,a,'''            let mut direct=std::mem::take(&mut s.dual_queue).into_iter().peekable();
            let count=groups.len();let mut original=groups.into_iter();
            for j in 0..=count{
                while direct.peek().is_some_and(|x|x.0==j){
                    let (_,p)=direct.next().unwrap();let bank=crate::joint_root::explicit_child(g.epoch,rid,&p)?;
                    crate::dual_return::minted(bank.stage_serial(),p,g.epoch);tuples+=1;pages.push(bank);
                }
                let Some(refs)=original.next()else{continue};
                let bank=crate::joint_root::multi_page(g.epoch,rid,c.pick_count,refs,s.page_fault)?;''')
    p=src/'incremental_raw.rs'
    a='        let full_left = left.frame.rows.len();'
    edit(p,a,'''        // Independently release named children before any paired lookup; all remaining
        // source pairs keep the ordinary sender. Positions affect placement only.
        let assigned=if self.wave.preparing{crate::dual_return::release(c.graph,self.rule,if c.rule.seminaive{c.watermark}else{0})?}else{Default::default()};
        let mut protected=BTreeMap::new();
        for (w,p) in assigned{
            let index=left.frame.rows.binary_search_by_key(&w,|row|row.witness).map_err(|_|"missing certified source location")?;
            protected.insert(index,p);
        }
'''+a)
    a='                            for &l in indices {'
    edit(p,a,a+'\n                                if protected.contains_key(&l){crate::dual_return::skip(true);continue;}')
    edit(p,'            active.sort_unstable();','''            active.extend(protected.keys().copied());active.sort_unstable();active.dedup();''')
    a='            let l = if selective { active[pos] } else { pos };'
    edit(p,a,a+'''
            if let Some(child)=protected.remove(&l){
                crate::dual_return::skip(false);
                if !self.page_refs.is_empty(){self.pending_pages.push(std::mem::take(&mut self.page_refs));}
                self.dual_queue.push((self.pending_pages.len(),child));continue;
            }''')
    a='        self.flat_offsets.clear();\n        Ok(())\n    }\n}'
    edit(p,a,'        if !protected.is_empty(){return Err("independently verified child not placed".into())}\n'+a)
    # Use the existing macOS inference boundary solely when the caller requests RSS.
    from runpy import run_path
    prior=HERE.parent/'verified-wave-rss'
    copyfile(prior/'window.rs',src/'rss_window.rs')
    p=src/'lib.rs';p.write_text(p.read_text()+'\npub mod rss_window;\n')
    run_path(str(prior/'overlay.py'))['driver'](ex,'req','eggfuse_cell_runtime::rss_window')
