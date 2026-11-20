"""Memoize only within one native rule occurrence, while the model and recurrent context are immutable."""
from pathlib import Path

def change(text,old,new):
    if text.count(old)!=1:raise ValueError((old[:90],text.count(old)))
    return text.replace(old,new)

def install(crate):
    p=Path(crate)/'src/single_witness.rs';s=p.read_text()
    s=change(s,'pub(crate) struct Trial{','''pub(crate) struct Trial{
    share_mode:u8,share_audit:bool,share_counts:[u64;7],share_times:[f64;2],share_digest:sha2::Sha256,state_digest:sha2::Sha256,''')
    s=change(s,'Ok(Self{plans,initial,residual,','''Ok(Self{share_mode:0,share_audit:false,share_counts:[0;7],share_times:[0.;2],
             share_digest:sha2::Sha256::default(),state_digest:sha2::Sha256::default(),plans,initial,residual,''')
    s=change(s,'        let mut offers=Vec::new();let mut delivered=0;let mut score_sum=0.;','''        let mut offers=Vec::new();let mut delivered=0;let mut score_sum=0.;
        let phase=std::time::Instant::now();
        let mut cache=rustc_hash::FxHashMap::<[u8;N],f32>::default();
        let mut fresh_scores=[None::<f32>;2];
        let certified=self.policy.as_ref().is_some_and(|m|m.certified_inputs);
        let stale_single=r.seminaive && p.pivot.is_some() && p.order.is_empty();
        let mut static_features=[0u8;N];
        if matches!(self.share_mode,2|3|5){
            static_features=self.features(g,r,&p,None,wm);
            if let Some(pivot)=p.pivot{
                static_features[9]=r.query[pivot].args.len().min(32) as u8;
                static_features[13]=r.query[pivot].args.iter().filter(|a|matches!(a,Arg::Literal(_))).count().min(32) as u8;
            }
        }''')
    # fast feature construction preserves every effective component of the weighted model.
    # For full raw-feature comparison keep reconstructing all columns in audit mode.
    old='''            let f=self.features(g,r,&p,row.as_ref(),wm);
            let s=self.policy.as_ref().map_or(0.,|m|m.score(&f,rid,&self.state));'''
    new='''            let f=if self.share_mode<2 || self.share_mode==4{self.features(g,r,&p,row.as_ref(),wm)}else{
                let mut v=static_features;
                if let Some(row)=&row{
                    v[5]=32*u8::from(row.epoch>=wm);
                    if !certified{
                        v[6]=g.epoch.saturating_sub(row.epoch).min(32) as u8;
                        v[7]=32*u8::from(self.initial.contains(&row.witness));
                        v[8]=32*u8::from(matches!(row.witness,Dependency::Function(_)));
                        v[10]=row.values.iter().filter(|v|matches!(v,Value::Int(_))).count().min(32) as u8;
                        v[11]=32*u8::from(row.values.iter().any(|v|matches!(v,Value::Int(0))));
                        v[12]=row.values.iter().find_map(|v|if let Value::Int(n)=v{Some(n.unsigned_abs().min(31) as u8)}else{None}).unwrap_or(32);
                    }
                }
                v
            };
            self.share_counts[0]+=1;
            let s=if let Some(m)=&self.policy{
                if self.share_mode==0 || self.share_mode==4{
                    self.share_counts[1]+=1;m.score(&f,rid,&self.state)
                }else if self.share_mode>=2 && certified{
                    let fresh=usize::from(f[5]!=0);
                    if let Some(s)=fresh_scores[fresh]{self.share_counts[2]+=1;s}else{
                        let s=m.score(&f,rid,&self.state);fresh_scores[fresh]=Some(s);self.share_counts[1]+=1;s
                    }
                }else{
                    match cache.entry(f){
                        std::collections::hash_map::Entry::Occupied(e)=>{self.share_counts[2]+=1;*e.get()}
                        std::collections::hash_map::Entry::Vacant(e)=>{self.share_counts[1]+=1;*e.insert(m.score(&f,rid,&self.state))}
                    }
                }
            }else{0.};'''
    s=change(s,old,new)
    s=change(s,'''            let row=match w{Some(w)=>g.row(w)?,None=>None};
            if w.is_some()&&row.as_ref().is_none_or(|r|r.hidden){continue;}''','''            let header_only=self.share_mode==5 && certified && self.mode=="learned";
            let (row,seen_epoch)=if header_only{
                let epoch=if let Some(addr)=w{self.share_counts[6]+=1;let Some(e)=g.visible_epoch(addr)else{continue};e}else{0};
                (None,epoch)
            }else{
                let row=match w{Some(w)=>g.row(w)?,None=>None};
                if w.is_some()&&row.as_ref().is_none_or(|r|r.hidden){continue;}
                let epoch=row.as_ref().map_or(0,|r|r.epoch);
                (row,epoch)
            };''')
    s=change(s,'                let mut v=static_features;','''                let mut v=static_features;
                if header_only && w.is_some(){v[5]=32*u8::from(seen_epoch>=wm);}''')
    s=change(s,'let ok=r.seminaive && p.pivot.is_some() && row.as_ref().is_some_and(|v|v.epoch<wm)', 'let ok=r.seminaive && p.pivot.is_some() && w.is_some() && seen_epoch<wm')
    s=change(s,'version:row.as_ref().map_or(0,|r|r.epoch),initial:w.is_some_and','version:seen_epoch,initial:w.is_some_and')
    s=change(s,'        let n=offers.len();self.work[0]+=n as u64;', '''        self.share_counts[3]=self.share_counts[3].max(cache.len() as u64);
        self.share_counts[4]+=cache.capacity() as u64;
        if self.share_audit{
            use sha2::Digest;
            self.share_digest.update((rid as u64).to_le_bytes());self.share_digest.update(wm.to_le_bytes());
            self.share_digest.update((offers.len() as u64).to_le_bytes());
            for (t,_,send) in &offers{
                self.share_digest.update(t.id.to_le_bytes());self.share_digest.update(t.version.to_le_bytes());
                self.share_digest.update(t.score.to_bits().to_le_bytes());self.share_digest.update([*send as u8,t.guarded as u8,t.initial as u8]);
                for word in t.w.map(address).unwrap_or([0,0,0]){self.share_digest.update(word.to_le_bytes());}
            }
        }
        let n=offers.len();self.work[0]+=n as u64;''')
    s=change(s,'        let mut answers=Vec::new();let mut hist=BTreeMap::new();','''        if self.share_audit{use sha2::Digest;for h in self.state{self.state_digest.update(h.to_bits().to_le_bytes());}}
        self.share_times[0]+=phase.elapsed().as_secs_f64();
        let verify_clock=std::time::Instant::now();
        let mut answers=Vec::new();let mut hist=BTreeMap::new();''')
    s=change(s,'            self.work[2]+=1;\n            let matched=self.check', '''            if matches!(self.share_mode,3|4|5) && stale_single && token.version<wm{
                self.share_counts[5]+=1;continue;
            }
            self.work[2]+=1;
            let matched=self.check''')
    s=change(s,'        if self.mode=="capture"&&n>0{','''        self.share_times[1]+=verify_clock.elapsed().as_secs_f64();
        if self.mode=="capture"&&n>0{''')
    s=change(s,'        json!({"mode":self.mode,','''        use sha2::Digest;
        json!({"score_sharing":{"mode":self.share_mode,"counts":self.share_counts,"seconds":self.share_times,
            "raw_if_audited":if self.share_audit{format!("{:x}",self.share_digest.clone().finalize())}else{String::new()},
            "state_if_audited":if self.share_audit{format!("{:x}",self.state_digest.clone().finalize())}else{String::new()}},
            "mode":self.mode,''')
    s+='''\nimpl Trial{
        pub(crate) fn set_score_sharing(&mut self,mode:&str,record:bool)->Result<()>{
            self.share_mode=match mode{"off"=>0,"full-key"=>1,"static"=>2,"static-stale"=>3,"stale"=>4,"header-stale"=>5,_=>return Err("unknown score-sharing mode".into())};
            self.share_audit=record;Ok(())
        }
    }\n'''
    p.write_text(s)
    p=Path(crate)/'src/runtime.rs';s=p.read_text();mark='    pub fn execute(&mut self) -> Result<()> {'
    s=change(s,mark,'''    pub fn set_single_score_sharing(&mut self,mode:&str,audit:bool)->Result<()>{
        if let Some(s)=self.stage_spine.single.as_mut(){s.set_score_sharing(mode,audit)?;}
        Ok(())
    }
'''+mark);p.write_text(s)
    p=Path(crate)/'examples/joint_witness_session.rs';s=p.read_text()
    s=change(s,'        let initial_cells = runtime.graph.stats.cells_created;', '''        runtime.set_single_score_sharing(req["score_sharing"].as_str().unwrap_or("off"),audit)?;
        let initial_cells = runtime.graph.stats.cells_created;''');p.write_text(s)
    p=Path(crate)/'src/ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {hint_fault:u8','struct Store {phase_seconds:[f64;2],hint_fault:u8')
    s=change(s,'let s=Store{hint_fault,','let s=Store{phase_seconds:[0.;2],hint_fault,')
    s=change(s,'        let mut remaining=vec![0;ins.len()+1];','        let multi_start=std::time::Instant::now();\n        let mut remaining=vec![0;ins.len()+1];')
    marker='        if c.sealing{\n            s.counts.peak_rule_tuples='
    s=change(s,marker,'        let multi_sealed=std::time::Instant::now();s.phase_seconds[0]+=(multi_sealed-multi_start).as_secs_f64();\n'+marker)
    marker='        if s.trial_attempts>=s.cap{s.counts.exhausted+=1;}'
    s=change(s,marker,'        s.phase_seconds[1]+=multi_sealed.elapsed().as_secs_f64();\n'+marker)
    s=change(s,'json!({"shortlist":s.memo_counts,','json!({"joint_profile_seconds":s.phase_seconds,"shortlist":s.memo_counts,')
    p.write_text(s)
    p=Path(crate)/'examples/joint_witness_session.rs';s=p.read_text()
    marker='        report["merge_child"]=eggfuse_cell_runtime::joint_merge::report();'
    s=change(s,marker,marker+'''
        report["native_phase_ms"]=json!(runtime.steps.iter().fold([0f64;5],|mut a,s|{
            let p=&s.phases;for (i,x) in [p.search,p.rhs,p.repair,p.delivery_gc,p.query_update].iter().enumerate(){a[i]+=1000.*x;}a
        }));''')
    p.write_text(s)
