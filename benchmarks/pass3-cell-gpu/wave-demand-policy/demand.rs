#[derive(Clone, Copy)]
enum WaveDemand {
    EntryForecast,
    Delay,
    Clip,
    Count([f64; 8]),
    Fraction([f64; 8]),
}

impl WaveDemand {
    fn parse(spec: &J) -> Result<Self> {
        let weights = || -> Result<[f64; 8]> {
            let w: [f64; 8] =
                serde_json::from_value(spec["weights"].clone()).map_err(|e| e.to_string())?;
            if w.iter().all(|v| v.is_finite()) {
                Ok(w)
            } else {
                Err("nonfinite wave weights".into())
            }
        };
        match spec["mode"].as_str() {
            None if spec.is_null() => Ok(Self::EntryForecast),
            Some("delay") => Ok(Self::Delay),
            Some("clip") => Ok(Self::Clip),
            Some("count") => Ok(Self::Count(weights()?)),
            Some("fraction") => Ok(Self::Fraction(weights()?)),
            _ => Err("unknown wave-demand mode".into()),
        }
    }
    fn delayed(self) -> bool {
        !matches!(self, Self::EntryForecast)
    }
    fn uses_entry(self) -> bool {
        !matches!(self, Self::Count(_) | Self::Fraction(_))
    }

    fn requested(self, r: &RuleRecord, cap: usize) -> usize {
        let offers = r.now.offers;
        match self {
            Self::EntryForecast => unreachable!(),
            Self::Delay => r.request,
            Self::Clip => r.request.min(offers),
            Self::Count(_) | Self::Fraction(_) if offers == 0 => 0,
            Self::Count(w) | Self::Fraction(w) => {
                let mut x = r.x;
                x[7] = (offers as f64).ln_1p();
                let z: f64 = x.iter().zip(w).map(|(v, weight)| v * weight).sum();
                let estimate = match self {
                    Self::Fraction(_) => offers as f64 / (1. + (-z).exp()),
                    _ => z.clamp(0., (cap as f64).ln_1p()).exp_m1(),
                };
                (estimate.round() as usize).min(offers).min(cap)
            }
        }
    }
}

#[derive(Default, serde::Serialize)]
struct DemandCounts {
    batches: usize,
    active_rules: usize,
    nonempty_rules: usize,
    predictions: usize,
    excess_at_issue: usize,
    post_issue_grants: usize,
    min_demand_bound: usize,
}

impl Staging {
    // Called exactly once on the first sealed wave that enters the verifier. Later
    // waves keep their original source authority but receive no additional budget.
    fn allocate_after_issue(&mut self, g: &Graph) {
        self.demand_counts.batches += 1;
        let mut forecasts = Vec::with_capacity(self.order.len());
        for &rid in &self.order {
            let rule = self.rules.get_mut(&rid).unwrap();
            let n = self.wave_demand.requested(rule, self.cap);
            self.demand_counts.active_rules += 1;
            self.demand_counts.nonempty_rules += usize::from(rule.now.offers != 0);
            self.demand_counts.excess_at_issue += n.saturating_sub(rule.now.offers);
            self.demand_counts.predictions +=
                usize::from(!self.wave_demand.uses_entry() && rule.now.offers != 0);
            self.stats.requested += n;
            rule.request = n;
            forecasts.push((rid, n));
        }
        self.allocate_forecasts(g, forecasts);
        for &rid in &self.order {
            let rule = self.rules.get_mut(&rid).unwrap();
            let grant = rule.span.len;
            self.demand_counts.post_issue_grants += grant;
            self.demand_counts.min_demand_bound += grant.min(rule.now.offers);
            for page in &mut rule.pages {
                if grant == 0 || self.fault == 1 {
                    page.handle = None;
                } else {
                    page.claimed = vec![0; page.n.div_ceil(64)];
                    let bytes = page.claimed.capacity() * size_of::<u64>();
                    self.bitmap_live += bytes;
                    self.stats.bitmap_bytes += bytes;
                    self.stats.group_pages += 1;
                    self.stats.authorized_lanes += page.n;
                }
            }
        }
        self.stats.peak_bitmap_bytes = self.stats.peak_bitmap_bytes.max(self.bitmap_live);
    }
}
