//! Source-snapshot reads are mandatory before matching. RHS accesses and writes
//! become obligations only for rules that actually contribute bindings.
use super::*;

#[derive(Clone, Debug, Default, Serialize)]
pub struct Rule {
    pub query: TableSet,
    pub rhs: TableSet,
    pub accesses: TableSet,
    /// Shared Cell operand wiring and ordered source positions. The concrete
    /// closure must still be proved; None retains the ordinary scoped path.
    pub(crate) pure: Option<std::rc::Rc<crate::cell::BoundRhs>>,
}
impl Rule {
    pub fn derive(
        p: &Program,
        plan: &Plan,
        rid: usize,
        sorts: &[(BTreeSet<String>, bool)],
    ) -> Self {
        let cell = crate::cell::Definition::new(p,rid).expect("validated completion rule");
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
        for (operation,op) in template.ops.iter().enumerate() {
            // The same validated alias mask used by ordinary RHS execution
            // proves this constructor is supplied by a matched/earlier result.
            // Keep query demands above and the original source's access below;
            // only the already-elided operation contributes no new RHS demand.
            if matches!(op,Op::Let(_,Call::Table(t),_) if p.tables[*t].constructor)
                && p.known_results.static_skip.get(rid)
                    .and_then(|mask|mask.get(operation))==Some(&true) {
                continue;
            }
            match op {
                // Existing ordered Cell aliases prove identical values, not
                // merely a possible future union. Such a union adds no repair
                // influence; the instruction itself still executes normally.
                Op::Union(a, b) if cell.value(a) != cell.value(b) => {
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
                    rhs.extend(plan.completion_reads[*t].iter());
                    rhs.extend((0..n).filter(|&other| plan.affects(*t, other)));
                }
            }
        }
        let accesses: Vec<usize> = if opaque_rhs {
            (0..n).collect()
        } else {
            rhs.iter().copied().collect()
        };
        for (t, (names, unknown)) in sorts.iter().enumerate() {
            if !unions.is_empty() && (*unknown || !names.is_disjoint(&unions)) {
                rhs.extend(plan.completion_reads[t].iter());
                rhs.extend((0..n).filter(|&other| plan.affects(t, other)));
            }
        }
        if opaque_rhs {
            rhs.extend(0..n);
        }
        Self {
            query: query.into_iter().collect(),
            rhs: rhs.into_iter().collect(),
            accesses: accesses.into(),
            pure: None,
        }
    }
}
