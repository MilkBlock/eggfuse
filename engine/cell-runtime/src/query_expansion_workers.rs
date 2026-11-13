//! Residual queries use the same physical-Cell Run queue as point continuations.
use super::*;
use crate::query::snapshot::{Read, Domain};
use smallvec::SmallVec;
#[path = "query_result_fragments.rs"]
mod fragments;

struct Plan {
    layout:Vec<(usize,Vec<usize>)>, tables:Vec<usize>, expanded:usize,
    code:usize, table:usize, active:bool, partitioned:bool, serial_position:usize,
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
    fragment_gather_rows:u64, fragment_ordered_rows:u64, fragment_pieces:u64,
    fragment_worker_rows:u64, fragment_inline_rows:u64,
    fragment_header_capacity_bytes:u64, fragment_ordered_capacity_bytes:u64,
    merge_pool_calls:u64, merge_tasks:u64, merge_inline_tasks:u64,
    merge_task_capacity_bytes:u64, merge_prepare_seconds:f64, merge_execute_seconds:f64,
    merge_worker_rows:Vec<u64>, merge_worker_tasks:Vec<u64>, merge_worker_seconds:Vec<f64>,
    partitioned_entries:u64, partitioned_pivots:u64, partitioned_admitted:u64,
    partitioned_answers:u64, partitioned_admission_probes:u64,
    partitioned_expansion_rows:u64, partitioned_point_reads:u64,
    partitioned_worker_entries:Vec<u64>, partitioned_inline_entries:u64,
    column_prepares:u64, column_prepare_reuses:u64,
    #[cfg(feature="cell-absorption")]
    absorption_capacity_bytes:u64,
}
#[derive(Default)]
pub(super) struct Output {
    pub pending:bool, direct:u64, candidates:u64, pub rows:fragments::Answers,
    pub coverage:Option<PendingCoverage>,
    merged:Option<(usize,usize)>, // (candidates before dedup, prior serial answers)
}
#[derive(Default)]
pub(super) struct PendingCoverage { pub residual:usize, pub owned:bool }
/// Each rule owns its existing answer vector and final RHS input vector. The
/// input layout is borrowed from the Cell, not copied into every candidate.
struct Merge<'a> {
    inputs:&'a [usize], serial:&'a mut Vec<Binding>,
    rows:Vec<((usize,usize),Binding)>, count:usize,
    comparisons:u64, capacity_bytes:u64, worker:Option<usize>,
}
impl Merge<'_> {
    fn run(&mut self,pooled:bool) {
        self.worker=pooled.then(rayon::current_thread_index).flatten();
        // Raw entries precede ordinary answers. Already-filtered Seeds keep
        // their original position between serial kernel results. Stable ties
        // retain expansion row order, exactly as the coordinator sorter did.
        self.rows.extend(self.serial.drain(..).enumerate().map(|(i,b)|((i,usize::MAX),b)));
        self.capacity_bytes=(self.rows.capacity()*std::mem::size_of::<((usize,usize),Binding)>()) as u64;
        self.count=self.rows.len();
        self.rows.sort_by(|(a,x),(b,y)| {self.comparisons+=1;
            x.compare_inputs(y,self.inputs).then_with(||a.cmp(b))});
        self.rows.dedup_by(|(_,x),(_,y)|x.compare_inputs(y,self.inputs).is_eq());
        self.serial.extend(self.rows.drain(..).map(|(_,b)|b));
    }
}

pub(super) struct MergeWork { pub comparisons:u64, pub bytes:u64, pub seconds:f64, pub worker:Option<usize>, pub count:usize,
    gather:fragments::Gather }
