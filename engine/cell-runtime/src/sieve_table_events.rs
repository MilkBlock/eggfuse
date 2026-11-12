//! The existing table owner releases conditions in the same worker scope.
//! Only the node's own table and compiled child edges are prerequisites. The
//! original Columns and Summary owners survive until the Run publication fence.
use super::*;
use crate::query::PublicationTask;

#[derive(Default, serde::Serialize)]
pub(super) struct Work {
    attempts: u64,
    batches: u64,
    unavailable: u64,
    shared_pool_calls: u64,
    table_events: u64,
    potential_nodes: u64,
    completed_nodes: u64,
    early_nodes: u64,
    early_work_nodes: u64,
    empty_nodes: u64,
    failed_batches: u64,
    discarded_nodes: u64,
    change_handoff_rows_avoided: u64,
    header_bytes: u64,
    group_capacity_bytes: u64,
    group_header_bytes: u64,
    group_growth_bytes: u64,
    materialized_nodes: u64,
    summary_borrows: u64,
    unchanged_child_borrows: u64,
    partition_steps: u64,
    partition_comparisons: u64,
    owner_header_bytes: u64,
    result_header_bytes: u64,
}

#[derive(Default)]
struct Inputs {
    groups: Vec<Vec<usize>>,
    dispatches: u64,
    inactive: u64,
    column_checks: u64,
    skipped: u64,
    rows: u64,
    headers: u64,
    growth_bytes: u64,
}
struct Table {
    column: Option<PublicationTask>,
    inputs: Inputs,
    ok: bool,
}
struct Node<'a> {
    state: &'a mut Summary,
    added: Vec<Projection>,
    direct: u64,
    dependencies: u64,
    visits: u64,
    columns: u64,
    worker: Option<usize>,
    seconds: f64,
}
// Empty readiness propagation only exposes the original immutable Summary.
// It never creates execution state, a delta vector or a timing record.
enum Finished<'a> {
    Empty(&'a Summary),
    Executed(Node<'a>),
}
impl Finished<'_> {
    fn read(&self) -> (&Summary, &[Projection]) {
        match self {
            Self::Empty(state) => (state, &[]),
            Self::Executed(node) => (&*node.state, &node.added),
        }
    }
}
struct Events<'a> {
    specs: &'a [Spec],
    parents: &'a [Vec<(usize, usize)>],
    dispatch: &'a [Dispatch],
    group: &'a [usize],
    table_groups: &'a [usize],
    unchanged: Vec<&'a Summary>,
    index: &'a QueryIndexes,
    collide: bool,
    positions: Vec<usize>,
    table_positions: Vec<usize>,
    table_ids: &'a [(usize, bool)],
    node_ids: &'a [usize],
    owners: Vec<Mutex<Option<&'a mut Summary>>>,
    finished: Vec<OnceLock<Finished<'a>>>,
    remaining: Vec<AtomicUsize>,
    inputs: Vec<Mutex<Option<Inputs>>>,
    tables: Vec<OnceLock<Table>>,
    unfinished_tables: AtomicUsize,
    early: AtomicUsize,
    early_work: AtomicUsize,
    empty: AtomicUsize,
    #[cfg(test)]
    after: Option<&'a (dyn Fn(usize, &Summary) + Sync)>,
}
impl<'a> Events<'a> {
    fn child(&self, id: usize) -> (&Summary, &[Projection]) {
        let p = self.positions[id];
        if p >= self.node_ids.len() {
            (self.unchanged[p - self.node_ids.len()], &[])
        } else {
            self.finished[p].get().expect("completed child").read()
        }
    }
    fn table(&self, id: usize) -> Option<&Table> {
        let p = self.table_positions[id];
        (p != usize::MAX).then(|| self.tables[p].get().expect("completed own table"))
    }
    fn direct(&self, id: usize) -> (&[usize], Option<&PublicationTask>) {
        let table = self.specs[id].table;
        let Some(done) = self.table(table) else {
            return (&[], None);
        };
        (
            &done.inputs.groups[self.group[id] - self.table_groups[table]],
            done.column.as_ref(),
        )
    }
    fn has_work(&self, id: usize) -> bool {
        !self.direct(id).0.is_empty()
            || self.specs[id]
                .guards
                .iter()
                .any(|g| !g.cols.is_empty() && !self.child(g.child).1.is_empty())
    }
    fn release<'scope>(&'scope self, p: usize, scope: Option<&rayon::Scope<'scope>>) {
        if self.remaining[p].fetch_sub(1, Ordering::AcqRel) != 1 {
            return;
        }
        self.ready(p, scope);
    }
    fn ready<'scope>(&'scope self, p: usize, scope: Option<&rayon::Scope<'scope>>) {
        let id = self.node_ids[p];
        let has_work = self.has_work(id);
        let state = self.owners[p]
            .lock()
            .unwrap()
            .take()
            .expect("one Summary borrow");
        if !has_work {
            self.empty.fetch_add(1, Ordering::Relaxed);
            self.finish(p, Finished::Empty(state), scope, false);
        } else if let Some(scope) = scope {
            scope.spawn(move |scope| self.complete(p, state, Some(scope)));
        } else {
            self.complete(p, state, None);
        }
    }
    fn complete<'scope>(
        &'scope self,
        p: usize,
        state: &'a mut Summary,
        scope: Option<&rayon::Scope<'scope>>,
    ) {
        let id = self.node_ids[p];
        let mut n = Node {
            state,
            added: Vec::new(),
            direct: 0,
            dependencies: 0,
            visits: 0,
            columns: 0,
            worker: None,
            seconds: 0.0,
        };
        let spec = &self.specs[id];
        let clock = Instant::now();
        let (direct, column) = self.direct(id);
        n.direct = direct.len() as u64;
        let mut columns = smallvec::SmallVec::<[usize; 4]>::new();
        for guard in &spec.guards {
            if !self.child(guard.child).1.is_empty() {
                columns.extend(guard.cols.iter().copied());
            }
        }
        columns.sort_unstable();
        columns.dedup();
        n.columns = columns.len() as u64;
        let read = (!columns.is_empty()).then(|| match column {
            Some(c) => c.publication_support(&columns),
            None => self.index.publication_support(spec.table, &columns),
        });
        let rows = direct.iter().map(|&p| {
            let c = column.expect("direct notification owner");
            c.hashes(c.changes()[p].0).expect("visible changed row")
        });
        (n.dependencies, n.visits) = complete_condition(
            spec,
            n.state,
            &mut n.added,
            rows,
            read.as_ref(),
            |id| self.child(id),
            self.collide,
        );
        n.worker = scope.and_then(|_| rayon::current_thread_index());
        n.seconds = clock.elapsed().as_secs_f64();
        let did_work = n.direct > 0 || n.columns > 0;
        self.finish(p, Finished::Executed(n), scope, did_work);
    }
    fn finish<'scope>(
        &'scope self,
        p: usize,
        result: Finished<'a>,
        scope: Option<&rayon::Scope<'scope>>,
        did_work: bool,
    ) {
        let id = self.node_ids[p];
        assert!(self.finished[p].set(result).is_ok());
        // Count actual unfinished table computation, not unprocessed callbacks.
        if self.unfinished_tables.load(Ordering::Acquire) != 0 {
            self.early.fetch_add(1, Ordering::Relaxed);
            if did_work {
                self.early_work.fetch_add(1, Ordering::Relaxed);
            }
        }
        #[cfg(test)]
        if let Some(after) = self.after {
            after(id, self.finished[p].get().unwrap().read().0);
        }
        for &(parent, _) in &self.parents[id] {
            let p = self.positions[parent];
            if p < self.node_ids.len() {
                self.release(p, scope);
            }
        }
    }
    fn table_complete<'scope>(
        &'scope self,
        p: usize,
        mut column: Option<PublicationTask>,
        ok: bool,
        scope: Option<&rayon::Scope<'scope>>,
    ) {
        let table = self.table_ids[p].0;
        let mut inputs = self.inputs[p].lock().unwrap().take().unwrap();
        if ok && let Some(c) = &mut column {
            c.sort_changes();
            let dispatch = &self.dispatch[table];
            for (position, &(w, _, fields)) in c.changes().iter().enumerate() {
                inputs.dispatches += 1;
                if dispatch.built == 0 {
                    inputs.inactive += 1;
                    continue;
                }
                if c.hashes(w).is_none() {
                    continue;
                }
                inputs.rows += 1;
                for (i, group) in dispatch.groups.iter().enumerate() {
                    if group.built == 0 {
                        continue;
                    }
                    if fields != u64::MAX {
                        inputs.column_checks += 1;
                        if fields & group.columns == 0 {
                            inputs.skipped += group.built as u64;
                            continue;
                        }
                    }
                    let before = inputs.groups[i].capacity();
                    inputs.groups[i].push(position);
                    inputs.growth_bytes += ((inputs.groups[i].capacity() - before)
                        * std::mem::size_of::<usize>())
                        as u64;
                    inputs.headers += 1;
                }
            }
        }
        assert!(self.tables[p].set(Table { column, inputs, ok }).is_ok());
        self.unfinished_tables.fetch_sub(1, Ordering::AcqRel);
        if !ok || self.table_positions[table] == usize::MAX {
            return;
        }
        // Static template membership, never a per-instance subscriber list.
        for &id in &self.dispatch[table].members {
            let position = self.positions[id];
            if position < self.node_ids.len() {
                self.release(position, scope);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::value::Value;
    use std::{sync::mpsc, time::Duration};

    fn graph() -> Graph {
        let original = crate::query::test_projection_graph();
        let mut p = serde_json::to_value(&original.program).unwrap();
        let mut third = p["tables"][0].clone();
        third["name"] = "unrelated".into();
        p["tables"].as_array_mut().unwrap().push(third);
        let mut graph = Graph::new(serde_json::from_value(p).unwrap()).unwrap();
        graph.merge_programs_enabled = false;
        graph
    }
    fn fixture(g: &Graph, index: &mut QueryIndexes, collide: bool) -> Sieve {
        let mut s = Sieve::new(&g.program);
        s.specs = vec![
            Spec::new(0, vec![0], vec![]),
            Spec::new(1, vec![0], vec![]),
            Spec::new(
                0,
                vec![2],
                vec![Guard {
                    cols: vec![1],
                    child: 1,
                }],
            ),
            Spec::new(
                0,
                vec![0, 1, 2],
                vec![
                    Guard {
                        cols: vec![1],
                        child: 1,
                    },
                    Guard {
                        cols: vec![0],
                        child: 0,
                    },
                ],
            ),
            Spec::new(
                1,
                vec![2],
                vec![Guard {
                    cols: vec![1],
                    child: 0,
                }],
            ),
            Spec::new(2, vec![0], vec![]),
            Spec::new(1, vec![], vec![]),
            Spec::new(
                0,
                vec![2],
                vec![Guard {
                    cols: vec![0],
                    child: 0,
                }],
            ),
            Spec::new(
                2,
                vec![2],
                vec![Guard {
                    cols: vec![0],
                    child: 0,
                }],
            ),
        ];
        s.states = (0..s.specs.len()).map(|_| Summary::default()).collect();
        s.parents = vec![vec![]; s.specs.len()];
        for (parent, spec) in s.specs.iter().enumerate() {
            for (gid, g) in spec.guards.iter().enumerate() {
                s.parents[g.child].push((parent, gid));
            }
        }
        s.collide = collide;
        s.compile_influence();
        for id in 0..8 {
            s.ensure(id, g, index).unwrap();
        }
        s
    }
    struct Write {
        table: usize,
        column: Option<PublicationTask>,
    }
    fn tasks(g: &Graph, index: &mut QueryIndexes) -> Vec<Write> {
        g.changes
            .tables()
            .map(|(table, _)| Write {
                table,
                column: index.take_publication(table, g.query_versions[table]),
            })
            .collect()
    }
    fn restore(index: &mut QueryIndexes, tasks: Vec<Write>) {
        for task in tasks {
            if let Some(c) = task.column {
                index.restore_publication(c);
            }
        }
    }
    fn fill(g: &mut Graph, table: usize, base: i64) {
        for i in 0..128 {
            let key = if table == 1 {
                vec![Value::Int(i + 1000), Value::Int(i)]
            } else {
                vec![Value::Int(i), Value::Int(i + 1000)]
            };
            g.set_function(table, key, Value::Int(i + base)).unwrap();
        }
    }
    fn keys(s: &Summary) -> Vec<Vec<u64>> {
        let mut keys = s.keys.iter().map(<[u64]>::to_vec).collect::<Vec<_>>();
        keys.sort();
        keys
    }

    #[test]
    fn a_condition_waits_for_its_table_and_children_but_not_an_unrelated_table() {
        let mut g = graph();
        let mut index = crate::query::test_projection_indexes(64);
        index.track_changes = true;
        let mut s = fixture(&g, &mut index, false);
        for t in 0..3 {
            fill(&mut g, t, 2000);
        }
        let mut tasks = tasks(&g, &mut index);
        let ids: Vec<_> = tasks.iter().map(|t| (t.table, true)).collect();
        let rows: Vec<_> = tasks
            .iter()
            .map(|t| {
                g.changes
                    .tables()
                    .find(|(id, _)| *id == t.table)
                    .unwrap()
                    .1
                    .iter()
                    .map(|(&w, c)| (w, c.row(&g, w).unwrap()))
                    .collect::<Vec<_>>()
            })
            .collect();
        let versions = g.query_versions.clone();
        let (tx, rx) = mpsc::channel();
        let rx = Mutex::new(rx);
        let addresses: Vec<_> = s
            .states
            .iter()
            .map(|s| s as *const Summary as usize)
            .collect();
        let after = |id, state: &Summary| {
            assert_eq!(
                state as *const Summary as usize, addresses[id],
                "original Summary stays in place"
            );
            if id == 3 {
                tx.send(()).unwrap();
            }
        };
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(2)
            .build()
            .unwrap();
        assert!(s.publish_table_events_inner(
            &index,
            &ids,
            &mut tasks,
            Some(&pool),
            |t| {
                if t.table == 2 {
                    rx.lock()
                        .unwrap()
                        .recv_timeout(Duration::from_secs(5))
                        .unwrap();
                }
                let mut c = t.column.take().unwrap();
                for (w, row) in &rows[t.table] {
                    c.update(*w, row.as_ref());
                }
                c.finish(versions[t.table]);
                (Some(c), true)
            },
            &mut |t, c| t.column = c,
            Some(&after)
        ));
        assert_eq!(
            s.states[3].keys.len(),
            128,
            "both guards and actual own row are ready"
        );
        assert!(s.publication.work.table_events.early_nodes > 0);
        restore(&mut index, tasks);
        assert!(index.changes.is_empty());
    }

    #[test]
    fn empty_children_keep_existing_support_at_its_original_address() {
        let mut g = graph();
        let mut index = crate::query::test_projection_indexes(64);
        index.track_changes = true;
        let mut s = fixture(&g, &mut index, false);
        for table in 0..3 {
            fill(&mut g, table, 2000);
        }
        index.update(&mut g).unwrap();
        s.publish(&mut index);
        g.changes.clear();
        assert_eq!(s.states[0].keys.len(), 128);
        assert_eq!(s.states[7].keys.len(), 128);
        let addresses: Vec<_> = s
            .states
            .iter()
            .map(|s| s as *const Summary as usize)
            .collect();
        fill(&mut g, 0, 3000);
        let mut tasks = tasks(&g, &mut index);
        let ids: Vec<_> = tasks.iter().map(|t| (t.table, true)).collect();
        let rows: Vec<_> = g
            .changes
            .tables()
            .find(|(table, _)| *table == 0)
            .unwrap()
            .1
            .iter()
            .map(|(&w, c)| (w, c.row(&g, w).unwrap()))
            .collect();
        let version = g.query_versions[0];
        let after = |id, state: &Summary| {
            assert_eq!(state as *const Summary as usize, addresses[id]);
            if id == 0 {
                assert_eq!(
                    state.keys.len(),
                    128,
                    "empty completion must retain old support"
                );
            }
        };
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(4)
            .build()
            .unwrap();
        assert!(s.publish_table_events_inner(
            &index,
            &ids,
            &mut tasks,
            Some(&pool),
            |t| {
                let mut c = t.column.take().unwrap();
                for (w, row) in &rows {
                    c.update(*w, row.as_ref());
                }
                c.finish(version);
                (Some(c), true)
            },
            &mut |t, c| t.column = c,
            Some(&after)
        ));
        assert_eq!(
            s.states[7].keys.len(),
            256,
            "parent reads the empty child's unchanged support"
        );
        assert_eq!(
            s.states[2].keys.len(),
            256,
            "parent also borrows its unaffected child"
        );
        let work = &s.publication.work.table_events;
        assert!(work.empty_nodes > 0 && work.unchanged_child_borrows > 0);
        assert_eq!(
            work.materialized_nodes + work.empty_nodes,
            work.completed_nodes
        );
        assert_eq!(work.summary_borrows, work.potential_nodes);
        restore(&mut index, tasks);
        assert!(index.changes.is_empty());
    }

    #[test]
    fn table_events_match_ordinary_publication_with_masks_retirement_and_collisions() {
        for workers in [1, 4] {
            for (bits, collide) in [(64, false), (0, false), (64, true)] {
                let pool = rayon::ThreadPoolBuilder::new()
                    .num_threads(workers)
                    .build()
                    .unwrap();
                let mut g = graph();
                let mut a = crate::query::test_projection_indexes(bits);
                a.track_changes = true;
                let mut b = crate::query::test_projection_indexes(bits);
                b.track_changes = true;
                let mut ordinary = fixture(&g, &mut a, collide);
                let mut fused = fixture(&g, &mut b, collide);
                for stage in 0..6 {
                    match stage {
                        0 => {
                            for t in 0..3 {
                                fill(&mut g, t, 2000);
                            }
                        }
                        1 => fill(&mut g, 0, 3000),
                        2 => {
                            g.hide(0, &[Value::Int(0), Value::Int(1000)], true).unwrap();
                            g.hide(1, &[Value::Int(1000), Value::Int(0)], true).unwrap();
                        }
                        3 => fill(&mut g, 1, 4000),
                        4 => fill(&mut g, 0, 5000),
                        _ => fill(&mut g, 2, 6000),
                    }
                    a.update(&mut g).unwrap();
                    ordinary.publish(&mut a);
                    let mut tasks = tasks(&g, &mut b);
                    let ids: Vec<_> = tasks
                        .iter()
                        .map(|t| (t.table, t.column.is_some()))
                        .collect();
                    // Owned row headers in this test only; production borrows the
                    // repaired Graph once through QueryReads, with no graph clone.
                    let rows: HashMap<_, _> = g
                        .changes
                        .tables()
                        .map(|(t, c)| {
                            (
                                t,
                                c.iter()
                                    .map(|(&w, c)| (w, c.row(&g, w).unwrap()))
                                    .collect::<Vec<_>>(),
                            )
                        })
                        .collect();
                    let versions = g.query_versions.clone();
                    assert!(fused.publish_table_events(
                        &b,
                        &ids,
                        &mut tasks,
                        Some(&pool),
                        |t| {
                            let mut c = t.column.take().unwrap();
                            for (w, row) in &rows[&t.table] {
                                c.update(*w, row.as_ref());
                            }
                            c.finish(versions[t.table]);
                            (Some(c), true)
                        },
                        |t, c| t.column = c
                    ));
                    restore(&mut b, tasks);
                    for (id, (x, y)) in ordinary.states.iter().zip(&fused.states).enumerate() {
                        assert_eq!(
                            keys(x),
                            keys(y),
                            "node {id} stage {stage} workers {workers} bits {bits}"
                        );
                        assert_eq!(x.built, y.built);
                    }
                    assert!(b.changes.is_empty());
                    assert!(fused.publication.inputs.iter().all(Vec::is_empty));
                    if stage == 3 {
                        ordinary.ensure(8, &g, &mut a).unwrap();
                        fused.ensure(8, &g, &mut b).unwrap();
                    }
                    g.changes.clear();
                }
                assert_eq!(ordinary.stats.added_keys, fused.stats.added_keys);
                assert_eq!(ordinary.stats.update_rows, fused.stats.update_rows);
                assert_eq!(ordinary.stats.column_checks, fused.stats.column_checks);
            }
        }
    }

    #[test]
    fn a_failed_table_never_releases_its_readers_and_discards_speculative_caches() {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(4)
            .build()
            .unwrap();
        for pool in [None, Some(&pool)] {
            let mut g = graph();
            let mut index = crate::query::test_projection_indexes(64);
            index.track_changes = true;
            let mut s = fixture(&g, &mut index, false);
            for t in 0..3 {
                fill(&mut g, t, 2000);
            }
            let mut tasks = tasks(&g, &mut index);
            let ids: Vec<_> = tasks.iter().map(|t| (t.table, true)).collect();
            let rows: HashMap<_, _> = g
                .changes
                .tables()
                .map(|(t, c)| {
                    (
                        t,
                        c.iter()
                            .map(|(&w, c)| (w, c.row(&g, w).unwrap()))
                            .collect::<Vec<_>>(),
                    )
                })
                .collect();
            let versions = g.query_versions.clone();
            let after =
                |id, _: &Summary| assert_ne!(id, 5, "failed table must not release its condition");
            assert!(s.publish_table_events_inner(
                &index,
                &ids,
                &mut tasks,
                pool,
                |t| {
                    let mut c = t.column.take().unwrap();
                    for (w, row) in &rows[&t.table] {
                        c.update(*w, row.as_ref());
                    }
                    c.finish(versions[t.table]);
                    (Some(c), t.table != 2)
                },
                &mut |t, c| t.column = c,
                Some(&after)
            ));
            assert!(s.states.iter().all(|s| !s.built && s.keys.is_empty()));
            assert_eq!(s.publication.work.table_events.failed_batches, 1);
            assert!(s.publication.work.table_events.discarded_nodes > 0);
            restore(&mut index, tasks);
            assert!(
                !index.changes.is_empty(),
                "error retains source notifications"
            );
            for id in 0..8 {
                s.ensure(id, &g, &mut index).unwrap();
            }
            assert_eq!(
                s.states[3].keys.len(),
                128,
                "lazy recovery reads actual current graph"
            );
        }
    }

    #[test]
    fn an_unproved_disconnected_guard_leaves_task_ownership_untouched() {
        let g = graph();
        let mut index = crate::query::test_projection_indexes(64);
        index.track_changes = true;
        let mut s = fixture(&g, &mut index, false);
        s.specs[7].guards = vec![Guard {
            cols: vec![],
            child: 6,
        }];
        let mut tasks = vec![7];
        assert!(!s.publish_table_events(
            &index,
            &[(0, true)],
            &mut tasks,
            None,
            |_| panic!("unproved task must not run"),
            |_, _| panic!("nothing to restore")
        ));
        assert_eq!(tasks, [7]);
    }
}

impl Sieve {
    /// `run` moves only the completed original column owner out of its table
    /// task. `restore` puts that same owner back after all its readers finish.
    /// False means no task ran: use the ordinary publication path.
    pub(crate) fn publish_table_events<T: Send>(
        &mut self,
        index: &QueryIndexes,
        ids: &[(usize, bool)],
        tasks: &mut [T],
        pool: Option<&rayon::ThreadPool>,
        run: impl Fn(&mut T) -> (Option<PublicationTask>, bool) + Sync,
        mut restore: impl FnMut(&mut T, Option<PublicationTask>),
    ) -> bool {
        self.publish_table_events_inner(
            index,
            ids,
            tasks,
            pool,
            run,
            &mut restore,
            #[cfg(test)]
            None,
        )
    }
    fn publish_table_events_inner<T: Send>(
        &mut self,
        index: &QueryIndexes,
        ids: &[(usize, bool)],
        tasks: &mut [T],
        pool: Option<&rayon::ThreadPool>,
        run: impl Fn(&mut T) -> (Option<PublicationTask>, bool) + Sync,
        restore: &mut impl FnMut(&mut T, Option<PublicationTask>),
        #[cfg(test)] after: Option<&(dyn Fn(usize, &Summary) + Sync)>,
    ) -> bool {
        self.publication.work.table_events.attempts += 1;
        if !self.enabled
            || !index.changes.is_empty()
            || !ids.iter().any(|&(t, c)| c && self.by_table[t].built > 0)
        {
            self.publication.work.table_events.unavailable += 1;
            return false;
        }
        let clock = Instant::now();
        if !self.publication.compiled {
            let work = std::mem::take(&mut self.publication.work);
            self.publication = State::compile(&self.specs, &self.by_table);
            self.publication.work = work;
        }
        if !self.publication.valid {
            self.publication.work.table_events.unavailable += 1;
            return false;
        }
        assert_eq!(tasks.len(), ids.len());
        let plan = &mut self.publication;
        let mut positions = vec![usize::MAX; self.specs.len()];
        let mut affected = Vec::new();
        let mut table_positions = vec![usize::MAX; self.by_table.len()];
        let mut inputs = Vec::with_capacity(ids.len());
        for (p, &(table, column)) in ids.iter().enumerate() {
            if column {
                assert_eq!(table_positions[table], usize::MAX);
                table_positions[table] = p;
                for &id in &self.by_table[table].members {
                    if self.states[id].built && positions[id] == usize::MAX {
                        positions[id] = affected.len();
                        affected.push(id);
                    }
                }
            }
            let groups = (0..if column {
                self.by_table[table].groups.len()
            } else {
                0
            })
                .map(|i| std::mem::take(&mut plan.inputs[plan.table_groups[table] + i]))
                .collect();
            inputs.push(Mutex::new(Some(Inputs {
                groups,
                ..Inputs::default()
            })));
        }
        let mut head = 0;
        while head < affected.len() {
            for &(parent, _) in &self.parents[affected[head]] {
                if self.states[parent].built && positions[parent] == usize::MAX {
                    positions[parent] = affected.len();
                    affected.push(parent);
                }
            }
            head += 1;
        }
        let mut remaining = Vec::with_capacity(affected.len());
        let mut roots = Vec::new();
        for (p, &id) in affected.iter().enumerate() {
            let spec = &self.specs[id];
            let edges = spec
                .guards
                .iter()
                .filter(|g| positions[g.child] != usize::MAX)
                .count();
            let dependencies = edges + usize::from(table_positions[spec.table] != usize::MAX);
            plan.work.event_edges += edges as u64;
            if dependencies == 0 {
                roots.push(p);
            }
            remaining.push(AtomicUsize::new(dependencies));
        }
        // Partition only the affected states and their actual guard inputs.
        // Their addresses remain in the existing Summary array. The source
        // creates borrowed handles, never moves out/reinstalls Summary values.
        let mut required = affected.clone();
        for &id in &affected {
            for guard in &self.specs[id].guards {
                if positions[guard.child] == usize::MAX {
                    positions[guard.child] = usize::MAX - 1;
                    required.push(guard.child);
                }
            }
        }
        let mut partition_comparisons = 0;
        required.sort_unstable_by(|a, b| {
            partition_comparisons += 1;
            a.cmp(b)
        });
        let partition_steps = required.len();
        let partition_bytes = required.capacity() * std::mem::size_of::<usize>();
        let mut owners: Vec<_> = (0..affected.len()).map(|_| Mutex::new(None)).collect();
        let mut unchanged = Vec::with_capacity(required.len() - affected.len());
        let mut tail = self.states.as_mut_slice();
        let mut next = 0;
        for &id in &required {
            let (_, suffix) = tail.split_at_mut(id - next);
            let (state, suffix) = suffix.split_first_mut().unwrap();
            tail = suffix;
            next = id + 1;
            let p = positions[id];
            if p < affected.len() {
                *owners[p].get_mut().unwrap() = Some(state);
            } else {
                positions[id] = affected.len() + unchanged.len();
                unchanged.push(&*state);
            }
        }
        drop(required);
        let child_borrows = unchanged.len();
        let events = Events {
            specs: &self.specs,
            parents: &self.parents,
            dispatch: &self.by_table,
            group: &plan.group,
            table_groups: &plan.table_groups,
            unchanged,
            index,
            collide: self.collide,
            positions,
            table_positions,
            table_ids: ids,
            node_ids: &affected,
            owners,
            remaining,
            inputs,
            finished: (0..affected.len()).map(|_| OnceLock::new()).collect(),
            tables: (0..ids.len()).map(|_| OnceLock::new()).collect(),
            unfinished_tables: AtomicUsize::new(ids.len()),
            early: AtomicUsize::new(0),
            early_work: AtomicUsize::new(0),
            empty: AtomicUsize::new(0),
            #[cfg(test)]
            after,
        };
        let owner_bytes =
            events.owners.capacity() * std::mem::size_of::<Mutex<Option<&mut Summary>>>();
        let result_bytes =
            events.finished.capacity() * std::mem::size_of::<OnceLock<Finished<'_>>>();
        let header_bytes = owner_bytes
            + result_bytes
            + partition_bytes
            + events.unchanged.capacity() * std::mem::size_of::<&Summary>()
            + events.tables.capacity() * std::mem::size_of::<OnceLock<Table>>()
            + events.inputs.capacity() * std::mem::size_of::<Mutex<Option<Inputs>>>()
            + events.remaining.capacity() * std::mem::size_of::<AtomicUsize>()
            + (events.positions.capacity()
                + events.table_positions.capacity()
                + affected.capacity()
                + roots.capacity())
                * std::mem::size_of::<usize>();
        plan.work.prepare_seconds += clock.elapsed().as_secs_f64();
        let clock = Instant::now();
        if let Some(pool) = pool {
            pool.scope(|scope| {
                let events = &events;
                let run = &run;
                for &p in &roots {
                    events.ready(p, Some(scope));
                }
                for (p, task) in tasks.iter_mut().enumerate() {
                    scope.spawn(move |scope| {
                        let (column, ok) = run(task);
                        events.table_complete(p, column, ok, Some(scope));
                    });
                }
            });
        } else {
            for p in roots {
                events.ready(p, None);
            }
            for (p, task) in tasks.iter_mut().enumerate() {
                let (column, ok) = run(task);
                events.table_complete(p, column, ok, None);
            }
        }
        plan.work.execute_seconds += clock.elapsed().as_secs_f64();
        let clock = Instant::now();
        let success = events
            .tables
            .iter()
            .all(|t| t.get().expect("finished table").ok);
        let early = events.early.load(Ordering::Relaxed) as u64;
        let early_work = events.early_work.load(Ordering::Relaxed) as u64;
        let empty = events.empty.load(Ordering::Relaxed) as u64;
        let Events {
            owners,
            unchanged,
            finished,
            tables,
            ..
        } = events;
        drop(owners);
        drop(unchanged);
        let work = &mut plan.work;
        work.enabled = true;
        work.attempts += 1;
        work.batches += 1;
        work.event_nodes += affected.len() as u64;
        work.event_header_bytes += header_bytes as u64;
        let workers = pool.map_or(1, rayon::ThreadPool::current_num_threads);
        work.worker_tasks.resize(workers, 0);
        work.worker_rows.resize(workers, 0);
        work.worker_seconds.resize(workers, 0.0);
        work.table_events.batches += 1;
        work.table_events.shared_pool_calls += u64::from(pool.is_some());
        work.table_events.table_events += ids.len() as u64;
        work.table_events.potential_nodes += affected.len() as u64;
        work.table_events.header_bytes += header_bytes as u64;
        work.table_events.early_nodes += early;
        work.table_events.early_work_nodes += early_work;
        work.table_events.empty_nodes += empty;
        work.table_events.failed_batches += u64::from(!success);
        work.table_events.summary_borrows += affected.len() as u64;
        work.table_events.unchanged_child_borrows += child_borrows as u64;
        work.table_events.partition_steps += partition_steps as u64;
        work.table_events.partition_comparisons += partition_comparisons;
        work.table_events.owner_header_bytes += owner_bytes as u64;
        work.table_events.result_header_bytes += result_bytes as u64;
        for slot in finished {
            if let Some(done) = slot.into_inner() {
                work.table_events.completed_nodes += 1;
                work.table_events.discarded_nodes += u64::from(!success);
                work.tasks += 1;
                let Finished::Executed(n) = done else {
                    work.inline_tasks += 1;
                    work.event_empty_nodes += 1;
                    continue;
                };
                work.table_events.materialized_nodes += 1;
                work.direct_rows += n.direct;
                work.dependency_rows += n.dependencies;
                work.candidate_visits += n.visits;
                work.added_keys += n.added.len() as u64;
                work.prepared_columns += n.columns;
                work.event_empty_nodes += u64::from(n.direct == 0 && n.dependencies == 0);
                if let Some(w) = n.worker {
                    work.worker_tasks[w] += 1;
                    work.worker_rows[w] += n.direct + n.dependencies;
                    work.worker_seconds[w] += n.seconds;
                } else {
                    work.inline_tasks += 1;
                }
                if success {
                    self.stats.update_rows += n.direct;
                    self.stats.dependency_rows += n.dependencies;
                    self.stats.added_keys += n.added.len() as u64;
                }
            } else {
                assert!(!success);
            }
        }
        for ((slot, task), &(table, _)) in tables.into_iter().zip(tasks).zip(ids) {
            let mut done = slot.into_inner().unwrap();
            let stats = &done.inputs;
            if success {
                self.stats.publication_dispatches += stats.dispatches;
                self.stats.inactive_publications += stats.inactive;
                self.stats.column_checks += stats.column_checks;
                self.stats.unchanged_column_rows += stats.skipped;
                if let Some(c) = &mut done.column {
                    work.table_events.change_handoff_rows_avoided += c.changes().len() as u64;
                    c.clear_changes();
                }
            }
            work.borrowed_rows += stats.rows;
            work.group_headers += stats.headers;
            work.table_events.group_growth_bytes += stats.growth_bytes;
            work.table_events.group_header_bytes +=
                (done.inputs.groups.capacity() * std::mem::size_of::<Vec<usize>>()) as u64;
            work.table_events.group_capacity_bytes +=
                (done.inputs.groups.capacity() * std::mem::size_of::<Vec<usize>>()) as u64;
            for (i, mut group) in done.inputs.groups.into_iter().enumerate() {
                work.table_events.group_capacity_bytes +=
                    (group.capacity() * std::mem::size_of::<usize>()) as u64;
                group.clear();
                plan.inputs[plan.table_groups[table] + i] = group;
            }
            restore(task, done.column);
        }
        work.restore_seconds += clock.elapsed().as_secs_f64();
        plan.work.peak_scratch_bytes = plan
            .work
            .peak_scratch_bytes
            .max(plan.scratch_bytes() as u64);
        // A failed table never releases its readers. Successful speculative
        // condition additions are only caches; invalidate them on the error
        // path instead of copying Summary/indices to provide rollback.
        if !success {
            self.invalidate();
        }
        true
    }
}
