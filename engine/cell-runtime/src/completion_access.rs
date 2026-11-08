//! Source-snapshot reads are mandatory before matching. RHS accesses and writes
//! become obligations only for rules that actually contribute bindings.
use super::*;

#[derive(Clone, Debug, Default, Serialize)]
pub struct Rule {
    pub query: Vec<usize>,
    pub rhs: Vec<usize>,
    pub accesses: Vec<usize>,
    /// Direct reads for a bound Copy/i64 arithmetic/Union/constructor-Set RHS.
    /// This classifies instructions only; concrete closure must still be proved.
    pub pure_writes: Option<Vec<usize>>,
}
impl Rule {
    pub fn derive(
        p: &Program,
        plan: &Plan,
        rid: usize,
        sorts: &[(BTreeSet<String>, bool)],
    ) -> Self {
        let rule = &p.rules[rid];
        let template = &p.templates[rule.template];
        let n = p.tables.len();
        let mut query = BTreeSet::new();
        let mut opaque_query = false;
        for atom in rule.query.iter() {
            if let Call::Table(t) = atom.call {
                query.insert(t);
            }
            for arg in &atom.args {
                opaque_query |= opaque_literal(arg);
                if let Arg::Slot(slot) = arg {
                    opaque_query |= eq_sorts(std::slice::from_ref(&template.sorts[*slot])).1;
                }
            }
        }
        if opaque_query {
            query.extend(0..n);
        }
        let mut rhs = BTreeSet::new();
        let mut opaque_rhs = eq_sorts(&template.sorts).1;
        let mut unions = BTreeSet::new();
        for op in template.ops.iter() {
            match op {
                Op::Union(a, b) => {
                    for arg in [a, b] {
                        if let Arg::Slot(slot) = arg {
                            let (names, unknown) =
                                eq_sorts(std::slice::from_ref(&template.sorts[*slot]));
                            unions.extend(names);
                            opaque_rhs |= unknown;
                        }
                    }
                }
                Op::Set(t, _, _) if p.tables[*t].constructor => {
                    let (names, unknown) =
                        eq_sorts(&p.tables[*t].schema[p.tables[*t].schema.len() - 1..]);
                    unions.extend(names);
                    opaque_rhs |= unknown;
                }
                _ => (),
            }
            opaque_rhs |= match op {
                Op::Copy(_, a) => opaque_literal(a),
                Op::Let(_, _, args) | Op::Hide(_, args, _) => args.iter().any(opaque_literal),
                Op::Set(_, args, v) => args.iter().any(opaque_literal) || opaque_literal(v),
                Op::Union(a, b) => opaque_literal(a) || opaque_literal(b),
                Op::Panic => false,
            };
            if let Op::Let(_, Call::Table(t), _) | Op::Set(t, _, _) | Op::Hide(t, _, _) = op {
                rhs.insert(*t);
                opaque_rhs |= plan.opaque_tables.contains(t);
                if matches!(op, Op::Set(..)) {
                    rhs.extend(&plan.completion_reads[*t]);
                    rhs.extend((0..n).filter(|&other| plan.affects(*t, other)));
                }
            }
        }
        let accesses = if opaque_rhs {
            (0..n).collect()
        } else {
            rhs.iter().copied().collect()
        };
        for (t, (names, unknown)) in sorts.iter().enumerate() {
            if !unions.is_empty() && (*unknown || !names.is_disjoint(&unions)) {
                rhs.extend(&plan.completion_reads[t]);
                rhs.extend((0..n).filter(|&other| plan.affects(t, other)));
            }
        }
        if opaque_rhs {
            rhs.extend(0..n);
        }
        Self {
            query: query.into_iter().collect(),
            rhs: rhs.into_iter().collect(),
            accesses,
            pure_writes: pure_writes(p, rid),
        }
    }
}

fn pure_writes(p: &Program, rid: usize) -> Option<Vec<usize>> {
    let t = &p.templates[p.rules[rid].template];
    let scalar = |a: &Arg| match a {
        Arg::Slot(s) => matches!(t.sorts[*s]["kind"].as_str(), Some("eq" | "i64")),
        Arg::Literal(Value::Int(_)) => true,
        _ => false,
    };
    let integer = |a: &Arg| match a {
        Arg::Slot(s) => t.sorts[*s]["kind"] == "i64",
        Arg::Literal(Value::Int(_)) => true,
        _ => false,
    };
    let mut writes = BTreeSet::new();
    for op in t.ops.iter() {
        match op {
            Op::Copy(_, a) if scalar(a) => (),
            Op::Union(a, b) if scalar(a) && scalar(b) => (),
            Op::Let(_, Call::Primitive(name, output), args)
                if output == "i64"
                    && args.len() == 2
                    && matches!(name.as_str(), "+" | "-" | "*")
                    && args.iter().all(integer) =>
            {
                ()
            }
            Op::Set(table, args, value)
                if p.tables[*table].constructor
                    && p.cell_ownership.tables[*table]
                    && args.len() <= 4
                    && args.iter().all(scalar)
                    && scalar(value) =>
            {
                writes.insert(*table);
            }
            _ => return None,
        }
    }
    Some(writes.into_iter().collect())
}
