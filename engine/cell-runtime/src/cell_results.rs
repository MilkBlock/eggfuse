//! Actual results retained by a Cell for its compiled consumers. The template
//! owns the source-to-slot mapping; instances store only the returned references.
//! A reference is a location to revalidate, not a cached value or liveness proof.
use super::Site;
use crate::graph::Dependency;
use serde::{Serialize, Serializer};
use smallvec::SmallVec;
use std::num::NonZeroU32;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub(crate) struct ResultPort {
    rule: u32,
    slot: NonZeroU32,
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
    fn slot(self) -> usize { self.slot.get() as usize - 1 }
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

#[derive(Clone, Debug)]
pub(crate) struct Results {
    rule: usize,
    slots: SmallVec<[Option<Dependency>; 2]>,
}
impl Results {
    pub fn new(rule: usize) -> Self {
        Self { rule, slots: SmallVec::new() }
    }
    /// Return only the padding written for missing earlier results. Captures
    /// are sorted by the shared layout; a present result is written once.
    pub fn insert(&mut self, port: ResultPort, result: Dependency) -> usize {
        debug_assert_eq!(self.rule, port.rule(), "Cell result belongs to another definition");
        let slot = port.slot();
        debug_assert!(slot >= self.slots.len(), "ordered, distinct Cell captures");
        let padding = slot - self.slots.len();
        self.slots.resize(slot, None);
        self.slots.push(Some(result));
        padding
    }
    pub fn get(&self, port: ResultPort) -> Option<Dependency> {
        if self.rule != port.rule() { return None; }
        self.slots.get(port.slot()).copied().flatten()
    }
    pub fn len(&self) -> usize { self.slots.len() }
}
