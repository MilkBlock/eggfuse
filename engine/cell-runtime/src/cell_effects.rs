//! The actual receipts of one executing Cell. Retained output slots come first
//! and become its publication storage without a copy. Boundary receipts follow
//! in the same frame and are released after completion.
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
    fn forwarded(&self) -> u64 { 0 }
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

// Keep the full u32 slot range. Only padding is removed; history is encoded
// as 0 (absent) or 1..=64. Copy packed fields by value, never borrow them.
#[repr(C, packed)]
#[derive(Clone, Copy, Default)]
struct EffectSlot { index:Option<NonZeroU32>, history:u8 }
pub(crate) struct EffectPlan {
    slots: Vec<EffectSlot>,
    width: usize,
    pub outputs: usize,
}
impl EffectPlan {
    pub fn compile(p: &Program, rule: usize, outputs: &[Output], published: usize, full: bool) -> Self {
        let cell = Definition::new(p, rule).expect("typed Cell");
        let mut plan = Self { slots: vec![EffectSlot::default(); cell.template.ops.len()], width: 0, outputs: published };
        // The retained prefix belongs to the actual producer, even when its
        // publication is attached to a later alias operation. Output::prepare
        // has already selected one last output per exact source.
        for output in &outputs[..published] {
            plan.require(match output.receipt_source {
                Some(Site::Effect(donor)) => donor,
                _ => output.operation,
            });
        }
        debug_assert_eq!(plan.width, published, "distinct retained Cell sources");
        // Every executor, including closed completion and first-miss resume,
        // skips these instructions. Their raw receipts are always absent, so
        // they need no transient slot. A retained query-alias publication may
        // still own a prefix slot above, filled only after history capture.
        let executes = |op: usize| !p.known_results.static_skip[rule][op];
        for output in outputs {
            if executes(output.operation) { plan.require(output.operation); }
        }
        for output in outputs {
            if let Some(Site::Effect(op)) = output.receipt_source { plan.require(op); }
        }
        #[cfg(feature = "iterative-bake")]
        for (slot,site) in p.iterative.exports(rule).iter().enumerate() {
            if let Site::Effect(op) = *site {
                if executes(op) {
                    plan.require(op);
                    if slot < 64 { plan.slots[op].history=slot as u8+1; }
                }
            }
        }
        if full {
            for op in 0..cell.template.ops.len() {
                if executes(op) && cell.relation(Site::Effect(op)).is_some() { plan.require(op); }
            }
        }
        plan
    }
    pub(crate) fn slot_bytes(&self) -> usize { self.slots.capacity()*std::mem::size_of::<EffectSlot>() }
    fn require(&mut self, op: usize) {
        let index = self.slots[op].index;
        if index.is_none() {
            self.width += 1;
            self.slots[op] = EffectSlot { index:Some(NonZeroU32::new(u32::try_from(self.width).expect("Cell receipt layout exhausted")).unwrap()), history:0 };
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
    forwarded: u64,
}
impl Effects {
    pub fn begin(plan: Rc<EffectPlan>, mut buffer: Vec<Option<Dependency>>, keep: bool) -> Self {
        let first = buffer.len();
        buffer.resize(first + plan.width, None);
        let keep = if keep { plan.outputs } else { 0 };
        Self { plan: Some(plan), buffer, first, keep, probes: 0, targets: 0, forwarded:0 }
    }
    pub fn slot(&mut self, operation: usize) -> Option<&mut Option<Dependency>> {
        let plan = self.plan.as_ref()?;
        self.probes += 1;
        let slot = plan.slots.get(operation)?.index?.get() as usize - 1;
        self.targets += 1;
        Some(&mut self.buffer[self.first + slot])
    }
    #[cfg(feature = "iterative-bake")]
    pub fn record_handoff(&mut self, operation:usize, receipt:Dependency, input:&crate::result_handoff::Input, original:bool, track:bool) {
        let Some(plan)=&self.plan else { return };
        self.probes+=1;
        let Some(slot)=plan.slots.get(operation) else { return };
        let Some(index)=slot.index else { return };
        self.targets+=1;
        self.buffer[self.first+index.get() as usize-1]=Some(receipt);
        // Provenance rides in the existing operation-to-slot descriptor: no
        // second index or per-instance source map is queried or maintained.
        if track && input.from_history && input.back==1 && original
            && let Some(history)=slot.history.checked_sub(1) { self.forwarded |= 1<<history; }
    }
    pub fn record(&mut self, operation: usize, receipt: Dependency) {
        if let Some(slot) = self.slot(operation) { *slot = Some(receipt); }
    }
    #[cfg(feature = "sparse-cells")]
    pub fn keeps_outputs(&self) -> bool { self.keep != 0 }
    #[cfg(feature = "sparse-cells")]
    pub fn output_first(&self) -> usize {
        assert!(self.keep != 0, "Cell outputs need a reserved completion span");
        self.first
    }
    /// Actual effect donors already occupy their final output slot. Query
    /// aliases are filled only after history captured the raw RHS.
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
    fn forwarded(&self) -> u64 { self.forwarded }
    const DEFERRED_KEYS: bool = true;
    fn get(&self, operation: usize) -> Option<Dependency> {
        let slot = self.plan.as_ref()?.slots.get(operation)?.index?.get() as usize - 1;
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

#[cfg(all(test, feature = "iterative-bake"))]
mod packed_slot_tests {
    use super::*;

    #[test]
    fn packed_descriptors_preserve_absence_and_both_history_mask_ends() {
        assert_eq!(std::mem::size_of::<EffectSlot>(), 5);
        let largest = EffectSlot { index:NonZeroU32::new(u32::MAX), history:64 };
        let index = largest.index;
        assert_eq!(index.unwrap().get(), u32::MAX, "slot range is not truncated");
        let plan = Rc::new(EffectPlan { slots:vec![EffectSlot::default(),
            EffectSlot { index:NonZeroU32::new(1), history:64 },
            EffectSlot { index:NonZeroU32::new(2), history:1 }], width:2, outputs:0 });
        let mut effects = Effects::begin(plan, vec![Some(Dependency::Function(99))], false);
        let mut input = crate::result_handoff::Input {
            op:1, back:1, fact:None, equal_output:false, from_history:true,
        };
        effects.record_handoff(1, Dependency::Function(7), &input, true, true);
        assert_eq!(effects.get(1), Some(Dependency::Function(7)));
        assert_eq!(effects.forwarded(), 1u64 << 63);
        input.op=2;
        effects.record_handoff(2, Dependency::Function(8), &input, true, true);
        assert_eq!(effects.get(2), Some(Dependency::Function(8)));
        assert_eq!(effects.forwarded(), (1u64 << 63)|1);
        effects.record(0, Dependency::Function(9));
        assert_eq!(effects.get(0), None);
        assert_eq!(effects.buffer[0], Some(Dependency::Function(99)));
    }
}
