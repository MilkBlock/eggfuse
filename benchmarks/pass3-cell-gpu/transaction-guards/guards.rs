// Guards observe the immutable source view of ONE rule occurrence. A hit never supplies an address.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
enum GuardMode {
    #[default]
    Off,
    Constants,
    Local,
    Stale,
    Foreign,
}
#[derive(Clone, Debug)]
enum GuardValue {
    Column(usize),
    Literal(Value),
}
impl GuardValue {
    fn eval(&self, g: &Graph, parent: Option<&Row>) -> Value {
        match self {
            Self::Literal(v) => canon(v, &g.parents),
            Self::Column(i) => parent.unwrap().values[*i].clone(),
        }
    }
}
#[derive(Clone, Debug)]
struct GuardProgram {
    atom: usize,
    table: usize,
    owner: Option<usize>,
    key: Vec<GuardValue>,
    expected: Option<GuardValue>,
}
#[derive(Clone, Default, Serialize)]
struct GuardStats {
    calls: u64,
    probes: u64,
    zero_probes: u64,
    keyed_probes: u64,
    output_tests: u64,
    dead_calls: u64,
    peak_outcome_bytes: usize,
    distinct_parent_rows: u64,
    cached_parent_rows: u64,
    rejected_prefixes: u64,
    invalid_receipts: u64,
    raw: u64,
    failures_by_atom: Vec<u64>,
}
#[derive(Default)]
struct EarlyGuards {
    mode: GuardMode,
    programs: Vec<Vec<Rc<GuardProgram>>>,
    stats: Vec<GuardStats>,
    active: Option<GuardInvocation>,
}
struct GuardInvocation {
    rule: usize,
    by_owner: Vec<Vec<Receipt>>,
    outcomes: Vec<Vec<u8>>,
}
struct Receipt {
    plan: Rc<GuardProgram>,
    rule: usize,
    source: usize,
    version: u64,
    value: Option<Value>,
}

fn parent_value(arg: &Arg, parent: &[Arg]) -> Option<GuardValue> {
    match arg {
        Arg::Literal(v) => Some(GuardValue::Literal(v.clone())),
        Arg::Slot(s) => parent
            .iter()
            .position(|a| matches!(a,Arg::Slot(x) if x==s))
            .map(GuardValue::Column),
    }
}

fn compile_guards(rule: &Rule, plan: &Plan, mode: GuardMode) -> Vec<Rc<GuardProgram>> {
    let picks = plan.ins.iter().take_while(|v| v.1 == 1).count();
    // The two-parent shortcut has its own delta and correlation guard.
    if picks < 3 || plan.ins[picks..].iter().any(|v| v.1 != 0) {
        return vec![];
    }
    let mut result = Vec::new();
    for (atom, _, _) in &plan.ins[picks..] {
        let a = &rule.query[*atom];
        let Call::Table(table) = a.call else { continue };
        let Some((output, keys)) = a.args.split_last() else {
            continue;
        };
        let constant = keys.iter().all(|k| matches!(k, Arg::Literal(_)));
        if !constant && mode == GuardMode::Constants {
            continue;
        }
        // Choose the earliest parent that determines every key. For a constant key the
        // best parent is the earliest one that additionally determines the output.
        let mut placement = None;
        for (owner, (id, _, _)) in plan.ins[..picks].iter().enumerate() {
            let args = &rule.query[*id].args;
            let Some(key) = keys
                .iter()
                .map(|a| parent_value(a, args))
                .collect::<Option<Vec<_>>>()
            else {
                continue;
            };
            let expected = parent_value(output, args);
            if constant && !matches!(expected, Some(GuardValue::Column(_))) {
                continue;
            }
            placement = Some(GuardProgram {
                atom: *atom,
                table,
                owner: Some(owner),
                key,
                expected,
            });
            break;
        }
        if placement.is_none() && constant {
            placement = Some(GuardProgram {
                atom: *atom,
                table,
                owner: None,
                key: keys.iter().map(|a| parent_value(a, &[]).unwrap()).collect(),
                expected: parent_value(output, &[]),
            })
        }
        if let Some(g) = placement {
            result.push(Rc::new(g))
        }
    }
    result
}

pub fn configure_early_guards(program: &Program, mode: &str) -> Result<()> {
    let mode = match mode {
        "constants" => GuardMode::Constants,
        "local" => GuardMode::Local,
        "stale" => GuardMode::Stale,
        "foreign" => GuardMode::Foreign,
        _ => return Err("unknown early-guard mode".into()),
    };
    STORE.with(|state| {
        let mut state = state.borrow_mut();
        let s = state.as_mut().ok_or("missing witness generator")?;
        s.early.programs = s
            .plans
            .iter()
            .zip(&program.rules)
            .map(|(p, r)| {
                p.as_ref()
                    .map_or_else(Vec::new, |p| compile_guards(r, p, mode))
            })
            .collect();
        s.early.stats = program
            .rules
            .iter()
            .map(|r| GuardStats {
                failures_by_atom: if s.detailed {
                    vec![0; r.query.len()]
                } else {
                    Vec::new()
                },
                ..Default::default()
            })
            .collect();
        s.early.mode = mode;
        Ok(())
    })
}

