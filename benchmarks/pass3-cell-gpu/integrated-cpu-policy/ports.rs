#[derive(Default, Serialize)]
struct PortIndexStats {
    epoch_rereads: u64,
    epoch_updates: u64,
    epoch_audit: u64,
    skipped_updates: u64,
    scanned_epoch_headers: u64,
    skipped_cold_rows: u64,
    full_hits: u64,
    published_columns: u64,
    pivot_reads: u64,
    frame_field_reads: u64,
    reused_after_change: u64,
    changed_rebuilds: u64,
    source_rows: u64,
    evicted: u64,
    notifications: u64,
    tracked_batches: u64,
    ineligible_transitions: u64,
    overflow: u64,
    saved_directory_reads: u64,
    seeded_from_suffix: u64,
    verified: u64,
    peak_bytes: usize,
    peak_pending: usize,
}
struct TypedColumn {
    generation: u64,
    union: u64,
    tick: u64,
    codes: Rc<Vec<u16>>,
    epochs: Vec<u64>,
    addresses: Vec<u64>,
    through: u64,
    dirty: std::collections::BTreeSet<u64>,
    complete: bool,
}
impl TypedColumn {
    fn bytes(&self) -> usize {
        self.codes.capacity() * 2 + self.epochs.capacity() * 8 + self.addresses.capacity() * 8
    }
}
#[derive(Default)]
struct TypedPortIndexes {
    maintain: bool,
    sparse: bool,
    floors: HashMap<EpochKey, u64>,
    budget: usize,
    delta: bool,
    clock: u64,
    columns: HashMap<EpochKey, TypedColumn>,
    stats: PortIndexStats,
}
fn typed_word(w: Dependency) -> u64 {
    match w {
        Dependency::Fact(f) => (u64::from(f.cell) << 32) | u64::from(f.op),
        Dependency::Function(i) => i as u64,
    }
}
impl TypedPortIndexes {
    fn room(&mut self, want: usize) {
        let mut used: usize = self.columns.values().map(TypedColumn::bytes).sum();
        while used + want > self.budget {
            let Some(k) = self
                .columns
                .iter()
                .min_by_key(|(_, v)| v.tick)
                .map(|(k, _)| *k)
            else {
                break;
            };
            let r = self.columns.remove(&k).unwrap();
            used -= r.bytes();
            self.stats.evicted += 1;
        }
    }
    fn insert(
        &mut self,
        k: EpochKey,
        g: &Graph,
        codes: Vec<u16>,
        epochs: Vec<u64>,
        addresses: Vec<u64>,
    ) -> Rc<Vec<u16>> {
        let codes = Rc::new(codes);
        let col = TypedColumn {
            generation: g.query_versions[k.0],
            union: g.stats.unions,
            tick: self.clock,
            codes: codes.clone(),
            epochs,
            addresses,
            through: g.query_versions[k.0],
            dirty: Default::default(),
            complete: true,
        };
        self.room(col.bytes());
        self.columns.insert(k, col);
        self.stats.published_columns += 1;
        self.stats.peak_bytes = self
            .stats
            .peak_bytes
            .max(self.columns.values().map(TypedColumn::bytes).sum());
        codes
    }
    fn publish(&mut self, g: &Graph) {
        if self.columns.is_empty() {
            return;
        }
        // Per cached column, require every generation change to arrive through a covered
        // publication. Coalesced/partial notifications conservatively force a fresh decode.
        for (&(t, _), v) in &mut self.columns {
            if !v.complete {
                continue;
            }
            let gen_now = g.query_versions[t];
            if gen_now == v.through {
                continue;
            }
            let changes = g
                .changes
                .tables()
                .find(|(table, _)| *table == t)
                .map(|(_, c)| c);
            if v.union != g.stats.unions
                || changes.is_none_or(|b| gen_now.saturating_sub(v.through) > b.len() as u64)
            {
                v.complete = false;
                self.stats.ineligible_transitions += 1;
                continue;
            }
            let changes = changes.unwrap();
            if v.dirty.len() + changes.len() > 256 {
                v.complete = false;
                self.stats.overflow += 1;
                continue;
            }
            self.stats.tracked_batches += 1;
            self.stats.notifications += changes.len() as u64;
            v.dirty.extend(changes.keys().copied().map(typed_word));
            v.through = gen_now;
            self.stats.peak_pending = self.stats.peak_pending.max(v.dirty.len());
        }
    }
    fn for_pivot(
        &mut self,
        g: &Graph,
        t: usize,
        col: usize,
        bank: &[SourceHeader],
        frame: Option<&Rc<Frame>>,
        code: &impl Fn(&Value) -> usize,
        audit: bool,
    ) -> Result<Option<Rc<Vec<u16>>>> {
        let key = (t, col);
        let ver = g.query_versions[t];
        let union = g.stats.unions;
        self.clock += 1;
        if let Some(x) = self.columns.get_mut(&key)
            && x.generation == ver
            && x.union == union
            && x.codes.len() == bank.len()
        {
            if audit {
                for (i, h) in bank.iter().enumerate() {
                    let r = g
                        .row(h.source.ok_or("typed null parent")?)?
                        .ok_or("typed missing parent")?;
                    if r.table != t
                        || r.hidden
                        || r.epoch != h.version
                        || code(&r.values[col]) != usize::from(x.codes[i])
                    {
                        return Err("typed immutable source audit failed".into());
                    }
                    self.stats.verified += 1;
                }
            }
            self.stats.full_hits += bank.len() as u64;
            x.tick = self.clock;
            return Ok(Some(x.codes.clone()));
        }
        if bank.len() * if self.delta { 18 } else { 10 } > self.budget {
            return Ok(None);
        }
        let old = self.columns.remove(&key);
        let prior = old
            .as_ref()
            .filter(|a| self.delta && a.complete && a.through == ver && a.union == union);
        let mut prior_i = 0;
        let mut keys = Vec::with_capacity(bank.len());
        let mut epochs = Vec::with_capacity(bank.len());
        let mut addresses = if self.delta {
            Vec::with_capacity(bank.len())
        } else {
            vec![]
        };
        if prior.is_some() {
            self.stats.changed_rebuilds += 1
        }
        for (i, h) in bank.iter().enumerate() {
            let dep = h.source.ok_or("null typed source fact")?;
            let word = typed_word(dep);
            if self.delta {
                addresses.push(word)
            }
            epochs.push(h.version);
            if let Some(x) = prior {
                while prior_i < x.addresses.len() && x.addresses[prior_i] < word {
                    prior_i += 1
                }
                if x.addresses.get(prior_i) == Some(&word)
                    && x.epochs[prior_i] == h.version
                    && !x.dirty.contains(&word)
                {
                    if audit {
                        let r = g.row(dep)?.ok_or("incremental typed source missing")?;
                        if r.hidden
                            || r.table != t
                            || r.epoch != h.version
                            || code(&r.values[col]) != x.codes[prior_i] as usize
                        {
                            return Err("changed typed source audit failed".into());
                        }
                        self.stats.verified += 1;
                    }
                    keys.push(x.codes[prior_i]);
                    self.stats.reused_after_change += 1;
                    continue;
                }
            }
            let tmp;
            let row = if let Some(r) = frame
                .and_then(|f| f.rows.get(i))
                .filter(|r| r.witness == dep && r.epoch == h.version)
            {
                self.stats.frame_field_reads += 1;
                r
            } else {
                self.stats.pivot_reads += 1;
                tmp = g.row(dep)?.ok_or("missing immutable typed source")?;
                &tmp
            };
            keys.push(code(&row.values[col]) as u16)
        }
        self.stats.source_rows += bank.len() as u64;
        Ok(Some(self.insert(key, g, keys, epochs, addresses)))
    }
    fn epoch_directory(&mut self, t: usize, col: usize, g: &Graph) -> Option<Rc<Vec<u64>>> {
        let x = self.columns.get_mut(&(t, col))?;
        if x.generation != g.query_versions[t] || x.union != g.stats.unions {
            return None;
        }
        self.clock += 1;
        x.tick = self.clock;
        let mut hi = vec![0; 1 << B];
        for (&key, &epoch) in x.codes.iter().zip(&x.epochs) {
            hi[key as usize] = hi[key as usize].max(epoch)
        }
        self.stats.saved_directory_reads += x.codes.len() as u64;
        Some(Rc::new(hi))
    }
    fn offer_rows(
        &mut self,
        t: usize,
        col: usize,
        g: &Graph,
        rows: &[Row],
        code: &impl Fn(&Value) -> usize,
    ) {
        if self.budget == 0 || rows.len() * if self.delta { 18 } else { 10 } > self.budget {
            return;
        }
        let k = (t, col);
        if self
            .columns
            .get(&k)
            .is_some_and(|x| x.generation == g.query_versions[t] && x.union == g.stats.unions)
        {
            return;
        }
        self.columns.remove(&k);
        let keys = rows.iter().map(|r| code(&r.values[col]) as u16).collect();
        let epochs = rows.iter().map(|r| r.epoch).collect();
        let ids = if self.delta {
            rows.iter().map(|r| typed_word(r.witness)).collect()
        } else {
            vec![]
        };
        self.clock += 1;
        self.insert(k, g, keys, epochs, ids);
        self.stats.seeded_from_suffix += 1
    }
}