pub(super) struct PendingMerge { rows:fragments::Answers }
impl Output {
    pub fn resolve_coverage(&mut self,g:&Graph,spine:&mut crate::stage_spine::Programs,rid:usize,stats:&mut Stats) {
        if let Some(coverage)=self.coverage.take() {
            if coverage.residual==0 {
                assert!(self.rows.is_empty(),"no residual Entry implies no residual answer");
                // No residual owner was delivered. The ordinary matcher and
                // the Cell selection already own any remaining answers.
                self.pending=false;
            }
            stats.coverage_rules+=1;
            stats.coverage_complete_rules+=u64::from(coverage.residual==0);
            stats.coverage_cursor_resolutions+=spine.resolve_query_coverage(g,rid,
                coverage.residual,coverage.owned) as u64;
        }
    }
    pub fn take_merge(&mut self)->Option<PendingMerge> {
        assert!(self.coverage.is_none(),"Entry coverage precedes residual winner selection");
        self.pending.then(||PendingMerge {rows:std::mem::take(&mut self.rows)})
    }
    pub fn record_merge(&mut self,n:usize,previous:usize) {self.merged=Some((n,previous));}
}
impl PendingMerge {
    pub fn len(&self)->usize {self.rows.len()}
    pub fn run(self,serial:&mut Vec<Binding>,inputs:&[usize],pooled:bool)->(usize,usize,usize,MergeWork) {
        let clock=Instant::now();
        let previous=serial.len();
        let (rows,gather)=self.rows.gather();
        let mut job=Merge {inputs,serial,rows,count:0,comparisons:0,capacity_bytes:0,worker:None};
        job.run(pooled);
        (job.count,previous,job.serial.len(),MergeWork {comparisons:job.comparisons,bytes:job.capacity_bytes,
            seconds:clock.elapsed().as_secs_f64(),worker:job.worker,count:job.count,gather})
    }
}

