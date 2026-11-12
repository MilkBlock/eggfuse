//! The table owner updates the existing Shared Entries alongside its indexes.
//! No producer subscriptions or second Entry registry are built. Cold nodes
//! remain lazy; a sealed graph and exclusive states cover warm-node updates.
use super::*;
use crate::{change_batch::Change, graph::query_reads::QueryReads};

pub(crate) struct PublicationTask {
    nodes: Vec<(usize, std::sync::Arc<Node>, State)>,
    stats: Stats,
    pub row_reads: u64,
}
impl PublicationTask {
    fn update_node(
        node: &Node,
        state: &mut State,
        w: Dependency,
        row: Option<&Row>,
        parents: &crate::value::Parents,
        stats: &mut Stats,
    ) {
        let previous = state.rows.remove(&w).unwrap_or_default();
        let publication = previous.publication;
        let mut packet = previous.packet;
        if let Some(p) = &packet {
            state.remove_epoch(p.row.epoch, w);
        }
        let had_previous = packet.is_some();
        let Some(row) = row.filter(|r| r.table == node.table && !r.hidden) else {
            stats.retired_packets += u64::from(had_previous);
            return;
        };
        stats.predicate_checks += 1;
        if !node.checks.iter().all(|(col, check)| match check {
            Arg::Slot(other) => row.values[*other] == row.values[*col],
            Arg::Literal(v) => canon(v, parents) == row.values[*col],
        }) {
            stats.retired_packets += u64::from(had_previous);
            return;
        }
        let row = Packet::refresh_row(&mut packet, row.clone(), stats);
        state.insert_epoch(row.epoch, w);
        state.rows.insert(
            w,
            Stored {
                packet: Some(Packet { row }),
                publication,
            },
        );
        stats.worker_entry_updates += 1;
    }
    pub(crate) fn update(&mut self, w: Dependency, row: Option<&Row>, reads: &QueryReads<'_>) {
        for (_, node, state) in &mut self.nodes {
            Self::update_node(node, state, w, row, reads.parents, &mut self.stats);
        }
    }
    pub(crate) fn finish(
        &mut self,
        changes: &HashMap<Dependency, Change>,
        reads: &QueryReads<'_>,
    ) -> Result<()> {
        // A dormant consumer can have notifications from older Runs. Current
        // changes were handled by the table's single row read; finish only the
        // remaining old notifications against this same sealed graph.
        for (_, node, state) in &mut self.nodes {
            let mut pending = std::mem::take(&mut state.pending);
            pending.sort_unstable();
            pending.dedup();
            self.stats.node_notifications += pending.len() as u64;
            self.stats.node_refreshes += 1;
            for w in pending.drain(..) {
                if changes.contains_key(&w) {
                    continue;
                }
                let row = reads.row(w)?;
                self.row_reads += 1;
                Self::update_node(node, state, w, row.as_ref(), reads.parents, &mut self.stats);
            }
            state.pending = pending;
            state.sorted_pending = 0;
        }
        Ok(())
    }
}
impl Scheduler {
    pub(crate) fn has_publication_work(&self, table: usize) -> bool {
        self.enabled
            && self.plan.tables[table]
                .iter()
                .any(|&id| !self.states[id].cold && !self.states[id].pending.is_empty())
    }
    pub(crate) fn take_publication_work(&mut self, table: usize) -> Option<PublicationTask> {
        if !self.has_publication_work(table) {
            return None;
        }
        let nodes = self.plan.tables[table]
            .iter()
            .filter_map(|&id| {
                let state = &mut self.states[id];
                (!state.cold && !state.pending.is_empty())
                    .then(|| (id, self.plan.nodes[id].clone(), std::mem::take(state)))
            })
            .collect();
        Some(PublicationTask {
            nodes,
            stats: Stats::default(),
            row_reads: 0,
        })
    }
    pub(crate) fn restore_publication_work(
        &mut self,
        task: PublicationTask,
        worker: Option<usize>,
    ) {
        self.stats.owner_entry_tasks += 1;
        self.stats.owner_entry_nodes += task.nodes.len() as u64;
        self.stats.owner_entry_state_bytes += (task.nodes.capacity()
            * std::mem::size_of::<(usize, std::sync::Arc<Node>, State)>())
            as u64;
        self.stats.owner_entry_updates += task.stats.worker_entry_updates;
        self.stats.owner_entry_prior_reads += task.row_reads;
        if worker.is_some() {
            self.stats.worker_entry_tasks += 1;
            self.stats.worker_entry_updates += task.stats.worker_entry_updates;
        }
        self.stats.node_refreshes += task.stats.node_refreshes;
        self.stats.node_notifications += task.stats.node_notifications;
        self.stats.predicate_checks += task.stats.predicate_checks;
        self.stats.retired_packets += task.stats.retired_packets;
        self.stats.row_reuse_checks += task.stats.row_reuse_checks;
        self.stats.row_reuses += task.stats.row_reuses;
        self.stats.row_reuse_shared += task.stats.row_reuse_shared;
        for (id, _, state) in task.nodes {
            self.states[id] = state;
        }
    }
}
