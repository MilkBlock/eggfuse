//! A new Cell result excludes external constructor candidates until a shared
//! effect or another graph birth intervenes. Bake supplies exact local sites;
//! workers build actual row storage, not a second binding or operation log.
use super::*;
use crate::cell::{Definition, EffectWriter};
use crate::value::parent_epoch::Read;
#[path = "cell_births_shared.rs"]
mod shared;
#[path = "cell_root_births.rs"]
mod roots;
pub(crate) use roots::isolate as isolate_roots;
pub(crate) use shared::stream as stream_shared;
pub(crate) use shared::produce as produce_shared;
pub(crate) struct Completed { pub done: Done, pub effects: crate::cell::Effects }
pub(crate) fn execution_group()->Counts {Counts{execution_groups:1,..Counts::default()}}
pub(crate) fn execution_grain(tasks:&[(Job,crate::cell::Effects)],workers:usize)->usize {
    // Retain at least two groups per worker when possible. The compiler's
    // constructor/Unit instruction count bounds each serial run of instances;
    // it is a scheduling heuristic, not a measured time estimate.
    let widest=tasks.iter().map(|(job,_)|job.work_units()).max().unwrap_or(1).max(1);
    (tasks.len()/(2*workers.max(1))).clamp(1,8).min((32/widest).max(1))
}
#[path = "cell_birth_units.rs"]
pub(crate) mod units;
#[path = "cell_unit_registration.rs"]
mod unit_registration;
#[path = "cell_constructor_registration.rs"]
mod constructor_registration;
pub(crate) use unit_registration::Registration;

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
pub(crate) struct Plan { steps:Vec<Step>, operators:Vec<Vec<usize>>, continues:Vec<bool>, definitions:Vec<(usize,usize)>, batch_rule:bool, no_unions:bool, isolated:Vec<bool>, lineage:Vec<Vec<usize>>, roots:Vec<bool>, units:Option<units::Tail> }
impl Plan {
    pub(crate) fn batch_rule(&self)->bool {self.batch_rule}
    pub(crate) fn has_roots(&self)->bool {self.roots.iter().any(|&v|v)}
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
        if steps.is_empty() {return None;}
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
        // A queued tail is the final constructor region. Earlier primitives
        // have already succeeded at admission; a primitive after that region
        // could fail after later source Cells had mutated the graph, so reject
        // it. Total scalar/Unit writes still run at their source positions.
        let last_constructor=steps.last().unwrap().operation;
        let batch_rule=cell.template.ops.iter().enumerate().all(|(i,op)| {
          if p.known_results.static_skip[rule][i] {return true;}
          match op {
            Op::Copy(..)=>true,
            Op::Let(_,Call::Table(t),_)=>p.tables[*t].virtual_fact && p.tables[*t].constructor,
            Op::Let(_,Call::Primitive(..),_)=>i<last_constructor,
            Op::Union(a,b)=>[a,b].iter().all(|a|match cell.value(a) {
                Arg::Literal(Value::Eq(_))=>true,
                Arg::Slot(s)=>cell.template.sorts[s]["kind"]=="eq",_=>false,
            }),
            Op::Set(t,_,_)=> {
                let table=&p.tables[*t];let e=&table.merge;
                !table.virtual_fact && table.schema.last().is_some_and(|s|s["kind"]=="i64" || s["kind"]=="Unit")
                    && (matches!(e["var"].as_str(),Some("old"|"new"))
                        || table.schema.last().is_some_and(|s|s["kind"]=="i64")
                            && matches!(e["call"]["primitive"].as_str(),Some("min"|"max"))
                            && e["args"].as_array().is_some_and(|a|a.len()==2
                                && a.iter().all(|v|matches!(v["var"].as_str(),Some("old"|"new")))))
            }
            _=>false,
        }});
        let mut isolated=vec![false;steps.len()];
        if batch_rule {
            for from in 1..steps.len() {
                let seed=&steps[from-1];
                let mut fresh=vec![seed.operation];
                isolated[from]=steps[from..].iter().all(|step| {
                    if step.region!=seed.region {return false;}
                    let anchor=step.anchors.iter().find(|(op,_)|fresh.contains(op)
                        && operators[step.candidates][..step.prior].last().is_none_or(|prior|prior<=op));
                    if anchor.is_none() {return false;}
                    fresh.push(step.operation);true
                });
            }
        }
        // A dependent tail may reuse a peer's result. Prove only that every key
        // stays in the fresh cone, not that each operation creates a new node.
        // These are input slots, not runtime producer/consumer subscriptions.
        let lineage:Vec<Vec<usize>>=if batch_rule {steps.iter().enumerate().map(|(from,first)| {
            first.keys.iter().filter_map(|arg| {
                let Arg::Slot(seed)=arg else {return None;};
                let mut derived=vec![*seed];
                steps[from..].iter().all(|step| {
                    if step.region!=first.region || !step.keys.iter().any(|a|
                        matches!(a,Arg::Slot(s) if derived.contains(s))) {return false;}
                    derived.push(step.destination);true
                }).then_some(*seed)
            }).collect::<BTreeSet<_>>().into_iter().collect()
        }).collect()} else {vec![]};
        let units=units::Tail::derive(p,rule,last_constructor);
        let no_unions=!cell.template.ops.iter().any(|op|matches!(op,Op::Union(..)));
        // A missing first key can start the same fresh cone on a worker. Every
        // later constructor must consume that result (or one derived from it),
        // and the region must finish without an ordered/fallible suffix.
        let terminal=last_constructor+1==cell.template.ops.len() || units.as_ref()
            .is_some_and(|u|u.ends_at(cell.template.ops.len()));
        let roots=steps.iter().enumerate().map(|(i,step)|!cfg!(feature="rhs-locals") && batch_rule && no_unions && terminal
            && (i+1==steps.len() || steps[i+1].region==step.region
                && lineage[i+1].contains(&step.destination))).collect::<Vec<_>>();
        if !steps.iter().any(|s|!s.anchors.is_empty()) && !roots.iter().any(|&v|v) {return None;}
        Some(Self{steps,operators,continues,definitions:cell.template.defs.iter().map(|(&slot,&op)|(slot,op)).collect(),batch_rule,no_unions,isolated,lineage,roots,units})
    }
    pub(crate) fn storage_bytes(&self)->usize {
        std::mem::size_of::<Self>() + 2*std::mem::size_of::<usize>()
            + self.steps.capacity()*std::mem::size_of::<Step>() + self.steps.iter().map(|s|
            s.keys.capacity()*std::mem::size_of::<Arg>() + s.anchors.capacity()*std::mem::size_of::<(usize,usize)>()).sum::<usize>()
            + self.operators.capacity()*std::mem::size_of::<Vec<usize>>()
            + self.operators.iter().map(|v|v.capacity()*std::mem::size_of::<usize>()).sum::<usize>()
            + self.continues.capacity()*std::mem::size_of::<bool>()
            + self.definitions.capacity()*std::mem::size_of::<(usize,usize)>()
            + self.isolated.capacity()*std::mem::size_of::<bool>()
            + self.roots.capacity()*std::mem::size_of::<bool>()
            + self.lineage.capacity()*std::mem::size_of::<Vec<usize>>()
            + self.lineage.iter().map(|s|s.capacity()*std::mem::size_of::<usize>()).sum::<usize>()
            + self.units.as_ref().map_or(0,units::Tail::storage_bytes)
    }
    fn start(&self,position:usize)->Option<usize> {
        let i=self.steps.binary_search_by_key(&position,|s|s.operation).ok()?;
        (!self.steps[i].anchors.is_empty()).then_some(i)
    }
}

