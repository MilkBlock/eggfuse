// Experimental typed port head for sealed whole-pass neural certificates.
use crate::{graph::{Dependency,Graph},program::{Result,Rule},value::Value};
use serde::Deserialize;
use serde_json::{json,Value as Json};
use std::collections::BTreeMap;

#[derive(Deserialize)]
pub struct Head { pub hidden: Vec<[f32;14]>, pub bias: [f32;16], pub parent: Vec<[f32;12]>,
                  pub read: [[f32;16];2], pub out_bias: [f32;2], #[serde(default)] pub raw:Option<RawHead> }
#[derive(Deserialize)]
pub struct Template { choices: Vec<Vec<(u16,[f32;14])>>, #[serde(default)] requests:Vec<Request> }
#[derive(Deserialize)]
struct Request { features:[f32;14], sort:String }
#[derive(Deserialize)]
pub struct RawHead {
    hidden:Vec<[f32;30]>,bias:[f32;32],output:Vec<[f32;32]>,out_bias:Vec<f32>,classes:Vec<(String,Value)>
}
impl RawHead {
    fn value(&self,request:&Request,parent:&[f32;12],token:&[i64;6])->Option<Value>{
        if self.hidden.len()!=32 || self.output.len()!=self.classes.len() || self.out_bias.len()!=self.classes.len(){return None;}
        let mut input=[0.;30];input[..14].copy_from_slice(&request.features);input[14..26].copy_from_slice(parent);
        input[26..].copy_from_slice(&[token[1] as f32/8.,token[2] as f32/1024.,token[3] as f32/1024.,token[4] as f32/16.]);
        let h=std::array::from_fn::<_,32,_>(|i|dot(&input,&self.hidden[i],self.bias[i]).tanh());
        let mut best=f32::NEG_INFINITY;let mut selected=None;
        for (i,(sort,value)) in self.classes.iter().enumerate(){
            if *sort!=request.sort{continue;}
            let score=dot(&h,&self.output[i],self.out_bias[i]);
            if score>best{best=score;selected=Some(value);}
        }
        selected.cloned()
    }
}
#[derive(Deserialize)]
pub struct Plan { pub mode:String, pub capacity:usize, pub stride:usize,
                  pub layouts:Vec<usize>,pub templates:Vec<Template> }

pub(crate) struct State {
    mode:String,cap:usize,stride:usize,
    starts:Vec<usize>, widths:Vec<usize>, refs:Vec<u16>, copies:Vec<u16>, values:Vec<Option<Value>>,
    faults:Vec<[u64;3]>, visited:Vec<u64>,
    active:usize, eligible:usize,overflow:usize, scored:usize, invalid_layout:usize,
}

fn dot<const N:usize>(v:&[f32;N],w:&[f32;N],bias:f32)->f32{
    v.iter().zip(w).fold(bias,|sum,(a,b)|sum+a*b)
}

impl State {
    pub(crate) fn emit(head:&Head,plan:&Plan,parents:&[[f32;12]],children:&mut [[i64;6]])->Result<Self>{
        if plan.layouts.len()!=children.len()||head.hidden.len()!=16||head.parent.len()!=16||plan.stride==0{
            return Err("invalid variable-port plan".into());
        }
        let direct=plan.mode=="direct";let collect=plan.mode=="collect-values";
        let fixed=plan.mode=="fixed" || direct || collect;let boundary=plan.mode=="boundary";
        if !fixed && !boundary && !matches!(plan.mode.as_str(),"all"|"wrong-reference"|"wrong-value"){
            return Err("unknown variable-port layout".into());
        }
        let fixed=fixed||plan.mode=="wrong-value";
        let mut s=Self{mode:plan.mode.clone(),cap:plan.capacity,stride:plan.stride,starts:Vec::new(),widths:Vec::new(),
            refs:Vec::new(),copies:Vec::new(),values:Vec::new(),faults:vec![[0;3];children.len()],
            visited:vec![0;children.len()],active:0,eligible:0,overflow:0,scored:0,invalid_layout:0};
        let mut cache:BTreeMap<(usize,usize),Vec<(u16,u16)>>=BTreeMap::new();
        for (id,token) in children.iter_mut().enumerate(){
            let template=plan.templates.get(plan.layouts[id]).ok_or("unknown port template")?;
            let width=template.choices.len();
            s.starts.push(s.refs.len());s.widths.push(width);
            if token[0]==0{continue;}
            s.active+=1;
            if width==0{s.invalid_layout+=1;token[5]=-2;continue;}
            s.eligible+=1;
            // All three variants keep the same original compiled verifier and direct one-atom proof flags.
            if fixed && width>plan.capacity{s.overflow+=1;token[5]=-3;}
            if boundary{continue;}
            let parent=usize::try_from(token[1]).map_err(|_| "invalid parent")?;
            let latent=parents.get(parent).ok_or("unknown parent latent")?;
            let n=if fixed {plan.capacity} else {width};
            let contextual=std::array::from_fn::<_,16,_>(|i|dot(latent,&head.parent[i],0.0));
            let choices=cache.entry((plan.layouts[id],parent)).or_insert_with(||{
                template.choices.iter().map(|bank|{
                    let mut best=[f32::NEG_INFINITY;2];let mut source=[u16::MAX;2];
                    for (addr,input) in bank{
                        let h=std::array::from_fn::<_,16,_>(|i|
                            (dot(input,&head.hidden[i],head.bias[i])+contextual[i]).tanh());
                        for k in 0..(if fixed {2}else{1}){
                            let score=dot(&h,&head.read[k],head.out_bias[k]);
                            if score>best[k]{best[k]=score;source[k]=*addr;}
                        }
                    }
                    (source[0],source[1])
                }).collect()
            });
            for j in 0..n{
                let (r,v)=choices.get(j).copied().unwrap_or((u16::MAX,u16::MAX));
                s.refs.push(if plan.mode=="wrong-reference"{u16::MAX}else{r});
                if fixed{
                    if !direct{s.copies.push(if plan.mode=="wrong-value"{u16::MAX}else{v});}
                    let value=if direct && j<width{
                        head.raw.as_ref().ok_or("missing raw-value policy")?.value(
                            template.requests.get(j).ok_or("missing typed request")?,latent,token)
                    }else{None};
                    s.values.push(value);
                }
            }
        }
        s.scored=cache.len();
        Ok(s)
    }
    pub(crate) fn check(&mut self,id:usize,g:&Graph,rule:&Rule,known:&[(usize,Dependency)])->Result<bool>{
        if self.mode=="boundary"{return Ok(true);}
        self.visited[id]+=1;
        let fixed=!self.values.is_empty();
        let width:usize=rule.query.iter().map(|a|a.args.len()).sum();
        if self.widths[id]!=width || fixed && width>self.cap{return Ok(false);}
        let start=self.starts[id];
        // Materialize the network-selected copies separately from reference identity checks.
        // Only the fixed arm needs actual typed values at this source visibility boundary.
        let rows=if fixed{
            let mut rows=Vec::with_capacity(known.len());
            for &(_,w) in known{rows.push(g.row(w)?.filter(|r|!r.hidden).ok_or("lost validated port")?);}
            rows
        }else{Vec::new()};
        let mut fault=[false;3];let mut at=start;
        for (atom,q) in rule.query.iter().enumerate(){
            let pos=known.iter().position(|(a,_)|*a==atom).ok_or("missing verified member")?;
            for col in 0..q.args.len(){
                let address=self.refs[at] as usize;
                let (member,column)=(address/self.stride,address%self.stride);
                fault[0]|=member!=pos;fault[1]|=column!=col;
                if fixed{
                    if self.mode=="collect-values"{self.values[at]=rows[pos].values.get(col).cloned();}
                    else if self.mode!="direct"{
                        let copy=self.copies[at] as usize;
                        self.values[at]=rows.get(copy/self.stride).and_then(|r|r.values.get(copy%self.stride)).cloned();
                    }
                    fault[2]|=self.values[at].as_ref()!=rows[pos].values.get(col);
                }
                at+=1;
            }
        }
        for k in 0..3{self.faults[id][k]+=u64::from(fault[k]);}
        Ok(self.mode=="collect-values" || !fault.iter().any(|v|*v))
    }
    pub(crate) fn report(&self)->Json{
        json!({"mode":self.mode,"active":self.active,"eligible":self.eligible,"overflow":self.overflow,
               "unsupported":self.invalid_layout,"scored_template_parent_pairs":self.scored,
               "extra_reference_slots":self.refs.len(),"value_copy_slots":self.copies.len(),
               "typed_value_slot_bytes":std::mem::size_of::<Option<Value>>(),"typed_value_slots":self.values.len(),
               "typed_values_materialized":self.values.iter().filter(|v|v.is_some()).count(),
               "training_values":if self.mode=="collect-values"{Some(&self.values)}else{None},
               "reference_bytes":self.refs.len()*2,"copy_bytes":self.copies.len()*2,
               "offset_bytes":self.starts.len()*std::mem::size_of::<usize>(),
               "reserved_payload_bytes":2*(self.refs.len()+self.copies.len())+self.values.len()*std::mem::size_of::<Option<Value>>(),
               "vec_capacity_payload_bytes":2*(self.refs.capacity()+self.copies.capacity())+
                       self.values.capacity()*std::mem::size_of::<Option<Value>>(),
               "vec_capacity_layout_bytes":std::mem::size_of::<usize>()*(self.starts.capacity()+self.widths.capacity()),
               "vec_capacity_audit_bytes":std::mem::size_of::<u64>()*(3*self.faults.capacity()+self.visited.capacity()),
               "faults":self.faults,"visited":self.visited,"widths":self.widths,"starts":self.starts,"refs":self.refs,"copies":self.copies})
    }
}