// Retirements may leave an old high value behind. This is conservative: a high bucket may
// keep an unnecessary learned input, while a negative proof always uses an upper bound.
impl Store {
    fn publish_epoch_bounds(&mut self, g: &Graph) {
        let s = &mut self.single_epochs;
        if !s.typed.maintain || s.private.is_empty() {
            return;
        }
        let Some(codebook) = &self.baked_codes else {
            return;
        };
        for (t, changes) in g.changes.tables() {
            let mut keys = smallvec::SmallVec::<[(usize, usize); 8]>::new();
            for (&k, (generation, union, _)) in &s.private {
                if k.0 != t || *generation == g.query_versions[t] {
                    continue;
                }
                if *union == g.stats.unions
                    && g.query_versions[t].saturating_sub(*generation) <= changes.len() as u64
                {
                    keys.push(k)
                } else {
                    s.typed.stats.skipped_updates += 1
                }
            }
            if keys.is_empty() {
                continue;
            }
            let mut ok = true;
            for &dep in changes.keys() {
                let row = match g.row(dep) {
                    Ok(Some(r)) if !r.hidden && r.table == t => r,
                    Ok(_) => continue,
                    Err(_) => {
                        ok = false;
                        break;
                    }
                };
                s.typed.stats.epoch_rereads += 1;
                for &(table, col) in &keys {
                    let d = s.private.get_mut(&(table, col)).unwrap();
                    let hi = Rc::make_mut(&mut d.2);
                    let k = codebook.port(&row.values[col], self.views).key as usize;
                    hi[k] = hi[k].max(row.epoch);
                }
            }
            if ok {
                for k in keys {
                    let d = s.private.get_mut(&k).unwrap();
                    let floor = s.typed.floors.get(&k).copied().unwrap_or(0);
                    if self.detailed {
                        for w in g.witnesses(t) {
                            if let Some(row) = g.row(w).expect("guard-index source audit")
                                && !row.hidden
                                && row.epoch >= floor
                            {
                                let code = codebook.port(&row.values[k.1], self.views).key as usize;
                                assert!(
                                    d.2[code] >= row.epoch,
                                    "incremental epoch bound lost a fresh address"
                                );
                                s.typed.stats.epoch_audit += 1;
                            }
                        }
                    }
                    d.0 = g.query_versions[t];
                    s.typed.stats.epoch_updates += 1;
                }
            } else {
                for k in keys {
                    s.private.remove(&k);
                }
            }
        }
    }
}
