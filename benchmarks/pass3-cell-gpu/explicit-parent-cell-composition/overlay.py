from pathlib import Path
from shutil import copyfile

def edit(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise ValueError(a)
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';j=src/'joint_root.rs';r=src/'runtime.rs';a=src/'adaptive_rows.rs';sg=src/'single_witness.rs';g=src/'graph.rs'
    copyfile(Path(__file__).parent/'strict.rs',src/'strict_named.rs')
    with (src/'lib.rs').open('a') as f:f.write('\npub mod strict_named;\n')
    edit(j,"struct Decoded{serial:u64,","struct Decoded{strict_code:usize,serial:u64,")
    for old in ('Some(Decoded{serial,origin,run,','Decoded{serial:state.serial,','Decoded{serial,origin:"single",run,'):
        edit(j,old,old.replace('Decoded{','Decoded{strict_code:0,'))
    p=src/'adaptive_root_page.rs';edit(p,'        Some(Decoded {','        Some(Decoded {strict_code:(w[4]>>32) as usize,')
    edit(p,'template: usize::try_from(w[4]).ok()?,','template:usize::try_from(w[4]&0xffffffff).ok()?,')
    edit(p,'        let mut words = Vec::with_capacity(8 + 3 * inputs.len());','''        let template=crate::strict_named::tag(rid,template,inputs.len());
        let mut words = Vec::with_capacity(8 + 3 * inputs.len());''')
    p=src/'multi_root_pages.rs';edit(p,'        Some(Decoded {','        Some(Decoded {strict_code:p.template>>32,')
    edit(p,'            template: p.template,','            template:p.template&0xffffffff,')
    edit(p,'        let invalid_version = st.mode','        let template=crate::strict_named::tag(rid,template,count);\n        let invalid_version = st.mode')
    edit(j,'        state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));','''        crate::strict_named::begin(r.serial,rid,!r.refs.is_empty(),r.strict_code)?;
        state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));''')
    edit(j,'            s.allocated+=1;','            crate::strict_named::fresh(id);s.allocated+=1;')
    edit(j,'pub(crate) fn end(){STATE.with_borrow_mut','pub(crate) fn end(){crate::strict_named::end();STATE.with_borrow_mut')
    edit(g,'        self.stats.logical_facts_created += 1;','        self.stats.logical_facts_created += 1;crate::strict_named::output(f,t,self.epoch);')
    with g.open('a') as f:f.write('''
impl Graph{
    pub(crate) fn strict_member(&self,t:usize,w:Dependency)->bool{
        matches!(w,Dependency::Fact(f) if self.members[t].contains(&f.ordered_id()))
    }
}
''')
    edit(r,'        let wave_width=crate::ordinary_witness::wave_width();','''        crate::strict_named::run(self.steps.len()+1);
        let wave_width=crate::ordinary_witness::wave_width();''')
    edit(a,'        let sources: &[SourceHeader] = if let Some(pivot) = p.pivot {','''        let signed=if model.certified_inputs && self.rows.batch && !self.residual && self.rows.prefilter==2{
            crate::strict_named::open(g,rid,wm)?
        }else{None};
        let prepared;
        let sources:&[SourceHeader]=if let Some(h)=&signed{
            prepared=h.iter().map(|&(w,e)|SourceHeader::from_published(w,e,self.initial.contains(&w))).collect::<Vec<_>>();&prepared
        }else if let Some(pivot) = p.pivot {''')
    edit(a,'        let can_prefilter = self.rows.prefilter == 2','        let can_prefilter = signed.is_none() && self.rows.prefilter == 2')
    edit(a,'if self.rows.signature_budget && !can_prefilter','if signed.is_none() && self.rows.signature_budget && !can_prefilter')
    edit(a,'let closed=model.certified_inputs && self.rows.batch && !self.residual &&','let closed=signed.is_some() && model.certified_inputs && self.rows.batch && !self.residual &&')
    edit(a,'        let mut emitted = 0;','''        if signed.is_some() && !closed{return Err("strict closed release failed its own prebound order".into())}
        let mut emitted = 0;''')
    edit(sg,'crate::integral_wave::with(|s|if s.roots.contains_key(&lane.root){Ok(())}else{Err("unauthenticated integral seed".to_string())})?;','crate::strict_named::link(closed.first_root+i as u64,lane.root,rid,lane.w)?;')
    ex=crate/'examples/joint_witness_session.rs'
    edit(ex,'        eggfuse_cell_runtime::integral_packets::configure(req["integral_packets"]==true,audit,req["integral_release_fault"]==true);','''        if req["integral_root"].as_str().is_some_and(|n|n!="off")||req["integral_packets"]==true{return Err("explicit-parent prototype requires ordinary integral path disabled".into())}
        eggfuse_cell_runtime::strict_named::configure(&req["strict_named"],&runtime.graph)?;
        eggfuse_cell_runtime::integral_packets::configure(req["strict_named"]["depth"].as_u64().unwrap_or(0)>0,audit,false);''')
    edit(ex,'        report["integral_packets"]=','        report["strict_named"]=eggfuse_cell_runtime::strict_named::report();\n        report["integral_packets"]=')
    edit(a,'        let prepared;','''        if let Some(h)=&signed{
            let n=h.len();
            if !self.rows.detailed && !self.archive_winners{
                if self.rows.fixed!=Some(4)||n>16_777_216{return Err("unsupported strict recurrence shape".into())}
                crate::integral_packets::strict_seal(g.epoch,rid,wm,self.serial+1,n)?;
                self.serial+=n as u64;crate::strict_named::source_work(n,false);
                // Sole-table semi-naive winners are all fresh. The certified
                // policy sends all such rows. Only these three counts feed
                // its recurrent update; no per-child model logit is needed.
                return Ok((vec![],n,n as f32,n))
            }
            crate::strict_named::source_work(n,true);
        }
        let prepared;''')
    with (src/'integral_packets.rs').open('a') as f:f.write('''
pub(crate) fn strict_seal(epoch:u64,rid:usize,wm:u64,first_model:u64,n:usize)->Result<()>{
    S.with_borrow_mut(|s|{
        let s=s.as_mut().ok_or("strict internal verifier unavailable")?;
        let bank=s.collect.remove(&(rid,0)).ok_or("strict fixed outputs missing")?;
        if bank.len()!=n{return Err("strict output cardinality".into())}
        let lanes=bank.into_values().collect::<Option<Vec<_>>>().ok_or("duplicate signed address")?;
        let first_root=crate::joint_root::internal_serials(n)?;
        s.counts.closed_lanes+=n as u64;s.counts.closed_banks+=1;s.counts.peak_bank=s.counts.peak_bank.max(n);
        *s.closed_rules.entry(rid).or_default()+=n as u64;
        assert!(s.ready.insert(rid,Closed{pivot:0,first_model,first_root,scores:[0.;2],lanes,ep:epoch,wm}).is_none());Ok(())
    })
}
''')
    p=src/'entry_schedule.rs'
    with p.open('a') as f:f.write('''
impl Scheduler{
    pub(crate) fn strict_single_entry(&self,rid:usize,table:usize)->bool{
        self.plan.rules[rid].iter().any(|c|c.atom==0 && self.plan.nodes[c.node].table==table)
    }
}
''')
    p=src/'stage_spine.rs';old='''        let mut routed = Vec::new();
        let mut owned = BTreeSet::new();
        entries.batches(g, rid, watermark, |batch, _| {'''
    edit(p,old,'''        let mut routed = Vec::new();
        let mut owned = BTreeSet::new();
        if crate::strict_named::closed(rid){
            let rule=&g.program.rules[rid];
            let Call::Table(t)=rule.query[0].call else{return Err("strict Spine pivot not a table".into())};
            if rule.query.len()!=1{return Err("strict Spine needs a sole pivot".into())}
            if entries.strict_single_entry(rid,t) && let Some(map)=self.scheduled_cursors(rid,0,t){
                for (i,answer) in rows.iter().enumerate(){
                    let w=answer.known.receipt(0).ok_or("missing strict returned port")?;
                    crate::strict_named::spine_point();
                    let Some(cursor)=map.get(&w)else{continue};
                    let row=g.row(w)?.ok_or("retired strict Spine receipt")?;
                    if row.hidden||row.table!=t||row.epoch<watermark{return Err("stale strict Spine owner".into())}
                    routed.push((0,Rc::new(row),cursor.expand()));owned.insert(i);
                }
            }
        }else{entries.batches(g, rid, watermark, |batch, _| {''')
    edit(p,'        })?;\n        let count = routed.len();','        })?;}\n        let count = routed.len();')
