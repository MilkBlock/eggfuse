// A signed source coordinate exists before the child Run. Release may open
// precisely these coordinates and reads a cardinality scalar for completeness.
use crate::{
    graph::{Dependency, FactRef, Graph},
    program::{Arg, Call, Result},
    slots::Slots,
};
use serde::Serialize;
use serde_json::{Value as J, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
};
pub(crate) type E = [usize; 3]; // producer, declared operation, consumer (sole pivot is zero)
#[derive(Clone)]
struct Permit {
    root: u64,
    rule: usize,
    prior: Vec<E>,
    run: usize,
}
#[derive(Clone)]
struct Owner {
    path: Vec<E>,
    root: u64,
    born: usize,
    version: u64,
}
#[derive(Default, Serialize)]
struct Counts {
    no_score_banks: u64,
    no_score_inputs: u64,
    audit_score_inputs: u64,
    direct_spine_lookups: u64,
    tagged: u64,
    external_roots: u64,
    no_named_input: u64,
    selected_primary: u64,
    actual_output_events: u64,
    named_ports: u64,
    tries: u64,
    uncovered: u64,
    absent: u64,
    changed: u64,
    stale: u64,
    complete_banks: u64,
    explicit_addresses: u64,
    local_field_reads: u64,
    released: u64,
    actual_internal: u64,
    source_commits: u64,
    two_with_internal_parent: u64,
}
#[derive(Default)]
struct State {
    depth: usize,
    library: Option<BTreeSet<Vec<E>>>,
    extend: bool,
    fault: bool,
    run: usize,
    closed_rules: BTreeSet<usize>,
    targets: BTreeMap<usize, Vec<usize>>,
    next_at: BTreeMap<(usize, usize, usize), Vec<usize>>,
    availability: BTreeMap<usize, [u64; 6]>,
    child_table: BTreeMap<usize, usize>,
    programs: BTreeMap<usize, Vec<Vec<E>>>,
    active: Option<Permit>,
    physical: Option<u32>,
    known: BTreeSet<u64>,
    ports: BTreeMap<usize, BTreeMap<Dependency, Owner>>,
    issued: BTreeMap<u64, Owner>,
    emitting: BTreeMap<(usize, Dependency), Owner>,
    stats: Counts,
    routes: BTreeMap<Vec<E>, [u64; 3]>,
}
thread_local! {static S:RefCell<Option<State>>=const{RefCell::new(None)};}
pub fn configure(spec: &J, g: &Graph) -> Result<()> {
    let depth = spec["depth"].as_u64().unwrap_or(0) as usize;
    #[cfg(feature = "sparse-cells")]
    if depth > 0 {
        return Err(
            "strict direct Spine lookup currently requires the ordinary published cursor map"
                .into(),
        );
    }
    if depth > 2 {
        return Err("strict depth exceeds two".into());
    }
    let library = spec
        .get("library")
        .map(|v| serde_json::from_value::<BTreeSet<Vec<E>>>(v.clone()).map_err(|e| e.to_string()))
        .transpose()?;
    let mut s = State {
        depth,
        library,
        extend: spec["explore_second"] == true,
        fault: spec["wrong_port"] == true,
        ..Default::default()
    };
    if let Some(lib) = &s.library
        && lib.iter().any(|p| {
            p.is_empty()
                || p.len() > depth
                || p.len() == 2 && (p[0][2] != p[1][0] || !lib.contains(&vec![p[0]]))
        })
    {
        return Err("unconnected strict template".into());
    }
    if depth != 0 {
        for (rid, r) in g.program.rules.iter().enumerate() {
            if !r.seminaive || r.query.len() != 1 {
                continue;
            }
            let a = &r.query[0];
            let Call::Table(t) = a.call else { continue };
            let mut slots = BTreeSet::new();
            if !g.program.tables[t].constructor
                || !a
                    .args
                    .iter()
                    .all(|v| matches!(v,Arg::Slot(s) if slots.insert(*s)))
                || !r.inputs.iter().all(|v| slots.contains(v))
            {
                continue;
            }
            s.targets.entry(t).or_default().push(rid);
            s.child_table.insert(rid, t);
        }
        for (rid, r) in g.program.rules.iter().enumerate() {
            for (op, ins) in g.program.templates[r.template].ops.iter().enumerate() {
                let crate::program::Op::Let(_, Call::Table(t), _) = ins else {
                    continue;
                };
                if let Some(children) = s.targets.get(t) {
                    for &c in children {
                        s.next_at.entry((rid, op, *t)).or_default().push(c);
                        let key = vec![[rid, op, c]];
                        if s.library.as_ref().is_none_or(|lib| lib.contains(&key)) {
                            s.programs.entry(rid).or_default().push(key)
                        }
                    }
                }
            }
        }
    }
    S.with_borrow_mut(|v| *v = (depth != 0).then_some(s));
    Ok(())
}
pub(crate) fn run(n: usize) {
    S.with_borrow_mut(|s| {
        if let Some(s) = s {
            if s.run != n {
                s.closed_rules.clear();
            }
            s.run = n
        }
    })
}
pub(crate) fn tag(rid: usize, template: usize, n: usize) -> usize {
    assert!(template <= u32::MAX as usize);
    S.with_borrow_mut(|s| {
        if let Some(s) = s
            && s.programs.contains_key(&rid)
        {
            s.stats.tagged += n as u64;
            template | ((rid + 1) << 32)
        } else {
            template
        }
    })
}
pub(crate) fn begin(serial: u64, rid: usize, named: bool, code: usize) -> Result<()> {
    S.with_borrow_mut(|v| {
        let Some(s) = v else {
            if code != 0 {
                return Err("unexpected strict variant".into());
            }
            return Ok(());
        };
        s.active = None;
        s.physical = None;
        if let Some(internal) = s.issued.remove(&serial) {
            s.stats.source_commits += 1;
            s.routes.get_mut(&internal.path).unwrap()[2] += 1;
            if internal.path.len() == 2 {
                s.stats.two_with_internal_parent += 1;
            }
            if internal.path.len() < s.depth {
                s.active = Some(Permit {
                    root: internal.root,
                    rule: rid,
                    prior: internal.path,
                    run: s.run,
                })
            }
        } else if code != 0 {
            if code != rid + 1 || !s.programs.contains_key(&rid) {
                return Err("invalid strict variant selector".into());
            }
            if !named {
                s.stats.no_named_input += 1;
                return Ok(());
            }
            s.stats.external_roots += 1;
            assert!(s.known.insert(serial));
            s.active = Some(Permit {
                root: serial,
                rule: rid,
                prior: vec![],
                run: s.run,
            });
        }
        Ok(())
    })
}
pub(crate) fn fresh(id: u32) {
    S.with_borrow_mut(|s| {
        if let Some(s) = s
            && s.active.is_some()
        {
            s.physical = Some(id);
            s.stats.selected_primary += 1;
        }
    })
}
pub(crate) fn end() {
    S.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.active = None;
            s.physical = None;
        }
    })
}
pub(crate) fn output(f: FactRef, t: usize, epoch: u64) {
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return };
        if s.physical != Some(f.cell) {
            return;
        }
        let Some(a) = &s.active else { return };
        let Some(children) = s.next_at.get(&(a.rule, f.op as usize, t)) else {
            return;
        };
        s.stats.actual_output_events += 1;
        for &rid in children {
            let mut path = a.prior.clone();
            path.push([a.rule, f.op as usize, rid]);
            if path.len() > s.depth
                || !(s.extend && path.len() == 2)
                    && s.library.as_ref().is_some_and(|lib| !lib.contains(&path))
            {
                continue;
            }
            let owner = Owner {
                path: path.clone(),
                root: a.root,
                born: a.run,
                version: epoch,
            };
            let w = Dependency::Fact(f);
            if s.ports.entry(rid).or_default().insert(w, owner).is_some() {
                panic!("repeat native constructor registration")
            }
            s.stats.named_ports += 1;
            s.routes.entry(path).or_default()[0] += 1;
        }
    })
}
pub(crate) fn open(g: &Graph, rid: usize, wm: u64) -> Result<Option<Vec<(Dependency, u64)>>> {
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return Ok(None) };
        let Some(&t) = s.child_table.get(&rid) else {
            return Ok(None);
        };
        s.stats.tries += 1;
        let Some(ports) = s.ports.get(&rid) else {
            s.stats.absent += 1;
            return Ok(None);
        };
        let n = g.witness_count(t);
        let entry = s.availability.entry(rid).or_default();
        entry[0] += 1;
        entry[1] = entry[1].max(ports.len() as u64);
        entry[2] = entry[2].max(n as u64);
        if n == 0 || ports.len() < n {
            entry[3] += 1;
            s.stats.uncovered += 1;
            return Ok(None);
        }
        let rule = &g.program.rules[rid];
        let atom = &rule.query[0];
        let mut live = 0;
        let mut ready = vec![];
        for (&w, o) in ports {
            s.stats.explicit_addresses += 1;
            if o.born >= s.run || !g.strict_member(t, w) {
                continue;
            }
            let Some(row) = g.row(w)? else { continue };
            if row.hidden || row.table != t || row.witness != w || row.epoch != o.version {
                s.stats.changed += 1;
                continue;
            }
            live += 1;
            if row.epoch < wm {
                s.stats.stale += 1;
                continue;
            }
            let mut input = Slots::default();
            for &slot in rule.inputs.iter() {
                let c = atom
                    .args
                    .iter()
                    .position(|x| matches!(x,Arg::Slot(s)if *s==slot))
                    .ok_or("missing signed field")?;
                input.insert(
                    slot,
                    row.values
                        .get(c)
                        .ok_or("missing signed output field")?
                        .clone(),
                );
                s.stats.local_field_reads += 1;
            }
            ready.push((w, row.epoch, input, o));
        }
        if live != n || ready.is_empty() {
            entry[4] += 1;
            s.stats.uncovered += 1;
            return Ok(None);
        }
        entry[5] += 1;
        let mut headers = vec![];
        for (w, epoch, slots, o) in ready {
            let Dependency::Fact(mut physical) = w else {
                return Err("strict child lacked constructor port".into());
            };
            if s.fault {
                physical.op ^= 1
            }
            let expected = o.path.last().ok_or("empty strict continuation")?;
            if expected[1] != physical.op as usize
                || expected[2] != rid
                || !s.known.contains(&o.root)
            {
                return Err("strict named return port corruption".into());
            }
            crate::integral_packets::release(
                s.run,
                rid,
                0,
                w,
                epoch,
                epoch,
                &slots,
                &[(0, w)],
                o.root,
            );
            headers.push((w, epoch));
            s.emitting.insert((rid, w), o.clone());
            s.stats.released += 1;
            s.routes.get_mut(&o.path).unwrap()[1] += 1;
        }
        s.stats.complete_banks += 1;
        s.closed_rules.insert(rid);
        Ok(Some(headers))
    })
}
pub(crate) fn link(serial: u64, root: u64, rid: usize, w: Dependency) -> Result<()> {
    S.with_borrow_mut(|v| {
        let s = v.as_mut().ok_or("strict owner missing")?;
        let owner = s.emitting.remove(&(rid, w)).ok_or("unissued strict port")?;
        if owner.root != root || !s.known.contains(&root) || owner.born >= s.run {
            return Err("invalid signed parent provenance".into());
        }
        assert!(s.issued.insert(serial, owner).is_none());
        s.stats.actual_internal += 1;
        Ok(())
    })
}
pub fn report() -> J {
    S.with_borrow(|v|v.as_ref().map_or(J::Null,|s|json!({"availability":s.availability,"counts":s.stats,"routes":s.routes.iter().map(|(p,r)|(p,r)).collect::<Vec<_>>(),"uncommitted":s.issued.len()})))
}

pub(crate) fn closed(rid: usize) -> bool {
    S.with_borrow(|s| s.as_ref().is_some_and(|s| s.closed_rules.contains(&rid)))
}
pub(crate) fn source_work(n: usize, audit: bool) {
    S.with_borrow_mut(|s| {
        if let Some(s) = s {
            if audit {
                s.stats.audit_score_inputs += n as u64
            } else {
                s.stats.no_score_banks += 1;
                s.stats.no_score_inputs += n as u64
            }
        }
    })
}
pub(crate) fn spine_point() {
    S.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.stats.direct_spine_lookups += 1
        }
    })
}
