//! Actual results retained by a Cell for its compiled consumers. The template
//! owns the source-to-slot mapping; instances store only the returned references.
//! A reference is a location to revalidate, not a cached value or liveness proof.
//! Shared slots permit same-key forwarding in this serial Rc history. This is
//! not a concurrent mutation interface; consuming Runs still check validity.
use super::Site;
use crate::graph::Dependency;
use serde::{Serialize, Serializer};
use smallvec::SmallVec;
use std::{cell::Cell, num::NonZeroU32, rc::Rc};
use crate::result_handoff::Trail;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub(crate) struct ResultPort {
    rule: u32,
    slot: NonZeroU32,
}

#[cfg(all(test, feature = "sparse-cells"))]
mod joint_tests {
    use super::*;
    use crate::graph::FactRef;

    #[test]
    fn completed_outputs_keep_the_original_allocation_and_actual_foreign_witness() {
        let foreign = Dependency::Fact(FactRef { cell: 91, op: 4 });
        let outputs = vec![Cell::new(None), Cell::new(Some(foreign)), Cell::new(Some(Dependency::Function(17)))];
        let allocation = outputs.as_ptr();
        let results = Results::from_outputs(3, outputs);
        assert_eq!(results.slots.as_ptr(), allocation);
        assert_eq!(results.output(1), Some(foreign));
        assert_eq!(results.get(ResultPort::new(3, 1)), Some(foreign));
        assert_eq!(results.get(ResultPort::new(3, 0)), None);
        assert_eq!(results.get(ResultPort::new(91, 1)), None);
    }

    #[test]
    fn projected_forwarding_updates_shared_slots_without_copying_or_rewriting_layout() {
        let old=Dependency::Fact(FactRef {cell:7,op:1});
        let other=Dependency::Fact(FactRef {cell:8,op:2});
        let target=Dependency::Fact(FactRef {cell:99,op:3});
        let original=Rc::new(Trail::One(Results::from_outputs(0,vec![Cell::new(Some(old)),Cell::new(Some(other))])));
        let layout=SlotLayout::compile(1,vec![Some(ResultPort::new(0,0)),Some(ResultPort::new(0,0)),Some(ResultPort::new(0,1))]).unwrap();
        let projected=ResultFrame {owner:original.clone(),projection:Some(layout.clone())};
        let sibling=ResultFrame {owner:original.clone(),projection:None};
        let Trail::One(base)=original.as_ref() else {unreachable!()};
        let address=base.slots.as_ptr();
        assert!(projected.view().unwrap().forward_output(0,target));
        assert_eq!(projected.view().unwrap().output(0),Some(target));
        assert_eq!(projected.view().unwrap().output(1),Some(target));
        assert_eq!(projected.view().unwrap().output(2),Some(other));
        assert_eq!(sibling.view().unwrap().output(0),Some(target));
        assert!(Rc::ptr_eq(&projected.owner,&original));
        assert!(Rc::ptr_eq(projected.projection.as_ref().unwrap(),&layout));
        assert_eq!(base.slots.as_ptr(),address);
        // The Run forwarding map can now expire; no later lookup is needed.
        assert_eq!(sibling.view().unwrap().output(0),Some(target));
        assert!(!projected.view().unwrap().forward_output(99,other));
    }

    #[test]
    fn oversized_projection_declines_without_shifting_outside_its_mask() {
        let slots=(0..64).map(|slot|Some(ResultPort::new(1,slot))).collect::<Vec<_>>();
        assert!(SlotLayout::compile(2,slots.clone()).is_some());
        let mut too_many=slots;too_many.push(None);
        assert!(SlotLayout::compile(2,too_many).is_none());
        assert!(SlotLayout::compile(2,vec![Some(ResultPort::new(1,64))]).is_none());
    }

