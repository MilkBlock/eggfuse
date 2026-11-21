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
    collections::{BTreeMap, BTreeSet, HashMap},
};
#[derive(Default, Serialize)]
struct Counts {
    producer_tags: u64,
    signed_commits: u64,
    missing_named: u64,
    fresh_producers: u64,
    typed_returns: u64,
    both_returns: u64,
    expired: u64,
    unavailable: u64,
    multiplicity: u64,
    watermark: u64,
    nonmatching: u64,
    captured: u64,
    duplicates: u64,
    direct_reads: u64,
    upper_bound_reads: u64,
    count_activations: u64,
    count_unions: u64,
    protected_anchors: u64,
    bypassed_reverse: u64,
    private_created: u64,
    actual_commits: u64,
    audited_external_lanes: u64,
}
#[derive(Clone)]
pub(crate) struct Pair {
    pub producer: u64,
    pub left: Ref,
    pub right: Ref,
}
struct Active {
    serial: u64,
    epoch: u64,
    cell: Option<u32>,
    left: Option<Ref>,
    right: Option<Ref>,
}
struct State {
    p: usize,
    c: usize,
    lt: usize,
    rt: usize,
    ops: [usize; 2],
    lc: usize,
    source_atoms: Vec<usize>,
    fault: u8,
    active: Option<Active>,
    protected_epoch: u64,
    protected: BTreeSet<Dependency>,
    ready: BTreeMap<u64, Vec<Pair>>,
    counts: Counts,
    degree: HashMap<u64, u8>,
    internal: HashMap<u64, Pair>,
    logged: Vec<[u64; 5]>,
    trace: bool,
}
thread_local! {static S:RefCell<Option<State>>=const{RefCell::new(None)};}
fn sorted_json(v: &J) -> String {
    match v {
        J::Object(m) => {
            let sorted: BTreeMap<_, _> = m.iter().collect();
            format!(
                "{{{}}}",
                sorted
                    .into_iter()
                    .map(|(k, v)| format!(
                        "{}:{}",
                        serde_json::to_string(k).unwrap(),
                        sorted_json(v)
                    ))
                    .collect::<Vec<_>>()
                    .join(",")
            )
        }
        J::Array(a) => format!(
            "[{}]",
            a.iter().map(sorted_json).collect::<Vec<_>>().join(",")
        ),
        _ => v.to_string(),
    }
}
fn fingerprint(r: &J) -> String {
    let cols = ["metadata", "query", "effects", "slots", "interface"]
        .iter()
        .map(|k| sorted_json(&r[*k]))
        .collect::<Vec<_>>()
        .join(",");
    format!("{:x}", Sha256::digest(format!("[{cols}]").as_bytes()))
}
pub fn configure(cfg: &J, program: &Program, source: &[u8], trace: bool) -> Result<()> {
    S.with_borrow_mut(|s| *s = None);
    if cfg.is_null() {
        return Ok(());
    }
    let artifacts: J = serde_json::from_slice(source).map_err(|e| e.to_string())?;
    let rules = artifacts["recipe"]["rules"].as_array().unwrap();
    let find = |sig: &str| -> Result<usize> {
        let hits: Vec<_> = rules
            .iter()
            .enumerate()
            .filter(|(_, r)| fingerprint(r) == sig)
            .map(|(i, _)| i)
            .collect();
        if hits.len() != 1 {
            return Err("ambiguous signed dual template".into());
        }
        Ok(hits[0])
    };
    let p = find(cfg["producer"].as_str().ok_or("missing producer schema")?)?;
    let c = find(cfg["consumer"].as_str().ok_or("missing consumer schema")?)?;
    let ops: [usize; 2] = serde_json::from_value(cfg["ops"].clone()).map_err(|e| e.to_string())?;
    let a = &program.rules[p];
    let b = &program.rules[c];
    if cfg["distance"] != 1 || b.query.len() != 2 || !b.seminaive {
        return Err("unsupported dual release mode".into());
    }
    let (Call::Table(lt), Call::Table(rt)) = (&b.query[0].call, &b.query[1].call) else {
        return Err("missing named dual table".into());
    };
    if !program.tables[*lt].constructor || !program.tables[*rt].constructor {
        return Err("dual parents must be constructors".into());
    }
    let (Some(Op::Let(_, Call::Table(a0), args)), Some(Op::Let(dst, Call::Table(a1), _))) = (
        program.templates[a.template].ops.get(ops[0]),
        program.templates[a.template].ops.get(ops[1]),
    ) else {
        return Err("unproved dual operations".into());
    };
    if a0 != lt || a1 != rt || ops[1] >= ops[0] {
        return Err("incorrect dual constructor programs".into());
    }
    let Some(Arg::Slot(shared)) = b.query[1].args.last() else {
        return Err("unexpected inverse projection".into());
    };
    let Some(lc) = b.query[0]
        .args
        .iter()
        .position(|x| matches!(x,Arg::Slot(v) if v==shared))
    else {
        return Err("missing dual shared slot".into());
    };
    if !matches!(args.get(lc),Some(Arg::Slot(x)) if x==dst) {
        return Err("unconnected dual RHS output".into());
    }
    let dedup: BTreeSet<usize> =
        serde_json::from_value(artifacts["physical_plan"]["dedup"][c].clone())
            .map_err(|e| e.to_string())?;
    let mut seen = BTreeSet::new();
    for (i, atom) in b.query.iter().enumerate() {
        for (j, arg) in atom.args.iter().enumerate() {
            let Arg::Slot(v) = arg else {
                return Err("unsupported dual literal".into());
            };
            if !(i == 1 && j + 1 == atom.args.len()) && !seen.insert(*v) {
                return Err("unsupported dual repetition".into());
            }
            if j + 1 < atom.args.len() && !dedup.contains(v) {
                return Err("winner key does not determine every physical source key".into());
            }
        }
    }
    let source_atoms = a
        .query
        .iter()
        .enumerate()
        .filter_map(|(i, q)| matches!(q.call, Call::Table(_)).then_some(i))
        .collect();
    let fault = match cfg["fault"].as_str() {
        None => 0,
        Some("version") => 1,
        Some("count") => 2,
        _ => return Err("unknown proof fault".into()),
    };
    S.with_borrow_mut(|s| {
        *s = Some(State {
            p,
            c,
            lt: *lt,
            rt: *rt,
            ops,
            lc,
            source_atoms,
            fault,
            trace,
            active: None,
            protected_epoch: 0,
            protected: Default::default(),
            ready: Default::default(),
            counts: Default::default(),
            degree: Default::default(),
            internal: Default::default(),
            logged: vec![],
        })
    });
    Ok(())
}
pub(crate) fn tag(rule: usize, template: usize, n: usize) -> usize {
    S.with_borrow_mut(|s| {
        if let Some(s) = s
            && rule == s.p
        {
            s.counts.producer_tags += n as u64;
            template | 1usize << 32
        } else {
            template
        }
    })
}
pub(crate) fn begin(serial: u64, rule: usize, epoch: u64, refs: &[Ref], tag: bool) -> Result<()> {
    S.with_borrow_mut(|c| {
        let Some(s) = c else { return Ok(()) };
        s.active = None;
        if let Some(p) = s.internal.remove(&serial) {
            if rule != s.c
                || refs.len() != 2
                || refs[0].row != p.left.row
                || refs[0].version != p.left.version
                || refs[1].row != p.right.row
                || refs[1].version != p.right.version
            {
                return Err("internal dual origin mismatch".into());
            }
            s.counts.actual_commits += 1;
            return Ok(());
        }
        if !tag {
            return Ok(());
        }
        if rule != s.p {
            return Err("wrong dual variant".into());
        }
        let named: BTreeSet<_> = refs.iter().map(|r| r.atom).collect();
        if named.len() != refs.len() || named.iter().copied().ne(s.source_atoms.iter().copied()) {
            s.counts.missing_named += 1;
            return Ok(());
        }
        s.counts.signed_commits += 1;
        s.active = Some(Active {
            serial,
            epoch,
            cell: None,
            left: None,
            right: None,
        });
        Ok(())
    })
}
pub(crate) fn fresh(id: u32) {
    S.with_borrow_mut(|c| {
        if let Some(s) = c
            && let Some(a) = &mut s.active
        {
            a.cell = Some(id);
            s.counts.fresh_producers += 1;
        }
    })
}
pub(crate) fn birth(g: &Graph, f: FactRef, t: usize, v: &Value) {
    S.with_borrow_mut(|c| {
        let Some(s) = c else { return };
        if t == s.rt
            && let Value::Eq(id) = canon(v, &g.parents)
        {
            let k = s.degree.entry(id).or_default();
            *k = (*k + 1).min(2);
            s.counts.count_activations += 1;
        }
        if let Some(a) = &mut s.active
            && a.cell == Some(f.cell)
        {
            let atom = if t == s.lt && f.op as usize == s.ops[0] {
                0
            } else if t == s.rt && f.op as usize == s.ops[1] {
                1
            } else {
                return;
            };
            let r = Ref {
                atom,
                row: Dependency::Fact(f),
                version: g.epoch,
            };
            if atom == 0 {
                a.left = Some(r)
            } else {
                a.right = Some(r)
            }
            s.counts.typed_returns += 1;
        }
    })
}
pub(crate) fn union(hi: u64, lo: u64) {
    S.with_borrow_mut(|c| {
        if let Some(s) = c
            && let Some(n) = s.degree.remove(&hi)
        {
            let entry = s.degree.entry(lo).or_default();
            *entry = (*entry + n).min(2);
            s.counts.count_unions += 1;
        }
    })
}
pub(crate) fn end() {
    S.with_borrow_mut(|c| {
        if let Some(s) = c
            && let Some(a) = s.active.take()
            && let (Some(left), Some(right)) = (a.left, a.right)
        {
            s.ready.entry(a.epoch + 1).or_default().push(Pair {
                producer: a.serial,
                left,
                right,
            });
            s.counts.both_returns += 1;
        }
    })
}
pub(crate) fn release(g: &Graph, rid: usize, mark: u64) -> Result<BTreeMap<Dependency, Pair>> {
    S.with_borrow_mut(|c| {
        let mut result = BTreeMap::new();
        let Some(s) = c else { return Ok(result) };
        while s.ready.first_key_value().is_some_and(|(&e, _)| e < g.epoch) {
            s.counts.expired += s.ready.pop_first().unwrap().1.len() as u64;
        }
        if s.protected_epoch != g.epoch {
            s.protected.clear();
            s.protected_epoch = g.epoch;
        }
        if rid != s.c {
            return Ok(result);
        }
        for p in s.ready.remove(&g.epoch).unwrap_or_default() {
            s.counts.direct_reads += 2;
            let version = if s.fault == 1 {
                p.right.version.wrapping_add(1)
            } else {
                p.right.version
            };
            let (Some(a), Some(b)) = (
                g.row(p.left.row)?
                    .filter(|r| !r.hidden && r.table == s.lt && r.epoch == p.left.version),
                g.row(p.right.row)?
                    .filter(|r| !r.hidden && r.table == s.rt && r.epoch == version),
            ) else {
                s.counts.unavailable += 1;
                continue;
            };
            if a.epoch.max(b.epoch) < mark {
                s.counts.watermark += 1;
                continue;
            }
            let Some(Value::Eq(eq)) = b.values.last() else {
                return Err("unexpected public dual result".into());
            };
            if a.values.get(s.lc) != b.values.last() {
                s.counts.nonmatching += 1;
                continue;
            }
            s.counts.upper_bound_reads += 1;
            if s.degree.get(eq) != Some(&1) || s.fault == 2 {
                s.counts.multiplicity += 1;
                continue;
            }
            if result.insert(p.left.row, p).is_some() {
                return Err("ambiguous dual owner".into());
            }
            s.counts.captured += 1;
        }
        s.protected.extend(result.keys().copied());
        Ok(result)
    })
}
pub(crate) fn minted(serial: u64, p: Pair, epoch: u64) {
    S.with_borrow_mut(|c| {
        let s = c.as_mut().unwrap();
        s.counts.private_created += 1;
        if s.trace {
            let enc = |d: Dependency| match d {
                Dependency::Fact(f) => (u64::from(f.cell) << 32) | u64::from(f.op),
                _ => unreachable!(),
            };
            s.logged
                .push([serial, p.producer, epoch, enc(p.left.row), enc(p.right.row)]);
        }
        assert!(s.internal.insert(serial, p).is_none());
    })
}
pub(crate) fn skip(reverse: bool) {
    S.with_borrow_mut(|c| {
        if let Some(s) = c {
            if reverse {
                s.counts.bypassed_reverse += 1
            } else {
                s.counts.protected_anchors += 1
            }
        }
    })
}
pub fn report() -> J {
    S.with_borrow(|c|c.as_ref().map_or(J::Null,|s|json!({"counts":s.counts,"children":s.logged,"outstanding":s.internal.len(),"degree_keys":s.degree.len()})))
}

pub(crate) fn check_external(epoch: u64, rid: usize, refs: &[Ref], width: usize) {
    S.with_borrow_mut(|c| {
        if let Some(s) = c
            && s.trace
            && s.c == rid
            && s.protected_epoch == epoch
        {
            for row in refs.chunks_exact(width) {
                assert!(
                    !s.protected.contains(&row[0].row),
                    "an original external consumer packet was double issued"
                );
                s.counts.audited_external_lanes += 1;
            }
        }
    });
}