impl EarlyGuards {
    fn report(&self) -> Json {
        let active = self
            .programs
            .iter()
            .enumerate()
            .filter(|(_, p)| !p.is_empty())
            .map(|(rid, p)| {
                let guards = p
                    .iter()
                    .map(|q| json!([q.atom, q.table, q.owner, q.key.len(), q.expected.is_some()]))
                    .collect::<Vec<_>>();
                (rid, json!({"guards":guards,"work":self.stats[rid]}))
            })
            .collect::<BTreeMap<_, _>>();
        json!(active)
    }
    fn prepare(&mut self, c: &Context<'_>, steps: &[StackStep], rid: usize) -> Result<bool> {
        self.active = None;
        let programs = &self.programs[rid];
        if programs.is_empty() {
            return Ok(true);
        }
        let stats = &mut self.stats[rid];
        stats.calls += 1;
        let mut local = GuardInvocation {
            rule: rid,
            by_owner: (0..steps.len()).map(|_| vec![]).collect(),
            outcomes: (0..steps.len()).map(|_| vec![]).collect(),
        };
        for p in programs {
            let g = c.graph;
            let mut receipt = Receipt {
                plan: p.clone(),
                rule: rid,
                source: p.table,
                version: g.query_versions[p.table],
                value: None,
            };
            // Untrusted receipt fault controls. A mismatched identity or version cannot veto.
            if self.mode == GuardMode::Stale {
                receipt.version = receipt.version.wrapping_sub(1)
            }
            if self.mode == GuardMode::Foreign {
                receipt.source = receipt.source.wrapping_add(1)
            }
            if receipt.rule != rid
                || receipt.source != p.table
                || receipt.version != g.query_versions[p.table]
            {
                stats.invalid_receipts += 1;
                continue;
            }
            if p.key.iter().all(|a| matches!(a, GuardValue::Literal(_))) {
                let key = p.key.iter().map(|v| v.eval(g, None)).collect::<Vec<_>>();
                stats.probes += 1;
                stats.zero_probes += 1;
                let value = g
                    .lookup(p.table, &key)?
                    .filter(|r| !r.hidden)
                    .and_then(|row| row.values.last().cloned());
                if value.is_none()
                    || (p.owner.is_none()
                        && p.expected
                            .as_ref()
                            .is_some_and(|v| Some(v.eval(g, None)) != value))
                {
                    if let Some(n) = stats.failures_by_atom.get_mut(p.atom) {
                        *n += 1;
                    }
                    stats.dead_calls += 1;
                    return Ok(false);
                }
                receipt.value = value;
            }
            if let Some(i) = p.owner {
                local.by_owner[i].push(receipt)
            }
        }
        for (i, list) in local.by_owner.iter().enumerate() {
            if !list.is_empty() {
                local.outcomes[i] = vec![0; steps[i].frame.rows.len()]
            }
        }
        stats.peak_outcome_bytes = stats
            .peak_outcome_bytes
            .max(local.outcomes.iter().map(Vec::capacity).sum());
        if local.by_owner.iter().any(|s| !s.is_empty()) {
            self.active = Some(local)
        }
        Ok(true)
    }

    fn permits(&mut self, c: &Context<'_>, i: usize, pos: usize, row: &Row) -> Result<bool> {
        let a = self.active.as_mut().unwrap();
        if a.by_owner[i].is_empty() {
            return Ok(true);
        }
        let stats = &mut self.stats[a.rule];
        let known = a.outcomes[i][pos];
        if known != 0 {
            stats.cached_parent_rows += 1;
            if known == 2 {
                stats.rejected_prefixes += 1
            }
            return Ok(known == 1);
        }
        stats.distinct_parent_rows += 1;
        let mut pass = true;
        for r in &a.by_owner[i] {
            let p = &r.plan;
            let g = c.graph;
            // The parent row, table versions and receiver storage are borrowed from the
            // same frozen rule occurrence; the expectation may only veto this row.
            let actual = if let Some(v) = &r.value {
                Some(v.clone())
            } else {
                let key = p
                    .key
                    .iter()
                    .map(|v| v.eval(g, Some(row)))
                    .collect::<Vec<_>>();
                stats.probes += 1;
                stats.keyed_probes += 1;
                g.lookup(p.table, &key)?
                    .filter(|r| !r.hidden)
                    .and_then(|r| r.values.last().cloned())
            };
            if p.expected.is_some() {
                stats.output_tests += 1
            }
            if actual.is_none()
                || p.expected
                    .as_ref()
                    .is_some_and(|v| Some(v.eval(g, Some(row))) != actual)
            {
                if let Some(n) = stats.failures_by_atom.get_mut(p.atom) {
                    *n += 1;
                }
                pass = false;
                break;
            }
        }
        a.outcomes[i][pos] = if pass { 1 } else { 2 };
        if !pass {
            stats.rejected_prefixes += 1
        }
        Ok(pass)
    }
}
