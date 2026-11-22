// Static, one-return wires. Every remaining query key must be determined by
// the covered pivot; the receiver executes the original program on its Run.
#[derive(Default)]
struct PointClaims {
    retained: bool,
    gate: Option<[bool; 8]>,
    suffixes: BTreeMap<usize, usize>,
    epochs: BTreeMap<usize, BTreeMap<u64, u64>>,
    initial_epoch: u64,
    unions: u64,
    generations: BTreeMap<usize, u64>,
    rekeyed: usize,
    delta_unions: bool,
    union_probes: usize,
    skipped: BTreeMap<usize, usize>,
    pivots: BTreeMap<usize, usize>,
    pending: BTreeMap<usize, BTreeMap<VersionedPort, (usize, u64, Option<u64>)>>,
    attempts: BTreeMap<usize, usize>,
    children: Vec<(u64, usize)>,
    misses: Vec<(usize, u64, VersionedPort, usize)>,
}

fn configure_point_claims(g: &Graph, spec: &J) -> Result<()> {
    if spec.is_null() {
        return Ok(());
    }
    let program = &g.program;
    let consumers: Vec<(usize, usize)> =
        serde_json::from_value(spec["consumers"].clone()).map_err(|e| e.to_string())?;
    let mut by_table: BTreeMap<usize, Vec<usize>> = Default::default();
    let mut claims = PointClaims {
        initial_epoch: g.epoch,
        unions: g.stats.unions,
        delta_unions: spec["delta_unions"] == true,
        retained: spec["retained"] == true,
        gate: serde_json::from_value(spec["gate"].clone()).map_err(|e| e.to_string())?,
        ..Default::default()
    };
    if claims.gate.is_some_and(|a| !a[5] || !a[6] || !a[7]) {
        return Err("fresh operand must reach the point receiver".into());
    }
    for (rid, pivot) in consumers {
        let r = program.rules.get(rid).ok_or("invalid point consumer")?;
        if !r.seminaive || r.query.len() != 2 || pivot > 1 {
            return Err("invalid point plan".into());
        }
        let source = &r.query[pivot];
        let suffix = &r.query[1 - pivot];
        let (Call::Table(src), Call::Table(other)) = (&source.call, &suffix.call) else {
            return Err("expected two table atoms".into());
        };
        let (_, keys) = suffix.args.split_last().ok_or("missing point result")?;
        if !program.tables[*src].constructor || keys.iter().any(|arg|matches!(arg,Arg::Slot(i) if !source.args.iter().any(|v|matches!(v,Arg::Slot(j) if j==i)))) {
            return Err("independent point suffix".into())
        }
        if claims.gate.is_some() {
            if keys.len() != 1
                || !matches!((source.args.first(),keys.first()),(Some(Arg::Slot(a)),Some(Arg::Slot(b))) if a==b)
            {
                return Err(
                    "history gate requires the first returned field as its sole key".into(),
                );
            }
            claims.generations.insert(*other, g.query_versions[*other]);
            claims.suffixes.insert(rid, *other);
            claims.epochs.entry(*other).or_default();
        }
        if claims.pivots.insert(rid, pivot).is_some() {
            return Err("duplicate point pivot".into());
        }
        by_table.entry(*src).or_default().push(rid);
    }
    STATE.with_borrow_mut(|s| -> Result<()> {
        let s = s.as_mut().ok_or("missing history context")?;
        for (rid, r) in program.rules.iter().enumerate() {
            if r.query.is_empty() {
                continue;
            }
            let mut wiring = BTreeMap::new();
            for (op, ins) in program.templates[r.template].ops.iter().enumerate() {
                if let crate::program::Op::Let(_, Call::Table(t), _) = ins
                    && let Some(uses) = by_table.get(t)
                {
                    wiring.insert(op, uses.clone());
                }
            }
            if !wiring.is_empty() {
                Rc::make_mut(&mut s.layout[rid]).point_wires = wiring;
            }
        }
        let tail = s
            .history_issuer
            .as_mut()
            .and_then(|h| h.tail.as_mut())
            .ok_or("missing root program")?;
        if claims.pivots.contains_key(&tail.rule) {
            return Err("overlapping successor ownership".into());
        }
        tail.points = claims;
        Ok(())
    })
}

