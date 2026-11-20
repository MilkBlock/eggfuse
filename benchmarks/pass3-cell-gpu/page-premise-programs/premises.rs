// The pool exists only while the source Graph is immutable at this rule occurrence.
use crate::joint_root::{MultiPage, Ref as PageRef};
type SmallRows = smallvec::SmallVec<[Row; 4]>;
type PointKey = smallvec::SmallVec<[Value; 3]>;
type SourceMap<K, V> = rustc_hash::FxHashMap<K, V>;

enum LocalTest {
    Literal(usize, Value),
    Equal(usize, usize),
}
struct Role {
    atom: usize,
    table: usize,
    width: usize,
    tests: Vec<LocalTest>,
    prior: Vec<(usize, usize, usize)>, // current column, previous role, previous column
}
struct PageProgram {
    roles: Vec<Role>,
    slots: Vec<(usize, (usize, usize))>,
}
impl PageProgram {
    fn compile(rule: &Rule, plan: &Plan) -> Option<Self> {
        let mut first = BTreeMap::<usize, (usize, usize)>::new();
        let mut roles = vec![];
        for (j, (atom, _, _)) in plan
            .ins
            .iter()
            .take_while(|(_, pick, _)| *pick == 1)
            .enumerate()
        {
            let a = &rule.query[*atom];
            let Call::Table(table) = a.call else {
                return None;
            };
            let mut local = BTreeMap::new();
            let mut r = Role {
                atom: *atom,
                table,
                width: a.args.len(),
                tests: vec![],
                prior: vec![],
            };
            for (col, arg) in a.args.iter().enumerate() {
                match arg {
                    Arg::Literal(v) => r.tests.push(LocalTest::Literal(col, v.clone())),
                    Arg::Slot(slot) => {
                        if let Some(&previous) = local.get(slot) {
                            r.tests.push(LocalTest::Equal(col, previous));
                            continue;
                        }
                        local.insert(*slot, col);
                        if let Some(&(role, offset)) = first.get(slot) {
                            r.prior.push((col, role, offset));
                        } else {
                            first.insert(*slot, (j, col));
                        }
                    }
                }
            }
            roles.push(r);
        }
        Some(Self {
            roles,
            slots: first.into_iter().collect(),
        })
    }
}

#[derive(Default, Serialize)]
struct PremiseCounts {
    pages: u64,
    tuples: u64,
    logical_parents: u64,
    source_reads: u64,
    row_hits: u64,
    later_role_hits: u64,
    local_tests: u64,
    cross_tests: u64,
    accepted_parent_sets: u64,
    projected_slots: u64,
    suffix_requests: u64,
    suffix_hits: u64,
    missing_hits: u64,
    suffix_reads: u64,
    peak_rows: usize,
    peak_points: usize,
    audited: u64,
}
#[derive(Default)]
struct PagePremises {
    mode: u8,
    plans: Vec<Option<Rc<PageProgram>>>,
    points: SourceMap<(usize, PointKey), Option<Row>>,
    active_points: bool,
    stats: PremiseCounts,
}
pub fn configure_page_premises(program: &Program, mode: u64) -> Result<()> {
    if !(1..=6).contains(&mode) {
        return Err("invalid premise sharing mode".into());
    }
    STORE.with_borrow_mut(|state| {
        let s = state.as_mut().ok_or("parent issuer is missing")?;
        if !s.page {
            return Err("premise programs require sealed multi-parent pages".into());
        }
        s.premises.mode = mode as u8;
        s.premises.plans = s
            .plans
            .iter()
            .zip(&program.rules)
            .map(|(p, r)| {
                p.as_ref()
                    .and_then(|p| PageProgram::compile(r, p))
                    .map(Rc::new)
            })
            .collect();
        Ok(())
    })
}
impl Store {
    fn suffix_point(&mut self, g: &Graph, table: usize, key: &[Value]) -> Result<Option<Row>> {
        if !self.premises.active_points {
            self.counts.point_reads += 1;
            return g.lookup(table, key);
        }
        let p = &mut self.premises;
        p.stats.suffix_requests += 1;
        if key.len() > 3
            || key
                .iter()
                .any(|v| !matches!(v, Value::Int(_) | Value::Eq(_)))
        {
            p.stats.suffix_reads += 1;
            self.counts.point_reads += 1;
            return g.lookup(table, key);
        }
        let k = (table, key.iter().cloned().collect());
        if let Some(v) = p.points.get(&k) {
            p.stats.suffix_hits += 1;
            p.stats.missing_hits += u64::from(v.is_none());
            return Ok(v.clone());
        }
        p.stats.suffix_reads += 1;
        self.counts.point_reads += 1;
        let v = g.lookup(table, key)?;
        if p.points.len() < 4096 {
            p.points.insert(k, v.clone());
            p.stats.peak_points = p.stats.peak_points.max(p.points.len());
        }
        Ok(v)
    }

