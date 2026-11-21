from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def edit(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise ValueError((p,a))
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';copyfile(HERE/'strict.rs',src/'strict_merge_return.rs')
    p=src/'lib.rs';edit(p,'pub mod joint_merge;','pub mod joint_merge;\npub mod strict_merge_return;')
    p=src/'multi_root_pages.rs'
    edit(p,'    refs: Vec<Ref>,\n    withheld:', '''    refs:Vec<Ref>,
    strict_merge:Option<crate::strict_merge_return::IssuedPage>,
    withheld:''')
    edit(p,'        st.emitted[1] += count as u64;', '''        let strict_merge=crate::strict_merge_return::issue_page(rid,run,first_serial,width,&refs);
        st.emitted[1] += count as u64;''')
    edit(p,'            refs,\n            withheld,','            refs,strict_merge,\n            withheld,')
    p=src/'joint_root.rs'
    edit(p,'struct Bound{recipe:Decoded,','struct Bound{strict_merge:Option<crate::strict_merge_return::Claim>,recipe:Decoded,')
    original=p.read_text()
    assert original.count('Bound{recipe,values:')==2
    p.write_text(original.replace('Bound{recipe,values:', 'Bound{strict_merge:crate::strict_merge_return::seal(packet.strict_merge_claim(),verified)?,recipe,values:'))
    with p.open('a') as f:f.write('''
impl Recipe{fn strict_merge_claim(&self)->Option<crate::strict_merge_return::Claim>{
    if let Body::MultiPage(page,i)=&self.0{page.0.strict_merge.as_ref().and_then(|b|b.get(*i,page.slice(*i)?))}else{None}
}}
''')
    a='        crate::strict_named::begin(r.serial,rid,!r.refs.is_empty(),r.strict_code)?;'
    edit(p,a,a+'\n        crate::strict_merge_return::activate(bound.strict_merge.as_ref(),rid,epoch,r.serial,state.ordinal,&r.refs)?;')
    edit(p,'pub(crate) fn end(){crate::strict_named::end();','pub(crate) fn end(){crate::strict_merge_return::end();crate::strict_named::end();')
    p=src/'graph.rs'
    a='            self.stats.constructor_reused += 1;\n\n            let value = row.values.last().unwrap().clone();'
    edit(p,a,'            crate::strict_merge_return::returned(cell,op,t,row.witness);\n'+a)
    a='        let value = self.insert_constructor(cell, op, t, &key, dst)?;'
    edit(p,a,a+'\n        crate::strict_merge_return::returned(cell,op,t,Dependency::Fact(FactRef{cell,op:op as u32}));')
    a='            crate::joint_merge::issue(self,cell,op,t,&key,&value)?;'
    edit(p,a,'''            if !crate::strict_merge_return::arm(self,cell,op,t,&key,&value)?{
                crate::joint_merge::issue(self,cell,op,t,&key,&value)?;
            }''')
    edit(p,'            crate::joint_merge::finish();','            crate::joint_merge::finish();crate::strict_merge_return::finish_effect();')
    a='        if let Some(packet)=crate::joint_merge::take(self,t,&key)?{'
    edit(p,a,'''        if let Some(template)=crate::strict_merge_return::take(t,&key)?{
            if let Some(row)=self.lookup_canonical(t,&key)?{
                crate::strict_merge_return::complete(row.witness,false);return Ok(row.values.last().unwrap().clone());
            }
            let columns=key.iter().cloned().enumerate().collect();
            let id=self.linked_slots(template,columns,None)?;
            self.stats.constructor_requests+=1;
            let value=self.insert_constructor(id,0,t,&key,key.len())?;
            crate::strict_merge_return::complete(Dependency::Fact(FactRef{cell:id,op:0}),true);
            return Ok(value);
        }
'''+a)
    p=src/'cell_handoff.rs'
    a='        receipts.record_handoff(input.op, witness, input, original, g.program.iterative.tracks_slots());'
    edit(p,a,'        crate::strict_merge_return::returned_handoff(cell,input.op,witness);\n'+a)
    p=crate/'examples/joint_witness_session.rs'
    a='        let root_config=req["root_config"].as_str().map(std::fs::read).transpose()?;'
    edit(p,a,'''        eggfuse_cell_runtime::strict_merge_return::configure(&program,req["strict_merge"].as_u64().unwrap_or(0).try_into()?,audit)?;
'''+a)
    a='        report["merge_child"]=eggfuse_cell_runtime::joint_merge::report();'
    edit(p,a,a+'\n        report["strict_merge"]=eggfuse_cell_runtime::strict_merge_return::report();')
    # The existing child audit records a boolean for an intern hit. Keep its
    # exact physical return too so both branches have independent witnesses.
    p=src/'joint_merge.rs'
    edit(p,'    allocated: Option<u32>,','    allocated: Option<u32>,\n    returned_reference:Option<Dependency>,')
    edit(p,'            allocated: None,','            allocated: None,returned_reference:None,')
    edit(p,'pub(crate) fn allocated(id: usize, cell: Option<u32>) {','pub(crate) fn allocated(id:usize,cell:Option<u32>,actual:Dependency){')
    edit(p,'        t.allocated = cell;','        t.allocated = cell; if s.audit {t.returned_reference=Some(actual);}')
    p=src/'graph.rs'
    edit(p,'crate::joint_merge::allocated(packet.id,None);','crate::joint_merge::allocated(packet.id,None,existing.witness);')
    edit(p,'crate::joint_merge::allocated(packet.id,Some(id));','crate::joint_merge::allocated(packet.id,Some(id),Dependency::Fact(FactRef{cell:id,op:0}));')
