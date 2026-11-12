//! Completion events carry the original owners. Query successors can advance
//! independently; ordered effects consume only their ready source prefix.
//! The slots contain the original owners, not copies of bindings or effects.
use std::sync::{Condvar, Mutex};
use std::time::Instant;
#[path="completion_background.rs"]
mod background;
pub(crate) use background::Background;

#[derive(Default)]
pub(crate) struct Work {
    pub waves: u64,
    pub early: u64,
    pub wait_ns: u64,
    pub bytes: u64,
}
struct Pending<T> {
    slots: Vec<Option<T>>,
    next: usize,
    completed: usize,
    aborted: bool,
    ready: Vec<T>,
    bytes:u64,
}
struct Events<T> { pending: Mutex<Pending<T>>, wake: Condvar }
struct Producer<'a, T> { events: &'a Events<T>, committed: bool }
impl<T> Drop for Producer<'_, T> {
    fn drop(&mut self) {
        if !self.committed {
            self.events.pending.lock().unwrap_or_else(|e| e.into_inner()).aborted = true;
            self.events.wake.notify_one();
        }
    }
}

/// The callback may own source-local Cursors. A worker panic wakes the receiver
/// before scope unwinding; a callback error discards later private results and
/// still joins their readers. Neither path publishes later source effects.
pub(crate) fn ordered<T: Send, R: Send, E>(
    tasks: Vec<T>, pool: Option<&rayon::ThreadPool>,
    run: impl Fn(T) -> R + Sync,
    mut consume: impl FnMut(&mut Vec<R>) -> Result<(), E>,
) -> (Result<(), E>, Work) {
    run_events(tasks, 0, pool, run, |ready,_|consume(ready), true)
}

pub(crate) fn followups<T: Send, R: Send, E>(tasks: Vec<T>, extra:usize, pool: Option<&rayon::ThreadPool>,
    run: impl Fn(T) -> R + Sync, consume: impl FnMut(&mut Vec<R>, &mut Vec<T>) -> Result<(), E>,
) -> (Result<(), E>, Work) { run_events(tasks, extra, pool, run, consume, false) }

/// A long-lived owner may release several completed fragments before returning
/// its directory. The receiver drains every event, including after its own
/// source error, so leased owners are never discarded by an early return.
pub(crate) fn fragments<T:Send,R:Send>(tasks:Vec<T>,pool:Option<&rayon::ThreadPool>,
    run:impl Fn(T,&(dyn Fn(R)+Sync))+Sync,mut consume:impl FnMut(&mut Vec<R>))->Work {
    struct State<R> {ready:Vec<R>,remaining:usize,aborted:bool,bytes:u64}
    struct Guard<'a,R> {state:&'a Mutex<State<R>>,wake:&'a Condvar,done:bool}
    impl<R> Drop for Guard<'_,R> {
        fn drop(&mut self) {
            let mut state=self.state.lock().unwrap_or_else(|e|e.into_inner());
            state.remaining-=1;state.aborted|=!self.done;self.wake.notify_one();
        }
    }
    let mut work=Work::default();
    // Use the same event semantics inline, without borrowing the source from
    // a worker callback. This mode is a diagnostic, not the parallel runtime.
    let Some(pool)=pool else {
        for task in tasks {
            let ready=Mutex::new(Vec::new());run(task,&|event|ready.lock().unwrap().push(event));
            let mut ready=ready.into_inner().unwrap();work.bytes+=(ready.capacity()*std::mem::size_of::<R>()) as u64;
            work.waves+=u64::from(!ready.is_empty());consume(&mut ready);
        }
        return work;
    };
    let state=Mutex::new(State {ready:Vec::new(),remaining:tasks.len(),aborted:false,bytes:0});
    let wake=Condvar::new();let mut ready=Vec::new();
    let send=|event| {
            let mut state=state.lock().unwrap();let before=state.ready.capacity();state.ready.push(event);
            state.bytes+=((state.ready.capacity()-before)*std::mem::size_of::<R>()) as u64;
            wake.notify_one();
        };
    pool.in_place_scope_fifo(|scope| {
        for task in tasks {
            let (state,wake,run,send)=(&state,&wake,&run,&send);
            scope.spawn_fifo(move |_| {
                let mut guard=Guard {state,wake,done:false};run(task,send);guard.done=true;
            });
        }
        loop {
            let mut pending=state.lock().unwrap();
            if pending.aborted {break;}
            if pending.ready.is_empty() && pending.remaining!=0 {
                let clock=Instant::now();pending=wake.wait_while(pending,|p|p.ready.is_empty() && p.remaining!=0 && !p.aborted).unwrap();
                work.wait_ns+=clock.elapsed().as_nanos() as u64;
            }
            if pending.aborted || (pending.ready.is_empty() && pending.remaining==0) {break;}
            std::mem::swap(&mut ready,&mut pending.ready);
            work.early+=if pending.remaining!=0 {ready.len() as u64}else{0};drop(pending);
            work.waves+=1;consume(&mut ready);ready.clear();
        }
    });
    // Growth is counted where each vector grows, not again when it swaps hands.
    let pending=state.into_inner().unwrap();work.bytes+=pending.bytes;
    work
}

