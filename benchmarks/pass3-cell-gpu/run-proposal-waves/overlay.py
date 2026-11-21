from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def rep(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    src=crate/'src';p=src/'single_witness.rs';s=p.read_text()
    s=rep(s,'pub(crate) struct Trial{','type Offered = Vec<(Token,[u8;N],bool)>;\npub(crate) struct Trial{\n    waiting_wave:BTreeMap<usize,(u64,u64,u64,Offered)>,')
    s=rep(s,'Ok(Self{rows:RowEngine::default(),','Ok(Self{waiting_wave:Default::default(),rows:RowEngine::default(),')
    start=s.index('    pub fn generate(&mut self,g:&Graph,rid:usize,wm:u64)->Result<Vec<Instance>>{')
    end=s.index('        let verification_start=',start)
    prep=s[start:end].replace('pub fn generate(&mut self,g:&Graph,rid:usize,wm:u64)->Result<Vec<Instance>>{',
                              'fn wave_issue_single(&mut self,g:&Graph,rid:usize,wm:u64)->Result<(Offered,usize)>{')
    # n and f are used by capture mode later; waves accept only the deployed learned configuration.
    new=prep+'''        Ok((offers,n))
    }
    pub(crate) fn prepare_single_wave(&mut self,g:&Graph,rid:usize,wm:u64)->Result<()> {
        if self.residual || self.mode!="learned" || !self.rows.batch{return Err("wave needs deployed complete learned single issuer".into())}
        let (offers,_)=self.wave_issue_single(g,rid,wm)?;
        let n=offers.len();
        if self.waiting_wave.insert(rid,(g.epoch,wm,g.stats.unions,offers)).is_some(){return Err("duplicate rule in wave".into())}
        crate::ordinary_witness::wave_mark(true,n);Ok(())
    }
    pub(crate) fn wave_is_empty(&self)->bool{self.waiting_wave.is_empty()}
    pub fn generate(&mut self,g:&Graph,rid:usize,wm:u64)->Result<Vec<Instance>>{
        let p=self.plans[rid].clone().ok_or("unproved grammar")?;let r=&g.program.rules[rid];
        let (offers,n)=if let Some((ep,watermark,unions,offers))=self.waiting_wave.remove(&rid) {
            if ep!=g.epoch || watermark!=wm || unions!=g.stats.unions{return Err("single wave source changed before validation".into())}
            crate::ordinary_witness::wave_single_consumed();
            let n=offers.len();(offers,n)
        }else{self.wave_issue_single(g,rid,wm)?};
        let delivered=offers.iter().filter(|v|v.2).count();
'''
    # Preserve n and delivered from original issuance for stats without rescoring or re-counting offers.
    new=new.replace('Result<(Offered,usize)>','Result<(Offered,usize,usize)>').replace('Ok((offers,n))','Ok((offers,n,delivered))').replace('let (offers,_)=','let (offers,n,delivered)=').replace('        let n=offers.len();\n        if self.waiting_wave','        let issued=offers.len();\n        if self.waiting_wave').replace('(g.epoch,wm,g.stats.unions,offers)', '(g.epoch,wm,g.stats.unions,offers,n,delivered)').replace('wave_mark(true,n)','wave_mark(true,issued)').replace('let (offers,n)=if let Some((ep,watermark,unions,offers))','let (offers,n,delivered)=if let Some((ep,watermark,unions,offers,n,delivered))').replace('let n=offers.len();(offers,n)','(offers,n,delivered)').replace('        let delivered=offers.iter().filter(|v|v.2).count();\n','')
    s=s[:start]+new+s[end:];s=s.replace('waiting_wave:BTreeMap<usize,(u64,u64,u64,Offered)>','waiting_wave:BTreeMap<usize,(u64,u64,u64,Offered,usize,usize)>');p.write_text(s)
    p=src/'ordinary_witness.rs';s=p.read_text()
    s=rep(s,'struct Store {','struct Store {wave:RunWave,')
    s=rep(s,'let s=Store{','let s=Store{wave:RunWave::default(),')
    s=rep(s,'"pages":s.pages,','"wave":s.wave.stats,"pages":s.pages,')
    a='        let rule=&g.program.rules[rid];'
    s=rep(s,a,'''        let deferred=if s.wave.width!=0 && !s.wave.preparing{s.wave.waiting.remove(&rid)}else{None};
        if let Some(saved)=&deferred{
            if (saved.epoch,saved.run,saved.watermark,saved.unions)!=(g.epoch,run,mark,g.stats.unions){return Err("multi wave source changed before verification".into())}
            s.counts.calls-=1;
            s.wave.stats.validated_multi_sets+=1;
            if saved.pages.is_empty(){return Ok(vec![])}
        }
        if s.wave.preparing{
            if s.wave.waiting.insert(rid,WaitingPageBank{epoch:g.epoch,run,watermark:mark,unions:g.stats.unions,remaining:vec![],pages:vec![],tuples:0}).is_some(){
                return Err("duplicate multi source issue in one wave".into())
            }
        }
'''+a)
    s=rep(s,'        for (i,(id,_,_)) in ins.iter().enumerate().rev(){','''        if let Some(saved)=&deferred {remaining.clone_from(&saved.remaining);} else {
        for (i,(id,_,_)) in ins.iter().enumerate().rev(){''')
    s=rep(s,'        let prepared=clock.map','        }\n        let prepared=clock.map')
    s=rep(s,'let mut out=vec![];let mut raw=vec![];if s.accel>=4{','let mut out=vec![];let mut raw=vec![];if deferred.is_some(){}else if s.accel>=4{')
    a='        let issued=clock.map'
    s=rep(s,a,'''        if s.wave.preparing {
            let mut groups=std::mem::take(&mut s.pending_pages);
            if !s.page_refs.is_empty(){groups.push(std::mem::take(&mut s.page_refs));}
            let mut pages=Vec::with_capacity(groups.len());let mut tuples=0;
            for refs in groups{
                let bank=crate::joint_root::multi_page(g.epoch,rid,c.pick_count,refs,s.page_fault)?;
                tuples+=bank.count();s.max_sealed_page=s.max_sealed_page.max(bank.count());pages.push(bank);
            }
            if !raw.is_empty() || !s.flat.is_empty(){return Err("unexpected nonpage wave output".into())}
            let save=s.wave.waiting.get_mut(&rid).unwrap();save.remaining=c.remaining;save.tuples=tuples;save.pages=pages;
            return Ok(vec![])
        }
'''+a)
    s=rep(s,'if s.page && (!s.pending_pages.is_empty() || !s.page_refs.is_empty()){','if s.page && (deferred.is_some() || !s.pending_pages.is_empty() || !s.page_refs.is_empty()){')
    s=rep(s,'let mut pages=Vec::with_capacity(s.pending_pages.len());\n                let mut total=0;',
        'let mut pages=deferred.map_or_else(||Vec::with_capacity(s.pending_pages.len()),|v|v.pages);\n                let mut total:usize=pages.iter().map(|p|p.count()).sum();')
    p.write_text(s+'\ninclude!("neural_run_wave.rs");\n');copyfile(HERE/'waves.rs',src/'neural_run_wave.rs')
    p=src/'runtime.rs';s=p.read_text()
    a='        for rid in rules {\n            // Only semi-naive rules clear'
    s=rep(s,a,'''        let wave_width=crate::ordinary_witness::wave_width();
        let span=if wave_width==0{rules.len().max(1)}else{wave_width};
        for batch in rules.chunks(span){
            if wave_width>0{
                if self.stage_spine.single.as_ref().is_some_and(|v|!v.wave_is_empty()){return Err("undrained single issue wave".into())}
                crate::ordinary_witness::wave_begin()?;
                for &rid in batch{
                    if !self.dirty[rid] && (!self.profile_queries || self.graph.program.rules[rid].seminaive){continue}
                    let wm=self.ready_sets.as_ref().map_or(self.watermarks[rid],|r|self.watermarks[rid].max(r.watermark(rid)));
                    if let Some(residual)=crate::ordinary_witness::eligible(rid) {
                        if residual{return Err("wave does not accept multi residuals".into())}
                        let facts=self.stage_spine.alias_query_facts(&self.graph,rid);
                        crate::ordinary_witness::prepare_multi_wave(&self.graph,rid,self.steps.len()+1,wm,&facts)?;
                    }else if let Some(model)=self.stage_spine.single.as_mut() && model.accepts(rid) {
                        model.prepare_single_wave(&self.graph,rid,wm)?;
                    }
                }
                crate::ordinary_witness::wave_sealed();
            }
            for &rid in batch {
            // Only semi-naive rules clear''')
    a='        if let (Some(id),Some(sets)) = (set_id,&mut self.ready_sets) {'
    p.write_text(rep(s,a,'''        }
        if wave_width>0 {
            if self.stage_spine.single.as_ref().is_some_and(|v|!v.wave_is_empty()){return Err("unverified single proposals at Run boundary".into())}
            crate::ordinary_witness::wave_begin()?;
        }
'''+a))
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(rep(p.read_text(),a,'''        if let Some(n)=req["proposal_wave"].as_u64(){ordinary_witness::configure_run_wave(n)?;}
'''+a))
