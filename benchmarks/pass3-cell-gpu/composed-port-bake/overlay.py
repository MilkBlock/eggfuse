from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent

def change(p, old, new):
    s=p.read_text()
    if s.count(old)!=1:raise ValueError((p.name,old,s.count(old)))
    p.write_text(s.replace(old,new))


def install(crate):
    src=crate/'src'
    h=src/'higher.rs'
    change(h,'    transaction_batch: usize,','    transaction_batch: usize,\n    #[serde(default)]\n    composed:u8,\n    #[serde(default)] macro_policy:Option<MacroPolicy>,')
    change(h,'    tx: Transactions,','    tx: Transactions,\n    composed:u8,macro_policy:Option<MacroPolicy>,charges:Vec<Charge>,delta:DeltaCover,cover:Cover,frontier_stats:[u64;9],')
    change(h,'            family: f,','            family: f,composed:c.composed,macro_policy:c.macro_policy,charges:vec![],delta:DeltaCover::default(),cover:Cover::default(),frontier_stats:[0;9],')
    change(h,'"winners":s.winners,','"delta":s.delta.stats,"charges":s.charges,"boundary":s.frontier_stats, "winners":s.winners,')
    change(h,'    generation: u64,\n}\n#[derive(Clone, Copy)]','    generation:u64, macro_accepted:bool,\n}\n#[derive(Clone, Copy)]')
    change(h,'    let c = Child {','    let mut c = Child {macro_accepted:false,')
    change(h,'    s.pending.insert(w, c);','    c.macro_accepted=admit(s,&c);\n    s.pending.insert(w,c);')
    change(h,'        if c.version < wm {','        audit_read(s,c,c.version>=wm,if is_gt{2}else{1});\n        if c.version < wm {')
    change(h,'            s.last_child = Some((ordinal, c));','            s.last_child=Some((ordinal,c));if s.profile{s.charges[c.generation as usize-1].counts[2]+=1;}')
    change(h,'    if s.pending.remove(&w).is_some() {','    if let Some(old)=s.pending.remove(&w) {if s.profile{s.charges[old.generation as usize-1].superseded+=1;}')
    change(h,'        if c.version != row.epoch || s.mode == Mode::Stale || row.hidden {','        if c.version != row.epoch || s.mode == Mode::Stale || row.hidden {if s.profile && (c.version!=row.epoch||row.hidden){s.charges[c.generation as usize-1].visible_version_misses+=1;}')
    change(h,'            s.pending.remove(&prior.source);','            s.pending.remove(&prior.source);if s.composed==4 && s.delta.version.is_some(){s.delta.dirty.insert(prior.source);}')
    change(h,'    if c.transaction_batch > 32 {','    if c.composed>4 || c.macro_policy.as_ref().is_some_and(|p|!p.bias.is_finite() || !p.threshold.is_finite() || p.weights.iter().any(|v|!v.is_finite())){return Err("invalid composed gate".into());}\n    if c.transaction_batch > 32 {')
    change(h,'    s.tx.completed += 1;','    s.tx.completed += 1;if s.composed==4 && s.delta.version.is_some(){s.delta.dirty.insert(w);}')
    q=src/'runtime_completion.rs'
    change(q,'        self.publication.publish(','        crate::higher::changes(&self.graph);\n        self.publication.publish(')
    shutil.copy2(HERE/'delta.rs',src/'composed_delta.rs')
    shutil.copy2(HERE/'boundary.rs',src/'composed_boundary.rs')
    with h.open('a') as f:f.write('\ninclude!("composed_boundary.rs");\ninclude!("composed_delta.rs");\n')
    driver=crate/'examples/joint_witness_session.rs'
    change(driver,'        let start = Instant::now();','        let initial_decodes=runtime.graph.fact_decode_calls.get();\n        let start = Instant::now();')
    change(driver,'        let mut state = vec![];','        let inference_decodes=runtime.graph.fact_decode_calls.get()-initial_decodes;\n        let mut state = vec![];')
    change(driver,'        report["higher"]=','        report["inference_fact_decodes"]=json!(inference_decodes);\n        report["higher"]=')
    p=src/'single_witness.rs'
    change(p,'struct Token{higher:', 'struct Token{reserved:u64,higher:')
    code=p.read_text().replace('Token{higher:','Token{reserved:0,higher:')
    p.write_text(code)
    change(p,'        let candidates=if let Some(a)=p.pivot{','''        let higher_rule=crate::higher::handles(rid);if higher_rule{crate::higher::barrier(3)?;}
        let mut frontier=if higher_rule{crate::higher::boundary(g,rid,wm)}else{None};
        let candidates=if frontier.is_some(){vec![]}else if let Some(a)=p.pivot{''')
    # Anchor after the candidate expression; keep barriers before frontier construction.
    change(p,'}else{vec![None]};\n        let higher_rule=crate::higher::handles(rid);if higher_rule{crate::higher::barrier(3)?;}','}else{vec![None]};')
    change(p,'        for w in candidates{','''        let base_serial=self.serial;let mut ordinary=candidates.into_iter();
        loop{
            let w=if let Some(f)=&mut frontier{
                let Some((rank,w,owned))=f.entries.next()else{break};
                self.serial=base_serial+rank as u64;
                if let Some(child)=owned {
                    let (recipe,reserved)=if crate::higher::inline_child(){(None,crate::joint_root::reserve_child()?)}
                        else{(crate::joint_root::from_conditional(g.epoch,rid,&child),if crate::higher::fuse_seal(){u64::MAX}else{0})};
                    self.serial+=1;
                    offers.push((Some(Token{reserved,higher:Some(child),recipe,id:self.serial,rid,w:Some(w),guarded:false,version:child.version,initial:self.initial.contains(&w),score:1.}),[0;N],true));
                    delivered+=1;score_sum+=1.;continue;
                }
                Some(w)
            }else{let Some(w)=ordinary.next()else{break};w};''')
    change(p,'        let n=offers.len();','''        let n=if let Some(f)=frontier{
            self.serial=base_serial+f.total as u64;score_sum+=f.omitted_fresh as f32;f.total
        }else{offers.len()};''')
    change(p,'let root_recipe=crate::joint_root::bind_single(token.recipe.clone(),g,rid,&binding.known,&binding.values)?;',
    '''let root_recipe=if token.reserved!=0 && token.reserved!=u64::MAX {
        crate::joint_root::bind_inline_child(token.reserved,g,rid,&binding.known,&binding.values,token.higher.ok_or("missing composed parent")?)?
    }else if let Some(child)=token.higher.filter(|_|token.reserved==u64::MAX){
        crate::joint_root::bind_leaf_port(token.recipe.clone(),g,rid,&binding.known,&binding.values,child)?
    }else{crate::joint_root::bind_single(token.recipe.clone(),g,rid,&binding.known,&binding.values)?};''')
    with (src/'joint_root.rs').open('a') as f:f.write("""
pub(crate) fn reserve_child()->Result<u64>{
    STATE.with_borrow_mut(|state|{
        let s=state.as_mut().ok_or("missing learned root provider")?;
        s.serial+=1;s.emitted[0]+=1;crate::higher::absorbed();Ok(s.serial)
    })
}
pub(crate) fn bind_inline_child(serial:u64,g:&Graph,rid:usize,known:&QueryFacts,verified:&Slots,c:crate::higher::Child)->Result<Option<Rc<Bound>>>{
    if known.receipt(0)!=Some(c.source){return Err("composed parent port changed".into());}
    STATE.with_borrow_mut(|state|{
        let s=state.as_mut().ok_or("missing composed root")?;
        let layout=s.layout.get(rid).ok_or("unadmitted composed rule")?.clone();
        if layout.template!=g.program.rules[rid].template||serial>s.serial{return Err("invalid composed boundary".into());}
        let next=crate::higher::inherit(g.epoch,rid,serial,c);
        crate::higher::charged(layout.fields.len());
        let refs=vec![Ref{atom:0,row:c.source,version:c.version}];
        let recipe=Decoded{higher:next,serial,origin:"single",run:g.epoch,template:layout.template,layout,refs,ports:Vec::new()};
        s.sealed+=1;
        Ok(Some(Rc::new(Bound{recipe,values:verified.clone()})))
    })
}
pub(crate) fn bind_leaf_port(packet:Option<Recipe>,g:&Graph,rid:usize,known:&QueryFacts,verified:&Slots,c:crate::higher::Child)->Result<Option<Rc<Bound>>>{
    let rejected=||{STATE.with_borrow_mut(|s|s.as_mut().unwrap().rejected+=1);Ok(None)};
    let Some(packet)=packet else{return rejected()};
    // Only the statically checked conditional projection creates this private compact packet.
    let Some(recipe)=packet.compact else{return rejected()};
    if recipe.layout.rid!=rid || recipe.run!=g.epoch || recipe.refs.len()!=1 ||
        recipe.template!=g.program.rules[rid].template || recipe.refs[0].atom!=0 ||
        recipe.refs[0].row!=c.source || recipe.refs[0].version!=c.version ||
        known.receipt(0)!=Some(c.source) {return rejected();}
    crate::higher::charged(recipe.ports.len());
    STATE.with_borrow_mut(|s|s.as_mut().unwrap().sealed+=1);
    Ok(Some(Rc::new(Bound{recipe,values:verified.clone()})))
}
""")