impl PointClaims {
    fn publish(&mut self, g: &Graph) -> Result<()> {
        if self.unions != g.stats.unions {
            // Two formerly distinct keys can now name the same mutable row.
            // Preserve the newest observed version over both histories.
            for keys in self.epochs.values_mut() {
                self.rekeyed += keys.len();
                for (key, epoch) in std::mem::take(keys) {
                    let Value::Eq(key) = crate::value::canon(&Value::Eq(key), &g.parents) else {
                        unreachable!()
                    };
                    let entry = keys.entry(key).or_default();
                    *entry = (*entry).max(epoch);
                }
            }
            self.unions = g.stats.unions;
        }
        for (table, changes) in g.changes.tables() {
            let Some(keys) = self.epochs.get_mut(&table) else {
                continue;
            };
            for &dep in changes.keys() {
                if let Some(row) = g.row(dep)?
                    && row.table == table
                    && !row.hidden
                    && let Some(Value::Eq(key)) = row.values.first()
                {
                    let Value::Eq(key) = crate::value::canon(&Value::Eq(*key), &g.parents) else {
                        unreachable!()
                    };
                    keys.entry(key)
                        .and_modify(|v| *v = (*v).max(row.epoch))
                        .or_insert(row.epoch);
                }
            }
            self.generations.insert(table, g.query_versions[table]);
        }
        Ok(())
    }

    fn drain(
        &mut self,
        g: &Graph,
        rid: usize,
        mark: u64,
    ) -> Vec<(Dependency, u64, usize, usize, usize)> {
        let Some(pending) = self.pending.get_mut(&rid) else {
            return vec![];
        };
        let pivot = self.pivots[&rid];
        let mut claims = Vec::new();
        let mut skipped = 0;
        pending.retain(|&[cell, op, version], &mut (owner, birth, key)| {
            if birth >= g.epoch {
                return true;
            }
            let d = Dependency::Fact(crate::graph::FactRef {
                cell: cell as u32,
                op: op as u32,
            });
            if g.visible_epoch(d) != Some(version) {
                return false;
            }
            if let Some(actions) = self.gate
                && let Some(key) = key
            {
                let table = self.suffixes[&rid];
                let Value::Eq(key) = crate::value::canon(&Value::Eq(key), &g.parents) else {
                    unreachable!()
                };
                let e = self.epochs[&table]
                    .get(&key)
                    .copied()
                    .unwrap_or(0)
                    .max(self.initial_epoch);
                if self.unions == g.stats.unions
                    && self.generations[&table] == g.query_versions[table]
                    && !actions[4 + 2 * usize::from(version >= mark) + usize::from(e >= mark)]
                {
                    skipped += 1;
                    return self.retained;
                }
            }
            claims.push((d, version, owner, 1, pivot));
            self.retained
        });
        *self.skipped.entry(rid).or_default() += skipped;
        *self.attempts.entry(rid).or_default() += claims.len();
        claims
    }
}

// A class link only changes receipts keyed by the displaced representative.
// The graph calls this once immediately before installing each actual link.
pub(crate) fn point_claim_union(hi: u64, lo: u64) {
    STATE.with_borrow_mut(|s| {
        let Some(tail) = s
            .as_mut()
            .and_then(|s| s.history_issuer.as_mut())
            .and_then(|h| h.tail.as_mut())
        else {
            return;
        };
        let points = &mut tail.points;
        if !points.delta_unions || points.gate.is_none() {
            return;
        }
        points.unions += 1;
        for keys in points.epochs.values_mut() {
            points.union_probes += 1;
            if let Some(epoch) = keys.remove(&hi) {
                let e = keys.entry(lo).or_default();
                *e = (*e).max(epoch);
                points.rekeyed += 1;
            }
        }
    });
}
