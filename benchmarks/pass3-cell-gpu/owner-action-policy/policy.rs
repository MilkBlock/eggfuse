#[derive(serde::Deserialize)]
pub struct OwnerPolicy {
    /// Scores use only pre-action local layout counts, in the order in owner_features.
    weights: [f64; 8],
    intercept: f64,
}
impl OwnerPolicy {
    fn score(&self, features: &[usize; 8]) -> Result<f64> {
        let score = features.iter().zip(&self.weights).fold(self.intercept, |a,(n,w)| a+*n as f64*w);
        if score.is_finite() { Ok(score) } else { Err("non-finite owner policy".into()) }
    }
}
