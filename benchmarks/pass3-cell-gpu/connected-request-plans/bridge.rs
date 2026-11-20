#[derive(Default, Serialize)]
struct BridgeWork {
    calls: u64,
    root_rows: u64,
    requests: u64,
    cached: u64,
    cached_empty: u64,
    directory_reads: u64,
    directory_misses: u64,
    directory_rows: u64,
    directory_reuses: u64,
    audited_directory_reads: u64,
    found: u64,
    score_visits: u64,
    raw: u64,
    over_budget: u64,
    active: BTreeMap<usize, (u64, u64)>,
}

#[derive(Default)]
struct Bridges {
    cache: bool,
    shared: bool,
    // One table at a time, at most 16K scalar keys and image-relative row offsets.
    directory: Option<(usize, u64, u64, Rc<RequestDirectory>)>,
    plans: Vec<Option<[usize; 3]>>,
    work: BridgeWork,
}

pub fn configure_bridges(plans: Json, cache: bool, shared: bool) -> Result<()> {
    let plans = serde_json::from_value(plans).map_err(|e| e.to_string())?;
    STORE.with_borrow_mut(|s| {
        let s = s.as_mut().ok_or("missing parent issuer")?;
        s.bridges.plans = plans;
        s.bridges.cache = cache;
        s.bridges.shared = shared;
        if s.bridges.plans.len() != s.plans.len() || s.model.q != s.model.k {
            return Err("incompatible request plans or untied parent heads".into());
        }
        Ok(())
    })
}

enum RequestArg {
    Source(usize),
    Literal(Value),
}

type RequestDirectory = rustc_hash::FxHashMap<Value, (usize, Port)>;

impl Store {
    fn prepare_requests(
        &mut self,
        c: &Context<'_>,
        step: &StackStep,
    ) -> Option<Rc<RequestDirectory>> {
        if !self.bridges.shared || step.frame.rows.len() > 16384 {
            return None;
        }
        let generation = step.frame.generation;
        let unions = c.graph.stats.unions;
        if let Some((table, g, u, map)) = &self.bridges.directory
            && (*table, *g, *u) == (step.table, generation, unions)
        {
            self.bridges.work.directory_reuses += 1;
            return Some(map.clone());
        }
        let mut map = RequestDirectory::default();
        for (i, row) in step.frame.rows.iter().enumerate() {
            let [key, value] = row.values.as_slice() else {
                return None;
            };
            if !matches!(key, Value::Eq(_) | Value::Int(_)) {
                return None;
            }
            let code = self.code(value);
            if map.insert(key.clone(), (i, code)).is_some() {
                return None;
            }
        }
        self.bridges.work.directory_rows += map.len() as u64;
        let map = Rc::new(map);
        self.bridges.directory = Some((step.table, generation, unions, map.clone()));
        Some(map)
    }

