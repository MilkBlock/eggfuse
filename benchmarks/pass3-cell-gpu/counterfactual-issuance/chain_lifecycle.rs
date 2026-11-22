// Optional observation of writes and later publications on already named ports.
struct ChainLifecycle {
    allow_set_ports: bool,
    initial: Vec<J>,
    aliases: Vec<[u64; 3]>,
    proofs: BTreeMap<u64, Vec<J>>,
    scheduled: Vec<[u64; 3]>,
    targets: BTreeMap<usize, usize>,
    inputs: Vec<Vec<Option<usize>>>,
    owners: std::collections::HashMap<(usize, Dependency), (usize, i64, u64)>,
    publish_changes: u64,
    publish_reads: u64,
    writes: Vec<J>,
    updates: Vec<J>,
}

pub fn configure_chain_lifecycle(program: &Program, spec: &J, allow_set_ports: bool) -> Result<()> {
    let mut targets = BTreeMap::new();
    for rid in serde_json::from_value::<Vec<usize>>(spec.clone()).map_err(|e| e.to_string())? {
        for atom in program
            .rules
            .get(rid)
            .ok_or("unknown receipt target")?
            .query
            .iter()
        {
            if let Call::Table(t) = atom.call
                && targets.insert(t, rid).is_some_and(|prev| prev != rid)
            {
                return Err("receipt study needs separate target tables".into());
            }
        }
    }
    let inputs = program
        .rules
        .iter()
        .map(|r| {
            r.query
                .iter()
                .map(|atom| match atom.call {
                    Call::Table(t) if targets.contains_key(&t) => Some(t),
                    _ => None,
                })
                .collect()
        })
        .collect();
    let trace = ChainLifecycle {
        allow_set_ports,
        initial: vec![],
        aliases: vec![],
        proofs: Default::default(),
        scheduled: vec![],
        targets,
        inputs,
        owners: Default::default(),
        publish_changes: 0,
        publish_reads: 0,
        writes: vec![],
        updates: vec![],
    };
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.chain_lifecycle = Some(trace);
        }
    });
    Ok(())
}

impl ChainLifecycle {
    fn observe(
        &mut self,
        rid: usize,
        owner: usize,
        slot: i64,
        table: usize,
        dep: Dependency,
        version: u64,
    ) {
        if self
            .targets
            .get(&table)
            .is_some_and(|target| *target != rid || self.allow_set_ports)
        {
            let known = self
                .owners
                .entry((table, dep))
                .or_insert((owner, slot, version));
            if version > known.2 {
                *known = (owner, slot, version);
            }
        }
    }

    fn cite(&mut self, rid: usize, owner: usize, refs: &[Ref]) {
        for premise in refs {
            if let Some(table) = self.inputs[rid][premise.atom] {
                self.observe(
                    rid,
                    owner,
                    !(premise.atom as i64),
                    table,
                    premise.row,
                    premise.version,
                );
            }
        }
    }
}

pub(crate) fn chain_function_result(g: &Graph, t: usize, i: usize, op: usize) {
    STATE.with_borrow_mut(|s| {
        let Some(s) = s else { return };
        let Some((owner, _, _, rid, _)) = s.active else {
            return;
        };
        if let Some(live) = &mut s.live_chain
            && rid != live.target
            && live.tables.contains(&t)
            && let Some(row) = g.function(i)
        {
            live.returned(
                rid,
                t,
                row.witness,
                row.epoch,
                g.epoch,
                (owner, op as i64),
                &row.values,
                row.values.last().unwrap(),
            );
        }
        let Some(trace) = &mut s.chain_lifecycle else {
            return;
        };
        if !trace.targets.get(&t).is_some_and(|target| *target != rid) {
            return;
        }
        if let Some(row) = g.function(i) {
            trace.observe(rid, owner, op as i64, t, row.witness, row.epoch);
            trace.writes.push(json!([
                owner,
                rid,
                g.epoch,
                t,
                op,
                i,
                row.epoch,
                &*row.values
            ]));
        }
    });
}

