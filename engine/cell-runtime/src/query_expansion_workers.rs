//! Residual queries use the same physical-Cell Run queue as point continuations.
use super::*;
use crate::query::snapshot::{Read, Domain};
use smallvec::SmallVec;

struct Plan {
    layout:Vec<(usize,Vec<usize>)>, tables:Vec<usize>, expanded:usize,
    code:usize, table:usize, active:bool,
}
#[derive(Default,Serialize)]
struct Work {
    batches:u64, entries:u64, coordinator_entries:u64, chunks:u64,
    admission_probes:u64, admission_rejected:u64, admission_rows:u64,
    expansion_probes:u64, expansion_rows:u64, row_reads:u64,
    answers:u64, point_reads:u64, prepare_seconds:f64, execute_seconds:f64,
    index_rows_examined:u64, entry_header_capacity_bytes:u64, answer_capacity_bytes:u64,
    worker_entries:Vec<u64>, worker_rows:Vec<u64>, worker_task_seconds:Vec<f64>,
    input_rows:u64, filter_probes:u64, filter_rejected:u64, direct_entries:u64,
    direct_batches:u64, worker_inputs:Vec<u64>, queued_row_owners:u64,
    merged_runs:u64, run_pool_calls:u64, mixed_runs:u64, order_comparisons:u64,
    merge_capacity_bytes:u64,
}
#[derive(Default)]
struct Output { pending:bool, direct:u64, candidates:u64, rows:Vec<((usize,usize),Binding)> }
#[derive(Default)]
pub(super) struct Plans {
    enabled:bool, rules:Vec<Vec<Option<Plan>>>, work:Work,
    active:Vec<(usize,usize)>, pub ready:Vec<usize>, outputs:Vec<Output>,
}
impl Plans {
    pub fn report(&self)->J { json!({"enabled":self.enabled,
        "organization":"shared-cell-run/v1",
        "compiled_entries":self.rules.iter().flatten().filter(|p|p.is_some()).count(),
        "plan_capacity_bytes":self.plan_bytes(),"stats":self.work}) }
    fn plan_bytes(&self)->usize {
        self.rules.capacity()*std::mem::size_of::<Vec<Option<Plan>>>()
        + self.rules.iter().map(|r|r.capacity()*std::mem::size_of::<Option<Plan>>()).sum::<usize>()
        + self.rules.iter().flatten().flatten().map(|p|p.layout.capacity()*std::mem::size_of::<(usize,Vec<usize>)>()
            + p.layout.iter().map(|(_,c)|c.capacity()*std::mem::size_of::<usize>()).sum::<usize>()
            + p.tables.capacity()*std::mem::size_of::<usize>()).sum::<usize>()
        + self.ready.capacity()*std::mem::size_of::<usize>()
        + self.outputs.capacity()*std::mem::size_of::<Output>()
    }
    fn compile(p:&Program, entry:&crate::entry_join::Plan, codes:&mut Vec<CellCode>)->Self {
        let rules=p.kernels.iter().enumerate().map(|(rid,ks)|ks.iter().enumerate().map(|(pivot,k)| {
            let k=k.as_ref()?;
            if k.routes.is_some() || k.sum_filter.is_some() {return None;}
            #[cfg(feature="cell-absorption")]
            if k.absorption.is_some() {return None;}
            let expanded=k.query.steps.iter().find(|s|s.expansion.is_some())?;
            if expanded.expansion.as_ref()?.bound.is_empty() || !p.physical.ranges[rid][expanded.atom].is_empty() {return None;}
            let mut layout=BTreeMap::<usize,BTreeSet<usize>>::new();
            let mut tables=BTreeSet::new();
            for s in &k.query.steps {
                if let Call::Table(t)=s.call {tables.insert(t);}
                if let (Call::Table(t),Some(e))=(&s.call,&s.expansion) {
                    layout.entry(*t).or_default().extend(e.bound.iter().map(|(c,_)|*c));
                }
            }
            for step in &entry.entries[rid][pivot] {
                let shape=&entry.projections[step.projection];
                if shape.columns.is_empty() {return None;}
                tables.insert(shape.table);
                layout.entry(shape.table).or_default().extend(shape.columns.iter().map(|(c,_)|*c));
            }
            let Call::Table(table)=p.rules[rid].query[pivot].call else {return None;};
            let code=codes.len();
            codes.push(CellCode {first_read:None,query:k.query.clone(),inputs:p.rules[rid].inputs.clone(),
                rule:rid,pivot,slots:k.query.result_slots(),reads:p.rules[rid].query.len(),expansion:true,
                #[cfg(feature="cell-query-sharing-audit")] audit_prefixes:Vec::new(),});
            Some(Plan {layout:layout.into_iter().map(|(t,c)|(t,c.into_iter().collect())).collect(),
                tables:tables.into_iter().collect(),expanded:expanded.atom,code,table,active:false})
        }).collect()).collect();
        Self {enabled:true,rules,ready:vec![0;codes.len()],outputs:(0..p.rules.len()).map(|_|Output::default()).collect(),..Default::default()}
    }
    pub fn prepare<'a>(&mut self, index:&'a crate::query::QueryIndexes,
        sieve:&'a crate::sieve::Sieve, entries:&'a crate::entry_join::Plan)->Vec<Prepared<'a>> {
        self.active.iter().enumerate().map(|(i,&(rid,pivot))| {
            let plan=self.rules[rid][pivot].as_ref().unwrap();
            self.ready[plan.code]=i;
            Prepared {index:index.read_columns(&plan.layout,plan.table),filter:sieve.entry_filter(rid,pivot),
                steps:&entries.entries[rid][pivot],projections:&entries.projections,expanded:plan.expanded}
        }).collect()
    }
    pub fn finished(&mut self) {
        for (rid,pivot) in self.active.drain(..) {self.rules[rid][pivot].as_mut().unwrap().active=false;}
    }
    pub fn discard(&mut self) {
        for &(rid,_) in &self.active {self.outputs[rid]=Output::default();}
        self.finished();
    }
}
impl Executor {
    pub fn use_parallel_residuals(&mut self)->Result<()> {
        if !self.steps.is_empty() {return Err("configure residual workers before execution".into());}
        let workers=self.query_workers.as_mut().ok_or("residual workers require query workers")?;
        if workers.expansion.enabled {return Err("residual workers already configured".into());}
        if cfg!(feature="structural-depth") || cfg!(feature="family-survey") || cfg!(feature="family-overlap") {
            return Err("residual workers do not support per-read structural/family audits".into());
        }
        let previous=workers.cell_codes.capacity();
        workers.expansion=Plans::compile(&self.graph.program,self.free_join.entry_plan(),&mut workers.cell_codes);
        workers.stats.compiled_cell_code_bytes+=((workers.cell_codes.capacity()-previous)*std::mem::size_of::<CellCode>()) as u64;
        Ok(())
    }
    pub(crate) fn expansion_worker_batch(&mut self,rid:usize,
        kernel:&crate::row_kernel::Kernel,seeds:&[crate::entry_schedule::Seed],known:&QueryFacts,serial_position:usize)->Result<bool> {
        if self.completion.is_some() || self.stage_spine.active_for_rule(rid) || !self.free_join.planned || !self.free_join.enabled {return Ok(false);}
        let Some(workers)=&mut self.query_workers else {return Ok(false);};
        if !workers.expansion_ready(&self.graph,rid,kernel.pivot) {return Ok(false);}
        let seeds=crate::entry_schedule::Seed::for_atom(seeds,kernel.pivot,&mut workers.stats.seed_range_comparisons);
        if seeds.is_empty() {return Ok(true);}
        let code=workers.activate_expansion(&self.graph,&mut self.query_indexes,rid,kernel.pivot)?;
        for s in seeds {workers.enqueue_query(&self.graph,code,serial_position,self.watermarks[rid],s.packet.row.clone(),None,known,false);}
        workers.expansion.work.queued_row_owners+=seeds.len() as u64;
        Ok(true)
    }
}
impl Workers {
    pub(crate) fn expansion_ready(&self,g:&Graph,rid:usize,pivot:usize)->bool {
        if !self.expansion.enabled {return false;}
        let Some(plan)=&self.expansion.rules[rid][pivot] else {return false;};
        #[cfg(feature="cell-absorption")]
        if g.program.kernels[rid][pivot].as_ref().is_some_and(|k|k.absorption.is_some()) {return false;}
        g.query_reads(&plan.tables,&mut 0).is_some_and(|r|r.canonical_rows())
    }
    fn activate_expansion(&mut self,g:&Graph,index:&mut crate::query::QueryIndexes,rid:usize,pivot:usize)->Result<usize> {
        let plan=self.expansion.rules[rid][pivot].as_mut().unwrap();
        index.prepare_columns(g,&plan.layout)?;
        if !plan.active {plan.active=true;self.expansion.active.push((rid,pivot));}
        self.expansion.outputs[rid].pending=true;
        Ok(plan.code)
    }
    pub(crate) fn expansion_entries(&mut self,g:&Graph,index:&mut crate::query::QueryIndexes,
        rid:usize,batch:crate::entry_schedule::Batch<'_>,inverted:Option<&[Dependency]>,
        watermark:u64,known:&QueryFacts)->Result<()> {
        let clock=Instant::now();
        let before=self.cell_queries.len();
        // Keep the old preparation order: another rule may consult the same
        // columns while choosing its reverse candidate traversal in this Run.
        let mut code=None;
        let mut enqueue=|w|->Result<()> {
            let code=match code {Some(c)=>c,None=>{let c=self.activate_expansion(g,index,rid,batch.atom())?;code=Some(c);c}};
            let row=batch.shared_row(w).expect("current delta Entry");
            self.enqueue_query(g,code,0,watermark,row,None,known,true);
            Ok(())
        };
        if let Some(ws)=inverted {for &w in ws {enqueue(w)?;}}
        else {for &(_,w) in batch.delta() {enqueue(w)?;}}
        let n=self.cell_queries.len()-before;
        self.expansion.work.direct_batches+=u64::from(n!=0);
        self.expansion.work.queued_row_owners+=n as u64;
        self.expansion.work.prepare_seconds+=clock.elapsed().as_secs_f64();
        Ok(())
    }
    pub(crate) fn pending_expansion(&self,rid:usize)->bool {
        self.expansion.outputs.get(rid).is_some_and(|o|o.pending)
    }
    pub(crate) fn finish_expansion_rule(&mut self,rid:usize,serial:&mut Vec<Binding>,inputs:&[usize])->Option<(usize,u64,u64)> {
        let output=self.expansion.outputs.get_mut(rid)?;
        if !std::mem::take(&mut output.pending) {return None;}
        let mut rows=std::mem::take(&mut output.rows);
        // Raw direct entries precede ordinary answers. Already-filtered Seeds
        // occupy their original position between serial kernel results. Retain
        // both orders in this one stable key/source sort, including expansion
        // row order; no preliminary source sort or copied bindings are needed.
        rows.extend(serial.drain(..).enumerate().map(|(i,b)|((i,usize::MAX),b)));
        self.expansion.work.merge_capacity_bytes+=(rows.capacity()*std::mem::size_of::<((usize,usize),Binding)>()) as u64;
        let n=rows.len();
        rows.sort_by(|(a,x),(b,y)| {self.expansion.work.order_comparisons+=1;
            x.compare_inputs(y,inputs).then_with(||a.cmp(b))});
        rows.dedup_by(|(_,x),(_,y)|x.compare_inputs(y,inputs).is_eq());
        serial.extend(rows.into_iter().map(|(_,b)|b));
        Some((n,std::mem::take(&mut output.direct),std::mem::take(&mut output.candidates)))
    }
    pub(super) fn record_expansion_answer(&mut self,rid:usize,position:usize,source:usize,answer:Binding) {
        self.expansion.outputs[rid].rows.push(((position,source),answer));
    }
    pub(super) fn record_expansion_chunk(&mut self,g:&mut Graph,sieve:&mut crate::sieve::Sieve,
        chunk:ChunkWork,worker:Option<usize>,seconds:f64,answer_capacity:usize) {
        let ChunkWork {counts:c,work:w,filters}=chunk;
        if w.input_rows==0 {return;}
        let t=&mut self.expansion.work;
        t.chunks+=1;t.entries+=c.entries;t.answers+=c.answers;t.point_reads+=c.point_reads;
        t.input_rows+=w.input_rows;t.filter_probes+=w.filter_probes;t.filter_rejected+=w.filter_rejected;t.direct_entries+=w.direct_entries;
        t.admission_probes+=w.admission_probes;t.admission_rejected+=w.admission_rejected;t.admission_rows+=w.admission_rows;
        t.expansion_probes+=w.expansion_probes;t.expansion_rows+=w.expansion_rows;t.row_reads+=w.row_reads;t.index_rows_examined+=w.index_rows_examined;
        t.answer_capacity_bytes+=(answer_capacity*std::mem::size_of::<(usize,Binding)>()) as u64;
        t.worker_entries.resize(self.stats.worker_entries.len(),0);t.worker_inputs.resize(self.stats.worker_entries.len(),0);
        t.worker_rows.resize(self.stats.worker_entries.len(),0);t.worker_task_seconds.resize(self.stats.worker_entries.len(),0.0);
        if let Some(i)=worker {t.worker_entries[i]+=c.entries;t.worker_inputs[i]+=w.input_rows;t.worker_rows[i]+=w.expansion_rows;t.worker_task_seconds[i]+=seconds;}
        else {t.coordinator_entries+=c.entries;}
        for (rid,probes,rejected,direct,candidates) in filters {
            sieve.record_entry_filter(rid,probes,rejected);
            self.expansion.outputs[rid].direct+=direct;
            self.expansion.outputs[rid].candidates+=candidates;
        }
        g.record_constructor_query_work(&c.constructors);
        g.stats.register_seeds+=c.entries-w.admission_rejected;g.stats.register_answers+=c.answers;
        g.stats.register_result_writes+=c.result_writes;g.stats.register_expansion_rows+=w.expansion_rows;
        g.stats.residual_candidates+=c.point_reads+w.row_reads;g.stats.key_operations+=c.key_operations;
        g.key_lookup_calls.set(g.key_lookup_calls.get()+c.point_reads);
        self.absorb(&c,worker);
    }
    pub(super) fn record_expansion_run(&mut self,seconds:f64,pooled:bool,header_capacity:usize) {
        if self.expansion.active.is_empty() {return;}
        let t=&mut self.expansion.work;t.batches+=1;t.merged_runs+=1;t.run_pool_calls+=u64::from(pooled);
        t.mixed_runs+=u64::from(self.cell_queries.iter().any(|q|!self.cell_codes[q.code].expansion));
        t.execute_seconds+=seconds;
        t.entry_header_capacity_bytes+=(header_capacity*std::mem::size_of::<QueryRead<'_>>()) as u64;
    }
}
pub(super) struct Prepared<'a> {
    index:Read<'a>,filter:crate::sieve::EntryFilter<'a>,steps:&'a [crate::entry_join::Step],
    projections:&'a [crate::entry_join::Projection],expanded:usize,
}
#[derive(Default)]
pub(super) struct ChunkWork {
    pub counts:Counts,work:Work,
    filters:SmallVec<[(usize,u64,u64,u64,u64);4]>,
}
impl Prepared<'_> {
    pub fn evaluate(&self,q:&QueryRead<'_>,reads:&crate::graph::query_reads::QueryReads<'_>,
        key_nodes:&J,known:&RuleRun,frame:&mut Frame,chunk:&mut ChunkWork,answers:&mut Vec<(usize,Binding)>)->Result<()> {
        let (c,w)=(&mut chunk.counts,&mut chunk.work);
        let entry=Entry {values:&q.row.values,epoch:q.row.epoch,witness:q.row.witness};
        let before=(w.filter_probes,w.filter_rejected,w.direct_entries,c.point_reads+w.row_reads);
        let result=(|| {
            w.input_rows+=1;
            if q.filter {
                if !self.filter.allow(self.index.entry_hashes(entry.witness),&mut w.filter_probes,&mut w.filter_rejected) {return Ok(());}
                w.direct_entries+=1;
            }
            c.entries+=1;
            let owner=(entry.epoch,entry.witness);
            let mut domain=None;
            for step in self.steps {
                w.admission_probes+=1;
                let shape=&self.projections[step.projection];
                let selectors=shape.columns.iter().map(|(col,src)|(*col,self.index.fingerprint(&match src {
                    crate::entry_join::Source::Cover(col)=>entry.values[*col].clone(),
                    crate::entry_join::Source::Literal(v)=>value::canon(v,reads.parents),
                }))).collect();
                let selected=self.index.domain(shape.table,selectors);
                let (first,second)={let mut it=selected.iter();(it.next(),it.next())};
                w.index_rows_examined+=selected.take_examined();
                w.admission_rows+=u64::from(first.is_some())+u64::from(second.is_some());
                if first.is_none() || (second.is_none() && reads.visible_epoch(first.unwrap()).is_some_and(|e|
                    (e,first.unwrap())>owner || ((e,first.unwrap())==owner && step.atom<q.code.pivot))) {
                    w.admission_rejected+=1;return Ok(());
                }
                if step.atom==self.expanded {domain=Some(selected);}
            }
            frame.witnesses.clear();frame.witnesses.push((q.code.pivot,entry.witness));
            Host {query:&q.code.query,entry:&entry,pivot:q.code.pivot,reads,index:&self.index,key_nodes,
                inputs:&q.code.inputs,known:&known.facts,frame,counts:c,work:w,answers,
                source:q.source,watermark:known.watermark}.step(0,None,entry.epoch,domain.as_ref())
        })();
        let stats=match chunk.filters.iter().position(|s|s.0==q.code.rule) {
            Some(i)=>&mut chunk.filters[i],
            None=>{chunk.filters.push((q.code.rule,0,0,0,0));chunk.filters.last_mut().unwrap()}
        };
        stats.1+=w.filter_probes-before.0;stats.2+=w.filter_rejected-before.1;
        stats.3+=w.direct_entries-before.2;stats.4+=c.point_reads+w.row_reads-before.3;
        result
    }
}
struct Host<'a,'g,'i> {
    query:&'a crate::cell::Query, entry:&'a Entry<'a>, pivot:usize,
    reads:&'a crate::graph::query_reads::QueryReads<'g>, index:&'a Read<'i>, key_nodes:&'a J,
    inputs:&'a [usize], known:&'a QueryFacts, frame:&'a mut Frame,
    counts:&'a mut Counts, work:&'a mut Work, answers:&'a mut Vec<(usize,Binding)>, source:usize, watermark:u64,
}
impl Host<'_, '_, '_> {
    fn step(&mut self, pc:usize, expanded:Option<(usize,&Row)>, mut epoch:u64,
        supplied:Option<&Domain<'_>>) -> Result<()> {
        let owner=(self.entry.epoch,self.entry.witness);
        for (position,ins) in self.query.steps.iter().enumerate().skip(pc) {
            self.counts.steps += 1;
            if let Some(expansion)=&ins.expansion {
                let Call::Table(table)=ins.call else {unreachable!()};
                let selected;
                let domain = if let Some(d)=supplied {d} else {
                    self.work.expansion_probes+=1;
                    let selectors=expansion.bound.iter().map(|(c,f)| (*c,self.index.fingerprint(
                        &f.operand_in(self.reads.parents,|col|&self.entry.values[col],&self.frame.values,expanded)))).collect();
                    selected=self.index.domain(table,selectors); &selected
                };
                let mark=self.frame.witnesses.len();
                for w in domain.iter() {
                    self.work.row_reads+=1;
                    let Some(row)=self.reads.row(w)? else {continue};
                    let stamp=(row.epoch,w);
                    if row.hidden || row.table!=table || stamp>owner || (stamp==owner && ins.atom<self.pivot) {continue;}
                    self.work.expansion_rows+=1;
                    if !expansion.checks.iter().all(|(c,f)| f.operand_in(self.reads.parents,
                        |col|&self.entry.values[col],&self.frame.values,Some((position,&row))).as_ref()==&row.values[*c]) {continue;}
                    self.frame.witnesses.truncate(mark);
                    self.frame.witnesses.push((ins.atom,w));
                    self.step(position+1,Some((position,&row)),epoch.max(row.epoch),None)?;
                }
                self.work.index_rows_examined += domain.take_examined();
                self.frame.witnesses.truncate(mark);
                return Ok(());
            }
            let bound=ins.bind::<SmallVec<[Value;4]>>(|f|f.operand_in(self.reads.parents,
                |c|&self.entry.values[c],&self.frame.values,expanded));
            let result=bound.evaluate(|args|match &ins.call {
                Call::Table(t)=>{
                    self.counts.point_reads+=1;
                    let Some((v,e,w))=self.reads.point(*t,&args,&mut self.frame.constructors,&mut self.counts.constructors)? else {return Ok(None)};
                    if (e,w)>owner || ((e,w)==owner && ins.atom<self.pivot) {self.counts.owner_rejections+=1;return Ok(None)}
                    epoch=epoch.max(e);self.frame.witnesses.push((ins.atom,w));Ok(Some(v))
                }
                Call::Primitive(name,sort)=>{
                    self.counts.guards+=1; self.counts.key_operations+=u64::from(name.starts_with("cell-key-"));
                    value::primitive(name,&args,sort,self.key_nodes)
                }
            })?;
            let Some(result)=result else{return Ok(())};
            if ins.check_result.is_none(){self.frame.values[position]=result;self.counts.result_writes+=1;}
        }
        if epoch < self.watermark { return Ok(()); }
        if self.answers.len() == self.answers.capacity() { self.counts.answer_buffer_allocations += 1; }
        let mut answer=Binding::matched(self.inputs.iter().zip(&self.query.inputs).map(|(&slot,f)|
            (slot,f.operand_in(self.reads.parents,|c|&self.entry.values[c],&self.frame.values,expanded).into_owned())).collect(),
            self.known.with_rows(self.frame.witnesses.iter().copied()),epoch);
        answer.compiled=true;
        self.answers.push((self.source,answer));
        self.counts.answers+=1;
        Ok(())
    }
}
