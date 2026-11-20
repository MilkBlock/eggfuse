//! Single-threaded FP32 inference for the two-level forest trained in PyTorch.
use crate::{executor::Executor, precomputed_forest::Packet, program::Result};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::time::Instant;

#[derive(Deserialize)]
pub struct ForestPolicy {
    schema: String,
    root_weight: [[f32; 6]; 12],
    root_bias: [f32; 12],
    table: Vec<[f32; 8]>,
    consumer: Vec<[f32; 8]>,
    child_weight: Vec<Vec<f32>>,
    child_bias: [f32; 32],
    out_weight: [f32; 32],
    out_bias: f32,
}

#[derive(Deserialize)]
pub struct ForestInputs {
    schema: String,
    program_sha256: String,
    roots: Vec<usize>,
    root_features: Vec<[f32; 6]>,
    candidates: Vec<Candidate>,
}

#[derive(Deserialize)]
struct Candidate {
    // Index into roots, parent effect, consumer rule and consumer pivot.
    entry: [usize; 4],
    table: usize,
    direct: bool,
    features: [f32; 12],
}

impl Executor {
    pub fn use_cpu_forest_policy(
        &mut self,
        model: &ForestPolicy,
        inputs: &ForestInputs,
        digest: &str,
        residual: bool,
    ) -> Result<serde_json::Value> {
        if inputs.schema != "eggfuse.forest-inputs/v1" || inputs.program_sha256 != digest {
            return Err("forest inputs do not describe the loaded program".into());
        }
        if model.schema != "eggfuse.cpu-forest-policy/v1"
            || model.child_weight.len() != 32
            || model.child_weight.iter().any(|r| r.len() != 40)
            || inputs.roots.len() != inputs.root_features.len()
        {
            return Err("unsupported forest policy or input shape".into());
        }
        let start = Instant::now();
        let parents: Vec<[f32; 12]> = inputs
            .root_features
            .iter()
            .map(|f| {
                std::array::from_fn(|i| dot(f, &model.root_weight[i], model.root_bias[i]).tanh())
            })
            .collect();
        let mut children = Vec::with_capacity(inputs.candidates.len());
        let mut active_count = 0;
        for c in &inputs.candidates {
            let [parent, effect, rule, pivot] = c.entry;
            let mut x = [0.; 40];
            x[..12].copy_from_slice(parents.get(parent).ok_or("unknown policy parent")?);
            x[12..24].copy_from_slice(&c.features);
            x[24..32].copy_from_slice(model.table.get(c.table).ok_or("unknown table embedding")?);
            x[32..].copy_from_slice(model.consumer.get(rule).ok_or("unknown rule embedding")?);
            let hidden: [f32; 32] = std::array::from_fn(|i| {
                dot(&x, &model.child_weight[i], model.child_bias[i]).tanh()
            });
            let score = dot(&hidden, &model.out_weight, model.out_bias);
            if !score.is_finite() {
                return Err("non-finite forest score".into());
            }
            let active = score >= 0.;
            active_count += usize::from(active);
            children.push([
                i64::from(active),
                parent as i64,
                effect as i64,
                rule as i64,
                pivot as i64,
                i64::from(active && c.direct),
            ]);
        }
        let forward_ms = start.elapsed().as_secs_f64() * 1000.;
        let mut hash = Sha256::new();
        for row in &children {
            for &value in row {
                let word = i32::try_from(value).map_err(|_| "forest address exceeds i32")?;
                hash.update(word.to_le_bytes());
            }
        }
        let packet = Packet {
            schema: "eggfuse.sealed-forest/v1".into(),
            program_sha256: digest.into(),
            roots: inputs.roots.clone(),
            catalog: inputs.candidates.iter().map(|c| c.entry).collect(),
            children,
        };
        self.install_forest_packet(packet, digest, residual)?;
        Ok(
            serde_json::json!({"backend":"rust-cpu","candidates":inputs.candidates.len(),"active":active_count,
            "certificate_sha256":format!("{:x}",hash.finalize()),"forward_ms":forward_ms}),
        )
    }
}

fn dot(x: &[f32], w: &[f32], bias: f32) -> f32 {
    x.iter().zip(w).fold(bias, |sum, (x, w)| sum + x * w)
}
