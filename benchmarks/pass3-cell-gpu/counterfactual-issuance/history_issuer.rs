// One history-driven binary Cell issuer, optionally authoritative for its rule.
struct HistoryIssuer {
    target: usize,
    tail: Option<HistoryTail>,
    takeover: bool,
    refresh: bool,
    release: Option<[bool; 8]>,
    retired: std::collections::BTreeSet<VersionedPort>,
    suppressed: Vec<(u64, HistoryProposal, bool)>,
    updates: Vec<(u64, usize, i64, usize, u64, u64, u64, u64, u64)>,
    tables: [usize; 2],
    inputs: Vec<Vec<Option<(usize, usize)>>>,
    weight: f32,
    bias: f32,
    banks: [BTreeMap<VersionedPort, (u64, usize, i64)>; 2],
    proposed: std::collections::BTreeSet<[VersionedPort; 2]>,
    pending: Vec<HistoryProposal>,
    seeds: Vec<[u64; 8]>,
    checked: Vec<(u64, HistoryProposal, bool)>,
}

#[derive(Serialize)]
struct HistoryProposal {
    epoch: u64,
    refs: [VersionedPort; 2],
    owners: [(usize, i64); 2],
}

pub fn configure_history_issuer(g: &Graph, spec: &J) -> Result<()> {
    let program = &g.program;
    let target = spec["target"].as_u64().ok_or("missing history target")? as usize;
    let query = &program
        .rules
        .get(target)
        .ok_or("unknown history target")?
        .query;
    let [left, right] = query.as_slice() else {
        return Err("invalid history query".into());
    };
    let (Call::Table(l), Call::Table(r)) = (&left.call, &right.call) else {
        return Err("history query needs two tables".into());
    };
    if program.tables[*l].name != "Get"
        || program.tables[*r].name != "HasArgType"
        || !matches!((left.args.first(),right.args.first()),(Some(Arg::Slot(a)),Some(Arg::Slot(b))) if a==b)
    {
        return Err("unexpected history projection".into());
    }
    let tables = [*l, *r];
    let inputs = program
        .rules
        .iter()
        .map(|rule| {
            rule.query
                .iter()
                .map(|atom| {
                    let Call::Table(t) = atom.call else {
                        return None;
                    };
                    let Some(Arg::Slot(slot)) = atom.args.first() else {
                        return None;
                    };
                    Some((tables.iter().position(|id| *id == t)?, *slot))
                })
                .collect()
        })
        .collect();
    let param = |key: &str| {
        spec[key]
            .as_f64()
            .map(|v| v as f32)
            .filter(|v| v.is_finite())
            .ok_or("invalid history parameter")
    };
    let mut issuer = HistoryIssuer {
        target,
        tail: HistoryTail::compile(program, target, *r, &spec["tail"])?,
        release: serde_json::from_value(spec["release"].clone()).map_err(|e| e.to_string())?,
        retired: Default::default(),
        suppressed: Vec::new(),
        refresh: spec["refresh"].as_bool().unwrap_or(false),
        updates: Vec::new(),
        takeover: spec["takeover"].as_bool().unwrap_or(false),
        tables,
        inputs,
        weight: param("weight")?,
        bias: param("bias")?,
        banks: Default::default(),
        proposed: Default::default(),
        pending: vec![],
        seeds: vec![],
        checked: vec![],
    };
    if spec["initial"].as_bool() == Some(true) {
        for (role, table) in tables.into_iter().enumerate() {
            for dep in g.witnesses(table) {
                if let Some(row) = g.row(dep)?
                    && !row.hidden
                    && row.witness == dep
                    && let (Dependency::Fact(f), Some(Value::Eq(subject))) =
                        (dep, row.values.first())
                {
                    let id = issuer.seeds.len() as u64;
                    let port = [u64::from(f.cell), u64::from(f.op), row.epoch];
                    issuer.observe(0, role, (0, id as i64), port, *subject);
                    issuer
                        .seeds
                        .push([0, 0, id, role as u64, port[0], port[1], port[2], *subject]);
                }
            }
        }
    }
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.history_issuer = Some(issuer)
        }
    });
    Ok(())
}

impl HistoryIssuer {
    fn observe(
        &mut self,
        epoch: u64,
        role: usize,
        owner: (usize, i64),
        port: VersionedPort,
        key: u64,
    ) {
        if self.banks[role]
            .get(&port)
            .is_some_and(|entry| entry.0 == key)
        {
            return;
        }
        for (&other, &(other_key, ord, slot)) in &self.banks[1 - role] {
            let distance = (key ^ other_key).count_ones() as f32;
            if distance * self.weight + self.bias < 0.0 {
                continue;
            }
            let mut refs = [port, other];
            let mut owners = [owner, (ord, slot)];
            if role == 1 {
                refs.swap(0, 1);
                owners.swap(0, 1);
            }
            if self.proposed.insert(refs) {
                self.pending.push(HistoryProposal {
                    epoch,
                    refs,
                    owners,
                });
            }
        }
        self.banks[role].insert(port, (key, owner.0, owner.1));
    }

