// Private experiment module attached to the native graph at mark_affected.
use super::*;
use serde::{Deserialize,Serialize};
use serde_json::json;
use std::cell::RefCell;

pub const F:usize=12;
pub const H:usize=12;
#[derive(Clone,Deserialize,Default)]
pub struct Weights { pub first:Vec<Vec<f32>>,pub bias:Vec<f32>,pub last:Vec<Vec<f32>>,pub offset:Vec<f32> }
impl Weights {
    fn infer(&self, x:&[f32;F])->(bool,bool) {
        let mut y=[0f32;H];
        for (i,v) in y.iter_mut().enumerate(){
            *v=(self.bias[i]+self.first[i].iter().zip(x).map(|(a,b)|a*b).sum::<f32>()).max(0.);
        }
        let score=|k:usize| self.offset[k]+self.last[k].iter().zip(y).map(|(a,b)|a*b).sum::<f32>();
        (score(0)>0.,score(1)>0.)
    }
}

#[derive(Clone,Serialize,Default)]
struct Counts {
    candidates:u64, fast_eligible:u64, proposed:u64, applied:u64, rejected:u64,
    wrong_external:u64, unsafe_external_rejected:u64, eligible_port_work:u64,
    covered_port_work:u64, actual_external:u64, pending:u64, ambiguous:u64, key_changed:u64,
    local_only:u64,with_external:u64, catalog:u64, catalog_applied:u64, stale:u64
}
#[derive(Default)]
struct Trial { mode:String, detailed:bool,catalog:Vec<bool>,weights:Weights,counts:Counts,events:Vec<serde_json::Value>,decisions:Vec<[bool;2]>,delivered:Vec<[u64;5]>,current:Option<(u64,u64,u64)>,previous:Option<(u64,u64,u64)> }
thread_local! {static TRIAL:RefCell<Trial>=RefCell::new(Trial::default());}
pub fn configure(mode:&str,catalog:Vec<bool>,weights:Weights,detailed:bool){
    if mode=="model" || mode=="shadow" {assert!(weights.first.len()==H && weights.first.iter().all(|v|v.len()==F) && weights.last.len()==2 && weights.last.iter().all(|v|v.len()==H));}
    TRIAL.with(|s|*s.borrow_mut()=Trial{mode:mode.into(),detailed,catalog,weights,..Default::default()});
}
pub fn report()->serde_json::Value{
    TRIAL.with(|s|{let mut t=s.borrow_mut();json!({"counts":t.counts,"events":std::mem::take(&mut t.events),"delivered":std::mem::take(&mut t.delivered),"decisions":std::mem::take(&mut t.decisions)})})
}

pub(super) fn begin_union(index:u64,from:u64,to:u64){
    TRIAL.with(|store|{
        let mut t=store.borrow_mut();
        t.previous=t.current;t.current=Some((index,from,to));
    });
}
pub(super) fn delivered(d:Dependency,direct:bool){
    TRIAL.with(|store|{
        let mut t=store.borrow_mut();
        if !t.detailed{return}
        let u=t.current.unwrap().0;
        let row=match d {Dependency::Fact(f)=>[u,0,f.cell as u64,f.op as u64,u64::from(direct)],
                         Dependency::Function(i)=>[u,1,i as u64,0,u64::from(direct)]};
        t.delivered.push(row);
    });
}

