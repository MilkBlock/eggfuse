use crate::slots::Slots;

// Compiled positive/negative proofs for an unchanged source view. The learned gate remains the
// only producer. A previous binding can verify another issued token only after input/version checks.
#[derive(Default)]
struct ProofTable {
    union_version: u64,
    table_versions: Vec<u64>,
    known: rustc_hash::FxHashMap<Option<Dependency>, (u64, u64, Option<(Slots, QueryFacts, u64)>)>,
}
#[derive(Default)]
struct RowTable {
    generation: u64,
    union_version: u64,
    rows: rustc_hash::FxHashMap<Dependency, Option<Row>>,
    keys: rustc_hash::FxHashMap<smallvec::SmallVec<[Value; 3]>, Option<Row>>,
}
#[derive(Default, Serialize)]
struct VerificationStats {
    cache_resets: u64,
    negative_hits: u64,
    positive_hits: u64,
    displaced_positive: u64,
    pruned_by_suffix: u64,
    fresh_table_rebuild: u64,
    source_reads: u64,
    source_hits: u64,
    point_reads: u64,
    point_hits: u64,
    peak_proofs_per_rule: usize,
    peak_source_rows_per_table: usize,
    peak_points_per_table: usize,
}
#[derive(Default)]
struct VerifiedRows {
    mode: usize,
    frontiers: rustc_hash::FxHashMap<usize, (u64, u64)>,
    tables: rustc_hash::FxHashMap<usize, RowTable>,
    proofs: Vec<ProofTable>,
    registers: Vec<Option<Value>>,
    stats: VerificationStats,
    current_bound: u64,
    memo_enabled: bool,
}
impl VerifiedRows {
    fn table<'a>(&'a mut self, g: &Graph, t: usize) -> &'a mut RowTable {
        let table = self.tables.entry(t).or_default();
        if table.generation != g.query_versions[t] || table.union_version != g.stats.unions {
            table.generation = g.query_versions[t];
            table.union_version = g.stats.unions;
            table.rows.clear();
            table.keys.clear();
        }
        table
    }
    fn witness(&mut self, g: &Graph, t: usize, w: Dependency) -> Result<Option<Row>> {
        if self.mode < 3 {
            return g.row(w);
        }
        if let Some(found) = self.table(g, t).rows.get(&w).cloned() {
            self.stats.source_hits += 1;
            return Ok(found);
        }
        self.stats.source_reads += 1;
        let row = g.row(w)?;
        let table = self.table(g, t);
        table.rows.insert(w, row.clone());
        let size = table.rows.len();
        self.stats.peak_source_rows_per_table = self.stats.peak_source_rows_per_table.max(size);
        Ok(row)
    }
    fn point(
        &mut self,
        g: &Graph,
        t: usize,
        key: smallvec::SmallVec<[Value; 3]>,
    ) -> Result<Option<Row>> {
        if self.mode < 3 {
            return g.lookup(t, &key);
        }
        if let Some(found) = self.table(g, t).keys.get(&key).cloned() {
            self.stats.point_hits += 1;
            return Ok(found);
        }
        self.stats.point_reads += 1;
        let row = g.lookup(t, &key)?;
        let table = self.table(g, t);
        table.keys.insert(key, row.clone());
        let size = table.keys.len();
        self.stats.peak_points_per_table = self.stats.peak_points_per_table.max(size);
        Ok(row)
    }
    fn frontier(&mut self, g: &Graph, t: usize) -> u64 {
        if let Some(&(v, e)) = self.frontiers.get(&t)
            && v == g.query_versions[t]
        {
            return e;
        }
        self.stats.fresh_table_rebuild += 1;
        let greatest = g
            .witnesses(t)
            .into_iter()
            .filter_map(|w| g.visible_epoch(w))
            .max()
            .unwrap_or(0);
        self.frontiers.insert(t, (g.query_versions[t], greatest));
        greatest
    }
    fn begin(&mut self, g: &Graph, r: &Rule, p: &Plan, rid: usize) {
        if self.mode == 0 {
            return;
        }
        self.current_bound = if self.mode >= 2 {
            p.order
                .iter()
                .filter_map(|i| match r.query[*i].call {
                    Call::Table(t) => Some(self.frontier(g, t)),
                    _ => None,
                })
                .max()
                .unwrap_or(0)
        } else {
            u64::MAX
        };
        self.memo_enabled = self.mode >= 4
            && r.query.iter().all(|atom| match &atom.call {
                Call::Primitive(op, _) => matches!(
                    op.as_str(),
                    "+" | "-"
                        | "*"
                        | "/"
                        | "%"
                        | ">"
                        | "<"
                        | ">="
                        | "<="
                        | "!="
                        | "eq-id-!="
                        | "min"
                        | "max"
                ),
                _ => true,
            });
        if self.memo_enabled {
            self.proofs
                .resize_with(self.proofs.len().max(rid + 1), ProofTable::default);
            let proof = &mut self.proofs[rid];
            let stamp = r.query.iter().filter_map(|atom| match atom.call {
                Call::Table(t) => Some(g.query_versions[t]),
                _ => None,
            });
            if proof.union_version != g.stats.unions
                || !stamp.clone().eq(proof.table_versions.iter().copied())
            {
                proof.known.clear();
                proof.table_versions.clear();
                proof.table_versions.extend(stamp);
                proof.union_version = g.stats.unions;
                self.stats.cache_resets += 1;
            }
        }
        let n = r
            .query
            .iter()
            .flat_map(|a| &a.args)
            .filter_map(|a| match a {
                Arg::Slot(i) => Some(i + 1),
                _ => None,
            })
            .max()
            .unwrap_or(0);
        if self.registers.len() < n {
            self.registers.resize(n, None);
        }
    }

    fn check(
        &mut self,
        g: &Graph,
        r: &Rule,
        p: &Plan,
        tok: &Token,
        wm: u64,
        work: &mut [u64; 8],
    ) -> Result<Option<Instance>> {
        if r.seminaive && tok.version.max(self.current_bound) < wm {
            self.stats.pruned_by_suffix += 1;
            return Ok(None);
        }
        if self.memo_enabled {
            if let Some((version, previous, entry)) = self.proofs[tok.rid].known.get(&tok.w)
                && *version == tok.version
                && wm >= *previous
            {
                if let Some((values, known, epoch)) = entry {
                    if !r.seminaive || *epoch >= wm {
                        self.stats.positive_hits += 1;
                        return Ok(Some(Instance::matched(
                            values.clone(),
                            known.clone(),
                            *epoch,
                        )));
                    }
                    self.stats.displaced_positive += 1;
                    return Ok(None);
                }
                self.stats.negative_hits += 1;
                return Ok(None);
            }
        }
        let mut registers = std::mem::take(&mut self.registers);
        registers.fill(None);
        let result = self.verify(g, r, p, tok, wm, work, registers.as_mut_slice());
        self.registers = registers;
        let output = result?;
        if self.memo_enabled {
            let value = output
                .as_ref()
                .map(|b| (b.values.clone(), b.known.clone(), b.epoch));
            let entries = &mut self.proofs[tok.rid].known;
            entries.insert(tok.w, (tok.version, wm, value));
            self.stats.peak_proofs_per_rule = self.stats.peak_proofs_per_rule.max(entries.len());
        }
        Ok(output)
    }
    fn verify(
        &mut self,
        g: &Graph,
        r: &Rule,
        p: &Plan,
        tok: &Token,
        wm: u64,
        work: &mut [u64; 8],
        reg: &mut [Option<Value>],
    ) -> Result<Option<Instance>> {
        let mut witnesses = vec![None; r.query.len()];
        let mut epoch = 0;
        if let Some(i) = p.pivot {
            let atom = &r.query[i];
            let Call::Table(table) = atom.call else {
                return Err("non-table root".into());
            };
            let w = tok.w.ok_or("missing emitted root")?;
            let Some(row) = self.witness(g, table, w)? else {
                return Ok(None);
            };
            if row.hidden || row.witness != w || row.epoch != tok.version || row.table != table {
                return Ok(None);
            }
            if !atom
                .args
                .iter()
                .zip(row.values.iter())
                .all(|(a, v)| bind_query(a, v, reg, g))
            {
                return Ok(None);
            }
            witnesses[i] = Some(w);
            epoch = row.epoch;
        }
        for &i in &p.order {
            let atom = &r.query[i];
            let (last, keys) = atom.args.split_last().ok_or("empty source atom")?;
            let values = keys
                .iter()
                .map(|a| query_operand(a, reg, g).ok_or_else(|| "unknown input".to_string()))
                .collect::<Result<smallvec::SmallVec<[Value; 3]>>>()?;
            let result = match &atom.call {
                Call::Table(table) => {
                    work[3] += 1;
                    let Some(row) = self.point(g, *table, values)?.filter(|r| !r.hidden) else {
                        return Ok(None);
                    };
                    witnesses[i] = Some(row.witness);
                    epoch = epoch.max(row.epoch);
                    row.values.last().ok_or("empty table tuple")?.clone()
                }
                Call::Primitive(op, ty) => {
                    work[4] += 1;
                    let Some(value) = g.primitive(op, &values, ty)? else {
                        return Ok(None);
                    };
                    value
                }
            };
            if !bind_query(last, &result, reg, g) {
                return Ok(None);
            }
        }
        if r.seminaive && epoch < wm {
            return Ok(None);
        }
        let mut slots = Slots::default();
        for &s in r.inputs.iter() {
            slots.insert(s, reg[s].as_ref().ok_or("unbound verified slot")?.clone());
        }
        Ok(Some(Instance::matched(
            slots,
            QueryFacts::Ports(witnesses),
            epoch,
        )))
    }
}
