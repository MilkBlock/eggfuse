// Publication changes a stable logical-ID directory and the slot's visibility.
// Box ownership may move; the allocation containing the actual Cell does not.
use super::Cell;
use rustc_hash::FxHashMap;
use serde::Serialize;
use serde_json::{Value as J, json};
use std::cell::Cell as Count;

pub(super) struct Lane {
    pub(super) frame: Option<Cell>,
    id: Option<u32>,
    header: usize,
    fact_buffer: usize,
}
impl Lane {
    pub(super) fn private(c: Cell) -> Self {
        Self {
            frame: Some(c),
            id: None,
            header: 0,
            fact_buffer: 0,
        }
    }
    pub(super) fn freeze(&mut self) {
        let c = self.frame.as_ref().expect("private Cell at freeze");
        self.header = c as *const Cell as usize;
        self.fact_buffer = c.facts.stage_allocation();
    }
}
struct Page {
    epoch: u64,
    lanes: Box<[Lane]>,
    live: usize,
    closed: bool,
}
#[derive(Default, Serialize)]
struct Metrics {
    grants: usize,
    published: usize,
    same_address: usize,
    same_fact_buffer: usize,
    private_dropped: usize,
    retired: usize,
    released_pages: usize,
    peak_pages: usize,
    peak_total_slots: usize,
    peak_held_holes: usize,
    closed_runs: usize,
    cumulative_held_hole_runs: u64,
    cumulative_resident_live_runs: u64,
}
#[derive(Default)]
pub struct NativeCells {
    ordinary: FxHashMap<u32, Cell>,
    // Zero encodes ordinary or absent; high/low bits describe a live slab slot.
    positions: Vec<usize>,
    outliers: FxHashMap<u32, usize>,
    pages: Vec<Option<Page>>,
    free: Vec<usize>,
    current: Vec<usize>,
    live: usize,
    occupied: usize,
    holes: usize,
    epoch: u64,
    width: usize,
    audit: bool,
    stats: Metrics,
    audited_reads: Count<u64>,
    old_run_reads: Count<u64>,
}
impl NativeCells {
    #[inline]
    fn position(&self, id: u32) -> Option<(usize, usize)> {
        if self.live == 0 {
            return None;
        }
        let n = self
            .positions
            .get(id as usize)
            .copied()
            .filter(|v| *v != 0)
            .or_else(|| {
                if self.outliers.is_empty() {
                    None
                } else {
                    self.outliers.get(&id).copied()
                }
            })?;
        Some(((n - 1) >> 8, (n - 1) & 255))
    }
    fn publish_position(&mut self, id: u32, page: usize, lane: usize) {
        let encoded = page
            .checked_mul(256)
            .and_then(|v| v.checked_add(lane + 1))
            .expect("slab index overflow");
        let i = id as usize;
        if i <= self.positions.len().saturating_add(65536) {
            if i >= self.positions.len() {
                self.positions.resize(i + 1, 0);
            }
            assert_eq!(self.positions[i], 0);
            self.positions[i] = encoded;
        } else {
            assert!(self.outliers.insert(id, encoded).is_none());
        }
    }
    fn forget_position(&mut self, id: &u32) {
        if let Some(n) = self.positions.get_mut(*id as usize)
            && *n != 0
        {
            *n = 0;
        } else {
            assert!(self.outliers.remove(id).is_some());
        }
    }
    pub(super) fn start(&mut self, epoch: u64, width: usize, pages: Vec<Box<[Lane]>>, audit: bool) {
        assert!(self.current.is_empty());
        self.epoch = epoch;
        self.width = width;
        self.audit = audit;
        for lanes in pages {
            self.stats.grants += lanes.len();
            self.occupied += lanes.len();
            let page = Page {
                epoch,
                lanes,
                live: 0,
                closed: false,
            };
            let key = if let Some(i) = self.free.pop() {
                self.pages[i] = Some(page);
                i
            } else {
                let i = self.pages.len();
                self.pages.push(Some(page));
                i
            };
            self.current.push(key);
        }
        self.stats.peak_total_slots = self.stats.peak_total_slots.max(self.occupied);
        self.stats.peak_pages = self
            .stats
            .peak_pages
            .max(self.pages.len() - self.free.len());
    }
    fn current_loc(&self, index: usize) -> (usize, usize) {
        (self.current[index / self.width], index % self.width)
    }
    pub(super) fn private_mut(&mut self, index: usize) -> &mut Cell {
        let (p, s) = self.current_loc(index);
        let lane = &mut self.pages[p].as_mut().unwrap().lanes[s];
        assert!(lane.id.is_none());
        lane.frame.as_mut().expect("issued nonempty private lane")
    }
    pub(super) fn publish(&mut self, id: u32, index: usize) -> usize {
        let (p, s) = self.current_loc(index);
        let page = self.pages[p].as_mut().unwrap();
        let lane = &mut page.lanes[s];
        let c = lane.frame.as_ref().expect("private frame at publication");
        assert!(lane.id.replace(id).is_none());
        assert!(!page.closed);
        let same = lane.header == c as *const Cell as usize;
        assert!(same, "publication moved the Cell header");
        let fact_buffer = lane.fact_buffer;
        self.stats.same_address += usize::from(same);
        self.stats.same_fact_buffer += usize::from(fact_buffer == c.facts.stage_allocation());
        page.live += 1;
        self.publish_position(id, p, s);
        self.live += 1;
        self.stats.published += 1;
        fact_buffer
    }
    fn release(&mut self, p: usize) {
        let page = self.pages[p].take().unwrap();
        assert_eq!(page.live, 0);
        self.occupied -= page.lanes.len();
        self.free.push(p);
        self.stats.released_pages += 1;
    }
    pub(super) fn finish(&mut self) {
        if self.width == 0 {
            return;
        }
        for i in 0..self.current.len() {
            let p = self.current[i];
            let page = self.pages[p].as_mut().unwrap();
            for lane in page.lanes.iter_mut() {
                if lane.id.is_none() && lane.frame.take().is_some() {
                    self.stats.private_dropped += 1;
                }
            }
            page.closed = true;
            if page.live == 0 {
                self.release(p)
            } else {
                self.holes += page.lanes.len() - page.live;
            }
        }
        self.current.clear();
        self.stats.closed_runs += 1;
        assert_eq!(self.occupied, self.live + self.holes);
        self.stats.peak_held_holes = self.stats.peak_held_holes.max(self.holes);
        self.stats.cumulative_held_hole_runs += self.holes as u64;
        self.stats.cumulative_resident_live_runs += self.live as u64;
    }
    pub fn get(&self, id: &u32) -> Option<&Cell> {
        let Some((p, i)) = self.position(*id) else {
            return self.ordinary.get(id);
        };
        let page = self.pages[p].as_ref().unwrap();
        let lane = &page.lanes[i];
        let c = lane.frame.as_ref().unwrap();
        if self.audit {
            assert_eq!(lane.id, Some(*id));
            assert_eq!(c as *const Cell as usize, lane.header);
            self.audited_reads.set(self.audited_reads.get() + 1);
            self.old_run_reads
                .set(self.old_run_reads.get() + u64::from(page.epoch != self.epoch));
        }
        Some(c)
    }
    pub fn get_mut(&mut self, id: &u32) -> Option<&mut Cell> {
        let Some((p, i)) = self.position(*id) else {
            return self.ordinary.get_mut(id);
        };
        let page = self.pages[p].as_mut().unwrap();
        let lane = &mut page.lanes[i];
        let c = lane.frame.as_mut().unwrap();
        if self.audit {
            assert_eq!(lane.id, Some(*id));
            assert_eq!(c as *const Cell as usize, lane.header);
            self.audited_reads.set(self.audited_reads.get() + 1);
            self.old_run_reads
                .set(self.old_run_reads.get() + u64::from(page.epoch != self.epoch));
        }
        Some(c)
    }
    pub fn contains_key(&self, id: &u32) -> bool {
        self.position(*id).is_some() || self.ordinary.contains_key(id)
    }
    pub fn insert(&mut self, id: u32, c: Cell) -> Option<Cell> {
        if let Some((p, i)) = self.position(id) {
            let lane = &mut self.pages[p].as_mut().unwrap().lanes[i];
            return Some(std::mem::replace(lane.frame.as_mut().unwrap(), c));
        }
        self.ordinary.insert(id, c)
    }
    pub fn remove(&mut self, id: &u32) -> Option<Cell> {
        let Some((p, i)) = self.position(*id) else {
            return self.ordinary.remove(id);
        };
        self.forget_position(id);
        let page = self.pages[p].as_mut().unwrap();
        let lane = &mut page.lanes[i];
        assert_eq!(lane.id.take(), Some(*id));
        let c = lane.frame.take().unwrap();
        page.live -= 1;
        self.live -= 1;
        self.stats.retired += 1;
        if page.closed {
            self.holes += 1;
            if page.live == 0 {
                self.holes -= page.lanes.len();
                self.release(p);
            }
            self.stats.peak_held_holes = self.stats.peak_held_holes.max(self.holes);
        }
        Some(c)
    }
    pub fn iter(&self) -> impl Iterator<Item = (&u32, &Cell)> {
        self.ordinary
            .iter()
            .chain(self.pages.iter().flatten().flat_map(|p| {
                p.lanes
                    .iter()
                    .filter_map(|lane| Some((lane.id.as_ref()?, lane.frame.as_ref()?)))
            }))
    }
    pub fn values(&self) -> impl Iterator<Item = &Cell> {
        self.iter().map(|(_, c)| c)
    }
    pub fn len(&self) -> usize {
        self.live + self.ordinary.len()
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
    pub(super) fn report(&self) -> J {
        json!({"published":self.stats.published,"same_address":self.stats.same_address,"alive":self.live,
            "held_holes":self.holes,"pages":self.pages.len()-self.free.len(),"header_slot_bytes":std::mem::size_of::<Lane>(),
            "occupied_slots":self.occupied,"reserved_header_bytes":self.occupied*std::mem::size_of::<Lane>(),
            "dense_directory_capacity_bytes":self.positions.capacity()*std::mem::size_of::<usize>(),
            "page_directory_capacity_bytes":self.pages.capacity()*std::mem::size_of::<Option<Page>>(),
            "free_directory_capacity_bytes":self.free.capacity()*std::mem::size_of::<usize>(),
            "ordinary_live":self.ordinary.len(),"ordinary_capacity":self.ordinary.capacity(),
            "outlier_count":self.outliers.len(),"width":self.width,"stats":self.stats,"pointer_checks":self.audited_reads.get(),
            "old_run_reads":self.old_run_reads.get()})
    }
}
impl std::ops::Index<&u32> for NativeCells {
    type Output = Cell;
    fn index(&self, id: &u32) -> &Cell {
        self.get(id).expect("logical Cell not visible")
    }
}
