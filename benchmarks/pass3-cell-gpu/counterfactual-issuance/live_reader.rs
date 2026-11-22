// Frozen encoder from route_credit.py. Context is captured on the issuing page.
#[derive(serde::Deserialize)]
struct RouteReader {
    edges: [E; 2],
    encoder: Vec<[f32; 15]>,
    bias: Vec<f32>,
    head: [Vec<f32>; 3],
    out: [f32; 3],
    #[serde(default)]
    single_only: bool,
    #[serde(default)]
    expected_gain: bool,
    #[serde(skip)]
    tables: [usize; 3],
    #[serde(default)]
    training_fork: bool,
    #[serde(default)]
    force: Option<[u64; 2]>,
    #[serde(skip)]
    observations: Vec<(u64, usize, Vec<u16>)>,
    #[serde(skip)]
    activations: BTreeMap<u16, Vec<f32>>,
    #[serde(skip)]
    decisions: [u64; 4],
    #[serde(skip)]
    fallback: u64,
    #[serde(skip)]
    runs: BTreeSet<usize>,
}

impl RouteReader {
    fn load(value: &J, g: &Graph, s: &State) -> Result<Option<Self>> {
        if value.is_null() {
            return Ok(None);
        }
        let mut m: Self = serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
        let width = m.bias.len();
        if width == 0
            || m.encoder.len() != width
            || m.head.iter().any(|h| h.len() != width)
            || m.encoder
                .iter()
                .flatten()
                .chain(&m.bias)
                .chain(m.head.iter().flatten())
                .chain(&m.out)
                .any(|v| !v.is_finite())
            || m.edges[0][0] != m.edges[1][0]
            || m.edges[0] == m.edges[1]
            || m.force.is_some_and(|p| !m.training_fork || p[1] > 3)
            || m.edges
                .iter()
                .any(|e| s.library.as_ref().is_none_or(|l| !l.contains(&vec![*e])))
        {
            return Err("invalid frozen route reader".into());
        }
        for (slot, name) in ["Get", "Single", "SubTuple"].iter().enumerate() {
            m.tables[slot] = g
                .program
                .tables
                .iter()
                .position(|t| t.name == *name)
                .ok_or("missing context table")?;
        }
        Ok(Some(m))
    }
    fn signatures(
        rows: &[(usize, crate::graph::RowFields)],
        subject: &[crate::value::Value],
    ) -> BTreeSet<u16> {
        let mut seen = BTreeSet::new();
        for (kind, fields) in rows {
            let mut key = 1u16 << kind;
            for (i, v) in fields.iter().take(4).enumerate() {
                for (j, q) in subject.iter().enumerate() {
                    if q == v {
                        key |= 1 << (3 + 3 * i + j);
                    }
                }
            }
            seen.insert(key);
        }
        seen
    }
    fn choose(&mut self, signatures: BTreeSet<u16>) -> usize {
        let mut pooled = vec![f32::NEG_INFINITY; self.bias.len()];
        for key in signatures {
            let embedding = self.activations.entry(key).or_insert_with(|| {
                self.encoder
                    .iter()
                    .zip(&self.bias)
                    .map(|(weights, b)| {
                        (weights
                            .iter()
                            .enumerate()
                            .filter(|(i, _)| key & (1 << i) != 0)
                            .map(|(_, w)| w)
                            .sum::<f32>()
                            + *b)
                            .tanh()
                    })
                    .collect()
            });
            for (p, h) in pooled.iter_mut().zip(embedding.iter()) {
                *p = p.max(*h);
            }
        }
        let mut best = 0.;
        let mut choice = 0;
        for i in 0..if self.single_only { 2 } else { 3 } {
            let prediction = self.out[i]
                + self.head[i]
                    .iter()
                    .zip(&pooled)
                    .map(|(w, h)| w * h)
                    .sum::<f32>();
            let gain = if self.expected_gain {
                prediction
            } else {
                prediction.round_ties_even()
            };
            if gain > best {
                best = gain;
                choice = i + 1;
            }
        }
        choice
    }
}

pub(crate) fn route_page(g: &Graph, rid: usize) -> Option<Vec<(usize, crate::graph::RowFields)>> {
    S.with_borrow(|v| {
        let m = v.as_ref()?.reader.as_ref()?;
        if rid != m.edges[0][0] {
            return None;
        }
        let mut rows = Vec::new();
        for (i, &t) in m.tables.iter().enumerate() {
            for w in g.witnesses(t) {
                if let Some(row) = g.row(w).expect("issuer context read")
                    && !row.hidden
                    && row.table == t
                {
                    rows.push((i, row.values));
                }
            }
        }
        Some(rows)
    })
}
pub(crate) fn route_bits(
    g: &Graph,
    rows: &[(usize, crate::graph::RowFields)],
    dep: Option<Dependency>,
    serial: u64,
) -> u64 {
    S.with_borrow_mut(|v| {
        let s = v.as_mut().unwrap();
        let m = s.reader.as_mut().unwrap();
        let prediction = dep
            .and_then(|w| g.row(w).expect("issuer subject read"))
            .filter(|r| {
                r.table == m.tables[0] && !r.hidden && r.values.len() == 3 && !rows.is_empty()
            })
            .map(|r| {
                let keys = RouteReader::signatures(rows, &r.values);
                if m.training_fork {
                    m.observations
                        .push((serial, s.run, keys.into_iter().collect()));
                    m.force
                        .filter(|p| p[0] == serial)
                        .map_or(3, |p| p[1] as usize)
                } else {
                    m.choose(keys)
                }
            });
        if prediction.is_none() {
            m.fallback += 1;
        }
        let choice = prediction.unwrap_or(3);
        m.runs.insert(s.run);
        m.decisions[choice] += 1;
        ((4 + choice) as u64) << 56
    })
}
