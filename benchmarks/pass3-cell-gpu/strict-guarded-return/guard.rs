// A checked child may bind only the named pivot and deterministic primitive
// outputs. A missing input or an additional table cannot be resolved here.
fn guarded_plan(rule: &crate::program::Rule) -> bool {
    if !rule.seminaive || rule.query.is_empty() || !matches!(rule.query[0].call, Call::Table(_)) {
        return false;
    }
    let mut bound = BTreeSet::new();
    for a in &rule.query[0].args {
        if let Arg::Slot(i) = a {
            bound.insert(*i);
        }
    }
    for a in rule.query.iter().skip(1) {
        let Call::Primitive(op, _) = &a.call else {
            return false;
        };
        if !matches!(
            op.as_str(),
            ">" | "<" | ">=" | "<=" | "+" | "-" | "*" | "min" | "max"
        ) {
            return false;
        }
        let Some((result, inputs)) = a.args.split_last() else {
            return false;
        };
        if inputs
            .iter()
            .any(|v| matches!(v,Arg::Slot(i) if !bound.contains(i)))
        {
            return false;
        }
        if let Arg::Slot(i) = result {
            bound.insert(*i);
        }
    }
    rule.inputs.iter().all(|s| bound.contains(s))
}
fn direct_inputs(
    g: &Graph,
    rule: &crate::program::Rule,
    row: &crate::graph::Row,
) -> Result<Option<Slots>> {
    let mut inputs = BTreeMap::new();
    let pivot = &rule.query[0];
    if pivot.args.len() != row.values.len() {
        return Err("invalid named pivot width".into());
    }
    if !pivot
        .args
        .iter()
        .zip(row.values.iter())
        .all(|(a, v)| crate::cell::bind_query(a, v, &mut inputs, g))
    {
        return Ok(None);
    }
    for a in rule.query.iter().skip(1) {
        let Call::Primitive(op, ty) = &a.call else {
            return Err("unnamed table in signed guard".into());
        };
        let (result, keys) = a.args.split_last().ok_or("empty guard")?;
        let values = keys
            .iter()
            .map(|arg| crate::cell::query_operand(arg, &inputs, g).ok_or("missing guard operand"))
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let Some(value) = g.primitive(op, &values, ty)? else {
            return Ok(None);
        };
        if !crate::cell::bind_query(result, &value, &mut inputs, g) {
            return Ok(None);
        }
    }
    let mut slots = Slots::default();
    for s in rule.inputs.iter() {
        slots.insert(*s, inputs.get(s).ok_or("unbound guarded return")?.clone());
    }
    Ok(Some(slots))
}
pub(crate) fn strict_pivot_only(rule: &crate::program::Rule) -> bool {
    guarded_plan(rule)
}
