use std::collections::BTreeSet;

struct ChainPort {
    values: [Option<Value>; 2],
    owner: (usize, i64),
    version: u64,
    birth: u64,
}

// Logical owner and exported slot accompany the physical witness through issue.
type ChainReference = (Dependency, u64, (usize, i64));
type ChainRefs = [ChainReference; 3];

struct LiveChain {
    target: usize,
    tables: [usize; 3],
    atoms: [usize; 3],
    arities: [usize; 3],
    columns: [[Option<usize>; 2]; 3],
    sources: Vec<Vec<Option<(usize, Vec<Arg>)>>>,
    rows: [BTreeMap<Dependency, ChainPort>; 3],
    index: [[BTreeMap<Value, BTreeSet<Dependency>>; 2]; 3],
    changed: BTreeSet<(usize, Dependency)>,
    withhold: bool,
    corrupt_owner: bool,
    calls: u64,
    probes: u64,
    publications: u64,
    payload_reads: u64,
    issued: u64,
}

pub fn configure_live_chain(program: &Program, spec: &J) -> Result<()> {
    let target = spec["rule"].as_u64().ok_or("missing chain target")? as usize;
    let rule = program.rules.get(target).ok_or("unknown chain target")?;
    let wires: [[usize; 4]; 2] =
        serde_json::from_value(spec["wires"].clone()).map_err(|e| e.to_string())?;
    let [[left, m, i, j], [right, n, k, l]] = wires;
    let atoms = [left, m, right];
    if m != n
        || atoms.iter().copied().collect::<BTreeSet<_>>() != BTreeSet::from([0, 1, 2])
        || rule.query.len() != 3
        || !rule.seminaive
    {
        return Err("expected a seminaive three-atom chain".into());
    }
    let columns = [[Some(i), None], [Some(j), Some(l)], [None, Some(k)]];
    let mut tables = [0; 3];
    let mut shared = BTreeMap::<usize, Vec<(usize, usize)>>::new();
    for (role, &atom) in atoms.iter().enumerate() {
        let q = &rule.query[atom];
        let Call::Table(t) = q.call else {
            return Err("chain needs named tables".into());
        };
        tables[role] = t;
        for (c, arg) in q.args.iter().enumerate() {
            let Arg::Slot(s) = arg else {
                return Err("unsupported chain argument".into());
            };
            shared.entry(*s).or_default().push((role, c));
        }
    }
    let actual: BTreeSet<_> = shared.into_values().filter(|v| v.len() > 1).collect();
    if actual != BTreeSet::from([vec![(0, i), (1, j)], vec![(1, l), (2, k)]])
        || tables.iter().collect::<BTreeSet<_>>().len() != 3
    {
        return Err("learned projections do not cover the chain equalities".into());
    }
    let sources = program
        .rules
        .iter()
        .map(|r| {
            r.query
                .iter()
                .map(|a| {
                    let Call::Table(t) = a.call else { return None };
                    Some((tables.iter().position(|x| *x == t)?, a.args.clone()))
                })
                .collect()
        })
        .collect();
    let arities = atoms.map(|i| rule.query[i].args.len());
    let chain = LiveChain {
        target,
        tables,
        atoms,
        arities,
        columns,
        sources,
        rows: Default::default(),
        index: Default::default(),
        changed: Default::default(),
        withhold: spec["withhold"].as_bool() == Some(true),
        corrupt_owner: spec["corrupt_owner"].as_bool() == Some(true),
        calls: 0,
        probes: 0,
        publications: 0,
        payload_reads: 0,
        issued: 0,
    };
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.live_chain = Some(chain)
        }
    });
    Ok(())
}

