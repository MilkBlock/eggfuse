//! Compiler-owned shared entry nodes. Current parameter packets are maintained
//! once per changed input; consumers borrow them at their original source Run.
use crate::{
    graph::{Dependency, Graph, Row},
    program::*,
    value::{Value, canon},
};
use rustc_hash::FxHashMap as HashMap;
use serde::{Deserialize, Serialize};
use serde_json::{Value as J, json};
use std::{collections::BTreeMap, rc::Rc};
#[cfg(not(feature = "sparse-cells"))]
use {crate::graph::FactRef, std::collections::BTreeSet};

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Plan {
    nodes: Vec<Node>,
    rules: Vec<Vec<Rc<Consumer>>>,
    tables: Vec<Vec<usize>>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
struct Node {
    #[cfg(feature = "sparse-cells")]
    #[serde(skip)]
    checks: Vec<(usize, Arg)>,
    table: usize,
    args: Vec<Arg>,
    ports: usize,
    literal_identity: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
struct Consumer {
    node: usize,
    atom: usize,
    projection: Vec<Option<usize>>,
}
fn identity(v: &Value) -> bool {
    match v {
        Value::Eq(_) => true,
        Value::Set(xs) => xs.iter().any(identity),
        _ => false,
    }
}
impl Plan {
    #[cfg(any(feature = "family-frontiers", feature = "family-scan"))]
    pub(crate) fn survey_nodes(&self, r: usize) -> impl Iterator<Item = (usize, usize)> + '_ {
        self.rules[r].iter().map(|c| (c.atom, c.node))
    }

    pub fn parse(p: &Program, raw: &J) -> Result<Self> {
        if raw.is_null() {
            {
                return Err("shared node schedule requires compiler entry_schedule; re-emit the Cell CPU artifact".into());
            }
        }
        let (s, expected) = Self::derive(p)?;
        if *raw != expected {
            return Err("shared entry schedule differs from typed query wiring/control".into());
        }
        Ok(s)
    }
    pub(crate) fn derive(p: &Program) -> Result<(Self, J)> {
        let mut s = Self {
            nodes: vec![],
            rules: vec![vec![]; p.rules.len()],
            tables: vec![vec![]; p.tables.len()],
        };
        let mut ids = BTreeMap::new();
        let mut expected: Vec<J> = vec![];
        for (rid, r) in p.rules.iter().enumerate() {
            if r.seminaive {
                for (atom, a) in r.query.iter().enumerate() {
                    let Call::Table(t) = a.call else { continue };
                    let mut slots = BTreeMap::new();
                    let mut projection = vec![None; p.templates[r.template].sorts.len()];
                    let mut pairs = vec![];
                    let mut pattern = vec![];
                    let mut args = vec![];
                    for (col, v) in a.args.iter().enumerate() {
                        match v {
                            Arg::Slot(i) => {
                                let n = slots.len();
                                let port = *slots.entry(*i).or_insert(n);
                                if projection[*i].is_none() {
                                    #[cfg(feature = "sparse-cells")]
                                    {
                                        projection[*i] = Some(col);
                                    }
                                    #[cfg(not(feature = "sparse-cells"))]
                                    {
                                        projection[*i] = Some(port);
                                    }
                                    pairs.push(json!({"slot":i,"port":port}));
                                }
                                pattern.push(Arg::Slot(port));
                                args.push(json!({"slot":port}));
                            }
                            Arg::Literal(v) => {
                                pattern.push(Arg::Literal(v.clone()));
                                args.push(
                                    p.artifact["recipe"]["rules"][rid]["query"][atom]["args"][col]
                                        .clone(),
                                );
                            }
                        }
                    }
                    let key = (t, pattern.clone());
                    let n = ids.len();
                    let id = *ids.entry(key).or_insert(n);
                    if id == s.nodes.len() {
                        s.tables[t].push(id);
                        #[cfg(feature = "sparse-cells")]
                        let checks = pattern
                            .iter()
                            .enumerate()
                            .filter_map(|(col, a)| match a {
                                Arg::Literal(_) => Some((col, a.clone())),
                                Arg::Slot(_) => {
                                    let previous = pattern[..col].iter().position(|x| x == a)?;
                                    Some((col, Arg::Slot(previous)))
                                }
                            })
                            .collect();
                        s.nodes.push(Node {
                            #[cfg(feature = "sparse-cells")]
                            checks,
                            table: t,
                            args: pattern,
                            ports: slots.len(),
                            literal_identity: a
                                .args
                                .iter()
                                .any(|a| matches!(a,Arg::Literal(v) if identity(v))),
                        });
                        expected.push(json!({"id":id,"table":p.tables[t].name,"args":args,"ports":slots.len(),"consumers":[]}));
                    }
                    expected[id]["consumers"]
                        .as_array_mut()
                        .unwrap()
                        .push(json!({"rule":rid,"atom":atom,"slots":pairs}));
                    s.rules[rid].push(Rc::new(Consumer {
                        node: id,
                        atom,
                        projection,
                    }));
                }
            }
        }
        let expected = json!({"schema":"eggfuse-entry-schedule/v1","recipe_sha256":p.artifact["recipe"]["sha256"],"nodes":expected,"control":p.artifact["recipe"]["control"],"contract":{
            "input":"committed current row changes, coalesced before a legal consumer Run",
            "result":"complete correlated entry parameters and witness epoch",
            "delivery":"independent consumer watermarks; original RHS publication",
            "invalidation":"old/new witnesses, visibility, canonical identities and same-key forwarding",
            "scope":"table entry nodes; residual queries and guards remain exact"}});
        Ok((s, expected))
    }
}
#[cfg(feature = "sparse-cells")]
type SharedPacket = Packet;
#[cfg(not(feature = "sparse-cells"))]
type SharedPacket = Rc<Packet>;
#[derive(Clone)]
pub struct Packet {
    pub row: Rc<Row>,
    #[cfg(not(feature = "sparse-cells"))]
    values: Rc<Vec<Option<Value>>>,
}
#[derive(Clone)]
pub struct Seed {
    pub packet: SharedPacket,
    consumer: Rc<Consumer>,
    // This handle is used only while matching this delivered Run snapshot.
    // Publications are committed/retired after matching, before another batch.
    #[cfg(feature = "sparse-cells")]
    publication: Option<std::num::NonZeroUsize>,
}
impl Seed {
    pub fn atom(&self) -> usize { self.consumer.atom }
}
/// Sparse private suffix writes over immutable compiled parameter projections.
/// No initial full-width parameter array is cloned for a scheduled consumer.
#[derive(Clone)]
pub struct Inputs {
    #[cfg(feature = "sparse-cells")]
    legacy_base: std::cell::OnceCell<Box<[Option<Value>]>>,
    own: Vec<Option<Value>>,
    base: Option<Seed>,
}
impl Inputs {
    pub fn owned(n: usize) -> Self {
        Self {
            #[cfg(feature = "sparse-cells")]
            legacy_base: Default::default(),
            own: vec![None; n],
            base: None,
        }
    }
    pub fn shared(seed: Seed) -> Self {
        Self {
            #[cfg(feature = "sparse-cells")]
            legacy_base: Default::default(),
            own: vec![],
            base: Some(seed),
        }
    }
    pub fn len(&self) -> usize {
        self.own
            .len()
            .max(self.base.as_ref().map_or(0, |s| s.consumer.projection.len()))
    }
    pub fn iter(&self) -> impl Iterator<Item = &Option<Value>> {
        (0..self.len()).map(move |i| &self[i])
    }
    pub fn refs(&self) -> impl Iterator<Item = Option<&Value>> {
        (0..self.len()).map(move |i| self.get(i))
    }
    /// Move private slot values into the sealed RHS input. Shared entry
    /// packets remain immutable and supply owned snapshots when needed.

    pub fn materialize(&self) -> Vec<Option<Value>> {
        self.refs().map(|v| v.cloned()).collect()
    }
    pub fn owned_mut(&mut self) -> &mut [Option<Value>] {
        assert!(self.base.is_none());
        &mut self.own
    }
}
impl Inputs {
    pub fn get(&self, slot: usize) -> Option<&Value> {
        if let Some(v) = self.own.get(slot).and_then(Option::as_ref) {
            return Some(v);
        }
        let s = self.base.as_ref()?;
        let port = s.consumer.projection.get(slot).copied().flatten()?;
        #[cfg(feature = "sparse-cells")]
        {
            s.packet.row.values.get(port)
        }
        #[cfg(not(feature = "sparse-cells"))]
        {
            s.packet.values[port].as_ref()
        }
    }
    pub fn set(&mut self, slot: usize, v: Option<Value>) {
        if self.own.len() <= slot {
            self.own.resize(slot + 1, None)
        }
        self.own[slot] = v;
    }
}
#[cfg(feature = "sparse-cells")]
impl std::ops::Index<usize> for Inputs {
    type Output = Option<Value>;
    fn index(&self, i: usize) -> &Self::Output {
        if let Some(v) = self.own.get(i).filter(|v| v.is_some()) {
            return v;
        }
        let Some(s) = &self.base else { return &None };
        if s.consumer.projection.get(i).is_none_or(Option::is_none) {
            return &None;
        }
        &self.legacy_base.get_or_init(|| {
            s.consumer.projection
                .iter()
                .map(|port| port.map(|c| s.packet.row.values[c].clone()))
                .collect()
        })[i]
    }
}
#[cfg(not(feature = "sparse-cells"))]
impl std::ops::Index<usize> for Inputs {
    type Output = Option<Value>;
    fn index(&self, i: usize) -> &Self::Output {
        if let Some(v) = self.own.get(i).filter(|v| v.is_some()) {
            return v;
        }
        if let Some(s) = &self.base {
            if let Some(Some(port)) = s.consumer.projection.get(i) {
                return &s.packet.values[*port];
            }
        }
        &None
    }
}
impl std::ops::IndexMut<usize> for Inputs {
    fn index_mut(&mut self, i: usize) -> &mut Self::Output {
        if self.own.len() <= i {
            self.own.resize(i + 1, None)
        }
        &mut self.own[i]
    }
}

#[cfg(feature = "sparse-cells")]
#[path = "epoch_runs.rs"]
mod epoch_runs;
#[derive(Default)]
struct Stored {
    // A producer may publish before this node's first scheduled consumer.
    // Keep its expression here without decoding an otherwise unused row.
    packet: Option<SharedPacket>,
    #[cfg(feature = "sparse-cells")]
    publication: Option<std::num::NonZeroUsize>,
}
// Preserve the original compact packet map for ordinary nodes. Only a node
// that actually owns publications pays for the extra expression handle.
enum Entries {
    Plain(HashMap<Dependency, SharedPacket>),
    #[cfg(feature = "sparse-cells")]
    Owned(HashMap<Dependency, Stored>),
}
impl Default for Entries {
    fn default() -> Self { Self::Plain(HashMap::default()) }
}
impl Entries {
    fn len(&self) -> usize {
        match self {
            Self::Plain(rows) => rows.len(),
            #[cfg(feature = "sparse-cells")]
            Self::Owned(rows) => rows.len(),
        }
    }
    fn is_empty(&self) -> bool { self.len() == 0 }
    fn remove(&mut self, w: &Dependency) -> Option<Stored> {
        match self {
            Self::Plain(rows) => rows.remove(w).map(|packet| Stored {
                packet: Some(packet),
                #[cfg(feature = "sparse-cells")]
                publication: None,
            }),
            #[cfg(feature = "sparse-cells")]
            Self::Owned(rows) => rows.remove(w),
        }
    }
    fn insert(&mut self, w: Dependency, entry: Stored) {
        match self {
            Self::Plain(rows) => {
                #[cfg(feature = "sparse-cells")]
                debug_assert!(entry.publication.is_none());
                rows.insert(w, entry.packet.expect("ordinary packet"));
            }
            #[cfg(feature = "sparse-cells")]
            Self::Owned(rows) => { rows.insert(w, entry); }
        }
    }
    fn take(&mut self) -> Self {
        let empty = match self {
            Self::Plain(_) => Self::default(),
            #[cfg(feature = "sparse-cells")]
            Self::Owned(_) => Self::Owned(HashMap::default()),
        };
        std::mem::replace(self, empty)
    }
}
#[derive(Default)]
struct State {
    #[cfg(feature = "sparse-cells")]
    publications: usize,
    latest_witness_epoch: u64,
    #[cfg(feature = "sparse-cells")]
    planned_counts: bool,
    cold: bool,
    #[cfg(not(feature = "sparse-cells"))]
    pending: BTreeSet<Dependency>,
    #[cfg(feature = "sparse-cells")]
    pending: Vec<Dependency>,
    #[cfg(feature = "sparse-cells")]
    sorted_pending: usize,
    rows: Entries,
    #[cfg(not(feature = "sparse-cells"))]
    epochs: BTreeSet<(u64, Dependency)>,
    #[cfg(feature = "sparse-cells")]
    epochs: epoch_runs::Epochs,
    epoch_counts: Option<BTreeMap<u64, usize>>,
}
impl State {
    #[cfg(feature = "sparse-cells")]
    fn compact_pending(&mut self) {
        if self.sorted_pending < self.pending.len() {
            self.pending.sort_unstable();
            self.pending.dedup();
            self.sorted_pending = self.pending.len();
        }
    }
    #[cfg(feature = "sparse-cells")]
    fn pending_count(&self) -> usize {
        if self.sorted_pending == self.pending.len() { return self.sorted_pending; }
        let mut rows = self.pending.clone();
        rows.sort_unstable();
        rows.dedup();
        rows.len()
    }
    fn insert_epoch(&mut self, epoch: u64, w: Dependency) {
        self.latest_witness_epoch = self.latest_witness_epoch.max(epoch);
        if self.epochs.insert((epoch, w))
            && let Some(counts) = &mut self.epoch_counts
        {
            *counts.entry(epoch).or_default() += 1;
        }
    }
    fn remove_epoch(&mut self, epoch: u64, w: Dependency) {
        if self.epochs.remove(&(epoch, w))
            && let Some(counts) = &mut self.epoch_counts
        {
            let count = counts.get_mut(&epoch).expect("indexed epoch");
            *count -= 1;
            if *count == 0 {
                counts.remove(&epoch);
            }
        }
    }
}
#[derive(Default, Serialize)]
pub struct Stats {
    entry_publication_writes: u64,
    // Removed Pending-path counters stay zero for historical metric continuity.
    fragment_slot_probes: u64,
    publication_candidate_checks: u64,
    publication_loser_skips: u64,
    publication_slot_probes: u64,
    publication_pending_pushes: u64,
    publication_pending_reuses: u64,
    fragment_pending_writes: u64,
    fragment_pending_reads: u64,
    fragment_slot_replacements: u64,
    fragment_older_skips: u64,
    entry_publications_retired: u64,
    entry_retirement_checks: u64,
    pub predicate_checks: u64,
    node_refreshes: u64,
    changed_headers: u64,
    node_notifications: u64,
    cold_rows: u64,
    row_decodes: u64,
    private_row_reads: u64,
    parameters_copied: u64,
    parameter_packets_reused: u64,
    consumer_calls: u64,
    consumer_seed_deliveries: u64,
    borrowed_slots: u64,
    retired_packets: u64,
}
pub struct Scheduler {
    pub enabled: bool,
    plan: Plan,
    states: Vec<State>,
    rows: HashMap<Dependency, Option<Rc<Row>>>,
    unions: u64,
    #[cfg(feature = "sparse-cells")]
    publication_nodes: Vec<Option<usize>>,
    #[cfg(feature = "sparse-cells")]
    publications: Vec<Option<PublicationSlot>>,
    #[cfg(feature = "sparse-cells")]
    publication_batch: u64,
    #[cfg(feature = "sparse-cells")]
    publication_free: Vec<std::num::NonZeroUsize>,
    pub stats: Stats,
}
#[cfg(feature = "sparse-cells")]
struct PublicationSlot {
    published: crate::stage_spine::Published,
    batch: u64,
}
/// Immutable node contents after refresh, plus this consumer's delta frontier.
#[derive(Clone, Copy)]
pub(crate) struct Batch<'a> {
    state: &'a State,
    consumer: &'a Rc<Consumer>,
    watermark: u64,
    pub table: usize,
    #[cfg(feature = "sparse-cells")]
    publications: &'a [Option<PublicationSlot>],
}
/// One borrowed Cell Entry: its existing row, shared consumer projection and
/// publication location travel together. No per-consumer binding array or
/// producer subscription is created for this view.
pub(crate) struct Entry<'a> {
    packet: &'a SharedPacket,
    consumer: &'a Rc<Consumer>,
    #[cfg(feature = "sparse-cells")]
    publication: Option<std::num::NonZeroUsize>,
    #[cfg(feature = "sparse-cells")]
    publications: &'a [Option<PublicationSlot>],
}
impl std::ops::Deref for Entry<'_> {
    type Target = Packet;
    fn deref(&self) -> &Packet { self.packet }
}
impl Entry<'_> {
    pub fn seed(&self) -> Seed {
        Seed {
            packet: self.packet.clone(),
            consumer: self.consumer.clone(),
            #[cfg(feature = "sparse-cells")]
            publication: self.publication,
        }
    }
    #[cfg(feature = "sparse-cells")]
    pub fn published(&self) -> Option<&crate::stage_spine::Published> {
        Some(&self.publications[self.publication?.get() - 1].as_ref()?.published)
    }
}
impl<'a> Batch<'a> {
    #[cfg(any(
        feature = "projection-shared",
        feature = "family-overlap",
        feature = "family-frontiers",
        feature = "family-scan"
    ))]
    pub fn node(&self) -> usize {
        self.consumer.node
    }
    #[cfg(any(
        feature = "projection-semijoin",
        feature = "projection-shared",
        feature = "family-frontiers",
        feature = "family-scan"
    ))]
    pub fn watermark(&self) -> u64 {
        self.watermark
    }
    pub fn atom(&self) -> usize {
        self.consumer.atom
    }
    pub fn empty_delta(&self) -> bool {
        self.state.rows.is_empty() || self.state.latest_witness_epoch < self.watermark
    }
    pub fn len(&self) -> usize {
        self.state.rows.len()
    }
    #[cfg(feature = "sparse-cells")]
    pub fn delta(&self) -> impl Iterator<Item = &(u64, Dependency)> {
        self.state.epochs.range(self.watermark)
    }
    #[cfg(not(feature = "sparse-cells"))]
    pub fn delta(&self) -> std::collections::btree_set::Range<'_, (u64, Dependency)> {
        self.state
            .epochs
            .range((self.watermark, Dependency::Fact(FactRef { cell: 0, op: 0 }))..)
    }
    #[cfg(feature = "sparse-cells")]
    pub fn delta_len(&self) -> Option<usize> {
        self.state
            .planned_counts
            .then(|| self.state.epochs.counts(self.watermark).sum())
    }
    #[cfg(not(feature = "sparse-cells"))]
    pub fn delta_len(&self) -> Option<usize> {
        Some(
            self.state
                .epoch_counts
                .as_ref()?
                .range(self.watermark..)
                .map(|(_, n)| n)
                .sum(),
        )
    }
    #[cfg(feature = "sparse-cells")]
    pub fn delta_exceeds(&self, budget: usize, bins: &mut u64) -> bool {
        let mut total = 0;
        self.state.epochs.counts(self.watermark).any(|n| {
            *bins += 1;
            total += n;
            total > budget
        })
    }
    #[cfg(not(feature = "sparse-cells"))]
    pub fn delta_exceeds(&self, budget: usize, bins: &mut u64) -> bool {
        let counts = self.state.epoch_counts.as_ref().expect("planned entry");
        let mut total = 0;
        for (_, n) in counts.range(self.watermark..) {
            *bins += 1;
            total += n;
            if total > budget {
                return true;
            }
        }
        false
    }
    // Query consumers live in several codegen units. Inline this borrowed
    // view so it does not introduce a large return-value copy per delivered row.
    #[inline]
    pub fn entry(&self, w: Dependency) -> Option<Entry<'a>> {
        let packet = match &self.state.rows {
            Entries::Plain(rows) => rows.get(&w)?,
            #[cfg(feature = "sparse-cells")]
            Entries::Owned(rows) => {
                let e = rows.get(&w)?;
                return e.packet.as_ref().filter(|p| p.row.epoch >= self.watermark)
                    .map(|packet| Entry { packet, consumer: self.consumer,
                        publication: e.publication, publications: self.publications });
            }
        };
        (packet.row.epoch >= self.watermark).then_some(Entry {
            packet, consumer: self.consumer,
            #[cfg(feature = "sparse-cells")]
            publication: None,
            #[cfg(feature = "sparse-cells")]
            publications: self.publications,
        })
    }
}
impl Scheduler {
    pub fn new(p: &Program, enabled: bool) -> Self {
        Self::with_epoch_counts(p, enabled, false)
    }
    pub(crate) fn with_epoch_counts(p: &Program, enabled: bool, planned: bool) -> Self {
        let plan = p.entry_schedule.clone();
        let states = plan
            .nodes
            .iter()
            .map(|_| State {
                cold: true,
                #[cfg(feature = "sparse-cells")]
                planned_counts: enabled && planned,
                epoch_counts: (enabled && planned && !cfg!(feature = "sparse-cells"))
                    .then(BTreeMap::new),
                ..Default::default()
            })
            .collect();
        Self {
            #[cfg(feature = "sparse-cells")]
            publication_nodes: vec![None; p.tables.len()],
            #[cfg(feature = "sparse-cells")]
            publications: vec![],
            #[cfg(feature = "sparse-cells")]
            publication_batch: 0,
            #[cfg(feature = "sparse-cells")]
            publication_free: vec![],
            enabled,
            plan,
            states,
            rows: HashMap::default(),
            unions: 0,
            stats: Stats::default(),
        }
    }
    pub fn accepts(&self, rid: usize) -> bool {
        self.enabled && self.plan.rules.get(rid).is_some_and(|x| !x.is_empty())
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn own_publications(&mut self, eligible: impl Fn(usize) -> bool) -> Vec<bool> {
        for (table, nodes) in self.plan.tables.iter().enumerate() {
            // One exhaustive identity entry owns every visible row of this
            // table. Filtered/multiple entries retain the ordinary owner.
            if self.enabled && eligible(table) && nodes.len() == 1
                && self.plan.nodes[nodes[0]].checks.is_empty()
            {
                self.publication_nodes[table] = Some(nodes[0]);
                if let Entries::Plain(rows) = &mut self.states[nodes[0]].rows {
                    let owned = std::mem::take(rows).into_iter().map(|(w, packet)| {
                        (w, Stored { packet: Some(packet), publication: None })
                    }).collect();
                    self.states[nodes[0]].rows = Entries::Owned(owned);
                }
            }
        }
        self.publication_nodes.iter().map(Option::is_some).collect()
    }
    #[cfg(feature = "sparse-cells")]
    fn publication_slot(&mut self, table: usize, w: Dependency) -> std::num::NonZeroUsize {
        self.stats.publication_slot_probes += 1;
        let node = self.publication_nodes[table].expect("compiled entry owner");
        let state = &mut self.states[node];
        let Entries::Owned(rows) = &mut state.rows else { unreachable!("entry owner") };
        let e = rows.entry(w).or_default();
        let first = e.publication.is_none();
        state.publications += usize::from(first);
        if e.packet.is_none() && !state.cold {
            // A packetless published Entry is already queued by its first
            // publication. Refresh either installs its packet or removes the
            // Entry; later graph changes also retain the ordinary Wake path.
            if first {
                state.pending.push(w);
                self.stats.publication_pending_pushes += 1;
            } else {
                self.stats.publication_pending_reuses += 1;
            }
        }
        let id = *e.publication.get_or_insert_with(|| self.publication_free.pop().unwrap_or_else(|| {
            self.publications.push(None);
            std::num::NonZeroUsize::new(self.publications.len()).unwrap()
        }));
        id
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn begin_publication(&mut self) {
        self.publication_batch = self.publication_batch.checked_add(1).expect("publication generation exhausted");
    }
    /// Cell completion supplies candidates in descending source order. The
    /// first candidate in this boundary owns the slot; losing candidates never
    /// construct a continuation or write a Pending publication.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn install_publication(&mut self, table: usize, w: Dependency,
        make: impl FnOnce() -> crate::stage_spine::Published,
    ) -> bool {
        self.stats.publication_candidate_checks += 1;
        let id = self.publication_slot(table, w);
        let target = &mut self.publications[id.get() - 1];
        if target.as_ref().is_some_and(|p| p.batch == self.publication_batch) {
            self.stats.publication_loser_skips += 1;
            return false;
        }
        *target = Some(PublicationSlot { published: make(), batch: self.publication_batch });
        self.stats.entry_publication_writes += 1;
        true
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn publication_count(&self, table: usize) -> usize {
        self.publication_nodes[table].map_or(0, |id| self.states[id].publications)
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn publication(&self, seed: &Seed) -> Option<&crate::stage_spine::Published> {
        let id = seed.publication?;
        Some(&self.publications[id.get() - 1].as_ref()?.published)
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn owns_publications(&self, table: usize) -> bool {
        self.publication_nodes[table].is_some()
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn publications(&self) -> impl Iterator<Item = &crate::stage_spine::Published> {
        self.publications.iter().filter_map(|p| p.as_ref().map(|p| &p.published))
    }
    /// Called before query-change records are consumed. Only committed rows and
    /// exact same-key forwarding retirements enter the shared pending domains.
    pub(crate) fn settled(&self,g:&Graph)->bool {
        !self.enabled || (self.rows.is_empty() && self.unions == g.stats.unions)
    }
    pub fn publish(&mut self, g: &Graph) {
        self.publish_except(g, |_| false);
    }
    pub(crate) fn publish_except(&mut self, g: &Graph, dedicated: impl Fn(usize) -> bool) {
        if !self.enabled {
            return;
        }
        self.rows.clear();
        // A same-key repair retires the old witness and touches the survivor.
        for (table, changes) in g.changes.tables() {
            if dedicated(table) {
                continue;
            }
            self.stats.changed_headers += changes.len() as u64;
            #[cfg(feature = "sparse-cells")]
            if let Some(id) = self.publication_nodes[table] {
                let state = &mut self.states[id];
                for (&w, change) in changes {
                    // The sealed change batch already identifies the table
                    // and explicit removals. Only Wake can still be subsumed.
                    let live = if *change != crate::change_batch::Change::Wake {
                        false
                    } else {
                        self.stats.entry_retirement_checks += 1;
                        match w {
                            Dependency::Fact(f) => g.cells.get(&f.cell)
                                .and_then(|c| c.facts.get(&f.op)).is_some_and(|f| !f.hidden),
                            Dependency::Function(i) => g.functions.get(i).is_some_and(|f| f.live),
                        }
                    };
                    if !live {
                        if let Some(e) = state.rows.remove(&w) {
                            self.stats.entry_publications_retired += u64::from(e.publication.is_some());
                            state.publications -= usize::from(e.publication.is_some());
                            if let Some(id) = e.publication {
                                self.publications[id.get() - 1] = None;
                                self.publication_free.push(id);
                            }
                            if let Some(p) = e.packet {
                                state.remove_epoch(p.row.epoch, w);
                                self.stats.retired_packets += 1;
                            }
                        }
                    } else if !state.cold {
                        state.pending.push(w);
                    }
                }
                if state.pending.len() > state.sorted_pending.saturating_mul(2).max(64) {
                    state.compact_pending();
                }
                continue;
            }
            for &id in &self.plan.tables[table] {
                let state = &mut self.states[id];
                if !state.cold {
                    #[cfg(not(feature = "sparse-cells"))]
                    let before = state.pending.len();
                    state.pending.extend(changes.keys().copied());
                    #[cfg(not(feature = "sparse-cells"))]
                    { self.stats.node_notifications += (state.pending.len() - before) as u64; }
                    #[cfg(feature = "sparse-cells")]
                    if state.pending.len() > state.sorted_pending.saturating_mul(2).max(64) {
                        // Bound unconsumed repetitions even when this node's
                        // consumer ruleset is dormant for many publications.
                        state.compact_pending();
                    }
                }
            }
        }
        if self.unions != g.stats.unions {
            for (id, n) in self.plan.nodes.iter().enumerate() {
                if n.literal_identity {
                    self.states[id].cold = true;
                }
            }
            self.unions = g.stats.unions;
        }
    }
    pub fn seeds(&mut self, g: &Graph, rid: usize, watermark: u64) -> Result<Vec<Seed>> {
        self.seeds_where(g, rid, watermark, |_, _, _| true)
    }
    pub(crate) fn seeds_where(
        &mut self,
        g: &Graph,
        rid: usize,
        watermark: u64,
        mut allow: impl FnMut(usize, usize, Dependency) -> bool,
    ) -> Result<Vec<Seed>> {
        self.batches(g, rid, watermark, |batch, out| {
            for &(_, w) in batch.delta() {
                if allow(batch.atom(), batch.table, w) {
                    out.push(batch.entry(w).expect("current delta entry").seed());
                }
            }
            Ok(())
        })
    }
    pub(crate) fn terminal_batch(
        &mut self,
        g: &Graph,
        rid: usize,
        atom: usize,
        watermark: u64,
    ) -> Result<Batch<'_>> {
        let i = self.plan.rules[rid]
            .iter()
            .position(|c| c.atom == atom)
            .ok_or("missing terminal entry")?;
        let node = self.plan.rules[rid][i].node;
        self.refresh(g, node)?;
        Ok(Batch {
            #[cfg(feature = "sparse-cells")]
            publications: &self.publications,
            state: &self.states[node],
            consumer: &self.plan.rules[rid][i],
            watermark,
            table: self.plan.nodes[node].table,
        })
    }
    pub(crate) fn batches(
        &mut self,
        g: &Graph,
        rid: usize,
        watermark: u64,
        mut visit: impl FnMut(Batch<'_>, &mut Vec<Seed>) -> Result<()>,
    ) -> Result<Vec<Seed>> {
        self.stats.consumer_calls += 1;
        let mut out = vec![];
        for i in 0..self.plan.rules[rid].len() {
            let node = self.plan.rules[rid][i].node;
            self.refresh(g, node)?;
            let c = &self.plan.rules[rid][i];
            let start = out.len();
            visit(
                Batch {
                    #[cfg(feature = "sparse-cells")]
                    publications: &self.publications,
                    state: &self.states[c.node],
                    consumer: c,
                    watermark,
                    table: self.plan.nodes[c.node].table,
                },
                &mut out,
            )?;
            let count = (out.len() - start) as u64;
            self.stats.consumer_seed_deliveries += count;
            self.stats.borrowed_slots += count * self.plan.nodes[c.node].ports as u64;
        }
        Ok(out)
    }
    fn refresh(&mut self, g: &Graph, id: usize) -> Result<()> {
        let s = &mut self.states[id];
        if !s.cold && s.pending.is_empty() {
            return Ok(());
        }
        self.stats.node_refreshes += 1;
        let n = &self.plan.nodes[id];
        let full = s.cold;
        s.cold = false;
        #[cfg(feature = "sparse-cells")]
        {
            s.compact_pending();
            self.stats.node_notifications += s.pending.len() as u64;
            s.sorted_pending = 0;
        }
        let mut pending = if full {
            self.stats.cold_rows += g.witness_count(n.table) as u64;
            s.pending.clear();
            g.witnesses(n.table)
        } else {
            #[cfg(feature = "sparse-cells")]
            {
                std::mem::take(&mut s.pending)
            }
            #[cfg(not(feature = "sparse-cells"))]
            {
                std::mem::take(&mut s.pending).into_iter().collect()
            }
        };
        if full {
            s.epochs.clear();
            s.latest_witness_epoch = 0;
            if let Some(counts) = &mut s.epoch_counts {
                counts.clear();
            }
        }
        let mut old = if full {
            s.rows.take()
        } else {
            Entries::default()
        };
        for w in pending.drain(..) {
            let previous = if full {
                old.remove(&w)
            } else {
                s.rows.remove(&w)
            }.unwrap_or_default();
            #[cfg(feature = "sparse-cells")]
            let publication = previous.publication;
            let previous = previous.packet;
            if !full && let Some(p) = &previous {
                s.remove_epoch(p.row.epoch, w);
            }
            // A table with one compiled entry node has no sibling to consume
            // a shared decoded row before the next publication clears the cache.
            let row = if self.plan.tables[n.table].len() == 1 {
                self.stats.private_row_reads += 1;
                self.stats.row_decodes += 1;
                g.row(w)?.map(Rc::new)
            } else if let Some(row) = self.rows.get(&w) {
                row.clone()
            } else {
                self.stats.row_decodes += 1;
                let row = g.row(w)?.map(Rc::new);
                self.rows.insert(w, row.clone());
                row
            };
            let Some(row) = row.filter(|r| r.table == n.table && !r.hidden) else {
                self.stats.retired_packets += u64::from(previous.is_some());
                continue;
            };
            self.stats.predicate_checks += 1;
            if !n.literal_identity
                && let Some(_previous) = previous.as_ref().filter(|p| p.row.values == row.values)
            {
                self.stats.parameter_packets_reused += 1;
                s.insert_epoch(row.epoch, w);
                #[cfg(feature = "sparse-cells")]
                s.rows.insert(w, Stored { packet: Some(Packet { row }), publication });
                #[cfg(not(feature = "sparse-cells"))]
                s.rows.insert(
                    w,
                    Stored { packet: Some(Rc::new(Packet {
                        row,
                        values: _previous.values.clone(),
                    })) },
                );
                continue;
            }
            #[cfg(feature = "sparse-cells")]
            {
                let valid = n.checks.iter().all(|(col, check)| match check {
                    Arg::Slot(other) => row.values[*other] == row.values[*col],
                    Arg::Literal(v) => canon(v, &g.parents) == row.values[*col],
                });
                if valid {
                    s.insert_epoch(row.epoch, w);
                    s.rows.insert(w, Stored { packet: Some(Packet { row }), publication });
                } else {
                    self.stats.retired_packets += u64::from(previous.is_some());
                }
            }
            #[cfg(not(feature = "sparse-cells"))]
            {
                let mut values = vec![None; n.ports];
                let valid = n.args.iter().zip(row.values.iter()).all(|(a, v)| match a {
                    Arg::Literal(l) => canon(l, &g.parents) == *v,
                    Arg::Slot(i) => match &values[*i] {
                        Some(old) => old == v,
                        None => {
                            self.stats.parameters_copied += 1;
                            values[*i] = Some(v.clone());
                            true
                        }
                    },
                });
                if valid {
                    let values = if let Some(p) =
                        previous.as_ref().filter(|p| p.values.as_ref() == &values)
                    {
                        self.stats.parameter_packets_reused += 1;
                        p.values.clone()
                    } else {
                        Rc::new(values)
                    };
                    s.insert_epoch(row.epoch, w);
                    s.rows.insert(w, Stored { packet: Some(Rc::new(Packet { row, values })) });
                } else {
                    self.stats.retired_packets += u64::from(previous.is_some());
                }
            }
        }
        #[cfg(feature = "sparse-cells")]
        if !full { s.pending = pending; }
        self.stats.retired_packets += old.len() as u64;
        Ok(())
    }
    #[cfg(feature = "rhs-work-audit")]
    pub fn seed_deliveries(&self) -> u64 {
        self.stats.consumer_seed_deliveries
    }
    pub fn report(&self) -> J {
        #[allow(unused_mut)]
        let mut stats = json!(&self.stats);
        #[cfg(feature = "sparse-cells")]
        { stats["node_notifications"] = (self.stats.node_notifications
            + self.states.iter().map(|s|s.pending_count() as u64).sum::<u64>()).into(); }
        json!({"enabled":self.enabled,"nodes":self.plan.nodes.len(),"stats":stats,
            "seed_bytes":std::mem::size_of::<Seed>(),
            "live_packets":self.states.iter().map(|s|s.rows.len()).sum::<usize>(),
            "scope":"compiled Cell Entry projection, current row and publication location; consumer watermarks and residual/RHS remain source scheduled"})
    }
}

#[cfg(all(test,feature="sparse-cells"))]
mod pending_tests {
    use super::*;
    #[test]
    fn pending_counts_include_later_duplicates_only_once() {
        let mut s=State::default();
        s.pending.extend([Dependency::Function(2),Dependency::Function(1),Dependency::Function(2)]);
        assert_eq!(s.pending_count(),2);
        s.compact_pending();
        s.pending.extend([Dependency::Function(2),Dependency::Function(3)]);
        assert_eq!(s.pending_count(),3);
        s.compact_pending();
        assert_eq!(s.pending,vec![Dependency::Function(1),Dependency::Function(2),Dependency::Function(3)]);
    }
}
