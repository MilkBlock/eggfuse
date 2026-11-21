from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def rep(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise ValueError((p,a))
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';p=src/'lib.rs';rep(p,'pub mod strict_merge_return;','pub mod strict_merge_return;\npub mod strict_template_wire;');copyfile(HERE/'wire.rs',src/'strict_template_wire.rs')
    p=src/'strict_merge_return.rs'
    rep(p,'impl IssuedPage {','impl IssuedPage {\n    pub(crate) fn wire_tags(&self)->&[u8]{&self.tags}')
    p=src/'strict_named.rs';a='            template | ((rid + 1) << 32)'
    rep(p,a,'            assert!(rid < 0x7fff_ffff, "Spine tag exceeds 31-bit field");\n'+a)
    p=src/'multi_root_pages.rs'
    rep(p,'    template: usize,','    template_word:[u8;8],')
    rep(p,'strict_code:p.template>>32','strict_code:crate::strict_template_wire::spine(p.template_word)')
    rep(p,'template:p.template&0xffffffff','template:crate::strict_template_wire::source(p.template_word)')
    a='        st.emitted[1] += count as u64;'
    rep(p,a,'''        let template_word=crate::strict_template_wire::pack(template,strict_merge.is_some());
        crate::strict_template_wire::record(false,rid,run,first_serial,count,template_word,strict_merge.as_ref().map(|p|p.wire_tags()));
'''+a)
    rep(p,'            template,\n            refs,strict_merge,','            template_word,\n            refs,strict_merge,')
    p=src/'adaptive_root_page.rs';a='        for &(dep, version) in inputs {'
    rep(p,a,'''        let header=crate::strict_template_wire::pack(words[4] as usize,false);
        words[4]=u64::from_le_bytes(header);
        crate::strict_template_wire::record(true,rid,run,first,inputs.len(),words[4].to_le_bytes(),None);
'''+a)
    p=src/'joint_root.rs';s=p.read_text();assert s.count('packet.strict_merge_claim(),verified')==2
    p.write_text(s.replace('packet.strict_merge_claim(),verified','packet.strict_merge_claim()?,verified'))
    rep(p,'''fn strict_merge_claim(&self)->Option<crate::strict_merge_return::Claim>{
    if let Body::MultiPage(page,i)=&self.0{page.0.strict_merge.as_ref().and_then(|b|b.get(*i,page.slice(*i)?))}else{None}''',
        '''fn strict_merge_claim(&self)->Result<Option<crate::strict_merge_return::Claim>>{
    if let Body::MultiPage(page,i)=&self.0{
        if crate::strict_template_wire::merge(page.0.template_word)!=page.0.strict_merge.is_some(){return Err("strict merge tag/payload conflict".into());}
        Ok(page.0.strict_merge.as_ref().and_then(|b|b.get(*i,page.slice(*i)?)))
    }else{Ok(None)}''')
    p=crate/'examples/joint_witness_session.rs';a='        eggfuse_cell_runtime::strict_merge_return::configure('
    rep(p,a,'        eggfuse_cell_runtime::strict_template_wire::configure(audit,req["strict_wire_fault"].as_u64().unwrap_or(0).try_into()?)?;\n'+a)
    a='        report["strict_merge"]=eggfuse_cell_runtime::strict_merge_return::report();'
    rep(p,a,a+'\n        report["strict_template_words"]=eggfuse_cell_runtime::strict_template_wire::report();')
