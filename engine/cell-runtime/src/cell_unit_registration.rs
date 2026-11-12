//! A terminal Cell batch gives each table exclusive index/publication ownership.
//! Workers classify exact keys; a short source-order scan assigns compact IDs.
//! Actual rows are adopted once by source completion, then table owners install
//! the directory, membership, version and change events before any new query.
use super::*;
use rayon::prelude::*;
use crate::sync_diagnostics::{Clock, Timed, registry_inline};

#[derive(Clone, Copy)]
enum Choice { New, Existing(usize), Earlier(usize) }
struct Item<'a> { source: usize, row: &'a units::Row, choice: Choice }

impl Graph {
    /// Caller proves every parked Cell is already at its terminal boundary:
    /// no mutable read, union, fallible suffix or new Function-producing effect
    /// can intervene between classification and source-ordered adoption.
    pub(crate) fn plan_unit_registration(&mut self, done: &mut [Done], pool: &rayon::ThreadPool) -> bool {
        let mut diagnostic = Clock::new();
        if !self.pending_unions.is_empty() || !self.dirty.is_empty() || !self.dirty_markers.is_empty() { return false; }
        let count = done.iter().map(|d|d.piece.units.len()).sum::<usize>();
        if count < 32 || done.iter().flat_map(|d|&d.piece.units).any(|r|self.units.owned[r.function.table]) { return false; }
        let mut tables = BTreeMap::<usize, Vec<Item<'_>>>::new();
        for (source, row) in done.iter().flat_map(|d|&d.piece.units).enumerate() {
            tables.entry(row.function.table).or_default().push(Item { source, row, choice: Choice::New });
        }
        if tables.len() < 2 { return false; }
        let mut jobs: Vec<_> = tables.into_iter().map(|(table, rows)|Timed::new((&self.function_keys[table], rows))).collect();
        let run = |job: &mut Timed<(&scalar_keys::FunctionKeys, Vec<Item<'_>>)>| job.run(|(keys, rows)| {
            let mut seen = rustc_hash::FxHashMap::<&[Value], usize>::default();
            for item in rows.iter_mut() {
                item.choice = if let Some(&index) = keys.get(&item.row.function.key) { Choice::Existing(index) }
                    else if let Some(&previous) = seen.get(item.row.function.key.as_slice()) { Choice::Earlier(previous) }
                    else { seen.insert(&item.row.function.key, item.source); Choice::New };
            }
            seen.capacity()*std::mem::size_of::<(&[Value],usize)>()
        });
        diagnostic.enter();
        let scratch: usize = if registry_inline() { jobs.iter_mut().map(run).sum() }
            else { pool.install(||jobs.par_iter_mut().map(run).sum()) };
        diagnostic.join();
        #[cfg(feature="cell-sync-diagnostics")]
        let spans: Vec<_> = jobs.iter().filter_map(|job|job.span).collect();
        let mut choices = vec![Choice::New; count];
        let bytes = jobs.capacity()*std::mem::size_of_val(&jobs[0].value)
            + jobs.iter().map(|job|job.value.1.capacity()*std::mem::size_of::<Item<'_>>()).sum::<usize>()
            + choices.capacity()*std::mem::size_of::<Choice>() + scratch;
        let mut first = BTreeSet::new();
        for job in jobs {
            let (_, rows) = job.value;
            if let Some(row) = rows.iter().find(|r|matches!(r.choice,Choice::New)) { first.insert(row.source); }
            for item in rows { choices[item.source] = item.choice; }
        }
        let mut next = self.functions.len();
        for (source, row) in done.iter_mut().flat_map(|d|&mut d.piece.units).enumerate() {
            let (index, new) = match choices[source] {
                Choice::New => { let i = next; next += 1; (i, true) }
                Choice::Existing(i) => (i, false),
                Choice::Earlier(previous) => {
                    let Choice::Existing(i) = choices[previous] else { unreachable!("earlier source resolved") };
                    (i, false)
                }
            };
            choices[source] = Choice::Existing(index);
            row.registered = Some((index, new, first.contains(&source)));
        }
        self.stats.unit_registry_batches += 1;
        self.stats.unit_registry_candidates += count as u64;
        self.stats.unit_registry_bytes += bytes as u64;
        #[cfg(feature="cell-sync-diagnostics")]
        self.stats.sync_diagnostics.classify.record(diagnostic,Some(&spans),!registry_inline(),pool.current_num_threads());
        true
    }

    /// Install only rows actually appended, also on an early error path. This
    /// never publishes a directory entry pointing to an unallocated Function.
    pub(crate) fn finish_unit_registration(&mut self, start: usize, pool: &rayon::ThreadPool) {
        let mut diagnostic = Clock::new();
        let mut groups = BTreeMap::<usize, Vec<usize>>::new();
        for (offset, row) in self.functions[start..].iter().enumerate() {
            groups.entry(row.table).or_default().push(start + offset);
        }
        if groups.is_empty() { return; }
        let tables: Vec<_> = groups.keys().copied().collect();
        let changes = self.changes.new_row_tables(&tables);
        let mut keys = self.function_keys.iter_mut();
        let mut members = self.members.iter_mut();
        let mut versions = self.query_versions.iter_mut();
        let mut previous = 0;
        let mut jobs: Vec<_> = groups.into_iter().zip(changes).map(|((table, rows), changes)| {
            let distance = table - previous; previous = table + 1;
            Timed::new((table, rows, keys.nth(distance).unwrap(), members.nth(distance).unwrap(),
                versions.nth(distance).unwrap(), changes))
        }).collect();
        let functions = &self.functions;
        let run = |job: &mut Timed<(_, Vec<usize>, &mut scalar_keys::FunctionKeys, &mut TableRows<u64>, &mut u64, &mut rustc_hash::FxHashMap<Dependency, crate::change_batch::Change>)>| job.run(|(_,rows,keys,members,version,changes)| {
            for &index in rows.iter() {
                keys.insert(&functions[index].key, index);
                members.insert(index as u64);
                assert!(changes.insert(Dependency::Function(index), crate::change_batch::Change::Wake).is_none());
            }
            **version += rows.len() as u64;
        });
        diagnostic.enter();
        if registry_inline() { jobs.iter_mut().for_each(run); }
        else { pool.install(||jobs.par_iter_mut().for_each(run)); }
        diagnostic.join();
        #[cfg(feature="cell-sync-diagnostics")]
        let spans: Vec<_> = jobs.iter().filter_map(|job|job.span).collect();
        self.stats.unit_registry_tables += jobs.len() as u64;
        self.stats.unit_registry_installs += (self.functions.len()-start) as u64;
        self.stats.unit_registry_bytes += (jobs.capacity()*std::mem::size_of_val(&jobs[0].value)
            + jobs.iter().map(|j|j.value.1.capacity()*std::mem::size_of::<usize>()).sum::<usize>()) as u64;
        // Source adoption already activated tables in their original order.
        // Only per-table event counts return to the host after releasing maps.
        let completed: Vec<_> = jobs.into_iter().map(|job| { let (table,rows,_,_,_,_) = job.value;
            (table,rows.len() as u64) }).collect();
        for (table,count) in completed { self.changes.finish_new_rows(table,count); }
        #[cfg(feature="cell-sync-diagnostics")]
        self.stats.sync_diagnostics.install.record(diagnostic,Some(&spans),!registry_inline(),pool.current_num_threads());
    }
}
