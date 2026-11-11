//! Demand-driven context for attributes read on a constructor's children.
//! Only uncovered delta entries reach these caches, inside the ordinary kernel.
use crate::{
    graph::{Dependency, Graph, Row},
    program::*,
    value::Value,
};
use rustc_hash::FxHashMap;
use serde::Serialize;
use std::{rc::Rc, time::Instant};

#[derive(Clone, Debug, Serialize)]
pub(crate) struct Plan {
    pub structure: usize,
    pub attribute: usize,
    pub children: Vec<(usize, usize)>, // (LHS atom, constructor column)
    pub pivots: Vec<usize>,
}

pub(crate) fn derive(p: &Program) -> Vec<Option<Plan>> {
    p.rules
        .iter()
        .enumerate()
        .map(|(rid, r)| {
            let write = p.writes[rid].as_ref()?;
            let [Arg::Slot(parent)] = write.key.as_slice() else {
                return None;
            };
            let mut constructors = r
                .query
                .iter()
                .enumerate()
                .filter(|(_, a)| matches!(a.call,Call::Table(t) if p.tables[t].constructor));
            let (structure, a) = constructors.next()?;
            let (result, fields) = a.args.split_last()?;
            if constructors.next().is_some() || result != &Arg::Slot(*parent) || !r.seminaive {
                return None;
            }
            let mut children = vec![];
            for (i, atom) in r.query.iter().enumerate() {
                if i == structure {
                    continue;
                }
                if let Call::Table(t) = atom.call {
                    let [Arg::Slot(_), _] = atom.args.as_slice() else {
                        return None;
                    };
                    if t != write.table || p.tables[t].schema[0]["kind"] != "eq" {
                        return None;
                    }
                    let link = p.cell_links[rid].between(structure, i)?;
                    let column = link.columns.iter().find(|(_, to, _)| *to == 0)?.2;
                    // Neighbor queries require a constructor input, not its result.
                    if column >= fields.len() { return None; }
                    children.push((i, column));
                }
            }
            // Each expansion must enumerate this constructor through a bound expression.
            let pivots = p.kernels[rid]
                .iter()
                .enumerate()
                .filter_map(|(pivot, k)| {
                    let k = k.as_ref()?;
                    k.query.steps
                        .iter()
                        .all(|s| {
                            !matches!(s.access(), crate::cell::Access::Expand)
                                || s.atom == structure
                        })
                        .then_some(pivot)
                })
                .collect::<Vec<_>>();
            (!children.is_empty() && !pivots.is_empty()).then_some(Plan {
                pivots,
                structure,
                attribute: write.table,
                children,
            })
        })
        .collect()
}

