from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def replace(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)

def install(crate):
    src=crate/'src'
    p=src/'single_witness.rs';s=p.read_text()
    s=replace(s,'    packed: bool,','    pub(crate) class_actor:u8, class_gate:ClassGate,class_counts:ActionCounts, packed: bool,')
    s=replace(s,'Ok(Self{packed:false,','Ok(Self{class_actor:0,class_gate:Default::default(),class_counts:Default::default(),packed:false,')
    s=replace(s,'json!({"packed":self.packed_stats,','json!({"class_actor":self.class_counts,"recurrence_final_bits":self.state.map(f32::to_bits),"source_final_serial":self.serial,"packed":self.packed_stats,')
    mark="        Ok((offers,n,delivered))"
    s=replace(s,mark,'''        if self.rows.detailed {
            for v in [g.epoch,rid as u64,n as u64,delivered as u64,u64::from(score_sum.to_bits()),self.serial]
                .into_iter().chain(self.state.iter().map(|v|u64::from(v.to_bits()))){
                self.class_counts.recurrence_digest=(self.class_counts.recurrence_digest^v).wrapping_mul(1099511628211);
            }
        }
'''+mark)
    p.write_text(s+'\ninclude!("fresh_class_actor.rs");\n')
    copyfile(HERE/'actor.rs',src/'fresh_class_actor.rs')
    p=src/'header_banks.rs'
    with p.open('a') as f:f.write('''
impl Graph{pub(crate) fn public_class_headers(&self,table:usize)->std::sync::Arc<Vec<crate::single_witness::SourceHeader>>{
    let bank=self.header_bank(table);
    let headers=self.headers.borrow();
    let initial=headers.initial.as_ref().expect("initial source membership was registered at graph setup");
    std::sync::Arc::new(bank.rows.iter().map(|(w,e)|crate::single_witness::SourceHeader::from_published(*w,*e,initial.contains(w))).collect())
}}
''')
    p=src/'adaptive_rows.rs';s=p.read_text()
    anchor='        let nullary = [SourceHeader {'
    s=replace(s,anchor,'''        let class_eligible=model.certified_inputs && self.rows.fixed==Some(4) && self.packed && self.rows.batch &&
              !self.residual && !self.rows.capture && g.header_mode==3 && p.pivot.is_some();
'''+anchor)
    s=replace(s,'            header_part!(1);self.rows.stats.proof_empty_calls += 1;', '''            if self.class_actor!=0{self.class_counts.empty_table_skips+=1;}
            if self.rows.detailed{self.class_counts.rule_calls.push([g.epoch,rid as u64,u64::from(class_eligible),0,0,0,0,0,0,1]);}
            self.class_gate.observe(g.epoch,rid,0,0);
            header_part!(1);self.rows.stats.proof_empty_calls += 1;''')
    a='        let sources: &[SourceHeader] = if let Some(pivot) = p.pivot {'
    s=replace(s,a,'''        // The sender stops at this point. No pivot snapshot or membership has been read.
        let gate_allows=self.class_actor!=0 && class_eligible && self.class_gate.choose(g,rid,wm,p,&base,&self.state);
        let decision=if gate_allows {
            if let Some(pivot)=p.pivot {
                let Call::Table(table)=r.query[pivot].call else{return Err("invalid class pivot".into())};
                let packet=ClassAction::issue(model,&self.state,base,self.floors[rid],rid,pivot,table,g.epoch,
                    g.query_versions[table],wm,self.serial)?;
                let inst=packet.receive(g,rid,pivot,wm,self.serial,self.class_actor)?;
                self.class_counts.issued+=1;self.class_counts.logit_evaluations+=2;
                self.class_counts.masks[inst.mask as usize]+=1;Some(inst)
            }else{None}
        }else{None};
        let first_root=if decision.is_some() && self.rows.detailed {crate::joint_root::next_class_serial()}else{0};
        if self.class_actor!=0 && decision.is_none(){self.class_counts.residual_calls+=1;}
'''+a)
    a='''            keep = self
                .rows
                .snapshot(g, t, &self.initial, model.certified_inputs)?;'''
    s=replace(s,a,'''            keep=if let Some(class)=&decision{
                let bank=g.public_class_headers(class.table);
                self.class_counts.public_headers+=bank.len();bank
            }else{self.rows.snapshot(g,t,&self.initial,model.certified_inputs)?};''')
    s=replace(s,'''        let mut scores = vec![0.; n];
        let (evals, participants) =
            input.execute(sources, &mut scores, action, self.rows.pool.as_ref());''','''        let mut scores=Vec::new();
        let (evals,participants)=if decision.is_some() {
            self.class_counts.eligible_after_prefilters+=n;(2,1u64)
        }else{scores.resize(n,0.);input.execute(sources,&mut scores,action,self.rows.pool.as_ref())};''')
    a='        for (h, score) in sources.iter().zip(scores) {'
    s=replace(s,a,'''        for (index,h) in sources.iter().enumerate() {''')
    a='            let send = score >= self.floors[rid];'
    s=replace(s,a,'''            let (score,send)=if let Some(c)=&decision{
                let i=usize::from(fresh);(c.logits[i], c.mask & (1<<i)!=0)
            }else{let logit=scores[index];(logit,logit>=self.floors[rid])};''')
    a='        Ok((result, emitted+omitted, fresh_total, n))'
    s=replace(s,a,'''        if self.rows.detailed {self.class_counts.rule_calls.push([g.epoch,rid as u64,u64::from(class_eligible),
            u64::from(decision.is_some()),n as u64,(emitted+omitted) as u64,emitted as u64,
            u64::from(decision.is_some()),if decision.is_some(){0}else{emitted as u64},0]);}
        self.class_gate.observe(g.epoch,rid,n,emitted);
        if decision.is_some(){
            self.class_counts.accepted_by_action+=emitted+omitted;self.class_counts.scalar_rejected+=omitted;
            self.class_counts.internal_receipts+=emitted;self.class_counts.empty+=usize::from(emitted==0);
            if self.rows.detailed{self.class_counts.audit_ranges.push([first_root,emitted as u64]);}
            let (d,f,n)=class_feedback(emitted+omitted,fresh_total,n);
            self.class_counts.feedback_bytes+=20;
            Ok((result,d,f,n))
        }else{
            if self.class_actor!=0{self.class_counts.residual_receipts+=emitted;}
            Ok((result,emitted+omitted,fresh_total,n))
        }''')
    p.write_text(s)
    p=src/'joint_root.rs'
    with p.open('a') as f:f.write('\npub(crate) fn next_class_serial()->u64{STATE.with_borrow(|s|s.as_ref().unwrap().serial+1)}\n')
    p=src/'runtime.rs'
    with p.open('a') as f:f.write('''
impl Executor{pub fn set_class_actor(&mut self,mode:u8)->Result<()>{
    if mode>4{return Err("invalid causal actor mode".into());}
    self.stage_spine.single.as_mut().ok_or("class actor needs learned singletons")?.class_actor=mode;Ok(())
}}
''')
    p=crate/'examples/joint_witness_session.rs';s=p.read_text()
    a='            runtime.use_packed_single()?;'
    p.write_text(replace(s,a,a+'\n            runtime.set_class_actor(req["class_actor"].as_u64().unwrap_or(0).try_into()?)?;'))