impl LiveChain {
    fn remove(&mut self, role: usize, dep: Dependency) {
        if let Some(old) = self.rows[role].remove(&dep) {
            for (side, value) in old.values.into_iter().enumerate() {
                if let Some(v) = value
                    && let Some(set) = self.index[role][side].get_mut(&v)
                {
                    set.remove(&dep);
                    if set.is_empty() {
                        self.index[role][side].remove(&v);
                    }
                }
            }
        }
    }
    fn observe(
        &mut self,
        role: usize,
        dep: Dependency,
        version: u64,
        birth: u64,
        owner: (usize, i64),
        values: [Option<Value>; 2],
    ) {
        if self.rows[role].get(&dep).is_some_and(|old| {
            old.version > version || old.version == version && old.values == values
        }) {
            return;
        }
        self.remove(role, dep);
        for (side, value) in values.iter().enumerate() {
            if let Some(v) = value {
                self.index[role][side]
                    .entry(v.clone())
                    .or_default()
                    .insert(dep);
            }
        }
        self.rows[role].insert(
            dep,
            ChainPort {
                values,
                owner,
                version,
                birth,
            },
        );
        self.changed.insert((role, dep));
    }
    fn cite(&mut self, rid: usize, epoch: u64, owner: usize, refs: &[Ref], slots: &Slots) {
        if rid == self.target {
            return;
        }
        for r in refs {
            if let Some((role, args)) = &self.sources[rid][r.atom] {
                let values = self.columns[*role].map(|col| match &args[col?] {
                    Arg::Literal(v) => Some(v.clone()),
                    Arg::Slot(s) => slots.get(s).cloned(),
                });
                self.observe(
                    *role,
                    r.row,
                    r.version,
                    epoch,
                    (owner, !(r.atom as i64)),
                    values,
                );
            }
        }
    }
    fn returned(
        &mut self,
        rid: usize,
        t: usize,
        dep: Dependency,
        version: u64,
        epoch: u64,
        owner: (usize, i64),
        fields: &[Value],
        result: &Value,
    ) {
        if rid == self.target {
            return;
        }
        if let Some(role) = self.tables.iter().position(|id| *id == t) {
            let values = self.columns[role].map(|c| {
                let i = c?;
                if i + 1 == self.arities[role] {
                    Some(result.clone())
                } else {
                    fields.get(i).cloned()
                }
            });
            self.observe(role, dep, version, epoch, owner, values);
        }
    }
    fn publish(&mut self, g: &Graph) -> Result<()> {
        for (t, changes) in g.changes.tables() {
            let Some(role) = self.tables.iter().position(|id| *id == t) else {
                continue;
            };
            for &dep in changes.keys() {
                let Some(old) = self.rows[role].get(&dep) else {
                    continue;
                };
                self.publications += 1;
                match g.visible_epoch(dep) {
                    None => {
                        self.remove(role, dep);
                        continue;
                    }
                    Some(v) if v <= old.version => continue,
                    _ => {}
                }
                self.payload_reads += 1;
                if let Some(row) = g
                    .row(dep)?
                    .filter(|r| r.table == t && r.witness == dep && !r.hidden)
                {
                    if row.epoch > old.version {
                        let values = self.columns[role].map(|c| row.values.get(c?).cloned());
                        self.observe(role, dep, row.epoch, g.epoch, old.owner, values);
                    }
                } else {
                    self.remove(role, dep);
                }
            }
        }
        Ok(())
    }
    fn release(&mut self, epoch: u64, mark: u64) -> Vec<ChainRefs> {
        self.calls += 1;
        let mut candidates = BTreeSet::new();
        for (role, dep) in std::mem::take(&mut self.changed) {
            let Some(port) = self.rows[role].get(&dep) else {
                continue;
            };
            if port.birth >= epoch {
                self.changed.insert((role, dep));
                continue;
            }
            let bridges = if role == 1 {
                None
            } else {
                let side = usize::from(role == 2);
                let Some(key) = &port.values[side] else {
                    continue;
                };
                self.probes += 1;
                self.index[1][side].get(key)
            };
            for &bridge in (role == 1)
                .then_some(&dep)
                .into_iter()
                .chain(bridges.into_iter().flatten())
            {
                let m = &self.rows[1][&bridge];
                let [Some(a), Some(b)] = &m.values else {
                    continue;
                };
                self.probes += 2;
                let (Some(left), Some(right)) = (self.index[0][0].get(a), self.index[2][1].get(b))
                else {
                    continue;
                };
                use std::ops::Bound::{Included, Unbounded};
                let range = |fixed| {
                    if fixed {
                        (Included(dep), Included(dep))
                    } else {
                        (Unbounded, Unbounded)
                    }
                };
                for &x in left.range(range(role == 0)) {
                    for &y in right.range(range(role == 2)) {
                        let deps = [x, bridge, y];
                        if (0..3).any(|r| self.rows[r][&deps[r]].birth >= epoch)
                            || !(0..3).any(|r| self.rows[r][&deps[r]].version >= mark)
                        {
                            continue;
                        }
                        let mut refs = [(dep, 0, (0, 0)); 3];
                        for r in 0..3 {
                            let p = &self.rows[r][&deps[r]];
                            refs[self.atoms[r]] = (deps[r], p.version, p.owner);
                        }
                        candidates.insert(refs);
                    }
                }
            }
        }
        if self.withhold {
            candidates.clear();
        }
        self.issued += candidates.len() as u64;
        candidates.into_iter().collect()
    }
}

