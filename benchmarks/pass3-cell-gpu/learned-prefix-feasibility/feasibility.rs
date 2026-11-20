#[derive(Clone, Deserialize)]
struct ForwardConfig {
    columns: usize,
    budget: usize,
    existence: bool,
    freshness: bool,
    #[serde(default)]
    stale_control: bool,
    #[serde(default)]
    min_candidates: usize,
}
#[derive(Default, Serialize)]
struct ForwardStats {
    planned_calls: u64,
    indexes_built: u64,
    reused_indexes: u64,
    index_rows: u64,
    budget_skips: u64,
    charged_bytes: usize,
    peak_bytes: usize,
    prefixes: u64,
    probes: u64,
    rejected_absent: u64,
    rejected_old: u64,
    rejected_receipts: u64,
}
#[derive(Clone, Copy, Hash, Eq, PartialEq)]
struct ColumnSet {
    table: usize,
    len: usize,
    cols: [usize; 3],
}
struct PortDirectory {
    generation: u64,
    union_generation: u64,
    rows: rustc_hash::FxHashMap<u32, u64>,
    charge: usize,
}
#[derive(Clone, Copy)]
enum PortSource {
    Literal(u16),
    Slot(usize),
}
struct PortTest {
    dir: Rc<PortDirectory>,
    key: smallvec::SmallVec<[PortSource; 3]>,
    newly_bound: bool,
}
#[derive(Default)]
struct ForwardStep {
    tests: Vec<PortTest>,
    unkeyed_max: u64,
}
#[derive(Default)]
struct ForwardState {
    config: Option<ForwardConfig>,
    indexes: rustc_hash::FxHashMap<ColumnSet, Rc<PortDirectory>>,
    active: Vec<ForwardStep>,
    stats: ForwardStats,
}
pub fn use_forward(value: Json) -> Result<()> {
    let config: ForwardConfig = serde_json::from_value(value).map_err(|e| e.to_string())?;
    if !(1..=3).contains(&config.columns)
        || config.budget == 0
        || !(config.existence || config.freshness)
    {
        return Err("invalid forward viability policy".into());
    }
    STORE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("missing learned pointer proposer")?;
        if s.mode != "learned"
            || !s.seal
            || s.accel != 4
            || s.radius != 0
            || !s.packed_lookup
            || s.raw_cache.enabled
        {
            return Err(
                "forward viability requires packed, sealed, zero-radius neural proposals".into(),
            );
        }
        s.forward.config = Some(config);
        Ok(())
    })
}
impl Store {
    // Only the maximum visible epoch and learned signature are returned by each directory.
    // No index provides a matching row address or an RHS binding.
    fn viability_index(
        &mut self,
        cols: ColumnSet,
        frame: &Rc<Frame>,
        union: u64,
        limit: usize,
    ) -> Option<Rc<PortDirectory>> {
        if let Some(old) = self.forward.indexes.get(&cols)
            && old.generation == frame.generation
            && old.union_generation == union
        {
            self.forward.stats.reused_indexes += 1;
            return Some(old.clone());
        }
        if let Some(old) = self.forward.indexes.remove(&cols) {
            self.forward.stats.charged_bytes -= old.charge;
        }
        // Conservative upper bound on retained per-entry storage including load factor.
        let charge = 128usize.saturating_add(64usize.saturating_mul(frame.rows.len()));
        if charge.saturating_add(self.forward.stats.charged_bytes) > limit {
            self.forward.stats.budget_skips += 1;
            return None;
        }
        let mut rows = rustc_hash::FxHashMap::default();
        for row in &frame.rows {
            let mut key = 0u32;
            for &col in &cols.cols[..cols.len] {
                key = (key << B) | u32::from(self.code(&row.values[col]).key);
            }
            let high = rows.entry(key).or_insert(0u64);
            *high = (*high).max(row.epoch);
        }
        self.forward.stats.index_rows += frame.rows.len() as u64;
        self.forward.stats.indexes_built += 1;
        let dir = Rc::new(PortDirectory {
            generation: frame.generation,
            union_generation: union,
            rows,
            charge,
        });
        self.forward.indexes.insert(cols, dir.clone());
        self.forward.stats.charged_bytes += charge;
        self.forward.stats.peak_bytes = self
            .forward
            .stats
            .peak_bytes
            .max(self.forward.stats.charged_bytes);
        Some(dir)
    }

