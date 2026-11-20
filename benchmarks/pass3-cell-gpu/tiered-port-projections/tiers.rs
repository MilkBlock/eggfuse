#[derive(Default, Serialize)]
struct TierStats {
    primary_only: u64,
    builds: u64,
    coded_rows: u64,
    reuses: u64,
    extra_reads: u64,
    published_reads: u64,
    peak_bytes: usize,
    refused: u64,
}
#[derive(Default)]
struct Tiered {
    primary: bool,
    materialize: bool,
    budget: usize,
    bytes: usize,
    stats: TierStats,
    columns: rustc_hash::FxHashMap<(usize, usize), (u64, u64, Rc<Vec<u32>>)>,
}
#[derive(Default)]
struct TierStep {
    index: Option<Rc<Index>>,
    complete: bool,
    publish: Vec<(usize, Rc<Vec<u32>>)>,
    extra: rustc_hash::FxHashMap<usize, Rc<Vec<u32>>>,
}
fn decode_port(p: u32) -> Port {
    let mask = (1u32 << B) - 1;
    let a = (p & mask) as u16;
    let b = ((p >> B) & mask) as u16;
    let c = ((p >> (2 * B)) & mask) as u16;
    Port {
        query: a,
        key: a,
        certified: 0,
        uncertain: 0,
        extra: [[b, b, 0, 0], [c, c, 0, 0]],
    }
}
pub fn enable_tiers(config: Json) -> Result<()> {
    STORE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("missing typed port policy")?;
        if !s.packed_lookup
            || s.views < 2
            || s.views > 3
            || s.radius != 0
            || s.baked_codes.is_none()
            || s.prepared.mode != 0
            || s.mode != "learned"
            || !s
                .model
                .q
                .iter()
                .flatten()
                .zip(s.model.k.iter().flatten())
                .all(|(a, b)| a.to_bits() == b.to_bits())
        {
            return Err(
                "multi-view port block requires a tied learned zero-radius projection".into(),
            );
        }
        let views = config["evidence_views"].as_u64().unwrap_or(1) as usize;
        if views == 0
            || views > s.views
            || s.forward
                .config
                .as_ref()
                .is_none_or(|c| c.columns * views * B > 64)
        {
            return Err("joint evidence does not fit in a typed u64 key".into());
        }
        s.forward.extra_views = views - 1;
        s.tier.primary = config["primary"].as_bool().unwrap_or(false);
        s.tier.materialize = config["columns"].as_bool().unwrap_or(false);
        s.tier.budget = usize::try_from(config["bytes"].as_u64().ok_or("missing column budget")?)
            .map_err(|e| e.to_string())?;
        Ok(())
    })
}
impl Store {
    fn proof_word(&mut self, v: &Value) -> u32 {
        if self.forward.extra_views == 0 {
            return self.key_only(v) as u32;
        }
        let n = 1 + self.forward.extra_views;
        signature(self.code(v), false, n)
    }
    fn key_only(&mut self, v: &Value) -> u16 {
        if self.tier.primary {
            self.tier.stats.primary_only += 1;
            self.baked_codes.as_ref().unwrap().pair(mix(code_seed(v))).1
        } else {
            self.code(v).key
        }
    }
    fn tier_column(&mut self, d: &StackStep, col: usize) -> Option<Rc<Vec<u32>>> {
        let k = (d.table, col);
        let version = d.frame.generation;
        let union = d.frame.born_at_union;
        if let Some((v, u, rc)) = self.tier.columns.get(&k)
            && *v == version
            && *u == union
        {
            self.tier.stats.reuses += 1;
            return Some(rc.clone());
        }
        if let Some((_, _, old)) = self.tier.columns.remove(&k) {
            self.tier.bytes -= 4 * old.capacity();
        }
        if self.tier.bytes + 4 * d.frame.rows.len() > self.tier.budget {
            self.tier.stats.refused += 1;
            return None;
        }
        let words = Rc::new(
            d.frame
                .rows
                .iter()
                .map(|row| signature(self.code(&row.values[col]), false, self.views))
                .collect::<Vec<_>>(),
        );
        self.tier.bytes += 4 * words.capacity();
        self.tier.stats.peak_bytes = self.tier.stats.peak_bytes.max(self.tier.bytes);
        self.tier.stats.builds += 1;
        self.tier.stats.coded_rows += words.len() as u64;
        self.tier.columns.insert(k, (version, union, words.clone()));
        Some(words)
    }
    fn prepare_tiers(&mut self, steps: &mut [StackStep]) {
        for d in steps {
            let mut p = TierStep {
                complete: true,
                ..Default::default()
            };
            if let Some(&(col, _)) = d.shared.first() {
                p.index = Some(self.index(d.table, col, &d.frame));
            }
            for &(col, slot) in &d.publish {
                if let Some(w) = self.tier_column(d, col) {
                    p.publish.push((slot, w))
                } else {
                    p.complete = false;
                    break;
                }
            }
            if p.complete {
                for &(col, _) in d.shared.iter().skip(1) {
                    if let Some(w) = self.tier_column(d, col) {
                        p.extra.insert(col, w);
                    } else {
                        p.complete = false;
                        break;
                    }
                }
            }
            d.tier = Some(p);
        }
    }
}
