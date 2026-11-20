// Source-only functional-dependency lowering. Integers here are compiler slot
// identities, not e-class addresses or observed successful RHS bindings.
use std::collections::{BTreeSet as SlotSet, HashSet, VecDeque};

struct StaticAtom {
    keys: SlotSet<usize>,
    fields: SlotSet<usize>,
    relation: bool,
}

fn slot_set(args: &[Arg]) -> SlotSet<usize> {
    args.iter()
        .filter_map(|a| match a {
            Arg::Slot(i) => Some(*i),
            Arg::Literal(_) => None,
        })
        .collect()
}

fn project_closure(atoms: &[StaticAtom], bound: &mut SlotSet<usize>) {
    loop {
        let before = bound.len();
        for atom in atoms {
            if atom.keys.is_subset(bound) {
                bound.extend(&atom.fields);
            }
        }
        if bound.len() == before {
            return;
        }
    }
}

fn independent_width(atoms: &[StaticAtom]) -> Result<usize> {
    let goal: SlotSet<_> = atoms
        .iter()
        .flat_map(|a| a.fields.iter().copied())
        .collect();
    let mut start = SlotSet::new();
    project_closure(atoms, &mut start);
    let mut seen = HashSet::from([start.clone()]);
    let mut queue = VecDeque::from([(start, 0)]);
    while let Some((bound, width)) = queue.pop_front() {
        if bound == goal {
            return Ok(width);
        }
        for atom in atoms
            .iter()
            .filter(|a| a.relation && !a.fields.is_subset(&bound))
        {
            let mut next = bound.clone();
            next.extend(&atom.fields);
            project_closure(atoms, &mut next);
            if seen.insert(next.clone()) {
                queue.push_back((next, width + 1));
            }
        }
    }
    Err("source rule has an unbound primitive operand".into())
}

#[derive(Serialize)]
struct SealedPlan {
    width: usize,
    ins: Vec<(usize, usize, Vec<usize>)>,
    linked: Vec<usize>,
}

fn sealed_source_plan(rule: &Rule) -> Result<Option<SealedPlan>> {
    let mut atoms = Vec::with_capacity(rule.query.len());
    for a in rule.query.iter() {
        let (_, keys) = a
            .args
            .split_last()
            .ok_or("source atom has no result port")?;
        atoms.push(StaticAtom {
            keys: slot_set(keys),
            fields: slot_set(&a.args),
            relation: matches!(a.call, Call::Table(_)),
        });
    }
    let width = independent_width(&atoms)?;
    if width < 2 {
        return Ok(None);
    }
    let mut seen = HashSet::new();
    let mut queue = VecDeque::new();
    for (i, atom) in atoms.iter().enumerate().filter(|(_, a)| a.relation) {
        seen.insert(atom.fields.clone());
        queue.push_back((atom.fields.clone(), vec![i]));
    }
    while let Some((bound, path)) = queue.pop_front() {
        let mut closure = bound.clone();
        let mut done = vec![false; atoms.len()];
        let mut suffix = vec![];
        for &atom in &path {
            done[atom] = true;
        }
        loop {
            let before = suffix.len();
            for (i, a) in atoms.iter().enumerate() {
                if !done[i] && a.keys.is_subset(&closure) {
                    done[i] = true;
                    suffix.push((i, 0, vec![]));
                    closure.extend(&a.fields);
                }
            }
            if before == suffix.len() {
                break;
            }
        }
        if done.iter().all(|v| *v) {
            let mut slots: SlotSet<usize> = SlotSet::new();
            let mut ins = vec![];
            let mut linked = vec![];
            for atom in path {
                let cols = rule.query[atom]
                    .args
                    .iter()
                    .enumerate()
                    .filter_map(|(i, x)| match x {
                        Arg::Slot(v) if slots.contains(v) => Some(i),
                        _ => None,
                    })
                    .collect::<Vec<_>>();
                linked.push(cols.len());
                ins.push((atom, 1, cols));
                slots.extend(&atoms[atom].fields);
            }
            if linked.len() < width || linked.iter().skip(1).any(|n| *n == 0) {
                return Err("disconnected sealed source plan".into());
            }
            ins.extend(suffix);
            return Ok(Some(SealedPlan { width, ins, linked }));
        }
        for (i, a) in atoms.iter().enumerate() {
            if !a.relation || a.fields.is_disjoint(&bound) || a.fields.is_subset(&bound) {
                continue;
            }
            let mut next = bound.clone();
            next.extend(&a.fields);
            if seen.insert(next.clone()) {
                let mut sequence = path.clone();
                sequence.push(i);
                queue.push_back((next, sequence));
            }
        }
    }
    Ok(None)
}

pub fn compile_sealed_plans(program: &Program) -> Result<Vec<u8>> {
    let mut plans = Vec::with_capacity(program.rules.len());
    for (rid, r) in program.rules.iter().enumerate() {
        plans.push(sealed_source_plan(r).map_err(|e| format!("sealed source rule {rid}: {e}"))?);
    }
    let mut data = serde_json::to_vec(&plans).map_err(|e| e.to_string())?;
    data.push(b'\n');
    Ok(data)
}

#[cfg(test)]
mod native_width_tests {
    use super::{StaticAtom, independent_width};

    fn source(inputs: &[usize], fields: &[usize], relation: bool) -> StaticAtom {
        StaticAtom {
            keys: inputs.iter().copied().collect(),
            fields: fields.iter().copied().collect(),
            relation,
        }
    }

    #[test]
    fn large_sparse_slots_do_not_turn_a_shared_result_into_an_inverse_key() {
        let keys: Vec<_> = (0..70).map(|i| i * 1024).collect();
        let mut outputs = keys.clone();
        outputs.push(100_001);
        let atoms = [
            source(&keys, &outputs, true),
            source(&[91_000], &[91_000, 100_001], true),
        ];
        assert_eq!(independent_width(&atoms).unwrap(), 2);
    }

    #[test]
    fn forward_closure_accepts_nullary_keys_and_rejects_unbound_scalar_inputs() {
        let atoms = [
            source(&[], &[8], true),
            source(&[8], &[8, 14], false),
            source(&[14], &[14, 20], true),
        ];
        assert_eq!(independent_width(&atoms).unwrap(), 0);
        assert!(independent_width(&[source(&[8], &[8, 14], false)]).is_err());
    }
}