    fn verify_shared_page(
        &mut self,
        c: &Context,
        base: &Prefix,
        page: &MultiPage,
        out: &mut Vec<Instance>,
    ) -> Result<()> {
        let plan = self.premises.plans[self.rule]
            .clone()
            .ok_or("missing prefix layout")?;
        let mode = self.premises.mode;
        let shared = matches!(mode, 2 | 4 | 6);
        let wired = matches!(mode, 3 | 4 | 6);
        let mut cache = SourceMap::<(usize, Dependency, u64), Option<Row>>::default();
        self.premises.points.clear();
        self.premises.active_points = matches!(mode, 5 | 6);
        self.premises.stats.pages += 1;
        let mut unused = vec![];
        let mut rows = SmallRows::new();
        for i in 0..page.count() {
            let parents = page.parents(i);
            if parents.len() != plan.roles.len() {
                return Err("page arity disagrees with compiled layout".into());
            }
            let mut exact = base.clone();
            rows.clear();
            self.premises.stats.tuples += 1;
            let mut pass = true;
            for (j, (role, parent)) in plan.roles.iter().zip(parents).enumerate() {
                if parent.atom != role.atom {
                    return Err("page reference has wrong source atom".into());
                }
                self.premises.stats.logical_parents += 1;
                let key = (j, parent.row, parent.version);
                let stored = if shared { cache.get(&key) } else { None };
                let row = if let Some(hit) = stored {
                    self.premises.stats.row_hits += 1;
                    self.premises.stats.later_role_hits += u64::from(j > 0);
                    hit.clone()
                } else {
                    self.premises.stats.source_reads += 1;
                    let row = c.graph.row(parent.row)?;
                    if let Some(r) = &row
                        && (r.witness != parent.row || r.epoch != parent.version)
                    {
                        return Err("page reference has wrong source version".into());
                    }
                    let row = row.filter(|r| {
                        !wired
                            || (!r.hidden
                                && r.table == role.table
                                && r.values.len() == role.width
                                && role.tests.iter().all(|test| {
                                    self.premises.stats.local_tests += 1;
                                    match test {
                                        LocalTest::Equal(a, b) => r.values[*a] == r.values[*b],
                                        LocalTest::Literal(col, v) => {
                                            r.values[*col] == canon(v, &c.graph.parents)
                                        }
                                    }
                                }))
                    });
                    if shared && cache.len() < 8192 {
                        cache.insert(key, row.clone());
                        self.premises.stats.peak_rows =
                            self.premises.stats.peak_rows.max(cache.len());
                    }
                    row
                };
                let Some(row) = row else {
                    pass = false;
                    break;
                };
                if wired {
                    for &(col, previous, offset) in &role.prior {
                        self.premises.stats.cross_tests += 1;
                        if row.values[col] != rows[previous].values[offset] {
                            pass = false;
                            break;
                        }
                    }
                    if !pass {
                        break;
                    }
                    exact.epoch = exact.epoch.max(row.epoch);
                    exact.witness[role.atom] = Some(row.witness);
                    rows.push(row);
                } else if !extend(c.graph, c.rule, role.atom, &row, &mut exact) {
                    pass = false;
                    break;
                }
            }
            if wired && pass {
                for &(slot, (j, col)) in &plan.slots {
                    exact.slots.insert(slot, rows[j].values[col].clone());
                }
                self.premises.stats.projected_slots += plan.slots.len() as u64;
            }
            if self.detailed {
                let mut original = base.clone();
                let mut ok = true;
                for (j, PageRef { row, .. }) in parents.iter().enumerate() {
                    let Some(row) = c.graph.row(*row)? else {
                        ok = false;
                        break;
                    };
                    if !extend(c.graph, c.rule, c.inst[j].0, &row, &mut original) {
                        ok = false;
                        break;
                    }
                }
                if pass != ok
                    || pass
                        && (exact.epoch != original.epoch
                            || exact.witness != original.witness
                            || !exact.slots.iter().eq(original.slots.iter()))
                {
                    return Err(
                        "compiled parent projection disagrees with exact source extension".into(),
                    );
                }
                self.premises.stats.audited += 1;
            }
            if !pass {
                self.counts.raw_parent_rejects += 1;
                continue;
            }
            self.premises.stats.accepted_parent_sets += 1;
            self.counts.verified_parent_tuples += 1;
            exact.picks = parents.len();
            if self.detailed {
                exact.anchors = parents.iter().map(|r| r.row).collect();
            }
            exact.root_recipe = page.recipe(i);
            self.descend(c, c.pick_count, exact, out, &mut unused)?;
        }
        self.premises.active_points = false;
        self.premises.points.clear();
        Ok(())
    }
}
