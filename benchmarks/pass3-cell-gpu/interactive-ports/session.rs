// Interactive receiver for the three-Run, constructor-only family.
use eggfuse_cell_runtime::{
    executor::Executor,
    graph::{Dependency, FactRef, Graph},
    program::{Call, Op, Program},
    transfer_audit as audit,
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{BufRead, Write},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Issue {
    owner: u64,
    rule: usize,
    parents: Vec<(u64, usize, u64)>,
    compound: bool,
}

fn send(v: Value) -> Result<(), Box<dyn std::error::Error>> {
    println!("{v}");
    std::io::stdout().flush()?;
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args_os().nth(1).ok_or("expected program")?;
    let p = Program::parse(serde_json::from_slice(&std::fs::read(path)?)?)?;
    let stages = ["first", "advance", "finish"];
    let root = p.sets["first"][0];
    let mut effects = BTreeMap::new();
    for (rid, rule) in p.rules.iter().enumerate() {
        let mut output = None;
        for op in p.templates[rule.template].ops.iter() {
            match op {
                Op::Copy(_, _) => (),
                Op::Let(_, Call::Table(t), _) if p.tables[*t].constructor && output.is_none() => {
                    output = Some(*t)
                }
                _ => return Err("unsupported block effect".into()),
            }
        }
        effects.insert(rid, output.ok_or("missing constructor result")?);
    }
    // Bake the one internal wire only if its returned table is the consumer's sole atom.
    let consumers: Vec<_> = p.sets["advance"]
        .iter()
        .copied()
        .filter(|&rid| {
            let q = &p.rules[rid].query;
            q.len() == 1 && matches!(q[0].call,Call::Table(t) if t==effects[&root])
        })
        .collect();
    let [child] = consumers.as_slice() else {
        return Err("ambiguous block".into());
    };
    let template = p.rules[root].template;
    let op = p.templates[template]
        .ops
        .iter()
        .position(|op| matches!(op, Op::Let(_, Call::Table(_), _)))
        .ok_or("no result op")?;
    if !p
        .multi_stage
        .routes
        .contains_key(&(template, op, *child, 0))
    {
        return Err("missing compiled Bake route for internal child".into());
    }
    let mut current_owner = BTreeMap::new();
    let mut engine = Executor::new(Graph::new(p.clone())?, false);
    let mut ports = BTreeMap::new();
    let mut owners = BTreeSet::new();
    let mut initial = vec![];
    for (t, table) in p.tables.iter().enumerate() {
        // Ingress exposes every initial export once, before any decisions.
        for w in engine.graph.witnesses(t) {
            let row = engine.graph.row(w)?.ok_or("missing input")?;
            if !row.hidden {
                let id = owners.len() as u64 + 1;
                owners.insert(id);
                current_owner.insert(w, (id, 0));
                ports.insert((id, 0), (w, row.epoch));
                initial.push(json!([id, 0, row.epoch, table.name, &*row.values]));
            }
        }
    }
    send(
        json!({"initial":initial,"root":root,"child":child,"rules":effects.iter().map(|(r,t)|json!([r,p.tables[*t].name])).collect::<Vec<_>>() }),
    )?;
    let mut pending = None;
    let mut admitted = 0;
    let mut rejections = 0;
    let mut all_events = vec![];
    let mut lines = std::io::stdin().lock().lines();
    audit::set_active(true);
    audit::enable_write_audit();
    for (index, stage) in stages.iter().enumerate() {
        let run = index + 1;
        let issues: Vec<Issue> =
            serde_json::from_str(&lines.next().ok_or("missing Run proposals")??)?;
        let mut routes = BTreeMap::new();
        if let Some((owner, w, version)) = pending.take() {
            engine.issued.submit(serde_json::from_value(
                json!({"rule":child,"run":run,"parents":[[w,version]]}),
            )?);
            routes.insert(*child, (owner, 1, false));
            admitted += 1;
        }
        for a in issues {
            if !owners.insert(a.owner)
                || !p.sets[*stage].contains(&a.rule)
                || a.compound && a.rule != root
                || routes.contains_key(&a.rule)
            {
                rejections += 1;
                continue;
            }
            let refs: Option<Vec<_>> = a
                .parents
                .iter()
                .map(|&(id, slot, v)| {
                    ports
                        .get(&(id, slot))
                        .filter(|(_, epoch)| *epoch == v)
                        .copied()
                })
                .collect();
            let Some(refs) = refs else {
                rejections += 1;
                continue;
            };
            engine.issued.submit(serde_json::from_value(
                json!({"rule":a.rule,"run":run,"parents":refs}),
            )?);
            routes.insert(a.rule, (a.owner, 0, a.compound));
        }
        audit::enable_events();
        engine.execute_until(Some(run))?;
        if engine.steps.len() != run || engine.steps.last().unwrap().ruleset != *stage {
            return Err("unsupported schedule".into());
        }
        let events = audit::take_events()
            .ok_or("missing events")?
            .pop()
            .ok_or("missing run")?;
        let mut exports = vec![];
        let mut retired = vec![];
        for e in &events {
            let (w, src) = match e[0].as_str() {
                Some("birth") => {
                    let n = e[4].as_u64().ok_or("birth id")?;
                    (
                        Dependency::Fact(FactRef {
                            cell: (n >> 32) as u32,
                            op: n as u32,
                        }),
                        &e[5],
                    )
                }
                Some("returned") => (serde_json::from_value(e[2].clone())?, &e[3]),
                _ => continue,
            };
            let Some(rid) = src[1].as_u64().map(|n| n as usize) else {
                continue;
            };
            let &(owner, slot, compound) = routes.get(&rid).ok_or("unissued commit")?;
            let Some(row) = engine.graph.row(w)? else {
                continue;
            };
            if row.hidden || row.table != effects[&rid] {
                continue;
            }
            if let Some(old) = current_owner.insert(w, (owner, slot)) {
                ports.remove(&old);
                retired.push(old);
            }
            if ports.insert((owner, slot), (w, row.epoch)).is_some() {
                return Err("ambiguous export".into());
            }
            exports.push(json!([
                owner,
                slot,
                row.epoch,
                p.tables[row.table].name,
                &*row.values
            ]));
            if compound {
                pending = Some((owner, w, row.epoch));
            }
        }
        all_events.push(
            events
                .into_iter()
                .filter(|e| e[0] != "returned")
                .collect::<Vec<_>>(),
        );
        send(
            json!({"exports":exports,"retired":retired,"run":run,"reads":engine.issued.reads,"rejected":engine.issued.rejected+rejections}),
        )?;
    }
    engine.execute()?;
    if engine.steps.len() != 3 {
        return Err("extra source Runs".into());
    }
    audit::set_active(false);
    use sha2::{Digest, Sha256};
    let mut state = vec![];
    engine.graph.write_export(&mut state)?;
    send(
        json!({"internal":admitted,"state_sha":format!("{:x}",Sha256::digest(state)),
        "events":all_events,"rhs":audit::take_digests(),"writes":audit::take_write_digests(),"resumes":audit::take_resume_digests(),
        "schedule":engine.steps.iter().map(|s|json!([s.ruleset,s.epoch,s.path,s.iterations,s.executed_bindings,s.changed])).collect::<Vec<_>>() }),
    )
}