pub(crate) fn chain_updates(g: &Graph) -> Result<()> {
    STATE.with_borrow_mut(|s| {
        if let Some(join) = s.as_mut().and_then(|s| s.live_join.as_mut()) {
            join.publish(g)?;
        }
        if let Some(chain) = s.as_mut().and_then(|s| s.live_chain.as_mut()) {
            chain.publish(g)?;
        }
        let Some(trace) = s.as_mut().and_then(|s| s.chain_lifecycle.as_mut()) else {
            return Ok(());
        };
        for (table, changes) in g.changes.tables() {
            if !trace.targets.contains_key(&table) {
                continue;
            }
            for &dep in changes.keys() {
                trace.publish_changes += 1;
                let Some(&(owner, slot, old)) = trace.owners.get(&(table, dep)) else {
                    continue;
                };
                trace.publish_reads += 1;
                let row = g
                    .row(dep)?
                    .filter(|r| r.table == table && r.witness == dep && !r.hidden);
                if let Some(row) = row {
                    if row.epoch > old {
                        trace.updates.push(json!([
                            g.epoch,
                            table,
                            dep,
                            owner,
                            slot,
                            old,
                            row.epoch,
                            &*row.values
                        ]));
                        trace.owners.insert((table, dep), (owner, slot, row.epoch));
                    }
                } else {
                    trace
                        .updates
                        .push(json!([g.epoch, table, dep, owner, slot, old, null, null]));
                    trace.owners.remove(&(table, dep));
                }
            }
        }
        Ok(())
    })
}

#[derive(Deserialize)]
struct ChainPacket {
    birth: u64,
    refs: [(Dependency, u64); 3],
}

struct ChainChecks {
    policy: Option<[bool; 16]>,
    pending: BTreeMap<usize, Vec<ChainPacket>>,
    checked: Vec<J>,
    seen: std::collections::BTreeSet<(usize, u64)>,
}

pub fn configure_chain_checks(program: &Program, spec: &J, policy: &J) -> Result<()> {
    let policy = serde_json::from_value(policy.clone()).map_err(|e| e.to_string())?;
    let pending: BTreeMap<usize, Vec<ChainPacket>> =
        serde_json::from_value(spec.clone()).map_err(|e| e.to_string())?;
    for &rid in pending.keys() {
        let rule = program.rules.get(rid).ok_or("unknown chain rule")?;
        if rule.query.len() != 3
            || rule.query.iter().any(|a| {
                !matches!(a.call, Call::Table(_))
                    || a.args.iter().any(|arg| !matches!(arg, Arg::Slot(_)))
            })
        {
            return Err("chain check expects three explicit table premises".into());
        }
    }
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.chain_checks = Some(ChainChecks {
                policy,
                pending,
                checked: vec![],
                seen: Default::default(),
            });
        }
    });
    Ok(())
}

pub(crate) fn check_chain_packets(g: &Graph, rid: usize, mark: u64) -> Result<()> {
    STATE.with_borrow_mut(|s| {
        let Some(state) = s.as_mut() else {
            return Ok(());
        };
        let Some(checks) = state.chain_checks.as_mut() else {
            return Ok(());
        };
        let Some(pending) = checks.pending.get_mut(&rid) else {
            return Ok(());
        };
        if !checks.seen.insert((rid, g.epoch)) {
            return Ok(());
        }
        let rule = &g.program.rules[rid];
        for p in std::mem::take(pending) {
            if p.birth >= g.epoch {
                pending.push(p);
                continue;
            }
            let fresh = !rule.seminaive || p.refs.iter().any(|r| r.1 >= mark);
            if let Some(policy) = checks.policy {
                let trace = state
                    .chain_lifecycle
                    .as_ref()
                    .ok_or("release needs named receipt history")?;
                let mut code = usize::from(fresh);
                for (atom, &(dep, version)) in rule.query.iter().zip(&p.refs) {
                    let Call::Table(t) = atom.call else {
                        unreachable!()
                    };
                    code = 2 * code
                        + usize::from(trace.owners.get(&(t, dep)).is_some_and(|o| o.2 == version));
                }
                if !policy[code] {
                    checks.checked.push(json!([
                        rid, g.epoch, p.birth, p.refs, mark, fresh, false, 0, false
                    ]));
                    continue;
                }
            }
            let mut valid = fresh;
            let mut slots = Slots::default();
            let mut reads = 0;
            if valid {
                for (atom, &(dep, version)) in rule.query.iter().zip(&p.refs) {
                    reads += 1;
                    let Some(row) = g.row(dep)? else {
                        valid = false;
                        break;
                    };
                    if row.witness != dep
                        || row.hidden
                        || row.epoch != version
                        || !matches!(atom.call,Call::Table(t) if t==row.table)
                        || atom.args.len() != row.values.len()
                    {
                        valid = false;
                        break;
                    }
                    for (arg, value) in atom.args.iter().zip(row.values.iter()) {
                        let Arg::Slot(i) = arg else { unreachable!() };
                        if slots.get(i).is_some_and(|v| v != value) {
                            valid = false;
                            break;
                        }
                        slots.insert(*i, value.clone());
                    }
                    if !valid {
                        break;
                    }
                }
            }
            checks.checked.push(json!([
                rid, g.epoch, p.birth, p.refs, mark, fresh, valid, reads
            ]));
        }
        Ok(())
    })
}

