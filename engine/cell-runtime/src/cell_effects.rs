//! The actual receipts of one executing Cell. Retained output slots come first
//! and become its publication storage without a copy. Boundary receipts follow
//! in the same frame and are released after completion.
//! Each execution owns its buffer; no unrelated pending publication is borrowed.
//! Completion moves the retained prefix into its delivery without copying slots.
use super::{Definition, Output, Site};
use crate::{graph::Dependency, program::Program};
use std::{num::NonZeroU32, sync::Arc};
#[cfg(feature="sparse-cells")]
use std::cell::Cell;

/// The completion interface is independent of receipt storage. Single writes
/// carry their one actual return inline; other Cells own their result buffers.
/// Static dispatch keeps the inline case allocation-free.
pub(crate) trait CompletedEffects {
    const DEFERRED_KEYS: bool;
    fn forwarded(&self) -> u64 { 0 }
    fn get(&self, operation: usize) -> Option<Dependency>;
    #[cfg(feature = "sparse-cells")]
    fn output_frame(&mut self) -> Option<&mut Effects>;
    #[cfg(feature = "sparse-cells")]
    fn sealed_outputs(&mut self) -> Option<(usize, usize, usize)> {
        Effects::sealed_outputs(self.output_frame()?)
    }
    #[cfg(feature = "sparse-cells")]
    fn has_joint_results(&mut self) -> bool {
        self.output_frame().is_some_and(|frame| Effects::has_joint_results(frame))
    }
    #[cfg(feature = "sparse-cells")]
    fn take_results(&mut self, rule: usize) -> Option<super::Results> {
        Effects::take_results(self.output_frame()?, rule)
    }
    fn finish(self, publish: bool) -> Option<(Vec<Option<Dependency>>, usize, u64, u64)>;
}

