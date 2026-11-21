type Features = [u8; 12];
type InputWord = (usize, Dependency, u64);
type Words = smallvec::SmallVec<[InputWord; 4]>;
impl Handle {
    fn lane_words(&self, lane: usize) -> Words {
        match self {
            Self::Single(p) => p.ranking_parent(lane).into_iter().collect(),
            Self::Multi(p) => p
                .parents(lane)
                .iter()
                .map(|r| (r.atom, r.row, r.version))
                .collect(),
        }
    }
}

fn log_bin(n: u64) -> u8 {
    n.saturating_add(1).ilog2().min(8) as u8
}
fn fraction(n: usize, total: usize) -> u8 {
    (n.saturating_mul(8) / total.max(1)).min(8) as u8
}

#[derive(Default)]
struct LaneState {
    chosen: Vec<(usize, usize)>, // source lane -> offset in its Run/rule physical span
    features: Vec<Features>,     // retained only when capturing outcomes
    fresh: Vec<u64>,             // one bit per lane for all controls, to account distinct targets
    offset: usize,
}
#[derive(Clone, Copy)]
enum RankingMode {
    First,
    Score,
}
#[derive(serde::Deserialize)]
struct HiddenRank {
    hidden: [[f64; 12]; 8],
    hidden_bias: [f64; 8],
    output: [f64; 8],
}
struct LanePolicy {
    hidden: Option<HiddenRank>,
    groups: bool,
    mode: RankingMode,
    weights: [f64; 12],
    bias: f64,
    capture: bool,
    foreign: bool,
    features_only: bool,
}
#[derive(Default, serde::Serialize)]
struct LaneCounts {
    waves: u64,
    rules: u64,
    lanes: u64,
    scored: u64,
    selected: u64,
    partial_rules: u64,
    fresh_lanes: u64,
    repeated_fresh: u64,
    selected_fresh: u64,
    first_fresh: u64,
    oracle_fresh: u64,
    beyond_first_chosen: u64,
    beyond_first_fresh: u64,
    unlisted_fresh: u64,
    before_verifier: u64,
    peak_rank_pairs: usize,
    peak_selected: usize,
}
#[derive(Default)]
struct LaneRank {
    groups: Vec<(u64, usize, usize, Vec<(Features, u64, u64)>)>,
    policy: Option<LanePolicy>,
    counts: LaneCounts,
    hist: std::collections::BTreeMap<Features, [u64; 2]>,
    done: bool,
}
impl LaneRank {
    fn configure(cfg: &J, storage: Storage, timing: Timing) -> Result<Self> {
        let Some(spec) = cfg.get("lane_rank") else {
            return Ok(Self::default());
        };
        if storage != Storage::Named || !matches!(timing, Timing::Run) {
            return Err("lane ranking requires named Run staging".into());
        }
        let mode = match spec["mode"].as_str() {
            Some("first" | "capture" | "feature-first") => RankingMode::First,
            Some("score") => RankingMode::Score,
            _ => return Err("unknown lane ranking mode".into()),
        };
        let hidden: Option<HiddenRank> = if spec.get("hidden").is_some() {
            Some(serde_json::from_value(spec.clone()).map_err(|e| e.to_string())?)
        } else {
            None
        };
        if let Some(h) = &hidden
            && !h
                .hidden
                .iter()
                .flatten()
                .chain(&h.hidden_bias)
                .chain(&h.output)
                .all(|v| v.is_finite())
        {
            return Err("nonfinite hidden ranking coefficients".into());
        }
        let weights = if matches!(mode, RankingMode::Score) && hidden.is_none() {
            serde_json::from_value(spec["weights"].clone()).map_err(|e| e.to_string())?
        } else {
            [0.; 12]
        };
        let bias = spec["bias"].as_f64().unwrap_or(0.);
        if !bias.is_finite() || !weights.iter().all(|x: &f64| x.is_finite()) {
            return Err("nonfinite lane ranking parameters".into());
        }
        let foreign = match spec["fault"].as_str() {
            None | Some("none") => false,
            Some("foreign") => true,
            _ => return Err("unknown ranking fault".into()),
        };
        Ok(Self {
            policy: Some(LanePolicy {
                mode,
                hidden,
                groups: spec["groups"] == true,
                weights,
                bias,
                capture: spec["mode"] == "capture"
                    || spec["capture"] == true
                    || spec["groups"] == true,
                features_only: spec["mode"] == "feature-first",
                foreign,
            }),
            ..Self::default()
        })
    }
    fn report(&self) -> J {
        json!({"counts":self.counts,"hist":self.hist.iter().collect::<Vec<_>>(),"groups":self.groups})
    }
}

