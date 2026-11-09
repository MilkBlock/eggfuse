//! The actual receipts of one executing Cell. Required output slots come first
//! and can become the completed Cell's publication storage without a copy.
//! The buffer is lent exclusively by the source-scheduled executor; no Entry
//! can observe its unsealed suffix. Aborted RHS execution discards that suffix.
use super::{Definition, Output, Site};
use crate::{graph::Dependency, program::Program};
use std::{num::NonZeroU32, rc::Rc};

/// The completion interface is independent of receipt storage. Single writes
/// carry their one actual return inline; other Cells can retain an arena span.
/// Static dispatch keeps the inline case allocation-free.
pub(crate) trait CompletedEffects {
    const DEFERRED_KEYS: bool;
    fn get(&self, operation: usize) -> Option<Dependency>;
    #[cfg(feature = "sparse-cells")]
    fn output_frame(&mut self) -> Option<&mut Effects>;
    fn finish(self, publish: bool) -> Option<(Vec<Option<Dependency>>, usize, u64, u64)>;
}
pub(crate) struct SingleEffect(pub usize, pub Dependency);
impl CompletedEffects for SingleEffect {
    const DEFERRED_KEYS: bool = false;
    fn get(&self, operation: usize) -> Option<Dependency> {
        (operation == self.0).then_some(self.1)
    }
    #[cfg(feature = "sparse-cells")]
    fn output_frame(&mut self) -> Option<&mut Effects> { None }
    fn finish(self, _: bool) -> Option<(Vec<Option<Dependency>>, usize, u64, u64)> { None }
}

pub(crate) struct EffectPlan {
    slots: Vec<Option<NonZeroU32>>,
    width: usize,
    pub outputs: usize,
}
impl EffectPlan {
    pub fn compile(p: &Program, rule: usize, outputs: &[Output], full: bool) -> Self {
        let cell = Definition::new(p, rule).expect("typed Cell");
        let mut plan = Self { slots: vec![None; cell.template.ops.len()], width: 0, outputs: outputs.len() };
        for output in outputs { plan.require(output.operation); }
        for output in outputs {
            if let Some(Site::Effect(op)) = output.receipt_source { plan.require(op); }
        }
        #[cfg(feature = "iterative-bake")]
        for site in p.iterative.exports(rule) {
            if let Site::Effect(op) = *site { plan.require(op); }
        }
        if full {
            for op in 0..cell.template.ops.len() {
                if cell.relation(Site::Effect(op)).is_some() { plan.require(op); }
            }
        }
        plan
    }
    fn require(&mut self, op: usize) {
        if self.slots[op].is_none() {
            self.width += 1;
            self.slots[op] = Some(NonZeroU32::new(u32::try_from(self.width).expect("Cell receipt layout exhausted")).unwrap());
        }
    }
}

#[derive(Default)]
pub(crate) struct Effects {
    plan: Option<Rc<EffectPlan>>,
    buffer: Vec<Option<Dependency>>,
    first: usize,
    keep: usize,
    probes: u64,
    targets: u64,
}
impl Effects {
    pub fn begin(plan: Rc<EffectPlan>, mut buffer: Vec<Option<Dependency>>, keep: bool) -> Self {
        let first = buffer.len();
        buffer.resize(first + plan.width, None);
        let keep = if keep { plan.outputs } else { 0 };
        Self { plan: Some(plan), buffer, first, keep, probes: 0, targets: 0 }
    }
    pub fn slot(&mut self, operation: usize) -> Option<&mut Option<Dependency>> {
        let plan = self.plan.as_ref()?;
        self.probes += 1;
        let slot = plan.slots.get(operation)?.as_ref()?.get() as usize - 1;
        self.targets += 1;
        Some(&mut self.buffer[self.first + slot])
    }
    pub fn record(&mut self, operation: usize, receipt: Dependency) {
        if let Some(slot) = self.slot(operation) { *slot = Some(receipt); }
    }
    #[cfg(feature = "sparse-cells")]
    pub fn output_first(&self) -> usize {
        assert!(self.keep != 0, "Cell outputs need a reserved completion span");
        self.first
    }
    /// Actual effect returns already occupy their final output slot. A skipped
    /// effect's proven alias is filled only after history captured the raw RHS.
    #[cfg(feature = "sparse-cells")]
    pub fn retain_output(&mut self, position: usize, receipt: Dependency) -> bool {
        assert!(position < self.keep);
        let slot = &mut self.buffer[self.first + position];
        if let Some(old) = *slot {
            debug_assert_eq!(old, receipt);
            false
        } else {
            *slot = Some(receipt);
            true
        }
    }
}
impl CompletedEffects for Effects {
    const DEFERRED_KEYS: bool = true;
    fn get(&self, operation: usize) -> Option<Dependency> {
        let slot = self.plan.as_ref()?.slots.get(operation)?.as_ref()?.get() as usize - 1;
        self.buffer[self.first + slot]
    }
    #[cfg(feature = "sparse-cells")]
    fn output_frame(&mut self) -> Option<&mut Effects> { Some(self) }
    fn finish(mut self, publish: bool) -> Option<(Vec<Option<Dependency>>, usize, u64, u64)> {
        let plan = self.plan.take()?;
        self.buffer.truncate(self.first + if publish { self.keep } else { 0 });
        Some((self.buffer, plan.width, self.probes, self.targets))
    }
}
