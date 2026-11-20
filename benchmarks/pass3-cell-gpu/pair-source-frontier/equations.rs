#[derive(Clone)]
enum IntPort {
    Field(usize),
    Integer(i64),
}
#[derive(Clone)]
struct Equation {
    side: usize,
    atom: usize,
    from: [IntPort; 2],
    to: usize,
}
type CodeArray = Rc<Vec<u32>>;
type BucketMap = Rc<rustc_hash::FxHashMap<u64, Vec<usize>>>;
struct PairEquation {
    left: CodeArray,
    right: CodeArray,
    lookup: Option<BucketMap>,
}
#[derive(Default, Serialize)]
struct EquationStats {
    rule_plans: usize,
    calls: u64,
    encoded_rows: u64,
    numeric_requests: u64,
    undefined: u64,
    arrays_reused: u64,
    index_builds: u64,
    index_rows: u64,
    index_reuses: u64,
    pair_checks: u64,
    filtered: u64,
    index_probes: u64,
    invalid_receipts: u64,
}
#[derive(Default)]
struct EquationState {
    mode: usize,
    cache: bool,
    plans: Vec<Option<Equation>>,
    columns: rustc_hash::FxHashMap<(usize, usize), (u64, u64, CodeArray)>,
    indexes: rustc_hash::FxHashMap<usize, (u64, u64, BucketMap)>,
    stats: EquationStats,
}
fn row_column(atom: &crate::program::Atom, arg: &Arg) -> Option<usize> {
    let Arg::Slot(s) = arg else { return None };
    atom.args
        .iter()
        .position(|a| matches!(a,Arg::Slot(id) if id==s))
}
fn read_port(atom: &crate::program::Atom, arg: &Arg) -> Option<IntPort> {
    match arg {
        Arg::Literal(Value::Int(n)) => Some(IntPort::Integer(*n)),
        _ => row_column(atom, arg).map(IntPort::Field),
    }
}
fn derive_equation(r: &Rule, p: &Plan) -> Option<Equation> {
    if p.ins.iter().take_while(|x| x.1 == 1).count() != 2 {
        return None;
    }
    let parents = [&r.query[p.ins[0].0], &r.query[p.ins[1].0]];
    for (id, _, _) in &p.ins[2..] {
        let a = &r.query[*id];
        let Call::Primitive(name, ty) = &a.call else {
            continue;
        };
        if ty != "i64"
            || !matches!(name.as_str(), "+" | "-" | "*" | "/" | "%" | "min" | "max")
            || a.args.len() != 3
        {
            continue;
        }
        for side in 0..2 {
            let source = parents[side];
            let dest = parents[1 - side];
            let (Some(x), Some(y), Some(to)) = (
                read_port(source, &a.args[0]),
                read_port(source, &a.args[1]),
                row_column(dest, &a.args[2]),
            ) else {
                continue;
            };
            if row_column(source, &a.args[2]).is_some()
                || (!matches!(x, IntPort::Field(_)) && !matches!(y, IntPort::Field(_)))
            {
                continue;
            }
            return Some(Equation {
                side,
                atom: *id,
                from: [x, y],
                to,
            });
        }
    }
    None
}
pub fn configure_equations(p: &Program, v: Json) -> Result<()> {
    let mode = v["mode"].as_u64().ok_or("missing equation strategy")? as usize;
    if !(1..=3).contains(&mode) {
        return Err("unknown equation strategy".into());
    }
    STORE.with_borrow_mut(|s| {
        let s = s.as_mut().ok_or("missing source proposer")?;
        if s.accel != 4
            || !s.seal
            || !s.packed_lookup
            || s.radius != 0
            || s.signatures.enabled
            || !s
                .model
                .q
                .iter()
                .flatten()
                .zip(s.model.k.iter().flatten())
                .all(|(x, y)| x.to_bits() == y.to_bits())
        {
            return Err("derived ports require tied packed learned source choices".into());
        }
        s.equations.mode = mode;
        s.equations.cache = v["cache"].as_bool().unwrap_or(true);
        s.equations.plans = p
            .rules
            .iter()
            .zip(&s.plans)
            .map(|(r, plan)| plan.as_ref().and_then(|p| derive_equation(r, p)))
            .collect();
        s.equations.stats.rule_plans = s.equations.plans.iter().flatten().count();
        Ok(())
    })
}
impl Store {
    fn equation_codes(
        &mut self,
        c: &Context<'_>,
        eq: &Equation,
        d: &StackStep,
        side: usize,
    ) -> Result<Option<CodeArray>> {
        let key = (self.rule, side);
        let (v, u) = (d.frame.generation, d.frame.born_at_union);
        if self.equations.cache
            && let Some((version, union, words)) = self.equations.columns.get(&key)
            && (*version, *union) == (v, u)
        {
            self.equations.stats.arrays_reused += 1;
            return Ok(Some(words.clone()));
        }
        let mut words = Vec::with_capacity(d.frame.rows.len());
        let Call::Primitive(name, ty) = &c.rule.query[eq.atom].call else {
            return Err("expected a typed scalar calculation".into());
        };
        for row in &d.frame.rows {
            let computed;
            let val = if side == eq.side {
                let args = eq.from.each_ref().map(|a| match a {
                    IntPort::Integer(n) => Value::Int(*n),
                    IntPort::Field(i) => row.values[*i].clone(),
                });
                if args.iter().any(|a| !matches!(a, Value::Int(_))) {
                    return Ok(None);
                }
                self.equations.stats.numeric_requests += 1;
                computed = match c.graph.primitive(name, &args, ty) {
                    Ok(Some(val)) => val,
                    Ok(None) => {
                        self.equations.stats.undefined += 1;
                        words.push(u32::MAX);
                        continue;
                    }
                    // Preserve source error ordering: an unproved operand goes to ordinary verification.
                    Err(_) => return Ok(None),
                };
                &computed
            } else {
                let val = &row.values[eq.to];
                if !matches!(val, Value::Int(_)) {
                    return Ok(None);
                }
                val
            };
            words.push(signature(self.code(val), side == 0, self.views));
        }
        self.equations.stats.encoded_rows += words.len() as u64;
        let words = Rc::new(words);
        if self.equations.cache {
            self.equations.columns.insert(key, (v, u, words.clone()));
        }
        Ok(Some(words))
    }
    fn prepare_equation(
        &mut self,
        c: &Context<'_>,
        steps: &[StackStep],
        right_ports: &[Port],
    ) -> Result<Option<PairEquation>> {
        let Some(eq) = self.equations.plans.get(self.rule).and_then(|p| p.clone()) else {
            return Ok(None);
        };
        let (a, b) = (&steps[0], &steps[1]);
        self.equations.stats.calls += 1;
        if self.equations.mode == 3 {
            self.equations.stats.invalid_receipts += 1;
            return Ok(None);
        }
        let Some(left) = self.equation_codes(c, &eq, a, 0)? else {
            return Ok(None);
        };
        let Some(right) = self.equation_codes(c, &eq, b, 1)? else {
            return Ok(None);
        };
        let mut lookup = None;
        if self.equations.mode == 2 {
            let stamp = (b.frame.generation, b.frame.born_at_union);
            if self.equations.cache
                && let Some((v, u, index)) = self.equations.indexes.get(&self.rule)
                && (*v, *u) == stamp
            {
                self.equations.stats.index_reuses += 1;
                lookup = Some(index.clone());
            } else {
                let mut map = rustc_hash::FxHashMap::<u64, Vec<usize>>::default();
                for (pos, (&port, &value)) in right_ports.iter().zip(right.iter()).enumerate() {
                    if value == u32::MAX {
                        continue;
                    }
                    let key =
                        (u64::from(signature(port, false, self.views)) << 32) | u64::from(value);
                    map.entry(key).or_default().push(pos);
                }
                self.equations.stats.index_builds += 1;
                self.equations.stats.index_rows += right_ports.len() as u64;
                let index = Rc::new(map);
                if self.equations.cache {
                    self.equations
                        .indexes
                        .insert(self.rule, (stamp.0, stamp.1, index.clone()));
                }
                lookup = Some(index);
            }
        }
        Ok(Some(PairEquation {
            left,
            right,
            lookup,
        }))
    }
}