#[derive(Default, Serialize)]
pub(crate) struct Stats {
    pub spine_entries: u64,
    pub residual_entries: u64,
    pub seeds: u64,
    pub bindings: u64,
    pub point_hits: u64,
    pub point_probes: u64,
    pub expansion_visits: u64,
    pub group_hits: u64,
    pub cached_parent_visits: u64,
    pub group_builds: u64,
    pub build_visits: u64,
    pub owner_skips: u64,
    pub maintenance_ns: u64,
    resets: u64,
}
#[derive(Default)]
struct Ports {
    version: u64,
    rows: FxHashMap<u64, Option<Row>>,
    keys: FxHashMap<usize, u64>,
}
#[derive(Default, Serialize)]
struct Publication {
    checked: u64,
    refreshed: u64,
    retired: u64,
    cleared: u64,
    nanoseconds: u64,
}
struct Neighborhood {
    // Holding the original domain prevents allocator address reuse.
    _domain: crate::query::DomainRc<Vec<Dependency>>,
    rows: Rc<Vec<Row>>,
    #[cfg(feature = "cell-absorption")]
    absorption: Condition,
}
/// A positive bound proves the entire domain. A single actual output can only
/// reject that proof attempt; it never authorizes skipping a source effect.
#[cfg(feature = "cell-absorption")]
#[derive(Clone, Copy, Default)]
enum Condition {
    #[default]
    Empty,
    Upper { rule: usize, key: u64, value: i64 },
    Rejected { rule: usize, key: u64, output: usize },
}
/// This is a condition on one existing Cell query, not another consumer graph.
/// The only effect copies the input attribute into a permanent min function.
#[cfg(feature = "cell-absorption")]
#[derive(Clone, Copy, Debug)]
pub(crate) struct Absorption {
    attribute: usize,
    input_column: usize,
}
#[cfg(feature = "cell-absorption")]
pub(crate) fn compile_absorption(p: &mut Program) {
    for rid in 0..p.rules.len() {
        if let Some((pivot, plan)) = absorption(p, rid) {
            Rc::make_mut(p.kernels[rid][pivot].as_mut().unwrap()).absorption = Some(Box::new(plan));
        }
    }
}
#[cfg(feature = "cell-absorption")]
fn absorption(p: &Program, rid: usize) -> Option<(usize, Absorption)> {
    let r = &p.rules[rid];
    if !r.seminaive || r.query.len() != 2 { return None; }
    let w = p.writes[rid].as_ref()?;
    if !w.prefix.is_empty() || p.physical.merges[w.table] != Some(crate::physical_plan::ScalarMerge::Min) {
        return None;
    }
    // Deletion anywhere in the program would invalidate an old scalar bound.
    if p.templates.iter().any(|t| t.ops.iter().any(|op| matches!(op, Op::Hide(t,_,_) if *t == w.table))) {
        return None;
    }
    for pivot in 0..2 {
        let input = &r.query[pivot];
        if !matches!(input.call, Call::Table(t) if t == w.table) { continue; }
        let [Arg::Slot(key), Arg::Slot(value)] = input.args.as_slice() else { continue; };
        let ctor = &r.query[1-pivot];
        let Call::Table(table) = ctor.call else { continue; };
        if !p.tables[table].constructor || !p.tables[table].virtual_fact { continue; }
        let Some((Arg::Slot(result), fields)) = ctor.args.split_last() else { continue; };
        if w.key != [Arg::Slot(*result)] || w.value != Arg::Slot(*value) { continue; }
        let slots = ctor.args.iter().map(|a| match a { Arg::Slot(s) => Some(*s), _ => None })
            .collect::<Option<std::collections::BTreeSet<_>>>()?;
        if slots.len() != ctor.args.len() || slots.contains(value) { continue; }
        let Some(column) = fields.iter().position(|a| a == &Arg::Slot(*key)) else { continue; };
        let kernel = p.kernels[rid][pivot].as_ref()?;
        if kernel.query.steps.len() != 1 || kernel.query.steps[0].expansion.is_none() { continue; }
        return Some((pivot, Absorption { attribute: w.table, input_column: column }));
    }
    None
}
/// Stack-only reads of the active Cell's seed. No instance binding is retained.
#[cfg(feature = "cell-absorption")]
#[derive(Clone, Copy)]
pub(crate) struct Activated<'a> {
    plan: &'a Absorption,
    key: u64,
    value: i64,
    watermark: u64,
}
#[cfg(feature = "cell-absorption")]
impl Absorption {
    pub(crate) fn activate<'a>(&'a self, g: &Graph, seed: &Row, watermark: u64) -> Option<Activated<'a>> {
        if seed.table != self.attribute || seed.hidden || seed.epoch < watermark
            || g.has_visibility_changes(self.attribute) { return None; }
        let [Value::Eq(key), Value::Int(value)] = seed.values.as_ref() else { return None; };
        Some(Activated { plan:self, key:*key, value:*value, watermark })
    }
}
#[cfg(feature = "cell-absorption")]
#[derive(Default, Serialize)]
struct AbsorptionStats {
    checks: u64,
    reused_bounds: u64,
    bound_builds: u64,
    output_probes: u64,
    bound_rejections: u64,
    rejection_reads: u64,
    rejection_hits: u64,
    missing_outputs: u64,
    fresh_constructor_fallbacks: u64,
    groups_absorbed: u64,
    matches_absorbed: u64,
    single_candidates: u64,
    single_checks: u64,
    single_output_probes: u64,
    single_absorbed: u64,
    single_missing_outputs: u64,
    single_fresh_fallbacks: u64,
    pending: Vec<usize>,
}
#[derive(Default)]
struct Groups {
    version: u64,
    rows: usize,
    by_domain: FxHashMap<usize, Neighborhood>,
}
// Storage is demand bounded per shared input table, independent of root-table size.
const KEY_LIMIT: usize = 4096;
const ROW_LIMIT: usize = 65536;
pub(crate) struct Context {
    #[cfg(feature = "cell-absorption")]
    pub(crate) absorption_enabled: bool,
    #[cfg(feature = "cell-absorption")]
    absorption_stats: AbsorptionStats,
    ports: Vec<Option<Ports>>,
    published: Publication,
    groups: FxHashMap<usize, Groups>,
    stats: Vec<Stats>,
    profiling: bool,
}
impl Context {
    pub fn new(p: &Program, profiling: bool) -> Self {
        Self {
            #[cfg(feature = "cell-absorption")]
            absorption_enabled: false,
            #[cfg(feature = "cell-absorption")]
            absorption_stats: AbsorptionStats { pending: vec![0; p.rules.len()], ..Default::default() },
            ports: (0..p.tables.len()).map(|_| None).collect(),
            published: Publication::default(),
            groups: FxHashMap::default(),
            stats: (0..p.rules.len()).map(|_| Stats::default()).collect(),
            profiling,
        }
    }
    pub fn stats(&mut self, rid: usize) -> &mut Stats {
        &mut self.stats[rid]
    }
    pub fn report(&self, p: &Program) -> serde_json::Value {
        let rules = p
            .neighbor_plans
            .iter()
            .enumerate()
            .filter_map(|(r, plan)| {
                Some((
                    r,
                    serde_json::json!({"plan":plan.as_ref()?,"stats":self.stats[r]}),
                ))
            })
            .collect::<std::collections::BTreeMap<_, _>>();
        let demanded_keys: usize = self
            .ports
            .iter()
            .flatten()
            .map(|cache| cache.rows.len())
            .sum();
        let parent_refs: usize = self.groups.values().map(|cache| cache.rows).sum();
        #[allow(unused_mut)]
        let mut report = serde_json::json!({"demanded_keys":demanded_keys,"parent_refs":parent_refs,"mode":"neighbors","publication":self.published,"timed_maintenance":self.profiling,"rules":rules});
        #[cfg(feature = "cell-absorption")]
        {
          let kernels = p.kernels.iter().flatten().flatten();
          let entries = kernels.clone().count();
          let plans = kernels.filter(|k| k.absorption.is_some()).count();
          report["absorption"] = serde_json::json!({"enabled":self.absorption_enabled,
            "plans":plans, "capability_entries":entries,
            "compiled_capability_bytes":entries*std::mem::size_of::<Option<Box<Absorption>>>() + plans*std::mem::size_of::<Absorption>(),
            "removed_context_plan_bytes":p.rules.len()*std::mem::size_of::<Option<(usize,usize,usize,usize)>>(),
            "condition_bytes_per_neighborhood":std::mem::size_of::<Condition>(),
            "stats":self.absorption_stats}); }
        report
    }
    /// A current cached constructor domain plus a permanent min upper bound
    /// proves that every covered source effect is already absorbed. No logical
    /// mutation or new producer evidence is published for those omitted effects.
    #[cfg(feature = "cell-absorption")]
    fn absorbs(g: &Graph, rid: usize, active: Activated<'_>, group: &mut Neighborhood,
        stats: &mut AbsorptionStats) -> bool {
        let Activated { plan, key:key_id, value:candidate, watermark } = active;
        let key = Value::Eq(key_id);
        stats.checks += 1;
        // This pivot must own the entire domain; another fresh constructor may
        // also have a Spine continuation and must keep ordinary winner selection.
        if group.rows.last().is_none_or(|r| r.epoch >= watermark) {
            stats.fresh_constructor_fallbacks += 1;
            return false;
        }
        let upper = if let Condition::Upper { rule, key, value } = group.absorption
            && rule == rid && key == key_id {
            stats.reused_bounds += 1;
            value
        } else {
            if let Condition::Rejected { rule, key, output } = group.absorption
                && rule == rid && key == key_id {
                stats.rejection_reads += 1;
                // Borrow the actual prior lookup result, without rebuilding a
                // key or finding its row again. Even a stale rejection merely
                // retains ordinary matching; only the full scan below proves
                // an absorption. Missing/retired results must allow a retry.
                if g.absorption_rejection(plan.attribute, output)
                    .is_some_and(|value| value > candidate) {
                    stats.rejection_hits += 1;
                    return false;
                }
            }
            let mut upper = i64::MIN;
            for row in group.rows.iter() {
                // Candidate domains can be supersets. Cache a bound only for
                // an exact one-key domain, so its length is the match count.
                if row.values.get(plan.input_column) != Some(&key) { return false; }
                stats.output_probes += 1;
                let Some((output, value)) = g.absorption_value(plan.attribute, row.values.last().unwrap()) else {
                    stats.missing_outputs += 1;
                    return false;
                };
                if value > candidate {
                    stats.bound_rejections += 1;
                    group.absorption = Condition::Rejected { rule: rid, key: key_id, output };
                    return false;
                }
                upper = upper.max(value);
            }
            stats.bound_builds += 1;
            group.absorption = Condition::Upper { rule: rid, key: key_id, value: upper };
            upper
        };
        if candidate < upper {
            // A smaller old bound is still valid; refreshing is optional and
            // charged. Do it only on a later visit, not twice in this query.
            group.absorption = Condition::Empty;
            return false;
        }
        stats.groups_absorbed += 1;
        stats.matches_absorbed += group.rows.len() as u64;
        stats.pending[rid] += group.rows.len();
        true
    }
    /// The matcher has one actual constructor candidate and has checked all of
    /// its fields. It need not allocate a cached Neighborhood or a binding to
    /// prove this single permanent min write is already absorbed at Run start.
    #[cfg(feature = "cell-absorption")]
    pub(crate) fn absorbs_single(&mut self, g: &Graph, rid: usize, active: Activated<'_>, row: &Row) -> bool {
        let Activated { plan, key, value:candidate, watermark } = active;
        self.absorption_stats.single_candidates += 1;
        if row.hidden || row.values.get(plan.input_column) != Some(&Value::Eq(key)) { return false; }
        let stats = &mut self.absorption_stats;
        stats.single_checks += 1;
        if row.epoch >= watermark {
            stats.single_fresh_fallbacks += 1;
            return false;
        }
        stats.single_output_probes += 1;
        let Some((_, value)) = g.absorption_value(plan.attribute, row.values.last().unwrap()) else {
            stats.single_missing_outputs += 1;
            return false;
        };
        if value > candidate { return false; }
        stats.single_absorbed += 1;
        stats.matches_absorbed += 1;
        stats.pending[rid] += 1;
        true
    }
    #[cfg(feature = "cell-absorption")]
    pub(crate) fn pending_absorbed(&self, rule: usize) -> usize { self.absorption_stats.pending[rule] }
    #[cfg(feature = "cell-absorption")]
    pub(crate) fn take_absorbed(&mut self, rule: usize) -> usize { std::mem::take(&mut self.absorption_stats.pending[rule]) }
    pub fn point(
        &mut self,
        g: &mut Graph,
        rid: usize,
        t: usize,
        key: &[Value],
    ) -> Result<Option<Row>> {
        #[cfg(feature = "family-overlap")]
        let point_clock = crate::family_overlap::clock();
        let [Value::Eq(id)] = key else {
            return Err("expected compiler-proved expression key".into());
        };
        let cache = self.ports[t].get_or_insert_with(|| {
            Ports {
                version: g.query_versions[t],
                ..Default::default()
            }
        });
        let stats = &mut self.stats[rid];
        if cache.version == g.query_versions[t]
            && let Some(row) = cache.rows.get(id)
        {
            stats.point_hits += 1;
            #[cfg(feature = "family-overlap")]
            crate::family_overlap::physical(t, 1, point_clock, || {
                key.iter().cloned().enumerate().collect()
            });
            return Ok(row.clone());
        }
        let clock = self.profiling.then(Instant::now);
        if cache.version != g.query_versions[t] || cache.rows.len() >= ROW_LIMIT {
            stats.resets += 1;
            cache.version = g.query_versions[t];
            cache.rows.clear();
            cache.keys.clear();
        }
        stats.point_probes += 1;
        g.stats.residual_candidates += 1;
        let row = g.lookup_canonical(t, key)?;
        if let Some(Row {
            witness: Dependency::Function(i),
            ..
        }) = &row
        {
            cache.keys.insert(*i, *id);
        }
        cache.rows.insert(*id, row.clone());
        if let Some(clock) = clock {
            stats.maintenance_ns += clock.elapsed().as_nanos() as u64;
        }
        Ok(row)
    }
    /// Borrow just this table's demanded Cell reads at the repaired publication
    /// boundary. Completion advances only the table whose changes were delivered.
    pub(crate) fn writer(&mut self, table: usize) -> Option<PortWriter<'_>> {
        let cache = self.ports[table].as_mut()?;
        if cache.rows.is_empty() { return None; }
        Some(PortWriter { table, cache, published: &mut self.published, profiling: self.profiling })
    }
    pub fn neighborhood(
        &mut self,
        g: &Graph,
        rid: usize,
        t: usize,
        domain: &crate::query::DomainRc<Vec<Dependency>>,
        #[cfg(feature = "cell-absorption")] absorption: Option<Activated<'_>>,
    ) -> Access {
        if domain.len() < 2 || domain.len() > ROW_LIMIT {
            return Access::Direct;
        }
        let cache = self.groups.entry(t).or_default();
        let stats = &mut self.stats[rid];
        let version = g.query_versions[t];
        let id = crate::query::DomainRc::as_ptr(domain) as usize;
        if version == cache.version
            && let Some(hit) = cache.by_domain.get_mut(&id)
        {
            stats.group_hits += 1;
            #[cfg(feature = "cell-absorption")]
            if let Some(active) = absorption
                && Self::absorbs(g, rid, active, hit, &mut self.absorption_stats) {
                return Access::Absorbed;
            }
            return Access::Cached(hit.rows.clone());
        }
        let clock = self.profiling.then(Instant::now);
        if cache.version != version
            || cache.rows + domain.len() > ROW_LIMIT
            || cache.by_domain.len() >= KEY_LIMIT
        {
            stats.resets += 1;
            cache.by_domain.clear();
            cache.rows = 0;
            cache.version = version;
        }
        let rows = Vec::with_capacity(domain.len());
        if let Some(clock) = clock {
            stats.maintenance_ns += clock.elapsed().as_nanos() as u64;
        }
        Access::Build(rows)
    }
    pub fn finish_group(
        &mut self,
        rid: usize,
        table: usize,
        domain: crate::query::DomainRc<Vec<Dependency>>,
        mut rows: Vec<Row>,
    ) {
        let clock = self.profiling.then(Instant::now);
        rows.sort_unstable_by_key(|r| (r.epoch, r.witness));
        let cache = self.groups.get_mut(&table).unwrap();
        cache.rows += domain.len();
        self.stats[rid].group_builds += 1;
        self.stats[rid].build_visits += domain.len() as u64;
        cache.by_domain.insert(
            crate::query::DomainRc::as_ptr(&domain) as usize,
            Neighborhood {
                _domain: domain,
                rows: Rc::new(rows),
                #[cfg(feature = "cell-absorption")]
                absorption: Condition::Empty,
            },
        );
        if let Some(clock) = clock {
            self.stats[rid].maintenance_ns += clock.elapsed().as_nanos() as u64;
        }
    }
}
/// Same table-scoped lifecycle as the query-column writer: update from the
/// shared current row, then finish explicitly after every change was delivered.
/// Dropping an unfinished writer never certifies a newer table version.
pub(crate) struct PortWriter<'a> {
    table: usize,
    cache: &'a mut Ports,
    published: &'a mut Publication,
    profiling: bool,
}
#[cfg(feature = "parallel-publication")]
pub(crate) struct PublicationTask { table:usize, cache:Ports, published:Publication, profiling:bool }
#[cfg(feature = "parallel-publication")]
impl PublicationTask {
    pub fn update(&mut self,witness:Dependency,row:Option<&Row>) {
        PortWriter {table:self.table,cache:&mut self.cache,published:&mut self.published,
            profiling:self.profiling}.update(witness,row);
    }
    pub fn finish(&mut self,version:u64) {self.cache.version=version;}
}
#[cfg(feature = "parallel-publication")]
impl Context {
    pub(crate) fn take_publication(&mut self,table:usize)->Option<PublicationTask> {
        if self.ports[table].as_ref()?.rows.is_empty() {return None;}
        Some(PublicationTask {table,cache:self.ports[table].take()?,published:Default::default(),profiling:self.profiling})
    }
    pub(crate) fn has_publication(&self,table:usize)->bool {
        self.ports[table].as_ref().is_some_and(|p|!p.rows.is_empty())
    }
    pub(crate) fn restore_publication(&mut self,task:PublicationTask) {
        self.published.checked+=task.published.checked;
        self.published.refreshed+=task.published.refreshed;
        self.published.retired+=task.published.retired;
        self.published.nanoseconds+=task.published.nanoseconds;
        self.ports[task.table]=Some(task.cache);
    }
}
impl PortWriter<'_> {
    /// A demanded but absent key must see an insertion. Replacement and
    /// retirement can arrive in either order after same-key coalescence.
    pub(crate) fn update(&mut self, fact: Dependency, row: Option<&Row>) {
        let cache = &mut self.cache;
        let Dependency::Function(i) = fact else {
            return;
        };
        let clock = self.profiling.then(Instant::now);
        self.published.checked += 1;
        let current =
            row.filter(|r| r.table == self.table && !r.hidden)
                .and_then(|r| match r.values.first() {
                    Some(Value::Eq(k)) => Some((*k, r)),
                    _ => None,
                });
        if let Some(&old) = cache.keys.get(&i)
            && current.is_none_or(|(k, _)| k != old)
        {
            cache.keys.remove(&i);
            if let Some(slot) = cache.rows.get_mut(&old)
                && slot.as_ref().is_some_and(|r| r.witness == fact)
            {
                *slot = None;
                self.published.retired += 1;
            }
        }
        if let Some((k, row)) = current
            && let Some(slot) = cache.rows.get_mut(&k)
        {
            *slot = Some(row.clone());
            cache.keys.insert(i, k);
            self.published.refreshed += 1;
        }
        if let Some(clock) = clock {
            self.published.nanoseconds += clock.elapsed().as_nanos() as u64;
        }
    }
    pub(crate) fn finish(self, version: u64) {
        self.cache.version = version;
    }
}
pub(crate) enum Access {
    Direct,
    Build(Vec<Row>),
    Cached(Rc<Vec<Row>>),
    #[cfg(feature = "cell-absorption")]
    Absorbed,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(feature = "cell-absorption")]
    #[test]
    fn cached_condition_keeps_its_key_epoch_and_domain_generation() {
        use crate::graph::FactRef;
        use serde_json::json;
        let tables = [json!({"name":"Get","schema":[{"kind":"eq"},{"kind":"i64"},{"kind":"eq"}],
            "constructor":true,"virtual_fact":true,"internal":false,"merge":null}),
            json!({"name":"Cost","schema":[{"kind":"eq"},{"kind":"i64"}],
            "constructor":false,"virtual_fact":false,"internal":false,
            "merge":{"call":{"primitive":"min","output":"i64"},"args":[{"var":"old"},{"var":"new"}]}})];
        let p = serde_json::from_value(json!({
            "multi_stage":crate::multistage::MultiStage::default(),
            "entry_schedule":crate::entry_schedule::Plan::default(),"tables":tables,"templates":[],"rules":[],
            "sets":{},"control":[],"initial":[],"table_templates":[],"artifact":{}
        })).unwrap();
        let mut g = Graph::new(p).unwrap();
        g.merge_programs_enabled = false;
        for (key,value) in [(8,3),(9,4)] { g.set_function(1,vec![Value::Eq(key)],Value::Int(value)).unwrap(); }
        let rows: Vec<_> = [8,9].into_iter().enumerate().map(|(i,key)| Row { table:0,
            values:crate::graph::row_fields(vec![Value::Eq(7),Value::Int(i as i64),Value::Eq(key)]),
            epoch:1,witness:Dependency::Fact(FactRef { cell:i as u32,op:0 }),hidden:false }).collect();
        let domain: crate::query::DomainRc<Vec<Dependency>> = crate::query::DomainRc::new(rows.iter().map(|r|r.witness).collect());
        let mut c = Context::new(&g.program,false);
        c.absorption_enabled = true;
        let plan = Absorption { attribute:1,input_column:0 };
        c.stats.push(Stats::default());
        let rows = Rc::new(rows);
        c.absorption_stats.pending.push(0);
        c.groups.insert(0, Groups { version:g.query_versions[0], rows:2,
            by_domain: [(crate::query::DomainRc::as_ptr(&domain) as usize,Neighborhood { _domain:domain.clone(),rows:rows.clone(),absorption:Condition::Empty })].into_iter().collect() });
        let check = |c: &mut Context, g: &Graph, seed: &Row, watermark| matches!(
            c.neighborhood(g,0,0,&domain,plan.activate(g,seed,watermark)), Access::Absorbed);
        let mut seed = Row { table:1, values:crate::graph::row_fields(vec![Value::Eq(7),Value::Int(10)]),
            epoch:5,witness:Dependency::Function(20),hidden:false };
        assert!(check(&mut c,&g,&seed,3));
        let probes = c.absorption_stats.output_probes;
        // Smaller outputs preserve an old upper bound without new subscriptions.
        g.set_function(1,vec![Value::Eq(8)],Value::Int(1)).unwrap();
        assert!(check(&mut c,&g,&seed,3));
        assert_eq!(c.absorption_stats.output_probes,probes);
        seed.values = crate::graph::row_fields(vec![Value::Eq(99),Value::Int(10)]);
        assert!(!check(&mut c,&g,&seed,3),"a broad domain pointer is not an input identity");
        seed.values = crate::graph::row_fields(vec![Value::Eq(7),Value::Int(10)]);
        assert!(!check(&mut c,&g,&seed,1),"fresh constructors keep winner selection");
        g.query_versions[0] += 1;
        assert!(!check(&mut c,&g,&seed,3),"old membership cannot close a new domain");
        assert_eq!(c.absorption_stats.matches_absorbed,4);

        // A failed whole-domain condition only needs one current counterexample.
        // It stops scanning immediately, then reads the actual output directly
        // on the next attempt. Once that output improves, retry the full proof.
        c.finish_group(0,0,domain.clone(),rows.as_ref().clone());
        let probes = c.absorption_stats.output_probes;
        seed.values = crate::graph::row_fields(vec![Value::Eq(7),Value::Int(0)]);
        assert!(!check(&mut c,&g,&seed,3));
        assert_eq!(c.absorption_stats.output_probes-probes,1,"do not read the rest of a rejected group");
        seed.values = crate::graph::row_fields(vec![Value::Eq(7),Value::Int(-1)]);
        assert!(!check(&mut c,&g,&seed,3));
        assert_eq!(c.absorption_stats.output_probes-probes,1,"reuse the actual output address");
        assert_eq!(c.absorption_stats.rejection_hits,1);
        g.set_function(1,vec![Value::Eq(8)],Value::Int(-2)).unwrap();
        assert!(!check(&mut c,&g,&seed,3),"another output still rejects the proof");
        g.set_function(1,vec![Value::Eq(9)],Value::Int(-3)).unwrap();
        assert!(check(&mut c,&g,&seed,3),"a rejection must not become a permanent negative cache");
        assert_eq!(c.absorption_stats.output_probes-probes,5);
        assert_eq!(c.absorption_stats.rejection_reads,3);
        assert_eq!(std::mem::size_of::<Condition>(),std::mem::size_of::<Option<(usize,u64,i64)>>());
    }

    #[test]
    fn replacement_and_retirement_commute_for_a_subscribed_key() {
        let original = Row {
            table: 0,
            values: crate::graph::row_fields(vec![Value::Eq(7), Value::Int(1)]),
            epoch: 1,
            witness: Dependency::Function(3),
            hidden: false,
        };
        let replacement = Row {
            values: crate::graph::row_fields(vec![Value::Eq(7), Value::Int(9)]),
            epoch: 2,
            witness: Dependency::Function(4),
            ..original.clone()
        };
        for insert_first in [false, true] {
            let mut cache = Ports::default();
            cache.rows.insert(7, Some(original.clone()));
            cache.keys.insert(3, 7);
            let mut ctx = Context {
                #[cfg(feature = "cell-absorption")]
                absorption_enabled: false,
                #[cfg(feature = "cell-absorption")]
                absorption_stats: Default::default(),
                ports: vec![Some(cache)],
                groups: Default::default(),
                published: Default::default(),
                stats: vec![],
                profiling: false,
            };
            let mut writer = ctx.writer(0).unwrap();
            if insert_first {
                writer.update(replacement.witness, Some(&replacement));
            }
            writer.update(original.witness, None);
            if !insert_first {
                writer.update(replacement.witness, Some(&replacement));
            }
            writer.finish(2);
            let ports = ctx.ports[0].as_ref().unwrap();
            assert_eq!(ports.version, 2);
            assert_eq!(
                ports.rows[&7].as_ref().unwrap().witness,
                replacement.witness
            );
            assert_eq!(ports.keys.len(), 1);
            assert_eq!(ports.keys[&4], 7);
        }
    }

    #[test]
    fn shared_publication_finishes_only_delivered_tables_and_refreshes_absence() {
        use crate::{change_batch::{ChangeBatch, Publication}, physical_plan::Bound,
                    query::QueryIndexes, range_index::RangeIndex};
        use serde_json::json;
        let tables = ["left", "right"].map(|name| json!({
            "name":name,"schema":[{"kind":"eq","name":"E"},{"kind":"i64","name":"i64"}],
            "constructor":false,"virtual_fact":false,"internal":false,"merge":{"var":"new"}
        }));
        let p = serde_json::from_value(json!({
            "multi_stage":crate::multistage::MultiStage::default(),
            "entry_schedule":crate::entry_schedule::Plan::default(),"tables":tables,"templates":[],"rules":[],
            "sets":{},"control":[],"initial":[],"table_templates":[],"artifact":{}
        })).unwrap();
        let mut g = Graph::new(p).unwrap();
        g.merge_programs_enabled = false;
        let mut ctx = Context::new(&g.program, false);
        ctx.stats.push(Stats::default());
        let mut columns = QueryIndexes::default();
        let mut ranges = RangeIndex::default();
        let mut publication = Publication::default();
        #[cfg(feature = "family-survey")]
        let mut survey = crate::family_survey::Survey::new(&g.program);
        let key = [Value::Eq(7)];
        for table in 0..2 {
            g.set_function(table, key.to_vec(), Value::Int(1)).unwrap();
            assert!(ctx.point(&mut g, 0, table, &key).unwrap().is_some());
            columns.ensure(&g, table).unwrap();
            ranges.select(&g, table, (0, key[0].clone()), 1, Bound::Lt, 10,
                &crate::query::DomainRc::new(g.witnesses(table))).unwrap();
        }
        let old = g.query_versions.clone();
        g.changes.clear();
        g.changes.enable_split();
        let mut deferred = ChangeBatch::new(2);
        deferred.enable_split();
        for table in 0..2 { g.set_function(table, key.to_vec(), Value::Int(2)).unwrap(); }
        g.changes.defer_unready(&[true, false], &mut deferred);
        publication.publish(
            #[cfg(feature = "family-survey")] (&mut survey, false),
            &g, &mut columns, Some(&mut ranges), &mut ctx,
            #[cfg(feature = "parallel-publication")] None, |_, _, _| {}).unwrap();
        assert_eq!(ctx.ports[0].as_ref().unwrap().version, g.query_versions[0]);
        assert_eq!(ctx.ports[1].as_ref().unwrap().version, old[1]);
        assert_ne!(old[1], g.query_versions[1]);
        assert_eq!(ctx.ports[1].as_ref().unwrap().rows[&7].as_ref().unwrap().values[1], Value::Int(1));
        g.changes.clear();
        std::mem::swap(&mut g.changes, &mut deferred);
        publication.publish(
            #[cfg(feature = "family-survey")] (&mut survey, false),
            &g, &mut columns, Some(&mut ranges), &mut ctx,
            #[cfg(feature = "parallel-publication")] None, |_, _, _| {}).unwrap();
        for table in 0..2 {
            assert_eq!(ctx.point(&mut g, 0, table, &key).unwrap().unwrap().values[1], Value::Int(2));
            let selected = ranges.select(&g, table, (0, key[0].clone()), 1, Bound::Lt, 2,
                &crate::query::DomainRc::new(g.witnesses(table))).unwrap();
            assert!(selected.is_empty());
        }
        assert_eq!(ranges.stats.builds, 2, "published axes survive both batches");
        assert_eq!(ranges.stats.update_rows, 2);
        assert_eq!(json!(&publication)["row_reads"], 2, "all read consumers share each row");
        g.changes.clear();
        g.hide(0, &key, true).unwrap();
        publication.publish(
            #[cfg(feature = "family-survey")] (&mut survey, false),
            &g, &mut columns, Some(&mut ranges), &mut ctx,
            #[cfg(feature = "parallel-publication")] None, |_, _, _| {}).unwrap();
        assert!(ctx.point(&mut g, 0, 0, &key).unwrap().is_none());
        g.changes.clear();
        g.set_function(0, key.to_vec(), Value::Int(3)).unwrap();
        publication.publish(
            #[cfg(feature = "family-survey")] (&mut survey, false),
            &g, &mut columns, Some(&mut ranges), &mut ctx,
            #[cfg(feature = "parallel-publication")] None, |_, _, _| {}).unwrap();
        assert_eq!(ctx.point(&mut g, 0, 0, &key).unwrap().unwrap().values[1], Value::Int(3));
        assert_eq!(ctx.stats[0].point_probes, 2, "updates preserve positive and negative reads");
    }
}