impl Page {
    fn extract_features(&self, ep: u64, lhs: usize) -> Vec<Features> {
        let handle = self.handle.as_ref().expect("sealed ranked page");
        let multi = matches!(handle, Handle::Multi(_));
        let mut first = rustc_hash::FxHashMap::<InputWord, usize>::default();
        let mut last = rustc_hash::FxHashMap::<InputWord, usize>::default();
        for lane in 0..self.n {
            let w = handle.lane_words(lane);
            if let Some(k) = w.first() {
                *first.entry(*k).or_default() += 1;
            }
            if let Some(k) = w.last() {
                *last.entry(*k).or_default() += 1;
            }
        }
        let mut previous = Words::new();
        let mut features = Vec::with_capacity(self.n);
        for lane in 0..self.n {
            let w = handle.lane_words(lane);
            let n = w.len();
            let mut facts = 0;
            let mut fresh = 0;
            let mut min_age = u64::MAX;
            let mut max_age = 0;
            for &(_, address, version) in &w {
                facts += usize::from(matches!(address, Dependency::Fact(_)));
                let age = ep.saturating_sub(version);
                fresh += usize::from(age <= 1);
                min_age = min_age.min(age);
                max_age = max_age.max(age);
            }
            let repeated = w.iter().zip(&previous).filter(|(a, b)| a == b).count();
            let x = [
                u8::from(multi) * 8,
                log_bin(self.n as u64),
                fraction(lane, self.n.saturating_sub(1)),
                n.min(8) as u8,
                fraction(facts, n),
                fraction(fresh, n),
                log_bin(if n > 0 { min_age } else { 0 }),
                log_bin(max_age),
                fraction(repeated, n),
                log_bin(w.first().map_or(0, |k| first[k]) as u64),
                log_bin(w.last().map_or(0, |k| last[k]) as u64),
                lhs.min(8) as u8,
            ];
            features.push(x);
            previous = w;
        }
        features
    }
}

impl Staging {
    fn seal_ranked(&mut self, g: &Graph) -> Result<()> {
        let Some(policy) = &self.rank.policy else {
            return Ok(());
        };
        if self.first_verify.is_some() || self.rank.done {
            return Err("ranking must run exactly once, before the first validator".into());
        }
        self.rank.done = true;
        self.rank.counts.waves += 1;
        for &rid in &self.order {
            let r = self.rules.get_mut(&rid).unwrap();
            let n = r.now.offers;
            if n == 0 {
                continue;
            }
            let k = r.span.len.min(n);
            self.rank.counts.rules += 1;
            self.rank.counts.lanes += n as u64;
            self.rank.counts.partial_rules += u64::from(k != 0 && k < n);
            let use_scores = matches!(policy.mode, RankingMode::Score) && k != 0 && k < n;
            let mut scores = Vec::<(f64, usize)>::with_capacity(if use_scores { n } else { 0 });
            let mut offset = 0;
            for p in &mut r.pages {
                p.rank_state.offset = offset;
                p.rank_state.fresh = vec![0; p.n.div_ceil(64)];
                if use_scores || policy.capture || policy.features_only {
                    let features = p.extract_features(self.epoch, g.program.rules[rid].query.len());
                    for (i, x) in features.iter().enumerate() {
                        if use_scores {
                            let dot = |w: &[f64; 12], b: f64| {
                                w.iter()
                                    .zip(x)
                                    .fold(b, |v, (w, f)| v + w * f64::from(*f) / 8.)
                            };
                            let z = if let Some(h) = &policy.hidden {
                                h.hidden
                                    .iter()
                                    .zip(&h.hidden_bias)
                                    .zip(&h.output)
                                    .fold(policy.bias, |a, ((w, b), v)| a + dot(w, *b).tanh() * v)
                            } else {
                                dot(&policy.weights, policy.bias)
                            };
                            scores.push((z, i + offset));
                        }
                        if policy.capture {
                            self.rank.hist.entry(*x).or_default()[0] += 1;
                        }
                    }
                    if policy.capture {
                        p.rank_state.features = features;
                    }
                }
                offset += p.n;
            }
            assert_eq!(offset, n);
            let chosen = if use_scores {
                self.rank.counts.scored += scores.len() as u64;
                self.rank.counts.peak_rank_pairs =
                    self.rank.counts.peak_rank_pairs.max(scores.len());
                scores.select_nth_unstable_by(k, |a, b| {
                    b.0.total_cmp(&a.0).then_with(|| a.1.cmp(&b.1))
                });
                let mut positions: Vec<_> = scores[..k].iter().map(|v| v.1).collect();
                positions.sort_unstable();
                positions
            } else {
                (0..k).collect()
            };
            self.rank.counts.peak_selected = self.rank.counts.peak_selected.max(chosen.len());
            let mut page = 0;
            for (selected, position) in chosen.into_iter().enumerate() {
                while position >= r.pages[page].rank_state.offset + r.pages[page].n {
                    page += 1;
                }
                let p = &mut r.pages[page];
                let lane = position - p.rank_state.offset;
                let slot = r.span.start + selected;
                let serial = p.first + lane as u64;
                p.rank_state.chosen.push((lane, slot));
                self.slabs[r.span.slab][slot].named = match self.fault {
                    1 => None,
                    2 => Some((self.epoch.wrapping_sub(1), serial)),
                    _ => Some((self.epoch, serial)),
                };
                self.rank.counts.beyond_first_chosen += u64::from(position >= k);
            }
            self.stats.names_attached += if self.fault == 1 { 0 } else { k };
            self.rank.counts.selected += k as u64;
            self.rank.counts.before_verifier += k as u64;
        }
        Ok(())
    }
}

impl Graph {
    pub(crate) fn seal_ranked_staging(&self) -> Result<()> {
        if let Some(state) = &self.spec_cells {
            state.borrow_mut().seal_ranked(self)?
        }
        Ok(())
    }
}
