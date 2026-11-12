//! Completion events carry the original owners. Query successors can advance
//! independently; ordered effects consume only their ready source prefix.
//! The slots contain the original owners, not copies of bindings or effects.
use std::sync::{Condvar, Mutex};
use std::time::Instant;

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
