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
    _domain: Rc<Vec<Dependency>>,
    rows: Rc<Vec<Row>>,
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
    ports: Vec<Option<Ports>>,
    published: Publication,
    groups: FxHashMap<usize, Groups>,
    stats: Vec<Stats>,
    profiling: bool,
}
impl Context {
    pub fn new(p: &Program, profiling: bool) -> Self {
        Self {
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
        serde_json::json!({"demanded_keys":demanded_keys,"parent_refs":parent_refs,"mode":"neighbors","publication":self.published,"timed_maintenance":self.profiling,"rules":rules})
    }
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
        domain: &Rc<Vec<Dependency>>,
    ) -> Access {
        if domain.len() < 2 || domain.len() > ROW_LIMIT {
            return Access::Direct;
        }
        let cache = self.groups.entry(t).or_default();
        let stats = &mut self.stats[rid];
        let version = g.query_versions[t];
        let id = Rc::as_ptr(domain) as usize;
        if version == cache.version
            && let Some(hit) = cache.by_domain.get(&id)
        {
            stats.group_hits += 1;
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
        domain: Rc<Vec<Dependency>>,
        mut rows: Vec<Row>,
    ) {
        let clock = self.profiling.then(Instant::now);
        rows.sort_unstable_by_key(|r| (r.epoch, r.witness));
        let cache = self.groups.get_mut(&table).unwrap();
        cache.rows += domain.len();
        self.stats[rid].group_builds += 1;
        self.stats[rid].build_visits += domain.len() as u64;
        cache.by_domain.insert(
            Rc::as_ptr(&domain) as usize,
            Neighborhood {
                _domain: domain,
                rows: Rc::new(rows),
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
}

#[cfg(test)]
mod tests {
    use super::*;

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
                &Rc::new(g.witnesses(table))).unwrap();
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
            &g, &mut columns, Some(&mut ranges), &mut ctx, |_, _, _| {}).unwrap();
        assert_eq!(ctx.ports[0].as_ref().unwrap().version, g.query_versions[0]);
        assert_eq!(ctx.ports[1].as_ref().unwrap().version, old[1]);
        assert_ne!(old[1], g.query_versions[1]);
        assert_eq!(ctx.ports[1].as_ref().unwrap().rows[&7].as_ref().unwrap().values[1], Value::Int(1));
        g.changes.clear();
        std::mem::swap(&mut g.changes, &mut deferred);
        publication.publish(
            #[cfg(feature = "family-survey")] (&mut survey, false),
            &g, &mut columns, Some(&mut ranges), &mut ctx, |_, _, _| {}).unwrap();
        for table in 0..2 {
            assert_eq!(ctx.point(&mut g, 0, table, &key).unwrap().unwrap().values[1], Value::Int(2));
            let selected = ranges.select(&g, table, (0, key[0].clone()), 1, Bound::Lt, 2,
                &Rc::new(g.witnesses(table))).unwrap();
            assert!(selected.is_empty());
        }
        assert_eq!(ranges.stats.builds, 2, "published axes survive both batches");
        assert_eq!(ranges.stats.update_rows, 2);
        assert_eq!(json!(&publication)["row_reads"], 2, "all read consumers share each row");
        g.changes.clear();
        g.hide(0, &key, true).unwrap();
        publication.publish(
            #[cfg(feature = "family-survey")] (&mut survey, false),
            &g, &mut columns, Some(&mut ranges), &mut ctx, |_, _, _| {}).unwrap();
        assert!(ctx.point(&mut g, 0, 0, &key).unwrap().is_none());
        g.changes.clear();
        g.set_function(0, key.to_vec(), Value::Int(3)).unwrap();
        publication.publish(
            #[cfg(feature = "family-survey")] (&mut survey, false),
            &g, &mut columns, Some(&mut ranges), &mut ctx, |_, _, _| {}).unwrap();
        assert_eq!(ctx.point(&mut g, 0, 0, &key).unwrap().unwrap().values[1], Value::Int(3));
        assert_eq!(ctx.stats[0].point_probes, 2, "updates preserve positive and negative reads");
    }
}
