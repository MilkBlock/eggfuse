//! Execute the existing one-expansion Cell Query and its Free Join admission.
use super::*;
use crate::query::snapshot::{Read, Domain};
use smallvec::SmallVec;

struct Plan {
    layout: Vec<(usize, Vec<usize>)>,
    tables: Vec<usize>,
    expanded: usize,
}
#[derive(Default, Serialize)]
struct Work {
    batches: u64, entries: u64, coordinator_entries: u64, chunks: u64,
    admission_probes: u64, admission_rejected: u64, admission_rows: u64,
    expansion_probes: u64, expansion_rows: u64, row_reads: u64,
    answers: u64, point_reads: u64, prepare_seconds: f64, execute_seconds: f64,
    index_rows_examined:u64, entry_header_capacity_bytes:u64, answer_capacity_bytes:u64,
    worker_entries: Vec<u64>, worker_rows: Vec<u64>, worker_task_seconds:Vec<f64>,
}
#[derive(Default)]
pub(super) struct Plans {
    enabled: bool,
    rules: Vec<Vec<Option<Plan>>>,
    work: Work,
}
impl Plans {
    pub fn report(&self) -> J { json!({"enabled":self.enabled,
        "compiled_entries":self.rules.iter().flatten().filter(|p|p.is_some()).count(),"stats":self.work}) }
    fn compile(p: &Program, entry: &crate::entry_join::Plan) -> Self {
        let rules = p.kernels.iter().enumerate().map(|(rid, kernels)| kernels.iter().enumerate().map(|(pivot,k)| {
            let k = k.as_ref()?;
            if k.routes.is_some() || k.sum_filter.is_some() { return None; }
            #[cfg(feature = "cell-absorption")]
            if k.absorption.is_some() { return None; }
            let expanded = k.query.steps.iter().find(|s| s.expansion.is_some())?;
            if expanded.expansion.as_ref()?.bound.is_empty() || !p.physical.ranges[rid][expanded.atom].is_empty() { return None; }
            let mut layout = BTreeMap::<usize,BTreeSet<usize>>::new();
            let mut tables = BTreeSet::new();
            for s in &k.query.steps {
                if let Call::Table(t) = s.call { tables.insert(t); }
                if let (Call::Table(t),Some(e)) = (&s.call,&s.expansion) {
                    layout.entry(*t).or_default().extend(e.bound.iter().map(|(c,_)|*c));
                }
            }
            for step in &entry.entries[rid][pivot] {
                let shape = &entry.projections[step.projection];
                if shape.columns.is_empty() { return None; }
                tables.insert(shape.table);
                layout.entry(shape.table).or_default().extend(shape.columns.iter().map(|(c,_)|*c));
            }
            Some(Plan { layout:layout.into_iter().map(|(t,c)|(t,c.into_iter().collect())).collect(),
                tables:tables.into_iter().collect(), expanded:expanded.atom })
        }).collect()).collect();
        Self { enabled:true, rules, work:Default::default() }
    }
}
impl Workers {
    pub(crate) fn expansion_ready(&self, g: &Graph, rid: usize, pivot: usize) -> bool {
        if !self.expansion.enabled { return false; }
        let Some(plan) = &self.expansion.rules[rid][pivot] else { return false; };
        #[cfg(feature = "cell-absorption")]
        if g.program.kernels[rid][pivot].as_ref().is_some_and(|k| k.absorption.is_some()) { return false; }
        let mut checks = 0;
        g.query_reads(&plan.tables, &mut checks).is_some_and(|r| r.canonical_rows())
    }
}
impl Executor {
    pub fn use_parallel_residuals(&mut self) -> Result<()> {
        if !self.steps.is_empty() { return Err("configure residual workers before execution".into()); }
        let workers = self.query_workers.as_mut().ok_or("residual workers require query workers")?;
        if cfg!(feature="structural-depth") || cfg!(feature="family-survey") || cfg!(feature="family-overlap") {
            return Err("residual workers do not support per-read structural/family audits".into());
        }
        workers.expansion = Plans::compile(&self.graph.program, self.free_join.entry_plan());
        Ok(())
    }
    pub(crate) fn expansion_worker_batch(&mut self, rid:usize, rule:&Rule,
        kernel:&crate::row_kernel::Kernel, seeds:&[crate::entry_schedule::Seed],
        known:&QueryFacts, out:&mut Vec<Binding>) -> Result<bool> {
        if self.completion.is_some() || self.stage_spine.active_for_rule(rid) || !self.free_join.planned || !self.free_join.enabled { return Ok(false); }
        let Some(workers) = &mut self.query_workers else { return Ok(false); };
        if !workers.expansion_ready(&self.graph,rid,kernel.pivot) { return Ok(false); }
        let prepare = Instant::now();
        let plan = workers.expansion.rules[rid][kernel.pivot].as_ref().unwrap();
        let seeds = crate::entry_schedule::Seed::for_atom(seeds,kernel.pivot,&mut workers.stats.seed_range_comparisons);
        if seeds.is_empty() { return Ok(true); }
        let reads = self.graph.query_reads(&plan.tables,&mut workers.stats.admission_table_checks)
            .ok_or("residual snapshot changed after admission")?;
        let index = self.query_indexes.read_columns(&self.graph, &plan.layout)?;
        let entries:Vec<_> = seeds.iter().map(|s| Entry {values:&s.packet.row.values,
            epoch:s.packet.row.epoch,witness:s.packet.row.witness}).collect();
        let entry_plan = self.free_join.entry_plan();
        let steps = &entry_plan.entries[rid][kernel.pivot];
        let query = kernel.query.as_ref();
        let inputs = &rule.inputs;
        let query_width = rule.query.len();
        let pivot = kernel.pivot;
        let expanded = plan.expanded;
        let key_nodes = self.graph.program.key_nodes();
        let pooled = workers.pool.is_some() && entries.len() >= workers.grain;
        workers.expansion.work.entry_header_capacity_bytes += (entries.capacity()*std::mem::size_of::<Entry<'_>>()) as u64;
        workers.expansion.work.prepare_seconds += prepare.elapsed().as_secs_f64();
        let run = |chunk:&[Entry<'_>], frame:&mut Frame| -> Result<_> {
            let clock = Instant::now();
            let mut counts = Counts { entries:chunk.len() as u64,chunks:1,..Default::default() };
            let mut work = Work::default();
            let mut answers = Vec::new();
            frame.prepare(query.result_slots(),query_width,&mut counts);
            for entry in chunk {
                let owner = (entry.epoch,entry.witness);
                let mut domain = None;
                let mut accepted = true;
                // Preserve all original pre-query necessary checks and singleton
                // delta rejection, including checks preceding fallible primitives.
                for step in steps {
                    work.admission_probes += 1;
                    let shape = &entry_plan.projections[step.projection];
                    let selectors = shape.columns.iter().map(|(col,src)| (*col,index.fingerprint(&match src {
                        crate::entry_join::Source::Cover(c) => entry.values[*c].clone(),
                        crate::entry_join::Source::Literal(v) => value::canon(v,reads.parents),
                    }))).collect();
                    let selected = index.domain(shape.table,selectors);
                    let (first,second) = { let mut it=selected.iter();(it.next(),it.next()) };
                    work.index_rows_examined += selected.take_examined();
                    work.admission_rows += u64::from(first.is_some()) + u64::from(second.is_some());
                    if first.is_none() || (second.is_none() && reads.visible_epoch(first.unwrap()).is_some_and(|e|
                        (e,first.unwrap()) > owner || ((e,first.unwrap()) == owner && step.atom < pivot))) {
                        accepted = false; work.admission_rejected += 1; break;
                    }
                    if step.atom == expanded { domain = Some(selected); }
                }
                if !accepted { continue; }
                frame.witnesses.clear(); frame.witnesses.push((pivot,entry.witness));
                let mut host = Host {query,entry,pivot,reads:&reads,index:&index,key_nodes,inputs,known,
                    frame,counts:&mut counts,work:&mut work,answers:&mut answers};
                host.step(0,None,entry.epoch,domain.as_ref())?;
            }
            counts.answers = answers.len() as u64;
            counts.output_buffer_capacity = answers.capacity() as u64;
            counts.frame_capacity_bytes = frame.bytes();
            work.answer_capacity_bytes = (answers.capacity()*std::mem::size_of::<Binding>()) as u64;
            Ok((answers,counts,work,if pooled {rayon::current_thread_index()} else {None},clock.elapsed().as_secs_f64()))
        };
        let clock=Instant::now();
        let completed:Vec<_> = if pooled {
            workers.pool.as_ref().unwrap().install(|| entries.par_chunks(workers.grain)
                .map(|c|with_worker_frame(|f|run(c,f))).collect())
        } else { entries.chunks(workers.grain).map(|c|workers.inline_frame.with(|f|run(c,f))).collect() };
        drop(index);
        let total=&mut workers.expansion.work;
        total.execute_seconds += clock.elapsed().as_secs_f64();
        total.batches += 1;
        total.worker_entries.resize(workers.stats.worker_entries.len(),0);
        total.worker_rows.resize(workers.stats.worker_entries.len(),0);
        total.worker_task_seconds.resize(workers.stats.worker_entries.len(),0.0);
        workers.stats.batches += 1;
        workers.stats.batch_buffers += 2;
        workers.stats.entry_headers += entries.len() as u64;
        workers.stats.entry_buffer_bytes += (entries.capacity()*std::mem::size_of::<Entry<'_>>()) as u64;
        for result in completed {
            let (mut answers, counts, w, worker, seconds)=result?;
            let total=&mut workers.expansion.work;
            total.entries += counts.entries; total.chunks += 1; total.answers += counts.answers;
            total.point_reads += counts.point_reads;
            total.admission_probes+=w.admission_probes; total.admission_rejected+=w.admission_rejected;
            total.admission_rows+=w.admission_rows; total.expansion_probes+=w.expansion_probes;
            total.expansion_rows+=w.expansion_rows; total.row_reads+=w.row_reads;
            total.index_rows_examined+=w.index_rows_examined; total.answer_capacity_bytes+=w.answer_capacity_bytes;
            if let Some(i)=worker { total.worker_entries[i]+=counts.entries; total.worker_rows[i]+=w.expansion_rows;total.worker_task_seconds[i]+=seconds; }
            else {total.coordinator_entries+=counts.entries;}
            self.graph.record_constructor_query_work(&counts.constructors);
            workers.absorb(&counts,worker);
            self.graph.stats.register_seeds += counts.entries - w.admission_rejected;
            self.graph.stats.register_answers += counts.answers;
            self.graph.stats.register_result_writes += counts.result_writes;
            self.graph.stats.register_expansion_rows += w.expansion_rows;
            self.graph.stats.residual_candidates += counts.point_reads + w.row_reads;
            self.graph.stats.key_operations += counts.key_operations;
            self.graph.key_lookup_calls.set(self.graph.key_lookup_calls.get()+counts.point_reads);
            out.append(&mut answers);
        }
        Ok(true)
    }
}

struct Host<'a,'g> {
    query:&'a crate::cell::Query, entry:&'a Entry<'a>, pivot:usize,
    reads:&'a crate::graph::query_reads::QueryReads<'g>, index:&'a Read<'g>, key_nodes:&'a J,
    inputs:&'a [usize], known:&'a QueryFacts, frame:&'a mut Frame,
    counts:&'a mut Counts, work:&'a mut Work, answers:&'a mut Vec<Binding>,
}
impl Host<'_, '_> {
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
        if self.answers.len() == self.answers.capacity() { self.counts.answer_buffer_allocations += 1; }
        self.answers.push(Binding::matched(self.inputs.iter().zip(&self.query.inputs).map(|(&slot,f)|
            (slot,f.operand_in(self.reads.parents,|c|&self.entry.values[c],&self.frame.values,expanded).into_owned())).collect(),
            self.known.with_rows(self.frame.witnesses.iter().copied()),epoch));
        self.answers.last_mut().unwrap().compiled=true;
        Ok(())
    }
}
