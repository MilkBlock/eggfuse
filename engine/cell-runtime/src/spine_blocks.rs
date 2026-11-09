//! Bake admits Cell queries for cross-stage composition; it owns no second
//! query representation or execution path.
use crate::{cell::Query, program::*};
use serde_json::{Value as J, json};

pub(crate) fn select(p: &Program, r: usize, pivot: usize, staged: bool) -> Option<&Query> {
    let query = p.cell_queries.get(r, pivot)?.as_ref();
    (staged
        || query.steps.is_empty()
        || matches!(query.steps.as_slice(), [step] if matches!(step.call, Call::Table(_))))
    .then_some(query)
}
#[derive(Clone, Debug, Default)]
pub struct Catalog {
    entries: Vec<Vec<bool>>,
}
impl Catalog {
    pub(crate) fn contains(&self, r: usize, pivot: usize) -> bool {
        self.entries
            .get(r)
            .and_then(|v| v.get(pivot))
            .copied()
            .unwrap_or(false)
    }
    pub(crate) fn parse(p: &Program, raw: &J) -> Result<Self> {
        if raw.is_null() {
            return Ok(Self::default());
        }
        let staged = match raw["schema"].as_str() {
            Some("eggfuse-spine-blocks/v1") => false,
            Some("eggfuse-spine-blocks/v2") => true,
            _ => return Err("unsupported spine block policy".into()),
        };
        if raw["recipe_sha256"] != p.artifact["recipe"]["sha256"] {
            return Err("spine block recipe mismatch".into());
        }
        let mut entries: Vec<Vec<_>> = p.rules.iter().map(|r| vec![false; r.query.len()]).collect();
        for e in raw["entries"].as_array().ok_or("missing spine blocks")? {
            let r = e["consumer"].as_u64().ok_or("block consumer")? as usize;
            let a = e["pivot"].as_u64().ok_or("block pivot")? as usize;
            let block = select(p, r, a, staged).ok_or("uncertified spine entry")?;
            if e["rhs_template"] != p.rules[r].template
                || e["block"] != json!(block)
                || std::mem::replace(&mut entries[r][a], true)
            {
                return Err("invalid spine block wiring or duplicate entry".into());
            }
        }
        Ok(Self { entries })
    }
}