    fn emit_bridge(
        &mut self,
        c: &Context<'_>,
        steps: &[StackStep],
        raw: &mut Vec<Vec<Dependency>>,
    ) -> Result<bool> {
        let Some(&Some(atoms)) = self.bridges.plans.get(self.rule) else {
            return Ok(false);
        };
        if steps.len() != 3
            || self.cap != usize::MAX
            || self.mode != "learned"
            || self.radius != 0
            || !self.packed_lookup
            || !self.page
        {
            return Ok(false);
        }
        let mut roles = [0; 3];
        for (role, atom) in atoms.iter().enumerate() {
            roles[role] = steps
                .iter()
                .position(|s| s.atom == *atom)
                .ok_or("unknown bridge parent")?;
        }
        let [a, b, d] = roles;
        if a == b || a == d || b == d {
            return Err("duplicate bridge atom".into());
        }
        let (src, point, target) = (&steps[a], &steps[b], &steps[d]);
        // The native function table stores one live physical record per complete key.
        // Constructor members with equivalent keys may still carry separate source identities.
        if c.graph.program.tables[point.table].virtual_fact {
            return Ok(false);
        }
        let lhs = &c.rule.query[src.atom].args;
        let rhs = &c.rule.query[point.atom].args;
        let last = &c.rule.query[target.atom].args;
        let col = |args: &[Arg], slot| {
            args.iter()
                .position(|a| matches!(a, Arg::Slot(s) if *s == slot))
        };
        let mut key = Vec::new();
        for arg in &rhs[..rhs.len() - 1] {
            key.push(match arg {
                Arg::Slot(s) => {
                    RequestArg::Source(col(lhs, *s).ok_or("unbound bridge function input")?)
                }
                Arg::Literal(v) => RequestArg::Literal(v.clone()),
            });
        }
        let Some(Arg::Slot(result)) = rhs.last() else {
            return Ok(false);
        };
        let Some(join_col) = col(last, *result) else {
            return Ok(false);
        };
        if col(lhs, *result).is_some() {
            return Ok(false);
        }
        let index = self.index(target.table, join_col, &target.frame);
        self.bridges.work.calls += 1;
        self.bridges.work.active.entry(self.rule).or_default().0 += 1;
        let mut triples = Vec::<[usize; 3]>::new();
        let directory = if key.len() == 1 {
            self.prepare_requests(c, point)
        } else {
            None
        };
        let mut inputs = Vec::with_capacity(key.len());
        let mut memo = rustc_hash::FxHashMap::<Vec<Value>, Option<(usize, Port)>>::default();
        for (i, left) in src.frame.rows.iter().enumerate() {
            self.bridges.work.root_rows += 1;
            self.counts.root_offers += 1;
            if c.rule.seminaive
                && left
                    .epoch
                    .max(point.frame.max_epoch)
                    .max(target.frame.max_epoch)
                    .max(c.remaining[3])
                    < c.watermark
            {
                continue;
            }
            inputs.clear();
            inputs.extend(key.iter().map(|k| match k {
                RequestArg::Source(col) => left.values[*col].clone(),
                RequestArg::Literal(v) => v.clone(),
            }));
            let receipt = if let Some(map) = &directory {
                self.bridges.work.directory_reads += 1;
                let k = canon(&inputs[0], &c.graph.parents);
                let v = map.get(&k).copied();
                self.bridges.work.directory_misses += u64::from(v.is_none());
                if self.detailed {
                    let expected = c.graph.lookup(point.table, &inputs)?.filter(|r| !r.hidden);
                    let actual = v.map(|(idx, _)| point.frame.rows[idx].witness);
                    if expected.map(|r| r.witness) != actual {
                        return Err("request directory supplied wrong witness".into());
                    }
                    self.bridges.work.audited_directory_reads += 1;
                }
                v
            } else if self.bridges.cache
                && let Some(hit) = memo.get(&inputs)
            {
                self.bridges.work.cached += 1;
                self.bridges.work.cached_empty += u64::from(hit.is_none());
                *hit
            } else {
                self.bridges.work.requests += 1;
                let entry = if let Some(mid) =
                    c.graph.lookup(point.table, &inputs)?.filter(|r| !r.hidden)
                {
                    let j = point
                        .frame
                        .rows
                        .binary_search_by_key(&mid.witness, |row| row.witness)
                        .map_err(|_| "function receipt missing from current source frame")?;
                    let q = self.code(mid.values.last().ok_or("empty function row")?);
                    Some((j, q))
                } else {
                    None
                };
                if self.bridges.cache && memo.len() < 4096 {
                    memo.insert(inputs.clone(), entry);
                }
                entry
            };
            let Some((j, q)) = receipt else { continue };
            self.bridges.work.found += 1;
            let target_rows = self.shortlist(&target.frame, &index, join_col, q);
            self.bridges.work.score_visits += target_rows.len() as u64;
            self.counts.approximate_visits += target_rows.len() as u64;
            self.counts.learned_pointers += target_rows.len() as u64;
            for &k in target_rows.iter() {
                if c.rule.seminaive
                    && left
                        .epoch
                        .max(point.frame.rows[j].epoch)
                        .max(target.frame.rows[k].epoch)
                        .max(c.remaining[3])
                        < c.watermark
                {
                    continue;
                }
                if triples.len() == 32768 {
                    self.bridges.work.over_budget += 1;
                    return Ok(false);
                }
                let mut tuple = [0; 3];
                tuple[a] = i;
                tuple[b] = j;
                tuple[d] = k;
                triples.push(tuple);
            }
        }
        // Keep the source orientation and its first-winner order for external users.
        triples.sort_unstable();
        let mut path = Vec::with_capacity(3);
        self.bridges.work.raw += triples.len() as u64;
        self.bridges.work.active.entry(self.rule).or_default().1 += triples.len() as u64;
        for tuple in triples {
            path.clear();
            path.extend(
                steps
                    .iter()
                    .zip(tuple)
                    .map(|(s, idx)| s.frame.rows[idx].witness),
            );
            self.seal_raw(c, steps, &path, raw);
        }
        Ok(true)
    }
}
