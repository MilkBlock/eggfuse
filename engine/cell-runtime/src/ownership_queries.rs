//! A bound field addresses shared template code directly. These routes contain
//! positions in immutable signal slices, never instance IDs or live consumers.
use super::*;

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Plan {
    /// Symbol -> column -> positions in Shape::signals[symbol].
    pub columns: Vec<Vec<Vec<usize>>>,
}
impl Plan {
    pub fn derive(shape: &Shape) -> Self {
        let columns = shape.signals.iter().map(|steps| {
            let mut columns = Vec::<Vec<usize>>::new();
            for (position, step) in steps.iter().enumerate() {
                for &column in step.columns.iter() {
                    columns.resize_with(columns.len().max(column + 1), Vec::new);
                    columns[column].push(position);
                }
            }
            columns
        }).collect();
        Self { columns }
    }
    pub fn positions(&self, symbol: usize, column: usize) -> &[usize] {
        self.columns[symbol].get(column).map_or(&[], Vec::as_slice)
    }
}
