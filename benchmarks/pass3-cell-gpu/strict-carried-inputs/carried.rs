use crate::{
    graph::{Dependency, FactRef, Graph},
    joint_root::Ref,
    program::{Arg, Call, Op, Program, Result},
    value::{Value, canon},
};
use serde::Serialize;
use serde_json::{Value as J, json};
use sha2::{Digest, Sha256};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet, HashMap, HashSet},
};
#[derive(Clone)]
pub(crate) struct Child {
    pub producer: u64,
    pub refs: Vec<Ref>,
    pub path: Vec<Dependency>,
}
struct Grant {
    epoch: u64,
    serial: u64,
    refs: Vec<Ref>,
    phys: Option<u32>,
    result: Option<Ref>,
}
#[derive(Default, Serialize)]
struct Counts {
    tags: u64,
    producers: u64,
    incomplete_named: u64,
    allocated: u64,
    actual_outputs: u64,
    expired: u64,
    release_attempts: u64,
    missing: u64,
    stale: u64,
    wrong_table: u64,
    atom_guards: u64,
    old_binding: u64,
    public_counts: u64,
    not_unique: u64,
    protected: u64,
    prefix_preempted: u64,
    restored_without_external: u64,
    prefix_checks: u64,
    ordered_comparisons: u64,
    typed_reads: u64,
    count_updates: u64,
    count_unions: u64,
    private_roots: u64,
    confirmed: u64,
    audited_external: u64,
}
struct State {
    rid: usize,
    table: usize,
    op: usize,
    replaced: usize,
    last_table: usize,
    last_column: usize,
    distance: u64,
    fault: u8,
    trace: bool,
    counts: Counts,
    active: Option<Grant>,
    future: BTreeMap<u64, Vec<Child>>,
    degree: HashMap<Value, u8>,
    registered: HashMap<u64, Child>,
    protected: HashSet<Vec<Dependency>>,
    epoch: u64,
    audit: Vec<serde_json::Value>,
    collisions: [u64; 3],
    live: [u64; 3],
    guard_atoms: [u64; 5],
    audit_rows: u64,
}
thread_local! {static S:RefCell<Option<State>>=const{RefCell::new(None)};}
fn canonical_json(v: &J) -> String {
    match v {
        J::Object(m) => {
            let m: BTreeMap<_, _> = m.iter().collect();
            format!(
                "{{{}}}",
                m.iter()
                    .map(|(k, v)| format!(
                        "{}:{}",
                        serde_json::to_string(k).unwrap(),
                        canonical_json(v)
                    ))
                    .collect::<Vec<_>>()
                    .join(",")
            )
        }
        J::Array(a) => format!(
            "[{}]",
            a.iter().map(canonical_json).collect::<Vec<_>>().join(",")
        ),
        _ => v.to_string(),
    }
}
pub fn configure(cfg: &J, p: &Program, source: &[u8], trace: bool) -> Result<()> {
    S.with_borrow_mut(|s| *s = None);
    if cfg.is_null() {
        return Ok(());
    }
    if cfg["producer"] != cfg["consumer"] {
        return Err("carried self template requires one common schema".into());
    }
    let ir: J = serde_json::from_slice(source).map_err(|e| e.to_string())?;
    let rules = ir["recipe"]["rules"].as_array().ok_or("missing rules")?;
    let expected = cfg["producer"]
        .as_str()
        .ok_or("missing donor fingerprint")?;
    let mut matches = vec![];
    for (i, r) in rules.iter().enumerate() {
        let struc = ["metadata", "query", "effects", "slots", "interface"]
            .iter()
            .map(|k| canonical_json(&r[*k]))
            .collect::<Vec<_>>()
            .join(",");
        if format!("{:x}", Sha256::digest(format!("[{struc}]").as_bytes())) == expected {
            matches.push(i)
        }
    }
    let &[rid] = matches.as_slice() else {
        return Err("carried schema unavailable or ambiguous".into());
    };
    let rule = &p.rules[rid];
    let width = rule.query.len();
    let wires = cfg["wires"].as_array().ok_or("no carried map")?;
    if !rule.seminaive || width != 5 || wires.len() != width {
        return Err("unsupported carried rule arity".into());
    }
    let (mut produced, mut tables) = (vec![], vec![]);
    let dedup: BTreeSet<usize> = serde_json::from_value(ir["physical_plan"]["dedup"][rid].clone())
        .map_err(|e| e.to_string())?;
    for (i, (wire, a)) in wires.iter().zip(rule.query.iter()).enumerate() {
        if wire[0].as_u64() != Some(i as u64) {
            return Err("unordered carried mapping".into());
        }
        let Call::Table(t) = &a.call else {
            return Err("unnamed carried atom".into());
        };
        if !p.tables[*t].constructor {
            return Err("carried template only accepts immutable fact sources".into());
        }
        for v in &a.args[..a.args.len() - 1] {
            if let Arg::Slot(k) = v
                && !dedup.contains(k)
            {
                return Err("winner key does not determine all fact rows".into());
            }
        }
        match wire[1].as_str() {
            Some("input") if wire[2].as_u64() == Some(i as u64) => {}
            Some("op") => {
                let op = wire[2].as_u64().ok_or("bad carried op")? as usize;
                if !matches!(p.templates[rule.template].ops.get(op),Some(Op::Let(_,Call::Table(tt),_)) if tt==t)
                {
                    return Err("carried output table mismatch".into());
                }
                produced.push((i, op, *t));
            }
            _ => return Err("invalid carried parent".into()),
        }
        tables.push(*t);
    }
    let &[(replaced, op, table)] = produced.as_slice() else {
        return Err("one carried output required".into());
    };
    if replaced == width - 1 {
        return Err("new operation must occur in disjoint prefix".into());
    }
    let last = &rule.query[width - 1];
    let last_column = 0usize;
    if p.tables[tables[width - 1]].schema[last_column]["kind"] != "eq" {
        return Err("terminal-count certificate requires an Eq scalar column".into());
    }
    let Some(Arg::Slot(probe)) = last.args.get(last_column) else {
        return Err("terminal probe must have a named key".into());
    };
    if !rule.query[..width - 1]
        .iter()
        .any(|a| a.args.iter().any(|k| matches!(k,Arg::Slot(s) if s==probe)))
    {
        return Err("unconstrained terminal key".into());
    }
    let distance = cfg["distance"]
        .as_u64()
        .filter(|d| (1..=16).contains(d))
        .ok_or("unbounded Run release")?;
    let fault = match cfg["fault"].as_str() {
        None => 0,
        Some("version") => 1,
        Some("count") => 2,
        _ => return Err("unknown carry fault".into()),
    };
    S.with_borrow_mut(|c| {
        *c = Some(State {
            rid,
            table,
            op,
            replaced,
            last_table: tables[width - 1],
            last_column,
            distance,
            fault,
            trace,
            counts: Default::default(),
            active: None,
            future: Default::default(),
            degree: Default::default(),
            registered: Default::default(),
            protected: Default::default(),
            epoch: 0,
            audit: vec![],
            collisions: [0; 3],
            live: [0; 3],
            guard_atoms: [0; 5],
            audit_rows: 0,
        })
    });
    Ok(())
}
pub(crate) fn tag(rid: usize, template: usize, n: usize) -> usize {
    S.with_borrow_mut(|c| {
        if let Some(s) = c
            && s.rid == rid
        {
            s.counts.tags += n as u64;
            template | 1usize << 32
        } else {
            template
        }
    })
}
pub(crate) fn begin(sid: u64, rid: usize, ep: u64, refs: &[Ref], signed: bool) -> Result<()> {
    S.with_borrow_mut(|c| {
        let Some(s) = c else { return Ok(()) };
        s.active = None;
        if let Some(child) = s.registered.remove(&sid) {
            if s.rid != rid
                || refs.len() != child.refs.len()
                || !refs
                    .iter()
                    .zip(&child.refs)
                    .all(|(a, b)| a.atom == b.atom && a.row == b.row && a.version == b.version)
            {
                return Err("carried child provenance differs".into());
            }
            s.counts.confirmed += 1;
            return Ok(());
        }
        if !signed {
            return Ok(());
        }
        if rid != s.rid {
            return Err("incorrect signed carried producer".into());
        }
        if refs.len() != 5 || refs.iter().enumerate().any(|(i, r)| r.atom != i) {
            s.counts.incomplete_named += 1;
            return Ok(());
        }
        s.counts.producers += 1;
        s.active = Some(Grant {
            epoch: ep,
            serial: sid,
            refs: refs.to_vec(),
            phys: None,
            result: None,
        });
        Ok(())
    })
}
pub(crate) fn fresh(id: u32) {
    S.with_borrow_mut(|c| {
        if let Some(s) = c
            && let Some(a) = &mut s.active
        {
            a.phys = Some(id);
            s.counts.allocated += 1;
        }
    })
}
pub(crate) fn birth(g: &Graph, f: FactRef, t: usize, key: &[Value]) {
    S.with_borrow_mut(|c| {
        let Some(s) = c else { return };
        if t == s.last_table {
            let k = canon(&key[s.last_column], &g.parents);
            let e = s.degree.entry(k).or_default();
            *e = (*e + 1).min(2);
            s.counts.count_updates += 1;
        }
        if t == s.table
            && s.op == f.op as usize
            && let Some(a) = &mut s.active
            && a.phys == Some(f.cell)
        {
            a.result = Some(Ref {
                atom: s.replaced,
                row: Dependency::Fact(f),
                version: g.epoch,
            });
            s.counts.actual_outputs += 1;
        }
    })
}
pub(crate) fn union(hi: u64, lo: u64) {
    S.with_borrow_mut(|c| {
        if let Some(s) = c
            && let Some(n) = s.degree.remove(&Value::Eq(hi))
        {
            let e = s.degree.entry(Value::Eq(lo)).or_default();
            *e = (*e + n).min(2);
            s.counts.count_unions += 1;
        }
    })
}
pub(crate) fn end() {
    S.with_borrow_mut(|c| {
        if let Some(s) = c
            && let Some(mut a) = s.active.take()
            && let Some(r) = a.result
        {
            a.refs[s.replaced] = r;
            let path = a.refs.iter().map(|r| r.row).collect();
            s.future
                .entry(a.epoch + s.distance)
                .or_default()
                .push(Child {
                    producer: a.serial,
                    refs: a.refs,
                    path,
                });
        }
    })
}
pub(crate) fn release(
    g: &Graph,
    rid: usize,
    wm: u64,
    layout: &[(usize, usize, Vec<usize>)],
) -> Result<Vec<Child>> {
    S.with_borrow_mut(|c| {
        let Some(s) = c else { return Ok(vec![]) };
        if g.epoch != s.epoch {
            s.protected.clear();
            s.epoch = g.epoch;
        }
        while s
            .future
            .first_key_value()
            .is_some_and(|(&e, _)| e < g.epoch)
        {
            s.counts.expired += s.future.pop_first().unwrap().1.len() as u64;
        }
        if rid != s.rid {
            return Ok(vec![]);
        }
        let rule = &g.program.rules[rid];
        if layout.len() != 5
            || layout
                .iter()
                .enumerate()
                .any(|(i, (j, p, _))| i != *j || *p != 1)
            || layout[4].2.first() != Some(&s.last_column)
        {
            return Err("unsupported carried producer order".into());
        }
        let mut issued = vec![];
        'child: for child in s.future.remove(&g.epoch).unwrap_or_default() {
            s.counts.release_attempts += 1;
            let mut slots: Vec<Option<Value>> =
                vec![None; g.program.templates[rule.template].sorts.len()];
            let mut max_ep = 0;
            let mut last_key = None;
            for (i, r) in child.refs.iter().enumerate() {
                s.counts.typed_reads += 1;
                let Some(row) = g.row(r.row)?.filter(|r| !r.hidden) else {
                    s.counts.missing += 1;
                    continue 'child;
                };
                let expected = if s.fault == 1 && i == s.replaced {
                    r.version.wrapping_add(1)
                } else {
                    r.version
                };
                if row.epoch != expected {
                    s.counts.stale += 1;
                    continue 'child;
                }
                let atom = &rule.query[i];
                if !matches!(atom.call,Call::Table(t) if t==row.table)
                    || row.values.len() != atom.args.len()
                {
                    s.counts.wrong_table += 1;
                    continue 'child;
                }
                max_ep = max_ep.max(row.epoch);
                for (v, val) in atom.args.iter().zip(row.values.iter()) {
                    let ok = match v {
                        Arg::Literal(l) => canon(l, &g.parents) == *val,
                        Arg::Slot(slot) => match &slots[*slot] {
                            Some(old) => old == val,
                            None => {
                                slots[*slot] = Some(val.clone());
                                true
                            }
                        },
                    };
                    if !ok {
                        s.counts.atom_guards += 1;
                        s.guard_atoms[i] += 1;
                        continue 'child;
                    }
                }
                if i == 4 {
                    last_key = Some(row.values[s.last_column].clone());
                }
            }
            if max_ep < wm {
                s.counts.old_binding += 1;
                continue;
            }
            s.counts.public_counts += 1;
            let last_key = last_key.unwrap();
            let degree = s.degree.get(&last_key).copied().unwrap_or(0);
            // Detailed reference cross-check only. The measured release path consumes only the public bound and carried addresses.
            if s.trace {
                let mut live = 0usize;
                for w in g.witnesses(s.last_table) {
                    s.audit_rows += 1;
                    if let Some(row) = g.row(w)?
                        && !row.hidden
                        && row.table == s.last_table
                        && row.values[s.last_column] == last_key
                    {
                        live += 1;
                    }
                }
                assert!(degree >= live.min(2) as u8 && live >= 1);
                s.live[live.min(2)] += 1;
            }
            s.collisions[degree as usize] += 1;
            if degree != 1 || s.fault == 2 {
                s.counts.not_unique += 1;
                continue;
            }
            let prefix = child.path[..4].to_vec();
            if !s.protected.insert(prefix) {
                return Err("ambiguous carried prefix".into());
            }
            s.counts.protected += 1;
            issued.push(child);
        }
        issued.sort_unstable_by(|a, b| a.path.cmp(&b.path));
        Ok(issued)
    })
}
pub(crate) fn excluded(rid: usize, ep: u64, path: &[Dependency]) -> bool {
    S.with_borrow_mut(|c| {
        let Some(s) = c else { return false };
        if rid != s.rid || ep != s.epoch || path.len() != 4 || s.protected.is_empty() {
            return false;
        }
        s.counts.prefix_checks += 1;
        let yes = s.protected.contains(path);
        s.counts.prefix_preempted += u64::from(yes);
        yes
    })
}
pub(crate) fn placed(serial: u64, child: Child, ep: u64) {
    S.with_borrow_mut(|c| {
        let s = c.as_mut().unwrap();
        s.counts.private_roots += 1;
        if s.trace {
            s.audit
                .push(json!([serial, child.producer, ep, child.refs]));
        }
        assert!(s.registered.insert(serial, child).is_none());
    })
}
pub(crate) fn check_external(ep: u64, rid: usize, refs: &[Ref], width: usize) {
    S.with_borrow_mut(|c| {
        if let Some(s) = c
            && s.trace
            && rid == s.rid
            && ep == s.epoch
        {
            for rs in refs.chunks_exact(width) {
                s.counts.audited_external += 1;
                assert!(
                    rs.len() == 5
                        && !s
                            .protected
                            .contains(&rs[..4].iter().map(|r| r.row).collect::<Vec<_>>()),
                    "duplicate carried proof emitted"
                );
            }
        }
    })
}
pub fn report() -> J {
    S.with_borrow(|c|c.as_ref().map_or(J::Null,|s|json!({"counts":s.counts,"children":s.audit,"outstanding":s.registered.len(),"terminal_degree_bins":s.collisions,"reference_live_degree_bins":s.live,"reference_rows":s.audit_rows,"guard_failure_atoms":s.guard_atoms,"degree_keys":s.degree.len()})))
}