/// A specialized Cell completes through the same publication interface as an
/// executed RHS. It owns a view of actual results, never a second receipt array.
#[cfg(feature = "sparse-cells")]
pub(crate) struct ProjectedEffects {
    pub results: Option<super::Results>,
    pub plan: Option<Arc<EffectPlan>>,
    pub published: usize,
}
#[cfg(feature = "sparse-cells")]
impl CompletedEffects for ProjectedEffects {
    const DEFERRED_KEYS: bool = false;
    fn get(&self, operation: usize) -> Option<Dependency> {
        self.results.as_ref()?.output(self.plan.as_ref()?.history_effect(operation)?)
    }
    fn output_frame(&mut self) -> Option<&mut Effects> { None }
    fn sealed_outputs(&mut self) -> Option<(usize, usize, usize)> {
        (self.published != 0).then_some((self.published, 0, 0))
    }
    fn has_joint_results(&mut self) -> bool { true }
    fn take_results(&mut self, _: usize) -> Option<super::Results> { self.results.take() }
    fn finish(self, _: bool) -> Option<(Vec<Option<Dependency>>, usize, u64, u64)> { None }
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
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
struct EffectSlot { index:Option<NonZeroU32>, history:u8 }
/// One immutable operation-to-result layout, shared by worker preparation and
/// source effects. Result owners move to workers with this immutable plan; Cursors stay source-local.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct EffectLayout {
    slots: Vec<EffectSlot>,
    width: usize,
}
impl EffectLayout {
    pub(crate) fn width(&self) -> usize { self.width }
    pub(crate) fn index(&self, operation: usize) -> Option<usize> {
        self.slots.get(operation)?.index.map(|i| i.get() as usize - 1)
    }
}
pub(crate) struct EffectPlan {
    pub(crate) layout: Arc<EffectLayout>,
    pub outputs: usize,
    #[cfg(feature = "sparse-cells")]
    registration: Option<Registration>,
    #[cfg(feature = "sparse-cells")]
    joint: Option<Box<JointResults>>,
}
/// Full history exports and permanent publication slots can share a bounded
/// Cell frame. Remaining boundary publication still uses its original path.
#[cfg(feature = "sparse-cells")]
struct JointResults {
    width: usize,
    queries: Vec<(usize, usize)>,
    outputs: Vec<usize>,
    transient: Vec<Option<usize>>,
    transient_width: usize,
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
        let mut plan = Self { layout: Arc::new(EffectLayout {
                slots: vec![EffectSlot::default(); cell.template.ops.len()], width: 0 }), outputs: published,
            #[cfg(feature = "sparse-cells")]
            registration: Registration::compile(p, rule, outputs, published),
            #[cfg(feature = "sparse-cells")]
            joint: None,
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
        debug_assert_eq!(plan.layout.width, published, "distinct retained Cell sources");
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
                    if slot < 64 { Arc::get_mut(&mut plan.layout).unwrap().slots[op].history=slot as u8+1; }
                }
            }
        }
        if full {
            for op in 0..cell.template.ops.len() {
                if executes(op) && cell.relation(Site::Effect(op)).is_some() { plan.require(op); }
            }
        }
        // Composition reads the same actual-result array as worker preparation,
        // RHS and publication. Demand only eligible prefix sites, never a full
        // instruction history; existing export slots are reused by require().
        #[cfg(feature = "sparse-cells")]
        if let Some(prefix)=p.executions.get(rule).and_then(|execution|execution.constructor.as_ref()) {
            for op in prefix.entry_operations() {plan.require(op);}
        }
        #[cfg(feature = "sparse-cells")]
        if published != 0 && published <= 32
            && plan.registration.as_ref().is_some_and(|r| r.direct == published)
        {
            let mut queries = Vec::new();
            let exports = p.iterative.exports(rule);
            for (slot, site) in exports.iter().enumerate() {
                if let Site::Query(atom) = *site { queries.push((atom, slot)); }
            }
            let output_ports = outputs[..published].iter().map(|output| {
                let source = output.receipt_source.unwrap_or(Site::Effect(output.operation));
                exports.binary_search(&source).ok()
            }).collect::<Option<Vec<_>>>();
            if exports.len() <= 64 && output_ports.is_some()
                && matches!(exports.last(), Some(Site::Effect(op)) if !p.known_results.static_skip[rule][*op])
            {
                let mut transient = vec![None; plan.layout.width];
                let mut transient_width = 0;
                for (op, slot) in plan.layout.slots.iter().enumerate() {
                    if let Some(index) = slot.index && slot.history == 0 && executes(op) {
                        transient[index.get() as usize - 1] = Some(transient_width);
                        transient_width += 1;
                    }
                }
                plan.joint = Some(Box::new(JointResults { width: exports.len(), queries,
                    outputs: output_ports.unwrap(), transient, transient_width }));
            }
        }
        plan
    }
    #[cfg(feature = "sparse-cells")]
    pub fn joint_width(&self) -> Option<usize> { self.joint.as_ref().map(|p| p.width) }
    #[cfg(feature = "sparse-cells")]
    pub fn history_output(&self, position: usize) -> usize { self.joint.as_ref().unwrap().outputs[position] }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn history_effect(&self, operation:usize) -> Option<usize> {
        self.layout.slots.get(operation)?.history.checked_sub(1).map(usize::from)
    }
    pub(crate) fn joint_bytes(&self) -> usize {
        #[cfg(feature = "sparse-cells")]
        { std::mem::size_of::<Option<Box<JointResults>>>() + self.joint.as_ref().map_or(0, |j|
            std::mem::size_of::<JointResults>() + j.outputs.capacity() * std::mem::size_of::<usize>()
            + j.transient.capacity() * std::mem::size_of::<Option<usize>>()
            + j.queries.capacity() * std::mem::size_of::<(usize, usize)>()) }
        #[cfg(not(feature = "sparse-cells"))]
        { 0 }
    }
    pub(crate) fn slot_bytes(&self) -> usize { self.layout.slots.capacity()*std::mem::size_of::<EffectSlot>() }
    pub(crate) fn registration_bytes(&self) -> usize {
        #[cfg(feature = "sparse-cells")]
        { std::mem::size_of::<Option<Registration>>() + self.registration.as_ref().map_or(0, |r|
            r.query_aliases.capacity() * std::mem::size_of::<usize>()) }
        #[cfg(not(feature = "sparse-cells"))]
        { 0 }
    }
    fn require(&mut self, op: usize) {
        let layout = Arc::get_mut(&mut self.layout).expect("layout is shared only after compilation");
        let index = layout.slots[op].index;
        if index.is_none() {
            layout.width += 1;
            layout.slots[op] = EffectSlot { index:Some(NonZeroU32::new(u32::try_from(layout.width).expect("Cell receipt layout exhausted")).unwrap()), history:0 };
        }
    }
}