    #[test]
    fn baked_permutations_reuse_one_owner_through_repeated_completions() {
        use crate::cell::{CompletedPlan,compile_projections};
        let make=|rule,source| {
            let layout=SlotLayout::compile(rule,vec![Some(ResultPort::new(source,1)),Some(ResultPort::new(source,0))]).unwrap();
            Some(Rc::new(CompletedPlan {rule,back:1,layout,outputs:vec![],required_sources:3,projections:vec![],unions:None}))
        };
        let mut plans=[make(1,0),make(2,1),make(1,2)];
        compile_projections(&mut plans,std::iter::empty());
        let a=Dependency::Fact(FactRef{cell:19,op:4});
        let b=Dependency::Fact(FactRef{cell:71,op:8});
        let slots=vec![Cell::new(Some(a)),Cell::new(Some(b))]; let address=slots.as_ptr();
        let original=Rc::new(Trail::One(Results::from_outputs(0,slots)));
        let mut owner=ResultFrame { owner:original.clone(), projection:None }; let mut probes=0;
        for i in 0..101 {
            let plan=plans[if i==0 {0}else if i%2==1 {1}else{2}].as_ref().unwrap();
            let next=Results::project_complete(plan,owner,&mut probes).unwrap();
            assert_eq!(next.stored_len(),0);
            assert!(Rc::ptr_eq(next.parent_owner().unwrap(),&original));
            assert_eq!(next.output(0),Some(if i%2==0 {b}else{a}));
            let (frame, allocations)=ResultFrame::retain(next);
            assert_eq!(allocations,0);
            assert!(Rc::ptr_eq(&frame.owner,&original));
            assert_eq!(frame.view().unwrap().output(0),Some(if i%2==0 {b}else{a}));
            assert_eq!(frame.view().unwrap().get(ResultPort::new(99,0)),None);
            owner=frame;
        }
        let Trail::One(base)=original.as_ref() else{unreachable!()};
        assert_eq!(base.slots.as_ptr(),address);
        assert_eq!(base.output(0),Some(a));
        assert!(probes>0);
    }
}
impl ResultPort {
    pub fn new(rule: usize, slot: usize) -> Self {
        Self {
            rule: u32::try_from(rule).expect("Cell rule index exhausted"),
            slot: u32::try_from(slot).ok().and_then(|s| s.checked_add(1))
                .and_then(NonZeroU32::new).expect("Cell result index exhausted"),
        }
    }
    pub fn rule(self) -> usize { self.rule as usize }
    pub(crate) fn slot(self) -> usize { self.slot.get() as usize - 1 }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub(crate) struct Capture {
    pub site: Site,
    pub port: ResultPort,
}
impl Serialize for Capture {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        // Slots are a checked lowering of the existing source artifact. Keep
        // that artifact's structural definition and checksum stable.
        self.site.serialize(serializer)
    }
}

