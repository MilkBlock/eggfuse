//! Shared, bounded congruence conditions derived from checked symbolic wiring.
//! A program describes port layout, not operator identity. Runtime table tags
//! and scalar literals are explicit guards, never inferred from program IDs.
use super::*;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Site {
    pub frame: usize,
    pub op: u32,
    pub fields: Vec<Option<usize>>,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Condition {
    pub sites: [usize; 2],
    pub equality_inputs: Vec<[usize; 2]>,
    pub scalar_columns: Vec<usize>,
    pub outputs: [usize; 2],
}
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Plan {
    pub complete: bool,
    pub sites: Vec<Site>,
    pub conditions: Vec<Condition>,
    /// Site -> conditions, ordered by the other site. Shared code, never a
    /// consumer list attached to an individual producer instance.
    pub routes: Vec<Vec<usize>>,
    /// Signal -> (site, input column), used to certify boundary exclusion.
    pub inputs: Vec<Vec<(usize, usize)>>,
}
impl Plan {
    pub const MAX_SITES: usize = 16;
    pub fn derive(shape: &Shape, programs: &[Rc<PortProgram>]) -> Self {
        let mut sites = Vec::new();
        for (frame, &program) in shape.programs.iter().enumerate() {
            for (op, fields) in programs[program].fields.iter().enumerate() {
                if fields.len() < 2 || !fields[..fields.len() - 1].iter().any(Option::is_some) {
                    continue;
                }
                if sites.len() == Self::MAX_SITES {
                    return Self::default(); // Uncovered shape, never a truncated proof.
                }
                sites.push(Site {
                    frame,
                    op: op as u32,
                    fields: fields
                        .iter()
                        .map(|s| s.map(|s| shape.ports[frame][s]))
                        .collect(),
                });
            }
        }
        let mut plan = Self {
            complete: true,
            routes: vec![vec![]; sites.len()],
            inputs: vec![vec![]; shape.signals.len()],
            sites,
            conditions: vec![],
        };
        for (site, body) in plan.sites.iter().enumerate() {
            for (column, symbol) in body.fields[..body.fields.len() - 1].iter().enumerate() {
                if let Some(symbol) = symbol {
                    plan.inputs[*symbol].push((site, column));
                }
            }
        }
        for a in 0..plan.sites.len() {
            for b in a + 1..plan.sites.len() {
                let left = &plan.sites[a].fields;
                let right = &plan.sites[b].fields;
                if left.len() != right.len()
                    || left
                        .iter()
                        .zip(right)
                        .any(|(a, b)| a.is_some() != b.is_some())
                {
                    continue;
                }
                let (Some(&Some(u)), Some(&Some(v))) = (left.last(), right.last()) else {
                    continue;
                };
                let id = plan.conditions.len();
                plan.conditions.push(Condition {
                    sites: [a, b],
                    equality_inputs: left[..left.len() - 1]
                        .iter()
                        .zip(right)
                        .filter_map(|(a, b)| Some([(*a)?, (*b)?]))
                        .collect(),
                    scalar_columns: left[..left.len() - 1]
                        .iter()
                        .enumerate()
                        .filter_map(|(i, a)| a.is_none().then_some(i))
                        .collect(),
                    outputs: [u, v],
                });
                plan.routes[a].push(id);
                plan.routes[b].push(id);
            }
        }
        // The nested site order yields sorted other-sites for each route.
        plan
    }
    pub fn site(&self, frame: usize, op: u32) -> Option<usize> {
        self.sites
            .binary_search_by_key(&(frame, op), |s| (s.frame, s.op))
            .ok()
    }
}
