from pathlib import Path
from shutil import copyfile
def edit(p,old,new):
    s=p.read_text()
    if s.count(old)!=1:raise ValueError(old)
    p.write_text(s.replace(old,new))

def install(crate):
    src=crate/'src';s=src/'strict_named.rs';pub=src/'ripsat_set_publication.rs';g=src/'graph.rs';j=src/'joint_root.rs';ex=crate/'examples/joint_witness_session.rs'
    copyfile(Path(__file__).parent/'higher.rs',src/'higher_cell.rs')
    with s.open('a') as f:f.write('\ninclude!("higher_cell.rs");\n')
    edit(s,'struct State {set_plan:', 'struct State {higher:HigherState,set_plan:')
    edit(s,'struct Owner {set_data:', 'struct Owner {higher_handle:Option<HigherHandle>,set_data:')
    edit(s,'let owner = Owner {set_data:None,','let owner = Owner {higher_handle:None,set_data:None,')
    edit(pub,'        let o = Owner {','        let o = Owner {higher_handle:None,')
    edit(s,'s.set_plan=plan_set(spec,g,&s)?;','s.set_plan=plan_set(spec,g,&s)?;configure_higher(spec,g,&mut s)?;')
    edit(s,'json!({"set_publication":s.set_counts,','json!({"higher_cell":s.higher.report(),"set_publication":s.set_counts,')
    edit(pub,'    (rid + 1)\n        | if', '''    ((rid+1)|if s.higher.enabled && s.set_plan.as_ref().is_some_and(|p|p.first[0]==rid){1usize<<30}else{0})
        | if''')
    edit(s,'let code=selection(s,rid);if code!=(rid+1)', 'let code=selection(s,rid);if code & (1usize<<30)!=0{s.higher.stats.encoded+=n as u64;}if code!=(rid+1)')
    edit(j,'crate::strict_named::begin(r.serial,rid,!r.refs.is_empty(),r.strict_code)?;','''crate::strict_named::begin(r.serial,rid,!r.refs.is_empty(),r.strict_code)?;
        crate::strict_named::higher_begin(r.serial,rid,epoch,&r.refs)?;''')
    edit(g,'crate::strict_named::output(f,t,self.epoch);','crate::strict_named::output(f,t,self.epoch);crate::strict_named::higher_first(f,t,self.epoch);')
    edit(g,'        let signed_set=crate::strict_named::set_attempt(cell,op,t);\n','')
    old='''        let key = self.inline_arguments(cell, aa)?;
        let value = self.argument(cell, v)?;
        if !self.program.tables[t].virtual_fact {'''
    edit(g,old,'''        let signed_set=crate::strict_named::set_attempt(cell,op,t);let direct_clock=crate::strict_named::direct_operand_clock(signed_set);
        let (key,value)=if let Some(named)=crate::strict_named::higher_set_inputs(self,cell,op,t)?{named}
            else{(self.inline_arguments(cell,aa)?,self.argument(cell,v)?)};
        crate::strict_named::direct_operands_done(direct_clock);
        if !self.program.tables[t].virtual_fact {''')
    edit(pub,'S.with_borrow_mut(|s| s.as_mut().unwrap().set_counts.existing_key += 1)','''S.with_borrow_mut(|v|{let s=v.as_mut().unwrap();s.set_counts.existing_key+=1;
        if s.higher.enabled{if let Some(a)=&s.active{if let Some(b)=s.higher.pending.get_mut(&a.root){b.existing=true;}}}})''')
    edit(pub,'        let mut rederived=g.inline_arguments(f.cell,args)?.into_vec();rederived.push(g.argument(f.cell,assigned)?);\n        if rederived!=fields{return Err("Set operand packet disagrees with current named frame".into())}', '''        let check_time=s.higher.profile.then(Instant::now);
        if !s.higher.enabled||s.record_links{
            let mut rederived=g.inline_arguments(f.cell,args)?.into_vec();rederived.push(g.argument(f.cell,assigned)?);
            if rederived!=fields{return Err("Set operand packet disagrees with current named frame".into())}
        }''')
    edit(pub,'fields,path,trail});Ok(())','fields,path,trail});if let Some(t)=check_time{s.higher.stats.capture_ns+=t.elapsed().as_nanos() as u64}Ok(())')
    edit(pub,'pub(crate) fn finish_set(success: bool) -> Result<()> {','pub(crate) fn finish_set(success: bool) -> Result<()> {\n    if higher_after(success)?{return Ok(())}')
    edit(pub,'        let p = s.set_plan.as_ref().ok_or("unconfigured Set release")?;','        let clock=s.higher.profile.then(Instant::now);\n        let p = s.set_plan.as_ref().ok_or("unconfigured Set release")?;')
    edit(pub,'        s.set_counts.published += 1;','        s.set_counts.published += 1;if let Some(t)=clock{s.higher.stats.direct_publication_ns+=t.elapsed().as_nanos() as u64}')
    edit(s,'            if let Some(set)=&internal.set_data{','''            if internal.higher_handle.is_some(){s.higher.stats.terminal_commits+=1;}
            let set_value=if let Some(id)=internal.higher_handle{Some(s.higher.branch(id)?)}else{internal.set_data.as_deref()};
            if let Some(set)=set_value{''')
    edit(s,'            if let Some(receipt)=&o.set_data{','''            let receipt_clock=(s.higher.profile && (o.higher_handle.is_some()||o.set_data.is_some())).then(Instant::now);
            let fresh=if let Some(id)=o.higher_handle{s.higher.stats.lookup_checks+=1;Some(s.higher.branch(id)?)}else{o.set_data.as_deref()};
            if let Some(receipt)=fresh{''')
    edit(s,'                s.set_counts.opened+=1;','                s.set_counts.opened+=1;if let Some(t)=receipt_clock{s.higher.stats.validation_ns+=t.elapsed().as_nanos() as u64}')
    edit(src/'runtime_completion.rs','        self.graph.header_publish();','        crate::strict_named::higher_flush(&self.graph)?;\n        self.graph.header_publish();')
    edit(ex,'    let args: Vec<_> = std::env::args_os().skip(1).collect();','''    let args:Vec<_>=std::env::args_os().skip(1).collect();
    if args.len()==1 && args[0]=="--higher-cell-capabilities"{println!("{}",eggfuse_cell_runtime::strict_named::higher_capabilities());return Ok(())}''')
    edit(ex,'        let ms = start.elapsed().as_secs_f64() * 1000.;','        eggfuse_cell_runtime::strict_named::higher_close(&runtime.graph)?;\n        let ms = start.elapsed().as_secs_f64() * 1000.;')
