from pathlib import Path

def edit(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise ValueError(a)
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';single=src/'single_witness.rs';row=src/'adaptive_rows.rs';stage=src/'stage_spine.rs';integral=src/'integral_wave.rs'
    (src/'integral_packets.rs').write_bytes((Path(__file__).parent/'packets.rs').read_bytes())
    with (src/'lib.rs').open('a') as f:f.write('\npub mod integral_packets;\n')
    with (src/'integral_packets.rs').open('a') as f:f.write('''
pub(crate) fn start_run(run:usize){S.with_borrow_mut(|s|{if let Some(s)=s && s.run!=run{assert!(s.ready.is_empty());s.collect.clear();s.run=run;}});}
''')
    rt=src/'runtime.rs'
    a='                    if crate::integral_wave::enabled(){self.stage_spine.integral_release'
    edit(rt,a,'                    crate::integral_packets::start_run(self.steps.len()+1);\n'+a)
    a='        self.graph.spec_winner();'
    edit(rt,a,'        if let Some(serial)=crate::joint_root::consumed_serial(){crate::integral_packets::consume(serial);}\n'+a)
    edit(integral,'pub(crate) struct Candidate {','pub(crate) struct Candidate {\n    pub epoch:u64,')
    edit(integral,'    let mut refs = vec![(p, row.witness)];','    let mut refs = vec![(p, row.witness)];\n    let mut epoch=row.epoch;')
    edit(integral,'                refs.push((i, v.witness));','                refs.push((i,v.witness));epoch=epoch.max(v.epoch);')
    edit(integral,'Ok(Some(Candidate { values, refs }))','Ok(Some(Candidate{values,refs,epoch}))')
    edit(integral,'        self.m.offers += 1;','''        self.m.offers += 1;
        crate::integral_packets::release(self.run,rid,pivot,answer.refs[0].1,version,answer.epoch,&answer.values,&answer.refs,root);''')
    edit(row,'        let mut emitted = 0;', '''        let closed=model.certified_inputs && self.rows.batch && !self.residual &&
            crate::integral_packets::certify(g.epoch,rid,p.pivot,sources,&scores,wm,self.serial+1,self.floors[rid])?;
        let mut emitted = 0;''')
    edit(row,'            let recipe = if send && !self.rows.batch {','''            if closed{emitted+=usize::from(send);continue}
            let recipe = if send && !self.rows.batch {''')
    edit(row,'        self.rows.stats.emitted += emitted as u64;','        if !closed{self.rows.stats.emitted += emitted as u64;}')
    edit(single,'        let mut answers=Vec::new();let mut hist=BTreeMap::new();','''        let mut answers=Vec::new();let mut hist=BTreeMap::new();
        if let Some((closed,audit))=crate::integral_packets::take(rid,g.epoch,wm)?{
            if !offers.is_empty(){return Err("closed source occurrence also received external packets".into())}
            for (i,lane) in closed.lanes.into_iter().enumerate(){
                crate::integral_wave::with(|s|if s.roots.contains_key(&lane.root){Ok(())}else{Err("unauthenticated integral seed".to_string())})?;
                if g.visible_epoch(lane.w)!=Some(lane.version)||lane.epoch<wm{return Err("integral parent no longer visible".into())}
                let local_id=closed.first_model+i as u64;
                let wire_id=closed.first_root+i as u64;
                let mut known=vec![None;r.query.len()];
                for &(atom,w) in &lane.refs{known[atom]=Some(w);}
                let receipt=crate::joint_root::internal_point(g.epoch,rid,closed.pivot,lane.w,lane.version,wire_id)?;
                let root_recipe=crate::joint_root::bind(Some(receipt),g,rid,&known,&lane.values)?.ok_or("internal root projection failed")?;
                let token=Token{recipe:None,id:local_id,rid,w:Some(lane.w),guarded:false,version:lane.version,initial:self.initial.contains(&lane.w),score:closed.scores[usize::from(lane.version>=wm)]};
                if audit{
                    let saved=self.work;
                    let source=self.check(g,r,&p,&token,wm)?.ok_or("internally released binding not matched by source")?;
                    self.work=saved;
                    if source.values!=lane.values||source.epoch!=lane.epoch||!lane.refs.iter().all(|&(a,w)|source.known.receipt(a)==Some(w)){return Err("internal slot or source version differs".into())}
                }
                let values=r.inputs.iter().map(|s|lane.values[s].clone()).collect();
                let witnesses=if self.archive_winners{known.iter().enumerate().filter_map(|(a,w)|w.map(|d|(a,address(d)))).collect()}else{vec![]};
                let mut binding=Instance::matched(lane.values,QueryFacts::Ports(known),lane.epoch);
                binding.known=binding.known.tagged(Mark{root_recipe:Some(root_recipe),token,values,witnesses});
                crate::integral_packets::issued(wire_id);self.work[5]+=1;answers.push(binding);
            }
        }''')
    with (src/'joint_root.rs').open('a') as f:f.write('''
pub(crate) fn internal_serials(n:usize)->Result<u64>{
    STATE.with_borrow_mut(|s|{let s=s.as_mut().ok_or("internal source lacks a root verifier")?;
        if !matches!(s.encoding,Encoding::CheckedSlots){return Err("integral source needs checked slots".into())}
        let first=s.serial+1;s.serial=s.serial.checked_add(n as u64).ok_or("internal serial overflow")?;Ok(first)})
}
pub(crate) fn internal_point(run:u64,rid:usize,atom:usize,row:Dependency,version:u64,serial:u64)->Result<Recipe>{
    STATE.with_borrow(|s|{let s=s.as_ref().ok_or("missing internal root configuration")?;
        let layout=s.layout.get(rid).ok_or("missing internal rule layout")?.clone();
        Ok(Recipe(Body::Resident(Rc::new(Decoded{serial,origin:"single",run,template:layout.template,layout,refs:vec![Ref{atom,row,version}],ports:None}))))})
}
''')
    ex=crate/'examples/joint_witness_session.rs'
    edit(ex,'        eggfuse_cell_runtime::integral_wave::configure','''        eggfuse_cell_runtime::integral_packets::configure(req["integral_packets"]==true,audit,req["integral_release_fault"]==true);
        eggfuse_cell_runtime::integral_wave::configure''')
    edit(ex,'        report["integral_root"]=eggfuse_cell_runtime::integral_wave::report();','''        report["integral_root"]=eggfuse_cell_runtime::integral_wave::report();
        report["integral_packets"]=eggfuse_cell_runtime::integral_packets::report();''')
