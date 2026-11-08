//! A Cell's own unions and constructor closure select newly born rows whose
//! reverse subscriptions can wait for its first completion boundary. The
//! completion list is consumed once; it is never indexed by equality class.
use super::*;
use std::rc::Rc;

#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Plan {
    templates: Vec<Option<TemplatePlan>>,
    selected: BTreeSet<usize>,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
struct TemplatePlan {
    unions: Vec<(Arg, Arg)>,
    classes: Vec<Vec<usize>>,
    ports: BTreeMap<usize, Vec<usize>>,
    obligations: BTreeMap<usize, Vec<(Arg, Arg)>>,
}
#[derive(Default)]
struct Symbols {
    parents: Vec<usize>,
    literals: BTreeMap<Value, usize>,
}
impl Symbols {
    fn root(&self, mut i: usize) -> usize {
        while self.parents[i] != i {
            i = self.parents[i];
        }
        i
    }
    fn union(&mut self, a: usize, b: usize) -> bool {
        let (a, b) = (self.root(a), self.root(b));
        self.parents[a.max(b)] = a.min(b);
        a != b
    }
    fn arg(&mut self, a: &Arg) -> usize {
        match a {
            Arg::Slot(i) => *i,
            Arg::Literal(v) => *self.literals.entry(v.clone()).or_insert_with(|| {
                let i = self.parents.len();
                self.parents.push(i);
                i
            }),
        }
    }
    fn close(&mut self, facts: &[(usize, usize, Vec<usize>)]) {
        loop {
            let mut keys = BTreeMap::new();
            let mut changed = false;
            for (_, table, ports) in facts {
                let key = (
                    *table,
                    ports[..ports.len() - 1]
                        .iter()
                        .map(|&p| self.root(p))
                        .collect::<Vec<_>>(),
                );
                if let Some(other) = keys.insert(key, *ports.last().unwrap()) {
                    changed |= self.union(other, *ports.last().unwrap());
                }
            }
            if !changed {
                break;
            }
        }
    }
}
impl Plan {
    pub(crate) fn derive(p: &Program) -> Result<Self> {
        let mut plans = vec![];
        for t in &p.templates {
            let mut s = Symbols {
                parents: (0..t.sorts.len()).collect(),
                ..Default::default()
            };
            let mut facts = vec![];
            let mut unions = vec![];
            // Delete/subsume invalidate symbolic constructor witnesses.
            if t.ops.iter().any(|o| matches!(o, Op::Hide(..) | Op::Panic)) {
                plans.push(None);
                continue;
            }
            for (op, ins) in t.ops.iter().enumerate() {
                match ins {
                    Op::Copy(dst, a) => {
                        let a = s.arg(a);
                        s.union(*dst, a);
                    }
                    Op::Union(a, b) => {
                        let (a, b) = (s.arg(a), s.arg(b));
                        unions.push((a, b));
                    }
                    Op::Let(dst, Call::Table(table), args)
                        if p.repair_ports.key_eq_columns[*table].is_some() =>
                    {
                        let mut ports = args.iter().map(|a| s.arg(a)).collect::<Vec<_>>();
                        ports.push(*dst);
                        facts.push((op, *table, ports));
                    }
                    _ => (),
                }
            }
            if unions.is_empty() || facts.is_empty() {
                plans.push(None);
                continue;
            }
            s.close(&facts);
            let before = (0..s.parents.len()).map(|i| s.root(i)).collect::<Vec<_>>();
            for &(a, b) in &unions {
                s.union(a, b);
            }
            s.close(&facts);
            let mut groups = BTreeMap::<usize, BTreeSet<usize>>::new();
            for (i, &old) in before.iter().enumerate() {
                groups.entry(s.root(i)).or_default().insert(old);
            }
            let affected = groups
                .iter()
                .filter(|(_, v)| v.len() > 1)
                .map(|(&k, _)| k)
                .collect::<BTreeSet<_>>();
            let ports = facts
                .iter()
                .filter_map(|(op, table, fields)| {
                    let cols = fields
                        .iter()
                        .enumerate()
                        .filter_map(|(col, &v)| {
                            (p.tables[*table].schema[col]["kind"] == "eq"
                                && affected.contains(&s.root(v)))
                            .then_some(col)
                        })
                        .collect::<Vec<_>>();
                    (!cols.is_empty()).then_some((*op, cols))
                })
                .collect::<BTreeMap<_, _>>();
            if ports.is_empty() {
                plans.push(None);
                continue;
            }
            // Each row waits only for its own affected classes, not for the
            // entire graph. Copies and already-congruent constructors share
            // one pre-union representative, so they add no redundant tests.
            let argument = |i: usize| {
                if i < t.sorts.len() {
                    Arg::Slot(i)
                } else {
                    Arg::Literal(s.literals.iter().find(|(_, n)| **n == i).unwrap().0.clone())
                }
            };
            let obligations = facts
                .iter()
                .filter_map(|(op, _, fields)| {
                    let cols = ports.get(op)?;
                    let roots = cols
                        .iter()
                        .map(|&col| s.root(fields[col]))
                        .collect::<BTreeSet<_>>();
                    let pairs = roots
                        .into_iter()
                        .flat_map(|r| {
                            let group = &groups[&r];
                            let first = *group.first().unwrap();
                            group.iter().skip(1).map(move |&other| (first, other))
                        })
                        .map(|(a, b)| (argument(a), argument(b)))
                        .collect();
                    Some((*op, pairs))
                })
                .collect();
            let classes = affected
                .iter()
                .map(|&r| (0..t.sorts.len()).filter(|&i| s.root(i) == r).collect())
                .collect();
            let unions = t
                .ops
                .iter()
                .filter_map(|o| {
                    if let Op::Union(a, b) = o {
                        Some((a.clone(), b.clone()))
                    } else {
                        None
                    }
                })
                .collect();
            plans.push(Some(TemplatePlan {
                unions,
                classes,
                ports,
                obligations,
            }));
        }
        let selected = plans
            .iter()
            .enumerate()
            .filter_map(|(i, p)| p.as_ref().map(|_| i))
            .collect();
        let mut plan = Self {
            templates: plans,
            selected,
        };
        if let Some(raw) = p.artifact.get("local_union_cells") {
            let selected: Vec<usize> =
                serde_json::from_value(raw["selected"].clone()).map_err(|e| e.to_string())?;
            if selected.windows(2).any(|w| w[0] >= w[1])
                || selected.iter().any(|i| !plan.selected.contains(i))
            {
                return Err("invalid local union selection".into());
            }
            plan.selected = selected.into_iter().collect();
            if *raw != plan.artifact(p) {
                return Err("local union proof differs from typed Cell".into());
            }
        }
        Ok(plan)
    }
    pub fn artifact(&self, p: &Program) -> J {
        json!({"schema":"eggfuse-local-union-cells/v1","recipe":p.artifact["recipe"]["sha256"],"templates":self.templates,"selected":self.selected,
        "contract":"new scalar constructor rows; one source completion boundary; actual committed equality checked; surviving boundaries subscribe"})
    }
    pub fn select(p: &Program, enabled: bool) -> J {
        let mut plan = p.local_union_cells.clone();
        if !enabled {
            plan.selected.clear();
        }
        plan.artifact(p)
    }
    fn contains(&self, template: usize, op: usize) -> bool {
        self.selected.contains(&template)
            && self.templates[template]
                .as_ref()
                .is_some_and(|p| p.ports.contains_key(&op))
    }
}
#[derive(Default, Serialize)]
pub(super) struct Counts {
    birth_attempts: u64,
    births: u64,
    prepare_reads: u64,
    completion_allocations: u64,
    completion_visits: u64,
    port_checks: u64,
    waiting_visits: u64,
    obligation_checks: u64,
    obligation_reads: u64,
    obligation_missing: u64,
    completed_boundaries: u64,
    forced_boundaries: u64,
    completion_waves: u64,
    result_publications: u64,
    queued_keys: u64,
    unchanged: u64,
    retired_unsubscribed: u64,
    congruence_retirements: u64,
    owned_live: u64,
    owned_peak: u64,
    boundary_subscriptions: u64,
    vanished: u64,
    row_copies: u64,
    pending_peak: usize,
    by_template: Vec<[u64; 3]>,
}
pub(super) struct Runtime {
    pub(super) pending: Vec<FactRef>,
    pub untracked_tables: Vec<usize>,
    pub fallback_queries: std::cell::Cell<u64>,
    pub fallback_rows: std::cell::Cell<u64>,
    counts: Counts,
}
pub(super) type Completion = Vec<(FactRef, usize, RowFields, usize)>;
impl Graph {
    pub fn new_with_local_unions(p: Program) -> Result<Self> {
        let mut g = Self::new_with_repair_ports(p)?;
        g.use_local_union_cells()?;
        Ok(g)
    }
    pub fn use_local_union_cells(&mut self) -> Result<()> {
        if self.union_digest.is_some() {
            return Err("local union ownership requires ordered repair".into());
        }
        if self.program.local_union_cells.selected.is_empty() {
            return Ok(());
        }
        self.local_unions = Some(Runtime {
            pending: vec![],
            untracked_tables: vec![0; self.program.tables.len()],
            fallback_queries: Default::default(),
            fallback_rows: Default::default(),
            counts: Counts {
                by_template: vec![[0; 3]; self.program.templates.len()],
                ..Default::default()
            },
        });
        Ok(())
    }
    pub fn local_union_report(&self) -> J {
        json!({"enabled":self.local_unions.is_some(),"plan":self.program.local_union_cells.artifact(&self.program),
            "stats":self.local_unions.as_ref().map(|m|&m.counts),
            "untracked_live":self.local_unions.as_ref().map_or(0,|m|m.untracked_tables.iter().sum::<usize>()),
            "fallback_queries":self.local_unions.as_ref().map_or(0,|m|m.fallback_queries.get()),
            "fallback_rows":self.local_unions.as_ref().map_or(0,|m|m.fallback_rows.get())})
    }
    pub(super) fn defer_local_birth(&mut self, f: FactRef, table: usize) -> bool {
        let Some(m) = &mut self.local_unions else {
            return false;
        };
        m.counts.birth_attempts += 1;
        let template = self.cells[&f.cell].template;
        if !self
            .program
            .local_union_cells
            .contains(template, f.op as usize)
        {
            return false;
        }
        m.pending.push(f);
        m.untracked_tables[table] += 1;
        m.counts.births += 1;
        m.counts.owned_live += 1;
        m.counts.owned_peak = m.counts.owned_peak.max(m.counts.owned_live);
        m.counts.by_template[template][0] += 1;
        m.counts.pending_peak = m.counts.pending_peak.max(m.pending.len());
        true
    }
    pub(super) fn prepare_local_completion(&mut self) -> Completion {
        let Some(m) = &mut self.local_unions else {
            return vec![];
        };
        m.counts.completion_allocations += u64::from(!m.pending.is_empty());
        let mut rows = Vec::with_capacity(m.pending.len());
        for f in m.pending.drain(..) {
            m.counts.prepare_reads += 1;
            if let Some(s) = self
                .cells
                .get_mut(&f.cell)
                .and_then(|c| c.facts.get_mut(&f.op))
            {
                if let Some((t, fields)) = s.decoded.take() {
                    rows.push((f, t, fields, 0));
                }
            } else {
                m.counts.vanished += 1;
            }
        }
        rows
    }
    pub(super) fn finish_local_completion(
        &mut self,
        mut rows: Completion,
        final_boundary: bool,
    ) -> Result<Completion> {
        if rows.is_empty() {
            return Ok(rows);
        }
        self.local_unions.as_mut().unwrap().counts.completion_waves += 1;
        rows.retain_mut(|(f, table, fields, next_obligation)| {
            let (f, table) = (*f, *table);
            let Some(state) = self.cells.get(&f.cell).and_then(|c| c.facts.get(&f.op)) else {
                return false;
            };
            let hash = state.hash;
            let mut key_changed = false;
            let mut changed = false;
            let m = self.local_unions.as_mut().unwrap();
            m.counts.completion_visits += 1;
            for col in 0..fields.len() {
                // The compiler's full schema excludes containers; each scalar
                // equality port needs one current boundary projection.
                if let Value::Eq(id) = fields[col] {
                    m.counts.port_checks += 1;
                    let next = root(&self.parents, id);
                    if next != id {
                        m.counts.row_copies += u64::from(Rc::strong_count(fields) > 1);
                        Rc::make_mut(fields)[col] = Value::Eq(next);
                        key_changed |= col + 1 < fields.len();
                        changed = true;
                    }
                }
            }
            if !changed {
                let template = self.cells[&f.cell].template;
                let proof = &self.program.local_union_cells.templates[template]
                    .as_ref()
                    .unwrap()
                    .obligations[&(f.op as usize)];
                let mut checks = 0;
                let mut missing = 0;
                while *next_obligation < proof.len() {
                    let (a, b) = &proof[*next_obligation];
                    checks += 1;
                    // A partial RHS may never execute a predicted equation.
                    // Missing operands do not certify future equality.
                    match (self.argument(f.cell, a), self.argument(f.cell, b)) {
                        (Ok(a), Ok(b)) if a == b => *next_obligation += 1,
                        (Ok(_), Ok(_)) => break,
                        _ => {
                            missing += 1;
                            break;
                        }
                    }
                }
                let complete = *next_obligation == proof.len();
                let m = self.local_unions.as_mut().unwrap();
                m.counts.obligation_checks += checks;
                m.counts.obligation_reads += 2 * checks;
                m.counts.obligation_missing += missing;
                if !complete && !final_boundary {
                    m.counts.waiting_visits += 1;
                    return true;
                }
                m.counts.completed_boundaries += u64::from(complete);
                m.counts.forced_boundaries += u64::from(!complete);
            }
            let m = self.local_unions.as_mut().unwrap();
            let singleton = self
                .intern
                .get(&hash)
                .is_some_and(|b| b.len() == 1 && b.first() == Some(&f));
            if changed && (key_changed || !singleton) {
                // No cache or reverse edges while waiting for the original
                // ordered key repair. Later union waves are read lazily from
                // the recipe. A collision may retire the row without ever
                // installing its internal subscriptions.
                m.counts.queued_keys += 1;
                self.dirty.insert(Dependency::Fact(f));
                self.dirty_facts[table].insert(f);
            } else {
                if changed {
                    m.counts.result_publications += 1;
                } else {
                    m.counts.unchanged += 1;
                }
                self.end_local_ownership(f, table, false);
                self.subscribe_edges(Dependency::Fact(f), fields);
                let s = self
                    .cells
                    .get_mut(&f.cell)
                    .unwrap()
                    .facts
                    .get_mut(&f.op)
                    .unwrap();
                s.decoded = Some((table, fields.clone()));
                if changed {
                    s.epoch = self.epoch;
                    self.query_versions[table] += 1;
                    self.changes.touch(table, Dependency::Fact(f));
                }
            }
            false
        });
        Ok(rows)
    }
    pub(super) fn note_local_collision(&mut self, f: FactRef) {
        if self.cells[&f.cell].facts[&f.op].local_union_owned {
            self.local_unions
                .as_mut()
                .unwrap()
                .counts
                .congruence_retirements += 1;
        }
    }
    pub(super) fn end_local_ownership(&mut self, f: FactRef, table: usize, retired: bool) {
        let c = self.cells.get_mut(&f.cell).unwrap();
        let state = c.facts.get_mut(&f.op).unwrap();
        if !std::mem::take(&mut state.local_union_owned) {
            return;
        }
        let m = self.local_unions.as_mut().expect("local ownership runtime");
        m.untracked_tables[table] -= 1;
        m.counts.owned_live -= 1;
        if retired {
            m.counts.retired_unsubscribed += 1;
            m.counts.by_template[c.template][1] += 1;
        } else {
            m.counts.boundary_subscriptions += 1;
            m.counts.by_template[c.template][2] += 1;
        }
    }
}