/// Infallible worker continuations transfer one mutable owner along the ready
/// prefix. Producers only lock to publish/take original result owners; they do
/// not wait for the active consumer's maintenance or for missing predecessors.
/// Call inside the existing pool region. This also works with one worker.
pub(crate) fn owned_prefix<T: Send, R: Send, C: Send>(
    tasks: Vec<T>, owner: C, run: impl Fn(T) -> R + Sync,
    consume: impl Fn(&mut C, R) + Sync,
) -> (C, Work) {
    use rayon::prelude::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    struct State<R,C> { slots:Vec<Option<R>>, next:usize, owner:Option<C>, work:Work }
    let count=tasks.len();
    let slots:Vec<_>=(0..count).map(|_|None).collect();
    let bytes=(tasks.capacity()*std::mem::size_of::<T>()+slots.capacity()*std::mem::size_of::<Option<R>>()) as u64;
    let state=Mutex::new(State {slots,next:0,owner:Some(owner),work:Work {bytes,..Work::default()}});
    let unfinished=AtomicUsize::new(count);
    tasks.into_par_iter().enumerate().for_each(|(index,task)| {
        let result=run(task);
        unfinished.fetch_sub(1,Ordering::AcqRel);
        let mut pending=state.lock().unwrap();
        pending.slots[index]=Some(result);
        if pending.owner.is_none() || pending.slots[pending.next].is_none() {return;}
        let mut owner=pending.owner.take().unwrap();
        loop {
            let next=pending.next;
            let result=pending.slots[next].take().unwrap();pending.next+=1;
            drop(pending);
            consume(&mut owner,result);
            let early=unfinished.load(Ordering::Acquire)!=0;
            pending=state.lock().unwrap();
            pending.work.waves+=1;pending.work.early+=u64::from(early);
            if pending.next==count || pending.slots[pending.next].is_none() {
                // Restoring the owner and testing readiness under one lock
                // prevents a last producer from losing the wakeup/ownership.
                pending.owner=Some(owner);return;
            }
        }
    });
    let state=state.into_inner().unwrap();
    assert_eq!(state.next,count,"every completed owner must retire");
    (state.owner.unwrap(),state.work)
}

