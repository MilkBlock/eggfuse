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

#[derive(Clone, Copy)]
struct EffectSlot { index:NonZeroU32, history:Option<u8> }
pub(crate) struct EffectPlan {
    slots: Vec<Option<EffectSlot>>,
    width: usize,
    pub outputs: usize,
    #[cfg(feature = "sparse-cells")]
    registration: Option<Registration>,
}
/// A completed RHS has already written these retained effect results. Only
/// query aliases and uncovered boundaries still need individual registration.
/// This is shared template wiring, not a list maintained by each instance.
#[cfg(feature = "sparse-cells")]
struct Registration {
    query_aliases: Vec<usize>,
    direct: usize,
    aliases: usize,
}
#[cfg(feature = "sparse-cells")]
impl Registration {
    fn compile(p: &Program, rule: usize, outputs: &[Output], published: usize) -> Option<Self> {
        if published == 0 { return None; }
        let cell = Definition::new(p, rule).ok()?;
        let skip = p.known_results.static_skip.get(rule)?;
        let sources = p.known_results.static_sources.get(rule)?;
        let mut plan = Self { query_aliases: vec![], direct: 0, aliases: 0 };
        for (position, output) in outputs[..published].iter().enumerate() {
            if matches!(output.receipt_source, Some(Site::Query(_))) {
                plan.query_aliases.push(position);
                continue;
            }
            let donor = match output.receipt_source {
                Some(Site::Effect(donor)) => {
                    if !skip[output.operation] || sources[output.operation] != output.receipt_source { return None; }
                    plan.aliases += 1;
                    donor
                }
                None => output.operation,
                _ => unreachable!(),
            };
            // Successful ordinary, local-prefix and handoff execution all
            // record non-skipped relation results. An interrupted RHS never
            // seals a span. SourcePrefix without receipts is used only when
            // there is no publishing continuation.
            if *skip.get(donor)? || cell.relation(Site::Effect(donor))?.table != output.table { return None; }
            plan.direct += 1;
        }
        (plan.direct != 0).then_some(plan)
    }
}
impl EffectPlan {
    pub fn compile(p: &Program, rule: usize, outputs: &[Output], published: usize, full: bool) -> Self {
        let cell = Definition::new(p, rule).expect("typed Cell");
        let mut plan = Self { slots: vec![None; cell.template.ops.len()], width: 0, outputs: published,
            #[cfg(feature = "sparse-cells")]
            registration: Registration::compile(p, rule, outputs, published),
        };
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
        // Raw operation receipts remain distinct: closed completion may record
        // an alias, whereas ordinary execution skips it. History must observe
        // that distinction before publication fills any remaining output slots.
        for output in outputs { plan.require(output.operation); }
        for output in outputs {
            if let Some(Site::Effect(op)) = output.receipt_source { plan.require(op); }
        }
        #[cfg(feature = "iterative-bake")]
        for (slot,site) in p.iterative.exports(rule).iter().enumerate() {
            if let Site::Effect(op) = *site { plan.require(op); if slot < 64 { plan.slots[op].as_mut().unwrap().history=Some(slot as u8); } }
        }
        if full {
            for op in 0..cell.template.ops.len() {
                if cell.relation(Site::Effect(op)).is_some() { plan.require(op); }
            }
        }
        plan
    }
    pub(crate) fn slot_bytes(&self) -> usize { self.slots.capacity()*std::mem::size_of::<Option<EffectSlot>>() }
    pub(crate) fn registration_bytes(&self) -> usize {
        #[cfg(feature = "sparse-cells")]
        { std::mem::size_of::<Option<Registration>>() + self.registration.as_ref().map_or(0, |r|
            r.query_aliases.capacity() * std::mem::size_of::<usize>()) }
        #[cfg(not(feature = "sparse-cells"))]
        { 0 }
    }
    fn require(&mut self, op: usize) {
        if self.slots[op].is_none() {
            self.width += 1;
            self.slots[op] = Some(EffectSlot { index:NonZeroU32::new(u32::try_from(self.width).expect("Cell receipt layout exhausted")).unwrap(), history:None });
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
        let slot = plan.slots.get(operation)?.as_ref()?.index.get() as usize - 1;
        self.targets += 1;
        Some(&mut self.buffer[self.first + slot])
    }
    #[cfg(feature = "iterative-bake")]
    pub fn record_handoff(&mut self, operation:usize, receipt:Dependency, input:&crate::result_handoff::Input, original:bool, track:bool) {
        let Some(plan)=&self.plan else { return };
        self.probes+=1;
        let Some(Some(slot))=plan.slots.get(operation) else { return };
        self.targets+=1;
        self.buffer[self.first+slot.index.get() as usize-1]=Some(receipt);
        // Provenance rides in the existing operation-to-slot descriptor: no
        // second index or per-instance source map is queried or maintained.
        if track && input.from_history && input.back==1 && original
            && let Some(history)=slot.history { self.forwarded |= 1<<history; }
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
    /// Called only after successful execution and capture of raw RHS history.
    /// The retained arena is already the Entry delivery storage: seal once,
    /// without rereading each effect or registering each output separately.
    #[cfg(feature = "sparse-cells")]
    pub fn sealed_outputs(&self) -> Option<(usize, usize, usize, usize)> {
        if self.keep == 0 { return None; }
        let plan = self.plan.as_ref()?.registration.as_ref()?;
        debug_assert!((0..self.keep).all(|position| plan.query_aliases.contains(&position)
            || self.buffer[self.first + position].is_some()), "completed Cell must supply every proven effect result");
        Some((self.first, plan.direct, plan.aliases, plan.query_aliases.len()))
    }
    #[cfg(feature = "sparse-cells")]
    pub fn query_output(&self, index: usize) -> usize {
        self.plan.as_ref().unwrap().registration.as_ref().unwrap().query_aliases[index]
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
        let slot = self.plan.as_ref()?.slots.get(operation)?.as_ref()?.index.get() as usize - 1;
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