impl Graph {
    pub(super) fn trial_result(&mut self,f:FactRef,from:u64,to:u64,affected:&UseSet)->bool{
        TRIAL.with(|store|{
            let mut t=store.borrow_mut();
            if t.mode=="generic" {return false}
            let Some(cell)=self.cells.get(&f.cell) else{return false};
            let Some(st)=cell.facts.get(&f.op) else{return false};
            let Some((tab,fields))=&st.decoded else{return false};
            let Some(cols)=self.program.repair_ports.key_eq_columns[*tab].as_ref() else{return false};
            let is_catalog=t.catalog.get(*tab).copied().unwrap_or(false);
            let old=Value::Eq(from);
            let result=fields.last()==Some(&old);
            if t.mode=="gate" && !t.detailed {
                // The exact result comparison is cheaper than inspecting every key.
                return result && !self.dirty.contains(&Dependency::Fact(f)) && !self.dirty_markers.contains(&f)
                    && self.finish_result_port(f,from,to);
            }
            let dirty=self.dirty.contains(&Dependency::Fact(f)) || self.dirty_markers.contains(&f);
            let bound=self.intern.get(&st.hash).map_or(0,|v|v.len());
            let same=|dep:&Dependency|matches!(dep,Dependency::Fact(other) if other.cell==f.cell);
            // Native UseSet is ordered by kind, cell and operation. Other cells or
            // functions must be outside these two endpoints when both are local.
            let first_other=affected.first().is_some_and(|v|!same(v));
            let external=first_other || affected.last().is_some_and(|v|!same(v));
            let first_from=cols.first().is_some_and(|&i|fields[i]==old);
            let first_to=cols.first().is_some_and(|&i|fields[i]==Value::Eq(to));
            let arity=fields.len();
            let x=[(arity.min(8) as f32)/8.,(cols.len().min(8) as f32)/8.,result as u8 as f32,
                   first_from as u8 as f32,first_to as u8 as f32,dirty as u8 as f32,
                   (bound.min(3) as f32)/3.,(affected.len().min(16) as f32)/16.,first_other as u8 as f32,
                   is_catalog as u8 as f32,(f.op.min(16) as f32)/16.,(cell.recipe_depth.min(8) as f32)/8.];
            let detailed=t.detailed || t.mode=="capture";
            let exact=if detailed || t.mode=="oracle" {
                Some(result && !dirty && bound==1 && self.intern[&st.hash].first()==Some(&f)
                     && !cols.iter().any(|&i|fields[i]==old))
            }else{None};
            let (fast,leave)=match t.mode.as_str(){
                "capture"=>(false,true),"oracle"=>(exact.unwrap(),external),
                "gate"=>(result,true),"every"=>(true,true),"unsafe"=>(true,false),"stale"=>(true,true),
                "model"|"shadow"=>t.weights.infer(&x),_=>panic!("unknown repair policy")
            };
            let tag=if t.mode=="stale" {t.previous.or(t.current)}else{t.current};
            let stale=tag!=Some((self.stats.unions,from,to));
            if t.mode=="shadow" {t.decisions.push([fast,leave]);}
            let admissible=t.mode!="shadow" && fast && !stale && (!external || leave) && !dirty;
            let prior_depth=cell.recipe_depth;
            let template=cell.template;
            let table_id=*tab;
            let weight=arity as u64;
            if t.mode=="capture"{
                let same_count=affected.iter().filter(|d|same(d)).count();
                let key_positions:Vec<usize>=cols.iter().copied().filter(|&i|fields[i]==old).collect();
                assert_eq!(external, affected.iter().any(|d|!same(d)));
                let mut chain=0;let mut parent=cell.parent;
                while let Some(p)=parent{chain+=1;if chain>=16{break}parent=self.cells.get(&p.cell).and_then(|c|c.parent);}
                t.events.push(json!({"x":x,"fast":exact.unwrap(),"external":external,"weight":weight,
                                    "epoch":self.epoch,"union":self.stats.unions,"cell":f.cell,"op":f.op,
                                    "template":template,"table":table_id,"depth":prior_depth,
                                    "outside_count":affected.len()-same_count,"uses":affected.len(),
                                    "hash_bucket":bound,"dirty":dirty,"key_from":!key_positions.is_empty(),"positions":key_positions,"parent_chain":chain}));
            }
            // finish_result_port re-checks every key equality field, result, exact
            // bucket and source address before writing. All other incidences remain
            // in mark_affected's ordered loop, including independent readers.
            let applied=admissible && self.finish_result_port(f,from,to);
            if detailed{
                let c=&mut t.counts;c.candidates+=1;c.fast_eligible+=u64::from(exact.unwrap());c.proposed+=u64::from(fast);
                c.applied+=u64::from(applied);c.rejected+=u64::from(fast && !applied);c.actual_external+=u64::from(external);
                c.wrong_external+=u64::from(leave!=external);c.unsafe_external_rejected+=u64::from(fast && !leave && external);
                c.eligible_port_work+=u64::from(exact.unwrap())*weight;c.covered_port_work+=u64::from(applied)*weight;
                c.catalog+=u64::from(is_catalog);c.catalog_applied+=u64::from(is_catalog && applied);
                c.pending+=u64::from(dirty);c.ambiguous+=u64::from(bound!=1);c.key_changed+=u64::from(first_from);
                c.local_only+=u64::from(applied && !external);c.with_external+=u64::from(applied && external);
                c.stale+=u64::from(stale && fast);
                assert!(!applied || exact.unwrap());
            }
            applied
        })
    }
}
