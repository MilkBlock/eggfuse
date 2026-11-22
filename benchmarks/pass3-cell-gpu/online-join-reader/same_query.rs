// Included in the named receiver. Each signed family has the same complete LHS.
#[derive(Default)]
pub struct Families {
    ids: Vec<Option<usize>>,
    run: usize,
    ready: BTreeMap<usize, Batch>,
    tables: BTreeMap<usize, Vec<usize>>,
    carry: bool,
    pub cross_run: u64,
    pub internal: u64,
    pub signed: u64,
    commits: BTreeMap<u64, std::collections::BTreeSet<usize>>,
    pub projected_commits: u64,
}
struct Batch {
    rows: Vec<FamilyRow>,
    run: usize,
    watermark: u64,
    used: std::collections::BTreeSet<usize>,
    versions: Vec<u64>,
    unions: u64,
}
pub(crate) struct FamilyRow {
    serial: u64,
    values: BTreeMap<usize, crate::value::Value>,
    evidence: QueryFacts,
    epoch: u64,
}

impl Families {
    pub(crate) fn committed(&mut self, rid: usize, token: Option<(u64, bool)>) -> Result<()> {
        if let Some((serial, internal)) = token {
            if !self.commits.entry(serial).or_default().insert(rid) {
                return Err("signed token applied to the same rule twice".into());
            }
            self.projected_commits += u64::from(internal);
        }
        Ok(())
    }
    pub fn fanout(&self) -> BTreeMap<usize, u64> {
        let mut bins = BTreeMap::new();
        bins.insert(0, self.signed - self.commits.len() as u64);
        for uses in self.commits.values() {
            *bins.entry(uses.len()).or_default() += 1;
        }
        bins
    }
    pub fn compile(program: &crate::program::Program, carry: bool) -> Result<Self> {
        let mut groups = BTreeMap::new();
        for (rid, rule) in program.rules.iter().enumerate() {
            // The source scheduler alone selects which family members run.
            let signature =
                serde_json::to_vec(&(rule.seminaive, &*rule.query)).map_err(|e| e.to_string())?;
            groups.entry(signature).or_insert_with(Vec::new).push(rid);
        }
        let mut ids = vec![None; program.rules.len()];
        for group in groups.values().filter(|group| group.len() > 1) {
            for &rid in group {
                ids[rid] = Some(group[0]);
            }
        }
        let mut tables = BTreeMap::new();
        for id in ids.iter().flatten().copied() {
            tables.entry(id).or_insert_with(|| {
                let mut sources: Vec<_> = program.rules[id]
                    .query
                    .iter()
                    .filter_map(|a| match a.call {
                        Call::Table(t) => Some(t),
                        _ => None,
                    })
                    .collect();
                sources.sort_unstable();
                sources.dedup();
                sources
            });
        }
        Ok(Self {
            tables,
            carry,
            ids,
            ..Self::default()
        })
    }
}

impl Inbox {
    pub(crate) fn family_matches(
        &mut self,
        g: &crate::graph::Graph,
        run: usize,
        rid: usize,
        wm: u64,
    ) -> Result<Vec<Instance>> {
        if self.families.run != run {
            if !self.families.carry {
                self.families.ready.clear();
            }
            self.families.run = run;
        }
        let rule = &g.program.rules[rid];
        let family = self.families.ids.get(rid).copied().flatten();
        if let Some(f) = family
            && let Some(batch) = self.families.ready.get_mut(&f)
            && !batch.used.contains(&rid)
            && (batch.watermark == wm
                || self.families.carry && rule.seminaive && batch.watermark <= wm)
            && (batch.run == run
                || (self.families.carry
                    && batch.unions == g.stats.unions
                    && self.families.tables[&f]
                        .iter()
                        .map(|&t| g.query_versions[t])
                        .eq(batch.versions.iter().copied())))
        {
            batch.used.insert(rid);
            let mut projected = Vec::new();
            for row in &batch.rows {
                if rule.seminaive && row.epoch < wm {
                    continue;
                }
                let mut inputs = Slots::default();
                for &slot in rule.inputs.iter() {
                    inputs.insert(
                        slot,
                        row.values
                            .get(&slot)
                            .ok_or("missing shared query input")?
                            .clone(),
                    );
                }
                let mut instance = Instance::matched(inputs, row.evidence.clone(), row.epoch);
                instance.family_token = Some((row.serial, true));
                projected.push(instance);
            }
            if batch.run != run {
                self.families.cross_run += projected.len() as u64;
            }
            self.families.internal += projected.len() as u64;
            return Ok(projected);
        }
        let complete = crate::live_issuer::submit(g, run, rid, wm, self, family)?;
        let mut evidence = Vec::new();
        let rows = self.verify(Snapshot::new(g), rule, run, rid, wm, family, &mut evidence)?;
        if complete && !evidence.is_empty() {
            let f = family.ok_or("unsigned query evidence")?;
            let versions = if self.families.carry {
                self.families.tables[&f]
                    .iter()
                    .map(|&t| g.query_versions[t])
                    .collect()
            } else {
                Vec::new()
            };
            self.families.ready.insert(
                f,
                Batch {
                    rows: evidence,
                    run,
                    watermark: wm,
                    used: std::collections::BTreeSet::from([rid]),
                    versions,
                    unions: g.stats.unions,
                },
            );
        }
        Ok(rows)
    }
}
