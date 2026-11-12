//! Bounded owned producers whose source can keep admitting Cells. The queue
//! carries each original result once; it does not publish graph effects.
use super::Work;
use std::{any::Any, sync::{Arc, Condvar, Mutex, atomic::{AtomicBool, AtomicUsize, Ordering}}, time::Instant};

type Outcome<M> = Result<M, Box<dyn Any + Send>>;
struct Pending<T,M> { slots:Vec<Option<T>>, next:usize, end:Option<Outcome<M>>, finished:bool }
struct Shared<T,M> {
    pending:Mutex<Pending<T,M>>, wake:Condvar, unfinished:AtomicUsize,
    ready:AtomicBool, finished:AtomicBool,
}
pub(crate) struct Sender<T,M> { shared:Arc<Shared<T,M>> }
impl<T,M> Sender<T,M> {
    pub fn send(&self,index:usize,value:T) {
        self.shared.unfinished.fetch_sub(1,Ordering::AcqRel);
        let mut state=self.shared.pending.lock().unwrap();
        assert!(index>=state.next,"cannot replace an adopted owner");
        assert!(state.slots[index].replace(value).is_none(),"one result per owner");
        if index==state.next {self.shared.ready.store(true,Ordering::Release);self.shared.wake.notify_one();}
    }
}
pub(crate) struct Background<T,M> {
    shared:Arc<Shared<T,M>>, next:usize, count:usize, work:Work,
}
impl<T:Send+'static,M:Send+'static> Background<T,M> {
    pub fn start(count:usize,pool:&rayon::ThreadPool,run:impl FnOnce(Sender<T,M>)->M+Send+'static)->Self {
        let slots:Vec<_>=(0..count).map(|_|None).collect();
        let work=Work{bytes:(slots.capacity()*std::mem::size_of::<Option<T>>()
            +std::mem::size_of::<Shared<T,M>>()) as u64,..Default::default()};
        let shared=Arc::new(Shared {pending:Mutex::new(Pending {slots,next:0,end:None,finished:false}),
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
        if wait && !state.finished && state.slots.get(self.next).is_none_or(Option::is_none) {
            let clock=Instant::now();
            state=self.shared.wake.wait_while(state,|s|!s.finished && s.slots.get(self.next).is_none_or(Option::is_none))
                .unwrap_or_else(|e|e.into_inner());
            self.work.wait_ns+=clock.elapsed().as_nanos() as u64;
        }
        let n=state.slots[self.next..].iter().take_while(|s|s.is_some()).count();
        let before=ready.capacity();
        ready.extend(state.slots[self.next..self.next+n].iter_mut().map(|s|s.take().unwrap()));self.next+=n;
        state.next=self.next;
        self.shared.ready.store(state.slots.get(self.next).is_some_and(Option::is_some),Ordering::Release);
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
    pub fn finish(mut self)->(M,Work) {
        let state=self.shared.pending.lock().unwrap_or_else(|e|e.into_inner());
        let clock=(!state.finished).then(Instant::now);
        let mut state=self.shared.wake.wait_while(state,|s|!s.finished).unwrap_or_else(|e|e.into_inner());
        self.work.wait_ns+=clock.map_or(0,|c|c.elapsed().as_nanos() as u64);
        let end=state.end.take().expect("producer completion");drop(state);
        match end {
            Ok(metadata)=>(metadata,std::mem::take(&mut self.work)),
            Err(panic)=>std::panic::resume_unwind(panic),
        }
    }
}
impl<T,M> Drop for Background<T,M> {
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
