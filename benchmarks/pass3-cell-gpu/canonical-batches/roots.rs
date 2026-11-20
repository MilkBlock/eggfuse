use std::{
    cell::RefCell,
    sync::atomic::{AtomicU64, Ordering},
};

const MAX_CELL: usize = 1 << 20;
const MEMO_SIZE: usize = 256;
static EPOCH: AtomicU64 = AtomicU64::new(1);
fn next_stamp() -> u64 {
    let n = EPOCH.fetch_add(1, Ordering::Relaxed);
    assert_ne!(n, 0, "canonical epoch overflow");
    n
}
#[derive(Clone, Copy, Debug, Default)]
struct Cached {
    stamp: u64,
    id: u64,
    root: u64,
}
thread_local! {
    static MEMO:RefCell<[Cached;MEMO_SIZE]>=const{RefCell::new([Cached{stamp:0,id:0,root:0};MEMO_SIZE])};
    static STATS:RefCell<[[u64;10];3]>=const{RefCell::new([[0;10];3])};
}
#[derive(Clone, Debug, Default)]
struct Link {
    slot: u32,
    parent: u64,
    mask: u64,
    wide: bool,
}
#[derive(Clone, Debug, Default)]
struct CanonicalBatch {
    mode: u8,
    scope: u8,
    phase: u8,
    audit: bool,
    check: bool,
    stamp: u64,
    bits: Vec<u64>,
    cells: Vec<u32>,
    links: Vec<Link>,
    writes: u64,
}
impl CanonicalBatch {
    fn flags(&self) -> (bool, bool) {
        (matches!(self.mode, 2 | 4), matches!(self.mode, 3 | 4))
    }
    fn record(&mut self, id: u64, to: u64) {
        if self.mode == 0 {
            return;
        }
        self.writes += 1;
        let (direct, memo) = self.flags();
        if memo {
            self.stamp = next_stamp();
        }
        let cell = (id >> 32) as usize;
        if cell >= MAX_CELL {
            return;
        }
        let slot = id as u32;
        if self.mode == 1 {
            let block = cell >> 6;
            if self.bits.len() <= block {
                self.bits.resize(block + 1, 0);
            }
            self.bits[block] |= 1u64 << (cell % 64);
        } else if direct {
            if self.cells.len() <= cell {
                self.cells.resize(cell + 1, 0);
            }
            let mut idx = self.cells[cell];
            if idx == 0 {
                self.links.push(Link::default());
                idx = self.links.len() as u32;
                self.cells[cell] = idx;
            }
            let tag = &mut self.links[idx as usize - 1];
            tag.slot = slot;
            tag.parent = to;
            if slot < 64 {
                tag.mask |= 1u64 << slot;
            } else {
                tag.wide = true;
            }
        }
    }
    fn active(&self) -> bool {
        self.phase != 0 && self.scope & (1 << self.phase) != 0
    }
    fn bytes(&self) -> usize {
        self.bits.capacity() * 8
            + self.cells.capacity() * 4
            + self.links.capacity() * std::mem::size_of::<Link>()
    }
}
impl Parents {
    pub fn configure_canonical_batch(
        &mut self,
        mode: u8,
        scope: u8,
        audit: bool,
        check: bool,
    ) -> Result<(), String> {
        if mode > 4 || scope & !6 != 0 {
            return Err("unknown canonical batch mode or phase".into());
        }
        self.batch = CanonicalBatch {
            mode,
            scope,
            audit,
            check,
            stamp: next_stamp(),
            ..Default::default()
        };
        if self.base.is_some() {
            return Err("cannot configure during a reader epoch".into());
        }
        #[cfg(not(feature = "sparse-cells"))]
        if mode != 0 {
            for (&id, &to) in &self.local {
                self.batch.record(id, to);
            }
        }
        #[cfg(feature = "sparse-cells")]
        if mode != 0 {
            return Err("canonical batch study requires the ordinary source store".into());
        }
        self.batch.writes = 0;
        STATS.with_borrow_mut(|s| *s = [[0; 10]; 3]);
        Ok(())
    }
    pub(crate) fn canonical_phase(&mut self, phase: u8) {
        self.batch.phase = phase;
        if self.batch.flags().1 && phase != 0 {
            self.batch.stamp = next_stamp();
        }
    }
    #[inline]
    pub(crate) fn source_root(&self, mut x: u64) -> u64 {
        while let Some(&parent) = self.get(&x) {
            if x == parent {
                break;
            }
            x = parent;
        }
        x
    }
    #[inline]
    pub(crate) fn selected_root(&self, id: u64) -> u64 {
        let b = &self.batch;
        if b.phase == 0 || (!b.audit && (b.mode == 0 || !b.active())) {
            return self.source_root(id);
        }
        let enabled = b.active();
        let (direct, memo) = b.flags();
        let pos =
            ((id ^ (id >> 32).wrapping_mul(0x9e3779b9) ^ (id >> 5)) as usize) & (MEMO_SIZE - 1);
        let cached = if enabled && memo {
            MEMO.with_borrow(|m| {
                let t = m[pos];
                (t.stamp == b.stamp && t.id == id).then_some(t.root)
            })
        } else {
            None
        };
        let mut x = id;
        let mut map_reads = 0;
        let mut links = 0;
        let mut direct_hits = 0;
        let mut negative = 0;
        if let Some(w) = cached {
            x = w;
        } else {
            loop {
                let cell = (x >> 32) as usize;
                let slot = x as u32;
                let to;
                if enabled
                    && cell < MAX_CELL
                    && b.mode == 1
                    && !b
                        .bits
                        .get(cell >> 6)
                        .is_some_and(|raw| raw & (1u64 << (cell % 64)) != 0)
                {
                    negative += 1;
                    break;
                } else if enabled && cell < MAX_CELL && direct {
                    let idx = b.cells.get(cell).copied().unwrap_or(0);
                    if idx == 0 {
                        negative += 1;
                        break;
                    }
                    let entry = &b.links[idx as usize - 1];
                    if slot == entry.slot {
                        to = Some(entry.parent);
                        direct_hits += 1;
                    } else if (slot < 64 && entry.mask & (1u64 << slot) == 0)
                        || (slot >= 64 && !entry.wide)
                    {
                        negative += 1;
                        break;
                    } else {
                        map_reads += 1;
                        to = self.get(&x).copied();
                    }
                } else {
                    map_reads += 1;
                    to = self.get(&x).copied();
                }
                match to {
                    Some(y) if y != x => {
                        links += 1;
                        x = y
                    }
                    _ => break,
                }
            }
            if enabled && memo {
                MEMO.with_borrow_mut(|m| {
                    m[pos] = Cached {
                        stamp: b.stamp,
                        id,
                        root: x,
                    }
                });
            }
        }
        if b.check {
            assert_eq!(
                x,
                self.source_root(id),
                "canonical root changed under the same visible union state"
            );
        }
        if b.audit {
            STATS.with_borrow_mut(|s| {
                let phase = &mut s[b.phase as usize];
                phase[0] += 1;
                phase[1] += map_reads;
                phase[2] += links;
                phase[3] += direct_hits;
                phase[4] += negative;
                phase[5] += u64::from(cached.is_some());
                phase[6] += u64::from(id == x);
                phase[7] += u64::from(links >= 2);
                phase[8] += u64::from(links >= 4);
                phase[9] = phase[9].max(links);
            });
        }
        x
    }
    pub fn canonical_batch_report(&self) -> serde_json::Value {
        let b = &self.batch;
        serde_json::json!({"mode":b.mode,"scope":b.scope,"phase":STATS.with_borrow(|s|*s),"parent_insertions":b.writes,
            "directory_capacity_bytes":b.bytes(),"memo_bytes_per_thread":if b.flags().1{std::mem::size_of::<[Cached;MEMO_SIZE]>()}else{0}})
    }
}

