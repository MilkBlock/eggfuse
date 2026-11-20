//! A neural proposal names independent typed row ports. Only after a pointer
//! choice are its columns unified. The remaining compiler-closed atoms use
//! exact unique point reads or typed primitive evaluation, never join enumeration.
use crate::{cell::{Instance,QueryFacts},graph::{Dependency,Graph,Row},program::{Arg,Call,Program,Result,Rule},slots::Slots,value::{Value,canon}};
use serde::{Deserialize,Serialize};
use serde_json::{json,Value as Json};
use sha2::{Digest,Sha256};
use std::{cell::RefCell,collections::{BTreeMap,HashMap},hash::{Hash,Hasher},rc::Rc};
const F:usize=16;const B:usize=10;
#[derive(Deserialize)]
struct Model {q:[[f32;F];B],k:[[f32;F];B]}
#[derive(Deserialize)]
struct Plan {width:usize,ins:Vec<(usize,usize,Vec<usize>)>,linked:Vec<usize>}
#[derive(Clone,Default,Serialize)]
struct Counts {calls:u64,table_rebuilds:u64,visible_rows:u64,root_offers:u64,score_bucket_reads:u64,
    approximate_visits:u64,learned_pointers:u64,rejected_pointers:u64,point_reads:u64,primitive_evals:u64,
    validated:u64,committed:u64,exhausted:u64,unsupported:u64,stale_candidates:u64,shortlisted:u64,raw_tuples:u64,raw_root_slots:u64,raw_parent_rejects:u64,verified_parent_tuples:u64,peak_rule_tuples:usize}
struct Frame {generation:u64, rows:Vec<Row>, max_epoch:u64}
struct Index {generation:u64,bins:BTreeMap<u16,Vec<usize>>}
#[derive(Clone,Serialize)]
struct Ticket {run:usize,rule:usize,width:usize,anchors:Vec<Dependency>,inputs:Vec<Value>,ordinal:usize}
struct Store {views:usize,seal:bool,raw_digest:Sha256,model:Model,plans:Vec<Option<Plan>>,radius:u32,mode:String,residual:bool,
    detailed:bool,cap:usize,codes:HashMap<Value,Port>,frames:HashMap<usize,Rc<Frame>>,
    indexes:HashMap<(usize,usize),Rc<Index>>,counts:Counts,global_rhs:usize,by_width:BTreeMap<usize,usize>,
    tickets:Vec<Ticket>,wins:Vec<Ticket>,run:usize,rule:usize,trial_attempts:usize,unvisited_after_cap:bool}
