//! A condition on the existing candidate bucket, never another row graph.
//! Workers may race to prove it. Contention simply retains ordinary queries.
use super::{Activated, WorkerAbsorption};
use std::sync::Mutex;
use once_cell::race::OnceBox;

#[derive(Default)]
pub(crate) struct Completion(OnceBox<Mutex<Bound>>);

#[derive(Clone, Copy)]
struct Bound {
    version: u64,
    attribute: usize,
    key: u64,
    upper: i64,
    latest: u64,
    rows: usize,
}

pub(crate) struct Read<'a> {
    pub completion: &'a Completion,
    pub version: u64,
    pub rows: usize,
}
pub(crate) struct Build<'a> {
    read: Read<'a>,
    bound: Bound,
    observed: usize,
}
impl Completion {
    pub(crate) fn heap_bytes(&self) -> usize {
        usize::from(self.0.get().is_some()) * std::mem::size_of::<Mutex<Bound>>()
    }
}
impl<'a> Read<'a> {
    /// None means the entire current domain is proved absorbed. A missed or
    /// contended condition never blocks; ordinary reads may refresh the proof.
    pub(crate) fn begin(self, active: Activated<'_>, work: &mut WorkerAbsorption) -> Option<Build<'a>> {
        work.group_checks += 1;
        if let Some(saved) = self.completion.0.get() {
            if let Ok(b) = saved.try_lock() {
            if b.version == self.version && b.attribute == active.plan.attribute
                && b.key == active.key && b.rows == self.rows
                && b.latest < active.watermark && b.upper <= active.value {
                work.group_hits += 1;
                work.group_rows += self.rows as u64;
                work.candidates += self.rows as u64;
                work.absorbed += self.rows as u64;
                return None;
            }
            } else { work.group_contention += 1; }
        }
        let bound = Bound { version:self.version, attribute:active.plan.attribute, key:active.key,
            upper:i64::MIN, latest:0, rows:self.rows };
        Some(Build { read:self, bound, observed:0 })
    }
}
impl Build<'_> {
    /// Only the shared exact row proof calls this, after visibility, input and
    /// freshness checks and an actual attribute result. No extra output probe.
    pub(crate) fn observe(&mut self, value:i64, epoch:u64) {
        self.observed += 1;
        self.bound.upper = self.bound.upper.max(value);
        self.bound.latest = self.bound.latest.max(epoch);
    }
    pub(crate) fn finish(self, work:&mut WorkerAbsorption) {
        // Any collision, missing result, retired/new row or delta rejection
        // leaves at least one bucket member unproved. Never cache that subset.
        if self.observed != self.bound.rows { return; }
        // OnceBox publishes only a pointer. Competing initializers may both
        // allocate; the loser drops its copy without waiting for the winner.
        if self.read.completion.0.get().is_none() {
            work.group_allocations += 1;
            if self.read.completion.0.set(Box::new(Mutex::new(self.bound))).is_ok() {
                work.group_writes += 1;return;
            }
        }
        if let Ok(mut saved) = self.read.completion.0.get().unwrap().try_lock() {
            *saved = self.bound;
            work.group_writes += 1;
        } else { work.group_contention += 1; }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_complete_current_exact_domains_release_work_and_contention_never_waits() {
        let completion=Completion::default();
        let plan=super::super::Absorption {attribute:7,input_column:0};
        let active=Activated {plan:&plan,key:42,value:20,watermark:9};
        let read=|version|Read {completion:&completion,version,rows:2};
        let mut work=WorkerAbsorption::default();
        let mut partial=read(3).begin(active,&mut work).unwrap();
        partial.observe(1,4);partial.finish(&mut work);
        assert_eq!(work.group_writes,0,"one row cannot certify the domain");
        let mut full=read(3).begin(active,&mut work).unwrap();
        full.observe(1,4);full.observe(3,5);full.finish(&mut work);
        assert_eq!(work.group_allocations,1);
        assert!(read(3).begin(active,&mut work).is_none());
        assert_eq!(work.group_rows,2);
        assert!(read(4).begin(active,&mut work).is_some(),"any structural version change invalidates the proof");
        assert!(read(3).begin(Activated {key:43,..active},&mut work).is_some(),"fingerprints cannot prove input identity");
        assert!(read(3).begin(Activated {watermark:5,..active},&mut work).is_some(),"new constructors keep ordinary ownership");
        assert!(read(3).begin(Activated {value:2,..active},&mut work).is_some(),"smaller inputs must reopen a bound");
        let other=super::super::Absorption {attribute:8,input_column:0};
        assert!(read(3).begin(Activated {plan:&other,..active},&mut work).is_some());
        let guard=completion.0.get().unwrap().lock().unwrap();
        let mut concurrent=read(3).begin(active,&mut work).unwrap();
        concurrent.observe(1,4);concurrent.observe(3,5);concurrent.finish(&mut work);
        assert_eq!(work.group_contention,2,"both read and write races choose recomputation");
        drop(guard);
        assert!(read(3).begin(active,&mut work).is_none());
    }
}
