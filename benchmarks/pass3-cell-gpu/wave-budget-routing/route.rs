#[derive(Clone, Copy)]
enum Routing {
    Original,
    Offers,
    Model(WaveDemand),
}
impl Routing {
    fn parse(cfg: &J) -> Result<Option<Self>> {
        if cfg.is_null() {
            return Ok(None);
        }
        Ok(Some(match cfg["mode"].as_str() {
            Some("original") => Self::Original,
            Some("offers") => Self::Offers,
            Some("clip" | "count" | "fraction") => Self::Model(WaveDemand::parse(cfg)?),
            _ => return Err("unknown fixed-layout budget policy".into()),
        }))
    }
}

#[derive(Default)]
struct Router {
    mode: Option<Routing>,
    quiet_runs: usize,
    // Audit-only fresh counts are recorded AFTER ordinary commits.
    rows: Vec<J>,
    per_rule: Vec<(usize, usize)>,
}
impl Router {
    // Allocate no more than each item's requested weight. Source order breaks remainder ties.
    fn bounded_share(weights: &[usize], budget: usize) -> Vec<usize> {
        let sum: usize = weights.iter().sum();
        if sum <= budget {
            return weights.to_vec();
        }
        let mut shares = Vec::with_capacity(weights.len());
        let mut ranking = Vec::with_capacity(weights.len());
        for (i, &w) in weights.iter().enumerate() {
            let scaled = (w as u128) * (budget as u128);
            shares.push((scaled / sum as u128) as usize);
            ranking.push((std::cmp::Reverse(scaled % sum as u128), i));
        }
        let left = budget - shares.iter().sum::<usize>();
        if left > 0 {
            ranking.sort_unstable();
            for &(_, i) in &ranking[..left] {
                shares[i] += 1;
            }
        }
        shares
    }
}

impl Staging {
    fn route_layout_budgets(&mut self, g: &Graph, grants: &mut [(usize, usize)]) {
        let Some(mode) = self.router.mode else {
            return;
        };
        if !self.audit && (matches!(mode, Routing::Original) || grants.iter().all(|&(_, n)| n == 0))
        {
            return;
        }
        let mut classes: [Vec<usize>; 4] = Default::default();
        for (i, &(rid, original)) in grants.iter().enumerate() {
            let template = g.program.rules[rid].template;
            let class = g.program.templates[template].ops.len().clamp(1, 4) - 1;
            if self.audit {
                self.router.per_rule.push((class, original));
            }
            classes[class].push(i);
        }
        if matches!(mode, Routing::Original) {
            return;
        }
        for indices in &classes {
            let original: Vec<_> = indices.iter().map(|&i| grants[i].1).collect();
            let budget = original.iter().sum();
            if budget == 0 {
                continue;
            }
            let mut asks = Vec::with_capacity(indices.len());
            let mut offers = Vec::with_capacity(indices.len());
            for &i in indices {
                let r = &self.rules[&grants[i].0];
                offers.push(r.now.offers);
                asks.push(match mode {
                    Routing::Original => unreachable!(),
                    Routing::Offers => r.now.offers,
                    Routing::Model(plan) => plan.requested(r, self.cap),
                });
            }
            let mut assigned = Router::bounded_share(&asks, budget);
            let mut left = budget - assigned.iter().sum::<usize>();
            if left > 0 {
                let remaining: Vec<_> = offers.iter().zip(&assigned).map(|(n, g)| n - g).collect();
                let extras = Router::bounded_share(&remaining, left);
                for (a, e) in assigned.iter_mut().zip(extras) {
                    *a += e;
                    left -= e;
                }
            }
            if left > 0 {
                // More original same-layout headers than issued lanes. Preserve their
                // physical cost on original donors, including entirely empty Runs.
                let remaining: Vec<_> = original
                    .iter()
                    .zip(&assigned)
                    .map(|(n, g)| n.saturating_sub(*g))
                    .collect();
                let excess = Router::bounded_share(&remaining, left);
                for (a, e) in assigned.iter_mut().zip(excess) {
                    *a += e;
                    left -= e;
                }
            }
            assert_eq!(left, 0);
            for (&i, n) in indices.iter().zip(assigned) {
                grants[i].1 = n;
            }
        }
    }
    fn audit_layout_run(&mut self) {
        if !self.audit || self.router.mode.is_none() {
            return;
        }
        assert_eq!(self.router.per_rule.len(), self.order.len());
        let mut old = [0usize; 4];
        let mut allocated = [0usize; 4];
        let mut fresh = [0usize; 4];
        let mut offers = [0usize; 4];
        let mut attainable = 0usize;
        let mut actual = 0usize;
        let mut moved = 0usize;
        for (&rid, (c, prior)) in self.order.iter().zip(self.router.per_rule.drain(..)) {
            let r = &self.rules[&rid];
            old[c] += prior;
            allocated[c] += r.span.len;
            fresh[c] += r.now.fresh;
            offers[c] += r.now.offers;
            attainable += r.span.len.min(r.now.fresh);
            actual += r.span.taken;
            moved += r.span.len.saturating_sub(prior);
        }
        assert_eq!(old, allocated);
        self.router.rows.push(json!([
            self.epoch, old, allocated, offers, fresh, attainable, actual, moved
        ]));
    }
}
