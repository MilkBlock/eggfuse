// Original source readers and schedules are authoritative. Only the address part of a
// notification may be omitted when the installed complete matcher cannot read it.
#[derive(Default, serde::Serialize)]
struct ReaderWork {
    batches: u64,
    tables: u64,
    wakes: u64,
    logical_readers: u64,
    dirty_transitions: u64,
    pending_readers: u64,
    pending_attempts: u64,
    pending_added: u64,
    pending_omitted: u64,
    mask_words: u64,
    unique_wakes: u64,
    initial_pending: usize,
    retired_nodes: usize,
    removed_node_visits: u64,
    remaining_node_visits: u64,
    exclusive_single: usize,
    exclusive_multi: usize,
    by_origin: std::collections::BTreeMap<u32, u64>,
    origin_missing: u64,
    spine_kept: usize,
    // changed wake addresses, original rule fanout, pending attempts, omitted, actually added
    by_table: std::collections::BTreeMap<usize, [u64; 5]>,
}
struct ReaderPlan {
    mode: u8,
    detailed: bool,
    dedicated: Vec<bool>,
    external: Vec<Vec<usize>>,
    masks: Vec<Vec<(usize, u64)>>,
    words: Vec<u64>,
    stats: ReaderWork,
    nodes: Vec<(usize, usize)>,
}
impl Executor {
    pub fn install_publication_readers(&mut self, mode: u8, detailed: bool) -> Result<()> {
        if mode > 4 || !self.steps.is_empty() {
            return Err("reader contract must be installed before the first Run".into());
        }
        let mut stats = ReaderWork::default();
        let mut dedicated = vec![false; self.graph.program.rules.len()];
        let mut retire = dedicated.clone();
        let mut external = vec![Vec::new(); self.readers.len()];
        let mut masks = Vec::with_capacity(self.readers.len());
        let words = (dedicated.len() + 63) / 64;
        for rid in 0..dedicated.len() {
            let multi = crate::ordinary_witness::eligible(rid) == Some(false);
            let single = self
                .stage_spine
                .single
                .as_ref()
                .is_some_and(|s| s.accepts(rid) && !s.residual);
            dedicated[rid] = multi || single;
            stats.exclusive_multi += usize::from(multi);
            stats.exclusive_single += usize::from(!multi && single);
            let spine = self
                .stage_spine
                .can_read_future_entries(rid, self.graph.program.rules[rid].query.len());
            retire[rid] = dedicated[rid] && !spine;
            stats.spine_kept += usize::from(dedicated[rid] && spine);
            if dedicated[rid] {
                stats.initial_pending += self.pending[rid].len();
                if matches!(mode, 1 | 3 | 4) {
                    self.pending[rid].clear();
                }
            }
        }
        for (table, readers) in self.readers.iter().enumerate() {
            let mut bits = vec![0u64; words];
            for &r in readers {
                bits[r / 64] |= 1u64 << (r % 64);
                if !dedicated[r] && !self.entry_schedule.accepts(r) {
                    external[table].push(r);
                }
            }
            masks.push(
                bits.into_iter()
                    .enumerate()
                    .filter(|(_, v)| *v != 0)
                    .collect(),
            );
        }
        let before = self.entry_schedule.reader_fanout();
        if matches!(mode, 2 | 3 | 4) {
            stats.retired_nodes = self.entry_schedule.retire_dedicated(&retire);
        }
        let nodes = before
            .into_iter()
            .zip(self.entry_schedule.reader_fanout())
            .collect();
        self.notification_readers = Some(ReaderPlan {
            nodes,
            mode,
            detailed,
            dedicated,
            external,
            masks,
            words: vec![0; words],
            stats,
        });
        Ok(())
    }
    pub fn reader_report(&self) -> serde_json::Value {
        serde_json::json!({"reader":self.notification_readers.as_ref().map(|p|&p.stats),
            "publication":self.publication,"entry":self.entry_schedule.report(),
            "columns":{"builds":self.query_indexes.builds,"updated":self.query_indexes.updated_facts,
            "decoded":self.query_indexes.decoded_facts,"peak_refs":self.query_indexes.peak_references}})
    }
    fn deliver_with_plan(&mut self) {
        use crate::change_batch::Change;
        let plan = self.notification_readers.as_mut().unwrap();
        let batch = &self.graph.changes;
        self.graph.stats.delivery_events += batch.events;
        self.graph.stats.distinct_delivery_events += batch.distinct_events;
        let prune = matches!(plan.mode, 1 | 3 | 4);
        let masked = plan.mode == 4;
        if plan.detailed {
            plan.stats.batches += 1;
        }
        if masked {
            plan.words.fill(0);
        }
        for (t, changes) in batch.tables() {
            if plan.detailed {
                let (old, new) = plan.nodes[t];
                plan.stats.removed_node_visits += (old - new) as u64;
                plan.stats.remaining_node_visits += new as u64;
            }
            if !changes.values().any(|v| *v == Change::Wake) {
                continue;
            }
            #[cfg(feature = "rhs-work-audit")]
            for _ in &self.readers[t] {
                self.ledger.wake();
            }
            let wakes = if plan.detailed {
                changes.values().filter(|c| **c == Change::Wake).count() as u64
            } else {
                0
            };
            if plan.detailed {
                plan.stats.tables += 1;
                plan.stats.wakes += wakes;
                plan.stats.logical_readers += self.readers[t].len() as u64;
                let s = plan.stats.by_table.entry(t).or_default();
                s[0] += wakes;
                s[1] += self.readers[t].len() as u64;
            }
            if plan.detailed && plan.mode == 3 {
                let factor = self.readers[t]
                    .iter()
                    .filter(|&&r| plan.dedicated[r] && !self.entry_schedule.accepts(r))
                    .count() as u64;
                if factor > 0 {
                    for (&w, _) in changes.iter().filter(|(_, v)| **v == Change::Wake) {
                        if let Some(origin) = self.graph.origin(w) {
                            *plan.stats.by_origin.entry(origin.cell).or_default() += factor;
                        } else {
                            plan.stats.origin_missing += factor;
                        }
                    }
                }
            }
            if masked {
                for &(i, bits) in &plan.masks[t] {
                    plan.words[i] |= bits;
                }
                if plan.detailed {
                    plan.stats.mask_words += plan.masks[t].len() as u64;
                    for &rid in &self.readers[t] {
                        if plan.dedicated[rid] && !self.entry_schedule.accepts(rid) {
                            plan.stats.pending_omitted += wakes;
                            plan.stats.by_table.get_mut(&t).unwrap()[3] += wakes;
                        }
                    }
                }
            }
            let readers = if masked {
                &plan.external[t]
            } else {
                &self.readers[t]
            };
            for &rid in readers {
                if !masked && !self.dirty[rid] {
                    self.dirty[rid] = true;
                    if let Some(s) = &mut self.ready_sets {
                        s.wake(rid);
                    }
                    if plan.detailed {
                        plan.stats.dirty_transitions += 1;
                    }
                }
                if self.entry_schedule.accepts(rid) {
                    continue;
                }
                if prune && plan.dedicated[rid] {
                    if plan.detailed {
                        plan.stats.pending_omitted += wakes;
                        plan.stats.by_table.get_mut(&t).unwrap()[3] += wakes;
                    }
                    continue;
                }
                let before = if plan.detailed {
                    self.pending[rid].len()
                } else {
                    0
                };
                self.pending[rid].extend(
                    changes
                        .iter()
                        .filter_map(|(w, c)| (*c == Change::Wake).then_some(*w)),
                );
                if plan.detailed {
                    let added = (self.pending[rid].len() - before) as u64;
                    plan.stats.pending_readers += 1;
                    plan.stats.pending_attempts += wakes;
                    plan.stats.pending_added += added;
                    let s = plan.stats.by_table.get_mut(&t).unwrap();
                    s[2] += wakes;
                    s[4] += added;
                }
            }
        }
        if masked {
            for (i, &word) in plan.words.iter().enumerate() {
                let mut bits = word;
                if plan.detailed {
                    plan.stats.unique_wakes += u64::from(bits.count_ones());
                }
                while bits != 0 {
                    let n = bits.trailing_zeros() as usize;
                    bits &= bits - 1;
                    let rid = i * 64 + n;
                    if !self.dirty[rid] {
                        self.dirty[rid] = true;
                        if let Some(s) = &mut self.ready_sets {
                            s.wake(rid);
                        }
                        if plan.detailed {
                            plan.stats.dirty_transitions += 1;
                        }
                    }
                }
            }
        }
    }
}
