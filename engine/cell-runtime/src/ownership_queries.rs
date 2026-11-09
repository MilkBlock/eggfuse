//! A bound field addresses shared template code directly. These routes contain
//! positions in immutable signal slices, never instance IDs or live consumers.
use super::*;

/// The low bit records an input use. One word replaces the separate condition
/// input directory without widening each stored query position.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
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
    pub columns: Vec<Vec<Vec<Position>>>,
}
impl Plan {
    pub fn derive(shape: &Shape, programs: &[Rc<PortProgram>]) -> Self {
        let columns = shape
            .signals
            .iter()
            .map(|steps| {
                let mut columns = Vec::<Vec<Position>>::new();
                for (position, step) in steps.iter().enumerate() {
                    let width = programs[shape.programs[step.frame]].fields[step.op as usize].len();
                    for &column in step.columns.iter() {
                        columns.resize_with(columns.len().max(column + 1), Vec::new);
                        columns[column].push(Position::new(position, column + 1 < width));
                    }
                }
                columns
            })
            .collect();
        Self { columns }
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
    programs: &'a [Rc<PortProgram>],
    column: usize,
}
impl FieldUses<'_> {
    pub fn indexed(&self) -> bool {
        self.positions.is_some()
    }
    pub fn len(&self) -> usize {
        self.positions.map_or(self.steps.len(), <[_]>::len)
    }
    // Each caller fixes the access mode. Inline the borrowed projection so
    // candidate loops specialize that mode without a call or view reload.
    #[inline]
    pub fn fact(&self, position: usize, inputs_only: bool) -> Option<FactRef> {
        let step = if let Some(positions) = self.positions {
            let Position(encoded) = positions[position];
            if inputs_only && encoded & 1 == 0 {
                return None;
            }
            &self.steps[encoded >> 1]
        } else {
            let step = &self.steps[position];
            if !step.columns.contains(&self.column) {
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
        Ok(FieldUses {
            component,
            shape,
            steps: &shape.signals[signal.symbol],
            positions: plan
                .composition
                .queries
                .get(component.shape)
                .map(|p| p.positions(signal.symbol, column)),
            programs: &plan.programs,
            column,
        })
    }
}
