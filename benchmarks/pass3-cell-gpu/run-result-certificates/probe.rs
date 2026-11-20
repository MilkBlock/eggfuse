// A representation-only control in a private copy of the measured crate.
// Clear cached decoded fields, keep the original fact/function and compare both access paths.
pub fn probe_certificate_layout(mut g: Graph) -> Result<serde_json::Value> {
    let mut obs = vec![];
    for table in 0..g.program.tables.len() {
        for w in g.witnesses(table) {
            let Some(old) = g.row(w)? else { continue };
            if old.hidden || old.values.is_empty() {
                continue;
            }
            let kind = match w {
                Dependency::Fact(f) if g.stable_node(f).is_none() => 3,
                Dependency::Function(i) if !g.functions[i].key.is_empty() => 4,
                _ => continue,
            };
            if obs.iter().any(|(k, _, _, _)| *k == kind) {
                continue;
            }
            let test = |g: &Graph| -> Result<()> {
                let current = g
                    .row(w)?
                    .ok_or("missing source in representation control")?;
                if current.values != old.values
                    || current.epoch != old.epoch
                    || g.compare_certificate_row(&old, true)? != Some((true, kind))
                {
                    return Err("original decoder and direct proof disagree".into());
                }
                let mut values = old.values.to_vec();
                values[0] = if values[0] == Value::Int(-777) {
                    Value::Int(-778)
                } else {
                    Value::Int(-777)
                };
                let mut wrong = old.clone();
                wrong.values = row_fields(values);
                if g.compare_certificate_row(&wrong, true)? != Some((false, kind)) {
                    return Err("forged field accepted".into());
                }
                wrong = old.clone();
                wrong.epoch = wrong.epoch.wrapping_add(1);
                if g.compare_certificate_row(&wrong, true)? != Some((false, 0)) {
                    return Err("forged epoch accepted".into());
                }
                Ok(())
            };
            match w {
                Dependency::Fact(f) => {
                    let fields = g
                        .cells
                        .get_mut(&f.cell)
                        .unwrap()
                        .facts
                        .get_mut(&f.op)
                        .unwrap()
                        .decoded
                        .take();
                    test(&g)?;
                    g.cells
                        .get_mut(&f.cell)
                        .unwrap()
                        .facts
                        .get_mut(&f.op)
                        .unwrap()
                        .decoded = fields;
                }
                Dependency::Function(i) => {
                    let fields = g.function_decoded[i].take();
                    test(&g)?;
                    g.function_decoded[i] = fields;
                }
            }
            obs.push((kind, table, w, old.values.len()));
        }
    }
    if obs.len() != 2 {
        return Err("both source layouts must be exercised".into());
    }
    Ok(
        serde_json::json!({"observed":obs,"field_mismatches_rejected":2,"epoch_mismatches_rejected":2}),
    )
}
