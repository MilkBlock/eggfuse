from pathlib import Path

def edit(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise ValueError(a)
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';row=src/'adaptive_rows.rs';single=src/'single_witness.rs'
    (src/'scalar_frontier.rs').write_bytes((Path(__file__).parent/'frontier.rs').read_bytes())
    with single.open('a') as f:f.write('\ninclude!("scalar_frontier.rs");\n')
    edit(row,'    scalar:ScalarProofs,','    delta:DeltaFrontier,\n    scalar:ScalarProofs,')
    edit(row,'        self.rows.scalar.audit=audit;','''        self.rows.scalar.audit=audit;
        self.rows.delta.enabled=spec["scalar_delta_frontier"]==true;
        if self.rows.delta.enabled && !self.rows.scalar.enabled{return Err("delta frontier needs compiled scalar certificates".into())}
        self.rows.delta.audit=audit;self.rows.delta.profile=spec["scalar_frontier_profile"]==true;''')
    edit(row,'        let n = sources.len();\n        let input = RowInput', '''        let mask=if self.rows.delta.enabled{
            let start=self.rows.delta.profile.then(std::time::Instant::now);
            let result=self.rows.delta.mask(g,&self.rows.scalar.plans,rid,sources,wm)?;
            if let Some(start)=start{self.rows.delta.stats.mask_ns+=start.elapsed().as_nanos() as u64}
            result
        }else{Vec::new()};
        let n = sources.len();
        let input = RowInput''')
    edit(row,'        for (h, score) in sources.iter().zip(scores) {','        for (index,(h, score)) in sources.iter().zip(scores).enumerate() {')
    edit(row,'self.rows.scalar.enabled && self.rows.scalar.rejects(g,rid,h,wm)? {','''self.rows.scalar.enabled && (if let Some(&reason)=mask.get(index){
                let count=&mut self.rows.scalar.counts[rid];
                count.examined+=1;count.missing+=u64::from(reason==1);count.stale+=u64::from(reason==2);
                reason!=0
            }else{self.rows.scalar.rejects(g,rid,h,wm)?}) {''')
    edit(row,'"scalar_certificates":self.scalar.counts,','"delta":self.delta.stats,"delta_layout":self.delta.layout(),"scalar_certificates":self.scalar.counts,')
    p=src/'runtime_completion.rs'
    edit(p,'        self.graph.header_publish();','''        if let Some(single)=&mut self.stage_spine.single{single.publish_scalar_frontier(&self.graph);}
        self.graph.header_publish();''')
    with (src/'graph.rs').open('a') as f:f.write('''
impl Graph{
    pub(crate) fn supports_delta_scalar(&self,t:usize)->bool{!self.port_keys_enabled(t)}
    pub(crate) fn delta_scalar_key(&self,v:&Value)->Option<u64>{
        if let Value::Eq(k)=crate::value::canon(v,&self.parents){Some(k)}else{None}
    }
    pub(crate) fn delta_scalar_lookup(&self,t:usize,k:u64)->Result<Option<(usize,u64)>>{
        debug_assert!(self.supports_delta_scalar(t));
        Ok(self.function_index(t,&[Value::Eq(k)]).and_then(|i|self.functions.get(i).filter(|f|f.live).map(|f|(i,f.epoch))))
    }
    pub(crate) fn current_scalar_at(&self,t:usize,k:u64,i:usize)->Option<u64>{
        let f=self.functions.get(i)?;
        if f.live && f.table==t && f.key.len()==1 && self.delta_scalar_key(&f.key[0])==Some(k){Some(f.epoch)}else{None}
    }
}
''')
