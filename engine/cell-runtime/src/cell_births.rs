//! A new Cell result excludes external constructor candidates until a shared
//! effect or another graph birth intervenes. Bake supplies exact local sites;
//! workers build actual row storage, not a second binding or operation log.
use super::*;
use crate::cell::{Definition, EffectWriter};
use std::time::Instant;

#[derive(Clone, Debug, PartialEq, Eq)]
struct Step {
    operation: usize,
    region: usize,
    table: usize,
    destination: usize,
    keys: Vec<Arg>,
    anchors: Vec<(usize,usize)>, // newest producer first: (operation, slot)
    candidates: usize,
    prior: usize,
    skipped: usize,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Plan { steps:Vec<Step>, operators:Vec<Vec<usize>>, continues:Vec<bool> }
impl Plan {
    pub(crate) fn sites(&self)->usize {self.steps.iter().filter(|s|!s.anchors.is_empty()).count()}
    pub(crate) fn continues_after(&self,operation:usize)->bool {self.continues.get(operation).copied().unwrap_or(false)}
    pub(crate) fn derive(p:&Program, rule:usize) -> Option<Self> {
        if cfg!(feature="structural-depth") || cfg!(feature="keeper-proof") { return None; }
        let cell=Definition::new(p,rule).ok()?;
        if cell.rule.inputs.iter().any(|s|cell.template.defs.contains_key(s)) { return None; }
        let mut steps=vec![];
        let mut operators:Vec<Vec<usize>>=vec![];
        let mut origins=BTreeMap::new();
        let mut tables:BTreeMap<usize,usize>=BTreeMap::new();
        let mut region=0;
        let mut skipped=0;
        for (operation,op) in cell.template.ops.iter().enumerate() {
            if p.known_results.static_skip[rule][operation] { skipped+=1; continue; }
            if matches!(op,Op::Copy(..)) {continue;}
            let ctor=match op {
                Op::Let(dst,Call::Table(t),args) if p.tables[*t].constructor && p.tables[*t].virtual_fact => Some((*dst,*t,args)),
                _ => None,
            };
            let Some((destination,table,args))=ctor else {
                region+=1;origins.clear();tables.clear();skipped=0;continue;
            };
            if cell.value(&Arg::Slot(destination))!=Arg::Slot(destination)
                || cell.template.parent_columns.contains_key(&destination) {
                region+=1;origins.clear();tables.clear();skipped=0;continue;
            }
            let keys:Vec<_>=args.iter().map(|a|cell.value(a)).collect();
            let mut anchors:Vec<_>=keys.iter().filter_map(|a|match a {
                Arg::Slot(s)=>origins.get(s).map(|&op|(op,*s)), _=>None,
            }).collect();
            anchors.sort_unstable_by(|a,b|b.cmp(a));anchors.dedup();
            let group=*tables.entry(table).or_insert_with(|| {operators.push(vec![]);operators.len()-1});
            let candidates=&mut operators[group];
            steps.push(Step {operation,region,table,destination,keys,anchors,
                candidates:group,prior:candidates.len(),skipped});
            skipped=0;candidates.push(operation);origins.insert(destination,operation);
        }
        if !steps.iter().any(|s|!s.anchors.is_empty()) {return None;}
        let mut continues=vec![false;cell.template.ops.len()];
        let mut next=false;
        for (operation,op) in cell.template.ops.iter().enumerate().rev() {
            if let Ok(i)=steps.binary_search_by_key(&operation,|s|s.operation) {
                if steps.get(i+1).is_some_and(|s|s.region!=steps[i].region) {next=false;}
                continues[operation]=next;
                next|=!steps[i].anchors.is_empty();
            } else if matches!(op,Op::Copy(..)) || p.known_results.static_skip[rule][operation] {
                continues[operation]=next;
            } else {next=false;}
        }
        Some(Self{steps,operators,continues})
    }
    pub(crate) fn storage_bytes(&self)->usize {
        self.steps.capacity()*std::mem::size_of::<Step>() + self.steps.iter().map(|s|
            s.keys.capacity()*std::mem::size_of::<Arg>() + s.anchors.capacity()*std::mem::size_of::<(usize,usize)>()).sum::<usize>()
            + self.operators.capacity()*std::mem::size_of::<Vec<usize>>()
            + self.operators.iter().map(|v|v.capacity()*std::mem::size_of::<usize>()).sum::<usize>()
            + self.continues.capacity()*std::mem::size_of::<bool>()
    }
    fn start(&self,position:usize)->Option<usize> {
        let i=self.steps.binary_search_by_key(&position,|s|s.operation).ok()?;
        (!self.steps[i].anchors.is_empty()).then_some(i)
    }
}

#[derive(Clone, Copy)]
pub(crate) struct Window { first:usize, births:u64, unions:u64 }
impl Window {
    pub(crate) fn seed(g:&Graph,cell:u32,next:usize)->Option<Self> {
        let previous=next.checked_sub(1)?;
        let frame=g.rhs_frame(cell)?;
        let Some(Op::Let(dst,Call::Table(table),_))=g.program.templates[frame.template].ops.get(previous) else {return None;};
        let expected=Value::Eq(((cell as u64)<<32)|(*dst as u64+1));
        if !g.program.tables[*table].constructor || !g.program.tables[*table].virtual_fact
            || fields(frame,&[],previous)?.last()!=Some(&expected)
            || canon(&expected,&g.parents)!=expected {return None;}
        Some(Self {first:previous,births:g.stats.logical_facts_created,unions:g.stats.unions})
    }
    pub(crate) fn observes(g:&Graph,cell:u32,position:usize,old:Option<Self>)->Option<Self> {
        let frame=g.rhs_frame(cell)?;
        if matches!(g.program.templates[frame.template].ops[position],Op::Copy(..)) {return old;}
        if !matches!(g.program.templates[frame.template].ops[position],Op::Let(_,Call::Table(t),_)
            if g.program.tables[t].constructor && g.program.tables[t].virtual_fact) {return None;}
        if let Some(mut old)=old.filter(|w|w.unions==g.stats.unions
            && g.stats.logical_facts_created==w.births+u64::from(frame.facts.contains_key(&(position as u32)))) {
            old.births=g.stats.logical_facts_created;return Some(old);
        }
        Self::seed(g,cell,position+1)
    }
}

#[derive(Default, Serialize)]
pub(crate) struct Counts {
    pub plan_checks:u64, pub resume_checks:u64,
    pub window_checks:u64,
    pub attempts:u64, pub invalidated:u64, pub anchor_checks:u64,
    pub source_operand_reads:u64,
    pub operand_reads:u64, pub missing_operands:u64, pub candidate_ranges:u64,
    pub candidate_probes:u64, pub field_checks:u64, pub local_reuses:u64,
    pub local_births:u64, pub hashes:u64, pub row_fields:u64,
    pub identity_checks:u64,
    pub pending_growths:u64, pub pending_bytes:u64, pub value_writes:u64,
    pub slot_growths:u64, pub slot_bytes:u64, pub committed_rows:u64,
    pub worker_batches:u64, pub worker_operations:u64, pub worker_wait_ns:u64,
}
impl Counts {
    pub(crate) fn add(&mut self,b:Self) {
        macro_rules! add {($($f:ident),*)=>{$(self.$f+=b.$f;)*};}
        add!(plan_checks,resume_checks,window_checks,attempts,invalidated,anchor_checks,source_operand_reads,operand_reads,missing_operands,candidate_ranges,
            candidate_probes,field_checks,local_reuses,local_births,hashes,row_fields,identity_checks,
            pending_growths,pending_bytes,value_writes,slot_growths,slot_bytes,committed_rows,
            worker_batches,worker_operations,worker_wait_ns);
    }
}
struct Born { operation:usize, table:usize, fields:RowFields, hash:u64 }
pub(crate) fn record_bytes()->usize {std::mem::size_of::<Born>()}
type Rows=smallvec::SmallVec<[Born;4]>;
pub(crate) fn pending_bytes()->usize {std::mem::size_of::<Rows>()}
struct Piece { end:usize, rows:Rows, aliases:u64, counts:Counts }

fn fields<'a>(frame:&'a Cell,rows:&'a [Born],operation:usize)->Option<&'a [Value]> {
    if let Ok(i)=rows.binary_search_by_key(&operation,|r|r.operation) {return Some(&rows[i].fields);}
    frame.facts.get(&(operation as u32))?.decoded.as_ref().map(|(_,v)|v.as_ref())
}
fn anchor(step:&Step,frame:&Cell,rows:&[Born],first:usize,cell:u32,parents:&Parents,counts:&mut Counts)->Option<usize> {
    for &(op,slot) in &step.anchors {
        counts.anchor_checks+=1;
        let expected=Value::Eq(((cell as u64)<<32)|(slot as u64+1));
        if op>=first && fields(frame,rows,op).and_then(|v|v.last())==Some(&expected)
            && canon(&expected,parents)==expected {return Some(op);}
    }
    None
}
fn operand(frame:&Cell,template:&Template,rows:&[Born],first:usize,position:usize,
    arg:&Arg,parents:&Parents)->Option<Value> {
    match arg {
        Arg::Literal(v)=>Some(canon(v,parents)),
        Arg::Slot(s)=> {
            if let Some(v)=frame.values.get(s) {return Some(canon(v,parents));}
            let op=*template.defs.get(s)?;
            if op<first || op>=position {return None;}
            Some(canon(fields(frame,rows,op)?.last()?,parents))
        }
    }
}
impl Plan {
    fn prepare(&self,from:usize,limit:usize,cell:u32,frame:&mut Cell,template:&Template,
        parents:&Parents,first:usize,first_anchor:usize,first_key:smallvec::SmallVec<[Value;4]>,
        receipts:&mut EffectWriter<'_>)->Piece {
        let mut out=Piece {end:frame.completed_prefix,rows:Rows::new(),aliases:0,counts:Counts::default()};
        let capacity=frame.values.capacity_bytes();
        let mut first_key=Some(first_key);
        for (index,step) in self.steps[from..limit].iter().enumerate() {
            let selected=if index==0 {Some(first_anchor)} else {
                anchor(step,frame,&out.rows,first,cell,parents,&mut out.counts)
            };
            let Some(anchor)=selected else {break;};
            let key=if let Some(key)=first_key.take() {key} else {
            let mut key=smallvec::SmallVec::<[Value;4]>::new();
            for arg in &step.keys {
                out.counts.operand_reads+=1;
                let Some(value)=operand(frame,template,&out.rows,first,step.operation,arg,parents)
                    else {out.counts.missing_operands+=1;break;};
                key.push(value);
            }
            if key.len()!=step.keys.len() {break;}
            key
            };
            out.counts.candidate_ranges+=1;
            let candidates=&self.operators[step.candidates][..step.prior];
            let candidates=&candidates[candidates.partition_point(|&op|op<=anchor)..];
            let mut reused=None;
            for &prior in candidates {
                out.counts.candidate_probes+=1;
                let Some(old)=fields(frame,&out.rows,prior) else {continue;};
                if old.len()!=key.len()+1 {continue;}
                let equal=old[..key.len()].iter().zip(&key).all(|(a,b)| {
                    out.counts.field_checks+=1;a==b
                });
                if equal {reused=Some((prior,old.last().unwrap().clone()));break;}
            }
            let witness=if let Some((prior,value))=reused {
                frame.values.insert(step.destination,value);
                out.counts.value_writes+=1;out.counts.local_reuses+=1;
                FactRef{cell,op:prior as u32}
            } else {
                let value=Value::Eq(((cell as u64)<<32)|(step.destination as u64+1));
                out.counts.identity_checks+=1;
                if canon(&value,parents)!=value {break;}
                let hash=hashkey(step.table,&key);
                let fields=Graph::shared_fields(&key,&value);
                out.counts.hashes+=1;out.counts.row_fields+=fields.len() as u64;
                let before=if out.rows.spilled() {out.rows.capacity()} else {0};
                out.rows.push(Born{operation:step.operation,table:step.table,fields,hash});
                let after=if out.rows.spilled() {out.rows.capacity()} else {0};
                out.counts.pending_growths+=u64::from(before!=after);
                out.counts.pending_bytes+=((after-before)*std::mem::size_of::<Born>()) as u64;
                out.counts.local_births+=1;
                FactRef{cell,op:step.operation as u32}
            };
            receipts.record(step.operation,Dependency::Fact(witness));
            out.end=step.operation+1;
            // The first offered operation has no unexecuted gap before it.
            if step.operation!=self.steps[from].operation {out.aliases+=step.skipped as u64;}
        }
        let growth=frame.values.capacity_bytes().saturating_sub(capacity);
        out.counts.slot_growths+=u64::from(growth!=0);out.counts.slot_bytes+=growth as u64;
        out
    }
}

impl Graph {
    pub(crate) fn complete_local_births(&mut self,rule:usize,cell:u32,window:&mut Option<Window>,
        receipts:&mut EffectWriter<'_>,stop:usize,pool:Option<&rayon::ThreadPool>,grain:usize)->Result<Counts> {
        let mut counts=Counts {resume_checks:1,..Counts::default()};
        // These backends can have additional birth-time effects. Their source
        // handler remains authoritative until those effects join the proof.
        if self.stable_ports.is_some() || self.union_digest.is_some() || self.ownership.is_some()
            || self.local_unions.is_some() || cfg!(feature="keeper-proof") {return Ok(counts);}
        let Some(cert)=*window else {return Ok(counts);};
        let position=self.rhs_frame(cell).unwrap().completed_prefix;
        let Some(plan)=self.program.executions[rule].births.as_ref() else {return Ok(counts);};
        let Some(from)=plan.start(position).filter(|_|position<stop) else {return Ok(counts);};
        counts.attempts+=1;
        if cert.births!=self.stats.logical_facts_created || cert.unions!=self.stats.unions {
            counts.invalidated+=1;*window=None;return Ok(counts);
        }
        let region=plan.steps[from].region;
        let limit=from+plan.steps[from..].iter().take_while(|s|s.region==region && s.operation<stop).count();
        let Some(first_anchor)=anchor(&plan.steps[from],self.rhs_frame(cell).unwrap(),&[],cert.first,
            cell,&self.parents,&mut counts) else {return Ok(counts);};
        // This first boundary may use retained parent projections. Acquire its
        // ordinary operands once, then move the actual key into the worker.
        // An unproven window never dispatches an empty worker job.
        let first_key=self.inline_arguments(cell,&plan.steps[from].keys)?;
        counts.source_operand_reads+=first_key.len() as u64;
        let run_worker=pool.is_some() && limit-from>=grain;
        let clock=run_worker.then(Instant::now);
        let plan=&self.program.executions[rule].births.as_ref().unwrap();
        let template=&self.program.templates[self.program.rules[rule].template];
        // New root activation has already made this owner graph-addressable.
        // No worker borrows the mutable graph, index, Cursor or Rc plan owner.
        let frame=self.cells.get_mut(&cell).expect("new constructor owns its source Cell");
        let work=||plan.prepare(from,limit,cell,frame,template,&self.parents,cert.first,first_anchor,first_key,receipts);
        let mut piece=if run_worker {pool.unwrap().install(work)} else {work()};
        if let Some(clock)=clock {
            piece.counts.worker_batches+=1;
            piece.counts.worker_operations+=piece.counts.local_births+piece.counts.local_reuses;
            piece.counts.worker_wait_ns+=clock.elapsed().as_nanos() as u64;
        }
        for row in piece.rows {
            self.activate_fields(FactRef{cell,op:row.operation as u32},row.table,row.fields,row.hash,false)?;
            piece.counts.committed_rows+=1;
        }
        self.stats.constructor_requests+=piece.counts.local_births+piece.counts.local_reuses;
        self.stats.constructor_reused+=piece.counts.local_reuses;
        self.known_stats.static_eliminated+=piece.aliases;
        self.known_stats.avoided_lookups+=piece.aliases;
        self.rhs_frame_mut(cell).unwrap().completed_prefix=piece.end;
        if let Some(cert)=window {cert.births=self.stats.logical_facts_created;}
        counts.add(piece.counts);
        Ok(counts)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cell::Effects;
    use std::{rc::Rc,sync::Arc};
    fn graph()->Graph {
        let eq=json!({"kind":"eq","name":"E"});
        let template=Template{name:"local-birth".into(),sorts:vec![eq.clone();5],
            defs:[(1,0),(2,1),(3,2),(4,3)].into_iter().collect(),parent_columns:Default::default(),
            ops:Arc::new(vec![Op::Let(1,Call::Table(0),vec![Arg::Slot(0)]),
                Op::Let(2,Call::Table(0),vec![Arg::Slot(1)]),
                Op::Let(3,Call::Table(0),vec![Arg::Slot(1)]),
                Op::Let(4,Call::Table(0),vec![Arg::Slot(2)])])};
        let rule=Rule{template:0,query:Rc::new(vec![]),inputs:vec![0].into(),completion:Default::default(),
            seminaive:false,direct:None};
        let mut p:Program=serde_json::from_value(json!({
            "multi_stage":crate::multistage::MultiStage::default(),"entry_schedule":crate::entry_schedule::Plan::default(),
            "tables":[{"name":"F","schema":[eq,eq],"constructor":true,"virtual_fact":true,"internal":false,"merge":null}],
            "templates":[template],"rules":[rule],"sets":{},"control":[],"initial":[],"table_templates":[0],"artifact":{}
        })).unwrap();
        p.known_results.static_skip=vec![Rc::new(vec![false;4])];
        p.executions=vec![crate::cell::execution::Plan::derive(&p.tables,&p.templates[0],&[0])];
        p.executions[0].births=Plan::derive(&p,0);
        Graph::new(p).unwrap()
    }
    fn start(g:&mut Graph)->(u32,Value,Option<Window>) {
        let c=g.begin_transient(0,[(0,Value::Eq(100))].into_iter().collect(),None).unwrap();
        let u=g.construct(c,0,0,&[Arg::Slot(0)],1).unwrap();
        g.rhs_frame_mut(c).unwrap().completed_prefix=1;
        (c,u,Window::seed(g,c,1))
    }
    #[test]
    fn workers_build_the_existing_cell_and_locally_deduplicate_without_global_lookups() {
        let mut control=graph();let (c,_,_)=start(&mut control);
        for (op,input,dst) in [(1,1,2),(2,1,3),(3,2,4)] {control.construct(c,op,0,&[Arg::Slot(input)],dst).unwrap();}
        for workers in [0,4] {
            let mut g=graph();let (cell,_,mut window)=start(&mut g);
            let pool=(workers!=0).then(||rayon::ThreadPoolBuilder::new().num_threads(workers).build().unwrap());
            let mut receipts=Effects::default();let reads=g.key_lookup_calls.get();
            let counts=g.complete_local_births(0,cell,&mut window,&mut receipts.writer(),4,pool.as_ref(),1).unwrap();
            assert_eq!((counts.local_births,counts.local_reuses,counts.committed_rows),(2,1,2));
            assert_eq!(counts.worker_operations,if workers==0 {0}else{3});
            assert_eq!(counts.pending_growths,0,"small local pieces use inline row handles");
            assert_eq!(g.key_lookup_calls.get(),reads);
            assert_eq!(g.rhs_frame(cell).unwrap().completed_prefix,4);
            assert_eq!(g.slot(cell,2).unwrap(),g.slot(cell,3).unwrap());
            assert_eq!(g.export().unwrap(),control.export().unwrap());
            assert_eq!(g.stats.constructor_requests,control.stats.constructor_requests);
            assert_eq!(g.stats.constructor_reused,control.stats.constructor_reused);
            assert_eq!(g.maintenance.subscription_calls,control.maintenance.subscription_calls);
        }
    }
    #[test]
    fn an_external_birth_or_union_invalidates_local_exclusion_before_any_effect() {
        for union in [false,true] {
            let mut g=graph();let (cell,u,mut window)=start(&mut g);
            let foreign=g.begin_transient(0,[(0,u.clone())].into_iter().collect(),None).unwrap();
            let v=g.construct(foreign,0,0,&[Arg::Slot(0)],1).unwrap();
            if union {g.enqueue_union(u,Value::Eq(100)).unwrap();g.repair().unwrap();}
            let reads=g.key_lookup_calls.get();let facts=g.stats.logical_facts_created;
            let counts=g.complete_local_births(0,cell,&mut window,&mut Effects::default().writer(),4,None,1).unwrap();
            assert_eq!(counts.invalidated,1);assert!(window.is_none());
            assert_eq!(g.key_lookup_calls.get(),reads);assert_eq!(g.stats.logical_facts_created,facts);
            assert_eq!(g.rhs_frame(cell).unwrap().completed_prefix,1);
            let actual=g.construct(cell,1,0,&[Arg::Slot(1)],2).unwrap();
            assert_eq!(actual,canon(&v,&g.parents));
        }
    }
    #[test]
    fn new_fact_ownership_does_not_prove_a_new_result_identity() {
        let mut g=graph();let (cell,_,_)=start(&mut g);
        // A constructor Set / alias can install a fact with an old result.
        // The physical producer position alone must never certify freshness.
        g.cells.get_mut(&cell).unwrap().facts.get_mut(&0).unwrap().decoded=
            Some((0,row_fields(vec![Value::Eq(100),Value::Eq(200)])));
        assert!(Window::seed(&g,cell,1).is_none());
    }
    #[test]
    fn source_registration_adopts_the_prepared_row_allocation() {
        let mut g=graph();let (cell,u,_)=start(&mut g);
        let result=Value::Eq(((cell as u64)<<32)|3);
        let row=Graph::shared_fields(std::slice::from_ref(&u),&result);
        let allocation=row.as_ptr();let hash=hashkey(0,std::slice::from_ref(&u));
        g.activate_fields(FactRef{cell,op:1},0,row,hash,false).unwrap();
        assert_eq!(g.cells[&cell].facts[&1].decoded.as_ref().unwrap().1.as_ptr(),allocation);
        assert_eq!(g.fact(FactRef{cell,op:1}).unwrap().unwrap().values.as_ptr(),allocation);
    }
}
