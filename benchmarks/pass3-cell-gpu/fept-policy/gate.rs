#[derive(Default)]
struct ClassGate {
    mode: String,
    audit_features: bool,
    weights: GateWeights,
    prior: std::collections::HashMap<usize, (u64, usize, usize)>,
    inputs: Vec<(u64, usize, [f64; 12], bool)>,
    calls: u64,
    selected: u64,
}
#[derive(Default, serde::Deserialize)]
struct GateWeights {
    #[serde(default)]
    direct: [f64; 12],
    #[serde(default)]
    hidden: Vec<[f64; 12]>,
    #[serde(default)]
    offsets: Vec<f64>,
    #[serde(default)]
    output: Vec<f64>,
    #[serde(default)]
    bias: f64,
}
impl GateWeights {
    fn score(&self, x: &[f64; 12]) -> f64 {
        let dot = |w: &[f64; 12], b: f64| w.iter().zip(x).fold(b, |a, (u, v)| a + u * v);
        if self.hidden.is_empty() {
            return dot(&self.direct, self.bias);
        }
        self.hidden
            .iter()
            .zip(&self.offsets)
            .zip(&self.output)
            .fold(self.bias, |a, ((w, b), v)| a + dot(w, *b).tanh() * v)
    }
}
impl ClassGate {
    fn configure(&mut self, cfg: &J) -> Result<()> {
        self.mode = cfg["mode"].as_str().unwrap_or("always").into();
        if !matches!(
            self.mode.as_str(),
            "always" | "never" | "count" | "previous" | "learned"
        ) {
            return Err("invalid class gate".into());
        }
        self.audit_features = cfg["capture"] == true;
        if self.mode == "learned" {
            self.weights =
                serde_json::from_value(cfg["weights"].clone()).map_err(|e| e.to_string())?;
            let w = &self.weights;
            if w.hidden.len() != w.offsets.len()
                || w.hidden.len() != w.output.len()
                || w.hidden.len() > 64
                || !w
                    .direct
                    .iter()
                    .chain(w.hidden.iter().flatten())
                    .chain(&w.output)
                    .chain(&w.offsets)
                    .chain([&w.bias])
                    .all(|n| n.is_finite())
            {
                return Err("invalid gate checkpoint".into());
            }
        }
        Ok(())
    }
    fn choose(
        &mut self,
        g: &Graph,
        rid: usize,
        wm: u64,
        p: &Plan,
        base: &[u8; N],
        _state: &[f32; H],
    ) -> bool {
        let r = &g.program.rules[rid];
        let pivot = p.pivot.expect("class eligibility includes pivot");
        let Call::Table(t) = r.query[pivot].call else {
            unreachable!()
        };
        let (last, n, emitted) = self.prior.get(&rid).copied().unwrap_or_default();
        let log = |x: u64| (x as f64).ln_1p();
        let rows = g.witness_count(t);
        let x = [
            log(rows as u64),
            log(n as u64),
            log(emitted as u64),
            emitted as f64 / n.max(1) as f64,
            log(g.epoch.saturating_sub(last)),
            log(g.epoch.saturating_sub(wm)),
            log(r.query.len() as u64),
            log(r.inputs.len() as u64),
            log(g.program.templates[r.template].ops.len() as u64),
            f64::from(base[3]),
            f64::from(base[9]),
            f64::from(base[13]),
        ];
        let selected = match self.mode.as_str() {
            "never" => false,
            "count" => rows > 1,
            "previous" => emitted > 1,
            "learned" => self.weights.score(&x) > 0.,
            _ => true,
        };
        self.calls += 1;
        self.selected += u64::from(selected);
        if self.audit_features {
            self.inputs.push((g.epoch, rid, x, selected));
        }
        selected
    }
    fn observe(&mut self, ep: u64, rid: usize, n: usize, k: usize) {
        self.prior.insert(rid, (ep, n, k));
    }
    fn report(&self) -> J {
        json!({"calls":self.calls,"selected":self.selected,"inputs":self.inputs})
    }
}
