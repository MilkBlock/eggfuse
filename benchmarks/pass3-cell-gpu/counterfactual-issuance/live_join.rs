// Four-role decoder for BodyContainsExpr, DoWhile, Single and is-inv-Expr.
// The compiled history projection retains real witnesses for the determined reads.
struct JoinPort {
    fields: Vec<Value>,
    version: u64,
    owner: (usize, i64),
    arrival: u64,
}
struct LiveJoin {
    target: usize,
    tables: [usize; 4],
    sources: Vec<Vec<Option<(usize, Vec<Arg>)>>>,
    rows: [BTreeMap<Dependency, JoinPort>; 4],
    first: [f32; 3],
    pair: [f32; 4],
    corrupt: bool,
    counts: [u64; 4],
}

pub fn configure_live_join(program: &Program, spec: &J) -> Result<()> {
    let target = spec["rule"].as_u64().ok_or("missing join target")? as usize;
    let r = program.rules.get(target).ok_or("unknown join target")?;
    let layout: &[(&str, &[usize])] = &[
        ("BodyContainsExpr", &[0, 1, 2]),
        ("DoWhile", &[3, 0, 4]),
        ("Single", &[5, 1]),
        ("is-inv-Expr", &[0, 5, 6]),
    ];
    if !r.seminaive || r.query.len() != layout.len() {
        return Err("unexpected join shape".into());
    }
    let mut tables = [0; 4];
    for (i, (q, (name, cols))) in r.query.iter().zip(layout).enumerate() {
        let Call::Table(t) = q.call else {
            return Err("join expects a table".into());
        };
        if program.tables[t].name != *name
            || q.args.len() != cols.len()
            || !q
                .args
                .iter()
                .zip(*cols)
                .all(|(arg, col)| matches!(arg,Arg::Slot(s) if s==col))
        {
            return Err("join template interface changed".into());
        }
        tables[i] = t;
    }
    let sources = program
        .rules
        .iter()
        .map(|rule| {
            rule.query
                .iter()
                .map(|q| {
                    let Call::Table(t) = q.call else { return None };
                    Some((tables.iter().position(|&k| k == t)?, q.args.clone()))
                })
                .collect()
        })
        .collect();
    let join = LiveJoin {
        target,
        tables,
        sources,
        rows: Default::default(),
        first: serde_json::from_value(spec["first"].clone()).map_err(|e| e.to_string())?,
        pair: serde_json::from_value(spec["pair"].clone()).map_err(|e| e.to_string())?,
        corrupt: spec["corrupt"].as_bool() == Some(true),
        counts: [0; 4],
    };
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.live_join = Some(join)
        }
    });
    Ok(())
}