#[derive(Debug)]
pub(crate) struct SlotLayout {
    pub(crate) rule: usize,
    pub sources: Vec<Option<ResultPort>>,
    pub(crate) source_rule: usize,
    valid: u64,
    identity: u64,
    shifts: Vec<(isize,u64)>,
}
impl SlotLayout {
    pub fn compile(rule:usize, sources:Vec<Option<ResultPort>>) -> Option<Rc<Self>> {
        if sources.len()>64 {return None;}
        let source_rule=sources.iter().flatten().next()?.rule();
        if sources.iter().flatten().any(|p|p.rule()!=source_rule || p.slot()>=64) { return None; }
        let mut valid=0; let mut identity=0;
        let mut shifts=std::collections::BTreeMap::new();
        for (slot,source) in sources.iter().enumerate() {
            if let Some(source)=source {
                valid |= 1<<slot;
                if source.rule()==rule && source.slot()==slot { identity |= 1<<slot; }
                *shifts.entry(slot as isize-source.slot() as isize).or_insert(0u64) |= 1<<source.slot();
            }
        }
        Some(Rc::new(Self { rule,sources,source_rule,valid,identity,shifts:shifts.into_iter().collect() }))
    }
    pub(crate) fn storage_bytes(&self) -> usize {
        std::mem::size_of::<Self>()
            + self.sources.capacity() * std::mem::size_of::<Option<ResultPort>>()
            + self.shifts.capacity() * std::mem::size_of::<(isize,u64)>()
    }
    fn project(&self, mask:u64) -> u64 {
        self.shifts.iter().fold(0,|v,&(shift,bits)|v|if shift>=0 {(mask&bits)<<(shift as usize)} else {(mask&bits)>>((-shift) as usize)})
    }
}
/// An owned history position. A completely inherited result keeps the donor
/// owner and its shared slot program directly, without allocating a new Trail.
#[derive(Clone, Debug)]
pub(crate) struct ResultFrame {
    pub(crate) owner: Rc<Trail>,
    pub(crate) projection: Option<Rc<SlotLayout>>,
}
impl ResultFrame {
    pub(crate) fn retain(mut results: Results) -> (Self, usize) {
        if results.slots.is_empty()
            && results.projection.as_ref().is_some_and(|p| p.valid == results.forwarded)
        {
            return (Self { owner: results.parent.take().unwrap(), projection: results.projection.take() }, 0);
        }
        (Self { owner: Rc::new(Trail::One(results)), projection: None }, 1)
    }
    pub(crate) fn view(&self) -> Option<ResultView<'_>> {
        let Trail::One(results) = self.owner.as_ref() else { return None; };
        Some(ResultView { results, projection: self.projection.as_deref() })
    }
}
/// A borrowed read of existing result storage, with the logical consumer's
/// ResultPort identity. Neither publication nor query completion copies slots.
#[derive(Clone, Copy)]
pub(crate) struct ResultView<'a> {
    results: &'a Results,
    projection: Option<&'a SlotLayout>,
}
impl ResultView<'_> {
    fn rule(self) -> usize { self.projection.map_or(self.results.rule, |p| p.rule) }
    pub(crate) fn get(self, port: ResultPort) -> Option<Dependency> {
        if let Some(projection) = self.projection {
            if port.rule() != projection.rule { return None; }
            return self.results.get(*projection.sources.get(port.slot())?.as_ref()?);
        }
        self.results.get(port)
    }
    pub(crate) fn get_counted(self, port: ResultPort, extra: &mut u64) -> Option<Dependency> {
        if let Some(projection) = self.projection {
            if port.rule() == projection.rule && projection.sources.get(port.slot()).is_some_and(Option::is_some) {
                *extra += 1;
            }
            self.get(port)
        } else { self.results.get_counted(port, extra) }
    }
    /// Publication already resolved this logical output through the Run's
    /// same-key forwarding map. Update its physical slot through the compiled
    /// projection; all aliases observe the replacement without another scan.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn forward_output(self, slot:usize, result:Dependency) -> bool {
        let port=if let Some(projection)=self.projection {
            let Some(port)=projection.sources.get(slot).copied().flatten() else {return false};
            port
        } else {ResultPort::new(self.results.rule,slot)};
        let Some(target)=self.results.slot(port) else {return false};
        target.set(Some(result));
        true
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn output(self, slot: usize) -> Option<Dependency> {
        self.get(ResultPort::new(self.rule(), slot))
    }
}
#[derive(Clone, Debug)]
pub(crate) struct Results {
    rule: usize,
    slots: SmallVec<[Cell<Option<Dependency>>; 1]>,
    projection: Option<Rc<SlotLayout>>,
    parent: Option<Rc<Trail>>,
    forwarded: u64,
}
impl Results {
    pub fn new(rule: usize) -> Self {
        Self { rule, slots: SmallVec::new(), projection:None, parent:None, forwarded:0 }
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn from_outputs(rule: usize, slots: Vec<Cell<Option<Dependency>>>) -> Self {
        Self { slots: SmallVec::from_vec(slots), ..Self::new(rule) }
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn output(&self, slot: usize) -> Option<Dependency> {
        self.get(ResultPort::new(self.rule,slot))
    }
    /// The compiled capture width avoids geometric growth of tiny arrays.
    /// Called only after the first present local result, so empty captures
    /// never allocate a backing array.
    pub fn reserve_local(&mut self, width: usize) {
        self.slots.reserve_exact(width.saturating_sub(self.slots.len()));
    }
    /// Return only the padding written for missing earlier results. Captures
    /// are sorted by the shared layout; a present result is written once.
    pub fn insert(&mut self, port: ResultPort, result: Dependency) -> usize {
        debug_assert_eq!(self.rule, port.rule(), "Cell result belongs to another definition");
        // Inherited slots consume no local storage. Missing local results
        // retain None padding, so no second per-instance presence bitmap is needed.
        let slot = self.local_slot(port.slot());
        debug_assert!(slot >= self.slots.len(), "ordered, distinct Cell captures");
        let padding = slot - self.slots.len();
        self.slots.resize_with(slot, ||Cell::new(None));
        self.slots.push(Cell::new(Some(result)));
        padding
    }
    pub fn get_counted(&self, port:ResultPort, extra:&mut u64) -> Option<Dependency> {
        if self.rule == port.rule() && self.inherits(port) { *extra += 1; }
        self.get(port)
    }
    pub fn get(&self, port: ResultPort) -> Option<Dependency> {
        self.slot(port)?.get()
    }
    fn slot(&self, port: ResultPort) -> Option<&Cell<Option<Dependency>>> {
        if self.rule != port.rule() { return None; }
        if self.projection.is_some() {
            let bit = 1u64.checked_shl(port.slot() as u32)?;
            if self.forwarded & bit != 0 {
                let Trail::One(parent) = self.parent.as_deref()? else { unreachable!() };
                return parent.slot(self.projection.as_ref()?.sources[port.slot()]?);
            }
            return self.slots.get(self.local_slot(port.slot()));
        }
        self.slots.get(port.slot())
    }
    fn local_slot(&self, slot: usize) -> usize {
        let preceding = if slot >= 64 { u64::MAX } else { (1u64 << slot) - 1 };
        slot - (self.forwarded & preceding).count_ones() as usize
    }
    pub(crate) fn storage_parts(&self) -> (usize, Option<&Rc<Trail>>, Option<&Rc<SlotLayout>>) {
        (if self.slots.spilled() { self.slots.capacity() * std::mem::size_of::<Option<Dependency>>() } else { 0 },
         self.parent.as_ref(), self.projection.as_ref())
    }
    pub fn len(&self) -> usize { self.slots.len() + self.inherited_count() }
    #[cfg(test)]
    pub fn parent_owner(&self) -> Option<&Rc<Trail>> { self.parent.as_ref() }
    pub fn spilled(&self) -> bool { self.slots.spilled() }
    pub fn stored_len(&self) -> usize { self.slots.len() }
    /// Fresh nonprojected owners still seal unpublished/query result slots at
    /// their existing boundary. Shared output slots are forwarded by delivery.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn seal_local(&mut self, mut forward:impl FnMut(Dependency)->Dependency)->(usize,usize) {
        let mut writes=0;
        for slot in &self.slots {
            if let Some(old)=slot.get() {
                let new=forward(old);
                if new!=old {slot.set(Some(new));writes+=1;}
            }
        }
        (self.slots.len(),writes)
    }
    pub fn inherited_count(&self) -> usize { self.forwarded.count_ones() as usize }
    pub(crate) fn project_complete(plan:&crate::cell::CompletedPlan,frame:ResultFrame,probes:&mut u64) -> Option<Self> {
        let (rule,layout)=(plan.rule,&plan.layout);
        let width=layout.sources.len();
        if width==0 || width>64 || layout.sources.iter().any(Option::is_none) {return None;}
        let mask=u64::MAX >> (64-width);
        let view=frame.view()?;
        if view.rule()!=layout.source_rule {return None;}
        let old=view.results;
        let previous=frame.projection.as_ref().or(old.projection.as_ref());
        let (projection,parent)=if let Some(previous)=previous {
            let forwarded=if frame.projection.is_some() {previous.valid} else {old.forwarded};
            if forwarded & plan.required_sources != plan.required_sources {return None;}
            let composed=plan.projections.iter().find_map(|(source,target)| {
                *probes+=1;
                Rc::ptr_eq(source,previous).then_some(target.clone())
            })?;
            let parent=if frame.projection.is_some() {frame.owner.clone()} else {old.parent.clone()?};
            (composed,parent)
        } else {(layout.clone(),frame.owner)};
        Some(Self{rule,slots:SmallVec::new(),projection:Some(projection),parent:Some(parent),forwarded:mask})
    }
    pub fn inherits(&self, port: ResultPort) -> bool { port.slot() < 64 && self.forwarded & (1 << port.slot()) != 0 }
    pub fn prepare(&mut self, layout:&Rc<SlotLayout>, previous:ResultFrame, flags:u64) {
        let Some(view)=previous.view() else {return};
        if view.rule()!=layout.source_rule { return; }
        let old=view.results;
        let allowed=if let Some(projection)=&previous.projection {
            layout.project(projection.valid & projection.identity)
        } else if old.parent.is_some() {
            layout.project(old.forwarded & old.projection.as_ref().unwrap().identity)
        } else { layout.valid };
        let forwarded=flags & allowed;
        if forwarded!=0 {
            self.parent=Some(if previous.projection.is_some() { previous.owner }
                else if let Some(parent)=&old.parent { parent.clone() } else { previous.owner });
            self.projection=Some(layout.clone());
            self.forwarded=forwarded;
        }
    }
}
