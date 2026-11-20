"""Add request-bearing root tokens, checked publications and a guarded child projection to a private build."""
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent


def change(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise ValueError(f'{path.name}: expected one {old[:70]!r}, found {text.count(old)}')
    path.write_text(text.replace(old,new))


def install(crate):
    src=crate/'src'
    shutil.copyfile(HERE/'higher.rs',src/'higher.rs')
    with (src/'lib.rs').open('a') as f:f.write('\npub mod higher;\n')

    # Issue the symbolic conditional alongside the model-chosen parent's physical inputs.
    # The request is a member of the actual packet until verification/commit; its materialized
    # frontier starts only when the parent's checked output is published by the source.
    p=src/'joint_root.rs'
    change(p,'struct Recipe{wire:Rc<[u8]>}', 'struct Recipe{wire:Rc<[u8]>,higher:Option<crate::higher::Request>,compact:Option<Decoded>}')
    change(p,'struct Decoded{serial:u64,','struct Decoded{higher:Option<crate::higher::Request>,serial:u64,')
    change(p,'    if packet.wire.len()%8!=0','    if let Some(c)=&packet.compact{return Some(c.clone());}\n    if packet.wire.len()%8!=0')
    change(p,'Some(Decoded{serial,origin,run,layout','Some(Decoded{higher:packet.higher,serial,origin,run,layout')
    change(p,'Some(Recipe{wire:wire.into()})','Some(Recipe{wire:wire.into(),higher:crate::higher::issue(run,rid,state.serial),compact:None})')
    change(p,'state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));','state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));\n        crate::higher::activate(r.serial,r.higher,state.ordinal,epoch,rid)?;')
    change(p,'pub(crate) fn end(){STATE','pub(crate) fn end(){crate::higher::end();STATE')
    with p.open('a') as f:f.write('''
pub(crate) fn from_conditional(run:u64,rid:usize,parent:&crate::higher::Child)->Option<Recipe>{
    STATE.with_borrow_mut(|s|{
        let s=s.as_mut()?;let layout=s.layout.get(rid)?.clone();
        s.serial+=1;s.emitted[0]+=1;
        let refs=vec![Ref{atom:0,row:parent.source,version:parent.version}];
        let next=crate::higher::inherit(run,rid,s.serial,*parent);
        let c=Decoded{higher:next,serial:s.serial,origin:"single",run,template:layout.template,refs,ports:layout.fields.clone(),layout};
        Some(Recipe{wire:Rc::from([]),higher:next,compact:Some(c)})
    })
}
''')

    p=src/'stage_spine.rs'
    change(p,'pub(crate) struct Publication {','pub(crate) struct Publication {\n    higher:Option<crate::higher::Origin>,')
    change(p,'let publication = Publication {\n                slot,','let publication = Publication {\n                higher:crate::higher::stage(rid,i,table),\n                slot,')
    change(p,'let publication = Publication {\n                                slot,','let publication = Publication {\n                                higher:None,\n                                slot,')
    change(p,'                self.install_anchor(w, table, publication);','''                if crate::higher::tracking(table){crate::higher::publish(g,w,table,&key,publication.higher)?;}
                self.install_anchor(w, table, publication);''')
    p=src/'single_witness.rs'
    change(p,'struct Token{recipe:', 'struct Token{higher:Option<crate::higher::Child>,recipe:')
    change(p,'        let mut offers=Vec::new();let mut delivered=0;', '        let higher_rule=crate::higher::handles(rid);\n        let mut offers=Vec::new();let mut delivered=0;')
    change(p,'            let f=self.features(g,r,&p,row.as_ref(),wm);','''            if let Some(visible)=row.as_ref().filter(|_|higher_rule){
                match crate::higher::choose(rid,visible,wm){
                    crate::higher::Choice::Regular=>{}
                    crate::higher::Choice::Excluded=>{
                        // The classifier's causal history sees the exact guard mask. Other rules still
                        // observe the same visible rows, including unresolved external readers.
                        self.serial+=1;
                        offers.push((None,[0;N],false));
                        score_sum+=f32::from(visible.epoch>=wm);continue;
                    }
                    crate::higher::Choice::Selected(child)=>{
                        let recipe=if crate::higher::baked(){crate::joint_root::from_conditional(g.epoch,rid,&child)}
                            else{crate::joint_root::issue("single",g.epoch,rid,Some(crate::joint_root::Ref{atom:0,row:visible.witness,version:visible.epoch}).into_iter())};
                        self.serial+=1;
                        offers.push((Some(Token{higher:Some(child),recipe,id:self.serial,rid,w,guarded:false,version:visible.epoch,initial:self.initial.contains(&visible.witness),score:1.}),[0;N],true));
                        delivered+=usize::from(crate::higher::logical_offer(rid,child));score_sum+=f32::from(visible.epoch>=wm);continue;
                    }
                }
            }
            let f=self.features(g,r,&p,row.as_ref(),wm);'''.replace('f32::from(visible.epoch>=wm)','(visible.epoch>=wm) as u8 as f32'))
    change(p,'offers.push((Token{recipe,id:self.serial,','offers.push((Some(Token{higher:None,recipe,id:self.serial,')
    change(p,'score:s},f,send));','score:s}),f,send));')
    change(p,'        for (token,f,send) in offers{','        for (token,f,send) in offers{\n            let Some(token)=token else{continue};')
    change(p,'            let matched=self.check(g,r,&p,&token,wm)?;', '''            let matched=if let Some(child)=token.higher.filter(|_|crate::higher::baked()){
                crate::higher::projection(g,rid,&child)?
            }else{self.check(g,r,&p,&token,wm)?};''')
    change(p,'            let t=mark.token;assert_eq!(t.rid,rid);','            let t=mark.token;assert_eq!(t.rid,rid);\n            crate::higher::commit(rid,run,self.ordinal,t.w,t.higher);')
    p=crate/'examples/joint_witness_session.rs'
    change(p,'        let initial_cells = runtime.graph.stats.cells_created;','''        let higher_config=req.get("higher_config").filter(|v|!v.is_null()).map(serde_json::to_vec).transpose()?;
        crate_configure_higher(&program,higher_config.as_deref())?;
        let initial_cells = runtime.graph.stats.cells_created;''')
    change(p,'fn main() -> Result', 'use eggfuse_cell_runtime::higher::configure as crate_configure_higher;\nfn main() -> Result')
    change(p,'        if one_shot {','        report["higher"]=eggfuse_cell_runtime::higher::report();\n        if one_shot {') if p.read_text().count('        if one_shot {')==1 else change(p,'        if one_shot {\n            let single =','        report["higher"]=eggfuse_cell_runtime::higher::report();\n        if one_shot {\n            let single =')
