//! A bound field addresses shared template code directly. These routes contain
//! positions in immutable signal slices, never instance IDs or live consumers.
use super::*;

/// The low bit records an input use. One word replaces the separate condition
/// input directory without widening each stored query position.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Position(usize);
impl Position {
    fn new(index: usize, input: bool) -> Self {
        assert!(index <= usize::MAX / 2);
        Self((index << 1) | usize::from(input))
    }
}
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Plan {
    /// Symbol -> column -> positions in Shape::signals[symbol].
    pub columns: Vec<Arc<Vec<Vec<Position>>>>,
}
impl Plan {
    pub fn derive(shape: &Shape, programs: &[Arc<PortProgram>]) -> Self {
        let columns = shape
            .signals
            .iter()
            .enumerate()
            .map(|(symbol, steps)| {
                let mut columns = Vec::<Vec<Position>>::new();
                for (position, step) in steps.iter().enumerate() {
                    let width = programs[shape.programs[step.frame]].fields[step.op as usize].len();
                    for column in shape.columns(programs, symbol, step) {
                        columns.resize_with(columns.len().max(column + 1), Vec::new);
                        columns[column].push(Position::new(position, column + 1 < width));
                    }
                }
                Arc::new(columns)
            })
            .collect();
        Self { columns }
    }
    /// Content-address only immutable relative positions and input-use bits.
    /// The caller's shape still supplies the actual instruction/frame identity.
    pub(super) fn share_columns(&mut self, shared: &mut std::collections::HashSet<Arc<Vec<Vec<Position>>>>) {
        for columns in &mut self.columns {
            if let Some(existing) = shared.get(columns) {
                *columns = existing.clone();
            } else {
                shared.insert(columns.clone());
            }
        }
    }
    fn positions(&self, symbol: usize, column: usize) -> &[Position] {
        self.columns[symbol].get(column).map_or(&[], Vec::as_slice)
    }
}

/// A borrowed Cell field-use view. It names potential sites in shared code;
/// each caller still checks operator, current liveness and its own proof budget.
/// Unseen training shapes retain their complete unindexed wiring.
pub(in crate::graph::cell_ownership) struct FieldUses<'a> {
    component: &'a Component,
    shape: &'a Shape,
    steps: &'a [Instruction],
    positions: Option<&'a [Position]>,
    programs: &'a [Arc<PortProgram>],
    operators: &'a [Vec<usize>],
    column: usize,
    symbol: usize,
}
impl FieldUses<'_> {
    /// A shared layout may prove a table without consulting the instance directory.
    pub fn known_operator(&self, position: usize) -> Option<usize> {
        let index = self.positions.map_or(position, |p| p[position].0 >> 1);
        let step = &self.steps[index];
        let operator = *self.operators.get(self.shape.programs[step.frame])?.get(step.op as usize)?;
        (operator != usize::MAX).then_some(operator)
    }
    pub fn indexed(&self) -> bool {
        self.positions.is_some()
    }
    pub fn len(&self) -> usize {
        self.positions.map_or(self.steps.len(), <[_]>::len)
    }
    // Each caller fixes the access mode. Keep this projection in the candidate
    // loop: ordinary inline hints still left calls in local lookup and union.
    #[inline(always)]
    pub fn fact(&self, position: usize, inputs_only: bool) -> Option<FactRef> {
        let step = if let Some(positions) = self.positions {
            let Position(encoded) = positions[position];
            if inputs_only && encoded & 1 == 0 {
                return None;
            }
            &self.steps[encoded >> 1]
        } else {
            let step = &self.steps[position];
            if !self.shape.columns(self.programs, self.symbol, step).any(|column|column == self.column) {
                return None;
            }
            if inputs_only {
                let width =
                    self.programs[self.shape.programs[step.frame]].fields[step.op as usize].len();
                if self.column + 1 >= width {
                    return None;
                }
            }
            step
        };
        Some(FactRef {
            cell: self.component.frames[step.frame],
            op: step.op,
        })
    }
}
impl<'a> FieldUses<'a> {
    pub(in crate::graph::cell_ownership) fn new(component: &'a Component, shape: &'a Shape, plan: &'a super::super::Plan,
        symbol: usize, column: usize) -> Self {
        Self { component, shape, steps: &shape.signals[symbol],
            positions: plan.composition.queries.get(component.shape).map(|p| p.positions(symbol, column)),
            programs: &plan.programs, operators: &plan.layout_operators, column, symbol }
    }
}
impl Graph {
    #[inline]
    pub(in crate::graph::cell_ownership) fn cell_field_uses(
        &self,
        signal: Signal,
        column: usize,
    ) -> Result<FieldUses<'_>> {
        let owner = &self.ownership.as_ref().unwrap().composition;
        let component = owner
            .components
            .get(signal.component as usize)
            .and_then(Option::as_ref)
            .ok_or("expired field-use component")?;
        let shape = owner
            .shapes
            .get(component.shape)
            .and_then(Option::as_ref)
            .ok_or("missing field-use shape")?;
        let plan = &self.program.cell_ownership;
        Ok(FieldUses::new(component, shape, plan, signal.symbol, column))
    }
}
