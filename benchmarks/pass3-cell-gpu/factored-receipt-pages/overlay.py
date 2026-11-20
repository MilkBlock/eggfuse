"""Install typed column dictionaries in the existing immutable multi-parent page."""
from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent


def change(text,old,new):
    if text.count(old)!=1:
        raise ValueError(old)
    return text.replace(old,new)


def install(crate):
    src=crate/'src'
    p=src/'multi_root_pages.rs';s=p.read_text()
    s=s[:s.index('pub(crate) fn multi_page(')]
    s=change(s,'    refs: Vec<Ref>,','    store: FactorStore,')
    a=s.index('    fn slice(');b=s.index('    pub(crate) fn recipe',a)
    s=s[:a]+'''    pub(crate) fn read_parents<'a>(&'a self,slot:usize,scratch:&'a mut Vec<Ref>)->Result<&'a [Ref]> {
        if slot>=self.0.count {return Err("multi page slot out of range".into())}
        self.0.store.read(slot,self.0.width,scratch)
    }
'''+s[b:]
    s=change(s,'        let mut refs = self.slice(slot)?.to_vec();','''        let mut scratch=Vec::new();
        let mut refs=match &p.store {
            FactorStore::Flat(_)=>self.read_parents(slot,&mut scratch).ok()?.to_vec(),
            FactorStore::Packed(_)=>{self.read_parents(slot,&mut scratch).ok()?;scratch}
        };''')
    p.write_text(s+'\ninclude!("factored_pages.rs");\n')
    copyfile(HERE/'packed.rs',src/'factored_pages.rs')
    copyfile(HERE/'wire.rs',src/'factor_wire.rs')
    p=src/'joint_root.rs';s=change(p.read_text(),'struct State{','struct State{factor_mode:u8,factor_fault:bool,factor_stats:FactorStats,')
    s=change(s,'Some(State{encoding:c.encoding','Some(State{factor_mode:0,factor_fault:false,factor_stats:FactorStats::default(),encoding:c.encoding')
    p.write_text(change(s,'"root_row_decodes":s.decodes,','"factor":s.factor_stats,"root_row_decodes":s.decodes,'))
    p=src/'ordinary_shortlist.rs';s=change(p.read_text(),'self.seal_raw(c,steps,path,raw);','self.seal_raw(c,steps,path,raw)?;')
    s=change(s,'path:&Vec<Dependency>,raw:&mut Vec<Vec<Dependency>>){','path:&Vec<Dependency>,raw:&mut Vec<Vec<Dependency>>)->Result<()>{')
    s=change(s,'                self.page_refs.extend(refs);','''                if self.factor_stream && self.cap==usize::MAX {
                    let builder=self.factor_active.get_or_insert_with(||crate::joint_root::FactorBuilder::new(steps.len(),4,self.detailed));
                    builder.append(refs)?;
                    if self.page_tuples>0 && builder.count()>=self.page_tuples {
                        let built=self.factor_active.take().unwrap();
                        self.factor_pages.push(crate::joint_root::streamed_page(c.graph.epoch,self.rule,built,self.page_fault)?);
                    }
                    return Ok(())
                }
                self.page_refs.extend(refs);''')
    a=s.index('                self.page_refs.extend(refs);')
    s=s[:a]+s[a:].replace('                return;','                return Ok(());',1)
    s=change(s,'}else{raw.push(path.clone());}\n\n}', '}else{raw.push(path.clone());}\n            Ok(())\n}')
    p.write_text(s)
    p=src/'incremental_raw.rs';s=p.read_text()
    assert s.count('self.seal_raw(c, steps, &path, raw);')==2
    p.write_text(s.replace('self.seal_raw(c, steps, &path, raw);','self.seal_raw(c, steps, &path, raw)?;'))
    p=src/'ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {','struct Store {factor_stream:bool,factor_active:Option<crate::joint_root::FactorBuilder>,factor_pages:Vec<crate::joint_root::MultiPage>,')
    s=change(s,'let s=Store{','let s=Store{factor_stream:false,factor_active:None,factor_pages:Vec::new(),')
    a='            if s.page && (!s.pending_pages.is_empty() || !s.page_refs.is_empty()){'
    s=change(s,a,'''            if let Some(b)=s.factor_active.take(){
                s.factor_pages.push(crate::joint_root::streamed_page(g.epoch,rid,b,s.page_fault)?);
            }
            if s.page && (!s.factor_pages.is_empty() || !s.pending_pages.is_empty() || !s.page_refs.is_empty()){''')
    s=change(s,'let mut pages=Vec::with_capacity(s.pending_pages.len());\n                let mut total=0;', '''let mut pages=std::mem::take(&mut s.factor_pages);
                pages.reserve(s.pending_pages.len());
                let mut total:usize=pages.iter().map(|p|p.count()).sum();
                s.max_sealed_page=s.max_sealed_page.max(pages.iter().map(|p|p.count()).max().unwrap_or(0));''')
    s=change(s,'                for page in pages{','                let mut scratch=Vec::new();\n                for page in pages{')
    s=change(s,'let parents=page.parents(i);','let parents=page.read_parents(i,&mut scratch)?;')
    p.write_text(s+'''\npub fn set_factor_stream(active:bool)->Result<()>{
        STORE.with_borrow_mut(|s|{s.as_mut().ok_or("missing source issuer")?.factor_stream=active;Ok(())})
    }\n''')
    p=crate/'examples/joint_witness_session.rs'
    a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if let Some(mode)=req.get("factor_page") {
            let m=mode.as_u64().ok_or("invalid page coding")?;
            eggfuse_cell_runtime::joint_root::configure_factor(m,req["factor_fault"]==true)?;
            ordinary_witness::set_factor_stream(m==4)?;
        }
'''+a))
