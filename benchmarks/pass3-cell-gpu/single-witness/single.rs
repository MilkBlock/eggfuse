// A proposed token fixes one stable source dependency. Verification only binds that row,
// performs compiled complete-key lookups, and evaluates forward primitives.
use crate::cell::{Instance, QueryFacts,bind_query,query_operand};
use crate::graph::{Dependency,Graph,Row};
use crate::program::{Arg,Call,Program,Rule,Result};
use crate::value::Value;
use serde::Deserialize;
use serde_json::{json,Value as J};
use std::collections::{BTreeMap,BTreeSet};

#[derive(Clone)]
struct Plan{pivot:Option<usize>, order:Vec<usize>}
fn compile(rule:&Rule,pivot:Option<usize>)->Option<Plan>{
    let mut bound=BTreeSet::new();let mut done=vec![false;rule.query.len()];let mut order=Vec::new();
    if let Some(a)=pivot{
        if !matches!(rule.query[a].call,Call::Table(_)){return None;}
        done[a]=true;for arg in &rule.query[a].args{if let Arg::Slot(s)=arg{bound.insert(*s);}}
    }
    while done.iter().any(|b|!*b){
        let i=(0..done.len()).find(|&i|!done[i] && rule.query[i].args.split_last()
            .is_some_and(|(_,key)|key.iter().all(|v|matches!(v,Arg::Literal(_))||matches!(v,Arg::Slot(s) if bound.contains(s)))))?;
        for a in &rule.query[i].args{if let Arg::Slot(s)=a{bound.insert(*s);}}
        done[i]=true;order.push(i);
    }
    Some(Plan{pivot,order})
}
fn plan(r:&Rule)->Option<Plan>{
    compile(r,None).or_else(||(0..r.query.len()).find_map(|a|compile(r,Some(a))))
}

const N:usize=14;const H:usize=4;const K:usize=8;
#[derive(Deserialize)]
pub(crate) struct Model{pub threshold:f32,#[serde(default)] certified_inputs:bool, x:Vec<[f32;N]>,h:Vec<[f32;H]>,b:[f32;K],out:[f32;K],bias:f32,
    recurrent:[[f32;H];H],update:[[f32;4];H],rbias:[f32;H],rules:Vec<f32>}
impl Model{
    fn score(&self,f:&[u8;N],rid:usize,state:&[f32;H])->f32{
        let mut s=self.bias+self.rules[rid%self.rules.len()];
        for k in 0..K{
            let mut v=self.b[k];for i in 0..N{v+=self.x[k][i]*f[i] as f32/32.;}
            for i in 0..H{v+=self.h[k][i]*state[i];}s+=self.out[k]*v.tanh();
        }
        s
    }
    fn certified_floor(&self,r:&Rule,p:&Plan,rid:usize)->f32{
        let mut f=[0u8;N];f[0]=32;f[1]=r.query.len().min(32) as u8;f[2]=r.inputs.len().min(32) as u8;
        f[3]=p.order.iter().filter(|&&a|matches!(r.query[a].call,Call::Primitive(..))).count().min(32) as u8;
        f[4]=r.query.iter().flat_map(|a|&a.args).filter(|a|matches!(a,Arg::Literal(_))).count().min(32) as u8;
        if let Some(a)=p.pivot{f[9]=r.query[a].args.len().min(32) as u8;f[13]=r.query[a].args.iter().filter(|a|matches!(a,Arg::Literal(_))).count().min(32) as u8;}
        let sole=p.pivot.is_some() && r.seminaive && p.order.iter().all(|&a|matches!(r.query[a].call,Call::Primitive(..)));
        let fresh:&[u8]=if p.pivot.is_none(){&[0]}else if sole{&[32]}else{&[0,32]};
        let mut floor=f32::INFINITY;
        for &v in fresh{
            f[5]=v;let mut lower=self.bias+self.rules[rid%self.rules.len()];
            for k in 0..K{
                let mut point=self.b[k];for i in 0..N{point+=self.x[k][i]*f[i] as f32/32.;}
                let radius:f32=self.h[k].iter().map(|w|w.abs()).sum();
                let endpoint=if self.out[k]>=0.{point-radius}else{point+radius};
                lower+=self.out[k]*endpoint.tanh();
            }
            floor=floor.min(lower);
        }
        // Monotone tanh and |state|<=1; slack covers rounding of bounded FP32 dot products.
        floor-0.125
    }
    fn advance(&self,old:[f32;H],features:[f32;4])->[f32;H]{
        std::array::from_fn(|i|{
            let mut v=self.rbias[i];
            for j in 0..H{v+=self.recurrent[i][j]*old[j];}
            for j in 0..4{v+=self.update[i][j]*features[j];}
            v.tanh()
        })
    }
}

