// Neural estimate of extra paid proposals avoided by an eight-hop SubTuple root.
#[derive(serde::Deserialize)]
struct DepthReader {
    rule: usize,
    #[serde(default)]
    fixed_depth: Option<usize>,
    encoder: Vec<Vec<f32>>,
    bias: Vec<f32>,
    head: Vec<f32>,
    #[serde(default)]
    attention: Option<Vec<f32>>,
    #[serde(default)]
    anchored: bool,
    out: f32,
    #[serde(default = "depth_threshold")]
    threshold: f32,
    #[serde(skip)]
    tables: [usize; 3],
    #[serde(skip)]
    applied: [u64; 3],
    #[serde(skip)]
    caps: Vec<(u64, usize, usize)>,
    #[serde(skip)]
    runs: BTreeSet<usize>,
}

fn depth_threshold() -> f32 {
    0.5
}

impl DepthReader {
    fn load(config: &J, g: &Graph, depth: usize) -> Result<Option<Self>> {
        if config.is_null() {
            return Ok(None);
        }
        let mut m: Self = serde_json::from_value(config.clone()).map_err(|e| e.to_string())?;
        if m.fixed_depth.is_some_and(|d| !matches!(d, 2 | 8))
            || depth != 8
            || m.head.is_empty()
            || m.attention
                .as_ref()
                .is_some_and(|a| a.len() != m.head.len() || a.iter().any(|x| !x.is_finite()))
            || m.bias.len() != m.head.len()
            || m.encoder.len() != m.head.len()
            || m.encoder.iter().any(|r| r.len() != 68)
            || m.encoder
                .iter()
                .flatten()
                .chain(&m.bias)
                .chain(&m.head)
                .chain([&m.out, &m.threshold])
                .any(|w| !w.is_finite())
        {
            return Err("invalid depth reader weights".into());
        }
        for (i, name) in ["Get", "Single", "SubTuple"].iter().enumerate() {
            m.tables[i] = g
                .program
                .tables
                .iter()
                .position(|t| t.name == *name)
                .ok_or("missing depth reader table")?;
        }
        if !g
            .program
            .rules
            .get(m.rule)
            .and_then(|r| r.query.first())
            .is_some_and(|q| matches!(q.call,Call::Table(t) if t==m.tables[2]))
        {
            return Err("depth reader requires a SubTuple subject".into());
        }
        Ok(Some(m))
    }
}

pub(crate) struct DepthRow {
    fields: crate::graph::RowFields,
    base: Vec<f32>,
}
pub(crate) fn depth_page(g: &Graph, rid: usize) -> Option<Vec<DepthRow>> {
    S.with_borrow(|v| {
        let m = v.as_ref()?.depth_reader.as_ref()?;
        if m.rule != rid {
            return None;
        }
        if m.fixed_depth.is_some() {
            return Some(Vec::new());
        }
        let mut counts = BTreeMap::<u64, [usize; 12]>::new();
        let mut rows = Vec::new();
        for (kind, &table) in m.tables.iter().enumerate() {
            for witness in g.witnesses(table) {
                let Some(row) = g.row(witness).expect("depth context read") else {
                    continue;
                };
                if row.hidden || row.table != table {
                    continue;
                }
                for (j, value) in row.values.iter().take(4).enumerate() {
                    if let crate::value::Value::Eq(id) = value {
                        counts.entry(*id).or_default()[kind * 4 + j] += 1;
                    }
                }
                rows.push((kind, row.values));
            }
        }
        Some(
            rows.into_iter()
                .map(|(kind, fields)| {
                    let mut base = m.bias.clone();
                    for (b, w) in base.iter_mut().zip(&m.encoder) {
                        *b += w[kind];
                    }
                    for (i, v) in fields.iter().take(4).enumerate() {
                        if let crate::value::Value::Eq(id) = v {
                            for (k, &count) in counts[id].iter().enumerate() {
                                let other = count
                                    > usize::from(k / 4 == kind && fields.get(k % 4) == Some(v));
                                if other {
                                    let col = 20 + (k / 4) * 16 + i * 4 + k % 4;
                                    for (b, w) in base.iter_mut().zip(&m.encoder) {
                                        *b += w[col];
                                    }
                                }
                            }
                        }
                    }
                    DepthRow { fields, base }
                })
                .collect(),
        )
    })
}
pub(crate) fn depth_bits(g: &Graph, rows: &[DepthRow], dep: Option<Dependency>) -> u64 {
    S.with_borrow(|v| {
        let m = v.as_ref().unwrap().depth_reader.as_ref().unwrap();
        if let Some(depth) = m.fixed_depth {
            return (if depth == 8 { 2 } else { 1 }) << 54;
        }
        let Some(subject) = dep.and_then(|d| g.row(d).expect("depth subject read")) else {
            return 0;
        };
        if subject.table != m.tables[2]
            || subject.hidden
            || subject.values.len() != 4
            || rows.is_empty()
        {
            return 0;
        }
        let crate::value::Value::Int(length) = subject.values[2] else {
            return 0;
        };
        let mut pooled = vec![f32::NEG_INFINITY; m.head.len()];
        let mut max_logit = f32::NEG_INFINITY;
        let mut mass = 0.;
        let mut hidden = vec![0.; m.head.len()];
        if m.attention.is_some() {
            pooled.fill(0.);
        }
        for row in rows {
            if m.anchored
                && !row
                    .fields
                    .iter()
                    .any(|v| matches!(v, crate::value::Value::Eq(_)) && subject.values.contains(v))
            {
                continue;
            }
            let mut cols = Vec::new();
            for (i, val) in row.fields.iter().take(4).enumerate() {
                for (j, q) in subject.values.iter().enumerate() {
                    if val == q {
                        cols.push(3 + i * 4 + j);
                    }
                }
            }
            for ((h, b), w) in hidden.iter_mut().zip(&row.base).zip(&m.encoder) {
                *h = *b + (length as f32 / 5.) * w[19] + cols.iter().map(|&i| w[i]).sum::<f32>();
            }
            if let Some(attention) = &m.attention {
                for h in &mut hidden {
                    *h = h.tanh();
                }
                let logit = hidden
                    .iter()
                    .zip(attention)
                    .map(|(h, a)| h * a)
                    .sum::<f32>();
                let next_max = max_logit.max(logit);
                let old_scale = (max_logit - next_max).exp();
                let weight = (logit - next_max).exp();
                for (p, h) in pooled.iter_mut().zip(&hidden) {
                    *p = *p * old_scale + weight * h;
                }
                mass = mass * old_scale + weight;
                max_logit = next_max;
            } else {
                for (p, h) in pooled.iter_mut().zip(&hidden) {
                    *p = p.max(*h);
                }
            }
        }
        if m.attention.is_some() {
            for p in &mut pooled {
                *p /= mass;
            }
        } else {
            for p in &mut pooled {
                *p = p.tanh();
            }
        }
        let gain = m.out + pooled.iter().zip(&m.head).map(|(x, w)| x * w).sum::<f32>();
        (if gain >= m.threshold { 2 } else { 1 }) << 54
    })
}
