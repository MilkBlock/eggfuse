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
    worker_rows:Vec<u64>, worker_tables:Vec<u64>, worker_task_seconds:Vec<f64>,
    prepare_seconds:f64, execute_seconds:f64, restore_seconds:f64,
    task_capacity_bytes:u64, change_capacity_bytes:u64, max_table_rows:u64,
    change_buffer_growths:u64, peak_retained_change_bytes:u64,
    table_rows:Vec<u64>, table_task_seconds:Vec<f64>,
}
struct Task<'a> {
    table:usize, changes:&'a FxHashMap<Dependency,Change>, version:u64,
    columns:Option<crate::query::PublicationTask>,
    ranges:Option<crate::range_index::PublicationTask>,
    neighbor:Option<crate::neighbor::PublicationTask>,
    worker:Option<usize>, seconds:f64, row_reads:u64, error:Option<String>,
}
impl Task<'_> {
    fn run(&mut self,reads:&crate::graph::query_reads::QueryReads<'_>,pooled:bool) {
        self.worker=pooled.then(rayon::current_thread_index).flatten();
        let clock=Instant::now();
        let result=(|| {
            for (&w,change) in self.changes {
                let row=if *change==Change::Wake {self.row_reads+=1;reads.row(w)?} else {None};
                if let Some(columns)=&mut self.columns {columns.update(w,row.as_ref());}
                if let Some(ranges)=&mut self.ranges {ranges.update(w,row.as_ref())?;}
                if let Some(neighbor)=&mut self.neighbor {neighbor.update(w,row.as_ref());}
            }
            if let Some(columns)=&mut self.columns {columns.finish(self.version);}
            if let Some(ranges)=&mut self.ranges {ranges.finish(self.version);}
            if let Some(neighbor)=&mut self.neighbor {neighbor.finish(self.version);}
            Ok(())
        })();
        self.error=result.err();
        self.seconds=clock.elapsed().as_secs_f64();
    }
}
impl Publication {
    pub(crate) fn enable_parallel(&mut self) {self.parallel.enabled=true;}
    pub(crate) fn parallel_enabled(&self)->bool {self.parallel.enabled}
    pub(super) fn publish_parallel(&mut self,g:&Graph,columns:&mut QueryIndexes,
        mut ranges:Option<&mut RangeIndex>,neighbor:&mut Context,pool:Option<&rayon::ThreadPool>,grain:usize,
        publish_ports:&mut impl FnMut(usize,&FxHashMap<Dependency,Change>,bool))->Result<bool> {
        let needed=|t|columns.has_columns(t) || ranges.as_ref().is_some_and(|r|r.has_publication(t)) || neighbor.has_publication(t);
        let (count,total)=g.changes.tables().filter(|(t,_)|needed(*t))
            .fold((0,0),|(n,rows),(_,c)|(n+1,rows+c.len()));
        if total<grain.max(256) {self.parallel.small_batches+=1;return Ok(false);}
        let clock=Instant::now();
        let Some(reads)=g.publication_reads(g.changes.tables().filter(|(t,_)|needed(*t)).map(|(t,_)|t))
            .filter(|r|r.canonical_rows()) else {
            self.parallel.readiness_fallbacks+=1;return Ok(false);
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
            if column.is_none() && range.is_none() && ports.is_none() {
                self.header_only+=count;continue;
            }
            self.column_rows+=count*u64::from(column.is_some());
            self.range_rows+=count*u64::from(range.is_some());
            self.neighbor_rows+=count*u64::from(ports.is_some());
            self.parallel.column_rows+=count*u64::from(column.is_some());
            self.parallel.range_rows+=count*u64::from(range.is_some());
            self.parallel.neighbor_rows+=count*u64::from(ports.is_some());
            tasks.push(Task {table:t,changes,version,columns:column,ranges:range,neighbor:ports,
                worker:None,seconds:0.0,row_reads:0,error:None});
        }
        let pooled=pool.is_some() && tasks.len()>1;
        self.parallel.batches+=1;
        self.parallel.pool_calls+=u64::from(pooled);
        self.parallel.task_capacity_bytes+=(tasks.capacity()*std::mem::size_of::<Task<'_>>()) as u64;
        self.parallel.prepare_seconds+=clock.elapsed().as_secs_f64();
        let clock=Instant::now();
        if pooled {pool.unwrap().install(||tasks.par_iter_mut().for_each(|t|t.run(&reads,true)));}
        else {for t in &mut tasks {t.run(&reads,false);}}
        self.parallel.execute_seconds+=clock.elapsed().as_secs_f64();
        let clock=Instant::now();
        let n=pool.map_or(1,|p|p.current_num_threads());
        self.parallel.worker_rows.resize(n,0);
        self.parallel.worker_tables.resize(n,0);
        self.parallel.worker_task_seconds.resize(n,0.0);
        self.parallel.table_rows.resize(g.program.tables.len(),0);
        self.parallel.table_task_seconds.resize(g.program.tables.len(),0.0);
        let mut error=None;
        // Restore in source table order, including the ordinary Sieve change
        // stream. A failed task keeps its prior version, never a false ready bit.
        for task in tasks {
            if error.is_none() {error=task.error;}
            let rows=task.changes.len() as u64;
            self.parallel.tables+=1;self.parallel.rows+=rows;
            self.parallel.table_rows[task.table]+=rows;
            self.parallel.table_task_seconds[task.table]+=task.seconds;
            self.parallel.max_table_rows=self.parallel.max_table_rows.max(rows);
            self.parallel.row_reads+=task.row_reads;self.row_reads+=task.row_reads;
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
        }
        columns.finish_publication();
        self.parallel.peak_retained_change_bytes=self.parallel.peak_retained_change_bytes.max(columns.publication_buffer_bytes() as u64);
        self.parallel.restore_seconds+=clock.elapsed().as_secs_f64();
        if let Some(error)=error {return Err(error);}
        Ok(true)
    }
}
