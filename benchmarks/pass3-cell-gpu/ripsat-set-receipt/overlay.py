from pathlib import Path
from shutil import copyfile
def edit(p,before,after):
    s=p.read_text()
    if s.count(before)!=1:raise ValueError(before)
    p.write_text(s.replace(before,after))
def install(crate):
    src=crate/'src';p=src/'strict_named.rs';g=src/'graph.rs';rt=src/'runtime.rs';ex=crate/'examples/joint_witness_session.rs'
    copyfile(Path(__file__).parent/'publication.rs',src/'ripsat_set_publication.rs')
    with p.open('a') as f:f.write('\ninclude!("ripsat_set_publication.rs");\n')
    edit(p,'struct State {partial:bool,stale_versions:bool,','''struct State {set_plan:Option<SetPlan>,set_counts:PublicationCounts,pending_set:Option<PublishedSet>,
    set_links:Vec<J>,set_fault:String,partial:bool,stale_versions:bool,''')
    edit(p,'struct Permit {audit_ports:','struct Permit {immediate_serial:u64,audit_ports:')
    edit(p,'struct Owner {audit_ports:', 'struct Owner {set_data:Option<std::rc::Rc<PublishedSet>>,audit_ports:')
    edit(p,'let owner = Owner {audit_ports,','let owner = Owner {set_data:None,audit_ports,')
    edit(p,'                    prior: internal.path,','                    immediate_serial:serial,prior: internal.path,')
    edit(p,'                prior: vec![],','                immediate_serial:serial,prior: vec![],')
    edit(p,'    S.with_borrow_mut(|v| *v = (depth != 0).then_some(s));','''    s.set_plan=plan_set(spec,g,&s)?;
    s.set_fault=spec["set_fault"].as_str().unwrap_or("").to_owned();
    S.with_borrow_mut(|v| *v = (depth != 0).then_some(s));''')
    edit(p,'            template | ((rid + 1) << 32)','''            let code=selection(s,rid);if code!=(rid+1){s.set_counts.encoded+=n as u64}
            template | (code << 32)''')
    edit(p,'if code != rid + 1 || !s.programs.contains_key(&rid)', 'if code != selection(s,rid) || !s.programs.contains_key(&rid)')
    edit(p,'        if let Some(internal) = s.issued.remove(&serial) {','''        if let Some(internal) = s.issued.remove(&serial) {
            if let Some(set)=&internal.set_data{
                s.set_counts.confirmed+=1;
                if s.record_links{s.set_links.push(json!({"consumer":serial,"consumer_rule":rid,"consumer_run":s.run,"root":set.root,"middle":set.middle,
                    "middle_run":set.run,"fact":[set.fact.cell,set.fact.op],"version":set.generation,"table":set.table,"fields":set.fields,"path":set.path,"ports":set.trail.as_ref().map(|x|x.as_slice())}));}
            }
            if s.set_plan.as_ref().is_some_and(|p|internal.path.as_slice()==[p.first]){s.set_counts.active_middles+=1}''')
    edit(p,'            if row.epoch < wm {','''            if let Some(receipt)=&o.set_data{
                let offered=if s.set_fault=="stale"{receipt.generation^1}else{receipt.generation};
                if offered!=row.epoch{s.set_counts.excluded_generation+=1;continue}
                if w!=Dependency::Fact(receipt.fact)||receipt.table!=t||receipt.generation!=row.epoch||receipt.run>=s.run||o.root!=receipt.root||
                   s.set_plan.as_ref().is_none_or(|p|receipt.path.as_slice()!=[p.first,p.second])||receipt.fields.len()!=row.values.len(){
                    return Err("invalid committed constructor Set receipt".into())
                }
                if receipt.fields.iter().zip(row.values.iter()).any(|(a,b)|crate::value::canon(a,&g.parents)!=crate::value::canon(b,&g.parents)){
                    s.set_counts.invalidated+=1;continue;
                }
                s.set_counts.opened+=1;
            }
            if row.epoch < wm {''')
    edit(p,'json!({"signed_commits":s.path_links,','json!({"set_publication":s.set_counts,"set_commits":s.set_links,"signed_commits":s.path_links,')
    a='''        if let Some(old) = self.lookup_canonical(t, &key)? {
            if let Some(receipt) = receipt {'''
    edit(g,a,'''        let signed_set=crate::strict_named::set_attempt(cell,op,t);
        if let Some(old) = self.lookup_canonical(t, &key)? {
            if signed_set{crate::strict_named::set_existing();}
            if let Some(receipt) = receipt {''')
    a='''            self.activate(
                FactRef {
                    cell,
                    op: op as u32,
                },
                t,
                &key,
                value,
                false,
            )?;'''
    edit(g,a,'''            let fact=FactRef{cell,op:op as u32};
            let proof=signed_set.then(||{
                let mut input=key.to_vec();input.push(value.clone());input
            });
            self.activate(fact,t,&key,value,false)?;
            if let Some(fields)=proof{
                crate::strict_named::capture_set(self,fact,t,fields)?;
            }''')
    edit(rt,'        if let Some(before)=integral_before{','        crate::strict_named::finish_set(result.is_ok())?;\n        if let Some(before)=integral_before{')
    edit(ex,'        eggfuse_cell_runtime::strict_named::configure','''        if !req["strict_named"]["set_publication"].is_null() && (req["source_sha256"].as_str()!=Some(digest.as_str())||req["strict_named"]["set_publication"]["target_sha256"].as_str()!=Some(digest.as_str())){return Err("incorrect Set authorization target".into())}
        eggfuse_cell_runtime::strict_named::configure''')