#[derive(Default)]
pub(crate) struct Effects {
    plan: Option<Arc<EffectPlan>>,
    buffer: Vec<Option<Dependency>>,
    keep: usize,
    probes: u64,
    targets: u64,
    forwarded: u64,
    #[cfg(feature = "sparse-cells")]
    joint: bool,
    #[cfg(feature = "sparse-cells")]
    prepared_buffer: bool,
    #[cfg(feature = "sparse-cells")]
    history: Vec<Cell<Option<Dependency>>>,
}
impl Effects {
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn writer(&mut self) -> EffectWriter<'_> {
        EffectWriter { plan:self.plan.as_deref(), buffer:&mut self.buffer,
            history:&mut self.history, joint:self.joint, probes:&mut self.probes, targets:&mut self.targets }
    }
    pub fn begin(plan: Arc<EffectPlan>, mut buffer: Vec<Option<Dependency>>, keep: bool) -> Self {
        debug_assert!(buffer.is_empty(), "each Cell owns only its results");
        buffer.resize(plan.layout.width, None);
        let keep = if keep { plan.outputs } else { 0 };
        Self { plan: Some(plan), buffer, keep, probes: 0, targets: 0, forwarded:0,
            #[cfg(feature = "sparse-cells")] joint:false,
            #[cfg(feature = "sparse-cells")] prepared_buffer:false,
            #[cfg(feature = "sparse-cells")] history:vec![] }
    }
    #[cfg(feature = "sparse-cells")]
    pub fn begin_joint(plan: Arc<EffectPlan>, mut buffer: Vec<Option<Dependency>>, facts: &super::QueryFacts) -> (Self, usize) {
        debug_assert!(buffer.is_empty(), "joint results own only private transient scratch");
        let joint = plan.joint.as_ref().unwrap();
        buffer.resize(joint.transient_width, None);
        let history = vec![Cell::new(None); joint.width];
        for &(atom, slot) in &joint.queries { history[slot].set(facts.receipt(atom)); }
        let reads = joint.queries.len();
        let keep = plan.outputs;
        (Self { plan: Some(plan), buffer, keep, probes: 0, targets: 0, forwarded: 0, joint: true, prepared_buffer:false, history }, reads)
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn adopt(plan: Arc<EffectPlan>, buffer: Vec<Option<Dependency>>, keep: bool) -> Self {
        assert_eq!(buffer.len(), plan.layout.width, "checked worker result layout");
        let keep = if keep { plan.outputs } else { 0 };
        Self { plan:Some(plan), buffer, keep, probes:0, targets:0, forwarded:0,
            joint:false, prepared_buffer:true, history:vec![] }
    }
    /// Preserve the existing joint-history path when it selects a different
    /// result layout. Ordinary prepared frames transfer their allocation whole.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn import_prepared(&mut self, buffer: &[Option<Dependency>]) -> (usize, usize, usize) {
        let plan = self.plan.clone().expect("joint result plan");
        assert_eq!(buffer.len(), plan.layout.width);
        let (mut reads, mut writes) = (0, 0);
        for (op, slot) in plan.layout.slots.iter().enumerate() {
            if let Some(index) = slot.index {
                reads += 1;
                if let Some(result) = buffer[index.get() as usize - 1] {
                    self.record(op, result);
                    writes += 1;
                }
            }
        }
        (plan.layout.slots.len(), reads, writes)
    }
    pub fn scratch_capacity_bytes(&self) -> usize {
        self.buffer.capacity() * std::mem::size_of::<Option<Dependency>>()
    }
    #[cfg(feature = "sparse-cells")]
    pub fn take_results(&mut self, rule: usize) -> Option<super::Results> {
        self.joint.then(|| super::Results::from_outputs(rule, std::mem::take(&mut self.history)))
    }
    #[cfg(feature = "sparse-cells")]
    pub fn has_joint_results(&self) -> bool { self.joint }
    pub fn slot(&mut self, operation: usize) -> Option<&mut Option<Dependency>> {
        #[cfg(feature = "sparse-cells")]
        { return self.writer().into_slot(operation); }
        #[cfg(not(feature = "sparse-cells"))]
        {
        let plan = self.plan.as_ref()?;
        self.probes += 1;
        let descriptor = *plan.layout.slots.get(operation)?;
        let slot = descriptor.index?.get() as usize - 1;
        self.targets += 1;
        Some(&mut self.buffer[slot])
        }
    }
    #[cfg(feature = "iterative-bake")]
    pub fn record_handoff(&mut self, operation:usize, receipt:Dependency, input:&crate::result_handoff::Input, original:bool, track:bool) {
        let Some(plan)=&self.plan else { return };
        self.probes+=1;
        let Some(slot)=plan.layout.slots.get(operation) else { return };
        let Some(index)=slot.index else { return };
        self.targets+=1;
        #[cfg(feature = "sparse-cells")]
        if self.joint {
            if slot.history != 0 { self.history[slot.history as usize - 1].set(Some(receipt)); }
            else if let Some(index) = plan.joint.as_ref().unwrap().transient[index.get() as usize - 1] {
                self.buffer[index] = Some(receipt);
            }
            return;
        }
        self.buffer[index.get() as usize-1]=Some(receipt);
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
    /// Called only after successful execution and capture of raw RHS history.
    /// The retained prefix becomes the Entry delivery storage: seal once,
    /// without rereading each effect or registering each output separately.
    #[cfg(feature = "sparse-cells")]
    pub fn sealed_outputs(&self) -> Option<(usize, usize, usize)> {
        if self.keep == 0 { return None; }
        let plan = self.plan.as_ref()?.registration.as_ref()?;
        debug_assert!((0..self.keep).all(|position| plan.query_aliases.contains(&position)
            || if self.joint { self.history[self.plan.as_ref().unwrap().history_output(position)].get().is_some() }
               else { self.buffer[position].is_some() }), "completed Cell must supply every proven effect result");
        Some((plan.direct, plan.aliases, plan.query_aliases.len()))
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
        let slot = &mut self.buffer[position];
        if let Some(old) = *slot {
            debug_assert_eq!(old, receipt);
            false
        } else {
            *slot = Some(receipt);
            true
        }
    }
}

/// Borrow the existing output slots on their execution owner. The immutable
/// plan is shared through Arc; the unique result arrays travel with the Cell,
/// without another result packet or layout conversion.
#[cfg(feature = "sparse-cells")]
pub(crate) struct EffectWriter<'a> {
    plan: Option<&'a EffectPlan>,
    buffer: &'a mut Vec<Option<Dependency>>,
    history: &'a mut Vec<Cell<Option<Dependency>>>,
    joint: bool,
    probes: &'a mut u64,
    targets: &'a mut u64,
}
#[cfg(feature = "sparse-cells")]
impl<'a> EffectWriter<'a> {
    fn into_slot(self, operation:usize) -> Option<&'a mut Option<Dependency>> {
        let plan=self.plan?;
        *self.probes+=1;
        let descriptor=*plan.layout.slots.get(operation)?;
        let slot=descriptor.index?.get() as usize-1;
        let slot=if self.joint {
            if descriptor.history!=0 {
                *self.targets+=1;
                return self.history.get_mut(descriptor.history as usize-1).map(Cell::get_mut);
            }
            plan.joint.as_ref()?.transient[slot]?
        } else {slot};
        *self.targets+=1;
        Some(&mut self.buffer[slot])
    }
    pub(crate) fn record(&mut self, operation:usize, result:Dependency) {
        if let Some(slot)=(EffectWriter { plan:self.plan, buffer:self.buffer, history:self.history,
            joint:self.joint, probes:self.probes, targets:self.targets }).into_slot(operation) {
            *slot=Some(result);
        }
    }
}
impl CompletedEffects for Effects {
    fn forwarded(&self) -> u64 { self.forwarded }
    const DEFERRED_KEYS: bool = true;
    fn get(&self, operation: usize) -> Option<Dependency> {
        let plan = self.plan.as_ref()?;
        let descriptor = *plan.layout.slots.get(operation)?;
        let slot = descriptor.index?.get() as usize - 1;
        #[cfg(feature = "sparse-cells")]
        let slot = if self.joint {
            if descriptor.history != 0 { return self.history.get(descriptor.history as usize - 1).and_then(Cell::get); }
            plan.joint.as_ref()?.transient[slot]?
        } else { slot };
        self.buffer[slot]
    }
    #[cfg(feature = "sparse-cells")]
    fn output_frame(&mut self) -> Option<&mut Effects> { Some(self) }
    fn finish(mut self, publish: bool) -> Option<(Vec<Option<Dependency>>, usize, u64, u64)> {
        let plan = self.plan.take()?;
        #[cfg(feature = "sparse-cells")]
        if self.joint {
            self.buffer.clear();
            let joint = plan.joint.as_ref().unwrap();
            return Some((self.buffer, joint.width + joint.transient_width, self.probes, self.targets));
        }
        self.buffer.truncate(if publish { self.keep } else { 0 });
        #[cfg(feature = "sparse-cells")]
        let initialized = if self.prepared_buffer { 0 } else { plan.layout.width };
        #[cfg(not(feature = "sparse-cells"))]
        let initialized = plan.layout.width;
        Some((self.buffer, initialized, self.probes, self.targets))
    }
}