pub(crate) fn live_chain_packets(g: &Graph, rid: usize, mark: u64) -> Option<Vec<ChainRefs>> {
    STATE.with_borrow_mut(|s| {
        s.as_mut()?
            .live_chain
            .as_mut()
            .filter(|c| c.target == rid)
            .map(|c| c.release(g.epoch, mark))
    })
}

// Resolve the signed port exactly once before sealing the ordinary row page.
pub(crate) fn resolve_chain(rid: usize, packet: &ChainRefs) -> Result<()> {
    STATE.with_borrow(|s| {
        let chain = s
            .as_ref()
            .and_then(|s| s.live_chain.as_ref())
            .filter(|c| c.target == rid)
            .ok_or("missing live chain owner store")?;
        for (role, &atom) in chain.atoms.iter().enumerate() {
            let (dep, version, mut owner) = packet[atom];
            if chain.corrupt_owner && role == 0 {
                owner.1 = !owner.1;
            }
            if !chain.rows[role]
                .get(&dep)
                .is_some_and(|port| port.owner == owner && port.version == version)
            {
                return Err("invalid live chain owner slot or revision".into());
            }
        }
        Ok(())
    })
}

pub fn watch_chain(rid: usize) {
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.chain_page_count = Some((rid, 0));
        }
    });
}
pub(crate) fn takes_chain(rid: usize) -> bool {
    STATE.with_borrow(|s| {
        s.as_ref()
            .and_then(|s| s.live_chain.as_ref())
            .is_some_and(|c| c.target == rid)
    })
}

pub fn watch_paid_ranges() {
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.paid_ranges = Some(Vec::new());
        }
    });
}

fn record_paid(
    ranges: &mut Option<Vec<(u64, usize, usize)>>,
    first: u64,
    count: usize,
    rule: usize,
) {
    let Some(ranges) = ranges else { return };
    if count == 0 {
        return;
    }
    if let Some((start, n, rid)) = ranges.last_mut()
        && *rid == rule
        && *start + *n as u64 == first
    {
        *n += count;
    } else {
        ranges.push((first, count, rule));
    }
}

pub fn enable_prefix_ports() {
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.prefix_ports = true
        }
    });
}
pub(crate) fn prefix_port(
    table: usize,
    key: &[Value],
    value: &Value,
    op: usize,
    dep: Dependency,
    version: u64,
    epoch: u64,
    reused: bool,
) {
    if !STATE.with_borrow(|s| s.as_ref().is_some_and(|s| s.prefix_ports)) {
        return;
    }
    history_return(table, key, value, op, dep, version, epoch);
    // Keep the observed return for proof replay without altering pair selection.
    STATE.with_borrow_mut(|s| {
        let Some(s) = s else { return };
        if let Some((owner, _, _, rid, _)) = s.active
            && let Some((rules, rows)) = &mut s.pair_trace
            && rules.contains(&rid)
            && let Dependency::Fact(f) = dep
        {
            rows.push([
                owner as u64,
                rid as u64,
                op as u64,
                f.cell as u64,
                f.op as u64,
                version,
                reused as u64,
            ]);
        }
    });
}
