use crate::{
    graph::{Dependency, Graph},
    joint_root::Ref,
    program::{Arg, Call, Op, Program, Result},
    value::{Value, canon},
};
use serde::Serialize;
use serde_json::{Value as J, json};
use std::{cell::RefCell, rc::Rc};

#[derive(Clone, Debug, Serialize)]
struct Plan {
    old_atom: usize,
    old_result_slot: usize,
    old_table: usize,
    factory: usize,
    candidate_table: usize,
    effect: usize,
    constructor: usize,
    child_template: usize,
    required: Vec<usize>,
}
#[derive(Clone, Debug)]
pub(crate) struct Claim {
    sid: u64,
    rid: usize,
    epoch: u64,
    plan: Rc<Plan>,
    old: Dependency,
    version: u64,
    old_value: Option<Value>,
}
struct Active {
    claim: Claim,
    ordinal: usize,
    returned: Option<(u32, Dependency)>,
    armed: Option<(Value, Value, Dependency)>,
    entered: bool,
}
#[derive(Default, Serialize)]
struct Counts {
    scope_candidates: u64,
    tagged: u64,
    missing_named: u64,
    tag_bytes: usize,
    activated: u64,
    returned: u64,
    no_return: u64,
    stale_old: u64,
    changed_old_value: u64,
    armed: u64,
    entered: u64,
    noop: u64,
    interned: u64,
    fresh: u64,
    old_direct_reads: u64,
    candidate_direct_reads: u64,
}
#[derive(Default)]
struct Store {
    mode: u8,
    audit: bool,
    plans: Vec<Option<Rc<Plan>>>,
    active: Option<Active>,
    stats: Counts,
    events: Vec<J>,
}
thread_local! {static STORE:RefCell<Store>=RefCell::new(Store::default());}

