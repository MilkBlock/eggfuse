// Static, one-return wires. Every remaining query key must be determined by
// the covered pivot; the receiver executes the original program on its Run.
#[derive(Default)]
struct PointClaims {
    static_codes: BTreeMap<usize, usize>,
    batch_gate: bool,
    newest_pivots: BTreeMap<usize, u64>,
    batch_skips: usize,
    avoided_visits: usize,
    retained: bool,
    own_stale: bool,
    stale_omissions: usize,
    gate: Option<[bool; 8]>,
    suffixes: BTreeMap<usize, usize>,
    later_tables: BTreeMap<usize, Vec<(usize, Option<usize>)>>,
    epochs: BTreeMap<usize, BTreeMap<u64, u64>>,
    table_epochs: BTreeMap<usize, u64>,
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
    let mut by_table: BTreeMap<usize, Vec<(usize, Option<usize>)>> = Default::default();
    let mut claims = PointClaims {
        initial_epoch: g.epoch,
        unions: g.stats.unions,
        delta_unions: spec["delta_unions"] == true,
        retained: spec["retained"] == true,
        batch_gate: spec["batch_gate"] == true,
        own_stale: spec["own_stale"] == true,
        gate: serde_json::from_value(spec["gate"].clone()).map_err(|e| e.to_string())?,
        ..Default::default()
    };
    if claims.gate.is_some_and(|a| !a[5] || !a[6] || !a[7]) {
        return Err("fresh operand must reach the point receiver".into());
    }
    for (rid, pivot) in consumers {
        let r = program.rules.get(rid).ok_or("invalid point consumer")?;
        if !r.seminaive || pivot >= r.query.len() {
            return Err("invalid point plan".into());
        }
        let source = &r.query[pivot];
        let Call::Table(src) = &source.call else {
            return Err("expected a constructor pivot".into());
        };
        if !program.tables[*src].constructor {
            return Err("expected a constructor pivot".into());
        }
        let order = crate::single_witness::signed_point_order(r, pivot)
            .ok_or("independent point suffix")?;
        let mut tables = order.iter().filter_map(|&i| {
            let atom = &r.query[i];
            if let Call::Table(t) = atom.call {
                Some((t, atom))
            } else {
                None
            }
        });
        let first = tables.next();
        let field = |arg: Option<&Arg>| match arg {
            Some(Arg::Slot(i)) => source
                .args
                .iter()
                .position(|a| matches!(a,Arg::Slot(j) if i==j)),
            _ => None,
        };
        let projection = field(first.and_then(|(_, atom)| atom.args.split_last()?.1.first()));
        if claims.gate.is_some()
            && let Some((first, _)) = first
        {
            let later: std::collections::BTreeSet<_> = tables
                .map(|(t, atom)| {
                    let column = if spec["project_later"] == true {
                        field(atom.args.split_last().and_then(|(_, key)| key.first()))
                    } else {
                        None
                    };
                    (t, column)
                })
                .collect();
            for table in std::iter::once(&first).chain(later.iter().map(|(t, _)| t)) {
                claims.generations.insert(*table, g.query_versions[*table]);
                claims.epochs.entry(*table).or_default();
            }
            claims.suffixes.insert(rid, first);
            if !later.is_empty() {
                claims.later_tables.insert(rid, later.into_iter().collect());
            }
        }
        if spec["compose_paths"] == true
            && let Some(code) = crate::strict_named::static_point_code(rid)
        {
            claims.static_codes.insert(rid, code);
        }
        if claims.pivots.insert(rid, pivot).is_some() {
            return Err("duplicate point pivot".into());
        }
        by_table.entry(*src).or_default().push((rid, projection));
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
                {
                    let upper = self.table_epochs.entry(table).or_default();
                    *upper = (*upper).max(row.epoch);
                    let Some(Value::Eq(key)) = row.values.first() else {
                        continue;
                    };
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

    fn stale_test<'a>(
        &'a self,
        g: &'a Graph,
        rid: usize,
        mark: u64,
    ) -> Option<impl Fn(Dependency, u64, Option<u64>) -> bool + 'a> {
        let actions = self.gate?;
        let table = self.suffixes.get(&rid);
        if actions[4]
            || self.unions != g.stats.unions
            || table.is_some_and(|t| self.generations[t] != g.query_versions[*t])
        {
            return None;
        }
        let mut hot = Vec::new();
        for &(t, column) in self.later_tables.get(&rid).into_iter().flatten() {
            if self.generations[&t] != g.query_versions[t] {
                return None;
            }
            if self
                .table_epochs
                .get(&t)
                .copied()
                .unwrap_or(0)
                .max(self.initial_epoch)
                >= mark
            {
                hot.push((&self.epochs[&t], column?));
            }
        }
        let keys = table.map(|t| &self.epochs[t]);
        let fallback = table.and_then(|t| self.table_epochs.get(t));
        let initial = self.initial_epoch;
        Some(move |pivot, version, key| {
            if version >= mark {
                return false;
            }
            let upper = match key {
                Some(key) => {
                    let Value::Eq(key) = crate::value::canon(&Value::Eq(key), &g.parents) else {
                        unreachable!()
                    };
                    keys.and_then(|keys| keys.get(&key))
                }
                None => fallback,
            };
            if upper.copied().unwrap_or(0).max(initial) >= mark {
                return false;
            }
            if hot.is_empty() {
                return true;
            }
            // Reuse the versioned pivot for all hot projected keys. Unavailable
            // fields simply require the ordinary receiver.
            let Ok(Some(row)) = g.row(pivot) else {
                return false;
            };
            !row.hidden
                && row.witness == pivot
                && row.epoch == version
                && hot.iter().all(|(epochs, col)| {
                    let Some(Value::Eq(raw)) = row.values.get(*col) else {
                        return false;
                    };
                    let Value::Eq(key) = crate::value::canon(&Value::Eq(*raw), &g.parents) else {
                        unreachable!()
                    };
                    epochs.get(&key).copied().unwrap_or(0).max(initial) < mark
                })
        })
    }