impl Store{
    // Reaching the limit on the last candidate and refusing another branch are different.
    fn stop_generation(&mut self)->bool{
        if self.trial_attempts<self.cap{return false;}
        self.unvisited_after_cap=true;
        true
    }
}
thread_local!{static STORE:RefCell<Option<Store>>=const{RefCell::new(None)};}
pub fn configure(program:&Program,plan:&[u8],model:&[u8],mode:&str,radius:u32,residual:bool,cap:usize,detailed:bool)->Result<()>{
    let seal=mode.starts_with("seal");let mode=mode.strip_prefix("seal").unwrap_or(mode);
    let (views,mode)=if let Some(s)=mode.strip_prefix("2x"){(2,s)}else if let Some(s)=mode.strip_prefix("3x"){(3,s)}else{(1,mode)};
    if radius>B as u32 || !matches!(mode,"learned"|"adaptive"|"certified"|"off"|"wrong"|"shuffle"|"random"|"masked"|"drop"|"all"|"none"){return Err("invalid pointer mode".into())}
    let s=Store{views,seal,raw_digest:Sha256::new(),model:serde_json::from_slice(model).map_err(|e|e.to_string())?,
        plans:serde_json::from_slice(plan).map_err(|e|e.to_string())?,radius,mode:mode.into(),residual,detailed,cap,
        codes:HashMap::new(),frames:HashMap::new(),indexes:HashMap::new(),counts:Counts::default(),global_rhs:0,by_width:BTreeMap::new(),
        tickets:vec![],wins:vec![],run:0,rule:0,trial_attempts:0,unvisited_after_cap:false};
    if s.plans.len()!=program.rules.len(){return Err("rule count mismatch".into())}
    for (r,p) in program.rules.iter().zip(&s.plans){
        let Some(p)=p else{continue};
        let mut seen=std::collections::BTreeSet::new();let mut bound=std::collections::BTreeSet::new();let mut picks=0;
        for (i,pick,cols) in &p.ins{
            if *i>=r.query.len() || !seen.insert(*i){return Err("bad source atom permutation".into())}
            let atom=&r.query[*i];if atom.args.is_empty(){return Err("empty atom column vector".into())}
            let ready=|a:&Arg|matches!(a,Arg::Literal(_)) || matches!(a,Arg::Slot(i) if bound.contains(i));
            if *pick==0{
                if !cols.is_empty() || !atom.args[..atom.args.len()-1].iter().all(ready){return Err("invalid point suffix".into())}
            }else{
                if *pick!=1 || !matches!(atom.call,Call::Table(_)){return Err("bad independent port".into())}
                for &col in cols{if col>=atom.args.len()||!ready(&atom.args[col]){return Err("unbound pointer slot".into())}}
                picks+=1;
            }
            for a in &atom.args{if let Arg::Slot(i)=a{bound.insert(*i);}}
        }
        if seen.len()!=r.query.len() || p.linked.len()!=picks || p.width<2 || picks<p.width{return Err("incomplete source plan".into())}
    }
    if seal && s.plans.iter().flatten().any(|p|p.ins.windows(2).any(|x|x[0].1==0 && x[1].1!=0)){
        return Err("sealed mode requires all independent pointers before any verifier instruction".into())
    }
    STORE.with(|x|*x.borrow_mut()=Some(s)); Ok(())
}
pub fn unfinished_generation()->Option<Json>{
    STORE.with_borrow(|cell|{
        let s=cell.as_ref()?;
        (s.unvisited_after_cap && !s.residual).then(||json!({
            "run":s.run, "rule":s.rule, "attempts":s.trial_attempts, "limit":s.cap,
            "reason":"unexplored_parent_branch"
        }))
    })
}
pub fn report()->Json{STORE.with(|x|x.borrow().as_ref().map_or(Json::Null,|s|
    json!({"generator":s.mode,"sealed_before_verifier":s.seal,"embedding_views":s.views,"raw_sha256":if s.detailed && s.seal{format!("{:x}",s.raw_digest.clone().finalize())}else{String::new()},"neural_committed":if matches!(s.mode.as_str(),"learned"|"adaptive"|"certified"){s.counts.committed}else{0},"counts":s.counts,"total_rhs":s.global_rhs,"by_width":s.by_width,"tickets":s.wins})))}
pub(crate) fn assert_proposal_inputs(id:usize,slots:&Slots,inputs:&[usize]){
    if id==0{return}
    STORE.with(|x|{let x=x.borrow();let s=x.as_ref().unwrap();if s.detailed{
        let ticket=&s.tickets[id-1];
        assert!(ticket.inputs.iter().eq(inputs.iter().map(|i|&slots[i])));
    }});
}
pub(crate) fn commit(id:usize,rule:usize){
    STORE.with(|x|{let mut x=x.borrow_mut();let Some(s)=x.as_mut()else{return};s.global_rhs+=1;
        if id>0{let mut t=s.tickets[id-1].clone();assert_eq!(t.rule,rule);t.ordinal=s.global_rhs;
            s.counts.committed+=1;*s.by_width.entry(t.width).or_default()+=1;
            if s.detailed{s.wins.push(t)}
        }
    });
}
pub(crate) fn eligible(rule:usize)->Option<bool>{STORE.with(|s|s.borrow().as_ref().and_then(|s|
    s.plans.get(rule).and_then(|p|p.as_ref()).filter(|p|s.mode!="off" && p.width>=2 && p.linked.iter().skip(1).all(|&n|n>0)).map(|_|s.residual)))}

