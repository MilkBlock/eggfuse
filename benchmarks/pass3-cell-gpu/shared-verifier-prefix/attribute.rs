// A source table with a complete scalar key has a single checked read result,
// even when two independently proposed consumers use different pivots or guards.
#[derive(Default, serde::Serialize)]
struct AttributeStats {
    admitted_tables: usize,
    compiled_uses: usize,
    calls: u64,
    hits: u64,
    negative_hits: u64,
    different_rule: u64,
    different_pivot_table: u64,
    different_epoch: u64,
    populated: u64,
    stale_generations: u64,
    collisions: u64,
    audit_checks: u64,
    pairs: BTreeMap<usize, BTreeMap<usize, u64>>,
}
#[derive(Clone, PartialEq)]
struct AttributeValue {
    result: Value,
    witness: Dependency,
    epoch: u64,
}
struct AttributeEntry {
    key: Value,
    generation: u64,
    unions: u64,
    writer: usize,
    pivot: usize,
    at: u64,
    output: Option<AttributeValue>,
}
#[derive(Default)]
struct Attributes {
    mode: u64,
    audit: bool,
    operations: Vec<Vec<Option<(usize, usize)>>>,
    banks: Vec<Vec<Option<AttributeEntry>>>,
    stats: AttributeStats,
}
impl Attributes {
    fn compile(&mut self, prog: &Program, plans: &[Option<Plan>], mode: u64, detailed: bool) {
        self.mode = mode;
        self.audit = detailed;
        let mut owners = BTreeMap::<usize, BTreeSet<usize>>::new();
        for (rid, p) in plans.iter().enumerate() {
            let Some(p) = p else { continue };
            if p.pivot.is_none() {
                continue;
            }
            for &i in &p.order {
                let a = &prog.rules[rid].query[i];
                if let Call::Table(t) = a.call
                    && a.args.len() == 2
                {
                    owners.entry(t).or_default().insert(rid);
                }
            }
        }
        self.operations.resize_with(plans.len(), Vec::new);
        self.banks.resize_with(prog.tables.len(), Vec::new);
        self.stats.admitted_tables = owners.values().filter(|r| r.len() > 1).count();
        for (rid, p) in plans.iter().enumerate() {
            let Some(p) = p else { continue };
            let Some(root) = p.pivot else { continue };
            let q = &prog.rules[rid].query;
            let Call::Table(pivot) = q[root].call else {
                continue;
            };
            self.operations[rid].resize(q.len(), None);
            for &ix in &p.order {
                let atom = &q[ix];
                if let Call::Table(t) = atom.call
                    && atom.args.len() == 2
                    && owners[&t].len() > 1
                {
                    self.operations[rid][ix] = Some((t, pivot));
                    self.stats.compiled_uses += 1;
                }
            }
        }
    }
    fn read(g: &Graph, table: usize, key: &Value) -> Result<Option<AttributeValue>> {
        let Some(row) = g
            .lookup(table, std::slice::from_ref(key))?
            .filter(|row| !row.hidden)
        else {
            return Ok(None);
        };
        Ok(Some(AttributeValue {
            result: row.values.last().ok_or("empty unary result")?.clone(),
            witness: row.witness,
            epoch: row.epoch,
        }))
    }
    fn get(
        &mut self,
        g: &Graph,
        table: usize,
        pivot: usize,
        key: Value,
        raw: u64,
        rid: usize,
        work: &mut [u64; 8],
    ) -> Result<Option<AttributeValue>> {
        let bank = &mut self.banks[table];
        if bank.is_empty() {
            bank.resize_with(FAMILY_CAP, || None);
        }
        let pos = ((raw ^ (raw >> 32).wrapping_mul(0x9e3779b9)) as usize) & (FAMILY_CAP - 1);
        let generation = g.query_versions[table];
        let unions = g.stats.unions;
        self.stats.calls += 1;
        if let Some(e) = &bank[pos]
            && e.key == key
            && e.generation == generation
            && e.unions == unions
            && (self.mode != 7 || e.writer != rid)
        {
            if self.audit {
                if Self::read(g, table, &key)? != e.output {
                    return Err("unary family value differs from source".into());
                }
                self.stats.audit_checks += 1;
                *self
                    .stats
                    .pairs
                    .entry(e.writer)
                    .or_default()
                    .entry(rid)
                    .or_default() += 1;
            }
            self.stats.hits += 1;
            self.stats.different_rule += u64::from(e.writer != rid);
            self.stats.different_epoch += u64::from(e.at != g.epoch);
            self.stats.different_pivot_table += u64::from(e.pivot != pivot);
            self.stats.negative_hits += u64::from(e.output.is_none());
            return Ok(e.output.clone());
        }
        work[3] += 1;
        let output = Self::read(g, table, &key)?;
        match &bank[pos] {
            Some(e) if e.key != key => self.stats.collisions += 1,
            Some(e) if e.generation != generation || e.unions != unions => {
                self.stats.stale_generations += 1
            }
            None => self.stats.populated += 1,
            _ => {}
        }
        bank[pos] = Some(AttributeEntry {
            key,
            generation,
            unions,
            writer: rid,
            pivot,
            at: g.epoch,
            output: output.clone(),
        });
        Ok(output)
    }
}