    fn whole_batch_stale(&self, g: &Graph, rid: usize, mark: u64) -> bool {
        if !self.batch_gate
            || !self.retained
            || !self.gate.is_some_and(|a| !a[4])
            || self.unions != g.stats.unions
            || self.initial_epoch >= mark
            || self
                .newest_pivots
                .get(&rid)
                .is_none_or(|&epoch| epoch >= mark)
        {
            return false;
        }
        self.suffixes
            .get(&rid)
            .into_iter()
            .chain(
                self.later_tables
                    .get(&rid)
                    .into_iter()
                    .flatten()
                    .map(|(t, _)| t),
            )
            .all(|t| {
                self.generations[t] == g.query_versions[*t]
                    && self.table_epochs.get(t).copied().unwrap_or(0) < mark
            })
    }

    fn drain(
        &mut self,
        g: &Graph,
        rid: usize,
        mark: u64,
    ) -> Vec<(Dependency, u64, usize, usize, usize)> {
        if let Some(pending) = self.pending.get(&rid)
            && self.whole_batch_stale(g, rid, mark)
        {
            self.batch_skips += 1;
            self.avoided_visits += pending.len();
            return Vec::new();
        }
        let Some(mut pending) = self.pending.remove(&rid) else {
            return vec![];
        };
        let pivot = self.pivots[&rid];
        let mut claims = Vec::new();
        let mut skipped = 0;
        let stale = self.stale_test(g, rid, mark);
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
            if stale.as_ref().is_some_and(|test| test(d, version, key)) {
                skipped += 1;
                return self.retained;
            }
            claims.push((d, version, owner, 1, pivot));
            self.retained
        });
        drop(stale);
        if !pending.is_empty() {
            self.pending.insert(rid, pending);
        }
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

// Called only for a lane that passed all earlier filters and would pay for a
// packet. Its old pivot and the suffix upper bound prove semi-naive rejection.
pub(crate) fn owned_stale_point(
    g: &Graph,
    rid: usize,
    mark: u64,
    row: Dependency,
    version: u64,
) -> Option<usize> {
    STATE.with_borrow_mut(|s| {
        let t = s.as_mut()?.history_issuer.as_mut()?.tail.as_mut()?;
        let points = &mut t.points;
        if !t.own_misses || !points.own_stale || version >= mark {
            return None;
        }
        let Dependency::Fact(f) = row else {
            return None;
        };
        let port = [u64::from(f.cell), u64::from(f.op), version];
        let &(owner, birth, key) = points.pending.get(&rid)?.get(&port)?;
        if birth >= g.epoch
            || !points.stale_test(g, rid, mark)?(row, version, key)
            || g.visible_epoch(row) != Some(version)
        {
            return None;
        }
        points.stale_omissions += 1;
        Some(owner)
    })
}
