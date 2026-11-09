//! Shared, bounded congruence conditions derived from checked symbolic wiring.
//! A program describes port layout, not operator identity. Runtime table tags
//! and scalar literals are explicit guards, never inferred from program IDs.
use super::*;

/// A shared port program can represent several operators. Take the union of
/// their typed tables; exclusions are valid only outside this complete set.
pub fn operators(templates: &[Template], markers: &[Marker], programs: &[Rc<PortProgram>]) -> Vec<Vec<Vec<usize>>> {
    let mut result = programs.iter().map(|p| vec![vec![]; p.fields.len()]).collect::<Vec<_>>();
    for (template, marker) in templates.iter().zip(markers) {
        for (op, instruction) in template.ops.iter().enumerate() {
            if marker.program.fields[op].is_empty() { continue; }
            let table = match instruction {
                Op::Let(_, Call::Table(table), _) | Op::Set(table, _, _) => *table,
                _ => unreachable!("a typed body must publish a table"),
            };
            result[marker.program_id][op].push(table);
        }
    }
    for program in &mut result {
        for tables in program {
            tables.sort_unstable();
            tables.dedup();
        }
    }
    result
}

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
    pub operator_pairs_elided: usize,
    pub reflexive_inputs_elided: usize,
    pub duplicate_inputs_elided: usize,
}
impl Plan {
    pub const MAX_SITES: usize = 16;
    pub fn derive(shape: &Shape, programs: &[Rc<PortProgram>], operators: &[Vec<Vec<usize>>]) -> Self {
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
            ..Self::default()
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
                let tables = |site: &Site| &operators[shape.programs[site.frame]][site.op as usize];
                if !tables(&plan.sites[a]).iter().any(|t| tables(&plan.sites[b]).binary_search(t).is_ok()) {
                    plan.operator_pairs_elided += 1;
                    continue;
                }
                let mut equality_inputs = Vec::new();
                for (a, b) in left[..left.len() - 1].iter().zip(right) {
                    let (Some(a), Some(b)) = (a, b) else { continue; };
                    if a == b {
                        plan.reflexive_inputs_elided += 1;
                        continue;
                    }
                    let pair = [*a.min(b), *a.max(b)];
                    if equality_inputs.contains(&pair) {
                        plan.duplicate_inputs_elided += 1;
                    } else {
                        // Keep the first field's order: it can be the cheapest
                        // failing guard. Symmetry only normalizes code identity.
                        equality_inputs.push(pair);
                    }
                }
                let id = plan.conditions.len();
                plan.conditions.push(Condition {
                    sites: [a, b],
                    equality_inputs,
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
