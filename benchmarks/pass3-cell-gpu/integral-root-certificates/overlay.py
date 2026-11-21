"""Verify one-hop integral activations before the complete learned Run wave is issued."""
from pathlib import Path

def edit(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise ValueError(a)
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';rt=src/'runtime.rs';s=src/'stage_spine.rs'
    graph=src/'graph.rs'
    edit(graph,'    pub logical_facts_created: u64,','    pub logical_facts_created: u64,\n    pub integral_constructor_births:u64,')
    edit(graph,'        self.stats.logical_facts_created += 1;','        self.stats.logical_facts_created += 1;\n        self.stats.integral_constructor_births+=u64::from(self.program.tables[t].constructor);')
    (src/'integral_wave.rs').write_bytes((Path(__file__).parent/'integral.rs').read_bytes())
    with (src/'lib.rs').open('a') as f:f.write('\npub mod integral_wave;\n')
    edit(rt,'                    if let Some(residual)=crate::ordinary_witness::eligible(rid) {','''                    if crate::integral_wave::enabled(){self.stage_spine.integral_release(&self.graph,&mut self.entry_schedule,rid,wm,self.steps.len()+1)?;}
                    if let Some(residual)=crate::ordinary_witness::eligible(rid) {''')
    edit(rt,'        let result=self.apply_owned(rid,b,','''        let integral_before=crate::integral_wave::enabled().then(||crate::integral_wave::counters(&self.graph));
        let result=self.apply_owned(rid,b,''')
    edit(rt,'        crate::joint_root::end();','''        if let Some(before)=integral_before{crate::integral_wave::effects(before,crate::integral_wave::counters(&self.graph));}
        crate::joint_root::end();''')
    edit(rt,'        self.graph.spec_winner();','''        if crate::integral_wave::enabled(){let serial=crate::joint_root::consumed_serial().ok_or("integral source lacked an accepted external token")?;
            crate::integral_wave::commit(crate::stage_spine::integral_tag(stage_cursor.as_ref()),self.steps.len()+1,rid,serial,&mut b.values,&b.known)?;}
        self.graph.spec_winner();''')
    with (src/'joint_root.rs').open('a') as f:
        f.write('\npub(crate) fn consumed_serial()->Option<u64>{STATE.with_borrow(|s|s.as_ref().and_then(|s|s.active.map(|a|a.2)))}\n')
    edit(s,'pub struct Cursor {','pub struct Cursor {\n    integral_anchor:Option<(usize,Dependency,u64,usize)>,')
    edit(s,'fn fresh(root: Rc<Root>, producer: usize) -> Self {\n        Self {','fn fresh(root: Rc<Root>, producer: usize) -> Self {\n        Self {integral_anchor:None,')
    edit(s,'*self = Self::Live(Cursor {','*self = Self::Live(Cursor {integral_anchor:None,')
    edit(s,"'answer: for (_ordinal, (pivot, row, cursor)) in ready.into_iter().enumerate() {","'answer: for (_ordinal, (pivot, row, mut cursor)) in ready.into_iter().enumerate() {\n            if crate::integral_wave::enabled(){cursor.integral_anchor=Some((pivot,row.witness,row.epoch,cursor.state.output));}")
    with s.open('a') as f:f.write('''
pub(crate) fn integral_tag(step:Option<&Started>)->crate::integral_wave::Apply{
    use crate::integral_wave::Apply;
    match step{Some(Started::Root{id,..})=>Apply::External(*id),Some(Started::Live(c))=>Apply::Live(c.root.id,c.depth,c.integral_anchor),None=>Apply::Other}
}
impl Programs{
    pub(crate) fn integral_release(&self,g:&Graph,entries:&mut crate::entry_schedule::Scheduler,rid:usize,wm:u64,run:usize)->Result<()>{
        if !self.active_for_rule(rid){return Ok(())}
        let rule=&g.program.rules[rid];
        crate::integral_wave::with(|s|{
            s.begin_run(run);s.m.active_rule_releases+=1;
            entries.batches(g,rid,wm,|batch,_|{
                let pivot=batch.atom();
                let cursors=self.scheduled_cursors(rid,pivot,batch.table);
                let gram=s.grams.entry((rid,pivot)).or_insert_with(||{
                    if self.queries.get(rid,pivot).is_some(){crate::integral_wave::grammar(rule,pivot)}else{None}
                }).clone();
                for &(_,w) in batch.delta(){
                    s.m.delta_ports+=1;
                    let entry=batch.entry(w).ok_or("missing scheduled integral source entry")?;
                    #[cfg(feature="sparse-cells")]
                    let p=if self.entry_owns(rid,pivot,batch.table){entry.published()}else{cursors.and_then(|m|m.get(&w))};
                    #[cfg(not(feature="sparse-cells"))]
                    let p=cursors.and_then(|m|m.get(&w));
                    let Some(p)=p else{s.m.without_cursor+=1;continue};
                    #[cfg(feature="sparse-cells")]
                    let (root,producer,output)=match &p.base{
                        PublishedBase::Root(r,rid)=>(r.id,*rid,p.output),
                        PublishedBase::Solo{id,producer,..}=>(*id,*producer,p.output),
                        PublishedBase::Active(_)=>{s.m.deep_ports+=1;continue}
                    };
                    #[cfg(not(feature="sparse-cells"))]
                    let (root,producer,output)=if p.depth==1{(p.root.id,p.producer,p.state.output)}else{s.m.deep_ports+=1;continue};
                    let Some(owner)=s.roots.get(&root) else{s.m.owner_missing+=1;continue};
                    if owner.rule!=producer||owner.run>=run {s.m.stage_guard+=1;continue}
                    let Some(order)=&gram else{s.m.unsupported+=1;continue};
                    s.m.anchor_reads+=1;
                    let Some(row)=g.row(w)? else{s.m.negative+=1;continue};
                    if row.witness!=w||row.epoch!=entry.row.epoch||row.values!=entry.row.values||row.table!=entry.row.table{return Err("integral publication row disagreed with current source".into())}
                    let Some(candidate)=crate::integral_wave::execute(g,rule,pivot,order,&row,wm,&mut s.m)? else{s.m.negative+=1;continue};
                    s.offer(rid,pivot,root,producer,output,row.epoch,candidate);
                }
                Ok(())
            })?;Ok(())
        })
    }
}
''')
    p=crate/'examples/joint_witness_session.rs'
    edit(p,'        let initial_graph_ms=ingest_start.elapsed()', '''        eggfuse_cell_runtime::integral_wave::configure(req["integral_root"].as_str().unwrap_or("off"))?;
        let initial_graph_ms=ingest_start.elapsed()''')
    edit(p,'        report["spec_cells"]=runtime.graph.spec_cells_report();','''        report["spec_cells"]=runtime.graph.spec_cells_report();
        report["integral_root"]=eggfuse_cell_runtime::integral_wave::report();''')