fn address(w:Dependency)->[u64;3]{match w{
    Dependency::Fact(f)=>[1,f.cell as u64,f.op as u64],
    Dependency::Function(i)=>[2,i as u64,0]}}
#[derive(Clone,Debug)]
struct Token{id:u64,rid:usize,w:Option<Dependency>,version:u64,initial:bool,score:f32,guarded:bool}
#[derive(Clone,Debug)]
pub(crate) struct Mark{token:Token,values:Vec<Value>,witnesses:Vec<(usize,[u64;3])>}

pub(crate) struct Trial{
    plans:Vec<Option<Plan>>,initial:BTreeSet<Dependency>,pub residual:bool,pub unsupported:bool,mode:String,
    policy:Option<Model>,floors:Vec<f32>,state:[f32;H],work:[u64;8],guard_counts:[u64;6],guarded_ordinals:Vec<usize>,
    dict:BTreeMap<[u8;N],usize>,events:Vec<(usize,usize,Vec<(usize,[u32;2])>)>,
    pub(crate) winner:Option<Mark>,serial:u64,ordinal:usize,pub committed:Vec<J>,pub rules:BTreeMap<usize,[u64;4]>,
}
impl Trial{
    pub fn new(g:&Graph,mode:String,model:Option<Model>,residual:bool)->Result<Self>{
        if !["capture","all","none","learned","zero-state","guarded","delta"].contains(&mode.as_str()){return Err("unknown single-witness mode".into());}
        if matches!(mode.as_str(),"learned"|"zero-state"|"guarded") && model.is_none(){return Err("missing single-witness weights".into());}
        if let Some(m)=&model && (m.x.len()!=K||m.h.len()!=K||(m.rules.len()!=64&&m.rules.len()<g.program.rules.len())||!m.threshold.is_finite()){return Err("invalid single-witness weights".into());}
        let plans:Vec<_>=g.program.rules.iter().map(plan).collect();
        let mut floors=vec![model.as_ref().map_or(0.,|m|m.threshold);plans.len()];
        if let Some(m)=&model && m.certified_inputs{
            let disabled=[6,7,8,10,11,12];
            if m.x.iter().any(|w|disabled.iter().any(|&i|w[i]!=0.)) ||
               m.x.iter().flatten().chain(m.h.iter().flatten()).chain(&m.b).chain(&m.out).chain(&m.rules).chain([&m.bias]).any(|v|!v.is_finite()||v.abs()>16.){
                return Err("uncertifiable single-witness model".into());
            }
            for (rid,p) in plans.iter().enumerate(){if let Some(p)=p{floors[rid]=m.certified_floor(&g.program.rules[rid],p,rid);}}
        }
        let initial=(0..g.program.tables.len()).flat_map(|t|g.witnesses(t)).collect();
        Ok(Self{plans,initial,residual,unsupported:residual,mode,policy:model,floors,state:[0.;H],
            work:[0;8],guard_counts:[0;6],guarded_ordinals:Vec::new(),dict:BTreeMap::new(),events:Vec::new(),winner:None,serial:0,
            ordinal:0,committed:Vec::new(),rules:BTreeMap::new()})
    }
    pub fn accepts(&self,rid:usize)->bool{self.plans[rid].is_some()}
    fn features(&self,g:&Graph,r:&Rule,p:&Plan,row:Option<&Row>,wm:u64)->[u8;N]{
        let mut v=[0u8;N];v[0]=32;v[1]=r.query.len().min(32) as u8;v[2]=r.inputs.len().min(32) as u8;
        v[3]=p.order.iter().filter(|&&i|matches!(r.query[i].call,Call::Primitive(..))).count().min(32) as u8;
        v[4]=r.query.iter().flat_map(|a|&a.args).filter(|a|matches!(a,Arg::Literal(_))).count().min(32) as u8;
        if let Some(row)=row{
            v[5]=u8::from(row.epoch>=wm)*32;v[6]=g.epoch.saturating_sub(row.epoch).min(32) as u8;
            v[7]=u8::from(self.initial.contains(&row.witness))*32;
            v[8]=u8::from(matches!(row.witness,Dependency::Function(_)))*32;
            v[9]=row.values.len().min(32) as u8;
            v[10]=row.values.iter().filter(|v|matches!(v,Value::Int(_))).count().min(32) as u8;
            v[11]=u8::from(row.values.iter().any(|v|matches!(v,Value::Int(0))))*32;
            let pivot=p.pivot.unwrap();let args=&r.query[pivot].args;
            // Coarse integer content signal, independent of all suffix lookups.
            v[12]=row.values.iter().find_map(|v|if let Value::Int(i)=v{Some(i.unsigned_abs().min(31) as u8)}else{None}).unwrap_or(32);
            v[13]=args.iter().filter(|v|matches!(v,Arg::Literal(_))).count().min(32) as u8;
        }
        v
    }
    fn impossible(g:&Graph,r:&Rule,p:&Plan,row:Option<&Row>,wm:u64)->Option<usize>{
        if r.seminaive && row.map_or(0,|v|v.epoch)<wm &&
            p.order.iter().all(|&i|matches!(r.query[i].call,Call::Primitive(..))){return Some(0);}
        if let (Some(pivot),Some(row))=(p.pivot,row){
            let mut anchor=BTreeMap::new();
            if !r.query[pivot].args.iter().zip(row.values.iter()).all(|(a,v)|bind_query(a,v,&mut anchor,g)){return Some(1);}
        }
        if p.order.iter().any(|&i|matches!(r.query[i].call,Call::Table(t) if g.witness_count(t)==0)){return Some(2);}
        None
    }
    fn check(&mut self,g:&Graph,r:&Rule,p:&Plan,token:&Token,wm:u64)->Result<Option<Instance>>{
        let mut frame=BTreeMap::new();let mut rows=vec![None;r.query.len()];let mut epoch=0;
        if let Some(i)=p.pivot{
            let w=token.w.ok_or("missing anchor")?;
            let Some(row)=g.row(w)? else{return Ok(None)};
            if row.hidden||row.witness!=w||row.epoch!=token.version||!matches!(r.query[i].call,Call::Table(t) if t==row.table){return Ok(None);}
            if !r.query[i].args.iter().zip(row.values.iter()).all(|(a,v)|bind_query(a,v,&mut frame,g)){return Ok(None);}
            rows[i]=Some(w);epoch=row.epoch;
        }
        for &i in &p.order{
            let a=&r.query[i];let (last,key)=a.args.split_last().ok_or("empty atom")?;
            let args=key.iter().map(|v|query_operand(v,&frame,g).ok_or_else(||"unprovided compiled slot".to_string())).collect::<Result<Vec<_>>>()?;
            let v=match &a.call{
                Call::Table(t)=>{self.work[3]+=1;let Some(row)=g.lookup(*t,&args)?.filter(|r|!r.hidden) else{return Ok(None)};
                    rows[i]=Some(row.witness);epoch=epoch.max(row.epoch);row.values.last().unwrap().clone()}
                Call::Primitive(op,ty)=>{self.work[4]+=1;let Some(v)=g.primitive(op,&args,ty)? else{return Ok(None)};v}
            };
            if !bind_query(last,&v,&mut frame,g){return Ok(None);}
        }
        if r.seminaive && epoch<wm{return Ok(None);}
        let mut values=crate::slots::Slots::default();
        for &slot in r.inputs.iter(){values.insert(slot,frame.get(&slot).ok_or("unbound RHS slot")?.clone());}
        Ok(Some(Instance::matched(values,QueryFacts::Ports(rows),epoch)))
    }
    pub fn generate(&mut self,g:&Graph,rid:usize,wm:u64)->Result<Vec<Instance>>{
        let p=self.plans[rid].clone().ok_or("unproved grammar")?;let r=&g.program.rules[rid];
        let candidates=if let Some(a)=p.pivot{
            let Call::Table(t)=r.query[a].call else{unreachable!()};g.witnesses(t).into_iter().map(Some).collect()
        }else{vec![None]};
        let mut offers=Vec::new();let mut delivered=0;let mut score_sum=0.;
        // Seal all candidate decisions at this occurrence before the first suffix or primitive check.
        for w in candidates{
            let row=match w{Some(w)=>g.row(w)?,None=>None};
            if w.is_some()&&row.as_ref().is_none_or(|r|r.hidden){continue;}
            let f=self.features(g,r,&p,row.as_ref(),wm);
            let s=self.policy.as_ref().map_or(0.,|m|m.score(&f,rid,&self.state));
            let learned=match self.mode.as_str(){"capture"|"all"=>true,"none"=>false,
                "delta"=>!(r.seminaive && p.pivot.is_some() && row.as_ref().is_some_and(|v|v.epoch<wm) &&
                           p.order.iter().all(|&i|matches!(r.query[i].call,Call::Primitive(..)))),
                _=>s>=self.floors[rid]};
            if !learned && self.policy.as_ref().is_some_and(|m|m.certified_inputs) && self.mode!="none"{
                // Fail closed if a target's floating implementation or malformed checkpoint ever
                // violates the derived cutoff. Only the static delta certificate authorizes omission.
                let ok=r.seminaive && p.pivot.is_some() && row.as_ref().is_some_and(|v|v.epoch<wm)
                    && p.order.iter().all(|&i|matches!(r.query[i].call,Call::Primitive(..)));
                if !ok{return Err("neural abstention violates compiled freshness certificate".into());}
                self.guard_counts[0]+=1;
            }
            let mut send=learned;let mut guarded=false;
            if self.mode=="guarded" && !send{
                match Self::impossible(g,r,&p,row.as_ref(),wm){
                    Some(reason)=>self.guard_counts[reason]+=1,
                    None=>{send=true;guarded=true;self.guard_counts[3]+=1;}
                }
            }
            self.serial+=1;offers.push((Token{id:self.serial,rid,w,guarded,version:row.as_ref().map_or(0,|r|r.epoch),initial:w.is_some_and(|w|self.initial.contains(&w)),score:s},f,send));
            delivered+=usize::from(send);score_sum+=f[5] as f32/32.;
        }
        let n=offers.len();self.work[0]+=n as u64;self.work[1]+=delivered as u64;
        if n>0 && let Some(m)=&self.policy{
            self.state=if self.mode=="zero-state"{[0.;H]}else{m.advance(self.state,[(n.min(128) as f32)/128.,delivered as f32/(n.max(1) as f32),
                score_sum/n.max(1) as f32,(rid%64) as f32/63.])};
        }
        let mut answers=Vec::new();let mut hist=BTreeMap::new();
        for (token,f,send) in offers{
            if !send&&!self.residual{continue;}
            self.work[2]+=1;
            let matched=self.check(g,r,&p,&token,wm)?;
            if self.mode=="capture"{
                let next=self.dict.len();let id=*self.dict.entry(f).or_insert(next);
                hist.entry(id).or_insert([0u32;2])[usize::from(matched.is_some())]+=1;
            }
            if let Some(mut binding)=matched{
                if send{
                    self.work[5]+=1;
                    let values=r.inputs.iter().map(|s|binding.values[s].clone()).collect();
                    let witnesses=(0..r.query.len()).filter_map(|i|binding.known.receipt(i).map(|w|(i,address(w)))).collect();
                    if let Some(pivot)=p.pivot{assert_eq!(binding.known.receipt(pivot),token.w);}
                    binding.known=binding.known.tagged(Mark{token,values,witnesses});
                }else{self.work[6]+=1;}
                answers.push(binding);
            }
        }
        if self.mode=="capture"&&n>0{self.events.push((rid,n,hist.into_iter().collect()));}
        let counters=self.rules.entry(rid).or_default();counters[0]+=1;counters[1]+=n as u64;counters[2]+=delivered as u64;
        Ok(answers)
    }
    pub fn commit(&mut self,rid:usize,run:u64,values:&crate::slots::Slots,p:&Program){
        self.ordinal+=1;
        if let Some(mark)=self.winner.take(){
            let t=mark.token;assert_eq!(t.rid,rid);
            assert!(p.rules[rid].inputs.iter().map(|s|&values[s]).eq(mark.values.iter()));
            self.rules.entry(rid).or_default()[3]+=1;self.guard_counts[if t.guarded{5}else{4}]+=1;if t.guarded{self.guarded_ordinals.push(self.ordinal);}
            self.committed.push(json!([self.ordinal,run,rid,self.plans[rid].as_ref().unwrap().pivot,t.w.map(address),t.version,t.initial,t.score,t.id,mark.witnesses]));
        }
    }
    pub fn report(&self)->J{
        let mut features=vec![[0u8;N];self.dict.len()];for (v,i) in &self.dict{features[*i]=*v;}
        json!({"mode":self.mode,"rhs":self.ordinal,"residual":self.residual,"complete_unsupported":self.unsupported,"rules":self.rules,"work":self.work,"guard_counts":self.guard_counts,"guarded_ordinals":self.guarded_ordinals,"floors":self.floors,
               "committed":self.committed,"initial_rows":self.initial.len(),"features":features,"events":self.events,
               "plans":self.plans.iter().map(|p|p.as_ref().map(|p|json!({"pivot":p.pivot,"order":p.order}))).collect::<Vec<_>>()})
    }
}
