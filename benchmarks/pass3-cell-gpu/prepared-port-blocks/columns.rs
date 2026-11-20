#[derive(Default, Serialize)]
struct PreparedStats {
    calls: u64,
    index_bindings: u64,
    hoisted_probes: u64,
    columns_built: u64,
    coded_values: u64,
    reused_values: u64,
    columns_reused: u64,
    peak_column_bytes: usize,
    refusals: u64,
}
#[derive(Default)]
struct PreparedPorts {
    mode: u64,
    budget: usize,
    bytes: usize,
    columns: rustc_hash::FxHashMap<(usize, usize), (u64, u64, Rc<Vec<u16>>)>,
    stats: PreparedStats,
}
#[derive(Default)]
struct PreparedStep {
    index: Option<Rc<Index>>,
    columns_ready: bool,
    publish: Vec<(usize, Rc<Vec<u16>>)>,
    extra: rustc_hash::FxHashMap<usize, Rc<Vec<u16>>>,
}
pub fn configure_prepared(config: Json) -> Result<()> {
    let mode = config["mode"]
        .as_u64()
        .ok_or("missing prepared port mode")?;
    let budget = usize::try_from(
        config["bytes"]
            .as_u64()
            .ok_or("missing prepared column budget")?,
    )
    .map_err(|e| e.to_string())?;
    if !(1..=3).contains(&mode) {
        return Err("unknown prepared port mode".into());
    }
    STORE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("no active trained scorer")?;
        if !s.packed_lookup
            || s.views != 1
            || s.radius != 0
            || s.mode != "learned"
            || s.signatures.enabled
            || !s
                .model
                .q
                .iter()
                .flatten()
                .zip(s.model.k.iter().flatten())
                .all(|(a, b)| a.to_bits() == b.to_bits())
        {
            return Err("narrow source ports require one tied, frozen, zero-radius view".into());
        }
        s.prepared.mode = mode;
        s.prepared.budget = budget;
        Ok(())
    })
}
impl Store {
    fn narrow_column(&mut self, d: &StackStep, col: usize) -> Option<Rc<Vec<u16>>> {
        let key = (d.table, col);
        if let Some((version, union, words)) = self.prepared.columns.get(&key)
            && *version == d.frame.generation
            && *union == d.frame.born_at_union
        {
            self.prepared.stats.columns_reused += 1;
            return Some(words.clone());
        }
        if let Some((_, _, old)) = self.prepared.columns.remove(&key) {
            self.prepared.bytes -= 2 * old.capacity();
        }
        if self.prepared.bytes + 2 * d.frame.rows.len() > self.prepared.budget {
            self.prepared.stats.refusals += 1;
            return None;
        }
        let words = Rc::new(
            d.frame
                .rows
                .iter()
                .map(|r| self.code(&r.values[col]).key)
                .collect::<Vec<_>>(),
        );
        self.prepared.stats.columns_built += 1;
        self.prepared.stats.coded_values += words.len() as u64;
        self.prepared.bytes += 2 * words.capacity();
        self.prepared.stats.peak_column_bytes = self
            .prepared
            .stats
            .peak_column_bytes
            .max(self.prepared.bytes);
        self.prepared.columns.insert(
            key,
            (d.frame.generation, d.frame.born_at_union, words.clone()),
        );
        Some(words)
    }
    fn prepare_columns(&mut self, steps: &mut [StackStep]) {
        self.prepared.stats.calls += 1;
        for d in steps {
            let mut c = PreparedStep::default();
            if self.prepared.mode != 2
                && let Some(&(col, _)) = d.shared.first()
            {
                c.index = Some(self.index(d.table, col, &d.frame));
                self.prepared.stats.index_bindings += 1;
            }
            if self.prepared.mode != 1 {
                c.columns_ready = true;
                for &(col, slot) in &d.publish {
                    if let Some(words) = self.narrow_column(d, col) {
                        c.publish.push((slot, words))
                    } else {
                        c.columns_ready = false;
                        break;
                    }
                }
                if c.columns_ready {
                    for &(col, _) in d.shared.iter().skip(1) {
                        if let Some(words) = self.narrow_column(d, col) {
                            c.extra.insert(col, words);
                        } else {
                            c.columns_ready = false;
                            break;
                        }
                    }
                }
            }
            d.compiled = Some(c);
        }
    }
}
