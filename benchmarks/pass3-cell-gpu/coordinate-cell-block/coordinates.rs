#[derive(Default, Serialize)]
struct WordCounts {
    pages: u64,
    lanes: u64,
    words: u64,
    loaded: u64,
    lookups: u64,
    local_checks: u64,
    audited: u64,
    nonfirst_reuse: u64,
    word_hits: u64,
    cap_fallbacks: u64,
    port_maps: u64,
}
#[derive(Default)]
struct WordProgram {
    mode: u8,
    stats: WordCounts,
}
pub fn configure_word_verifier(mode: u64) -> Result<()> {
    if !(1..=3).contains(&mode) {
        return Err("unknown coordinate verifier".into());
    }
    STORE.with_borrow_mut(|source| {
        let s = source.as_mut().ok_or("missing issuer")?;
        if s.premises.mode != 9 {
            return Err("coordinate verification requires the compiled port block".into());
        }
        s.word_verifier.mode = mode as u8;
        Ok(())
    })
}

#[derive(Default)]
struct PortMemo {
    hashed: SourceMap<(usize, Dependency, u64), Option<Row>>,
    by_step: Vec<Option<(usize, Vec<Option<Option<Row>>>)>>,
    coordinates: smallvec::SmallVec<[usize; 4]>,
    filled: usize,
}
impl PortMemo {
    fn len(&self) -> usize {
        self.filled
    }
    fn get(&self, key: &(usize, Dependency, u64)) -> Option<&Option<Row>> {
        if let Some(Some((role, words))) = self.by_step.get(key.0) {
            return words[self.coordinates[*role]].as_ref();
        }
        self.hashed.get(key)
    }
    fn insert(&mut self, key: (usize, Dependency, u64), v: Option<Row>) {
        if let Some(Some((role, words))) = self.by_step.get_mut(key.0) {
            words[self.coordinates[*role]] = Some(v);
        } else {
            self.hashed.insert(key, v);
        }
        self.filled += 1;
    }
}
impl Store {
    fn read_word(
        &mut self,
        c: &Context,
        page: &MultiPage,
        j: usize,
        word: usize,
        role: &Role,
    ) -> Result<Option<Row>> {
        let rf = page.role_parent(j, word).ok_or("invalid page word")?;
        if rf.atom != role.atom {
            return Err("wrong dictionary atom".into());
        }
        self.word_verifier.stats.loaded += 1;
        let Some(row) = c.graph.row(rf.row)? else {
            return Ok(None);
        };
        if row.witness != rf.row || row.epoch != rf.version {
            return Err("wrong dictionary source version".into());
        }
        if row.hidden || row.table != role.table || row.values.len() != role.width {
            return Ok(None);
        }
        for test in &role.tests {
            self.word_verifier.stats.local_checks += 1;
            let ok = match test {
                LocalTest::Literal(col, v) => row.values[*col] == canon(v, &c.graph.parents),
                LocalTest::Equal(l, r) => row.values[*l] == row.values[*r],
            };
            if !ok {
                return Ok(None);
            }
        }
        Ok(Some(row))
    }

    fn verify_word_page(
        &mut self,
        c: &Context,
        base: &Prefix,
        page: &MultiPage,
        out: &mut Vec<Instance>,
    ) -> Result<bool> {
        let plan = self.premises.plans[self.rule]
            .clone()
            .ok_or("missing compiled role layout")?;
        let lengths: Option<Vec<_>> = (0..plan.roles.len()).map(|j| page.role_len(j)).collect();
        let Some(lengths) = lengths else {
            return Ok(false);
        };
        let total: usize = lengths.iter().sum();
        if total > 32768 {
            self.word_verifier.stats.cap_fallbacks += 1;
            return Ok(false);
        }
        self.word_verifier.stats.pages += 1;
        self.word_verifier.stats.words += total as u64;
        self.word_verifier.stats.lanes += (page.count() * plan.roles.len()) as u64;
        let mut words: Vec<Vec<Option<Option<Row>>>> =
            lengths.iter().map(|&n| vec![None; n]).collect();
        if self.word_verifier.mode == 3 {
            for (j, col) in words.iter_mut().enumerate() {
                for (i, cell) in col.iter_mut().enumerate() {
                    *cell = Some(self.read_word(c, page, j, i, &plan.roles[j])?)
                }
            }
        }
        let mut memo = PortMemo::default();
        if self.word_verifier.mode >= 2 {
            let mut room = 4096;
            for step in &plan.tail.steps {
                let tab = match (&step.call, step.parent_key) {
                    (Call::Table(_), Some(j)) if lengths[j] <= room => {
                        room -= lengths[j];
                        self.word_verifier.stats.port_maps += 1;
                        Some((j, vec![None; lengths[j]]))
                    }
                    _ => None,
                };
                memo.by_step.push(tab);
            }
        }
        let mut scratch = Vec::new();
        let mut rows = SmallRows::new();
        for i in 0..page.count() {
            rows.clear();
            memo.coordinates.clear();
            let mut epoch = 0;
            let mut pass = true;
            for (j, role) in plan.roles.iter().enumerate() {
                let code = page
                    .coordinate(i, j)?
                    .ok_or("page has no encoded coordinates")?;
                memo.coordinates.push(code);
                let cell = words[j]
                    .get_mut(code)
                    .ok_or("coordinate outside certified column")?;
                self.word_verifier.stats.lookups += 1;
                if cell.is_none() {
                    *cell = Some(self.read_word(c, page, j, code, role)?);
                } else {
                    self.word_verifier.stats.word_hits += 1;
                    self.word_verifier.stats.nonfirst_reuse += u64::from(j > 0);
                }
                let Some(row) = cell.as_ref().unwrap() else {
                    pass = false;
                    break;
                };
                if !role
                    .prior
                    .iter()
                    .all(|&(col, other, offset)| row.values[col] == rows[other].values[offset])
                {
                    pass = false;
                    break;
                }
                epoch = epoch.max(row.epoch);
                rows.push(row.clone());
            }
            if self.detailed {
                let mut reference = base.clone();
                let refs = page.read_parents(i, &mut scratch)?;
                let mut yes = true;
                for r in refs {
                    let Some(row) = c.graph.row(r.row)? else {
                        yes = false;
                        break;
                    };
                    if !extend(c.graph, c.rule, r.atom, &row, &mut reference) {
                        yes = false;
                        break;
                    }
                }
                if yes != pass
                    || (pass
                        && (epoch != reference.epoch
                            || plan.slots.iter().any(|(slot, (j, k))| {
                                reference.slots.get(slot) != Some(&rows[*j].values[*k])
                            })))
                {
                    return Err("coordinate verifier disagrees with source prefix".into());
                }
                self.word_verifier.stats.audited += 1;
            }
            if !pass {
                self.counts.raw_parent_rejects += 1;
                continue;
            }
            self.counts.verified_parent_tuples += 1;
            let exact = Prefix {
                root_recipe: page.recipe(i),
                slots: Slots::default(),
                latents: BTreeMap::new(),
                witness: vec![],
                picks: rows.len(),
                epoch,
                anchors: if self.detailed {
                    rows.iter().map(|r| r.witness).collect()
                } else {
                    vec![]
                },
            };
            self.run_block(c, &plan, &rows, epoch, exact, &mut memo, out)?;
        }
        Ok(true)
    }
}
