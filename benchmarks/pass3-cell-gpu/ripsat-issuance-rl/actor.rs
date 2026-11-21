// Two licensed actions on a root page: ordinary root or signed completion.
use serde::Deserialize;
#[derive(Deserialize)]
struct ActorConfig {
    mode: String,
    weights: [f32; 3],
    seed: u64,
}
struct Actor {
    config: ActorConfig,
    random: u64,
    decisions: Vec<(u64, [f32; 3], bool)>,
    tokens: [u64; 2],
}
impl Actor {
    fn parse(spec: &J) -> Result<Option<Self>> {
        if spec.is_null() {
            return Ok(None);
        }
        let config: ActorConfig =
            serde_json::from_value(spec.clone()).map_err(|e| e.to_string())?;
        if !matches!(config.mode.as_str(), "sample" | "greedy" | "leaf" | "full")
            || !config.weights.iter().all(|w| w.is_finite())
        {
            return Err("invalid RipSat actor".into());
        }
        Ok(Some(Self {
            random: config.seed,
            config,
            decisions: Vec::new(),
            tokens: [0; 2],
        }))
    }
    fn choose(&mut self, serial: u64, count: usize, age: u64) -> bool {
        let x = [
            1.,
            (count as f32).ln_1p().min(8.) / 8.,
            (age as f32).ln_1p().min(8.) / 8.,
        ];
        let logit: f32 = x.iter().zip(self.config.weights).map(|(v, w)| v * w).sum();
        let action = match self.config.mode.as_str() {
            "sample" => {
                self.random = self.random.wrapping_add(0x9e3779b97f4a7c15);
                let mut z = self.random;
                z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
                z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
                let u = ((z ^ (z >> 31)) >> 40) as f32 / 16777216.;
                let take = u < 1. / (1. + (-logit).exp());
                self.decisions.push((serial, x, take));
                take
            }
            "full" => true,
            "leaf" => false,
            _ => logit >= 0.,
        };
        self.tokens[action as usize] += 1;
        action
    }
}

pub(crate) fn leaf_bit(code: usize, serial: u64, count: usize, age: u64) -> u64 {
    if code & (1usize << 63) == 0 {
        return 0;
    }
    S.with_borrow_mut(|slot| {
        let Some(s) = slot else {
            return 0;
        };
        let Some(actor) = s.actor.as_mut() else {
            return 0;
        };
        if actor.choose(serial, count, age) {
            return 0;
        }
        s.set_counts.encoded -= 1;
        1u64 << 63
    })
}
