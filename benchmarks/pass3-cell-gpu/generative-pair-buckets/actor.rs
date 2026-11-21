type Posting=Rc<Vec<(Dependency,u64)>>;
#[derive(Default,Serialize)]
struct BucketWork{
    score_calls:u64,hard_ineligible:u64,small_or_large:u64,gate_reject:u64,
    groups:u64,declared_lanes:u64,receiver_decoded:u64,receiver_reuses:u64,receiver_postings:u64,
    external_residual:u64,wire_bytes:u64,extent_rejects:u64
}
#[derive(Default)]
struct PairActor{
    enabled:bool,fault:bool,trace:bool,weights:Option<[f64;3]>,
    pending:Vec<(usize,[u64;9],[f64;3])>,
    tables:HashMap<(usize,usize),(u64,u64,HashMap<u32,Posting>)>,
    work:BucketWork,examples:Vec<serde_json::Value>,
}
pub fn configure_pair_actor(v:&serde_json::Value)->Result<()>{
    STORE.with_borrow_mut(|s|{
        let s=s.as_mut().ok_or("missing multi-parent issuer")?;
        if !s.page || !s.packed_lookup || s.radius!=0 || s.mode!="learned" || s.raw_cache.enabled ||
           !s.model.q.iter().flatten().zip(s.model.k.iter().flatten()).all(|(a,b)|a.to_bits()==b.to_bits()){
            return Err("pair actions require packed tied zero-radius source pages".into())
        }
        let a=&mut s.pair_actor;
        a.enabled=v["enabled"]==true;a.trace=v["trace"]==true;a.fault=v["bad_bound"]==true;
        if let Some(w)=v.get("weights"){a.weights=Some(serde_json::from_value(w.clone()).map_err(|e|e.to_string())?);}
        Ok(())
    })
}
fn encode_dep(d:Dependency)->(u64,u64){match d{Dependency::Fact(f)=>(1,(u64::from(f.cell)<<32)|u64::from(f.op)),Dependency::Function(i)=>(2,i as u64)}}
fn decode_dep(tag:u64,id:u64)->Result<Dependency>{match tag{1=>Ok(Dependency::Fact(crate::graph::FactRef{cell:(id>>32) as u32,op:id as u32})),2=>Ok(Dependency::Function(usize::try_from(id).map_err(|e|e.to_string())?)),_=>Err("invalid anchor tag".into())}}
impl Store{
    fn issue_bucket(&mut self,c:&Context,steps:&[StackStep],row:&Row,lcol:usize,key:u32,count:usize)->bool{
        let a=&mut self.pair_actor;
        a.work.score_calls+=1;
        if !(2..=64).contains(&count){a.work.small_or_large+=1;return false}
        let features=[1.,(count as f64).ln(),(steps[1].frame.rows.len() as f64).ln_1p()/8.];
        if let Some(w)=a.weights && w.iter().zip(features).map(|(a,b)|a*b).sum::<f64>()<0. {
            a.work.gate_reject+=1;return false
        }
        // The feature extractor reads posting cardinality only. A nine-word packet freezes the claim.
        if !self.page_refs.is_empty(){self.pending_pages.push(std::mem::take(&mut self.page_refs));}
        let (tag,id)=encode_dep(row.witness);let n=if a.fault{count as u64+1}else{count as u64};
        let words=[c.graph.epoch,self.rule as u64,tag,id,row.epoch,steps[0].frame.generation,
                   steps[1].frame.generation,u64::from(key),n];
        let _=lcol;
        a.pending.push((self.pending_pages.len(),words,features));
        a.work.groups+=1;a.work.wire_bytes+=72;a.work.declared_lanes+=count as u64;
        self.counts.raw_tuples+=count as u64;self.counts.raw_root_slots+=2*count as u64;
        self.pair_stats.published_pairs+=count as u64;
        true
    }
    fn receive_bucket(&mut self,c:&Context,packet:[u64;9],features:[f64;3])->Result<crate::joint_root::MultiPage>{
        let [epoch,rid,tag,id,version,lg,rg,key,n]=packet;
        if epoch!=c.graph.epoch || rid!=self.rule as u64 || !(2..=64).contains(&n){return Err("invalid bucket bounds or scope".into())}
        let (ai,ak)=(c.inst[0].0,c.inst[1].0);
        let (a,b)=(&c.rule.query[ai],&c.rule.query[ak]);
        let (Call::Table(lt),Call::Table(rt))=(a.call.clone(),b.call.clone()) else{return Err("nonrelational group".into())};
        let rc=*c.inst[1].2.first().ok_or("missing bucket key")?;
        let Arg::Slot(slot)=b.args[rc] else{return Err("unbound bucket role".into())};
        let lc=a.args.iter().position(|v|matches!(v,Arg::Slot(i) if *i==slot)).ok_or("invalid recipient role")?;
        if c.graph.query_versions[lt]!=lg || c.graph.query_versions[rt]!=rg{return Err("stale bucket table".into())}
        let dep=decode_dep(tag,id)?;
        let left=c.graph.row(dep)?.filter(|r|!r.hidden && r.table==lt && r.epoch==version).ok_or("stale group anchor")?;
        if u64::from(signature(self.code(&left.values[lc]),true,self.views))!=key{return Err("wrong signed prototype".into())}
        let key=u32::try_from(key).map_err(|e|e.to_string())?;let generation=(rg,c.graph.stats.unions);
        if !self.pair_actor.tables.get(&(rt,rc)).is_some_and(|(g,u,_)|(*g,*u)==generation){
            let mut bins:HashMap<u32,Vec<(Dependency,u64)>>=HashMap::new();
            for w in c.graph.witnesses(rt){
                if let Some(r)=c.graph.row(w)?.filter(|r|r.table==rt && !r.hidden){
                    let k=signature(self.code(&r.values[rc]),false,self.views);
                    bins.entry(k).or_default().push((w,r.epoch));self.pair_actor.work.receiver_decoded+=1;
                }
            }
            let bins=bins.into_iter().map(|(k,v)|(k,Rc::new(v))).collect();
            self.pair_actor.tables.insert((rt,rc),(generation.0,generation.1,bins));
        }else{self.pair_actor.work.receiver_reuses+=1;}
        let posting=self.pair_actor.tables[&(rt,rc)].2.get(&key).ok_or("receiver bucket absent")?.clone();
        if posting.len() as u64!=n{self.pair_actor.work.extent_rejects+=1;return Err("wrong bucket extent".into())}
        self.pair_actor.work.receiver_postings+=n;
        let pg=crate::joint_root::bucket_page(epoch,self.rule,crate::joint_root::Ref{atom:ai,row:dep,version},ak,posting)?;
        if self.pair_actor.trace{self.pair_actor.examples.push(json!([pg.stage_serial(),n,features,epoch,self.rule]));}
        Ok(pg)
    }
}
