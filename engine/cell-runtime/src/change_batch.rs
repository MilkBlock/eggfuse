//! Coalesced notifications for one Run, sealed when graph repair finishes.
//! Commit order and producer receipts have separate ownership in Spine.
use crate::{
    graph::{Dependency, Graph, Row},
    neighbor::Context,
    program::Result,
    query::QueryIndexes,
    range_index::RangeIndex,
};
use rustc_hash::FxHashMap;
#[cfg(feature = "parallel-publication")]
#[path = "parallel_publication.rs"]
mod parallel;

#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) enum Change {
    // Includes a subsumed fact: readers wake and inspect its hidden bit.
    Wake,
    Removed,
    // Keep the original distinct event count when repair retires an earlier write.
    RemovedAfterWake,
}

pub(crate) struct ChangeBatch {
    tables: Vec<FxHashMap<Dependency, Change>>,
    active: Vec<usize>,
    // Allocated only for selective publication. Counts move with each table,
    // including writes coalesced before a later retirement.
    counts: Option<Vec<(u64, u64)>>,
    pub events: u64,
    pub distinct_events: u64,
}

impl ChangeBatch {
    pub fn new(tables: usize) -> Self {
        Self {
            tables: vec![FxHashMap::default(); tables],
            active: Vec::new(),
            counts: None,
            events: 0,
            distinct_events: 0,
        }
    }

    fn table(&mut self, table: usize) -> &mut FxHashMap<Dependency, Change> {
        let rows = &mut self.tables[table];
        if rows.is_empty() {
            self.active.push(table);
        }
        rows
    }

    pub fn touch(&mut self, table: usize, witness: Dependency) {
        let previous = self.table(table).insert(witness, Change::Wake);
        self.events += 1;
        self.distinct_events += u64::from(matches!(previous, None | Some(Change::Removed)));
        if let Some(counts) = &mut self.counts {
            counts[table].0 += 1;
            counts[table].1 += u64::from(matches!(previous, None | Some(Change::Removed)));
        }
    }

    pub fn retire(&mut self, table: usize, witness: Dependency) {
        let change = self.table(table).entry(witness).or_insert(Change::Removed);
        if *change == Change::Wake {
            *change = Change::RemovedAfterWake;
        }
    }

    #[cfg(feature = "projection-semijoin")]
    pub(crate) fn for_table(&self, t: usize) -> &FxHashMap<Dependency, Change> {
        &self.tables[t]
    }
    pub fn tables(&self) -> impl Iterator<Item = (usize, &FxHashMap<Dependency, Change>)> {
        self.active.iter().map(|&t| (t, &self.tables[t]))
    }

    pub fn is_empty(&self) -> bool {
        self.active.is_empty()
    }

    pub fn clear(&mut self) {
        for t in self.active.drain(..) {
            self.tables[t].clear();
            if let Some(counts) = &mut self.counts {
                counts[t] = (0, 0);
            }
        }
        self.events = 0;
        self.distinct_events = 0;
    }

    pub(crate) fn enable_split(&mut self) {
        assert!(self.is_empty(), "enable split after initial publication");
        self.counts = Some(vec![(0, 0); self.tables.len()]);
    }

    /// Move whole table batches; never copy fields or re-deliver deferred rows.
    /// The empty scratch maps are exchanged so both paths retain allocations.
    pub(crate) fn defer_unready(&mut self, ready: &[bool], deferred: &mut Self) -> (usize, usize) {
        assert!(deferred.is_empty());
        let checked = self.active.len();
        let counts = self.counts.as_mut().expect("split counts");
        let saved = deferred.counts.as_mut().expect("split counts");
        let mut moved = 0;
        self.active.retain(|&t| {
            if ready[t] {
                return true;
            }
            moved += self.tables[t].len();
            std::mem::swap(&mut self.tables[t], &mut deferred.tables[t]);
            std::mem::swap(&mut counts[t], &mut saved[t]);
            self.events -= saved[t].0;
            self.distinct_events -= saved[t].1;
            deferred.events += saved[t].0;
            deferred.distinct_events += saved[t].1;
            deferred.active.push(t);
            false
        });
        (moved, checked)
    }
}

impl Change {
    pub fn row(&self, graph: &Graph, w: Dependency) -> Result<Option<Row>> {
        if *self == Change::Wake {
            graph.row(w)
        } else {
            Ok(None)
        }
    }
}

