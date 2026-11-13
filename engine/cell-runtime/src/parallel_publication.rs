//! Publish repaired Cell outputs through exclusive existing index partitions.
//! The graph is borrowed until join; no graph mutation or second index exists.
use super::*;
use rayon::prelude::*;
use std::time::Instant;

#[derive(Default,serde::Serialize)]
pub(super) struct Stats {
    enabled:bool, batches:u64, pool_calls:u64, tables:u64, rows:u64,
    row_reads:u64, column_rows:u64, range_rows:u64, neighbor_rows:u64,
    inline_rows:u64, readiness_fallbacks:u64, small_batches:u64,
    admission_bound_tables:u64, admission_bound_rejections:u64, admission_owner_checks_avoided:u64,
    worker_rows:Vec<u64>, worker_tables:Vec<u64>, worker_task_seconds:Vec<f64>,
    prepare_seconds:f64, execute_seconds:f64, restore_seconds:f64,
    task_capacity_bytes:u64, change_capacity_bytes:u64, max_table_rows:u64,
    entry_order_headers:u64,
    entry_order_capacity_bytes:u64,
    split_entry_tasks:u64, split_entry_rows:u64, split_entry_row_reads:u64,
    single_table_split_batches:u64,
    duplicate_current_row_reads:u64, indexes_released_before_entries:u64,
    split_entry_worker_rows:Vec<u64>, split_entry_worker_seconds:Vec<f64>,
    condition_batches:u64, condition_table_header_bytes:u64,
    change_buffer_growths:u64, peak_retained_change_bytes:u64,
    table_rows:Vec<u64>, table_task_seconds:Vec<f64>,
}
struct Task<'a> {
    table:usize, changes:&'a FxHashMap<Dependency,Change>, version:u64,
    columns:Option<crate::query::PublicationTask>,
    ranges:Option<crate::range_index::PublicationTask>,
    neighbor:Option<crate::neighbor::PublicationTask>,
    entries:Option<crate::entry_schedule::PublicationTask>,
    worker:Option<usize>, seconds:f64, row_reads:u64, order_headers:u64, error:Option<String>,
    entry_worker:Option<usize>, entry_seconds:f64, entry_row_reads:u64,
    duplicate_reads:u64, split:bool, released_before_entry:bool, order_bytes:u64,
}
impl Task<'_> {
    fn run(&mut self,reads:&crate::graph::query_reads::QueryReads<'_>,pooled:bool) {
        self.worker=pooled.then(rayon::current_thread_index).flatten();
        let clock=Instant::now();
        let result=(|| {
            let mut ordered = Vec::new();
            if self.entries.is_some() {
                ordered.extend(self.changes.iter());
                ordered.sort_unstable_by_key(|(w,_)| **w);
                self.order_headers = ordered.len() as u64;
                self.order_bytes = (ordered.capacity()*std::mem::size_of::<(&Dependency,&Change)>()) as u64;
            }
            let mut update = |w: Dependency, change: &Change| -> Result<()> {
                let row=if *change==Change::Wake {self.row_reads+=1;reads.row(w)?} else {None};
                if let Some(columns)=&mut self.columns {columns.update(w,row.as_ref());}
                if let Some(ranges)=&mut self.ranges {ranges.update(w,row.as_ref())?;}
                if let Some(neighbor)=&mut self.neighbor {neighbor.update(w,row.as_ref());}
                if let Some(entries)=&mut self.entries {entries.update(w,row.as_ref(),reads);}
                Ok(())
            };
            if ordered.is_empty() { for (&w,change) in self.changes {update(w,change)?;} }
            else { for (&w,change) in ordered {update(w,change)?;} }
            if let Some(entries)=&mut self.entries {entries.finish(self.changes,reads)?;self.row_reads+=entries.row_reads;}
            if let Some(columns)=&mut self.columns {columns.finish(self.version);}
            if let Some(ranges)=&mut self.ranges {ranges.finish(self.version);}
            if let Some(neighbor)=&mut self.neighbor {neighbor.finish(self.version);}
            Ok(())
        })();
        self.error=result.err();
        self.seconds=clock.elapsed().as_secs_f64();
        self.entry_worker=self.worker;
    }
    fn can_split(&self, grain:usize) -> bool {
        self.entries.is_some() && self.changes.len()>=grain.max(256)
            && (self.columns.is_some() || self.ranges.is_some() || self.neighbor.is_some())
    }
    fn finish_split(&mut self) {
        // Ready condition readers need the completed fields, not a ready
        // version. Advance versions only after both owners have succeeded.
        if self.split && self.error.is_none() {
            if let Some(c)=&mut self.columns {c.finish(self.version);}
            if let Some(r)=&mut self.ranges {r.finish(self.version);}
            if let Some(n)=&mut self.neighbor {n.finish(self.version);}
        }
    }
    fn run_event(&mut self,reads:&crate::graph::query_reads::QueryReads<'_>,pooled:bool,grain:usize,
        ready:&(dyn Fn(Option<crate::query::PublicationTask>,bool)+Sync)) -> bool {
        if !pooled || !self.can_split(grain) {
            self.run(reads,pooled);
            ready(self.columns.take(),self.error.is_none());
            return self.error.is_none();
        }
        self.split=true;
        let clock=Instant::now();
        let mut ordered:Vec<_>=self.changes.iter().collect();
        ordered.sort_unstable_by_key(|(w,_)| **w);
        self.order_headers=ordered.len() as u64;
        self.order_bytes=(ordered.capacity()*std::mem::size_of::<(&Dependency,&Change)>()) as u64;
        let mut entry=self.entries.take().unwrap();
        let changes=self.changes;
        let entry_done=std::sync::atomic::AtomicBool::new(false);
        let (index_error,(entry_error,worker,seconds,row_reads,duplicates))=rayon::join(|| {
            self.worker=rayon::current_thread_index();
            let result=(|| -> std::result::Result<(),(usize,String)> {
                for (position,(&w,change)) in ordered.iter().copied().enumerate() {
                    let row=if *change==Change::Wake {
                        self.row_reads+=1;
                        reads.row(w).map_err(|e|(position,e))?
                    } else {None};
                    if let Some(c)=&mut self.columns {c.update(w,row.as_ref());}
                    if let Some(r)=&mut self.ranges {r.update(w,row.as_ref()).map_err(|e|(position,e))?;}
                    if let Some(n)=&mut self.neighbor {n.update(w,row.as_ref());}
                }
                Ok(())
            })();
            self.released_before_entry=!entry_done.load(std::sync::atomic::Ordering::Acquire);
            ready(self.columns.take(),result.is_ok());
            result.err()
        },|| {
            let clock=Instant::now();
            let worker=rayon::current_thread_index();
            let mut current_reads=0;
            let result=(|| -> std::result::Result<(),(usize,String)> {
                for (position,(&w,change)) in ordered.iter().copied().enumerate() {
                    let row=if *change==Change::Wake {
                        current_reads+=1;
                        reads.row(w).map_err(|e|(position,e))?
                    } else {None};
                    entry.update(w,row.as_ref(),reads);
                }
                entry.finish(changes,reads).map_err(|e|(ordered.len(),e))
            })();
            entry_done.store(true,std::sync::atomic::Ordering::Release);
            (result.err(),worker,clock.elapsed().as_secs_f64(),current_reads+entry.row_reads,current_reads)
        });
        self.entries=Some(entry);
        self.entry_worker=worker;
        self.entry_seconds=seconds;
        self.entry_row_reads=row_reads;
        self.duplicate_reads=duplicates;
        self.seconds=clock.elapsed().as_secs_f64();
        self.error=first_error(index_error,entry_error);
        self.error.is_none()
    }
    fn run_owned(&mut self,reads:&crate::graph::query_reads::QueryReads<'_>,pooled:bool,grain:usize) {
        let column=std::sync::OnceLock::new();
        self.run_event(reads,pooled,grain,&|c,_|assert!(column.set(c).is_ok()));
        self.columns=column.into_inner().expect("one index completion");
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn split_errors_follow_rows_then_index_before_entry() {
        let e=|row,message:&str|Some((row,message.to_owned()));
        assert_eq!(first_error(e(8,"index"),e(3,"entry")),Some("entry".into()));
        assert_eq!(first_error(e(3,"index"),e(3,"entry")),Some("index".into()));
        assert_eq!(first_error(e(8,"index"),e(9,"old notification")),Some("index".into()));
        assert_eq!(first_error(None,e(9,"old notification")),Some("old notification".into()));
    }
}
// Index work precedes Entry work at the same source row. Pending old Entry
// notifications come after every current row, regardless of worker completion.
fn first_error(index:Option<(usize,String)>, entry:Option<(usize,String)>)->Option<String> {
    match (index,entry) {
        (Some(a),Some(b))=>Some(if a.0<=b.0 {a.1}else{b.1}),
        (Some(e),None)|(None,Some(e))=>Some(e.1),
        (None,None)=>None,
    }
}
impl Publication {
    pub(crate) fn enable_parallel(&mut self) {self.parallel.enabled=true;}
    pub(crate) fn parallel_enabled(&self)->bool {self.parallel.enabled}
    pub(super) fn publish_parallel(&mut self,g:&Graph,columns:&mut QueryIndexes,
        ranges:Option<&mut RangeIndex>,neighbor:&mut Context,pool:Option<&rayon::ThreadPool>,grain:usize,
        entries:Option<&mut crate::entry_schedule::Scheduler>,
        sieve:Option<&mut crate::sieve::Sieve>,
        publish_ports:&mut impl FnMut(usize,&FxHashMap<Dependency,Change>,bool))->Result<Option<bool>> {
        // Needed owner rows are a subset of the sealed change maps. Their
        // existing lengths can reject small batches without probing indexes,
        // range maps, neighbor state or Entry readiness. Stop as soon as this
        // bound ceases to prove rejection; no retained admission state exists.
        let minimum=grain.max(256);
        let (mut rows,mut tables)=(0usize,0u64);
        for (_,changes) in g.changes.tables() {
            tables+=1;
            rows=rows.saturating_add(changes.len());
            if rows>=minimum {break;}
        }
        self.parallel.admission_bound_tables+=tables;
        if rows<minimum {
            self.parallel.small_batches+=1;
            self.parallel.admission_bound_rejections+=1;
            self.parallel.admission_owner_checks_avoided+=tables;
            return Ok(None);
        }
        self.publish_parallel_candidates(g,columns,ranges,neighbor,pool,grain,entries,sieve,publish_ports)
    }
    // Keep task storage and its register pressure out of the small-batch path.
    // The row bound grants no readiness or owner proof: retain the exact owner
    // count and canonical-read checks before moving any publication owners.
    #[inline(never)]
    fn publish_parallel_candidates(&mut self,g:&Graph,columns:&mut QueryIndexes,
        mut ranges:Option<&mut RangeIndex>,neighbor:&mut Context,pool:Option<&rayon::ThreadPool>,grain:usize,
        mut entries:Option<&mut crate::entry_schedule::Scheduler>,
        sieve:Option<&mut crate::sieve::Sieve>,
        publish_ports:&mut impl FnMut(usize,&FxHashMap<Dependency,Change>,bool))->Result<Option<bool>> {
        let needed=|t|columns.has_columns(t) || ranges.as_ref().is_some_and(|r|r.has_publication(t)) || neighbor.has_publication(t) || entries.as_ref().is_some_and(|e|e.has_publication_work(t));
        let (count,total)=g.changes.tables().filter(|(t,_)|needed(*t))
            .fold((0,0),|(n,rows),(_,c)|(n+1,rows+c.len()));
        if total<grain.max(256) {self.parallel.small_batches+=1;return Ok(None);}
        let clock=Instant::now();
        let Some(reads)=g.publication_reads(g.changes.tables().filter(|(t,_)|needed(*t)).map(|(t,_)|t))
            .filter(|r|r.canonical_rows()) else {
            self.parallel.readiness_fallbacks+=1;return Ok(None);
        };
        columns.begin_publication(g);
        let mut tasks=Vec::with_capacity(count);
        for (t,changes) in g.changes.tables() {
            let count=changes.len() as u64;
            self.headers+=count;
            let version=g.query_versions[t];
            let column=columns.take_publication(t,version);
            // This callback only publishes authoritative graph changes to the
            // existing view consumer. It cannot observe a partially built index.
            publish_ports(t,changes,column.is_some());
            #[cfg(feature = "view-storage")]
            if column.is_some() && g.has_view_plan(t) {self.view_column_rows+=count;}
            let range=ranges.as_deref_mut().and_then(|r|r.take_publication(t));
            let ports=neighbor.take_publication(t);
            let entry=entries.as_deref_mut().and_then(|e|e.take_publication_work(t));
            if column.is_none() && range.is_none() && ports.is_none() && entry.is_none() {
                self.header_only+=count;continue;
            }
            self.column_rows+=count*u64::from(column.is_some());
            self.range_rows+=count*u64::from(range.is_some());
            self.neighbor_rows+=count*u64::from(ports.is_some());
            self.parallel.column_rows+=count*u64::from(column.is_some());
            self.parallel.range_rows+=count*u64::from(range.is_some());
            self.parallel.neighbor_rows+=count*u64::from(ports.is_some());
            tasks.push(Task {table:t,changes,version,columns:column,ranges:range,neighbor:ports,entries:entry,
                worker:None,seconds:0.0,row_reads:0,order_headers:0,error:None,
                entry_worker:None,entry_seconds:0.0,entry_row_reads:0,duplicate_reads:0,
                split:false,released_before_entry:false,order_bytes:0});
        }
        let pooled=pool.is_some_and(|p|p.current_num_threads()>1)
            && (tasks.len()>1 || tasks.iter().any(|t|t.can_split(grain)));
        self.parallel.batches+=1;
        self.parallel.pool_calls+=u64::from(pooled);
        self.parallel.single_table_split_batches+=u64::from(pooled && tasks.len()==1 && tasks[0].can_split(grain));
        self.parallel.task_capacity_bytes+=(tasks.capacity()*std::mem::size_of::<Task<'_>>()) as u64;
        self.parallel.prepare_seconds+=clock.elapsed().as_secs_f64();
        let clock=Instant::now();
        let conditions=sieve.is_some_and(|sieve| {
            let ids:Vec<_>=tasks.iter().map(|t|(t.table,t.columns.is_some())).collect();
            self.parallel.condition_table_header_bytes+=(ids.capacity()*std::mem::size_of::<(usize,bool)>()) as u64;
            sieve.publish_table_events_early(columns,&ids,&mut tasks,pool.filter(|_|pooled),
                |task,ready|task.run_event(&reads,pooled,grain,ready),
                |task,column|task.columns=column)
        });
        self.parallel.condition_batches+=u64::from(conditions);
        if !conditions {
            if pooled {pool.unwrap().install(||tasks.par_iter_mut().for_each(|t|t.run_owned(&reads,true,grain)));}
            else {for t in &mut tasks {t.run(&reads,false);}}
        }
        self.parallel.execute_seconds+=clock.elapsed().as_secs_f64();
        let clock=Instant::now();
        let n=pool.map_or(1,|p|p.current_num_threads()).max(self.parallel.worker_rows.len());
        self.parallel.worker_rows.resize(n,0);
        self.parallel.worker_tables.resize(n,0);
        self.parallel.worker_task_seconds.resize(n,0.0);
        self.parallel.split_entry_worker_rows.resize(n,0);
        self.parallel.split_entry_worker_seconds.resize(n,0.0);
        self.parallel.table_rows.resize(g.program.tables.len(),0);
        self.parallel.table_task_seconds.resize(g.program.tables.len(),0.0);
        let mut error=None;
        // Restore in source table order, including the ordinary Sieve change
        // stream. A failed task keeps its prior version, never a false ready bit.
        for mut task in tasks {
            task.finish_split();
            if error.is_none() {error=task.error;}
            let rows=task.changes.len() as u64;
            self.parallel.entry_order_headers+=task.order_headers;
            self.parallel.entry_order_capacity_bytes+=task.order_bytes;
            if task.split {
                self.parallel.split_entry_tasks+=1;
                self.parallel.split_entry_rows+=rows;
                self.parallel.split_entry_row_reads+=task.entry_row_reads;
                self.parallel.duplicate_current_row_reads+=task.duplicate_reads;
                self.parallel.indexes_released_before_entries+=u64::from(task.released_before_entry);
                if let Some(i)=task.entry_worker {
                    self.parallel.split_entry_worker_rows[i]+=rows;
                    self.parallel.split_entry_worker_seconds[i]+=task.entry_seconds;
                }
            }
            self.parallel.tables+=1;self.parallel.rows+=rows;
            self.parallel.table_rows[task.table]+=rows;
            self.parallel.table_task_seconds[task.table]+=task.seconds;
            self.parallel.max_table_rows=self.parallel.max_table_rows.max(rows);
            self.parallel.row_reads+=task.row_reads+task.entry_row_reads;
            self.row_reads+=task.row_reads+task.entry_row_reads;
            if let Some(i)=task.worker {
                self.parallel.worker_rows[i]+=rows;self.parallel.worker_tables[i]+=1;
                self.parallel.worker_task_seconds[i]+=task.seconds;
            } else {self.parallel.inline_rows+=rows;}
            if let Some(c)=task.columns {
                self.parallel.change_capacity_bytes+=c.buffer_bytes() as u64;
                self.parallel.change_buffer_growths+=c.buffer_growths();
                columns.restore_publication(c);
            }
            if let Some(r)=task.ranges {ranges.as_deref_mut().unwrap().restore_publication(r);}
            if let Some(p)=task.neighbor {neighbor.restore_publication(p);}
            if let Some(e)=task.entries {entries.as_deref_mut().unwrap().restore_publication_work(e,task.entry_worker);}
        }
        columns.finish_publication();
        self.parallel.peak_retained_change_bytes=self.parallel.peak_retained_change_bytes.max(columns.publication_buffer_bytes() as u64);
        self.parallel.restore_seconds+=clock.elapsed().as_secs_f64();
        if let Some(error)=error {return Err(error);}
        Ok(Some(conditions))
    }
}
