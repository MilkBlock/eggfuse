// The certificate can answer only "no binding at this watermark". There is no
// positive binding cache and a rejected token never alters the learned stream.
#[derive(Clone)]
struct SourceSupport {
    generation: u64,
    row: Row,
}
struct MissingPoint {
    table: usize,
    generation: u64,
    key: Vec<Value>,
}
struct ResultCertificate {
    rule: usize,
    anchor: Dependency,
    anchor_epoch: u64,
    run_epoch: u64,
    unions: u64,
    supports: smallvec::SmallVec<[SourceSupport; 3]>,
    missing: Option<MissingPoint>,
    // A proved complete binding is inapplicable only above its binding epoch.
    cutoff: Option<u64>,
}
impl ResultCertificate {
    fn supports(g: &Graph, t: usize, row: &Row) -> bool {
        row.table == t
            && row.values.len() <= 8
            && row
                .values
                .iter()
                .all(|v| matches!(v, Value::Eq(_) | Value::Int(_)))
            && g.query_versions.get(t).is_some()
    }
    fn push(e: &mut Option<Self>, g: &Graph, t: usize, row: &Row) {
        let Some(p) = e else { return };
        if p.supports.len() >= 6 || !Self::supports(g, t, row) {
            *e = None;
            return;
        }
        p.supports.push(SourceSupport {
            generation: g.query_versions[t],
            row: row.clone(),
        });
    }
}
#[derive(Default, Serialize)]
struct CertificateCounts {
    probes: u64,
    physical_checks: [u64; 5],
    physical_audits: u64,
    delayed: u64,
    exact_entries: u64,
    cross_run_hits: u64,
    hits: u64,
    stale_bindings: u64,
    negative_hits: u64,
    writes: u64,
    evictions: u64,
    peak_entries: usize,
    changed_header: u64,
    changed_table: u64,
    changed_union: u64,
    expiry: u64,
    verified_rows: u64,
    verified_points: u64,
    missing_rechecks: u64,
    audited: u64,
}
#[derive(Default)]
struct ResultCertificates {
    mode: u8,
    held: bool,
    physical: u8,
    audit: bool,
    warm: Vec<Option<(usize, Dependency, u64)>>,
    entries: Vec<Option<Box<ResultCertificate>>>,
    stats: CertificateCounts,
}
impl ResultCertificates {
    fn index(&self, rule: usize, d: Dependency) -> usize {
        use std::hash::{Hash, Hasher};
        let mut h = rustc_hash::FxHasher::default();
        (rule, d).hash(&mut h);
        (h.finish() as usize) & (self.entries.len() - 1)
    }
    fn admit(&mut self, tok: &Token) -> bool {
        if self.warm.is_empty() {
            return true;
        }
        let Some(d) = tok.w else { return false };
        let i = self.index(tok.rid, d);
        let key = (tok.rid, d, tok.version);
        let seen = self.warm[i] == Some(key);
        self.warm[i] = Some(key);
        self.stats.delayed += u64::from(!seen);
        seen
    }
    fn put(&mut self, e: Option<ResultCertificate>, cutoff: Option<u64>) {
        if let Some(mut p) = e {
            let k = self.index(p.rule, p.anchor);
            if let Some(old) = &self.entries[k] {
                self.stats.evictions += u64::from(old.rule != p.rule || old.anchor != p.anchor)
            } else {
                self.stats.peak_entries += 1
            }
            p.cutoff = cutoff;
            self.entries[k] = Some(Box::new(p));
            self.stats.writes += 1;
        }
    }
    fn probe(&mut self, g: &Graph, tok: &Token, wm: u64) -> Result<bool> {
        let Some(d) = tok.w else { return Ok(false) };
        self.stats.probes += 1;
        let k = self.index(tok.rid, d);
        let Some(p) = self.entries[k].as_mut() else {
            return Ok(false);
        };
        if p.rule != tok.rid || p.anchor != d || p.anchor_epoch != tok.version {
            return Ok(false);
        }
        self.stats.exact_entries += 1;
        if p.cutoff.is_some_and(|e| wm <= e) {
            return Ok(false);
        }
        let changed = p.unions != g.stats.unions;
        if changed && self.mode < 3 {
            self.stats.changed_union += 1;
            return Ok(false);
        }
        for (i, s) in p.supports.iter().enumerate() {
            let table = s.row.table;
            if g.query_versions[table] == s.generation && !changed {
                continue;
            }
            if self.mode == 1 {
                self.stats.changed_table += 1;
                return Ok(false);
            }
            if self.physical > 0
                && (i == 0 || !g.program.tables[table].virtual_fact)
                && let Some((equal, kind)) =
                    g.compare_certificate_row(&s.row, self.physical == 2)?
            {
                self.stats.physical_checks[kind] += 1;
                if self.audit {
                    let actual = g.row(s.row.witness)?.is_some_and(|r| {
                        !r.hidden
                            && r.witness == s.row.witness
                            && r.table == table
                            && r.epoch == s.row.epoch
                            && r.values == s.row.values
                    });
                    if actual != equal {
                        return Err(
                            "direct Cell field comparison disagrees with original row".into()
                        );
                    }
                    self.stats.physical_audits += 1;
                }
                if !equal {
                    self.stats.changed_header += 1;
                    return Ok(false);
                }
                continue;
            }
            let now = if i == 0 || !g.program.tables[table].virtual_fact {
                self.stats.verified_rows += 1;
                g.row(s.row.witness)?
            } else {
                self.stats.verified_points += 1;
                g.lookup(table, &s.row.values[..s.row.values.len() - 1])?
            };
            if !now.is_some_and(|r| {
                !r.hidden
                    && r.table == table
                    && r.witness == s.row.witness
                    && r.epoch == s.row.epoch
                    && r.values == s.row.values
            }) {
                self.stats.changed_header += 1;
                return Ok(false);
            }
        }
        if let Some(m) = &p.missing
            && (g.query_versions[m.table] != m.generation || changed)
        {
            if self.mode < 3 {
                self.stats.changed_table += 1;
                return Ok(false);
            }
            self.stats.missing_rechecks += 1;
            if g.lookup(m.table, &m.key)?.is_some_and(|r| !r.hidden) {
                self.stats.expiry += 1;
                return Ok(false);
            }
        }
        self.stats.cross_run_hits += u64::from(p.run_epoch != g.epoch);
        self.stats.hits += 1;
        self.stats.negative_hits += u64::from(p.cutoff.is_none());
        self.stats.stale_bindings += u64::from(p.cutoff.is_some());
        // Every changed positive support and absent full key has just been revalidated.
        for s in &mut p.supports {
            s.generation = g.query_versions[s.row.table];
        }
        if let Some(m) = &mut p.missing {
            m.generation = g.query_versions[m.table];
        }
        p.unions = g.stats.unions;
        Ok(true)
    }
}
