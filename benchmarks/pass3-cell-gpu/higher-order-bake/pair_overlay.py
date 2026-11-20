"""Attach one guarded continuation family to the existing sealed multi-parent verifier."""
from pathlib import Path
import shutil
from overlay import change
HERE=Path(__file__).resolve().parent

def install(crate):
    src=crate/'src'
    shutil.copyfile(HERE/'pairs.rs',src/'higher_pairs.rs')
    p=src/'ordinary_witness.rs'
    with p.open('a') as f:f.write('\ninclude!("higher_pairs.rs");\n')
    change(p,'        if id>0{let mut t=s.tickets[id-1].clone();','        if id>0{let mut t=s.tickets[id-1].clone();pair_confirm(id,s.global_rhs,&t);')
    change(p,'        let mut out=vec![];let mut raw=vec![];if s.accel>=4{','''        let pair=pair_start(g,rid,run,mark);
        let mut sibling=None;let mut cached_raw=false;let mut deferred=vec![];
        let mut out=vec![];let mut raw=vec![];
        if let Some((family,sharing,stamp,old))=pair{
            if sharing!=Sharing::Independent{
                sibling=Some((family,sharing,stamp));
                match old {
                    Some(Waiting::Verified(batch,_))=>{
                        c.sealing=false;let mut unused=vec![];
                        for exact in batch{s.descend(&c,c.inst.len(),exact,&mut out,&mut unused)?;}
                        return Ok(out)
                    }
                    Some(Waiting::Raw(batch,recipes))=>{raw=batch;s.root_offers=recipes;cached_raw=true;}
                    None=>{}
                }
            }
        }
        if cached_raw{} else if s.accel>=4{''')
    change(p,'            let mut stack_recipes=stack_recipes.into_iter();','''            if !cached_raw && let Some((family,sharing,stamp))=&sibling
                && matches!(sharing,Sharing::Raw|Sharing::Stale) {
                let other=family.other(rid);
                let alt=stack_recipes.iter().map(|p|crate::joint_root::choose_sibling(p.clone(),other)).collect::<Result<Vec<_>>>()?;

                pair_store(other,Snapshot{run:stamp.run,watermark:stamp.watermark,versions:stamp.versions.clone()},Waiting::Raw(raw.clone(),alt));
            }
            let raw_count=raw.len();
            let mut stack_recipes=stack_recipes.into_iter();''')
    change(p,'                s.descend(&c,c.pick_count,exact,&mut out,&mut no_more)?;', '''                if let Some((family,Sharing::Verified,_))=&sibling{
                    let Some(chosen)=pair_project(family,&mut exact)? else{continue};
                    if chosen==rid {
                        s.descend(&c,c.inst.len(),exact,&mut out,&mut no_more)?;
                    }else{
                        exact.root_recipe=crate::joint_root::choose_sibling(exact.root_recipe.take(),chosen)?;
                        deferred.push(exact);
                    }
                }else{s.descend(&c,c.pick_count,exact,&mut out,&mut no_more)?;}''')
    change(p,'            debug_assert!(no_more.is_empty())','''            if let Some((family,Sharing::Verified,stamp))=sibling{

                pair_store(family.other(rid),stamp,Waiting::Verified(deferred,raw_count));
            }
            debug_assert!(no_more.is_empty())''')
    change(p,'            self.tickets.push(Ticket{root_recipe,','            pair_origins(c.graph,self.rule,self.tickets.len()+1,&p.anchors);\n            self.tickets.push(Ticket{root_recipe,')
    p=src/'ordinary_shortlist.rs'
    change(p,'self.root_offers.push(crate::joint_root::issue("multi",c.graph.epoch,self.rule,refs));','''let other=PAIRS.with_borrow(|s|s.as_ref().filter(|s|s.mode!=Sharing::Independent).and_then(|s|s.siblings[self.rule].as_ref().map(|f|f.other(self.rule))));
            let mut proposal=crate::joint_root::issue("multi",c.graph.epoch,self.rule,refs);
            crate::joint_root::attach_sibling(&mut proposal,other);
            self.root_offers.push(proposal);''')
    p=src/'joint_root.rs'
    change(p,'struct Recipe{wire:Rc<[u8]>,','struct Recipe{other:Option<usize>,wire:Rc<[u8]>,')
    change(p,'Some(Recipe{wire:wire.into(),','Some(Recipe{other:None,wire:wire.into(),');change(p,'Some(Recipe{wire:Rc::from([]),','Some(Recipe{other:None,wire:Rc::from([]),')
    with p.open('a') as f:f.write('''
pub(crate) fn current_parent()->Option<(usize,usize)>{
    STATE.with_borrow(|s|s.as_ref()?.active.map(|a|(a.0,a.3)))
}
pub(crate) fn attach_sibling(p:&mut Option<Recipe>,other:Option<usize>){
    if let Some(packet)=p{packet.other=other;}
}
pub(crate) fn choose_sibling(p:Option<Recipe>,rid:usize)->Result<Option<Recipe>>{
    let Some(mut packet)=p else{return Ok(None)};
    if packet.other!=Some(rid){return Err("child not named by conditional neural packet".into());}
    let mut decoded=decode(&packet).ok_or("invalid conditional neural parent")?;
    let layout=STATE.with_borrow(|s|s.as_ref()?.layout.get(rid).cloned()).ok_or("unadmitted guarded child")?;
    if layout.fields!=decoded.ports{return Err("guarded exact input projection changed".into());}
    decoded.layout=layout.clone();decoded.template=layout.template;
    decoded.higher=crate::higher::issue(decoded.run,rid,decoded.serial);packet.compact=Some(decoded);
    Ok(Some(packet))
}
''')
    p=src/'graph.rs'
    anchor='            let index = self.set_function_from(t, &key, value, Some((cell, op, source)))?;'
    change(p,anchor,anchor+'\n            crate::ordinary_witness::publish_pair(self,t,op,Dependency::Function(index));')
    p=crate/'examples/joint_witness_session.rs'
    change(p,'        let initial_cells = runtime.graph.stats.cells_created;', '''        let paired=req["guarded_pairs"].as_object().map(serde_json::to_vec).transpose()?;
        eggfuse_cell_runtime::ordinary_witness::configure_pairs(&program,paired.as_deref(),audit)?;
        let initial_cells = runtime.graph.stats.cells_created;''')
    change(p,'        report["higher"]=','        report["guarded_pairs"]=eggfuse_cell_runtime::ordinary_witness::pairs_report();\n        report["higher"]=')
