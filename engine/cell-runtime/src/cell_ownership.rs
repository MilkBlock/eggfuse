//! Persistent, typed Cell ownership. Interior equality incidences have no
//! reverse subscriptions: native results route to their source Cell, and only
//! foreign/escaped roots name an owner boundary. Owners contain forward bodies.
use super::*;
use std::cell::Cell as Counter;
use std::rc::Rc;

#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Plan {
    pub tables: Vec<bool>,
    pub markers: Vec<Marker>,
    pub entries: Vec<Vec<usize>>,
    /// Shared publication table -> scheduled typed entry ports. Producer body
    /// operations reference these same table IDs; routes are shared, not
    /// expanded into a separate per-producer/per-consumer dependency graph.
    pub routes: Vec<Vec<(usize, usize)>>,
    pub max_continuation_facts: usize,
}
#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Marker {
    pub active: bool,
    pub bodies: Vec<bool>,
    pub unions: Vec<usize>,
}
impl Plan {
    pub(crate) fn derive(p: &Program) -> Result<Self> {
        let tables = p
            .repair_ports
            .key_eq_columns
            .iter()
            .map(Option::is_some)
            .collect::<Vec<_>>();
        let markers = p
            .templates
            .iter()
            .map(|t| Marker {
                active: t.ops.iter().any(|op|matches!(op,Op::Let(_,Call::Table(table),_)|Op::Set(table,_,_) if tables[*table])),
                bodies: t
                    .ops
                    .iter()
                    .map(|op| matches!(op, Op::Let(_,Call::Table(table),_) | Op::Set(table,_,_) if tables[*table]))
                    .collect(),
                unions: t
                    .ops
                    .iter()
                    .enumerate()
                    .filter_map(|(i, op)| matches!(op, Op::Union(..)).then_some(i))
                    .collect(),
            })
            .collect();
        let entries = p
            .rules
            .iter()
            .map(|r| {
                r.query
                    .iter()
                    .enumerate()
                    .filter_map(|(i, a)| matches!(a.call,Call::Table(t) if tables[t]).then_some(i))
                    .collect()
            })
            .collect();
        let mut routes = vec![vec![]; p.tables.len()];
        for (rid, r) in p.rules.iter().enumerate() {
            for (atom, a) in r.query.iter().enumerate() {
                if let Call::Table(t) = a.call
                    && tables[t]
                {
                    routes[t].push((rid, atom));
                }
            }
        }
        let plan = Self {
            tables,
            markers,
            entries,
            routes,
            max_continuation_facts: 256,
        };
        if let Some(raw) = p.artifact.get("ownership_markers") {
            if *raw != plan.artifact(p) {
                return Err("ownership marker differs from typed entry/body wiring".into());
            }
        }
        Ok(plan)
    }
    pub fn artifact(&self, p: &Program) -> J {
        json!({"schema":"eggfuse-ownership-markers/v1", "recipe":p.artifact["recipe"]["sha256"],
            "entry_schedule":crate::checksum::artifact_digest(&p.artifact["entry_schedule"]),"plan":self,
            "contract":"checked scheduled bindings enter persistent scalar constructor owners; foreign roots are boundaries; no future union is assumed"})
    }
}
#[derive(Default, Serialize)]
struct Stats {
    marker_entries: u64,
    marker_anchor_reads: u64,
    marker_continuations: u64,
    cross_stage_continuations: u64,
    capacity_splits: u64,
    owners_created: u64,
    owners_retired: u64,
    owners_live: u64,
    owned_births: u64,
    adopted_existing: u64,
    owned_retirements: u64,
    owned_live: u64,
    internal_ports_seen: u64,
    boundary_ports_seen: u64,
    boundary_insert_attempts: u64,
    boundary_edges_created: u64,
    boundary_edges_removed: u64,
    boundary_live: u64,
    boundary_probes: u64,
    native_owner_routes: u64,
    boundary_owner_routes: u64,
    owner_visits: u64,
    body_visits: u64,
    port_checks: u64,
    row_copies: u64,
    result_publications: u64,
    key_enqueues: u64,
    key_completions: u64,
    boundary_rebuilds: u64,
    boundary_body_reads: u64,
    stage_barriers: u64,
    carried_facts: u64,
    carried_owners: u64,
    unbound_query_calls: Counter<u64>,
    unbound_query_rows: Counter<u64>,
    retired_result_boundaries: u64,
    domain_queries: Counter<u64>,
    domain_owner_visits: Counter<u64>,
    domain_body_visits: Counter<u64>,
    domain_legacy_visits: Counter<u64>,
    domain_results: Counter<u64>,
    uncovered_births: u64,
}
struct Owner {
    facts: BTreeSet<FactRef>,
    boundaries: BTreeSet<u64>,
    last_epoch: u64,
}
#[derive(Serialize)]
struct Barrier {
    epoch: u64,
    live_facts: u64,
    live_owners: u64,
    boundary_edges: u64,
    legacy_reverse_edges: u64,
    key_completions: u64,
    result_publications: u64,
    body_visits: u64,
}
pub(super) struct Runtime {
    owners: Vec<Option<Owner>>,
    boundaries: HashMap<u64, BTreeSet<u32>>,
    refresh: BTreeSet<u32>,
    pending: BTreeSet<FactRef>,
    pub(super) tables: Vec<usize>,
    entry: Option<u32>,
    stats: Stats,
    barriers: Vec<Barrier>,
}
impl Graph {
    pub fn ownership_enabled(&self) -> bool {
        self.ownership.is_some()
    }
    pub(super) fn ownership_settled(&self) -> bool {
        self.ownership
            .as_ref()
            .is_none_or(|m| m.pending.is_empty() && m.refresh.is_empty())
    }
    pub fn new_with_cell_ownership(p: Program) -> Result<Self> {
        let mut g = Self::new_with_repair_ports(p)?;
        g.use_cell_ownership()?;
        Ok(g)
    }
    pub fn use_cell_ownership(&mut self) -> Result<()> {
        if self.ownership.is_some() {
            return Ok(());
        }
        if self.local_unions.is_some() || self.union_digest.is_some() || {
            #[cfg(feature = "spine-blocks")]
            {
                self.repair_cells.is_some()
            }
            #[cfg(not(feature = "spine-blocks"))]
            {
                false
            }
        } {
            return Err(
                "persistent Cell ownership requires its own ordered completion backend".into(),
            );
        }
        self.ownership = Some(Runtime {
            owners: vec![],
            boundaries: HashMap::default(),
            refresh: BTreeSet::new(),
            pending: BTreeSet::new(),
            tables: vec![0; self.program.tables.len()],
            entry: None,
            stats: Stats::default(),
            barriers: vec![],
        });
        // Import is already settled. Adopt existing covered bodies, rather than
        // limiting ownership to rows born after activation.
        let facts = (0..self.program.tables.len())
            .flat_map(|t| self.witnesses(t))
            .filter_map(|w| {
                if let Dependency::Fact(f) = w {
                    Some(f)
                } else {
                    None
                }
            })
            .collect::<Vec<_>>();
        for f in facts {
            let Some(row) = self.fact(f)? else { continue };
            if !self.program.cell_ownership.tables[row.table] {
                continue;
            }
            let owner = self.ensure_cell_owner(f.cell);
            self.subscribe_edges(Dependency::Fact(f), &[]);
            self.dependencies.remove(&Dependency::Fact(f));
            self.cells
                .get_mut(&f.cell)
                .unwrap()
                .facts
                .get_mut(&f.op)
                .unwrap()
                .owned_owner = Some(owner);
            self.cells
                .get_mut(&f.cell)
                .unwrap()
                .facts
                .get_mut(&f.op)
                .unwrap()
                .owned = true;
            self.cells
                .get_mut(&f.cell)
                .unwrap()
                .facts
                .get_mut(&f.op)
                .unwrap()
                .decoded = Some((row.table, row.values));
            let m = self.ownership.as_mut().unwrap();
            m.owners[owner as usize].as_mut().unwrap().facts.insert(f);
            m.tables[row.table] += 1;
            m.stats.adopted_existing += 1;
            m.stats.owned_live += 1;
            m.refresh.insert(owner);
        }
        self.settle_owned_boundaries()?;
        Ok(())
    }
    fn ensure_cell_owner(&mut self, cell: u32) -> u32 {
        let inherited = self.cells[&cell].owner;
        let m = self.ownership.as_mut().unwrap();
        if let Some(id) = inherited
            && m.owners.get(id as usize).is_some_and(Option::is_some)
        {
            if m.owners[id as usize].as_ref().unwrap().facts.len()
                < self.program.cell_ownership.max_continuation_facts
            {
                return id;
            }
            m.stats.capacity_splits += 1;
        }
        let id = u32::try_from(m.owners.len()).expect("Cell owner capacity");
        m.owners.push(Some(Owner {
            facts: BTreeSet::new(),
            boundaries: BTreeSet::new(),
            last_epoch: self.epoch,
        }));
        m.stats.owners_created += 1;
        m.stats.owners_live += 1;
        self.cells.get_mut(&cell).unwrap().owner = Some(id);
        id
    }
    pub(crate) fn owner_entry(&self) -> Option<u32> {
        self.ownership.as_ref().and_then(|m| m.entry)
    }
    pub(crate) fn begin_owner_entry(
        &mut self,
        rid: usize,
        anchors: impl Iterator<Item = Option<Dependency>>,
    ) {
        let Some(m) = &mut self.ownership else { return };
        m.entry = None;
        m.stats.marker_entries += 1;
        for w in anchors.flatten() {
            m.stats.marker_anchor_reads += 1;
            let Dependency::Fact(f) = w else { continue };
            let Some(c) = self.cells.get(&f.cell) else {
                continue;
            };
            if !c.facts.get(&f.op).is_some_and(|s| s.owned) {
                continue;
            }
            let Some(owner) = c.facts[&f.op].owned_owner else {
                continue;
            };
            let Some(o) = m.owners[owner as usize].as_mut() else {
                continue;
            };
            if o.facts.len() >= self.program.cell_ownership.max_continuation_facts {
                m.stats.capacity_splits += 1;
                continue;
            }
            m.stats.marker_continuations += 1;
            m.stats.cross_stage_continuations += u64::from(o.last_epoch != self.epoch);
            o.last_epoch = self.epoch;
            m.entry = Some(owner);
            break;
        }
        let _ = rid; // The caller supplies only this marker's compiled entry ports.
    }
    pub(crate) fn end_owner_entry(&mut self) {
        if let Some(m) = &mut self.ownership {
            m.entry = None;
        }
    }
    pub(super) fn owns_birth(&mut self, f: FactRef) -> bool {
        if self.ownership.is_none() {
            return false;
        }
        let template = self.cells[&f.cell].template;
        if !self.program.cell_ownership.markers[template].bodies[f.op as usize] {
            self.ownership.as_mut().unwrap().stats.uncovered_births += 1;
            return false;
        }
        self.ensure_cell_owner(f.cell);
        true
    }
    pub(super) fn publish_owned_birth(&mut self, f: FactRef, t: usize, fields: &[Value]) {
        let owner = self.cells[&f.cell].facts[&f.op].owned_owner.unwrap();
        let m = self.ownership.as_mut().unwrap();
        m.owners[owner as usize].as_mut().unwrap().facts.insert(f);
        m.tables[t] += 1;
        m.stats.owned_births += 1;
        m.stats.owned_live += 1;
        self.register_owner_fields(owner, fields);
    }
    // Native result identities are recipe locations, never equivalence proofs.
    // Liveness distinguishes an interior result from a deleted/escaped anchor.
    fn native_owner(&self, id: u64, _live: bool) -> Option<u32> {
        let cell = u32::try_from(id >> 32).ok()?;
        let slot = (id as u32).checked_sub(1)? as usize;
        let c = self.cells.get(&cell)?;
        let op = *self.program.templates[c.template].defs.get(&slot)? as u32;
        let owner = c.facts.get(&op)?.owned_owner?;
        self.ownership
            .as_ref()?
            .owners
            .get(owner as usize)?
            .as_ref()?;
        Some(owner)
    }
    fn boundary(&mut self, root: u64, owner: u32) {
        let m = self.ownership.as_mut().unwrap();
        m.stats.boundary_insert_attempts += 1;
        if m.boundaries.entry(root).or_default().insert(owner) {
            m.stats.boundary_edges_created += 1;
            m.stats.boundary_live += 1;
        }
        m.owners[owner as usize]
            .as_mut()
            .unwrap()
            .boundaries
            .insert(root);
    }
    fn register_owner_fields(&mut self, owner: u32, fields: &[Value]) {
        for v in fields {
            if let Value::Eq(id) = v {
                let id = root(&self.parents, *id);
                if self.native_owner(id, true) == Some(owner) {
                    self.ownership.as_mut().unwrap().stats.internal_ports_seen += 1;
                } else {
                    self.ownership.as_mut().unwrap().stats.boundary_ports_seen += 1;
                    self.boundary(id, owner);
                }
            }
        }
    }
    pub(super) fn propagate_owned_union(&mut self, from: u64, to: u64) {
        if self.ownership.is_none() {
            return;
        }
        let native = self.native_owner(from, false);
        let m = self.ownership.as_mut().unwrap();
        m.stats.boundary_probes += 1;
        let mut owners = m.boundaries.remove(&from).unwrap_or_default();
        m.stats.boundary_owner_routes += owners.len() as u64;
        m.stats.boundary_live -= owners.len() as u64;
        m.stats.boundary_edges_removed += owners.len() as u64;
        for &id in &owners {
            m.owners[id as usize]
                .as_mut()
                .unwrap()
                .boundaries
                .remove(&from);
        }
        if let Some(id) = native {
            m.stats.native_owner_routes += 1;
            owners.insert(id);
        }
        for owner in owners {
            // A second union can precede ordered key completion. Retain a
            // conservative boundary until that completion settles the body.
            self.boundary(to, owner);
            let m = self.ownership.as_mut().unwrap();
            m.refresh.insert(owner);
            m.stats.owner_visits += 1;
            let facts = m.owners[owner as usize]
                .as_ref()
                .unwrap()
                .facts
                .iter()
                .copied()
                .collect::<Vec<_>>();
            for f in facts {
                self.project_owned_fact(f, from, to);
            }
        }
    }
    fn project_owned_fact(&mut self, f: FactRef, from: u64, to: u64) {
        let m = self.ownership.as_mut().unwrap();
        m.stats.body_visits += 1;
        let s = self
            .cells
            .get_mut(&f.cell)
            .unwrap()
            .facts
            .get_mut(&f.op)
            .unwrap();
        let (table, fields) = s.decoded.as_mut().expect("owned canonical body");
        let table = *table;
        let mut changed = false;
        let mut key = false;
        for i in 0..fields.len() {
            if matches!(fields[i], Value::Eq(_)) {
                m.stats.port_checks += 1;
            }
            if fields[i] == Value::Eq(from) {
                m.stats.row_copies += u64::from(Rc::strong_count(fields) > 1);
                Rc::make_mut(fields)[i] = Value::Eq(to);
                changed = true;
                key |= i + 1 < fields.len();
            }
        }
        if !changed {
            return;
        }
        let singleton = self
            .intern
            .get(&s.hash)
            .is_some_and(|b| b.len() == 1 && b.first() == Some(&f));
        if !key && singleton && !m.pending.contains(&f) {
            s.epoch = self.epoch;
            self.query_versions[table] += 1;
            self.changes.touch(table, Dependency::Fact(f));
            m.stats.result_publications += 1;
        } else {
            m.stats.key_enqueues += u64::from(m.pending.insert(f));
            self.dirty_facts[table].insert(f);
        }
    }
    pub(super) fn pop_owned_before(&mut self, next: Option<Dependency>) -> Option<FactRef> {
        let m = self.ownership.as_mut()?;
        let f = *m.pending.first()?;
        if next.is_some_and(|d| d < Dependency::Fact(f)) {
            return None;
        }
        m.pending.pop_first();
        Some(f)
    }
    pub(super) fn complete_owned_key(&mut self, f: FactRef) -> Result<()> {
        let Some(r) = self.fact(f)? else {
            return Ok(());
        };
        self.dirty_facts[r.table].remove(&f);
        self.ownership.as_mut().unwrap().stats.key_completions += 1;
        let h = hashkey(r.table, &r.values[..r.values.len() - 1]);
        let found = self.find_repair_collision(f, &r, h)?;
        if let Some(other) = &found {
            self.enqueue_union(
                r.values.last().unwrap().clone(),
                other.values.last().unwrap().clone(),
            )?;
        }
        self.commit_fact_repair(f, r, h, found)
    }
    pub(super) fn owned_refreshed(&mut self, f: FactRef, fields: &[Value]) {
        let owner = self.cells[&f.cell].facts[&f.op].owned_owner.unwrap();
        self.register_owner_fields(owner, fields);
        self.ownership.as_mut().unwrap().refresh.insert(owner);
    }
    pub(super) fn retire_owned(&mut self, f: FactRef, t: usize, fields: &[Value]) -> bool {
        if !self.cells[&f.cell].facts[&f.op].owned {
            return false;
        }
        let owner = self.cells[&f.cell].facts[&f.op].owned_owner.unwrap();
        // Deleting a result does not delete uses of its identity. Its old
        // recipe location may be collected; preserve an explicit boundary.
        if let Some(Value::Eq(id)) = fields.last() {
            self.boundary(root(&self.parents, *id), owner);
            self.ownership
                .as_mut()
                .unwrap()
                .stats
                .retired_result_boundaries += 1;
        }
        let m = self.ownership.as_mut().unwrap();
        m.owners[owner as usize].as_mut().unwrap().facts.remove(&f);
        m.pending.remove(&f);
        m.refresh.insert(owner);
        m.tables[t] -= 1;
        m.stats.owned_live -= 1;
        m.stats.owned_retirements += 1;
        true
    }
    pub(super) fn settle_owned_boundaries(&mut self) -> Result<()> {
        if self.ownership.is_none() {
            return Ok(());
        }
        while let Some(owner) = self.ownership.as_mut().unwrap().refresh.pop_first() {
            let m = self.ownership.as_mut().unwrap();
            let o = m.owners[owner as usize].as_mut().unwrap();
            let old = std::mem::take(&mut o.boundaries);
            let facts = o.facts.iter().copied().collect::<Vec<_>>();
            m.stats.boundary_rebuilds += 1;
            for id in old {
                let b = m.boundaries.get_mut(&id).unwrap();
                if b.remove(&owner) {
                    m.stats.boundary_live -= 1;
                    m.stats.boundary_edges_removed += 1;
                }
                if b.is_empty() {
                    m.boundaries.remove(&id);
                }
            }
            if facts.is_empty() {
                m.owners[owner as usize] = None;
                m.stats.owners_live -= 1;
                m.stats.owners_retired += 1;
                continue;
            }
            for f in facts {
                self.ownership.as_mut().unwrap().stats.boundary_body_reads += 1;
                if let Some(row) = self.fact(f)? {
                    self.register_owner_fields(owner, &row.values);
                }
            }
        }
        Ok(())
    }
    pub(crate) fn ownership_barrier(&mut self) {
        if let Some(m) = &mut self.ownership {
            assert!(
                m.pending.is_empty() && m.refresh.is_empty(),
                "unsettled owner at publication boundary"
            );
            m.stats.stage_barriers += 1;
            m.stats.carried_facts += m.stats.owned_live;
            m.stats.carried_owners += m.stats.owners_live;
            m.barriers.push(Barrier {
                epoch: self.epoch,
                live_facts: m.stats.owned_live,
                live_owners: m.stats.owners_live,
                boundary_edges: m.stats.boundary_live,
                legacy_reverse_edges: self.maintenance.live_reverse_edges,
                key_completions: m.stats.key_completions,
                result_publications: m.stats.result_publications,
                body_visits: m.stats.body_visits,
            });
        }
    }
    fn owner_domain(&self, id: u64) -> BTreeSet<u32> {
        let m = self.ownership.as_ref().unwrap();
        let mut owners = m.boundaries.get(&id).cloned().unwrap_or_default();
        if let Some(owner) = self.native_owner(id, false) {
            owners.insert(owner);
        }
        owners
    }
    fn smallest_owner_domain(
        &self,
        bound: &[Option<Value>],
    ) -> Option<(u64, BTreeSet<u32>, usize)> {
        let m = self.ownership.as_ref()?;
        bound
            .iter()
            .filter_map(|v| {
                let Some(Value::Eq(id)) = v else { return None };
                let id = root(&self.parents, *id);
                let owners = self.owner_domain(id);
                let count = owners
                    .iter()
                    .map(|&o| m.owners[o as usize].as_ref().unwrap().facts.len())
                    .sum::<usize>()
                    + self.uses.get(&id).map_or(0, UseSet::len);
                Some((id, owners, count))
            })
            .min_by_key(|x| x.2)
    }
    pub(super) fn owned_candidate_count(&self, table: usize, bound: &[Option<Value>]) -> usize {
        self.smallest_owner_domain(bound)
            .map_or(self.witness_count(table), |(_, _, n)| {
                n.min(self.witness_count(table))
            })
    }
    pub(super) fn owned_candidates(
        &self,
        table: usize,
        bound: &[Option<Value>],
    ) -> Vec<Dependency> {
        let Some((id, owners, _)) = self.smallest_owner_domain(bound) else {
            // No equality predicate: ordinary membership enumeration is also
            // the baseline path, not a missing-subscription fallback.
            let rows = self.witnesses(table);
            let s = &self.ownership.as_ref().unwrap().stats;
            s.unbound_query_calls.set(s.unbound_query_calls.get() + 1);
            s.unbound_query_rows
                .set(s.unbound_query_rows.get() + rows.len() as u64);
            return rows;
        };
        let m = self.ownership.as_ref().unwrap();
        let s = &m.stats;
        s.domain_queries.set(s.domain_queries.get() + 1);
        let mut result = BTreeSet::new();
        for owner in owners {
            s.domain_owner_visits.set(s.domain_owner_visits.get() + 1);
            for &f in &m.owners[owner as usize].as_ref().unwrap().facts {
                s.domain_body_visits.set(s.domain_body_visits.get() + 1);
                if self.cells[&f.cell].facts[&f.op].decoded.as_ref().unwrap().0 == table {
                    result.insert(Dependency::Fact(f));
                }
            }
        }
        for &d in self.uses.get(&id).into_iter().flat_map(|s| s.iter()) {
            s.domain_legacy_visits.set(s.domain_legacy_visits.get() + 1);
            if self.dependency_table(d) == Some(table) {
                result.insert(d);
            }
        }
        s.domain_results
            .set(s.domain_results.get() + result.len() as u64);
        result.into_iter().collect()
    }
    pub fn ownership_report(&self) -> J {
        let mut internal = 0u64;
        let mut boundary = 0u64;
        let mut across = 0u64;
        let mut largest = 0;
        if let Some(m) = &self.ownership {
            assert_eq!(
                m.stats.boundary_live,
                m.boundaries.values().map(|x| x.len() as u64).sum::<u64>()
            );
            assert_eq!(m.stats.owned_live, m.tables.iter().sum::<usize>() as u64);
            assert!(
                m.owners
                    .iter()
                    .flatten()
                    .flat_map(|o| o.facts.iter())
                    .all(|f| !self.dependencies.contains_key(&Dependency::Fact(*f)))
            );
            for (owner, o) in m
                .owners
                .iter()
                .enumerate()
                .filter_map(|(i, o)| o.as_ref().map(|o| (i, o)))
            {
                largest = largest.max(o.facts.len());
                for f in &o.facts {
                    let s = &self.cells[&f.cell].facts[&f.op];
                    assert_eq!(s.owned_owner, Some(owner as u32));
                    across += u64::from(s.born < self.epoch);
                    for v in s.decoded.as_ref().expect("settled owned body").1.iter() {
                        if let Value::Eq(id) = v {
                            assert_eq!(*id, root(&self.parents, *id), "owned body is stale");
                            if self.native_owner(*id, true) == Some(owner as u32) {
                                internal += 1;
                            } else {
                                boundary += 1;
                                assert!(
                                    m.boundaries
                                        .get(id)
                                        .is_some_and(|b| b.contains(&(owner as u32))),
                                    "missing owner boundary"
                                );
                            }
                        }
                    }
                }
            }
        }
        json!({"enabled":self.ownership.is_some(),"plan":self.program.cell_ownership.artifact(&self.program),
            "barriers":self.ownership.as_ref().map(|m|&m.barriers),
            "inventory":{"internal_eq_ports":internal,"boundary_eq_ports":boundary,"cross_stage_live_facts":across,"largest_owner":largest,
                "eligible_live_facts":self.program.cell_ownership.tables.iter().enumerate().filter(|(_,ok)|**ok).map(|(t,_)|self.witness_count(t)).sum::<usize>(),
                "unsupported_live_rows":self.program.cell_ownership.tables.iter().enumerate().filter(|(_,ok)|!**ok).map(|(t,_)|self.witness_count(t)).sum::<usize>()},
            "stats":self.ownership.as_ref().map(|m|&m.stats),"pending_keys":self.ownership.as_ref().map_or(0,|m|m.pending.len())})
    }
}
