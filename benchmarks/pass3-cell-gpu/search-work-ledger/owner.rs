// For each two-parent LHS, compile the unique second operation whose shared
// operands have exactly the same symbolic source in the first parent's template.
type OwnerPorts = HashMap<(usize, u32, usize), u32>;
fn owner_ports(program: &Program, plans: &[Option<Plan>]) -> OwnerPorts {
    use crate::program::Op;
    let mut pairs = HashMap::new();
    for (rid, plan) in plans.iter().enumerate() {
        let Some(p) = plan else { continue };
        if p.ins.iter().filter(|s| s.1 == 1).count() != 2 {
            continue;
        }
        let query = &program.rules[rid].query;
        let (a, b) = (&query[p.ins[0].0], &query[p.ins[1].0]);
        let (Call::Table(left), Call::Table(right)) = (&a.call, &b.call) else {
            continue;
        };
        let mut shared = Vec::new();
        for (i, l) in a.args.iter().enumerate() {
            for (j, r) in b.args.iter().enumerate() {
                if matches!(l, Arg::Slot(_)) && l == r {
                    shared.push((i, j));
                }
            }
        }
        if !shared.is_empty() {
            pairs
                .entry(*left)
                .or_insert_with(Vec::new)
                .push((*right, rid, shared));
        }
    }
    let mut routes = HashMap::new();
    for (tid, t) in program.templates.iter().enumerate() {
        let mut ports: HashMap<usize, Vec<(u32, Vec<Arg>)>> = HashMap::new();
        for (i, op) in t.ops.iter().enumerate() {
            let (table, mut fields, out) = match op {
                Op::Let(slot, Call::Table(table), fields) => {
                    (*table, fields.clone(), Arg::Slot(*slot))
                }
                Op::Set(table, fields, out) => (*table, fields.clone(), out.clone()),
                _ => continue,
            };
            if !program.tables[table].constructor {
                continue;
            }
            fields.push(out);
            ports.entry(table).or_default().push((i as u32, fields));
        }
        for (table, ports_left) in &ports {
            let Some(targets) = pairs.get(table) else {
                continue;
            };
            for (right, rid, shared) in targets {
                let Some(ports_right) = ports.get(right) else {
                    continue;
                };
                for (left_op, left) in ports_left {
                    let mut eligible = ports_right
                        .iter()
                        .filter(|(_, r)| shared.iter().all(|&(i, j)| left[i] == r[j]));
                    if let Some((other, _)) = eligible.next()
                        && eligible.next().is_none()
                    {
                        routes.insert((tid, *left_op, *rid), *other);
                    }
                }
            }
        }
    }
    routes
}
