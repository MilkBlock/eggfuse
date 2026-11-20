#[derive(Default, serde::Serialize)]
struct OrderWork {
    calls: u64,
    rows: u64,
    matched_layouts: u64,
    layout_fallbacks: u64,
    key_fields: u64,
    varying_fields: u64,
    identical_batches: u64,
    prefixed_batches: u64,
    duplicates: u64,
    permutations: u64,
    time_ns: u64,
}
#[derive(Default)]
struct BindingOrder {
    mode: usize,
    clock: bool,
    min: usize,
    stats: OrderWork,
    // Reusable vectors hold source ordinals and scalar prefixes, not graph bindings.
    permutation: Vec<usize>,
    dest: Vec<usize>,
    prefix: Vec<[u64; 2]>,
    plans: rustc_hash::FxHashMap<usize, Vec<usize>>,
}
impl Executor {
    pub fn configure_binding_order(&mut self, v: &serde_json::Value) -> Result<()> {
        let mode = v["mode"].as_u64().ok_or("missing binding ordering mode")? as usize;
        if mode > 4 {
            return Err("unknown binding ordering mode".into());
        }
        self.order_policy.mode = mode;
        self.order_policy.min = v["min"].as_u64().unwrap_or(4) as usize;
        self.order_policy.clock = v["clock"].as_bool().unwrap_or(false);
        Ok(())
    }
    pub fn binding_order_report(&self) -> serde_json::Value {
        serde_json::json!(self.order_policy.stats)
    }
}
impl BindingOrder {
    fn sort(&mut self, rid: usize, keys: &[usize], rows: &mut Vec<Binding>) -> bool {
        let n = rows.len();
        if n < self.min || n == 0 {
            return false;
        }
        self.stats.calls += 1;
        self.stats.rows += n as u64;
        let positions = self.plans.entry(rid).or_default();
        let first = rows[0].values.ordered_fields();
        if positions.len() != keys.len()
            || positions
                .iter()
                .zip(keys)
                .any(|(&p, k)| first.get(p).map(|v| &v.0) != Some(k))
        {
            positions.clear();
            for &key in keys {
                let Ok(i) = first.binary_search_by_key(&key, |x| x.0) else {
                    self.stats.layout_fallbacks += 1;
                    return false;
                };
                positions.push(i);
            }
        }
        let mut varying = smallvec::SmallVec::<[bool; 16]>::new();
        varying.resize(keys.len(), self.mode < 3);
        for row in rows.iter().skip(1) {
            let fields = row.values.ordered_fields();
            for (i, (&pos, &key)) in positions.iter().zip(keys).enumerate() {
                let Some((slot, v)) = fields.get(pos) else {
                    self.stats.layout_fallbacks += 1;
                    return false;
                };
                if *slot != key {
                    self.stats.layout_fallbacks += 1;
                    return false;
                }
                if !varying[i] && v != &first[pos].1 {
                    varying[i] = true;
                }
            }
        }
        let cols = positions
            .iter()
            .zip(&varying)
            .filter_map(|(&p, &yes)| yes.then_some(p))
            .collect::<smallvec::SmallVec<[usize; 16]>>();
        self.stats.matched_layouts += 1;
        self.stats.key_fields += (n * keys.len()) as u64;
        self.stats.varying_fields += (n * cols.len()) as u64;
        if cols.is_empty() {
            rows.truncate(1);
            self.stats.identical_batches += 1;
            self.stats.duplicates += (n - 1) as u64;
            return true;
        }
        let cmp = |a: &Binding, b: &Binding, cols: &[usize]| {
            let x = a.values.ordered_fields();
            let y = b.values.ordered_fields();
            for &p in cols {
                let d = x[p].1.cmp(&y[p].1);
                if !d.is_eq() {
                    return d;
                }
            }
            std::cmp::Ordering::Equal
        };
        if self.mode == 1 || self.mode == 3 {
            rows.sort_by(|a, b| cmp(a, b, &cols));
        } else {
            self.permutation.clear();
            self.permutation.extend(0..n);
            let prefix_len = if self.mode == 4 {
                let k = cols.len().min(2);
                self.prefix.clear();
                self.prefix.reserve(n);
                'pack: for row in rows.iter() {
                    let mut pair = [0; 2];
                    for (i, &pos) in cols[..k].iter().enumerate() {
                        pair[i] = match (&first[pos].1, &row.values.ordered_fields()[pos].1) {
                            (Value::Eq(_), Value::Eq(id)) => *id,
                            (Value::Int(_), Value::Int(value)) => (*value as u64) ^ (1u64 << 63),
                            _ => {
                                self.prefix.clear();
                                break 'pack;
                            }
                        };
                    }
                    self.prefix.push(pair);
                }
                if self.prefix.len() == n {
                    self.stats.prefixed_batches += 1;
                    k
                } else {
                    0
                }
            } else {
                0
            };
            let prefix = &self.prefix;
            self.permutation.sort_unstable_by(|&a, &b| {
                let lead = if prefix_len > 0 {
                    prefix[a].cmp(&prefix[b])
                } else {
                    std::cmp::Ordering::Equal
                };
                lead.then_with(|| cmp(&rows[a], &rows[b], &cols[prefix_len..]))
                    .then(a.cmp(&b))
            });
            self.dest.resize(n, 0);
            for (new, &old) in self.permutation.iter().enumerate() {
                self.dest[old] = new;
            }
            for i in 0..n {
                while self.dest[i] != i {
                    let j = self.dest[i];
                    rows.swap(i, j);
                    self.dest.swap(i, j);
                    self.stats.permutations += 1;
                }
            }
        }
        rows.dedup_by(|a, b| cmp(a, b, &cols).is_eq());
        self.stats.duplicates += (n - rows.len()) as u64;
        true
    }
}