    fn prepare_forward(
        &mut self,
        c: &Context<'_>,
        steps: &mut [StackStep],
        slot_count: &mut usize,
    ) -> Result<()> {
        let cfg = self.forward.config.clone().unwrap();
        if steps[0].frame.rows.len() < cfg.min_candidates {
            return Ok(());
        }
        let mut known = BTreeMap::<usize, (usize, usize)>::new();
        let mut stages = Vec::with_capacity(steps.len());
        for depth in 0..steps.len() {
            let current = &c.rule.query[steps[depth].atom];
            for (col, arg) in current.args.iter().enumerate() {
                if let Arg::Slot(slot) = arg {
                    known.entry(*slot).or_insert((depth, col));
                }
            }
            let mut stage = ForwardStep::default();
            for &(id, _, _) in c.inst.iter().skip(depth + 1) {
                let atom = &c.rule.query[id];
                let Call::Table(table) = atom.call else {
                    continue;
                };
                let frame = self.frame(c.graph, table)?;
                let mut cols = ColumnSet {
                    table,
                    len: 0,
                    cols: [0; 3],
                };
                let mut key = smallvec::SmallVec::<[PortSource; 3]>::new();
                let mut newly_bound = false;
                for (col, arg) in atom.args.iter().enumerate() {
                    let origin = match arg {
                        Arg::Literal(v) => {
                            PortSource::Literal(self.code(&canon(v, &c.graph.parents)).key)
                        }
                        Arg::Slot(slot) => {
                            let Some(&(first, pcol)) = known.get(slot) else {
                                continue;
                            };
                            let published = &mut steps[first].publish;
                            if !published.iter().any(|(_, v)| v == slot) {
                                published.push((pcol, *slot));
                            }
                            *slot_count = (*slot_count).max(*slot + 1);
                            newly_bound |= first == depth;
                            PortSource::Slot(*slot)
                        }
                    };
                    cols.cols[cols.len] = col;
                    cols.len += 1;
                    key.push(origin);
                    if cols.len == cfg.columns {
                        break;
                    }
                }
                let first_test = depth == 0 || newly_bound;
                if !key.is_empty()
                    && (cfg.existence && first_test
                        || cfg.freshness && c.rule.seminaive && frame.max_epoch >= c.watermark)
                    && let Some(dir) =
                        self.viability_index(cols, &frame, c.graph.stats.unions, cfg.budget)
                {
                    stage.tests.push(PortTest {
                        dir,
                        key,
                        newly_bound: first_test,
                    });
                } else {
                    stage.unkeyed_max = stage.unkeyed_max.max(frame.max_epoch);
                }
            }
            stages.push(stage);
        }
        self.forward.stats.planned_calls += 1;
        self.forward.active = stages;
        Ok(())
    }
}
impl ForwardState {
    fn permits(
        &mut self,
        depth: usize,
        ports: &[Option<Port>],
        now: u64,
        watermark: u64,
        semi: bool,
    ) -> Result<bool> {
        let cfg = self.config.as_ref().unwrap();
        if cfg.stale_control {
            self.stats.rejected_receipts += 1;
            return Ok(true);
        }
        let step = &self.active[depth];
        let mut upper = now.max(step.unkeyed_max);
        self.stats.prefixes += 1;
        for test in &step.tests {
            let need_presence = cfg.existence && test.newly_bound;
            if !need_presence && (!cfg.freshness || !semi || upper >= watermark) {
                continue;
            }
            self.stats.probes += 1;
            let mut key = 0u32;
            for arg in &test.key {
                let code = match arg {
                    PortSource::Literal(code) => *code,
                    PortSource::Slot(slot) => {
                        ports[*slot].ok_or("missing proposed source slot")?.key
                    }
                };
                key = (key << B) | u32::from(code);
            }
            if let Some(&high) = test.dir.rows.get(&key) {
                upper = upper.max(high);
            } else if need_presence {
                self.stats.rejected_absent += 1;
                return Ok(false);
            }
        }
        if cfg.freshness && semi && upper < watermark {
            self.stats.rejected_old += 1;
            return Ok(false);
        }
        Ok(true)
    }
}