pub(crate) fn observe_chain_run(rid: usize, epoch: u64, watermark: u64) {
    STATE.with_borrow_mut(|state| {
        if let Some(trace) = state.as_mut().and_then(|s| s.chain_lifecycle.as_mut())
            && trace.targets.values().any(|&target| target == rid)
        {
            trace.scheduled.push([rid as u64, epoch, watermark]);
        }
    });
}

// A committed Set can create or reuse a constructor owned by another token.
// Resolve the named witness only; release later Runs against publication versions.
pub(crate) fn trace_set_port(g: &Graph, table: usize, op: usize, dep: Dependency) -> Result<()> {
    STATE.with_borrow_mut(|s| {
        let Some(s) = s else { return Ok(()) };
        let Some(trace) = &mut s.chain_lifecycle else {
            return Ok(());
        };
        if !trace.allow_set_ports || !trace.targets.contains_key(&table) {
            return Ok(());
        }
        let Some((owner, _, _, rid, _)) = s.active else {
            return Ok(());
        };
        let Dependency::Fact(f) = dep else {
            return Ok(());
        };
        let Some(row) = g
            .row(dep)?
            .filter(|r| r.table == table && r.witness == dep && !r.hidden)
        else {
            return Ok(());
        };
        trace.observe(rid, owner, op as i64, table, dep, row.epoch);
        if let Some((_, rows)) = &mut s.chain_rows {
            rows.push(json!([
                owner,
                rid,
                g.epoch,
                table,
                op,
                f.cell,
                f.op,
                row.epoch,
                &*row.values
            ]));
        }
        Ok(())
    })
}

pub fn trace_initial_ports(g: &Graph) -> Result<()> {
    STATE.with_borrow_mut(|s| {
        let Some(trace) = s.as_mut().and_then(|s| s.chain_lifecycle.as_mut()) else {
            return Ok(());
        };
        for &table in trace.targets.keys() {
            for dep in g.witnesses(table) {
                if let Some(row) = g
                    .row(dep)?
                    .filter(|r| r.table == table && r.witness == dep && !r.hidden)
                {
                    let slot = trace.initial.len() as i64;
                    trace.owners.insert((table, dep), (0, slot, row.epoch));
                    trace
                        .initial
                        .push(json!([slot, table, dep, row.epoch, &*row.values]));
                }
            }
        }
        Ok(())
    })
}

// Held-out labels for diagnosis. Only source-committed serials are exported.
fn trace_join_proof(
    g: &Graph,
    rid: usize,
    serial: u64,
    known: &[Option<Dependency>],
) -> Result<()> {
    STATE.with_borrow_mut(|s| {
        let Some(trace) = s.as_mut().and_then(|s| s.chain_lifecycle.as_mut()) else {
            return Ok(());
        };
        if !trace.allow_set_ports || !trace.targets.values().any(|&rule| rule == rid) {
            return Ok(());
        }
        let mut proof = Vec::new();
        for (atom, w) in known.iter().enumerate() {
            if let Some(dep) = *w {
                let row = g.row(dep)?.ok_or("verified port disappeared")?;
                proof.push(json!([atom, dep, row.epoch, &*row.values]));
            }
        }
        trace.proofs.insert(serial, proof);
        Ok(())
    })
}

pub(crate) fn trace_port_union(epoch: u64, hi: u64, lo: u64) {
    STATE.with_borrow_mut(|s| {
        if let Some(trace) = s.as_mut().and_then(|s| s.chain_lifecycle.as_mut())
            && trace.allow_set_ports
        {
            trace.aliases.push([epoch, hi, lo]);
        }
    });
}