#[cfg(all(test, not(feature = "sparse-cells")))]
mod canonical_batch_lifecycle {
    use super::*;

    #[test]
    fn offsets_epochs_clones_and_late_unions_keep_source_roots() {
        let code = |cell: u64, slot: u64| (cell << 32) | slot;
        let small = code(3, 2);
        let spill = code(3, 99);
        let high = code((MAX_CELL + 17) as u64, 12);
        let keys = [
            small,
            spill,
            code(3, 4),
            code(3, 5),
            code(4, 2),
            high,
            11,
            12,
        ];
        for mode in 0..=4 {
            let mut p = Parents::default();
            p.insert(small, 12);
            p.configure_canonical_batch(mode, 6, false, true).unwrap();
            p.canonical_phase(1);
            for &id in &keys {
                assert_eq!(p.selected_root(id), p.source_root(id));
            }
            let mut sibling = p.clone();
            p.insert(spill, 11);
            p.insert(code(3, 4), 12);
            p.insert(high, 12);
            // Two independently mutable parents reach distinct states with the same insertion count.
            sibling.insert(spill, 10);
            sibling.insert(code(3, 4), 10);
            sibling.insert(high, 9);
            assert_eq!(p.selected_root(spill), 11);
            assert_eq!(sibling.selected_root(spill), 10);
            assert_eq!(p.selected_root(high), 12);
            assert_eq!(sibling.selected_root(high), 9);
            let frozen = p.freeze();
            let reference = Read {
                base: &frozen,
                delta: None,
            };
            assert_eq!(reference.root(small), 12);
            p.insert(12, 1);
            assert_eq!(p.selected_root(small), 1);
            assert_eq!(reference.root(small), 12);
            drop(frozen);
            p.thaw();
            p.canonical_phase(2);
            for &id in &keys {
                assert_eq!(p.selected_root(id), p.source_root(id));
            }
            p.insert(small, 6);
            assert_eq!(p.selected_root(small), 6);
            p.clear();
            for &id in &keys {
                assert_eq!(p.selected_root(id), id);
            }
            p.canonical_phase(0);
            p.insert(small, 2);
            assert_eq!(p.selected_root(small), 2);
        }
    }
}