    fn cite(
        &mut self,
        epoch: u64,
        ordinal: usize,
        serial: u64,
        rule: usize,
        refs: &[Ref],
        slots: &Slots,
    ) {
        if let Some(t) = &mut self.tail {
            t.inputs(rule, refs, slots);
            t.enter(epoch, ordinal, serial, rule, rule == self.target, refs);
        }
        if rule == self.target {
            return;
        }
        for src in refs {
            let Some((role, slot)) = self.inputs[rule][src.atom] else {
                continue;
            };
            if let (Dependency::Fact(f), Some(Value::Eq(key))) = (src.row, slots.get(&slot)) {
                self.observe(
                    epoch,
                    role,
                    (ordinal, !(src.atom as i64)),
                    [u64::from(f.cell), u64::from(f.op), src.version],
                    *key,
                );
            }
        }
    }
}

pub(crate) fn check_history_issuer(
    g: &Graph,
    rid: usize,
    mark: u64,
) -> Result<Option<Vec<[VersionedPort; 2]>>> {
    STATE.with_borrow_mut(|s| {
        let Some(h) = s.as_mut().and_then(|s| s.history_issuer.as_mut()) else {
            return Ok(None);
        };
        if rid != h.target {
            return Ok(None);
        }
        let mut ready = h.takeover.then(Vec::new);
        for p in std::mem::take(&mut h.pending) {
            if p.epoch >= g.epoch {
                h.pending.push(p);
                continue;
            }
            // Decide before verification, using only the owner's lifecycle receipts
            // and the scheduled watermark. Rejections are point-checked for audit.
            let available = p.refs.iter().enumerate().all(|(role, port)| {
                let [cell, op, _] = *port;
                !h.retired.contains(port)
                    && h.banks[role]
                        .range([cell, op, 0]..=[cell, op, u64::MAX])
                        .next_back()
                        .is_some_and(|(k, _)| k == port)
            });
            let flags = 4 * usize::from(available)
                + 2 * usize::from(p.refs[0][2] >= mark)
                + usize::from(p.refs[1][2] >= mark);
            let issue = h.release.is_none_or(|actions| actions[flags]);
            let read = |role: usize| -> Result<Option<Value>> {
                let [cell, op, version] = p.refs[role];
                let dep = Dependency::Fact(crate::graph::FactRef {
                    cell: cell as u32,
                    op: op as u32,
                });
                Ok(g.row(dep)?
                    .filter(|row| {
                        row.witness == dep
                            && row.table == h.tables[role]
                            && row.epoch == version
                            && !row.hidden
                    })
                    .and_then(|row| row.values.first().cloned()))
            };
            let matched = match (read(0)?, read(1)?) {
                (Some(a), Some(b)) => a == b && p.refs[0][2].max(p.refs[1][2]) >= mark,
                _ => false,
            };
            if !issue {
                if matched {
                    return Err("history release suppressed a valid named pair".into());
                }
                h.suppressed.push((g.epoch, p, false));
                continue;
            }
            if matched && let Some(refs) = &mut ready {
                if let Some(t) = &mut h.tail {
                    t.select(g.epoch, p.refs, h.weight, h.bias);
                }
                refs.push(p.refs);
            }
            h.checked.push((g.epoch, p, matched));
        }
        Ok(ready)
    })
}

// Process the ordinary published change set. A change can advance a port's
// version only when the generator already holds its physical identity.
pub(crate) fn history_updates(g: &Graph) -> Result<()> {
    STATE.with_borrow_mut(|s| {
        let Some(h) = s.as_mut().and_then(|s| s.history_issuer.as_mut()) else {
            return Ok(());
        };
        if let Some(tail) = &mut h.tail
            && tail.points.gate.is_some()
        {
            tail.points.publish(g)?;
        }
        if !h.refresh {
            return Ok(());
        }
        for (t, changes) in g.changes.tables() {
            let Some(role) = h.tables.iter().position(|id| *id == t) else {
                continue;
            };
            for &dep in changes.keys() {
                let Dependency::Fact(f) = dep else { continue };
                let cell = u64::from(f.cell);
                let op = u64::from(f.op);
                let Some((&old, &(_, owner, slot))) = h.banks[role]
                    .range([cell, op, 0]..=[cell, op, u64::MAX])
                    .next_back()
                else {
                    continue;
                };
                let row = g.row(dep)?;
                let Some(row) = row.filter(|r| !r.hidden && r.witness == dep && r.table == t)
                else {
                    h.retired.insert(old);
                    continue;
                };
                if row.epoch <= old[2] {
                    continue;
                }
                if let Some(Value::Eq(key)) = row.values.first() {
                    let port = [cell, op, row.epoch];
                    h.observe(g.epoch, role, (owner, slot), port, *key);
                    h.updates.push((
                        g.epoch, owner, slot, role, cell, op, row.epoch, *key, old[2],
                    ));
                }
            }
        }
        Ok(())
    })
}