#[cfg(all(test, feature = "iterative-bake"))]
mod packed_slot_tests {
    use super::*;

    #[cfg(feature = "sparse-cells")]
    #[test]
    fn prepared_results_keep_their_allocation_through_effects_and_publication_and_joint_fallback() {
        let foreign = Dependency::Fact(crate::graph::FactRef { cell:77, op:9 });
        let plan = Arc::new(EffectPlan {
            layout:Arc::new(EffectLayout { slots:vec![
                EffectSlot { index:NonZeroU32::new(2), history:1 },
                EffectSlot { index:NonZeroU32::new(1), history:2 }], width:2 }),
            outputs:2,
            registration:Some(Registration {query_aliases:vec![],direct:2,aliases:0}),
            joint:Some(Box::new(JointResults {width:2,queries:vec![],outputs:vec![1,0],
                transient:vec![None;2],transient_width:0})),
        });
        let prepared = vec![None,Some(foreign)];
        let allocation = prepared.as_ptr();
        let mut effects = Effects::adopt(plan.clone(),prepared,true);
        assert_eq!(effects.get(0),Some(foreign));
        assert_eq!(effects.get(1),None);
        effects.record(1,Dependency::Function(8));
        assert_eq!(effects.sealed_outputs(),Some((2,0,0)));
        let (published, initialized, probes, targets) = effects.finish(true).unwrap();
        assert_eq!(published.as_ptr(),allocation);
        assert_eq!(published,vec![Some(Dependency::Function(8)),Some(foreign)]);
        assert_eq!((initialized,probes,targets),(0,1,1));
        let (mut joint,_) = Effects::begin_joint(plan,vec![],&super::super::QueryFacts::None);
        assert_eq!(joint.import_prepared(&published),(2,2,2));
        assert_eq!(joint.get(0),Some(foreign));
        assert_eq!(joint.get(1),Some(Dependency::Function(8)));
        let history = joint.take_results(0).unwrap();
        assert_eq!(history.output(0),Some(foreign));
        assert_eq!(history.output(1),Some(Dependency::Function(8)));
    }

