//! Frozen CPU experiment: actual Set values, stable raw keys, canonicalized explicitly at graph boundaries.
use crate::graph::Dependency;
use crate::value::{Value, Parents, root};
use serde::{Serialize,Deserialize};
use serde_json::{json,Value as J};
use std::{cell::RefCell,cmp::Ordering,collections::{BTreeMap,BTreeSet},hash::{Hash,Hasher},sync::Arc};

#[derive(Clone,Copy,PartialEq)]pub enum Repr{Mask,Segments,Sparse}
#[derive(Debug)]enum Data{Mask(u64),Segments(Vec<(u32,u64)>),Sparse(Vec<u64>)}
#[derive(Debug)]pub struct SetData{data:Data}
struct Dictionary{
    mode:Repr,forward:Vec<usize>,redirections:u64,segment_scans:u64,by_id:BTreeMap<u64,usize>,ids:Vec<u64>,fault:Option<String>,
    created:u64,live:i64,peak:i64,canon:u64,canon_members:u64,normalized:u64,
    insert:u64,inter:u64,union:u64,length:u64,groups:bool,
    by_set:BTreeMap<Vec<u64>,u32>,sets:BTreeMap<u32,(Vec<u64>,BTreeSet<Dependency>)>,
    by_member:BTreeMap<u64,BTreeSet<u32>>,rows:BTreeMap<Dependency,BTreeSet<u32>>,next:u32,
    audit_wakes:bool,observed_set_rows_woken:u64,notified_groups:u64,notified_rows:u64,member_registrations:u64,row_links:u64,per_row_registrations:u64,
}
impl Default for Dictionary{fn default()->Self{
    Self{mode:match std::env::var("EGGFUSE_SET_REPR").as_deref(){Ok("mask")=>Repr::Mask,Ok("segments")=>Repr::Segments,_=>Repr::Sparse},
    forward:vec![],redirections:0,segment_scans:0,groups:std::env::var("EGGFUSE_SET_SUBSCRIPTION").as_deref()==Ok("instance"),by_id:BTreeMap::new(),ids:vec![],fault:None,
    created:0,live:0,peak:0,canon:0,canon_members:0,normalized:0,insert:0,inter:0,union:0,length:0,
    by_set:BTreeMap::new(),sets:BTreeMap::new(),by_member:BTreeMap::new(),rows:BTreeMap::new(),next:0,
    audit_wakes:std::env::var("EGGFUSE_SET_WAKE_AUDIT").as_deref()==Ok("1"),observed_set_rows_woken:0,notified_groups:0,notified_rows:0,member_registrations:0,row_links:0,per_row_registrations:0}
}}
thread_local!{static D:RefCell<Dictionary>=RefCell::new(Default::default());}
impl Dictionary{
    fn intern(&mut self,id:u64)->Result<usize,String>{
        if let Some(i)=self.by_id.get(&id){return Ok(*i);}
        let i=self.ids.len();
        if self.mode==Repr::Mask && i>=63{return Err("single Set mask exceeds 63 admitted member identities".into());}
        self.ids.push(id);self.forward.push(i);self.by_id.insert(id,i);Ok(i)
    }
    fn create(&mut self,data:Data)->SetData{
        let s=SetData{data};self.created+=1;self.live+=s.bytes() as i64;self.peak=self.peak.max(self.live);s
    }
    fn encode(&mut self,mut members:Vec<u64>)->Result<SetData,String>{
        members.sort_unstable();members.dedup();
        let data=match self.mode{
           Repr::Sparse=>Data::Sparse(members),
           Repr::Mask=>{let mut w=0;for id in members{w|=1u64<<self.intern(id)?;}Data::Mask(w)},
           Repr::Segments=>{let mut segments=BTreeMap::new();for id in members{let bit=self.intern(id)?;*segments.entry((bit/64) as u32).or_insert(0u64)|=1u64<<(bit%64);}Data::Segments(segments.into_iter().collect())},
        };Ok(self.create(data))
    }
}
impl SetData {
    fn bytes(&self)->usize{std::mem::size_of::<Self>()+match &self.data{Data::Mask(_)=>0,Data::Segments(s)=>s.capacity()*std::mem::size_of::<(u32,u64)>(),Data::Sparse(v)=>v.capacity()*8}}
    fn decode(&self,d:&Dictionary)->Vec<u64>{
        match &self.data{
            Data::Sparse(v)=>v.clone(),
            _=>{
                let mut v=Vec::with_capacity(self.len());
                let mut word=|seg:usize,mut bits:u64|{while bits!=0{let i=seg*64+bits.trailing_zeros() as usize;v.push(d.ids[i]);bits&=bits-1;}};
                match &self.data{Data::Mask(w)=>word(0,*w),Data::Segments(s)=>for &(i,w) in s{word(i as usize,w)},_=>unreachable!()}
                v.sort_unstable();v
            }
        }
    }
    pub fn values(&self)->Vec<Value>{D.with_borrow(|d|self.decode(d).into_iter().map(Value::Eq).collect())}
    pub fn len(&self)->usize{match &self.data{Data::Mask(w)=>w.count_ones() as usize,Data::Segments(s)=>s.iter().map(|(_,w)|w.count_ones() as usize).sum(),Data::Sparse(v)=>v.len()}}
    fn contains(&self,id:u64)->bool{
        match &self.data{
            Data::Sparse(v)=>v.binary_search(&id).is_ok(),
            Data::Mask(w)=>D.with_borrow(|d|d.by_id.get(&id).is_some_and(|i|w&(1<<i)!=0)),
            Data::Segments(s)=>D.with_borrow(|d|d.by_id.get(&id).is_some_and(|i|s.binary_search_by_key(&((i/64) as u32),|p|p.0).ok().is_some_and(|j|s[j].1&(1<<(i%64))!=0))),
        }
    }
    fn bin(&self,other:&SetData,kind:&str)->Result<Arc<Self>,String>{
        let op=|a:u64,b:u64|match kind{"set-union"|"insert-or"=>a|b,"set-intersect"=>a&b,_=>a&!b};
        D.with_borrow_mut(|d|{
            if kind=="set-union"{d.union+=1;}else if kind=="set-intersect"{d.inter+=1;}
            let data=match (&self.data,&other.data){
                (Data::Mask(a),Data::Mask(b))=>Data::Mask(op(*a,*b)),
                (Data::Segments(a),Data::Segments(b))=>{
                    d.segment_scans+=(a.len()+b.len()) as u64;let (mut i,mut j)=(0,0);let mut out=Vec::new();
                    while i<a.len()||j<b.len(){
                        let k=a.get(i).map(|p|p.0).unwrap_or(u32::MAX).min(b.get(j).map(|p|p.0).unwrap_or(u32::MAX));
                        let l=if a.get(i).is_some_and(|p|p.0==k){i+=1;a[i-1].1}else{0};
                        let r=if b.get(j).is_some_and(|p|p.0==k){j+=1;b[j-1].1}else{0};
                        let w=op(l,r);if w!=0{out.push((k,w));}
                    }Data::Segments(out)
                },
                (Data::Sparse(a),Data::Sparse(b))=>{
                    let (mut i,mut j)=(0,0);let mut v=Vec::new();
                    while i<a.len()||j<b.len(){
                        let next=match(a.get(i),b.get(j)){(Some(x),Some(y))=>*x.min(y),(Some(x),_)=>*x,(_,Some(y))=>*y,_=>break};
                        let l=a.get(i)==Some(&next);let r=b.get(j)==Some(&next);if l{i+=1;}if r{j+=1;}
                        if op(l as u64,r as u64)&1!=0{v.push(next);}
                    }Data::Sparse(v)
                },_=>return Err("mixed Set layouts".into())
            };Ok(Arc::new(d.create(data)))
        })
    }
}
impl Drop for SetData{fn drop(&mut self){let _=D.try_with(|d|{if let Ok(mut d)=d.try_borrow_mut(){d.live-=self.bytes() as i64;}});}}
impl PartialEq for SetData{fn eq(&self,o:&Self)->bool{match (&self.data,&o.data){(Data::Mask(a),Data::Mask(b))=>a==b,(Data::Segments(a),Data::Segments(b))=>a==b,(Data::Sparse(a),Data::Sparse(b))=>a==b,_=>self.values()==o.values()}}}
impl Eq for SetData{}
impl Ord for SetData{fn cmp(&self,o:&Self)->Ordering{if self==o{return Ordering::Equal;}match (&self.data,&o.data){(Data::Sparse(a),Data::Sparse(b))=>a.cmp(b),_=>self.values().cmp(&o.values())}}}
impl PartialOrd for SetData{fn partial_cmp(&self,o:&Self)->Option<Ordering>{Some(self.cmp(o))}}
impl Hash for SetData{fn hash<H:Hasher>(&self,h:&mut H){self.values().hash(h)}}
impl Serialize for SetData{fn serialize<S:serde::Serializer>(&self,s:S)->Result<S::Ok,S::Error>{self.values().serialize(s)}}
impl<'de> Deserialize<'de> for SetData{fn deserialize<A:serde::Deserializer<'de>>(d:A)->Result<Self,A::Error>{let v=Vec::<Value>::deserialize(d)?;encode(&v).map_err(serde::de::Error::custom)}}
fn encode(v:&[Value])->Result<SetData,String>{
    let ids=v.iter().map(|v|if let Value::Eq(id)=v{Ok(*id)}else{Err("Set trial requires e-class members")}).collect::<Result<Vec<_>,_>>()?;
    D.with_borrow_mut(|d|d.encode(ids))
}
pub fn make(v:&[Value])->Result<Value,String>{Ok(Value::Set(Arc::new(encode(v)?)))}
pub fn canonical(s:&Arc<SetData>,p:&Parents)->Value{
    let next=D.with_borrow_mut(|d|{
        d.canon+=1;
        let project=|mut bit:usize,forward:&[usize]|{while forward[bit]!=bit{bit=forward[bit];}bit};
        match &s.data{
            Data::Mask(word)=>{
                if d.redirections==0{return None;}
                let mut bits=*word;let mut out=0u64;
                while bits!=0{let n=bits.trailing_zeros() as usize;out|=1u64<<project(n,&d.forward);bits&=bits-1;d.canon_members+=1;}
                if out==*word{return None;}d.normalized+=1;Some(Arc::new(d.create(Data::Mask(out))))
            },
            Data::Segments(segments)=>{
                if d.redirections==0{return None;}
                d.segment_scans+=segments.len() as u64;
                let mut changed=false;
                for &(seg,mut bits) in segments{
                    while bits!=0{let bit=seg as usize*64+bits.trailing_zeros() as usize;bits&=bits-1;d.canon_members+=1;
                        if d.forward[bit]!=bit{changed=true;break;}}
                    if changed{break;}
                }
                if !changed{return None;}
                let mut out=BTreeMap::new();
                for &(seg,mut bits) in segments{
                    while bits!=0{let bit=project(seg as usize*64+bits.trailing_zeros() as usize,&d.forward);bits&=bits-1;
                        *out.entry((bit/64) as u32).or_insert(0u64)|=1u64<<(bit%64);d.canon_members+=1;}
                }
                d.normalized+=1;Some(Arc::new(d.create(Data::Segments(out.into_iter().collect()))))
            },
            Data::Sparse(ids)=>{
                d.canon_members+=ids.len() as u64;
                if !ids.iter().any(|id|p.contains_key(id)){return None;}
                let mut v=ids.iter().map(|id|root(p,*id)).collect::<Vec<_>>();v.sort_unstable();v.dedup();
                if &v==ids{return None;}d.normalized+=1;Some(Arc::new(d.create(Data::Sparse(v))))
            }
        }
    });Value::Set(next.unwrap_or_else(||s.clone()))
}
pub fn primitive(name:&str,args:&[Value])->Result<Option<Value>,String>{
    if name=="set-empty"||name=="set-of"{return make(args).map(Some);}
    let Value::Set(s)=&args[0] else{return Err("set expected".into())};
    match name{
        "set-length"=>{D.with_borrow_mut(|d|d.length+=1);Ok(Some(Value::Int(s.len() as i64)))},
        "set-insert"|"set-remove"|"set-contains"|"set-not-contains"=>{
            let Value::Eq(id)=args[1] else{return Err("set element type".into())};
            let present=s.contains(id);
            if name=="set-contains"||name=="set-not-contains"{return Ok((present==(name=="set-contains")).then_some(Value::Int(0)));}
            if name=="set-insert"{D.with_borrow_mut(|d|d.insert+=1);}
            if present==(name=="set-insert"){return Ok(Some(Value::Set(s.clone())));}
            if name=="set-remove"{let vals=s.values().into_iter().filter(|v|*v!=Value::Eq(id)).collect::<Vec<_>>();return make(&vals).map(Some);}
            let Value::Set(one)=make(&[Value::Eq(id)])? else{unreachable!()};Ok(Some(Value::Set(s.bin(&one,"insert-or")?)))
        }
        "set-union"|"set-intersect"|"set-diff"=>{let Value::Set(b)=&args[1] else{return Err("set expected".into())};Ok(Some(Value::Set(s.bin(b,name)?)))},
        _=>Err("unsupported Set primitive".into())
    }
}

pub fn subscribe(d:Dependency,values:&[Value],p:&Parents)->bool{
    let grouped=D.with_borrow(|s|s.groups);
    let members=values.iter().filter_map(|v|if let Value::Set(x)=v{Some(x)}else{None})
        .map(|x|{let mut v:Vec<_>=x.values().iter().map(|v|if let Value::Eq(i)=v{root(p,*i)}else{unreachable!()}).collect();v.sort_unstable();v.dedup();v})
        .filter(|v|!v.is_empty()).collect::<Vec<_>>();
    D.with_borrow_mut(|s|{
        if !grouped{s.per_row_registrations+=members.iter().map(|v|v.len() as u64).sum::<u64>();return;}
        let mut fresh=BTreeSet::new();
        for key in members{
            let id=if let Some(id)=s.by_set.get(&key){*id}else{
                let id=s.next;s.next+=1;
                for &m in &key{s.by_member.entry(m).or_default().insert(id);s.member_registrations+=1;}
                s.by_set.insert(key.clone(),id);s.sets.insert(id,(key,BTreeSet::new()));id
            };
            fresh.insert(id);
        }
        let old=s.rows.remove(&d).unwrap_or_default();
        for id in old.difference(&fresh){
            let (refs,rows)=s.sets.get_mut(id).unwrap();rows.remove(&d);
            if rows.is_empty(){
                let key=refs.clone();s.sets.remove(id);s.by_set.remove(&key);
                for m in key{let m=root(p,m);if let Some(b)=s.by_member.get_mut(&m){b.remove(id);if b.is_empty(){s.by_member.remove(&m);}}}
            }
        }
        for id in fresh.difference(&old){s.sets.get_mut(id).unwrap().1.insert(d);s.row_links+=1;}
        if !fresh.is_empty(){s.rows.insert(d,fresh);}
    });
    grouped
}
pub fn wake(hi:u64,lo:u64)->BTreeSet<Dependency>{
    D.with_borrow_mut(|s|{
        if let Some(&old)=s.by_id.get(&hi){
            match s.intern(lo){Ok(new)=>{s.forward[old]=new;s.redirections+=1;},Err(e)=>{s.fault=Some(e);}}
        }
        let mut out=BTreeSet::new();let groups=s.by_member.remove(&hi).unwrap_or_default();
        for id in &groups{if let Some((_,rows))=s.sets.get(id){s.notified_groups+=1;out.extend(rows.iter().copied());}}
        s.notified_rows+=out.len() as u64;if !groups.is_empty(){s.by_member.entry(lo).or_default().extend(groups);}
        out
    })
}
pub fn fault()->Option<String>{D.with_borrow(|d|d.fault.clone())}
pub fn report()->J{D.with_borrow(|d|json!({"created":d.created,"live_payload_bytes":d.live,"peak_payload_bytes":d.peak,
    "registry_members":d.ids.len(),"forwarding_entries":d.redirections,"segment_word_visits":d.segment_scans,"dense_reverse_capacity_bytes":d.ids.capacity()*8,"canon_calls":d.canon,"visited_members":d.canon_members,"changed_set_values":d.normalized,
    "insert":d.insert,"union":d.union,"intersect":d.inter,"length":d.length,"per_row_member_registrations":d.per_row_registrations,
    "groups":d.groups,"group_member_registrations":d.member_registrations,"group_row_links":d.row_links,"live_groups":d.sets.len(),
    "live_group_member_links":d.by_member.values().map(BTreeSet::len).sum::<usize>(),"live_group_row_links":d.rows.values().map(BTreeSet::len).sum::<usize>(),
    "observed_set_rows_woken":d.observed_set_rows_woken,"notified_groups":d.notified_groups,"notified_rows":d.notified_rows}))}

pub fn release_groups(){D.with_borrow_mut(|s|{s.by_set=BTreeMap::new();s.sets=BTreeMap::new();s.by_member=BTreeMap::new();s.rows=BTreeMap::new();});}
pub fn release_dictionary(){D.with_borrow_mut(|s|{s.ids=vec![];s.forward=vec![];s.by_id=BTreeMap::new();});}

pub fn auditing_rows()->bool{D.with_borrow(|s|s.audit_wakes && !s.groups)}
pub fn count_set_row(){D.with_borrow_mut(|s|s.observed_set_rows_woken+=1);}