fn code_seed(v:&Value)->u64{match v{
    Value::Eq(id)=>*id,Value::Int(i)=>(*i as u64)^0xd197a563728c114b,
    _=>{let mut h=std::collections::hash_map::DefaultHasher::new();v.hash(&mut h);h.finish()}
}}
fn mix(mut x:u64)->u64{x^=x>>30;x=x.wrapping_mul(0xbf58476d1ce4e5b9);x^=x>>27;
    x=x.wrapping_mul(0x94d049bb133111eb);x^(x>>31)}
#[derive(Clone,Copy)]
struct Port{query:u16,key:u16,certified:u16,uncertain:u16,extra:[[u16;4];2]}
fn model_port(x:u64,m:&Model,limit:u32)->Port{
    let mut q=0;let mut k=0;let mut band=0;let mut rank=[(0f32,0usize);B];
    for i in 0..B{
        let mut l=0f32;let mut r=0f32;let mut diff=0f32;
        for j in 0..F{
            let sign=if (x>>j)&1==1{1.}else{-1.};
            l+=sign*m.q[i][j];r+=sign*m.k[i][j];diff+=(m.q[i][j]-m.k[i][j]).abs();
        }
        if l>0.{q|=1<<i} if r>0.{k|=1<<i}
        // On identical bipolar inputs, |Qx-Kx| is bounded by the L1
        // difference of the learned filters. Include floating roundoff.
        if l.abs()<=diff+0.0001 {band|=1<<i;}
        rank[i]=(l.abs(),i);
    }
    rank.sort_unstable_by(|a,b|a.0.total_cmp(&b.0).then_with(||a.1.cmp(&b.1)));
    let uncertain=rank.iter().take(limit as usize).fold(0u16,|s,&(_,i)|s|(1<<i));
    Port{query:q,key:k,certified:band,uncertain,extra:[[0;4];2]}
}
impl Store{
    fn code(&mut self,v:&Value)->Port{
        if let Some(&pair)=self.codes.get(v){return pair}
        let seed=code_seed(v);
        let mut pair=model_port(mix(seed),&self.model,self.radius);
        for (j,salt) in [0x8220e116bd89aae9,0x461ac17fc5fe72c3].iter().take(self.views-1).enumerate(){
            // Independent symbol layouts with the same trained, untied Q and K heads.
            let e=model_port(mix(seed^salt),&self.model,self.radius);
            pair.extra[j]=[e.query,e.key,e.certified,e.uncertain];
        }
        self.codes.insert(v.clone(),pair);pair
    }
    fn equal_signature(&self,left:Port,right:u16)->bool{
        self.close(left.query,left.certified,left.uncertain,right)
    }
    fn compatible(&self,left:Port,right:Port)->bool{
        self.equal_signature(left,right.key) && (0..self.views-1).all(|j|{
            let v=left.extra[j];self.close(v[0],v[2],v[3],right.extra[j][1])
        })
    }
    fn close(&self,query:u16,certified:u16,uncertain:u16,right:u16)->bool{
        let d=query^right;
        match self.mode.as_str(){
            "certified"=>d&!certified==0, "adaptive"=>d&!uncertain==0,
            "masked"=>right.count_ones()<=self.radius,
            "wrong"=>(d^((1<<B)-1)).count_ones()<=self.radius,
            "shuffle"=>{let rotated=((query<<1)|(query>>(B-1)))&((1<<B)-1);(rotated^0x165^right).count_ones()<=self.radius},
            _=>d.count_ones()<=self.radius,
        }
    }
    fn publish_ports(&mut self,args:&[Arg],values:&[Value],p:&mut Prefix){
        for (a,v) in args.iter().zip(values){if let Arg::Slot(s)=a{
            p.latents.entry(*s).or_insert_with(||self.code(v));
        }}
    }
    fn frame(&mut self,g:&Graph,t:usize)->Result<Rc<Frame>>{
        let version=g.query_versions[t];
        if let Some(f)=self.frames.get(&t) && f.generation==version{return Ok(f.clone())}
        let mut rows=vec![];let mut max_epoch=0;
        for w in g.witnesses(t){if let Some(r)=g.row(w)? && !r.hidden{max_epoch=max_epoch.max(r.epoch);rows.push(r)}}
        self.counts.table_rebuilds+=1;self.counts.visible_rows+=rows.len() as u64;
        let f=Rc::new(Frame{generation:version,rows,max_epoch});self.frames.insert(t,f.clone());Ok(f)
    }
    fn index(&mut self,t:usize,col:usize,f:&Frame)->Rc<Index>{
        if let Some(h)=self.indexes.get(&(t,col)) && h.generation==f.generation{return h.clone()}
        let mut bins=BTreeMap::<u16,Vec<usize>>::new();
        for (i,row) in f.rows.iter().enumerate(){bins.entry(self.code(&row.values[col]).key).or_default().push(i);}
        let h=Rc::new(Index{generation:f.generation,bins});self.indexes.insert((t,col),h.clone());h
    }
}