impl LiveJoin {
    fn observe(
        &mut self,
        role: usize,
        dep: Dependency,
        version: u64,
        arrival: u64,
        owner: (usize, i64),
        fields: Vec<Value>,
    ) {
        if self.rows[role].get(&dep).is_some_and(|old| {
            old.version > version || (old.version == version && old.fields == fields)
        }) {
            return;
        }
        self.rows[role].insert(
            dep,
            JoinPort {
                fields,
                version,
                owner,
                arrival,
            },
        );
    }
    fn cite(&mut self, rid: usize, epoch: u64, owner: usize, refs: &[Ref], slots: &Slots) {
        if rid == self.target {
            return;
        }
        for r in refs {
            if let Some((role, args)) = &self.sources[rid][r.atom] {
                let fields = args
                    .iter()
                    .map(|a| match a {
                        Arg::Slot(s) => slots.get(s).cloned(),
                        Arg::Literal(v) => Some(v.clone()),
                    })
                    .collect::<Option<Vec<_>>>();
                if let Some(fields) = fields {
                    self.observe(
                        *role,
                        r.row,
                        r.version,
                        epoch,
                        (owner, !(r.atom as i64)),
                        fields,
                    )
                }
            }
        }
    }
    fn returned(
        &mut self,
        rid: usize,
        t: usize,
        dep: Dependency,
        v: u64,
        ep: u64,
        owner: (usize, i64),
        key: &[Value],
        result: &Value,
    ) {
        if rid == self.target {
            return;
        }
        if let Some(role) = self.tables.iter().position(|&x| x == t) {
            let mut fields = key.to_vec();
            fields.push(result.clone());
            self.observe(role, dep, v, ep, owner, fields);
        }
    }
    fn publish(&mut self, g: &Graph) -> Result<()> {
        for (t, changes) in g.changes.tables() {
            let Some(role) = self.tables.iter().position(|&v| v == t) else {
                continue;
            };
            for &dep in changes.keys() {
                let Some(old) = self.rows[role].get(&dep) else {
                    continue;
                };
                if let Some(v) = g.visible_epoch(dep) {
                    if v <= old.version {
                        continue;
                    }
                    if let Some(row) = g
                        .row(dep)?
                        .filter(|r| r.table == t && r.witness == dep && !r.hidden)
                    {
                        self.observe(
                            role,
                            dep,
                            row.epoch,
                            g.epoch,
                            old.owner,
                            row.values.to_vec(),
                        );
                        continue;
                    }
                }
                self.rows[role].remove(&dep);
            }
        }
        Ok(())
    }
    fn release(&mut self, ep: u64, mark: u64) -> Vec<[ChainReference; 4]> {
        self.counts[0] += 1;
        let visible = |role: usize| self.rows[role].iter().filter(move |(_, p)| p.arrival < ep);
        let mut by_expr = BTreeMap::<_, Vec<_>>::new();
        for (a, p) in visible(0) {
            by_expr
                .entry(&p.fields[1])
                .or_default()
                .push((&p.fields[0], (*a, p.version, p.owner)));
        }
        let mut paths = BTreeMap::<_, Vec<_>>::new();
        for (c, p) in visible(2) {
            for &(body, a) in by_expr.get(&p.fields[1]).into_iter().flatten() {
                paths
                    .entry((body, &p.fields[0]))
                    .or_default()
                    .push((a, (*c, p.version, p.owner)));
            }
        }
        let loops: Vec<_> = visible(1).collect();
        let new_loop = loops.iter().any(|(_, p)| p.version >= mark);
        let mut output = Vec::new();
        let mut first_scores = 0;
        let mut pair_scores = 0;
        for (d, p) in visible(3) {
            first_scores += 1;
            let path = paths.get(&(&p.fields[0], &p.fields[1]));
            let best = path.and_then(|v| v.iter().max_by_key(|(a, c)| a.1.max(c.1)));
            let fresh = best.is_some_and(|(a, c)| a.1.max(c.1) >= mark) || p.version >= mark;
            let bit = |v: bool| f32::from(u8::from(v));
            let [w0, w1, bias] = self.first;
            if w0 * bit(best.is_some()) + w1 * bit(fresh || new_loop) + bias <= 0. {
                continue;
            }
            for &(b, q) in &loops {
                pair_scores += 1;
                let [w0, w1, w2, bias] = self.pair;
                if w0 * bit(q.fields[1] == p.fields[0])
                    + w1 * bit(best.is_some())
                    + w2 * bit(fresh || q.version >= mark)
                    + bias
                    > 0.
                {
                    if let Some(&(a, c)) = best {
                        output.push([a, (*b, q.version, q.owner), c, (*d, p.version, p.owner)]);
                    }
                }
            }
        }
        self.counts[1] += first_scores;
        self.counts[2] += pair_scores;
        self.counts[3] += output.len() as u64;
        output
    }
}
pub(crate) fn takes_join(rid: usize) -> bool {
    STATE.with_borrow(|s| {
        s.as_ref()
            .and_then(|s| s.live_join.as_ref())
            .is_some_and(|j| j.target == rid)
    })
}
pub(crate) fn live_join_packets(
    rid: usize,
    ep: u64,
    mark: u64,
) -> Result<Vec<[ChainReference; 4]>> {
    STATE.with_borrow_mut(|s| {
        let j = s
            .as_mut()
            .and_then(|s| s.live_join.as_mut())
            .filter(|j| j.target == rid)
            .ok_or("unknown join")?;
        let mut out = j.release(ep, mark);
        for packet in &out {
            for (role, &(dep, version, owner)) in packet.iter().enumerate() {
                if !j.rows[role]
                    .get(&dep)
                    .is_some_and(|p| p.owner == owner && p.version == version)
                {
                    return Err("invalid join owner".into());
                }
            }
        }
        if j.corrupt {
            for packet in &mut out {
                packet[2].1 = packet[2].1.wrapping_add(1);
            }
        }
        Ok(out)
    })
}
