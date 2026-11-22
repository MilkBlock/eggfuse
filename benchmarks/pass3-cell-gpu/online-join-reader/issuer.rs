// Typed token memory belongs to the issuer; the receiver still accepts only named packets.
use crate::{
    graph::{Dependency, Graph},
    named_only::{Inbox, Packet},
    program::{Arg, Call, Result},
    value::Value,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{cell::RefCell, collections::BTreeMap, rc::Rc};

#[derive(Deserialize)]
pub struct Model {
    left: [bool; 4],
    sender: [[bool; 2]; 4],
    follow: [[bool; 4]; 2],
}
#[derive(Default, Serialize)]
pub struct Counts {
    reads: u64,
    encoded_fields: u64,
    first_scores: u64,
    second_scores: u64,
    issued: u64,
    abstained: u64,
    denied_budget: u64,
    rule_calls: u64,
}
#[derive(Clone, Copy, PartialEq, Eq)]
struct Code([u8; 20]);
impl Code {
    fn of(v: &Value) -> Result<Self> {
        let data = serde_json::to_vec(v).map_err(|e| e.to_string())?;
        let h = Sha256::digest(data);
        let mut b = [0; 20];
        b.copy_from_slice(&h[..20]);
        Ok(Self(b))
    }
    fn matches(self, b: Self) -> bool {
        self.0[4..] == b.0[4..]
    }
}
struct Token {
    address: Dependency,
    epoch: u64,
    fields: Vec<Code>,
}
struct Read {
    table: usize,
    checks: Vec<(usize, usize)>,
    literals: Vec<(usize, Code)>,
    repeats: Vec<(usize, usize)>,
    exports: Vec<(usize, usize)>,
    index: usize,
}
struct Layout {
    reads: Vec<Read>,
    slots: usize,
}
fn layout(rule: &crate::program::Rule) -> Result<Option<Layout>> {
    let mut atoms = vec![];
    for atom in rule.query.iter() {
        if let Call::Table(t) = atom.call {
            atoms.push((atoms.len(), t, &atom.args));
        }
    }
    let mut seen = BTreeMap::new();
    let mut reads = vec![];
    while !atoms.is_empty() {
        let rank = |args: &Vec<Arg>| {
            args.iter()
                .filter(|a| matches!(a,Arg::Slot(s) if seen.contains_key(s)))
                .count()
        };
        let i = if reads.is_empty() {
            atoms
                .iter()
                .position(|(_, _, args)| args.len() > 1)
                .unwrap_or(0)
        } else {
            let i = (0..atoms.len())
                .max_by_key(|&i| (rank(atoms[i].2), usize::MAX - i))
                .unwrap();
            if rank(atoms[i].2) != 0 {
                i
            } else if let Some(unit) = atoms.iter().position(|(_, _, args)| args.len() == 1) {
                // A nullary constructor/function has exactly one possible key.
                // The packet still names its actual versioned result.
                unit
            } else {
                return Ok(None);
            }
        };
        let (index, table, args) = atoms.remove(i);
        let mut read = Read {
            table,
            index,
            checks: vec![],
            repeats: vec![],
            literals: vec![],
            exports: vec![],
        };
        let mut local = BTreeMap::new();
        for (col, a) in args.iter().enumerate() {
            match a {
                Arg::Literal(Value::Eq(_)) => return Ok(None), // A changing canonical literal needs a runtime projection.
                Arg::Literal(v) => read.literals.push((col, Code::of(v)?)),
                Arg::Slot(s) => {
                    if let Some(&slot) = seen.get(s) {
                        read.checks.push((col, slot));
                    } else if let Some(&first) = local.get(s) {
                        read.repeats.push((col, first));
                    } else {
                        local.insert(*s, col);
                    }
                }
            }
        }
        for (s, col) in local {
            let n = seen.len();
            seen.insert(s, n);
            read.exports.push((col, n));
        }
        reads.push(read);
    }
    Ok(Some(Layout {
        reads,
        slots: seen.len(),
    }))
}
struct Issuer {
    model: Model,
    plans: Vec<Option<Layout>>,
    bank: BTreeMap<usize, Rc<Vec<Token>>>,
    run: usize,
    counts: Counts,
    cap: u64,
}
thread_local! {static ACTIVE:RefCell<Option<Issuer>>=const{RefCell::new(None)};}
pub fn init(g: &Graph, model: Model, cap: u64) -> Result<()> {
    let plans = g.program.rules.iter().map(layout).collect::<Result<_>>()?;
    ACTIVE.replace(Some(Issuer {
        model,
        plans,
        bank: BTreeMap::new(),
        run: 0,
        counts: Counts::default(),
        cap,
    }));
    Ok(())
}
pub fn finish() -> Counts {
    ACTIVE.take().unwrap().counts
}

pub fn submit(g: &Graph, run: usize, rid: usize, wm: u64, inbox: &mut Inbox) -> Result<()> {
    ACTIVE.with_borrow_mut(|active| {
        let a = active.as_mut().ok_or("missing issuer")?;
        a.counts.rule_calls += 1;
        if a.run != run {
            a.bank.clear();
            a.run = run;
        }
        let Some(plan) = &a.plans[rid] else {
            a.counts.abstained += 1;
            return Ok(());
        };
        let mut memory = vec![];
        for read in &plan.reads {
            if !a.bank.contains_key(&read.table) {
                let mut tokens = vec![];
                for address in g.witnesses(read.table) {
                    a.counts.reads += 1;
                    if let Some(row) = g.row(address)?
                        && !row.hidden
                    {
                        let fields = row
                            .values
                            .iter()
                            .map(Code::of)
                            .collect::<Result<Vec<_>>>()?;
                        a.counts.encoded_fields += fields.len() as u64;
                        tokens.push(Token {
                            address,
                            epoch: row.epoch,
                            fields,
                        });
                    }
                }
                a.bank.insert(read.table, Rc::new(tokens));
            }
            memory.push(a.bank[&read.table].clone());
        }
        if memory.iter().any(|m| m.is_empty()) {
            return Ok(());
        }
        let mut summary = [[[false; 2]; 32]; 4];
        let shared = if memory.len() >= 2 && !plan.reads[1].checks.is_empty() {
            let (col, slot) = plan.reads[1].checks[0];
            let first = plan.reads[0]
                .exports
                .iter()
                .find(|(_, s)| *s == slot)
                .unwrap()
                .0;
            for row in memory[1].iter() {
                let fresh = usize::from(
                    !g.program.rules[rid].seminaive || row.epoch >= wm || memory.len() > 2,
                );
                let code = row.fields[col];
                for (k, plane) in summary.iter_mut().enumerate() {
                    let entry = &mut plane[usize::from(code.0[k] % 32)];
                    for (v, learned) in entry.iter_mut().zip(a.model.sender[2 + fresh]) {
                        *v |= learned;
                    }
                }
            }
            Some(first)
        } else {
            None
        };
        // Visit every typed port for each conditional read. No keyed join list.
        let mut stack = vec![(
            Vec::<(usize, Dependency, u64)>::new(),
            vec![Code([0; 20]); plan.slots],
            false,
        )];
        let mut budget = a.cap;
        while let Some((parents, slots, fresh)) = stack.pop() {
            let step = parents.len();
            if step == memory.len() {
                if fresh || parents.is_empty() || !g.program.rules[rid].seminaive {
                    let mut ordered = parents;
                    ordered.sort_unstable_by_key(|p| p.0);
                    inbox.submit(Packet::issue(
                        run,
                        rid,
                        ordered.into_iter().map(|(_, w, e)| (w, e)).collect(),
                    ));
                    a.counts.issued += 1;
                }
                continue;
            }
            let read = &plan.reads[step];
            for row in memory[step].iter().rev() {
                if budget == 0 {
                    a.counts.denied_budget += 1;
                    return Ok(());
                }
                budget -= 1;
                let current = usize::from(!g.program.rules[rid].seminaive || row.epoch >= wm);
                if step == 0 {
                    a.counts.first_scores += 1;
                    if !a.model.left[current] {
                        continue;
                    }
                    if let Some(col) = shared {
                        let ch = usize::from(current == 0 && memory.len() == 2);
                        if !summary
                            .iter()
                            .enumerate()
                            .all(|(k, p)| p[usize::from(row.fields[col].0[k] % 32)][ch])
                        {
                            continue;
                        }
                    }
                } else {
                    a.counts.second_scores += 1;
                    let intermediate = step + 1 < memory.len();
                    if !a.model.follow[usize::from(fresh || intermediate)][2 + current]
                        || read
                            .checks
                            .iter()
                            .any(|&(col, slot)| !row.fields[col].matches(slots[slot]))
                    {
                        continue;
                    }
                }
                if read
                    .literals
                    .iter()
                    .any(|&(c, v)| !row.fields[c].matches(v))
                    || read
                        .repeats
                        .iter()
                        .any(|&(c, b)| !row.fields[c].matches(row.fields[b]))
                {
                    continue;
                }
                let mut next = parents.clone();
                next.push((read.index, row.address, row.epoch));
                let mut bound = slots.clone();
                for &(c, s) in &read.exports {
                    bound[s] = row.fields[c];
                }
                stack.push((next, bound, fresh || current == 1));
            }
        }
        Ok(())
    })
}
