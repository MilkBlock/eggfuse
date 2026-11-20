// The original Cell query compiler already lowers operands to anchor and prior-result fields.
// Reuse the plan after a neural token names its own independent source parent.
#[derive(Default, Serialize)]
struct ProjectedStats {
    programs: usize,
    attempts: u64,
    scalar_ops: u64,
    point_reads: u64,
    successes: u64,
    root_constraints: u64,
    canonical_key_proofs: u64,
}
#[derive(Default)]
struct ProjectedChecks {
    mode: u64,
    audit: bool,
    plans: Vec<Option<std::rc::Rc<ProjectedRule>>>,
    stats: ProjectedStats,
}
enum AnchorConstraint {
    Literal(usize, Value),
    Equal(usize, usize),
}
struct ProjectedRule {
    pivot: usize,
    table: usize,
    width: usize,
    constraints: Vec<AnchorConstraint>,
    query: crate::cell::Query,
}
impl Trial {
    pub(crate) fn install_projected_checks(&mut self, prog: &Program, mode: u64) -> Result<()> {
        if !(1..=2).contains(&mode) || self.rows.verify.mode != 2 {
            return Err("projected checks require the single-source watermark verifier".into());
        }
        let s = &mut self.rows.verify.projected;
        s.mode = mode;
        s.audit = self.rows.detailed;
        s.plans = prog
            .rules
            .iter()
            .zip(&self.plans)
            .map(|(r, p)| {
                let p = p.as_ref()?;
                let pivot = p.pivot?;
                let anchor = &r.query[pivot];
                let Call::Table(table) = anchor.call else {
                    return None;
                };
                let query = crate::cell::Query::compile(r, pivot, &p.order)?;
                let mut seen = BTreeMap::new();
                let mut constraints = vec![];
                for (col, arg) in anchor.args.iter().enumerate() {
                    match arg {
                        Arg::Literal(v) => {
                            constraints.push(AnchorConstraint::Literal(col, v.clone()))
                        }
                        Arg::Slot(id) => {
                            if let Some(&first) = seen.get(id) {
                                constraints.push(AnchorConstraint::Equal(col, first))
                            } else {
                                seen.insert(*id, col);
                            }
                        }
                    }
                }
                Some(std::rc::Rc::new(ProjectedRule {
                    pivot,
                    table,
                    width: anchor.args.len(),
                    constraints,
                    query,
                }))
            })
            .collect();
        s.stats.programs = s.plans.iter().flatten().count();
        Ok(())
    }
}
impl VerifiedRows {
    fn verify_projected(
        &mut self,
        g: &Graph,
        r: &Rule,
        tok: &Token,
        wm: u64,
        work: &mut [u64; 8],
        compiled: std::rc::Rc<ProjectedRule>,
    ) -> Result<Option<Instance>> {
        self.projected.stats.attempts += 1;
        let w = tok.w.ok_or("projected single token lacks a parent")?;
        let Some(row) = self.witness(g, compiled.table, w)? else {
            return Ok(None);
        };
        if row.hidden
            || row.witness != w
            || row.table != compiled.table
            || row.epoch != tok.version
            || row.values.len() != compiled.width
        {
            return Ok(None);
        }
        let fields = &row.values;
        for cond in &compiled.constraints {
            self.projected.stats.root_constraints += 1;
            let equal = match cond {
                AnchorConstraint::Literal(i, x) => fields[*i] == crate::value::canon(x, &g.parents),
                AnchorConstraint::Equal(i, j) => fields[*i] == fields[*j],
            };
            if !equal {
                return Ok(None);
            }
        }
        let mut receipts = smallvec::SmallVec::<[(usize, Dependency); 8]>::new();
        receipts.push((compiled.pivot, w));
        let mut results = smallvec::SmallVec::<[Value; 8]>::new();
        let mut epoch = row.epoch;
        for step in &compiled.query.steps {
            let keys: smallvec::SmallVec<[Value; 3]> = step
                .key
                .iter()
                .map(|f| f.read(g, |i| &fields[i], &results, None))
                .collect();
            let value = match &step.call {
                Call::Table(table) => {
                    work[3] += 1;
                    self.projected.stats.point_reads += 1;
                    let row = if self.projected.mode == 2
                        && !keys.iter().any(|v| matches!(v, Value::Set(_)))
                    {
                        if self.projected.audit
                            && keys
                                .iter()
                                .any(|v| crate::value::canon(v, &g.parents) != *v)
                        {
                            return Err("noncanonical key in projected proof".into());
                        }
                        self.projected.stats.canonical_key_proofs += 1;
                        g.lookup_canonical(*table, &keys)?
                    } else {
                        g.lookup(*table, &keys)?
                    };
                    let Some(found) = row.filter(|q| !q.hidden) else {
                        return Ok(None);
                    };
                    receipts.push((step.atom, found.witness));
                    epoch = epoch.max(found.epoch);
                    found.values.last().ok_or("empty point result")?.clone()
                }
                Call::Primitive(name, ty) => {
                    work[4] += 1;
                    self.projected.stats.scalar_ops += 1;
                    let Some(v) = g.primitive(name, &keys, ty)? else {
                        return Ok(None);
                    };
                    v
                }
            };
            if let Some(expected) = &step.check_result
                && !expected.agrees(&value, g, |i| &fields[i], &results, None)
            {
                return Ok(None);
            }
            if results.len() < compiled.query.result_slots() {
                results.push(value);
            }
        }
        if r.seminaive && epoch < wm {
            return Ok(None);
        }
        let values = r
            .inputs
            .iter()
            .zip(&compiled.query.inputs)
            .map(|(&slot, f)| (slot, f.read(g, |i| &fields[i], &results, None)))
            .collect();
        let mut known = vec![None; r.query.len()];
        for (i, d) in receipts {
            known[i] = Some(d);
        }
        self.projected.stats.successes += 1;
        Ok(Some(Instance::matched(
            values,
            QueryFacts::Ports(known),
            epoch,
        )))
    }
}