#[derive(Clone)]
struct Prefix {latents:BTreeMap<usize,Port>,slots:Slots,witness:Vec<Option<Dependency>>,anchors:Vec<Dependency>,epoch:u64,picks:usize}
fn value(arg:&Arg,g:&Graph,p:&Prefix)->Option<Value>{match arg{Arg::Slot(s)=>p.slots.get(s).cloned(),Arg::Literal(v)=>Some(canon(v,&g.parents))}}
fn bind(arg:&Arg,v:&Value,g:&Graph,p:&mut Prefix)->bool{match arg{
    Arg::Literal(w)=>canon(w,&g.parents)==*v,
    Arg::Slot(s)=>if let Some(old)=p.slots.get(s){old==v}else{p.slots.insert(*s,v.clone());true}
}}
fn extend(g:&Graph,r:&Rule,id:usize,row:&Row,p:&mut Prefix)->bool{
    if row.hidden || !matches!(r.query[id].call,Call::Table(t) if t==row.table) || r.query[id].args.len()!=row.values.len(){return false}
    if !r.query[id].args.iter().zip(row.values.iter()).all(|(a,v)|bind(a,v,g,p)){return false}
    p.witness[id]=Some(row.witness);p.epoch=p.epoch.max(row.epoch);true
}
struct Context<'a>{graph:&'a Graph,rule:&'a Rule,inst:&'a [(usize,usize,Vec<usize>)],watermark:u64,known:&'a QueryFacts,remaining:Vec<u64>,width:usize,pick_count:usize,sealing:bool}
impl Store{
    fn descend(&mut self,c:&Context<'_>,step:usize,mut p:Prefix,out:&mut Vec<Instance>,raw:&mut Vec<Vec<Dependency>>)->Result<()>{
        if c.sealing && step==c.pick_count{
            self.counts.raw_tuples+=1;self.counts.raw_root_slots+=p.anchors.len() as u64;
            if self.detailed{
                self.raw_digest.update((self.run as u64).to_le_bytes());self.raw_digest.update((self.rule as u64).to_le_bytes());
                self.raw_digest.update((p.anchors.len() as u64).to_le_bytes());
                for (i,a) in p.anchors.iter().enumerate(){
                    self.raw_digest.update((c.inst[i].0 as u64).to_le_bytes());
                    match a{Dependency::Fact(f)=>{self.raw_digest.update([1]);self.raw_digest.update(f.cell.to_le_bytes());self.raw_digest.update(f.op.to_le_bytes());},
                            Dependency::Function(k)=>{self.raw_digest.update([2]);self.raw_digest.update((*k as u64).to_le_bytes());}}
                }
            }
            raw.push(p.anchors);return Ok(())
        }
        if (c.sealing || !self.seal) && self.stop_generation(){return Ok(())}
        if c.rule.seminaive && p.epoch.max(c.remaining[step])<c.watermark{self.counts.stale_candidates+=1;return Ok(())}
        if step==c.inst.len(){
            if p.picks<2{return Err("unscored source tuple".into())}
            self.counts.validated+=1;
            let mut b=Instance::matched(p.slots,c.known.with_rows(p.witness.iter().enumerate().filter_map(|(i,v)|v.map(|w|(i,w)))),p.epoch);
            self.tickets.push(Ticket{run:self.run,rule:self.rule,width:c.width,anchors:if self.detailed{p.anchors}else{vec![]},inputs:if self.detailed{c.rule.inputs.iter().map(|i|b.values[i].clone()).collect()}else{vec![]},ordinal:0});
            b.ordinary_id=self.tickets.len();out.push(b);return Ok(())
        }
        let (id,pick,cols)=&c.inst[step];let id=*id;let atom=&c.rule.query[id];
        if *pick==0{
            let operands=atom.args[..atom.args.len()-1].iter().map(|a|value(a,c.graph,&p)).collect::<Option<Vec<_>>>().ok_or("unbound exact projection")?;
            match &atom.call{
                Call::Table(t)=>{
                    self.counts.point_reads+=1;
                    if let Some(row)=c.graph.lookup(*t,&operands)? && extend(c.graph,c.rule,id,&row,&mut p){
                        self.publish_ports(&atom.args,&row.values,&mut p);
                        self.descend(c,step+1,p,out,raw)?;
                    }
                }
                Call::Primitive(name,result)=>{
                    self.counts.primitive_evals+=1;
                    if let Some(v)=c.graph.primitive(name,&operands,result)? && bind(atom.args.last().unwrap(),&v,c.graph,&mut p){
                        self.publish_ports(&atom.args[atom.args.len()-1..],std::slice::from_ref(&v),&mut p);
                        self.descend(c,step+1,p,out,raw)?;
                    }
                }
            }
            return Ok(())
        }
        let Call::Table(t)=atom.call else{return Err("pointer must address a relation".into())};
        let frame=self.frame(c.graph,t)?;
        let required=cols.iter().map(|&col|match &atom.args[col]{Arg::Slot(s)=>p.latents.get(s).copied().map(|port|(col,port)), _=>None})
            .collect::<Option<Vec<_>>>().ok_or("missing neural query port")?;
        let mut visit=|this:&mut Self,row:&Row|->Result<()>{
            if this.stop_generation(){return Ok(())}
            if c.rule.seminaive && p.epoch.max(row.epoch).max(c.remaining[step+1])<c.watermark{return Ok(())}
            if p.picks>0{
                this.counts.approximate_visits+=1;
                if this.mode!="all" && !required.iter().all(|(col,q)|{let key=this.code(&row.values[*col]);this.compatible(*q,key)}){return Ok(())}
                if this.mode=="drop"{
                    let mut hash=std::collections::hash_map::DefaultHasher::new();
                    (this.run,this.rule,id,row.witness,&p.anchors).hash(&mut hash);
                    if hash.finish()&1!=0{return Ok(())}
                }
                this.counts.learned_pointers+=1;this.trial_attempts+=1;
            }else{this.counts.root_offers+=1}
            let mut next=p.clone();
            if c.sealing{
                // First assignment only. Conflicting repeated slots, literals,
                // primitive guards and joins are checked AFTER every raw row
                // tuple for this rule occurrence has already been emitted.
                for (a,v) in atom.args.iter().zip(row.values.iter()){
                    if let Arg::Slot(s)=a && !next.slots.contains_key(s){next.slots.insert(*s,v.clone());}
                }
                next.epoch=next.epoch.max(row.epoch);
            }else if !extend(c.graph,c.rule,id,row,&mut next){if p.picks>0{this.counts.rejected_pointers+=1;}return Ok(())}
            this.publish_ports(&atom.args,&row.values,&mut next);
            next.anchors.push(row.witness);next.picks+=1;
            this.descend(c,step+1,next,out,raw)
        };
        if p.picks==0 || self.mode=="all"{
            for row in &frame.rows{visit(self,row)?}
        }else{
            let Some(&(col,q))=required.first()else{return Err("independent pointer lacks a neural query".into())};
            let idx=self.index(t,col,&frame);
            // Hash buckets contain learned, lossy key signatures. Colliding raw
            // source values occur in each bucket. No exact join index is read.
            if matches!(self.mode.as_str(),"adaptive"|"certified"){
                let mask=if self.mode=="adaptive"{q.uncertain}else{q.certified};
                let mut sub=mask;
                loop{
                    self.counts.score_bucket_reads+=1;
                    if let Some(v)=idx.bins.get(&(q.query^sub)){for &j in v{visit(self,&frame.rows[j])?}}
                    if sub==0{break} sub=(sub-1)&mask;
                }
            } else if self.radius<=1 && self.mode!="wrong" && self.mode!="shuffle" && self.mode!="masked"{
                let mut masks=vec![0];if self.radius==1{masks.extend((0..B).map(|i|1<<i));}
                for mask in masks{
                    self.counts.score_bucket_reads+=1;
                    if let Some(v)=idx.bins.get(&(q.query^mask)){for &j in v{visit(self,&frame.rows[j])?}}
                }
            }else{
                for (&key,v) in &idx.bins{
                    self.counts.score_bucket_reads+=1;
                    if self.equal_signature(q,key){for &j in v{visit(self,&frame.rows[j])?}}
                }
            }
        }
        Ok(())
    }
}
pub(crate) fn proposals(g:&Graph,rid:usize,run:usize,mark:u64,known:&QueryFacts)->Result<Vec<Instance>>{
    STORE.with(|x|{
        let mut s=x.borrow_mut();let s=s.as_mut().unwrap();s.counts.calls+=1;
        if s.mode=="none"{return Ok(vec![])}
        let rule=&g.program.rules[rid];
        let plan=s.plans[rid].as_ref().unwrap();let ins=plan.ins.clone();let width=plan.width;
        if rule.query.iter().any(|a|matches!(a.call,Call::Table(t) if g.witness_count(t)==0)){return Ok(vec![])}
        let mut remaining=vec![0;ins.len()+1];
        for (i,(id,_,_)) in ins.iter().enumerate().rev(){
            remaining[i]=remaining[i+1];
            if let Call::Table(t)=rule.query[*id].call{remaining[i]=remaining[i].max(s.frame(g,t)?.max_epoch);}
        }
        s.run=run;s.rule=rid;s.trial_attempts=0;s.unvisited_after_cap=false;
        let mut c=Context{graph:g,rule,inst:&ins,watermark:mark,known,remaining,width,pick_count:ins.iter().filter(|x|x.1==1).count(),sealing:s.seal};
        let p=Prefix{latents:BTreeMap::new(),slots:Slots::default(),witness:vec![None;rule.query.len()],anchors:vec![],epoch:0,picks:0};
        let mut out=vec![];let mut raw=vec![];s.descend(&c,0,p.clone(),&mut out,&mut raw)?;
        if s.unvisited_after_cap && !s.residual{
            s.counts.exhausted+=1;
            return Err(format!("incomplete multi-parent generation at Run {run}, rule {rid}: limit {} left an unexplored branch",s.cap));
        }
        if c.sealing{
            s.counts.peak_rule_tuples=s.counts.peak_rule_tuples.max(raw.len());c.sealing=false;
            let mut no_more=vec![];
            for parents in raw{
                let mut exact=p.clone();let mut ok=true;
                for (i,&address) in parents.iter().enumerate(){
                    let id=c.inst[i].0;
                    let Some(row)=g.row(address)? else{ok=false;break};
                    if !extend(g,rule,id,&row,&mut exact){ok=false;break}
                }
                if !ok{s.counts.raw_parent_rejects+=1;continue}
                s.counts.verified_parent_tuples+=1;exact.picks=parents.len();exact.anchors=parents;
                // All remaining operations are uniquely determined. No further
                // source addresses may be generated or enumerated by this branch.
                s.descend(&c,c.pick_count,exact,&mut out,&mut no_more)?;
            }
            debug_assert!(no_more.is_empty())
        }
        if s.trial_attempts>=s.cap{s.counts.exhausted+=1;}
        Ok(out)
    })
}
