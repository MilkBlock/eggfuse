//! Bounded owned producers whose source can keep admitting Cells. A continued
//! result changes from computed to registered in the same source-ordered slot.
use super::Work;
use std::{any::Any, convert::Infallible, sync::{Arc, Condvar, Mutex,
    atomic::{AtomicBool, AtomicUsize, Ordering}}, time::Instant};

type Outcome<M> = Result<M, Box<dyn Any + Send>>;
enum Slot<I,T> { Empty, Computed(I), Ready(T) }
impl<I,T> Slot<I,T> {
    fn ready(&self)->bool {matches!(self,Self::Ready(_))}
    fn take(&mut self)->T {
        match std::mem::replace(self,Self::Empty) {Self::Ready(value)=>value,_=>unreachable!("ready slot")}
    }
}
struct Pending<I,T,M,C> {
    slots:Vec<Slot<I,T>>,next:usize,end:Option<Outcome<M>>,finished:bool,continuation:C,
}
struct Shared<I,T,M,C> {
    pending:Mutex<Pending<I,T,M,C>>,wake:Condvar,unfinished:AtomicUsize,
    ready:AtomicBool,finished:AtomicBool,
}
pub(crate) struct Sender<T,M,I=Infallible,C=()> {shared:Arc<Shared<I,T,M,C>>}
impl<T,M> Sender<T,M> {
    pub fn send(&self,index:usize,value:T) {
        self.shared.unfinished.fetch_sub(1,Ordering::AcqRel);
        let mut state=self.shared.pending.lock().unwrap();
        assert!(index>=state.next,"cannot replace an adopted owner");
        assert!(matches!(state.slots[index],Slot::Empty),"one result per owner");
        state.slots[index]=Slot::Ready(value);
        if index==state.next {self.shared.ready.store(true,Ordering::Release);self.shared.wake.notify_one();}
    }
}

/// Only the shared continuation owner and its progress live here. Computed
/// inputs and completed outputs occupy alternatives in the original slot array.
pub(crate) struct Ordered<C> {owner:Option<C>,next:usize,uncomputed:usize,work:Work}
impl<C> Default for Ordered<C> {
    fn default()->Self {Self {owner:None,next:0,uncomputed:0,work:Work::default()}}
}
pub(crate) type Continued<I,T,C,M> = Background<T,M,I,Ordered<C>>;
impl<T,M,I,C> Sender<T,M,I,Ordered<C>> {
    /// The callback handles any input, not only this producer's input: the
    /// active owner also continues already-computed successors in source order.
    pub fn complete(&self,index:usize,input:I,complete:impl Fn(&mut C,I)->T) {
        let mut pending=self.shared.pending.lock().unwrap();
        assert!(index>=pending.continuation.next && matches!(pending.slots[index],Slot::Empty),"one computation per owner");
        pending.continuation.uncomputed-=1;
        pending.slots[index]=Slot::Computed(input);
        let next=pending.continuation.next;
        if pending.continuation.owner.is_none() || !matches!(pending.slots[next],Slot::Computed(_)) {return;}
        let mut owner=pending.continuation.owner.take().unwrap();
        loop {
            let next=pending.continuation.next;
            let Slot::Computed(input)=std::mem::replace(&mut pending.slots[next],Slot::Empty) else {unreachable!()};
            pending.continuation.next+=1;
            drop(pending);
            // Keep directory maintenance outside the slot lock. Other workers
            // can publish computed inputs; the source can take earlier outputs.
            let value=complete(&mut owner,input);
            pending=self.shared.pending.lock().unwrap();
            assert!(matches!(pending.slots[next],Slot::Empty));
            pending.slots[next]=Slot::Ready(value);
            self.shared.unfinished.fetch_sub(1,Ordering::AcqRel);
            if next==pending.next {self.shared.ready.store(true,Ordering::Release);self.shared.wake.notify_one();}
            pending.continuation.work.waves+=1;
            pending.continuation.work.early+=u64::from(pending.continuation.uncomputed!=0);
            let next=pending.continuation.next;
            if next==pending.slots.len() || !matches!(pending.slots[next],Slot::Computed(_)) {
                // Test readiness and return ownership under the same lock so a
                // producer cannot publish into a gap and lose the handoff.
                pending.continuation.owner=Some(owner);return;
            }
        }
    }
}

