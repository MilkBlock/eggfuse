// Count concrete address inspections even when they precede freshness rejection.
use std::cell::RefCell;
use std::collections::BTreeMap;
const WIDTH: usize = 14;
type Counts = [u64; WIDTH];

#[derive(Default)]
struct Ledger {
    total: Counts,
    current: Counts,
    scope: (usize, usize),
    scopes: BTreeMap<(usize, usize), Counts>,
}
impl Ledger {
    fn flush(&mut self) {
        if self.current != [0; WIDTH] {
            let slot = self.scopes.entry(self.scope).or_default();
            for (count, part) in slot.iter_mut().zip(std::mem::take(&mut self.current)) {
                *count += part;
            }
        }
    }
}
thread_local! {static LEDGER: RefCell<Ledger> = RefCell::default();}
pub fn enter(run: usize, rule: usize) {
    LEDGER.with_borrow_mut(|ledger| {
        if ledger.scope != (run, rule) {
            ledger.flush();
            ledger.scope = (run, rule);
        }
    })
}
pub fn add(site: usize, n: usize) {
    LEDGER.with_borrow_mut(|l| {
        l.current[site] += n as u64;
        l.total[site] += n as u64;
    })
}
pub fn take() -> (Counts, Vec<(usize, usize, Counts)>) {
    LEDGER.with_borrow_mut(|ledger| {
        let mut l = std::mem::take(ledger);
        l.flush();
        (
            l.total,
            l.scopes
                .into_iter()
                .map(|((run, rule), counts)| (run, rule, counts))
                .collect(),
        )
    })
}