    #[cfg(feature = "sparse-cells")]
    #[test]
    fn simultaneous_joint_frames_keep_separate_results_and_private_transients() {
        let plan = Arc::new(EffectPlan {
            layout: Arc::new(EffectLayout { slots: vec![EffectSlot { index: NonZeroU32::new(1), history: 1 },
                EffectSlot { index: NonZeroU32::new(2), history: 0 }],
                width: 2 }), outputs: 1,
            registration: Some(Registration { query_aliases: vec![], direct: 1, aliases: 0 }),
            joint: Some(Box::new(JointResults { width: 1, queries: vec![], outputs: vec![0],
                transient: vec![None, Some(0)], transient_width: 1 })),
        });
        let (mut a, _) = Effects::begin_joint(plan.clone(), vec![], &super::super::QueryFacts::None);
        let (mut b, _) = Effects::begin_joint(plan, vec![], &super::super::QueryFacts::None);
        for (frame, base) in [(&mut a, 10), (&mut b, 20)] {
            frame.record(0, Dependency::Fact(crate::graph::FactRef { cell: base, op: 7 }));
            frame.record(1, Dependency::Function(base as usize));
        }
        assert_eq!(a.get(1), Some(Dependency::Function(10)));
        assert_eq!(b.get(1), Some(Dependency::Function(20)));
        assert_eq!(a.sealed_outputs(), Some((1, 0, 0)));
        assert_eq!(b.sealed_outputs(), Some((1, 0, 0)));
        let a_result = a.take_results(0).unwrap();
        let b_result = b.take_results(0).unwrap();
        let (a_scratch, _, _, _) = a.finish(true).unwrap();
        let (b_scratch, _, _, _) = b.finish(true).unwrap();
        assert!(a_scratch.is_empty() && b_scratch.is_empty());
        assert_eq!(a_result.output(0), Some(Dependency::Fact(crate::graph::FactRef { cell: 10, op: 7 })));
        assert_eq!(b_result.output(0), Some(Dependency::Fact(crate::graph::FactRef { cell: 20, op: 7 })));
    }

    #[test]
    fn packed_descriptors_preserve_absence_and_both_history_mask_ends() {
        assert_eq!(std::mem::size_of::<EffectSlot>(), 5);
        let largest = EffectSlot { index:NonZeroU32::new(u32::MAX), history:64 };
        let index = largest.index;
        assert_eq!(index.unwrap().get(), u32::MAX, "slot range is not truncated");
        let plan = Arc::new(EffectPlan { layout:Arc::new(EffectLayout { slots:vec![EffectSlot::default(),
            EffectSlot { index:NonZeroU32::new(1), history:64 },
            EffectSlot { index:NonZeroU32::new(2), history:1 }], width:2 }), outputs:0,
            #[cfg(feature = "sparse-cells")] registration:None,
            #[cfg(feature = "sparse-cells")] joint:None });
        let mut effects = Effects::begin(plan, vec![], false);
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
        assert_eq!(effects.buffer, vec![Some(Dependency::Function(7)), Some(Dependency::Function(8))]);
    }
}
