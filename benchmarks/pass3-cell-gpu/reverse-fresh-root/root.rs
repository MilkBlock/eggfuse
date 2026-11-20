#[derive(Clone, Copy, Eq, PartialEq, Hash)]
enum RootField {
    Column(usize),
    Fixed(u32),
}
type Fields = smallvec::SmallVec<[RootField; 3]>;
type Postings = rustc_hash::FxHashMap<u64, Vec<usize>>;
#[derive(Default, Serialize)]
struct ReverseStats {
    checked: u64,
    used: u64,
    unkeyed: u64,
    dense: u64,
    rows_before: u64,
    rows_after: u64,
    fresh_keys: u64,
    source_index_rows: u64,
    source_index_builds: u64,
    source_reuses: u64,
    peak_charge: usize,
    refused: u64,
}
#[derive(Default)]
struct RootDomain {
    current: Option<Rc<Vec<usize>>>,
    enabled: bool,
    budget: usize,
    charged: usize,
    min_rows: usize,
    percent: usize,
    by_key: rustc_hash::FxHashMap<(usize, Fields), (u64, u64, usize, Rc<Postings>)>,
    stats: ReverseStats,
}
pub fn enable_reverse_root(v: Json) -> Result<()> {
    let min = v["min_rows"].as_u64().ok_or("missing minimum root size")? as usize;
    let pct = v["percent"]
        .as_u64()
        .ok_or("missing maximum root expansion percent")? as usize;
    let bytes = v["budget"]
        .as_u64()
        .ok_or("missing reverse directory budget")? as usize;
    if min == 0 || pct == 0 || pct > 100 || bytes == 0 {
        return Err("invalid reverse domain bounds".into());
    }
    STORE.with_borrow_mut(|c| {
        let s = c.as_mut().ok_or("no port policy")?;
        let forward = s
            .forward
            .config
            .as_ref()
            .ok_or("reverse domain needs forward evidence")?;
        if !forward.freshness || s.raw_cache.enabled || !s.packed_lookup {
            return Err("reverse domain requires uncached, signed freshness proofs".into());
        }
        s.root_domain.enabled = true;
        s.root_domain.min_rows = min;
        s.root_domain.percent = pct;
        s.root_domain.budget = bytes;
        Ok(())
    })
}
impl Store {
    fn root_postings(&mut self, d: &StackStep, fields: Fields) -> Option<Rc<Postings>> {
        let k = (d.table, fields);
        if let Some((version, union, _, rows)) = self.root_domain.by_key.get(&k)
            && *version == d.frame.generation
            && *union == d.frame.born_at_union
        {
            self.root_domain.stats.source_reuses += 1;
            return Some(rows.clone());
        }
        if let Some((_, _, charge, _)) = self.root_domain.by_key.remove(&k) {
            self.root_domain.charged -= charge;
        }
        let charge = 128usize.saturating_add(96usize.saturating_mul(d.frame.rows.len()));
        if self.root_domain.charged.saturating_add(charge) > self.root_domain.budget {
            self.root_domain.stats.refused += 1;
            return None;
        }
        let bits = (1 + self.forward.extra_views) * B;
        let mut rows = Postings::default();
        for (i, row) in d.frame.rows.iter().enumerate() {
            let mut key = 0u64;
            for source in &k.1 {
                let code = match source {
                    RootField::Column(col) => self.proof_word(&row.values[*col]),
                    RootField::Fixed(x) => *x,
                };
                key = (key << bits) | u64::from(code);
            }
            rows.entry(key).or_default().push(i);
        }
        let rows = Rc::new(rows);
        self.root_domain.stats.source_index_rows += d.frame.rows.len() as u64;
        self.root_domain.stats.source_index_builds += 1;
        self.root_domain.charged += charge;
        self.root_domain.stats.peak_charge = self
            .root_domain
            .stats
            .peak_charge
            .max(self.root_domain.charged);
        self.root_domain.by_key.insert(
            k,
            (
                d.frame.generation,
                d.frame.born_at_union,
                charge,
                rows.clone(),
            ),
        );
        Some(rows)
    }
    fn select_root_domain(&mut self, c: &Context<'_>, d: &StackStep) -> Result<()> {
        let wm = c.watermark;
        let size = d.frame.rows.len();
        if !c.rule.seminaive || wm == 0 || size < self.root_domain.min_rows {
            return Ok(());
        }
        self.root_domain.stats.checked += 1;
        let plan = &self.forward.active[0];
        if plan.unkeyed_max >= wm {
            self.root_domain.stats.unkeyed += 1;
            return Ok(());
        }
        let cap = size.saturating_mul(self.root_domain.percent) / 100;
        // A fresh root is always permitted. Old roots need a compatible fresh source
        // somewhere in the remaining typed query. Union these necessary possibilities.
        let mut constraints = Vec::with_capacity(plan.tests.len());
        for test in &plan.tests {
            let versions = test.dir.fresh_keys.get_or_init(|| {
                let mut v: Vec<_> = test
                    .dir
                    .rows
                    .iter()
                    .map(|(&key, &age)| (age, key))
                    .collect();
                v.sort_unstable();
                v
            });
            let start = versions.partition_point(|(age, _)| *age < wm);
            if start == versions.len() {
                continue;
            }
            let mut fields = Fields::new();
            let mut dynamic = false;
            for src in &test.key {
                let f = match src {
                    PortSource::Literal(v) => RootField::Fixed(*v),
                    PortSource::Slot(slot) => {
                        let Some(i) = c.rule.query[d.atom]
                            .args
                            .iter()
                            .position(|a| matches!(a,Arg::Slot(id) if id==slot))
                        else {
                            return Err("root signature was not supplied by the pivot".into());
                        };
                        dynamic = true;
                        RootField::Column(i)
                    }
                };
                fields.push(f);
            }
            if !dynamic {
                let key = fields.iter().fold(0u64, |k, f| match f {
                    RootField::Fixed(x) => {
                        (k << ((1 + self.forward.extra_views) * B)) | u64::from(*x)
                    }
                    _ => unreachable!(),
                });
                if test.dir.rows.get(&key).is_some_and(|age| *age >= wm) {
                    self.root_domain.stats.unkeyed += 1;
                    return Ok(());
                }
                continue;
            }
            if versions.len() - start > cap {
                self.root_domain.stats.dense += 1;
                return Ok(());
            }
            constraints.push((fields, test.dir.clone(), start));
        }
        let epochs = self.epoch_order(d);
        let first = epochs.partition_point(|(age, _)| *age < wm);
        if epochs.len() - first > cap {
            self.root_domain.stats.dense += 1;
            return Ok(());
        }
        let mut positions: Vec<usize> = epochs[first..].iter().map(|x| x.1).collect();
        for (fields, dir, start) in constraints {
            let Some(postings) = self.root_postings(d, fields) else {
                return Ok(());
            };
            for &(_, key) in &dir.fresh_keys.get().unwrap()[start..] {
                self.root_domain.stats.fresh_keys += 1;
                if let Some(rows) = postings.get(&key) {
                    positions.extend(rows);
                }
                if positions.len() > cap {
                    positions.sort_unstable();
                    positions.dedup();
                    if positions.len() > cap {
                        self.root_domain.stats.dense += 1;
                        return Ok(());
                    }
                }
            }
        }
        positions.sort_unstable();
        positions.dedup();
        self.root_domain.stats.used += 1;
        self.root_domain.stats.rows_before += size as u64;
        self.root_domain.stats.rows_after += positions.len() as u64;
        self.root_domain.current = Some(Rc::new(positions));
        Ok(())
    }
}