fn run_events<T: Send, R: Send, E>(mut tasks: Vec<T>, extra:usize, pool: Option<&rayon::ThreadPool>,
    run: impl Fn(T) -> R + Sync, mut consume: impl FnMut(&mut Vec<R>, &mut Vec<T>) -> Result<(), E>, ordered: bool,
) -> (Result<(), E>, Work) {
    let mut work = Work::default();
    if pool.is_none() {
        loop {
            let mut results: Vec<_> = tasks.drain(..).map(&run).collect();
            work.bytes += (results.capacity() * std::mem::size_of::<R>()) as u64;
            work.waves += u64::from(!results.is_empty());
            let result=consume(&mut results,&mut tasks);
            if result.is_err() || tasks.is_empty() {return (result,work);}
        }
    }
    let mut count = tasks.len();
    let capacity=count+extra;
    let slots = (0..if ordered {capacity} else {0}).map(|_| None).collect::<Vec<_>>();
    work.bytes += (slots.capacity() * std::mem::size_of::<Option<R>>()) as u64;
    let events = Events { pending: Mutex::new(Pending { slots, next: 0, completed: 0, aborted: false,
        ready: Vec::new(), bytes:0 }), wake: Condvar::new() };
    let mut result = Ok(());
    let mut ready=Vec::new();
    let mut ready_bytes=0;
    pool.unwrap().in_place_scope_fifo(|scope| {
        let spawn=|index,task| {
            let (events,run)=(&events,&run);
            scope.spawn_fifo(move |_| {
                let mut producer=Producer {events,committed:false};
                let value=run(task);
                let mut pending=events.pending.lock().unwrap();
                if ordered {pending.slots[index]=Some(value);}
                else {
                    let before=pending.ready.capacity();pending.ready.push(value);
                    pending.bytes+=((pending.ready.capacity()-before)*std::mem::size_of::<R>()) as u64;
                }
                pending.completed+=1;producer.committed=true;
                if !ordered || index==pending.next {events.wake.notify_one();}
            });
        };
        for (index,task) in tasks.drain(..).enumerate() {spawn(index,task);}
        loop {
            let mut pending = events.pending.lock().unwrap();
            if pending.next == count || pending.aborted { break; }
            if if ordered { pending.slots[pending.next].is_none() } else { pending.ready.is_empty() } {
                let clock = Instant::now();
                pending = events.wake.wait_while(pending, |p| !p.aborted && if ordered { p.slots[p.next].is_none() } else { p.ready.is_empty() }).unwrap();
                work.wait_ns += clock.elapsed().as_nanos() as u64;
            }
            if pending.aborted { break; }
            if ordered {
                let start=pending.next;
                let length=pending.slots[start..].iter().take_while(|s|s.is_some()).count();
                let before=ready.capacity();ready.extend(pending.slots[start..start+length].iter_mut().map(|s|s.take().unwrap()));
                ready_bytes+=((ready.capacity()-before)*std::mem::size_of::<R>()) as u64;
            } else {std::mem::swap(&mut ready,&mut pending.ready);}
            let length = ready.len();
            pending.next += length;
            work.early += if pending.completed < count { length as u64 } else { 0 };
            drop(pending);
            work.waves += 1;
            if result.is_ok() { result = consume(&mut ready,&mut tasks); }
            ready.clear();
            if result.is_ok() {
                for task in tasks.drain(..) {
                    assert!(count<capacity,"compiled event capacity");spawn(count,task);count+=1;
                }
            } else {tasks.clear();}
        }
    });
    work.bytes+=ready_bytes+events.pending.into_inner().unwrap().bytes;
    (result, work)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{sync::mpsc, time::Duration};

    #[test]
    fn fragment_stream_handles_one_worker_empty_work_and_worker_panics() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(1).build().unwrap();
        for count in [0,1,3] {
            let mut values=Vec::new();
            fragments((0..count).collect(),Some(&pool),|i,emit| {emit(2*i);emit(2*i+1);},|ready|values.append(ready));
            assert_eq!(values,(0..2*count).collect::<Vec<_>>());
        }
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            fragments(vec![0,1],Some(&pool),|i,emit| {emit(i);assert_ne!(i,0,"failed owner");},|ready|ready.clear());
        })).is_err());
    }

    #[test]
    fn worker_owner_retires_a_prefix_while_a_later_job_is_still_running() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let (tx,rx)=mpsc::channel();let rx=Mutex::new(rx);
        let (order,work)=pool.install(||owned_prefix(vec![0,1,2],Vec::new(),|i| {
            if i==2 {rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();}i
        },|order,i| {
            assert!(rayon::current_thread_index().is_some());order.push(i);
            if i==1 {tx.send(()).unwrap();}
        }));
        assert_eq!(order,[0,1,2]);assert!(work.early>0);
    }

    #[test]
    fn worker_owner_handles_one_thread_empty_work_and_scrambled_completions() {
        for workers in [1,4] {for count in [0,1,129] {
            let pool=rayon::ThreadPoolBuilder::new().num_threads(workers).build().unwrap();
            let (order,work)=pool.install(||owned_prefix((0..count).collect(),Vec::new(),|i| {
                if i%3==0 {std::thread::yield_now();}i
            },|order,i|order.push(i)));
            assert_eq!(order,(0..count).collect::<Vec<_>>());assert_eq!(work.waves,count as u64);
        }}
    }
    #[test]
    fn worker_owner_panics_join_other_jobs_without_a_waiting_receiver() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        for fail_consumer in [false,true] {
            assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(||pool.install(|| {
                owned_prefix(vec![0,1,2],(),|i| {
                    assert!(fail_consumer || i!=1,"producer panic");i
                },|_,i|assert!(!fail_consumer || i!=1,"consumer panic"))
            }))).is_err());
        }
    }

    #[test]
    fn first_cell_continues_before_unrelated_cell_finishes() {
        let pool = rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let (tx, rx) = mpsc::channel();
        let rx = Mutex::new(rx);
        let mut order = Vec::new();
        let (result, work) = ordered(vec![0, 1], Some(&pool), |i| {
            if i == 1 { rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap(); }
            i
        }, |ready| -> Result<(), ()> {
            for i in ready.drain(..) { order.push(i); if i == 0 { tx.send(()).unwrap(); } }
            Ok(())
        });
        result.unwrap();
        assert_eq!(order, [0, 1]);
        assert_eq!(work.early, 1);
    }

    #[test]
    fn a_followup_runs_while_an_unrelated_query_is_still_open() {
        let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let (tx,rx)=mpsc::channel();let rx=Mutex::new(rx);
        let mut observed=Vec::new();
        let (result,_)=followups(vec![0,1],1,Some(&pool),|task| {
            if task==1 {rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap();}
            if task==2 {tx.send(()).unwrap();}
            task
        },|ready,next|->Result<(),()> {
            for task in ready.drain(..) {observed.push(task);if task==0 {next.push(2);}}
            Ok(())
        });
        result.unwrap();
        assert_eq!(observed.len(),3);
        assert!(observed.iter().position(|&t|t==0)<observed.iter().position(|&t|t==2));
    }

    #[test]
    fn later_completion_cannot_overtake_source_error() {
        let pool = rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        let (tx, rx) = mpsc::channel();
        let rx = Mutex::new(rx);
        let mut effects = Vec::new();
        let (result, _) = ordered(vec![0, 1], Some(&pool), |i| {
            if i == 0 { rx.lock().unwrap().recv_timeout(Duration::from_secs(5)).unwrap(); }
            else { tx.send(()).unwrap(); }
            i
        }, |ready| {
            for i in ready.drain(..) { if i == 0 { return Err("source error"); } effects.push(i); }
            Ok(())
        });
        assert_eq!(result, Err("source error"));
        assert!(effects.is_empty());
    }

    #[test]
    fn panicking_worker_wakes_receiver_and_joins_other_readers() {
        let pool = rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _ = ordered(vec![0, 1], Some(&pool), |i| {
                assert_ne!(i, 0, "worker failure"); i
            }, |_| Ok::<_, ()>(()));
        })).is_err());
    }
}