pub fn configure(p: &Program, mode: u8, audit: bool) -> Result<()> {
    if mode > 3 {
        return Err("invalid strict merge mode".into());
    }
    let mut plans = Vec::new();
    for rule in &p.rules {
        let ops = &p.templates[rule.template].ops;
        let mut found = Vec::new();
        for (effect, op) in ops.iter().enumerate() {
            let Op::Set(table, key, Arg::Slot(value)) = op else {
                continue;
            };
            let m = &p.tables[*table].merge;
            if m["args"] != json!([{"var":"old"},{"var":"new"}]) {
                continue;
            }
            let Some(name) = m["call"]["table"].as_str() else {
                continue;
            };
            let Some(ctor) = p
                .tables
                .iter()
                .position(|t| t.name == name && t.constructor && t.schema.len() == 3)
            else {
                continue;
            };
            let Some((factory, new_table)) =
                ops[..effect]
                    .iter()
                    .enumerate()
                    .find_map(|(i, instr)| match instr {
                        Op::Let(dst, Call::Table(t), _)
                            if dst == value && p.tables[*t].constructor =>
                        {
                            Some((i, *t))
                        }
                        _ => None,
                    })
            else {
                continue;
            };
            if factory + 1 != effect {
                continue;
            }
            let old_slots: Vec<_> = rule
                .query
                .iter()
                .enumerate()
                .filter_map(|(i, atom)| {
                    (matches!(atom.call,Call::Table(t) if t==*table)
                        && atom.args.split_last().is_some_and(|(_, keys)| keys == key))
                    .then_some(i)
                })
                .collect();
            if let [old_atom] = old_slots.as_slice() {
                let Some(Arg::Slot(old_result_slot)) = rule.query[*old_atom].args.last() else {
                    continue;
                };
                let required = rule
                    .query
                    .iter()
                    .enumerate()
                    .filter_map(|(i, a)| matches!(a.call, Call::Table(_)).then_some(i))
                    .collect();
                found.push(Plan {
                    old_atom: *old_atom,
                    old_result_slot: *old_result_slot,
                    old_table: *table,
                    factory,
                    candidate_table: new_table,
                    effect,
                    constructor: ctor,
                    child_template: p.table_templates[ctor],
                    required,
                });
            }
        }
        plans.push(if found.len() == 1 {
            Some(Rc::new(found.remove(0)))
        } else {
            None
        });
    }
    STORE.with_borrow_mut(|s| {
        *s = Store {
            mode,
            audit,
            plans,
            ..Default::default()
        }
    });
    Ok(())
}
#[derive(Debug)]
pub(crate) struct IssuedPage {
    tags: Vec<u8>,
    plan: Rc<Plan>,
    rid: usize,
    epoch: u64,
    first: u64,
    mode: u8,
}
impl IssuedPage {
    // The only variable-length wire field is the tag bitmap. Read the named
    // address and version from the parent recipe's already issued tuple.
    pub(crate) fn get(&self, i: usize, tuple: &[Ref]) -> Option<Claim> {
        if self.tags[i / 8] & (1 << (i % 8)) == 0 {
            return None;
        }
        let old = tuple
            .iter()
            .find(|r| r.atom == self.plan.old_atom)
            .expect("missing explicitly named old atom");
        let Dependency::Function(id) = old.row else {
            unreachable!("typed merge parent")
        };
        Some(Claim {
            sid: self.first + i as u64,
            rid: self.rid,
            epoch: self.epoch,
            plan: self.plan.clone(),
            old: Dependency::Function(if self.mode == 2 { id ^ 1 } else { id }),
            version: if self.mode == 3 {
                old.version.wrapping_add(1)
            } else {
                old.version
            },
            old_value: None,
        })
    }
}
pub(crate) fn issue_page(
    rid: usize,
    epoch: u64,
    first: u64,
    width: usize,
    refs: &[Ref],
) -> Option<IssuedPage> {
    STORE.with_borrow_mut(|s| {
        if s.mode == 0 {
            return None;
        }
        let p = s.plans.get(rid)?.clone()?;
        let mut tags = vec![0u8; (refs.len() / width).div_ceil(8)];
        for (i, tuple) in refs.chunks_exact(width).enumerate() {
            s.stats.scope_candidates += 1;
            if p.required
                .iter()
                .all(|a| tuple.iter().any(|r| r.atom == *a))
                && tuple
                    .iter()
                    .any(|r| r.atom == p.old_atom && matches!(r.row, Dependency::Function(_)))
            {
                s.stats.tagged += 1;
                tags[i / 8] |= 1 << (i % 8);
            } else {
                s.stats.missing_named += 1;
            }
        }
        s.stats.tag_bytes += tags.len();
        Some(IssuedPage {
            tags,
            plan: p,
            rid,
            epoch,
            first,
            mode: s.mode,
        })
    })
}
pub(crate) fn seal(claim: Option<Claim>, verified: &crate::slots::Slots) -> Result<Option<Claim>> {
    let Some(mut c) = claim else { return Ok(None) };
    c.old_value = Some(
        verified
            .get(&c.plan.old_result_slot)
            .ok_or("missing old result in verified root slots")?
            .clone(),
    );
    Ok(Some(c))
}
pub(crate) fn activate(
    claim: Option<&Claim>,
    rid: usize,
    epoch: u64,
    serial: u64,
    ord: usize,
    refs: &[Ref],
) -> Result<()> {
    STORE.with_borrow_mut(|s| {
        assert!(s.active.is_none());
        if let Some(c) = claim {
            if c.sid != serial
                || c.rid != rid
                || c.epoch != epoch
                || !refs
                    .iter()
                    .any(|r| r.atom == c.plan.old_atom && r.row == c.old && r.version == c.version)
            {
                return Err("strict merge old reference differs from issued root".into());
            }
            s.stats.activated += 1;
            s.active = Some(Active {
                claim: c.clone(),
                ordinal: ord,
                returned: None,
                armed: None,
                entered: false,
            });
        }
        Ok(())
    })
}
pub(crate) fn returned(cell: u32, op: usize, t: usize, w: Dependency) {
    STORE.with_borrow_mut(|s| {
        if let Some(a) = s.active.as_mut()
            && a.claim.plan.factory == op
            && a.claim.plan.candidate_table == t
        {
            assert!(a.returned.replace((cell, w)).is_none());
            s.stats.returned += 1;
        }
    });
}
pub(crate) fn returned_handoff(cell: u32, op: usize, w: Dependency) {
    STORE.with_borrow_mut(|s| {
        if let Some(a) = s.active.as_mut()
            && a.claim.plan.factory == op
        {
            assert!(a.returned.replace((cell, w)).is_none());
            s.stats.returned += 1;
        }
    });
}
pub(crate) fn arm(
    g: &Graph,
    cell: u32,
    op: usize,
    t: usize,
    key: &[Value],
    candidate: &Value,
) -> Result<bool> {
    STORE.with_borrow_mut(|s| {
        let Some(a) = s.active.as_mut() else {
            return Ok(false);
        };
        let p = &a.claim.plan;
        if p.effect != op || t != p.old_table {
            return Ok(false);
        }
        let Some((producer, returned)) = a.returned else {
            s.stats.no_return += 1;
            return Ok(false);
        };
        if producer != cell {
            return Err("strict merge factory belonged to another Cell".into());
        }
        s.stats.old_direct_reads += 1;
        let Some(row) = g.row(a.claim.old)?.filter(|r| {
            r.table == t
                && !r.hidden
                && r.epoch == a.claim.version
                && r.values.split_last().is_some_and(|(_, inputs)| {
                    inputs
                        .iter()
                        .map(|v| canon(v, &g.parents))
                        .eq(key.iter().cloned())
                })
        }) else {
            s.stats.stale_old += 1;
            return Ok(false);
        };
        s.stats.candidate_direct_reads += 1;
        let c = g
            .row(returned)?
            .ok_or("strict returned constructor no longer live")?;
        if c.hidden
            || c.table != p.candidate_table
            || c.values.last().map(|v| canon(v, &g.parents)).as_ref() != Some(candidate)
        {
            return Err("strict merge candidate ref/value mismatch".into());
        }
        let old = canon(row.values.last().ok_or("empty old row")?, &g.parents);
        if a.claim
            .old_value
            .as_ref()
            .map(|v| canon(v, &g.parents))
            .as_ref()
            != Some(&old)
        {
            s.stats.changed_old_value += 1;
            return Ok(false);
        }
        a.armed = Some((old, candidate.clone(), returned));
        s.stats.armed += 1;
        Ok(true)
    })
}
pub(crate) fn take(t: usize, key: &[Value]) -> Result<Option<usize>> {
    STORE.with_borrow_mut(|s| {
        let Some(a) = s.active.as_mut() else {
            return Ok(None);
        };
        let Some((old, new, _)) = &a.armed else {
            return Ok(None);
        };
        if t != a.claim.plan.constructor || key != [old.clone(), new.clone()] || a.entered {
            return Err("strict merge constructor operands differ".into());
        }
        a.entered = true;
        s.stats.entered += 1;
        Ok(Some(a.claim.plan.child_template))
    })
}
pub(crate) fn complete(w: Dependency, fresh: bool) {
    STORE.with_borrow_mut(|s| {
        let a = s.active.as_ref().unwrap();
        assert!(a.entered);
        if fresh {
            s.stats.fresh += 1
        } else {
            s.stats.interned += 1
        };
        if s.audit {
            s.events.push(json!([
                a.ordinal,
                a.claim.sid,
                a.claim.rid,
                a.claim.plan.effect,
                a.claim.old,
                a.claim.version,
                a.armed.as_ref().unwrap().2,
                a.claim.plan.constructor,
                w,
                fresh
            ]));
        }
    });
}
pub(crate) fn finish_effect() {
    STORE.with_borrow_mut(|s| {
        if let Some(a) = s.active.as_mut()
            && a.armed.take().is_some()
        {
            if !a.entered {
                s.stats.noop += 1;
            }
            a.entered = false;
        }
    });
}
pub(crate) fn end() {
    STORE.with_borrow_mut(|s| {
        s.active = None;
    });
}
pub fn report() -> J {
    STORE.with_borrow(|s|json!({"counts":s.stats,"plans":s.plans.iter().enumerate().filter_map(|(r,p)|p.as_ref().map(|x|json!([r,x.as_ref()]))).collect::<Vec<_>>(),"events":s.events}))
}