#[cfg(test)]
#[test]
fn residual_winners_preserve_source_and_stable_expansion_ties() {
    let binding=|key,epoch|Binding::matched([(0,Value::Int(key))].into_iter().collect(),QueryFacts::None,epoch);
    // Three distinct tie cases: direct vs serial, serial vs later pivot, and
    // multiple expansion answers from exactly the same source Entry.
    for pooled in [false,true] {
        let mut serial=vec![binding(2,20),binding(1,10)];
        let mut job=Merge {inputs:&[0],serial:&mut serial,
            rows:vec![((0,2),binding(1,12)),((0,1),binding(1,11)),
                ((1,0),binding(2,21)),((0,3),binding(3,30)),((0,3),binding(3,31))],
            count:0,comparisons:0,capacity_bytes:0,worker:None};
        if pooled {rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap().install(||job.run(true));}
        else {job.run(false);}
        assert_eq!(job.count,7);
        assert_eq!(job.serial.iter().map(|b|b.epoch).collect::<Vec<_>>(),[11,20,30]);
        assert_eq!(job.worker.is_some(),pooled);
        assert!(job.rows.is_empty());
    }
}
#[cfg(test)]
#[test]
fn fragmented_winners_match_flat_results_with_serial_and_source_ties() {
    let binding=|key,epoch|Binding::matched([(0,Value::Int(key))].into_iter().collect(),QueryFacts::None,epoch);
    for pooled in [false,true] {
        let mut serial=vec![binding(2,20),binding(1,10)];
        let mut rows=fragments::Answers::default();
        rows.push(((0,2),binding(1,12)));
        rows.range(vec![(1,binding(1,11)),(0,binding(2,21))],smallvec::smallvec![(1,0),(2,1)]);
        rows.push(((0,3),binding(3,30)));
        rows.range(vec![(3,binding(3,31))],smallvec::smallvec![(1,0)]);
        let job=PendingMerge {rows};
        let run=||job.run(&mut serial,&[0],pooled);
        let (count,previous,winners,work)=if pooled {
            rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap().install(run)
        } else {run()};
        assert_eq!((count,previous,winners),(7,2,3));
        assert_eq!(serial.iter().map(|b|b.epoch).collect::<Vec<_>>(),[11,20,30]);
        assert_eq!(work.worker.is_some(),pooled);
        assert_eq!((work.gather.range_rows,work.gather.ordered_rows),(3,2));
    }
}
#[derive(Default)]
pub(super) struct Plans {
    pub(super) enabled:bool, rules:Vec<Vec<Option<Plan>>>, work:Work,
    active:Vec<(usize,usize)>, pub ready:Vec<usize>, pub(super) outputs:Vec<Output>,
}
impl Plans {
    pub fn report(&self)->J { json!({"enabled":self.enabled,
        "organization":"shared-cell-run/v1",
        "task_counter_bytes":std::mem::size_of::<InputWork>(),
        "executor_counter_bytes":std::mem::size_of::<Work>(),
        "result_buffer_header_bytes":std::mem::size_of::<fragments::Answers>(),
        "output_record_bytes":std::mem::size_of::<Output>(),
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
            let expanded=k.query.steps.iter().find(|s|s.expansion.is_some())?;
            if expanded.expansion.as_ref()?.bound.is_empty() || !p.physical.ranges[rid][expanded.atom].is_empty() {return None;}
            let mut layout=BTreeMap::<usize,BTreeSet<usize>>::new();
            let mut tables=BTreeSet::new();
            #[cfg(feature="cell-absorption")]
            if let Some(plan)=&k.absorption {tables.insert(plan.attribute());}
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
                rule:rid,template:p.rules[rid].template,pivot,inherits_entry:false,slots:k.query.result_slots(),reads:p.rules[rid].query.len(),expansion:true,
                #[cfg(feature="cell-query-sharing-audit")] audit_prefixes:Vec::new(),});
            Some(Plan {layout:layout.into_iter().map(|(t,c)|(t,c.into_iter().collect())).collect(),
                tables:tables.into_iter().collect(),expanded:expanded.atom,code,table,active:false,
                partitioned:false,serial_position:0})
        }).collect()).collect();
        Self {enabled:true,rules,ready:vec![0;codes.len()],outputs:(0..p.rules.len()).map(|_|Output::default()).collect(),..Default::default()}
    }
    pub fn prepare<'a>(&mut self, index:&'a crate::query::QueryIndexes,
        sieve:&'a crate::sieve::Sieve, entries:&'a crate::entry_join::Plan,
        #[cfg(feature="cell-absorption")] graph:&Graph,
        #[cfg(feature="cell-absorption")] absorption:bool)->Vec<Prepared<'a>> {
        self.active.iter().enumerate().map(|(i,&(rid,pivot))| {
            let plan=self.rules[rid][pivot].as_ref().unwrap();
            self.ready[plan.code]=i;
            Prepared {index:index.read_columns(&plan.layout,plan.table),filter:sieve.entry_filter(rid,pivot),
                steps:&entries.entries[rid][pivot],projections:&entries.projections,expanded:plan.expanded,
                #[cfg(feature="cell-absorption")]
                absorption:graph.program.kernels[rid][pivot].as_ref().unwrap().absorption.as_deref()
                    .filter(|p|absorption && !graph.has_visibility_changes(p.attribute())).copied(),
                partitioned:plan.partitioned}
        }).collect()
    }
    pub fn position(&self, rid: usize, pivot: usize, original: usize) -> usize {
        self.rules[rid][pivot].as_ref().filter(|p|p.partitioned).map_or(original,|p|p.serial_position)
    }
    pub fn record_event_merge(&mut self, work: MergeWork) {
        let stats=&mut self.work;
        stats.merge_tasks+=1;stats.merge_inline_tasks+=u64::from(work.worker.is_none());
        stats.order_comparisons+=work.comparisons;stats.merge_capacity_bytes+=work.bytes;
        stats.fragment_gather_rows+=work.gather.range_rows;
        if work.worker.is_some() {stats.fragment_worker_rows+=work.gather.range_rows;}
        else {stats.fragment_inline_rows+=work.gather.range_rows;}
        stats.fragment_ordered_rows+=work.gather.ordered_rows;
        stats.fragment_pieces+=work.gather.pieces;
        stats.fragment_header_capacity_bytes+=work.gather.header_capacity_bytes;
        stats.fragment_ordered_capacity_bytes+=work.gather.ordered_capacity_bytes;
        stats.merge_execute_seconds+=work.seconds;
        if let Some(worker)=work.worker {
            if stats.merge_worker_rows.len()<=worker {
                stats.merge_worker_rows.resize(worker+1,0);stats.merge_worker_tasks.resize(worker+1,0);stats.merge_worker_seconds.resize(worker+1,0.0);
            }
            stats.merge_worker_rows[worker]+=work.count as u64;stats.merge_worker_tasks[worker]+=1;stats.merge_worker_seconds[worker]+=work.seconds;
        }
    }
    pub fn finished(&mut self) {
        for (rid,pivot) in self.active.drain(..) {
            let plan=self.rules[rid][pivot].as_mut().unwrap();
            plan.active=false;plan.partitioned=false;plan.serial_position=0;
        }
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
    pub(crate) fn pending_coverage(&self,rid:usize)->bool {
        self.expansion.outputs.get(rid).is_some_and(|o|o.coverage.is_some())
    }
    pub(crate) fn set_coverage_base(&mut self,rid:usize,residual:usize,owned:bool) {
        let c=self.expansion.outputs[rid].coverage.as_mut().expect("pending Entry coverage");
        c.residual=residual;c.owned=owned;
    }
    /// The current Entry has no possible published Cursor, even though other
    /// pivots of this rule do. Exact filters and residual queries share a task.
    pub(crate) fn uncovered_expansion_range(&mut self,g:&Graph,index:&mut crate::query::QueryIndexes,
        rid:usize,batch:crate::entry_schedule::Batch<'_>,watermark:u64,known:&QueryFacts)->Result<()> {
        let code=self.activate_expansion(g,index,rid,batch.atom())?;
        let plan=self.expansion.rules[rid][batch.atom()].as_mut().unwrap();
        self.expansion.work.partitioned_pivots+=u64::from(!plan.partitioned);
        plan.partitioned=true;
        self.expansion.outputs[rid].coverage.get_or_insert_with(Default::default);
        self.enqueue_entry_range(code,batch,watermark,known);
        self.mark_coverage_range();
        Ok(())
    }
    /// The Entry already passed Sieve and has no published Cursor. Its rule
    /// may still have other, independently owned Spine continuations.
    pub(crate) fn uncovered_expansion_entry(&mut self,g:&Graph,index:&mut crate::query::QueryIndexes,
        rid:usize,pivot:usize,node:usize,watermark:u64,witness:Dependency,known:&QueryFacts)->Result<()> {
        // The first accepted Entry activates the compiled read layout. Later
        // entries append only an address to that same query range.
        let plan=self.expansion.rules[rid][pivot].as_ref().unwrap();
        let code=if plan.active {plan.code} else {self.activate_expansion(g,index,rid,pivot)?};
        let plan=self.expansion.rules[rid][pivot].as_mut().unwrap();
        self.expansion.work.partitioned_pivots+=u64::from(!plan.partitioned);
        plan.partitioned=true;
        self.enqueue_selected_entry(code,node,watermark,witness,known);
        Ok(())
    }
    /// Record the original matcher's insertion point once per Cell query,
    /// after its Spine prefix and all preceding serial pivots are known.
    pub(crate) fn place_uncovered_expansion(&mut self,rid:usize,pivot:usize,position:usize) {
        if let Some(plan)=self.expansion.rules.get_mut(rid).and_then(|r|r.get_mut(pivot)).and_then(Option::as_mut)
            .filter(|p|p.partitioned) {plan.serial_position=position;}
    }
    pub(crate) fn expansion_ready(&self,g:&Graph,rid:usize,pivot:usize)->bool {
        if !self.expansion.enabled {return false;}
        let Some(plan)=&self.expansion.rules[rid][pivot] else {return false;};
        g.query_reads(&plan.tables,&mut 0).is_some_and(|r|r.canonical_rows())
    }
    fn activate_expansion(&mut self,g:&Graph,index:&mut crate::query::QueryIndexes,rid:usize,pivot:usize)->Result<usize> {
        let plan=self.expansion.rules[rid][pivot].as_mut().unwrap();
        if !plan.active {
            // A Cell's read layout is fixed and this Run cannot mutate the
            // graph or retire its index columns before all queries join.
            // finished()/discard() clear active before the next Run.
            index.prepare_columns(g,&plan.layout)?;
            self.expansion.work.column_prepares+=1;
            plan.active=true;self.expansion.active.push((rid,pivot));
        } else {self.expansion.work.column_prepare_reuses+=1;}
        self.expansion.outputs[rid].pending=true;
        Ok(plan.code)
    }
    pub(crate) fn expansion_entries(&mut self,g:&Graph,index:&mut crate::query::QueryIndexes,
        rid:usize,batch:crate::entry_schedule::Batch<'_>,inverted:Option<&[Dependency]>,
        watermark:u64,known:&QueryFacts)->Result<()> {
        let clock=Instant::now();
        // A tiny range otherwise creates its own scratch/answer chunk while
        // the old queue can combine it with neighbouring Cell entries. Keep
        // that locality until this range contains a useful worker-sized block.
        if inverted.is_none() && batch.range_len() >= self.grain {
            let code = self.activate_expansion(g,index,rid,batch.atom())?;
            self.enqueue_entry_range(code, batch, watermark, known);
            self.expansion.work.direct_batches += 1;
            self.expansion.work.prepare_seconds += clock.elapsed().as_secs_f64();
            return Ok(());
        }
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
    pub(crate) fn finish_expansion_rule(&mut self,rid:usize)->Option<(usize,usize,u64,u64)> {
        let output=self.expansion.outputs.get_mut(rid)?;
        if !std::mem::take(&mut output.pending) {return None;}
        let (n,previous)=output.merged.take().expect("joined residual winner selection");
        Some((n,previous,std::mem::take(&mut output.direct),std::mem::take(&mut output.candidates)))
    }
    pub(super) fn record_expansion_chunk(&mut self,g:&mut Graph,sieve:&mut crate::sieve::Sieve,
        chunk:ChunkWork,worker:Option<usize>,seconds:f64,answer_capacity:usize) {
        #[cfg(feature="cell-absorption")]
        {self.expansion.work.absorption_capacity_bytes+=(chunk.absorption.capacity()
            *std::mem::size_of::<(usize,crate::neighbor::WorkerAbsorption)>()) as u64;}
        let ChunkWork {counts:c,work:w,filters,selection:_,
            #[cfg(feature="cell-absorption")] absorption:_,}=chunk;
        if w.input_rows==0 {return;}
        let t=&mut self.expansion.work;
        t.partitioned_entries+=w.partitioned_entries;
        t.chunks+=1;t.entries+=c.entries;t.answers+=c.answers;t.point_reads+=c.point_reads;
        t.input_rows+=w.input_rows;t.filter_probes+=w.filter_probes;t.filter_rejected+=w.filter_rejected;t.direct_entries+=w.direct_entries;
        t.admission_probes+=w.admission_probes;t.admission_rejected+=w.admission_rejected;t.admission_rows+=w.admission_rows;
        t.expansion_probes+=w.expansion_probes;t.expansion_rows+=w.expansion_rows;t.row_reads+=w.row_reads;t.index_rows_examined+=w.index_rows_examined;
        t.partitioned_admitted+=w.partitioned_admitted;t.partitioned_answers+=w.partitioned_answers;
        t.partitioned_admission_probes+=w.partitioned_admission_probes;
        t.partitioned_expansion_rows+=w.partitioned_expansion_rows;t.partitioned_point_reads+=w.partitioned_point_reads;
        t.answer_capacity_bytes+=(answer_capacity*std::mem::size_of::<(usize,Binding)>()) as u64;
        t.worker_entries.resize(self.stats.worker_entries.len(),0);t.worker_inputs.resize(self.stats.worker_entries.len(),0);
        t.worker_rows.resize(self.stats.worker_entries.len(),0);t.worker_task_seconds.resize(self.stats.worker_entries.len(),0.0);
        t.partitioned_worker_entries.resize(self.stats.worker_entries.len(),0);
        if let Some(i)=worker {
            t.worker_entries[i]+=c.entries;t.worker_inputs[i]+=w.input_rows;t.worker_rows[i]+=w.expansion_rows;t.worker_task_seconds[i]+=seconds;
            t.partitioned_worker_entries[i]+=w.partitioned_entries;
        } else {t.coordinator_entries+=c.entries;t.partitioned_inline_entries+=w.partitioned_entries;}
        for (rid,probes,rejected,direct,candidates) in filters {
            sieve.record_entry_filter(rid,probes,rejected);
            self.expansion.outputs[rid].direct+=direct;
            self.expansion.outputs[rid].candidates+=candidates;
        }
        g.record_constructor_query_work(&c.constructors);
        g.stats.register_seeds+=c.entries-w.admission_rejected;g.stats.register_answers+=c.answers;
        g.stats.register_result_writes+=c.result_writes;g.stats.register_expansion_rows+=w.expansion_rows;
        g.stats.residual_candidates+=c.point_reads+w.row_reads;g.stats.key_operations+=c.key_operations;
        g.key_lookup_calls.set(g.key_lookup_calls.get()+c.point_reads+c.execution.constructor.lookups+c.execution.units.probes);
        self.absorb(&c,worker);
    }
    pub(super) fn record_expansion_run(&mut self,seconds:f64,pooled:bool,header_capacity:usize) {
        if self.expansion.active.is_empty() {return;}
        let partitioned_ranges=self.active_partitioned_ranges();
        let t=&mut self.expansion.work;t.batches+=1;t.merged_runs+=1;t.run_pool_calls+=u64::from(pooled);
        t.mixed_runs+=u64::from(!self.owned_ranges.is_empty()
            || partitioned_ranges
            || self.cell_queries.iter().any(|q|!self.cell_codes[q.code].expansion));
        t.execute_seconds+=seconds;
        t.entry_header_capacity_bytes+=(header_capacity*std::mem::size_of::<QueryRead<'_>>()) as u64;
    }
}
pub(super) struct Prepared<'a> {
    index:Read<'a>,filter:crate::sieve::EntryFilter<'a>,steps:&'a [crate::entry_join::Step],
    projections:&'a [crate::entry_join::Projection],expanded:usize,partitioned:bool,
    #[cfg(feature="cell-absorption")]
    absorption:Option<crate::neighbor::Absorption>,
}
#[derive(Default)]
struct InputWork {
    admission_probes:u64, admission_rejected:u64, admission_rows:u64,
    expansion_probes:u64, expansion_rows:u64, row_reads:u64,
    index_rows_examined:u64,
    input_rows:u64, filter_probes:u64, filter_rejected:u64, direct_entries:u64,
    partitioned_entries:u64, partitioned_admitted:u64, partitioned_answers:u64,
    partitioned_admission_probes:u64, partitioned_expansion_rows:u64, partitioned_point_reads:u64,
}
#[derive(Default)]
pub(super) struct ChunkWork {
    selection:crate::graph::query_reads::PreparedSelection,
    pub counts:Counts,work:InputWork,
    filters:SmallVec<[(usize,u64,u64,u64,u64);4]>,
    // Metrics only: no rejected bindings, result slots or row log cross back.
    #[cfg(feature="cell-absorption")]
    pub(super) absorption:Vec<(usize,crate::neighbor::WorkerAbsorption)>,
}
impl ChunkWork {
    // Coverage uses the same admission boundary as source Free Join, before
    // query guards or absorption. Empty domains cannot hide a residual match;
    // an admitted Entry with no final answer still prevents complete coverage.
    pub(super) fn coverage(&self)->(u64,u64) {(self.counts.entries,self.work.partitioned_admitted)}
}
impl Prepared<'_> {
    pub fn evaluate(&self,q:&QueryRead<'_>,reads:&crate::graph::query_reads::QueryReads<'_>,
        key_nodes:&J,known:&RuleRun,frame:&mut Frame,chunk:&mut ChunkWork,answers:&mut Vec<(usize,Binding)>,local:&crate::cell::execution::Plan,template:&Template)->Result<()> {
        let (c,w)=(&mut chunk.counts,&mut chunk.work);
        #[cfg(feature="cell-absorption")]
        let mut absorption_work=crate::neighbor::WorkerAbsorption::default();
        let entry=Entry {values:&q.row.values,epoch:q.row.epoch,witness:q.row.witness};
        let before=(w.filter_probes,w.filter_rejected,w.direct_entries,c.point_reads+w.row_reads);
        let partition_before=(w.admission_probes,w.expansion_rows,c.point_reads,c.answers);
        let result=(|| {
            w.input_rows+=1;
            if q.filter {
                if !self.filter.allow(self.index.entry_hashes(entry.witness),&mut w.filter_probes,&mut w.filter_rejected) {return Ok(());}
            }
            // Selected Entries already passed on the host; a whole mixed
            // range just passed here. Count either delivery exactly once.
            if q.filter || self.partitioned {w.direct_entries+=1;}
            if self.partitioned {w.partitioned_entries+=1;}
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
            w.partitioned_admitted+=u64::from(self.partitioned);
            frame.witnesses.clear();frame.witnesses.push((q.code.pivot,entry.witness));
            Host {local,template,query:&q.code.query,entry:&entry,pivot:q.code.pivot,reads,index:&self.index,key_nodes,
                #[cfg(feature="cell-absorption")]
                absorption:self.absorption.as_ref().and_then(|p|p.activate_sealed(q.row,known.watermark)),
                #[cfg(feature="cell-absorption")]
                absorption_work:&mut absorption_work,
                inputs:&q.code.inputs,known:&known.facts,frame,counts:c,work:w,answers,selection:&mut chunk.selection,
                source:q.source,watermark:known.watermark}.step(0,None,entry.epoch,domain.as_ref())
        })();
        #[cfg(feature="cell-absorption")]
        if absorption_work.candidates()!=0 {
            if let Some((_,work))=chunk.absorption.iter_mut().find(|(rule,_)|*rule==q.code.rule) {work.add(absorption_work);}
            else {chunk.absorption.push((q.code.rule,absorption_work));}
        }
        if self.partitioned {
            w.partitioned_admission_probes+=w.admission_probes-partition_before.0;
            w.partitioned_expansion_rows+=w.expansion_rows-partition_before.1;
            w.partitioned_point_reads+=c.point_reads-partition_before.2;
            w.partitioned_answers+=c.answers-partition_before.3;
        }
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
    local:&'a crate::cell::execution::Plan, template:&'a Template,
    query:&'a crate::cell::Query, entry:&'a Entry<'a>, pivot:usize,
    reads:&'a crate::graph::query_reads::QueryReads<'g>, index:&'a Read<'i>, key_nodes:&'a J,
    inputs:&'a [usize], known:&'a QueryFacts, frame:&'a mut Frame,
    selection:&'a mut crate::graph::query_reads::PreparedSelection,
    counts:&'a mut Counts, work:&'a mut InputWork, answers:&'a mut Vec<(usize,Binding)>, source:usize, watermark:u64,
    #[cfg(feature="cell-absorption")]
    absorption:Option<crate::neighbor::Activated<'a>>,
    #[cfg(feature="cell-absorption")]
    absorption_work:&'a mut crate::neighbor::WorkerAbsorption,
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
                    #[cfg(feature="cell-absorption")]
                    if let Some(active)=self.absorption
                        && self.absorption_work.check(active,&row,self.reads) {continue;}
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
        let mut answer=Binding::matched(self.local.slots(self.inputs.iter().zip(&self.query.inputs).map(|(&slot,f)|
            (slot,f.operand_in(self.reads.parents,|c|&self.entry.values[c],&self.frame.values,expanded).into_owned())),&mut self.counts.execution),
            self.known.with_rows(self.frame.witnesses.iter().copied()),epoch);
        answer.compiled=true;
        self.local.prepare_with_reads(self.template,&mut answer,Some(self.reads),&mut self.counts.execution);
        if let Some(plan) = &self.local.constructor {
            plan.complete(&mut answer,Some(self.reads),&mut self.frame.constructors,
                &mut self.counts.constructors,&mut self.counts.execution,self.selection);
        }
        self.answers.push((self.source,answer));
        self.counts.answers+=1;
        Ok(())
    }
}
