use rustc_hash::FxHashMap as Map;
use smallvec::SmallVec;

#[derive(Default, serde::Serialize)]
struct DeltaWork {
    batches: u64,
    lanes: u64,
    mask_ns: u64,
    publication_ns: u64,
    audited_ports: u64,
    audited_pivot_hits: u64,
    examined: u64,
    missing: u64,
    stale: u64,
    scalar_fresh_old_pivot: u64,
    pivot_reads: u64,
    pivot_hits: u64,
    point_uses: u64,
    point_lookups: u64,
    same_version_hits: u64,
    changed_generation_refreshes: u64,
    prior_missing_rechecks: u64,
    changed_handle_misses: u64,
    cross_run_reuses: u64,
    per_batch_reuses: u64,
    scalar_slots_created: u64,
    publications: u64,
    change_rows: u64,
    pivot_invalidations: u64,
    incomplete_journals: u64,
    pivot_full_resets: u64,
    union_resets: u64,
    capacity_resets: u64,
    peak_entries: usize,
}
struct CachedPivot {
    epoch: u64,
    ports: SmallVec<[usize; 2]>,
}
struct EpochSlot {
    table: usize,
    key: u64,
    generation: Option<u64>,
    positive: Option<(usize, u64)>,
    last_batch: u64,
    last_run: u64,
}
#[derive(Default)]
struct DeltaFrontier {
    profile: bool,
    audit: bool,
    enabled: bool,
    ready: bool,
    unions: u64,
    pivots: Vec<Map<Dependency, CachedPivot>>,
    users: Vec<Vec<usize>>,
    versions: Vec<u64>,
    scalar_keys: Map<(usize, u64), usize>,
    slots: Vec<EpochSlot>,
    cached_pivots: usize,
    stats: DeltaWork,
}
const DELTA_CAP: usize = 131_072;
impl DeltaFrontier {
    fn layout(&self) -> J {
        json!({"active_pivots":self.cached_pivots,"active_keys":self.slots.len(),
          "pivot_map_capacity":self.pivots.iter().map(Map::capacity).sum::<usize>(),"key_map_capacity":self.scalar_keys.capacity(),
          "key_slot_capacity":self.slots.capacity(),"key_slot_bytes":std::mem::size_of::<EpochSlot>(),
          "cached_pivot_bytes":std::mem::size_of::<CachedPivot>()})
    }
    fn prepare(&mut self, g: &Graph, plans: &[Option<ScalarPlan>]) {
        if self.ready {
            return;
        }
        self.pivots.resize_with(plans.len(), Default::default);
        self.users.resize_with(g.program.tables.len(), Vec::new);
        for (rule, plan) in plans.iter().enumerate() {
            if let Some(p) = plan {
                self.users[p.pivot_table].push(rule)
            }
        }
        self.versions = g.query_versions.clone();
        self.unions = g.stats.unions;
        self.ready = true;
    }
    fn reset(&mut self, g: &Graph) {
        self.pivots.iter_mut().for_each(Map::clear);
        self.cached_pivots = 0;
        self.slots.clear();
        self.scalar_keys.clear();
        self.versions.clone_from(&g.query_versions);
        self.unions = g.stats.unions;
    }
    fn reset_pivots(&mut self, table: usize) {
        for &r in &self.users[table] {
            self.cached_pivots -= self.pivots[r].len();
            self.pivots[r].clear()
        }
        self.stats.pivot_full_resets += 1;
    }
    fn sync_union(&mut self, g: &Graph) {
        if self.unions != g.stats.unions {
            self.reset(g);
            self.stats.union_resets += 1;
        }
    }
    fn publish(&mut self, g: &Graph) {
        if !self.ready {
            return;
        }
        self.stats.publications += 1;
        self.sync_union(g);
        for (t, changes) in g.changes.tables() {
            if self.users[t].is_empty() || self.versions[t] == g.query_versions[t] {
                continue;
            }
            let delta = g.query_versions[t].checked_sub(self.versions[t]);
            if delta != Some(changes.len() as u64) {
                self.stats.incomplete_journals += 1;
                self.reset_pivots(t);
            } else {
                self.stats.change_rows += changes.len() as u64;
                for w in changes.keys() {
                    for &r in &self.users[t] {
                        if self.pivots[r].remove(w).is_some() {
                            self.cached_pivots -= 1;
                            self.stats.pivot_invalidations += 1
                        }
                    }
                }
            }
            self.versions[t] = g.query_versions[t];
        }
    }
    fn intern(&mut self, table: usize, key: u64) -> usize {
        if let Some(i) = self.scalar_keys.get(&(table, key)) {
            return *i;
        }
        let i = self.slots.len();
        self.scalar_keys.insert((table, key), i);
        self.slots.push(EpochSlot {
            table,
            key,
            generation: None,
            positive: None,
            last_batch: 0,
            last_run: 0,
        });
        self.stats.scalar_slots_created += 1;
        i
    }
    fn current(g: &Graph, slot: &mut EpochSlot, stats: &mut DeltaWork) -> Result<Option<u64>> {
        let version = g.query_versions[slot.table];
        stats.point_uses += 1;
        if slot.generation == Some(version) {
            stats.same_version_hits += 1;
            if slot.last_batch == stats.batches {
                stats.per_batch_reuses += 1
            } else if slot.last_run != g.epoch {
                stats.cross_run_reuses += 1
            }
        } else {
            let found = slot
                .positive
                .and_then(|(i, _)| g.current_scalar_at(slot.table, slot.key, i).map(|e| (i, e)));
            if found.is_some() {
                stats.changed_generation_refreshes += 1
            } else {
                if slot.generation.is_some() {
                    if slot.positive.is_some() {
                        stats.changed_handle_misses += 1
                    } else {
                        stats.prior_missing_rechecks += 1
                    }
                }
                stats.point_lookups += 1;
            }
            slot.positive = match found {
                Some(pair) => Some(pair),
                None => g.delta_scalar_lookup(slot.table, slot.key)?,
            };
            slot.generation = Some(version);
        }
        slot.last_batch = stats.batches;
        slot.last_run = g.epoch;
        Ok(slot.positive.map(|(_, e)| e))
    }
    fn mask(
        &mut self,
        g: &Graph,
        plans: &[Option<ScalarPlan>],
        rid: usize,
        sources: &[SourceHeader],
        wm: u64,
    ) -> Result<Vec<u8>> {
        let Some(plan) = &plans[rid] else {
            return Ok(Vec::new());
        };
        if plan.points.len() >= DELTA_CAP
            || plan
                .points
                .iter()
                .any(|(t, _)| !g.supports_delta_scalar(*t))
        {
            return Ok(Vec::new());
        }
        self.prepare(g, plans);
        self.sync_union(g);
        if self.versions[plan.pivot_table] != g.query_versions[plan.pivot_table] {
            self.reset_pivots(plan.pivot_table);
            self.versions[plan.pivot_table] = g.query_versions[plan.pivot_table];
        }
        self.stats.batches += 1;
        self.stats.lanes += sources.len() as u64;
        let mut mask = Vec::with_capacity(sources.len());
        for h in sources {
            if self.cached_pivots + self.slots.len() + plan.points.len() + 1 > DELTA_CAP {
                self.reset(g);
                self.stats.capacity_resets += 1;
            }
            let Some(w) = h.source else {
                mask.push(0);
                continue;
            };
            if self.pivots[rid]
                .get(&w)
                .is_some_and(|p| p.epoch == h.version)
            {
                self.stats.pivot_hits += 1;
                if self.audit {
                    let row = g.row(w)?.ok_or("retained scalar pivot missing")?;
                    if row.hidden || row.epoch != h.version || row.table != plan.pivot_table {
                        return Err("retained scalar pivot version".into());
                    }
                    for (&port, &(table, col)) in
                        self.pivots[rid][&w].ports.iter().zip(&plan.points)
                    {
                        let slot = &self.slots[port];
                        if slot.table != table
                            || row.values.get(col).and_then(|v| g.delta_scalar_key(v))
                                != Some(slot.key)
                        {
                            return Err("retained projection disagrees with current pivot".into());
                        }
                    }
                    self.stats.audited_pivot_hits += 1;
                }
            } else {
                self.stats.pivot_reads += 1;
                let Some(row) = g.row(w)? else {
                    mask.push(0);
                    continue;
                };
                if row.hidden || row.table != plan.pivot_table || row.epoch != h.version {
                    mask.push(0);
                    continue;
                }
                let mut ports = SmallVec::new();
                for &(t, c) in &plan.points {
                    let Some(key) = row.values.get(c).and_then(|k| g.delta_scalar_key(k)) else {
                        break;
                    };
                    ports.push(self.intern(t, key))
                }
                if ports.len() != plan.points.len() {
                    mask.push(0);
                    continue;
                }
                if self.pivots[rid]
                    .insert(
                        w,
                        CachedPivot {
                            epoch: h.version,
                            ports,
                        },
                    )
                    .is_none()
                {
                    self.cached_pivots += 1
                }
                self.stats.peak_entries = self
                    .stats
                    .peak_entries
                    .max(self.cached_pivots + self.slots.len());
            }
            self.stats.examined += 1;
            let mut max_epoch = h.version;
            let mut missing = false;
            for &port in &self.pivots[rid][&w].ports {
                let slot = &mut self.slots[port];
                let known = Self::current(g, slot, &mut self.stats)?;
                if self.audit {
                    if known != g.single_scalar_epoch(slot.table, &Value::Eq(slot.key))? {
                        return Err("stale exact scalar epoch in delta frontier".into());
                    }
                    self.stats.audited_ports += 1;
                }
                match known {
                    Some(e) => max_epoch = max_epoch.max(e),
                    None => {
                        missing = true;
                        break;
                    }
                }
            }
            let reason = if missing {
                self.stats.missing += 1;
                1
            } else if max_epoch < wm {
                self.stats.stale += 1;
                2
            } else {
                self.stats.scalar_fresh_old_pivot += u64::from(h.version < wm);
                0
            };
            mask.push(reason);
        }
        Ok(mask)
    }
}
impl Trial {
    pub(crate) fn publish_scalar_frontier(&mut self, g: &Graph) {
        if self.rows.delta.enabled {
            let start = self.rows.delta.profile.then(std::time::Instant::now);
            self.rows.delta.publish(g);
            if let Some(start) = start {
                self.rows.delta.stats.publication_ns += start.elapsed().as_nanos() as u64
            }
        }
    }
}