#[derive(Default, serde::Serialize)]
pub(crate) struct Publication {
    #[cfg(feature = "parallel-publication")]
    parallel: parallel::Stats,
    #[cfg(feature = "view-storage")]
    view_column_rows: u64,
    row_reads: u64,
    headers: u64,
    header_only: u64,
    column_rows: u64,
    range_rows: u64,
    neighbor_rows: u64,
}
impl Publication {
    #[cfg(feature = "rhs-work-audit")]
    pub fn index_writes(&self) -> [u64; 3] {
        [self.column_rows, self.range_rows, self.neighbor_rows]
    }
    /// Resolve each requested witness once, after repair. Column and range indexes
    /// retain their own previous keys so a removal needs only the witness.
    pub fn publish(
        &mut self,
        #[cfg(feature = "family-survey")] sample: (&mut crate::family_survey::Survey, bool),
        g: &Graph,
        columns: &mut QueryIndexes,
        mut ranges: Option<&mut RangeIndex>,
        neighbor: &mut Context,
        #[cfg(feature = "parallel-publication")] workers:Option<(Option<&rayon::ThreadPool>,usize)>,
        mut publish_ports: impl FnMut(usize, &FxHashMap<Dependency, Change>, bool),
    ) -> Result<()> {
        #[cfg(feature = "parallel-publication")]
        if let Some((pool,grain))=workers
            && self.publish_parallel(g,columns,ranges.as_deref_mut(),neighbor,pool,grain,&mut publish_ports)? {
            return Ok(());
        }
        columns.begin_publication(g);
        for (t, changes) in g.changes.tables() {
            let count = changes.len() as u64;
            self.headers += count;
            let version = g.query_versions[t];
            #[cfg(feature = "family-survey")]
            let clock = std::time::Instant::now();
            let mut writer = columns.writer(t, version);
            publish_ports(t, changes, writer.is_some());
            #[cfg(feature = "view-storage")]
            if writer.is_some() && g.has_view_plan(t) {
                self.view_column_rows += count;
            }
            let mut range = ranges.as_deref_mut().and_then(|r| r.writer(t));
            let mut neighbors = neighbor.writer(t);
            #[cfg(feature = "family-survey")]
            let observed = (writer.is_some(), range.is_some());
            if writer.is_none() && range.is_none() && neighbors.is_none() {
                #[cfg(feature = "family-survey")]
                sample.0.table(
                    clock.elapsed().as_nanos() as u64,
                    t,
                    count,
                    changes.values().filter(|v| **v == Change::Wake).count() as u64,
                    sample.1,
                    false,
                    false,
                    false,
                );
                self.header_only += count;
                continue;
            }
            self.column_rows += count * u64::from(writer.is_some());
            self.range_rows += count * u64::from(range.is_some());
            self.neighbor_rows += count * u64::from(neighbors.is_some());
            for (&w, change) in changes {
                let row = change.row(g, w)?;
                self.row_reads += u64::from(*change == Change::Wake);
                let row = row.as_ref();
                if let Some(writer) = &mut writer {
                    writer.update(w, row);
                }
                if let Some(range) = &mut range {
                    range.update(w, row)?;
                }
                if let Some(neighbors) = &mut neighbors {
                    neighbors.update(w, row);
                }
            }
            if let Some(writer) = writer {
                writer.finish(version);
            }
            if let Some(range) = range {
                range.finish(version);
            }
            #[cfg(feature = "family-survey")]
            let neighbors_observed = neighbors.is_some();
            if let Some(neighbors) = neighbors {
                neighbors.finish(version);
            }
            #[cfg(feature = "family-survey")]
            sample.0.table(
                clock.elapsed().as_nanos() as u64,
                t,
                count,
                changes.values().filter(|v| **v == Change::Wake).count() as u64,
                sample.1,
                observed.0,
                observed.1,
                neighbors_observed,
            );
        }
        columns.finish_publication();
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selective_publication_moves_retirements_and_exact_counts_once() {
        let mut batch = ChangeBatch::new(2);
        let mut deferred = ChangeBatch::new(2);
        batch.enable_split();
        deferred.enable_split();
        let a = Dependency::Function(0);
        let b = Dependency::Function(1);
        batch.touch(0, a);
        batch.touch(0, a);
        batch.retire(0, a);
        batch.touch(1, b);
        assert_eq!(batch.defer_unready(&[false, true], &mut deferred), (1, 2));
        assert_eq!((batch.events, batch.distinct_events), (1, 1));
        assert_eq!((deferred.events, deferred.distinct_events), (2, 1));
        assert_eq!(batch.tables().map(|(t, _)| t).collect::<Vec<_>>(), [1]);
        batch.clear();
        std::mem::swap(&mut batch, &mut deferred);
        assert!(deferred.is_empty());
        assert!(batch.tables().next().unwrap().1[&a] == Change::RemovedAfterWake);
        batch.touch(0, a);
        assert_eq!((batch.events, batch.distinct_events), (3, 1));
        batch.clear();
        batch.retire(1, b);
        assert_eq!(batch.defer_unready(&[true, false], &mut deferred), (1, 1));
        assert_eq!((deferred.events, deferred.distinct_events), (0, 0));
    }

    #[test]
    fn retirement_cancels_wakeup_but_keeps_delivery_counts() {
        let mut batch = ChangeBatch::new(2);
        let w = Dependency::Function(0);
        let survivor = Dependency::Function(1);
        batch.touch(1, w);
        batch.touch(1, w);
        batch.retire(1, w);
        batch.retire(1, w);
        batch.touch(1, survivor);
        let (table, rows) = batch.tables().next().unwrap();
        assert_eq!(table, 1);
        assert!(rows[&w] == Change::RemovedAfterWake);
        assert!(rows[&survivor] == Change::Wake);
        assert_eq!((batch.events, batch.distinct_events), (3, 2));
        batch.clear();
        assert!(batch.is_empty());
        batch.retire(1, w);
        assert_eq!((batch.events, batch.distinct_events), (0, 0));
    }
}
