// A conservative upper bound on visible inner constructor facts sharing a result class.
// Initialize before graph ingestion; retirement never lowers the upper bound.
thread_local! {
    static PAIR_DEGREE: RefCell<Option<(usize, BTreeMap<u64,u8>)>> = const {RefCell::new(None)};
}
pub fn prepare_pair_degree(program: &Program, policy: &J) -> Result<()> {
    let table = if policy["takeover"] == true {
        let rid = policy["target"].as_u64().ok_or("missing pair target")? as usize;
        let atom = program
            .rules
            .get(rid)
            .and_then(|r| r.query.get(1))
            .ok_or("missing second atom")?;
        let Call::Table(table) = atom.call else {
            return Err("expected constructor atom".into());
        };
        Some(table)
    } else {
        None
    };
    PAIR_DEGREE.with_borrow_mut(|d| *d = table.map(|t| (t, BTreeMap::new())));
    Ok(())
}
pub(crate) fn pair_birth(g: &Graph, table: usize, v: &Value) {
    PAIR_DEGREE.with_borrow_mut(|d| {
        if let Some((target, counts)) = d
            && table == *target
            && let Value::Eq(id) = crate::value::canon(v, &g.parents)
        {
            let count = counts.entry(id).or_default();
            *count = (*count + 1).min(2);
        }
    });
}
pub(crate) fn pair_union(hi: u64, lo: u64) {
    PAIR_DEGREE.with_borrow_mut(|d| {
        if let Some((_, counts)) = d
            && let Some(n) = counts.remove(&hi)
        {
            let count = counts.entry(lo).or_default();
            *count = (*count + n).min(2);
        }
    });
}
fn unique_pair(value: Option<&Value>) -> bool {
    matches!(value,Some(Value::Eq(id)) if PAIR_DEGREE.with_borrow(|d|
        d.as_ref().is_some_and(|(_,counts)|counts.get(id)==Some(&1))))
}
#[derive(Clone)]
pub(crate) struct ReturnedPair {
    owner: usize,
    refs: [Ref; 2],
}
pub(crate) fn take_pair_pivots(rid: usize) -> BTreeMap<Dependency, ReturnedPair> {
    STATE.with_borrow_mut(|s| {
        s.as_mut()
            .and_then(|s| s.pair_issuer.as_mut())
            .filter(|p| p.policy.target == rid)
            .map(|p| std::mem::take(&mut p.ready))
            .unwrap_or_default()
    })
}
pub(crate) fn pair_child(run: u64, rid: usize, p: ReturnedPair) -> Result<MultiPage> {
    STATE.with_borrow_mut(|s| {
        let s = s.as_mut().ok_or("missing root issuer")?;
        let layout = s.layout[rid].clone();
        let serial = s.serial.checked_add(1).ok_or("root serial overflow")?;
        s.serial = serial;
        let child = MultiPage(Rc::new(MultiPageData {
            run,
            first_serial: serial,
            width: 2,
            source_width: 2,
            count: 1,
            template: layout.template,
            layout,
            refs: p.refs.to_vec(),
            withheld: false,
            invalid_version: false,
        }));
        s.pair_issuer
            .as_mut()
            .unwrap()
            .children
            .push((serial, p.owner));
        Ok(child)
    })
}

fn validate_pair_wiring(policy: &PairPolicy, program: &Program, source: &[u8]) -> Result<()> {
    use crate::program::Op;
    let rule = program
        .rules
        .get(policy.target)
        .ok_or("unknown pair consumer")?;
    let [outer, inner] = rule.query.as_slice() else {
        return Err("expected a two-parent rule".into());
    };
    let (Call::Table(a), Call::Table(b)) = (&outer.call, &inner.call) else {
        return Err("invalid pair tables".into());
    };
    if !rule.seminaive || !program.tables[*a].constructor || !program.tables[*b].constructor {
        return Err("unsupported pair consumer".into());
    }
    let mut slots = std::collections::BTreeSet::new();
    let mut keys = std::collections::BTreeSet::new();
    for atom in [outer, inner] {
        let Some((_, inputs)) = atom.args.split_last() else {
            return Err("missing constructor result".into());
        };
        for arg in inputs {
            let Arg::Slot(slot) = arg else {
                return Err("literal in pair key".into());
            };
            keys.insert(*slot);
        }
    }
    let (Some(Arg::Slot(shared)), Some(Arg::Slot(reference))) =
        (inner.args.last(), outer.args.get(policy.column))
    else {
        return Err("missing shared pair slot".into());
    };
    if policy.column >= outer.args.len() - 1 || shared != reference {
        return Err("wrong shared column".into());
    }
    for arg in outer
        .args
        .iter()
        .chain(inner.args.iter().take(inner.args.len() - 1))
    {
        let Arg::Slot(s) = arg else {
            return Err("literal in pair atom".into());
        };
        if !slots.insert(s) {
            return Err("unexpected repeated pair slot".into());
        }
    }
    let artifact: J = serde_json::from_slice(source).map_err(|e| e.to_string())?;
    let dedup: std::collections::BTreeSet<usize> =
        serde_json::from_value(artifact["physical_plan"]["dedup"][policy.target].clone())
            .map_err(|e| e.to_string())?;
    if !keys.is_subset(&dedup) {
        return Err("ambiguous pair key".into());
    }
    for (&rid, pairs) in &policy.wiring {
        let producer = program.rules.get(rid).ok_or("unknown pair producer")?;
        let ops = &program.templates[producer.template].ops;
        let mut defs = BTreeMap::new();
        let mut proven = std::collections::BTreeSet::new();
        for (i, op) in ops.iter().enumerate() {
            match op {
                Op::Copy(dst, Arg::Slot(src)) => {
                    let src = defs.get(src).copied();
                    defs.remove(dst);
                    if let Some(src) = src {
                        defs.insert(*dst, src);
                    }
                }
                Op::Copy(dst, _) => {
                    defs.remove(dst);
                }
                Op::Let(dst, call, args) => {
                    if matches!(call,Call::Table(table) if table==a)
                        && let Some(Arg::Slot(s)) = args.get(policy.column)
                        && let Some(&j) = defs.get(s)
                    {
                        proven.insert([i, j]);
                    }
                    defs.remove(dst);
                    if matches!(call,Call::Table(table) if table==b) {
                        defs.insert(*dst, i);
                    }
                }
                _ => {}
            }
        }
        if pairs.iter().any(|p| !proven.contains(p)) {
            return Err("unproved return wiring".into());
        }
    }
    Ok(())
}
