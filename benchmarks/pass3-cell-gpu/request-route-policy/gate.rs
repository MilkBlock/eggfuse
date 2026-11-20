const ROUTE_INPUTS: usize = 8;
#[derive(Deserialize)]
struct GateWeights {
    hidden: Vec<[f32; ROUTE_INPUTS]>,
    bias: Vec<f32>,
    output: Vec<f32>,
    offset: f32,
}
impl GateWeights {
    fn valid(&self) -> bool {
        let n = self.hidden.len();
        n <= 8
            && self.bias.len() == n
            && self.output.len() == if n == 0 { ROUTE_INPUTS } else { n }
            && self
                .hidden
                .iter()
                .flatten()
                .chain(self.bias.iter())
                .chain(self.output.iter())
                .all(|v| v.is_finite())
            && self.offset.is_finite()
    }
    fn predict(&self, x: &[f32; ROUTE_INPUTS]) -> f32 {
        let dot = |a: &[f32]| a.iter().zip(x).map(|(v, y)| v * y).sum::<f32>();
        if self.hidden.is_empty() {
            return self.offset + dot(&self.output);
        }
        self.offset
            + self
                .hidden
                .iter()
                .zip(&self.bias)
                .zip(&self.output)
                .map(|((w, b), o)| (dot(w) + b).tanh() * o)
                .sum::<f32>()
    }
}
#[derive(Default, Serialize)]
struct RouteReport {
    calls: u64,
    choices: u64,
    samples: Vec<(usize, usize, [f32; ROUTE_INPUTS], bool, u64)>,
}
#[derive(Default)]
struct RouteGate {
    mode: u8,
    capture: bool,
    weights: Option<GateWeights>,
    report: RouteReport,
    pending: Option<(std::time::Instant, usize, usize, [f32; ROUTE_INPUTS], bool)>,
}
pub fn configure_route_gate(value: &Json) -> Result<()> {
    let mode = value["mode"].as_u64().ok_or("missing gate mode")?;
    if mode > 4 || mode == 0 {
        return Err("invalid gate mode".into());
    }
    let weights = if mode == 3 {
        let w: GateWeights =
            serde_json::from_value(value["weights"].clone()).map_err(|e| e.to_string())?;
        if !w.valid() {
            return Err("invalid route weights".into());
        }
        Some(w)
    } else {
        None
    };
    STORE.with_borrow_mut(|x| {
        let s = x.as_mut().ok_or("no parent issuer")?;
        s.route_gate = RouteGate {
            mode: mode as u8,
            weights,
            capture: value["capture"].as_bool() == Some(true),
            ..Default::default()
        };
        Ok(())
    })
}
impl RouteGate {
    fn choose(
        &mut self,
        run: usize,
        rule: usize,
        c: &Context,
        src: &StackStep,
        point: &StackStep,
        target: &StackStep,
    ) -> bool {
        let size = |n: usize| (n.saturating_add(1).ilog2() as f32) / 16.;
        let since = |s: &StackStep| u8::from(s.frame.max_epoch >= c.watermark) as f32;
        let closed = c.rule.seminaive && c.remaining[3] < c.watermark;
        let x = [
            size(src.frame.rows.len()),
            size(point.frame.rows.len()),
            size(target.frame.rows.len()),
            since(src),
            since(point),
            since(target),
            u8::from(closed) as f32,
            u8::from(point.frame.rows.len() < src.frame.rows.len()) as f32,
        ];
        let use_request = match self.mode {
            1 => false,
            2 => true,
            3 => self.weights.as_ref().unwrap().predict(&x) > 0.,
            4 => closed && point.frame.rows.len() < src.frame.rows.len(),
            _ => unreachable!(),
        };
        self.report.calls += 1;
        self.report.choices += u64::from(use_request);
        if self.capture {
            self.pending = Some((std::time::Instant::now(), run, rule, x, use_request));
        }
        use_request
    }
    fn finish(&mut self) {
        if let Some((start, run, rid, x, on)) = self.pending.take() {
            self.report
                .samples
                .push((run, rid, x, on, start.elapsed().as_nanos() as u64));
        }
    }
}
