"""Install over the linked, typed joint-root forest and sealed multi-witness shortlist."""
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent

def sub(s,before,after):
    if s.count(before)!=1:raise ValueError(f'unsupported runtime near {before[:85]!r}: {s.count(before)}')
    return s.replace(before,after)

def install(crate):
    src=Path(crate)/'src'
    file=src/'ordinary_witness.rs';s=file.read_text()
    s=sub(s,'struct Store {root_offers:', 'struct Store {signatures:SignatureJoin,profiling:bool,profile:Vec<RuleProfile>,frame_delta:bool,delta_stats:DeltaStats,frame_changes:HashMap<usize,DeltaFrame>,pair_mode:u8,pair_stats:PairStats,neural_columns:NeuralColumns,reverse_masks:Vec<u16>,raw_cache:RawCache,root_offers:')
    s=sub(s,'let (hint_fault,mode)=', '''let (profiling,mode)=if let Some(m)=mode.strip_prefix("profile"){(true,m)}else{(false,mode)};
    let (global,mode)=if let Some(s)=mode.strip_prefix("global"){(true,s)}else{(false,mode)};
    let (frame_delta,mode)=if let Some(m)=mode.strip_prefix("rowdelta"){(true,m)}else{(false,mode)};
    let (pair_mode,mode)=if let Some(s)=mode.strip_prefix("corrguard"){(4,s)}else if let Some(s)=mode.strip_prefix("pairguard"){(3,s)}else if let Some(s)=mode.strip_prefix("paircols"){(1,s)}else if let Some(s)=mode.strip_prefix("pairdelta"){(2,s)}else{(0,mode)};
    let (incremental,mode)=if let Some(m)=mode.strip_prefix("tuplememo"){(true,m)}else{(false,mode)};
    let (hint_fault,mode)=''')
    s=sub(s,'let s=Store{root_offers:', 'if global && (mode!="learned" || radius>2){return Err("unsupported global signature index".into());}\n    let s=Store{signatures:SignatureJoin::new(global),profiling,profile:vec![RuleProfile::default();program.rules.len()],frame_delta,delta_stats:Default::default(),frame_changes:HashMap::new(),pair_mode,pair_stats:Default::default(),neural_columns:Default::default(),reverse_masks:(0..(1u16<<B)).filter(|m|m.count_ones()<=radius).collect(),raw_cache:RawCache::new(incremental),root_offers:')
    s=sub(s,'json!({"shortlist":s.memo_counts,', 'json!({"signature_stats":s.signatures.stats,"rule_profile":if s.profiling{json!(s.profile)}else{Json::Null},"delta_stats":s.delta_stats,"pair_stats":s.pair_stats,"raw_cache":s.raw_cache.counts,"shortlist":s.memo_counts,')
    s=sub(s,'s.emit_stack(&c,&steps,0,0,&mut vec![],&mut vec![None;slots],&mut raw)?;', '''if s.pair_mode>0 && steps.len()==2 && !steps[1].shared.is_empty(){
                s.emit_two(&c,&steps,&mut raw)?;
            }else if s.raw_cache.enabled{
                s.emit_cached(&c,&steps,slots,&mut raw)?;
            }else{
                s.emit_stack(&c,&steps,0,0,&mut vec![],&mut vec![None;slots],&mut raw)?;
            }''')
    s=sub(s,"        let mut rows=vec![];let mut max_epoch=0;", """        if self.frame_delta{
            if let Some(frame)=self.update_frame(g,t,version)?{return Ok(frame);}
            self.delta_stats.rebuilt+=1;
        }
        let mut rows=vec![];let mut max_epoch=0;""")
    s=sub(s,"        let mut remaining=vec![0;ins.len()+1];","""        let clock=s.profiling.then(std::time::Instant::now);
        let initial=(s.counts.raw_tuples,s.counts.root_offers,s.counts.approximate_visits,s.counts.verified_parent_tuples);
        let mut remaining=vec![0;ins.len()+1];""")
    s=sub(s,"        s.run=run;s.rule=rid;", """        let prepared=clock.map(|_|std::time::Instant::now());
        s.run=run;s.rule=rid;""")
    s=sub(s,"        if c.sealing{\n            s.counts.peak_rule_tuples=", """        let issued=clock.map(|_|std::time::Instant::now());
        if c.sealing{
            s.counts.peak_rule_tuples=""")
    s=sub(s,"        if s.trial_attempts>=s.cap{s.counts.exhausted+=1;}", """        if let (Some(start),Some(mid),Some(sealed))=(clock,prepared,issued){
            let p=&mut s.profile[rid];p.calls+=1;p.picks=c.pick_count;
            p.frame_ms+=(mid-start).as_secs_f64()*1000.;
            p.issuance_ms+=(sealed-mid).as_secs_f64()*1000.;
            p.validation_ms+=sealed.elapsed().as_secs_f64()*1000.;
            p.raw+=s.counts.raw_tuples-initial.0;p.root_visits+=s.counts.root_offers-initial.1;
            p.signature_visits+=s.counts.approximate_visits-initial.2;p.checks+=s.counts.verified_parent_tuples-initial.3;
        }
        if s.trial_attempts>=s.cap{s.counts.exhausted+=1;}""")
    file.write_text(s+'\ninclude!("incremental_raw.rs");\n')
    runtime=src/"runtime_completion.rs"
    old=runtime.read_text();anchor="        self.publication.publish("
    runtime.write_text(sub(old,anchor,"        crate::ordinary_witness::changed_frame_rows(&self.graph);\n"+anchor))

    file=src/'ordinary_shortlist.rs';s=file.read_text()
    entry=s.index('        if i==steps.len(){');end=s.index('            return Ok(())',entry)
    terminal=s[entry+len('        if i==steps.len(){'):end]
    s=s[:entry]+'''        if i==steps.len(){
            if self.raw_cache.capturing{
                self.raw_cache.save(epoch,&self.flat_offsets);
            }
            self.seal_raw(c,steps,path,raw);\n'''+s[end:]
    # Offsets index only the current snapshot; corresponding stable source addresses remain authoritative.
    s=sub(s,'if self.accel>=5{self.flat_offsets.push(j as u32);}', 'if self.accel>=5 || self.raw_cache.capturing{self.flat_offsets.push(j as u32);}')
    s=sub(s,'if self.accel>=5{self.flat_offsets.pop();}', 'if self.accel>=5 || self.raw_cache.capturing{self.flat_offsets.pop();}')
    s+='\nimpl Store {\nfn seal_raw(&mut self,c:&Context,steps:&[StackStep],path:&Vec<Dependency>,raw:&mut Vec<Vec<Dependency>>){'+terminal+'\n}\n}\n'
    file.write_text(s)
    shutil.copyfile(HERE/'incremental.rs',src/'incremental_raw.rs')
    file=src/'ordinary_witness.rs';s=file.read_text()
    s=sub(s,'struct Frame {generation:u64,','struct Frame {table:usize,generation:u64,')
    s=sub(s,'Frame{generation:version,rows,max_epoch}','Frame{table:t,generation:version,rows,max_epoch}')
    file.write_text(s+'\ninclude!("signature_join.rs");\n')
    file=src/'ordinary_shortlist.rs';s=file.read_text()
    s=sub(s,'let idx=self.index(d.table,col,&d.frame);\n            Some(self.shortlist(&d.frame,&idx,col,ports[slot].ok_or("missing parent token port")?))','''let q=ports[slot].ok_or("missing parent token port")?;
            if self.signatures.enabled{
                let table=self.full_code_table(&d.frame,col);Some(self.full_code_list(&table,q))
            }else{
                let idx=self.index(d.table,col,&d.frame);Some(self.shortlist(&d.frame,&idx,col,q))
            }''')
    file.write_text(s)
    shutil.copyfile(HERE/'signature_join.rs',src/'signature_join.rs')
