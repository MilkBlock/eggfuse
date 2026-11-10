//! Shared conservative influence code. A changed input may merge the result;
//! result-only uses observe the alias without starting a new constructor proof.
//! This is typed wiring, not a prediction that a congruence condition is true.
use super::*;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Step {
    pub frame: usize,
    pub op: u32,
    pub output: Option<usize>,
}
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Plan {
    pub signals: Vec<Vec<Step>>,
}
impl Plan {
    pub fn derive(shape: &Shape, programs: &[Arc<PortProgram>]) -> Self {
        Self {
            signals: shape
                .signals
                .iter()
                .map(|uses| {
                    uses.iter()
                        .map(|site| {
                            let fields =
                                &programs[shape.programs[site.frame]].fields[site.op as usize];
                            let key = site.columns.iter().any(|&column| column + 1 < fields.len());
                            let output = key
                                .then(|| *fields.last().unwrap())
                                .flatten()
                                .map(|local| shape.ports[site.frame][local]);
                            Step {
                                frame: site.frame,
                                op: site.op,
                                output,
                            }
                        })
                        .collect()
                })
                .collect(),
        }
    }
}