pub(crate) struct Background<T,M,I=Infallible,C=()> {
    shared:Arc<Shared<I,T,M,C>>,next:usize,count:usize,work:Work,
}
impl<T:Send+'static,M:Send+'static> Background<T,M> {
    pub fn start(count:usize,pool:&rayon::ThreadPool,run:impl FnOnce(Sender<T,M>)->M+Send+'static)->Self {
        Self::start_state(count,pool,(),run)
    }
    pub fn finish(self)->(M,Work) {let (metadata,(),work)=self.finish_state();(metadata,work)}
}
impl<T:Send+'static,M:Send+'static,I:Send+'static,C:Send+'static> Background<T,M,I,Ordered<C>> {
    pub fn start_continued(count:usize,pool:&rayon::ThreadPool,owner:C,
        run:impl FnOnce(Sender<T,M,I,Ordered<C>>)->M+Send+'static)->Self {
        Self::start_state(count,pool,Ordered {owner:Some(owner),uncomputed:count,..Default::default()},run)
    }
    pub fn slot_bytes()->usize {std::mem::size_of::<Slot<I,T>>()}
    pub fn finish(self)->((C,M,Work),Work) {
        let (metadata,state,work)=self.finish_state();
        assert_eq!(state.uncomputed,0,"every producer must complete");
        ((state.owner.expect("return the continuation owner"),metadata,state.work),work)
    }
}
impl<T:Send+'static,M:Send+'static,I:Send+'static,C:Send+Default+'static> Background<T,M,I,C> {
    fn start_state(count:usize,pool:&rayon::ThreadPool,continuation:C,
        run:impl FnOnce(Sender<T,M,I,C>)->M+Send+'static)->Self {
        let slots:Vec<_>=(0..count).map(|_|Slot::Empty).collect();
        let work=Work {bytes:(slots.capacity()*std::mem::size_of::<Slot<I,T>>()
            +std::mem::size_of::<Shared<I,T,M,C>>()) as u64,..Default::default()};
        let shared=Arc::new(Shared {pending:Mutex::new(Pending {slots,next:0,end:None,finished:false,continuation}),
            wake:Condvar::new(),unfinished:AtomicUsize::new(count),ready:AtomicBool::new(false),finished:AtomicBool::new(false)});
        let producer=shared.clone();
        pool.spawn_fifo(move || {
            // A detached Rayon panic would terminate the process. Catch it at
            // the owner boundary, after any nested scoped readers have joined.
            let end=std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                let metadata=run(Sender {shared:producer.clone()});
                assert_eq!(producer.unfinished.load(Ordering::Acquire),0,"producer must return every owner");
                metadata
            }));
            let mut state=producer.pending.lock().unwrap_or_else(|e|e.into_inner());
            state.end=Some(end);state.finished=true;producer.finished.store(true,Ordering::Release);producer.wake.notify_one();
        });
        Self {shared,next:0,count,work}
    }
    pub fn unfinished(&self)->usize {self.shared.unfinished.load(Ordering::Acquire)}
    pub fn poll(&mut self,wait:bool,ready:&mut Vec<T>) {
        assert!(ready.is_empty());
        if !wait && !self.shared.ready.load(Ordering::Acquire) && !self.shared.finished.load(Ordering::Acquire) {return;}
        let mut state=self.shared.pending.lock().unwrap_or_else(|e|e.into_inner());
        if wait && !state.finished && state.slots.get(self.next).is_none_or(|s|!s.ready()) {
            let clock=Instant::now();
            state=self.shared.wake.wait_while(state,|s|!s.finished && s.slots.get(self.next).is_none_or(|s|!s.ready()))
                .unwrap_or_else(|e|e.into_inner());
            self.work.wait_ns+=clock.elapsed().as_nanos() as u64;
        }
        let n=state.slots[self.next..].iter().take_while(|s|s.ready()).count();
        let before=ready.capacity();
        ready.extend(state.slots[self.next..self.next+n].iter_mut().map(Slot::take));self.next+=n;
        state.next=self.next;
        self.shared.ready.store(state.slots.get(self.next).is_some_and(Slot::ready),Ordering::Release);
        self.work.bytes+=((ready.capacity()-before)*std::mem::size_of::<T>()) as u64;
        self.work.waves+=u64::from(n!=0);
        self.work.early+=if self.unfinished()!=0 {n as u64} else {0};
    }
    pub fn finished(&self)->bool {
        if !self.shared.finished.load(Ordering::Acquire) {return false;}
        if self.next==self.count {return true;}
        let state=self.shared.pending.lock().unwrap_or_else(|e|e.into_inner());
        state.finished && (self.next==state.slots.len() || state.end.as_ref().is_some_and(Result::is_err))
    }
    fn finish_state(mut self)->(M,C,Work) {
        let state=self.shared.pending.lock().unwrap_or_else(|e|e.into_inner());
        let clock=(!state.finished).then(Instant::now);
        let mut state=self.shared.wake.wait_while(state,|s|!s.finished).unwrap_or_else(|e|e.into_inner());
        self.work.wait_ns+=clock.map_or(0,|c|c.elapsed().as_nanos() as u64);
        let end=state.end.take().expect("producer completion");
        let continuation=std::mem::take(&mut state.continuation);drop(state);
        match end {
            Ok(metadata)=>(metadata,continuation,std::mem::take(&mut self.work)),
            Err(panic)=>std::panic::resume_unwind(panic),
        }
    }
}
impl<T,M,I,C> Drop for Background<T,M,I,C> {
    fn drop(&mut self) {
        // Source errors may discard private results, but must not release the
        // immutable parent epoch while its producer still uses it.
        let state=self.shared.pending.lock().unwrap_or_else(|e|e.into_inner());
        drop(self.shared.wake.wait_while(state,|s|!s.finished).unwrap_or_else(|e|e.into_inner()));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{sync::mpsc,time::Duration};
    #[test]
    fn computed_slots_are_hidden_and_do_not_wait_for_registration() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let (entered,in_registration)=mpsc::channel();let (release,allowed)=mpsc::channel();
        let (later,produced_later)=mpsc::channel();let (start_second,second_started)=mpsc::channel();
        let allowed=Mutex::new(allowed);let second_started=Mutex::new(second_started);
        let mut wave=Continued::start_continued(2,&pool,Vec::new(),move |out| {
            rayon::scope(|scope| {
                scope.spawn(|_|out.complete(0,10,|owner,value| {
                    if value==10 {
                        entered.send(()).unwrap();
                        allowed.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();
                    }
                    owner.push(value);value+1
                }));
                scope.spawn(|_| {
                    second_started.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();
                    out.complete(1,20,|owner,value| {owner.push(value);value+1});
                    later.send(()).unwrap();
                });
            });
        });
        in_registration.recv_timeout(Duration::from_secs(5)).unwrap();
        start_second.send(()).unwrap();
        produced_later.recv_timeout(Duration::from_secs(5)).unwrap();
        let mut ready=Vec::new();wave.poll(false,&mut ready);
        assert!(ready.is_empty(),"computed rows are not yet registered");
        assert_eq!(wave.unfinished(),2);
        release.send(()).unwrap();let mut received=Vec::new();
        while received.len()<2 {
            wave.poll(true,&mut ready);received.append(&mut ready);
            if wave.finished() {break;}
        }
        let ((owner,(),prefix),_)=wave.finish();
        assert_eq!(received,[11,21]);assert_eq!(owner,[10,20]);
        assert_eq!(prefix.bytes,0,"the ordered continuation has no second slot array");
    }
    #[test]
    fn continuation_panics_return_readers_and_empty_regions_finish() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(1).build().unwrap();
        for compute_panic in [false,true] {
            let read=Arc::new(());let reader=read.clone();
            let wave=Continued::start_continued(1,&pool,0,move |out| {
                let _reader=reader;
                if compute_panic {panic!("producer failure");}
                out.complete(0,(),|_,()|->(){panic!("registration failure")});
            });
            assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(||wave.finish())).is_err());
            assert_eq!(Arc::strong_count(&read),1);
        }
        let wave=Continued::<(),(),_,_>::start_continued(0,&pool,7,|_|9);
        let ((owner,metadata,prefix),_)=wave.finish();
        assert_eq!((owner,metadata,prefix.waves),(7,9,0));
    }
    #[test]
    fn ordinary_completion_slots_keep_their_original_layout() {
        assert_eq!(std::mem::size_of::<Slot<Infallible,u64>>(),std::mem::size_of::<Option<u64>>());
        assert_eq!(std::mem::size_of::<Slot<Infallible,Box<u64>>>(),std::mem::size_of::<Option<Box<u64>>>());
        type Cell=crate::graph::cell_births::Completed;
        assert_eq!(std::mem::size_of::<Slot<Infallible,Cell>>(),std::mem::size_of::<Option<Cell>>());
    }
    #[test]
    fn admission_and_prefix_retirement_run_before_the_old_wave_finishes() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let (admit,admitted)=mpsc::channel();let (continue_source,continued)=mpsc::channel();
        let mut wave=Background::start(2,&pool,move |out| {
            admitted.recv_timeout(Duration::from_secs(5)).unwrap();
            out.send(0,10);continued.recv_timeout(Duration::from_secs(5)).unwrap();
            out.send(1,20);7
        });
        // A whole-batch join before returning from start would deadlock here.
        admit.send(()).unwrap();let mut ready=Vec::new();wave.poll(true,&mut ready);
        assert_eq!(ready,[10]);assert_eq!(wave.unfinished(),1);
        continue_source.send(()).unwrap();ready.clear();wave.poll(true,&mut ready);
        assert_eq!(ready,[20]);let (metadata,work)=wave.finish();
        assert_eq!(metadata,7);assert!(work.early>0);
    }
    #[test]
    fn finished_producer_does_not_discard_undelivered_results() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let mut wave=Background::start(2,&pool,|out| {out.send(0,10);out.send(1,20);});
        let state=wave.shared.pending.lock().unwrap();
        drop(wave.shared.wake.wait_while(state,|s|!s.finished).unwrap());
        assert!(!wave.finished(),"finished computation is not finished source adoption");
        let mut ready=Vec::new();wave.poll(false,&mut ready);
        assert_eq!(ready,[10,20]);assert!(wave.finished());wave.finish();
    }
    #[test]
    fn source_order_is_preserved_and_panics_join_owned_readers() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let mut wave=Background::start(2,&pool,|out| {out.send(1,20);out.send(0,10);});
        let mut received=Vec::new();let mut ready=Vec::new();
        while received.len()<2 {wave.poll(true,&mut ready);received.append(&mut ready);}
        assert_eq!(received,[10,20]);wave.finish();
        let owner=Arc::new(());let reader=owner.clone();
        let wave=Background::start(1,&pool,move |_:Sender<usize,()>| {drop(reader);panic!("worker failure")});
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(||wave.finish())).is_err());
        assert_eq!(Arc::strong_count(&owner),1);
    }
}