#[derive(Clone, Copy)]
pub(crate) struct Window { first:usize, births:u64, unions:u64 }
impl Window {
    /// The scheduler only drained earlier fresh-cone tails and total, non-birthing
    /// ordered effects. Those earlier inputs cannot name this Cell's fresh IDs.
    pub(crate) fn after_ready_batch(&mut self,g:&Graph) {
        if self.unions==g.stats.unions {self.births=g.stats.logical_facts_created;}
    }

    pub(crate) fn seed(g:&Graph,cell:u32,next:usize)->Option<Self> {
        let previous=next.checked_sub(1)?;
        let frame=g.rhs_frame(cell)?;
        let Some(Op::Let(dst,Call::Table(table),_))=g.program.templates[frame.template].ops.get(previous) else {return None;};
        let expected=Value::Eq(((cell as u64)<<32)|(*dst as u64+1));
        if !g.program.tables[*table].constructor || !g.program.tables[*table].virtual_fact
            || frame.facts.get(&(previous as u32))?.decoded.as_ref()?.1.last()!=Some(&expected)
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
    pub execution_groups:u64,
    pub root_bucket_probes:u64, pub root_bucket_fallbacks:u64, pub root_jobs:u64,
    pub root_births:u64, pub root_reuses:u64, pub root_pending:u64, pub root_boundary_probes:u64,
    pub root_isolated:u64, pub root_hash_bytes:u64,
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
    pub unit_candidates:u64, pub unit_worker_rows:u64, pub unit_inserts:u64, pub unit_invalidated:u64, pub unit_bytes:u64,
    pub prefix_reads:u64, pub prefix_handles:u64, pub prefix_unavailable:u64,
    pub slot_seals:u64, pub slot_leases:u64, pub slot_reattachments:u64,
    pub root_snapshots:u64, pub root_writes:u64, pub root_growths:u64, pub root_merges:u64,
    pub plan_handles:u64, pub prefix_growths:u64, pub prefix_bytes:u64,
    pub sealed_bytes:u64, pub captured_reads:u64, pub captured_writes:u64,
    pub shared_slots:u64, pub shared_bytes:u64, pub shared_growths:u64,
    pub result_reads:u64, pub result_hits:u64, pub evaluations:u64, pub duplicate_evaluations:u64,
    pub bloom_checks:u64, pub bloom_skips:u64, pub bloom_writes:u64,
    pub result_handles:u64, pub frame_handles:u64, pub dependency_proofs:u64, pub key_screens:u64, pub directory_checks:u64,
}
impl Counts {
    pub(crate) fn add(&mut self,b:Self) {
        macro_rules! add {($($f:ident),*)=>{$(self.$f+=b.$f;)*};}
        add!(execution_groups,root_bucket_probes,root_bucket_fallbacks,root_jobs,root_births,root_reuses,root_pending,root_boundary_probes,root_isolated,root_hash_bytes,
            plan_checks,resume_checks,window_checks,attempts,invalidated,anchor_checks,source_operand_reads,operand_reads,missing_operands,candidate_ranges,
            candidate_probes,field_checks,local_reuses,local_births,hashes,row_fields,identity_checks,
            pending_growths,pending_bytes,value_writes,slot_growths,slot_bytes,committed_rows,
            worker_batches,worker_operations,worker_wait_ns,prefix_reads,prefix_handles,prefix_unavailable,
            unit_candidates,unit_worker_rows,unit_inserts,unit_invalidated,unit_bytes,
            slot_seals,slot_leases,slot_reattachments,root_snapshots,root_writes,root_growths,root_merges,
            plan_handles,prefix_growths,prefix_bytes,sealed_bytes,captured_reads,captured_writes,
            shared_slots,shared_bytes,shared_growths,result_reads,result_hits,evaluations,duplicate_evaluations,
            bloom_checks,bloom_skips,bloom_writes,result_handles,frame_handles,dependency_proofs,key_screens,directory_checks);
    }
}
struct Born { operation:usize, table:usize, fields:RowFields, hash:u64 }
pub(crate) fn record_bytes()->usize {std::mem::size_of::<Born>()}
type Rows=smallvec::SmallVec<[Born;4]>;
pub(crate) fn pending_bytes()->usize {std::mem::size_of::<Rows>()}
// Only committed logical work belongs to the Cell result. Diagnostic work is
// accumulated by the worker loop, including private results later discarded.
struct Piece { end:usize, rows:Rows, units:Vec<units::Row>, aliases:u64, births:u64, reuses:u64 }
struct Local {
    values:crate::slots::FrameSlots,
    facts:smallvec::SmallVec<[(u32,RowFields);4]>,
    completed_prefix:usize,
}

// Both transports execute the same typed plan. An uncovered synchronous
// piece borrows its existing Cell; only a queued job needs a sealed prefix.
trait Frame {
    fn values(&self)->&crate::slots::FrameSlots;
    fn values_mut(&mut self)->&mut crate::slots::FrameSlots;
    fn fields(&self,operation:usize)->Option<&[Value]>;
    fn position(&self)->usize;
}
impl Frame for Local {
    fn values(&self)->&crate::slots::FrameSlots {&self.values}
    fn values_mut(&mut self)->&mut crate::slots::FrameSlots {&mut self.values}
    fn fields(&self,operation:usize)->Option<&[Value]> {
        let i=self.facts.binary_search_by_key(&(operation as u32),|r|r.0).ok()?;
        Some(self.facts[i].1.as_ref())
    }
    fn position(&self)->usize {self.completed_prefix}
}
impl Frame for Cell {
    fn values(&self)->&crate::slots::FrameSlots {&self.values}
    fn values_mut(&mut self)->&mut crate::slots::FrameSlots {&mut self.values}
    fn fields(&self,operation:usize)->Option<&[Value]> {
        Some(self.facts.get(&(operation as u32))?.decoded.as_ref()?.1.as_ref())
    }
    fn position(&self)->usize {self.completed_prefix}
}

fn fields<'a>(frame:&'a impl Frame,rows:&'a [Born],operation:usize)->Option<&'a [Value]> {
    if let Ok(i)=rows.binary_search_by_key(&operation,|r|r.operation) {return Some(&rows[i].fields);}
    frame.fields(operation)
}
fn anchor(step:&Step,frame:&impl Frame,rows:&[Born],first:usize,cell:u32,parents:Read<'_>,counts:&mut Counts)->Option<usize> {
    for &(op,slot) in &step.anchors {
        counts.anchor_checks+=1;
        let expected=Value::Eq(((cell as u64)<<32)|(slot as u64+1));
        if op>=first && fields(frame,rows,op).and_then(|v|v.last())==Some(&expected)
            && parents.canon(&expected)==expected {return Some(op);}
    }
    None
}
fn operand(frame:&impl Frame,definitions:&[(usize,usize)],rows:&[Born],first:usize,position:usize,
    arg:&Arg,parents:Read<'_>)->Option<Value> {
    match arg {
        Arg::Literal(v)=>Some(parents.canon(v)),
        Arg::Slot(s)=> {
            if let Some(v)=frame.values().get(s) {return Some(parents.canon(v));}
            let op=definitions.get(definitions.binary_search_by_key(s,|&(slot,_)|slot).ok()?)?.1;
            if op<first || op>=position {return None;}
            Some(parents.canon(fields(frame,rows,op)?.last()?))
        }
    }
}
impl Plan {
    fn prepare(&self,from:usize,limit:usize,cell:u32,frame:&mut impl Frame,
        parents:Read<'_>,first:usize,first_anchor:usize,first_key:smallvec::SmallVec<[Value;4]>,
        receipts:&mut EffectWriter<'_>,counts:&mut Counts)->Piece {
        let mut out=Piece {end:frame.position(),rows:Rows::new(),units:Vec::new(),aliases:0,births:0,reuses:0};
        let capacity=frame.values().capacity_bytes();
        let mut first_key=Some(first_key);
        for (index,step) in self.steps[from..limit].iter().enumerate() {
            let selected=if index==0 {Some(first_anchor)} else {
                anchor(step,frame,&out.rows,first,cell,parents,counts)
            };
            let Some(anchor)=selected else {break;};
            let key=if let Some(key)=first_key.take() {key} else {
            let mut key=smallvec::SmallVec::<[Value;4]>::new();
            for arg in &step.keys {
                counts.operand_reads+=1;
                let Some(value)=operand(frame,&self.definitions,&out.rows,first,step.operation,arg,parents)
                    else {counts.missing_operands+=1;break;};
                key.push(value);
            }
            if key.len()!=step.keys.len() {break;}
            key
            };
            counts.candidate_ranges+=1;
            let candidates=&self.operators[step.candidates][..step.prior];
            let candidates=&candidates[candidates.partition_point(|&op|op<=anchor)..];
            let mut reused=None;
            for &prior in candidates {
                counts.candidate_probes+=1;
                let Some(old)=fields(frame,&out.rows,prior) else {continue;};
                if old.len()!=key.len()+1 {continue;}
                let equal=old[..key.len()].iter().zip(&key).all(|(a,b)| {
                    counts.field_checks+=1;a==b
                });
                if equal {reused=Some((prior,old.last().unwrap().clone()));break;}
            }
            let witness=if let Some((prior,value))=reused {
                frame.values_mut().insert(step.destination,value);
                counts.value_writes+=1;out.reuses+=1;
                FactRef{cell,op:prior as u32}
            } else {
                let value=Value::Eq(((cell as u64)<<32)|(step.destination as u64+1));
                counts.identity_checks+=1;
                if parents.canon(&value)!=value {break;}
                let hash=hashkey(step.table,&key);
                let fields=Graph::shared_fields(&key,&value);
                counts.hashes+=1;counts.row_fields+=fields.len() as u64;
                let before=if out.rows.spilled() {out.rows.capacity()} else {0};
                out.rows.push(Born{operation:step.operation,table:step.table,fields,hash});
                let after=if out.rows.spilled() {out.rows.capacity()} else {0};
                counts.pending_growths+=u64::from(before!=after);
                counts.pending_bytes+=((after-before)*std::mem::size_of::<Born>()) as u64;
                out.births+=1;
                FactRef{cell,op:step.operation as u32}
            };
            receipts.record(step.operation,Dependency::Fact(witness));
            out.end=step.operation+1;
            // The first offered operation has no unexecuted gap before it.
            if step.operation!=self.steps[from].operation {out.aliases+=step.skipped as u64;}
        }
        let growth=frame.values().capacity_bytes().saturating_sub(capacity);
        counts.slot_growths+=u64::from(growth!=0);counts.slot_bytes+=growth as u64;
        out
    }
}

pub(crate) struct Job {
    cell:u32, plan:std::sync::Arc<Plan>, frame:Local,
    from:usize,limit:usize,first:usize,anchor:usize,
    key:smallvec::SmallVec<[Value;4]>, isolated:bool, fresh_root:Option<usize>,
    unit_epoch:Option<u64>,
    root:Option<u64>,
}
pub(crate) struct Done { cell:u32, frame:Local, piece:Piece, pub worker:Option<usize> }
impl Done {
    pub(crate) fn cell(&self)->u32 {self.cell}
    pub(crate) fn complete_at(&self, end: usize)->bool {self.piece.end == end}
}
impl Job {
    pub(crate) fn starts_root(&self)->bool {self.root.is_some()}
    pub(crate) fn root_hash(&self)->Option<u64> {self.root}
    pub(crate) fn dependent(&self)->bool {!self.isolated}
    /// Only a complete, union-free final region may overlap admission of the
    /// next wave. A transfer stop or an ordered suffix retains the old fence.
    pub(crate) fn terminal_at(&self,end:usize)->bool {
        if !self.plan.no_unions {return false;}
        let stop=self.plan.steps[self.limit-1].operation+1;
        stop==end || self.unit_epoch.is_some() && self.plan.units.as_ref()
            .is_some_and(|tail|tail.starts_at(stop) && tail.ends_at(end))
    }
    pub(crate) fn unstarted(self)->Done {
        Done{cell:self.cell,piece:Piece{end:self.frame.completed_prefix,rows:Rows::new(),units:Vec::new(),aliases:0,births:0,reuses:0},
            frame:self.frame,worker:None}
    }
    pub(crate) fn operations(&self)->usize {self.limit-self.from}
    pub(crate) fn work_units(&self)->usize {self.operations()+self.unit_epoch.map_or(0,|_|self.plan.units.as_ref().map_or(0,|u|u.sites.len()))}
    pub(crate) fn run(mut self,parents:Read<'_>,receipts:&mut EffectWriter<'_>,counts:&mut Counts)->Done {
        let mut piece=self.plan.prepare(self.from,self.limit,self.cell,&mut self.frame,parents,
            self.first,self.anchor,self.key,receipts,counts);
        counts.root_births+=u64::from(self.root.is_some() && piece.end>self.frame.completed_prefix);
        if self.isolated {
            assert_eq!(piece.end,self.plan.steps[self.limit-1].operation+1,
                "compiled isolated Cell tail must reach its proven boundary");
        }
        if let Some(epoch)=self.unit_epoch {
            self.plan.prepare_units(self.cell,epoch,&self.frame,self.first,parents,&mut piece,counts);
        }
        Done{cell:self.cell,frame:self.frame,piece,worker:rayon::current_thread_index()}
    }
}
impl Graph {
    pub(crate) fn take_local_job(&mut self,rule:usize,cell:u32,window:&mut Option<Window>,
        stop:usize,queued:bool)->Result<(Counts,Option<Job>)> {
        let mut counts=Counts {resume_checks:1,..Counts::default()};
        // These backends can have additional birth-time effects. Their source
        // handler remains authoritative until those effects join the proof.
        if self.stable_ports.is_some() || self.union_digest.is_some() || self.ownership.is_some()
            || self.local_unions.is_some() || cfg!(feature="keeper-proof") {return Ok((counts,None));}
        let Some(cert)=*window else {return Ok((counts,None));};
        let position=self.rhs_frame(cell).unwrap().completed_prefix;
        let Some(plan)=self.program.executions[rule].births.as_ref() else {return Ok((counts,None));};
        let Some(from)=plan.start(position).filter(|_|position<stop) else {return Ok((counts,None));};
        counts.attempts+=1;
        if cert.births!=self.stats.logical_facts_created || cert.unions!=self.stats.unions {
            counts.invalidated+=1;*window=None;return Ok((counts,None));
        }
        let region=plan.steps[from].region;
        let limit=from+plan.steps[from..].iter().take_while(|s|s.region==region && s.operation<stop).count();
        if queued && (!plan.batch_rule || limit!=plan.steps.len()) {return Ok((counts,None));}
        let plan=plan.clone();counts.plan_handles+=1;
        let unit_epoch=(queued && limit==plan.steps.len() && plan.units.as_ref().is_some_and(|u|
            u.sites.iter().all(|s|!self.units.owned[s.table] || self.pending_unions.is_empty())))
            .then_some(self.epoch);
        // Capture only missing retained-parent operands, once, into this same
        // execution frame. Internal results remain implicit local row outputs.
        if queued {
            for arg in plan.steps[from..limit].iter().flat_map(|s|&s.keys).chain(
                plan.units.iter().filter(|_|unit_epoch.is_some()).flat_map(|u|u.sites.iter().flat_map(|s|&s.keys))) {
                let Arg::Slot(slot)=arg else {continue;};
                if !self.rhs_frame(cell).unwrap().values.contains_key(slot)
                    && plan.definitions.binary_search_by_key(slot,|&(s,_)|s).ok()
                        .is_none_or(|i|plan.definitions[i].1<cert.first) {
                    let value=self.slot(cell,*slot)?;
                    counts.captured_reads+=1;counts.captured_writes+=1;
                    let values=&mut self.rhs_frame_mut(cell).unwrap().values;
                    let before=values.capacity_bytes();values.insert(*slot,value);
                    let growth=values.capacity_bytes()-before;
                    counts.slot_growths+=u64::from(growth!=0);counts.slot_bytes+=growth as u64;
                }
            }
        }
        let mut prefix=smallvec::SmallVec::new();
        for (&op,fact) in self.rhs_frame(cell).unwrap().facts.iter().filter(|(op,_)|**op as usize>=cert.first) {
            counts.prefix_reads+=1;
            let Some((_,fields))=&fact.decoded else {counts.prefix_unavailable+=1;return Ok((counts,None));};
            let before=if prefix.spilled() {prefix.capacity()} else {0};
            prefix.push((op,fields.clone()));counts.prefix_handles+=1;
            let after=if prefix.spilled() {prefix.capacity()} else {0};
            counts.prefix_growths+=u64::from(after!=before);
            counts.prefix_bytes+=((after-before)*std::mem::size_of::<(u32,RowFields)>()) as u64;
        }
        let mut frame=Local{values:Default::default(),facts:prefix,completed_prefix:position};
        let Some(first_anchor)=anchor(&plan.steps[from],&frame,&[],cert.first,
            cell,self.parents.reader(),&mut counts) else {return Ok((counts,None));};
        let root=plan.steps.binary_search_by_key(&first_anchor,|s|s.operation).unwrap();
        let isolated=queued && plan.isolated[from] && from>0 && first_anchor==plan.steps[from-1].operation;
        if queued && !isolated && !plan.lineage[from].contains(&plan.steps[root].destination) {return Ok((counts,None));}
        // This first boundary may use retained parent projections. Acquire its
        // ordinary operands once, then move the actual key into the worker.
        // An unproven window never dispatches an empty worker job.
        let first_key=self.inline_arguments(cell,&plan.steps[from].keys)?;
        counts.source_operand_reads+=first_key.len() as u64;
        let (values,sealed)=self.rhs_frame_mut(cell).unwrap().values.lease();
        counts.slot_seals+=u64::from(sealed);counts.slot_leases+=1;frame.values=values;
        counts.sealed_bytes+=u64::from(sealed)*crate::slots::FrameSlots::seal_bytes() as u64;
        Ok((counts,Some(Job{cell,plan,frame,from,limit,first:cert.first,anchor:first_anchor,key:first_key,isolated,fresh_root:Some(root),unit_epoch,root:None})))
    }
    pub(crate) fn commit_local_job(&mut self,done:Done,receipts:&mut EffectWriter<'_>)->Result<Counts> {
        self.commit_registered_local_job(done,receipts,None)
    }
    pub(crate) fn commit_registered_local_job(&mut self,done:Done,receipts:&mut EffectWriter<'_>,
        publication:Option<constructor_registration::Publication>)->Result<Counts> {
        let Done{cell,frame,mut piece,..}=done;
        self.rhs_frame_mut(cell).unwrap().values.reattach(frame.values)
            .map_err(|_|"Cell continuation lost its public prefix".to_string())?;
        let units=std::mem::take(&mut piece.units);
        let mut counts=self.register_local_piece(cell,piece,publication)?;
        counts.slot_reattachments+=1;
        for unit in units {
            let operation=unit.function.origin.unwrap().op as usize;
            let (index,inserted)=self.commit_unit_row(unit)?;
            receipts.record(operation,Dependency::Function(index));
            counts.unit_inserts+=u64::from(inserted);
            counts.unit_invalidated+=u64::from(!inserted);
        }
        Ok(counts)
    }
    fn register_local_piece(&mut self,cell:u32,piece:Piece,
        publication:Option<constructor_registration::Publication>)->Result<Counts> {
        let mut counts=Counts{local_births:piece.births,local_reuses:piece.reuses,..Counts::default()};
        if let Some(publication)=publication {
            let rows=self.publish_registered_births(publication);
            debug_assert!(piece.rows.is_empty() || piece.rows.len()==rows);
            counts.committed_rows+=rows as u64;
        } else { for row in piece.rows {
                self.activate_fields(FactRef{cell,op:row.operation as u32},row.table,row.fields,row.hash,false)?;
                counts.committed_rows+=1;
        }}
        self.stats.constructor_requests+=piece.births+piece.reuses;
        self.stats.constructor_reused+=piece.reuses;
        self.known_stats.static_eliminated+=piece.aliases;
        self.known_stats.avoided_lookups+=piece.aliases;
        self.rhs_frame_mut(cell).unwrap().completed_prefix=piece.end;
        Ok(counts)
    }
    /// A source-attached piece has no concurrent peer work. Execute it here;
    /// only the ready queue dispatches constructor jobs to the worker pool.
    pub(crate) fn complete_local_births(&mut self,rule:usize,cell:u32,window:&mut Option<Window>,
        receipts:&mut EffectWriter<'_>,stop:usize)->Result<Counts> {
        let mut counts=Counts{resume_checks:1,..Counts::default()};
        if !self.local_jobs_supported() {return Ok(counts);}
        let Some(cert)=*window else {return Ok(counts);};
        let position=self.rhs_frame(cell).unwrap().completed_prefix;
        let Some(plan)=self.program.executions[rule].births.as_deref() else {return Ok(counts);};
        let Some(from)=plan.start(position).filter(|_|position<stop) else {return Ok(counts);};
        counts.attempts+=1;
        if cert.births!=self.stats.logical_facts_created || cert.unions!=self.stats.unions {
            counts.invalidated+=1;*window=None;return Ok(counts);
        }
        let region=plan.steps[from].region;
        let limit=from+plan.steps[from..].iter().take_while(|s|s.region==region && s.operation<stop).count();
        let Some(first_anchor)=anchor(&plan.steps[from],self.rhs_frame(cell).unwrap(),&[],
            cert.first,cell,self.parents.reader(),&mut counts) else {return Ok(counts);};
        let key=self.inline_arguments(cell,&plan.steps[from].keys)?;
        counts.source_operand_reads+=key.len() as u64;
        let frame=self.cells.get_mut(&cell).expect("fresh constructor has a public Cell");
        let parents=self.parents.reader();
        let piece=plan.prepare(from,limit,cell,frame,parents,cert.first,first_anchor,key,receipts,&mut counts);
        let piece=self.register_local_piece(cell,piece,None)?;
        if let Some(cert)=window {cert.births=self.stats.logical_facts_created;}
        counts.add(piece);Ok(counts)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cell::Effects;
    use std::{rc::Rc,sync::Arc};
    pub(super) fn graph()->Graph {
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
        p.executions[0].births=Plan::derive(&p,0).map(Arc::new);
        Graph::new(p).unwrap()
    }
    pub(super) fn start(g:&mut Graph)->(u32,Value,Option<Window>) {
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
            let counts=if let Some(pool)=pool {
                let (_,job)=g.take_local_job(0,cell,&mut window,4,false).unwrap();
                let parents=g.parents.reader();
                let mut writer=receipts.writer();
                let mut counts=Counts::default();
                let done=pool.install(||job.unwrap().run(parents,&mut writer,&mut counts));
                assert!(done.worker.is_some());
                counts.add(g.commit_local_job(done,&mut receipts.writer()).unwrap());counts
            } else {
                g.complete_local_births(0,cell,&mut window,&mut receipts.writer(),4).unwrap()
            };
            assert_eq!((counts.local_births,counts.local_reuses,counts.committed_rows),(2,1,2));
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
    fn an_earlier_pending_union_keeps_the_parent_epoch_admission_fence() {
        let mut g=graph();let (_,u,_)=start(&mut g);
        assert!(g.pipelined_births_ready());
        g.enqueue_union(u,Value::Eq(100)).unwrap();
        assert!(!g.pipelined_births_ready(),"this template alone cannot prove an earlier repair harmless");
        g.repair().unwrap();assert!(g.pipelined_births_ready());
    }
    #[test]
    fn an_external_birth_or_union_invalidates_local_exclusion_before_any_effect() {
        for union in [false,true] {
            let mut g=graph();let (cell,u,mut window)=start(&mut g);
            let foreign=g.begin_transient(0,[(0,u.clone())].into_iter().collect(),None).unwrap();
            let v=g.construct(foreign,0,0,&[Arg::Slot(0)],1).unwrap();
            if union {g.enqueue_union(u,Value::Eq(100)).unwrap();g.repair().unwrap();}
            let reads=g.key_lookup_calls.get();let facts=g.stats.logical_facts_created;
            let counts=g.complete_local_births(0,cell,&mut window,&mut Effects::default().writer(),4).unwrap();
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
    #[test]
    fn two_worker_slot_owners_leave_public_parent_projections_readable_during_graph_mutation() {
        let mut g=graph();let (a,_,_)=start(&mut g);
        let b=g.begin_transient(0,[(0,Value::Eq(200))].into_iter().collect(),None).unwrap();
        g.construct(b,0,0,&[Arg::Slot(0)],1).unwrap();
        let pointer=g.cells[&a].values.get(&0).unwrap() as *const Value;
        let (mut av,_)=g.cells.get_mut(&a).unwrap().values.lease();
        let (mut bv,_)=g.cells.get_mut(&b).unwrap().values.lease();
        let ar=g.parents.freeze();let br=ar.clone();
        let gate=std::sync::Barrier::new(3);
        let (av,bv,reads)=std::thread::scope(|scope| {
            let first=scope.spawn(|| {av.insert(3,Read{base:&ar,delta:None}.canon(&Value::Eq(200)));gate.wait();gate.wait();av});
            let second=scope.spawn(|| {bv.insert(4,Read{base:&br,delta:None}.canon(&Value::Eq(200)));gate.wait();gate.wait();bv});
            gate.wait();
            let before=g.fact_column(FactRef{cell:a,op:0},0);
            let pending=g.cells[&a].values.get(&3).is_none() && g.cells[&b].values.get(&4).is_none();
            let changed=g.enqueue_union(Value::Eq(200),Value::Eq(100)).and_then(|()|g.repair());
            let after=g.fact_column(FactRef{cell:b,op:0},0);
            gate.wait();
            (first.join().unwrap(),second.join().unwrap(),(before,pending,changed,after))
        });
        assert_eq!(reads.0.unwrap(),Value::Eq(100));assert!(reads.1);reads.2.unwrap();
        assert_eq!(reads.3.unwrap(),Value::Eq(100));
        assert_eq!(av.get(&3),Some(&Value::Eq(200)),"worker retains its original root read version");
        g.cells.get_mut(&a).unwrap().values.reattach(av).unwrap();
        g.cells.get_mut(&b).unwrap().values.reattach(bv).unwrap();
        assert_eq!(g.slot(a,3).unwrap(),Value::Eq(100));
        assert_eq!(g.cells[&a].values.get(&0).unwrap() as *const Value,pointer);
        drop(ar);drop(br);
        let work=g.parents.thaw();
        assert_eq!(work.copied_units,0);assert!(work.merged_entries>0);
    }
}

/// Pending IDs name parked instances, not per-producer consumer lists. Eq ports
/// into their unfinished tails are real scheduling dependencies.
pub(crate) fn blocked(values:&[Value],pending:&[u32])->(u64,bool) {
    let mut probes=0;
    for value in values {
        probes+=1;
        match value {
            Value::Eq(id) if pending.binary_search(&((*id>>32) as u32)).is_ok()=>return (probes,true),
            Value::Set(values)=> {let (n,found)=blocked(values,pending);probes+=n;if found {return (probes,true);}},
            _=>(),
        }
    }
    (probes,false)
}
impl Graph {
    pub(crate) fn pipelined_births_ready(&self)->bool {
        // An earlier rule may already have queued a union even when this
        // template contains none. Do not carry its old parent read epoch
        // across admission that could complete that repair.
        self.pending_unions.is_empty() && self.dirty.is_empty() && self.dirty_markers.is_empty()
    }
    pub(crate) fn local_jobs_supported(&self)->bool {
        self.stable_ports.is_none() && self.union_digest.is_none() && self.ownership.is_none()
            && self.local_unions.is_none() && !cfg!(feature="keeper-proof")
    }
}
