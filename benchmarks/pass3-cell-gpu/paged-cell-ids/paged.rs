// Source addresses remain (Cell id, op). Rank within a live bitmap is private storage.
use super::Cell;
use rustc_hash::FxHashMap;
use serde_json::{Value as Json, json};

#[derive(Default)]
struct Page {
    live: u64,
    entries: Vec<(u32, Cell)>,
}
impl Page {
    #[inline]
    fn rank(&self, bit: u64) -> usize {
        (self.live & (bit - 1)).count_ones() as usize
    }
    fn get(&self, bit: u64) -> Option<&Cell> {
        if self.live & bit == 0 {
            return None;
        }
        Some(&self.entries[self.rank(bit)].1)
    }
    fn get_mut(&mut self, bit: u64) -> Option<&mut Cell> {
        if self.live & bit == 0 {
            return None;
        }
        let i = self.rank(bit);
        Some(&mut self.entries[i].1)
    }
}
pub struct PackedCells<const W: u32> {
    primary: Vec<Page>,
    sparse: FxHashMap<u32, Page>,
    count: usize,
    inserted: u64,
    removed: u64,
    shifts: u64,
    retired_pages: u64,
}
impl<const W: u32> Default for PackedCells<W> {
    fn default() -> Self {
        assert!(matches!(W, 16 | 64));
        Self {
            primary: Vec::new(),
            sparse: FxHashMap::default(),
            count: 0,
            inserted: 0,
            removed: 0,
            shifts: 0,
            retired_pages: 0,
        }
    }
}
impl<const W: u32> PackedCells<W> {
    #[inline]
    fn bit(id: u32) -> u64 {
        1u64 << (id % W)
    }
    #[inline]
    fn page(&self, id: u32) -> Option<&Page> {
        self.primary
            .get((id / W) as usize)
            .or_else(|| self.sparse.get(&(id / W)))
    }
    pub fn get(&self, id: &u32) -> Option<&Cell> {
        self.page(*id)?.get(Self::bit(*id))
    }
    pub fn contains_key(&self, id: &u32) -> bool {
        self.get(id).is_some()
    }
    pub fn get_mut(&mut self, id: &u32) -> Option<&mut Cell> {
        let p = *id / W;
        self.primary
            .get_mut(p as usize)
            .or_else(|| self.sparse.get_mut(&p))?
            .get_mut(Self::bit(*id))
    }
    pub fn insert(&mut self, id: u32, c: Cell) -> Option<Cell> {
        let p = id / W;
        if p as usize >= self.primary.len() && (p as usize) - self.primary.len() <= 64 {
            self.primary.resize_with(p as usize + 1, Page::default);
            // A previously isolated high page may now fall inside the direct directory.
            if !self.sparse.is_empty() {
                self.sparse.retain(|key, page| {
                    if let Some(slot) = self.primary.get_mut(*key as usize) {
                        *slot = std::mem::take(page);
                        false
                    } else {
                        true
                    }
                })
            }
        }
        let page = if let Some(page) = self.primary.get_mut(p as usize) {
            page
        } else {
            self.sparse.entry(p).or_default()
        };
        let bit = Self::bit(id);
        let i = page.rank(bit);
        if page.live & bit != 0 {
            return Some(std::mem::replace(&mut page.entries[i].1, c));
        }
        self.shifts += (page.entries.len() - i) as u64;
        page.entries.insert(i, (id, c));
        page.live |= bit;
        self.count += 1;
        self.inserted += 1;
        None
    }
    pub fn remove(&mut self, id: &u32) -> Option<Cell> {
        let p = *id / W;
        let direct = (p as usize) < self.primary.len();
        let page = if direct {
            &mut self.primary[p as usize]
        } else {
            self.sparse.get_mut(&p)?
        };
        let bit = Self::bit(*id);
        if page.live & bit == 0 {
            return None;
        }
        let i = page.rank(bit);
        self.shifts += (page.entries.len() - i - 1) as u64;
        let (_, c) = page.entries.remove(i);
        page.live ^= bit;
        self.count -= 1;
        self.removed += 1;
        if page.live == 0 {
            self.retired_pages += 1;
            if direct {
                page.entries = Vec::new()
            } else {
                self.sparse.remove(&p);
            }
        }
        Some(c)
    }
    pub fn values(&self) -> impl Iterator<Item = &Cell> {
        self.primary
            .iter()
            .chain(self.sparse.values())
            .flat_map(|p| p.entries.iter().map(|(_, c)| c))
    }
    pub fn iter(&self) -> impl Iterator<Item = (&u32, &Cell)> {
        self.primary
            .iter()
            .chain(self.sparse.values())
            .flat_map(|p| p.entries.iter().map(|(i, c)| (i, c)))
    }
    pub fn is_empty(&self) -> bool {
        self.count == 0
    }
    pub fn len(&self) -> usize {
        self.count
    }
    pub fn placement_report(&self) -> Json {
        let mut hist = vec![0usize; W as usize + 1];
        let mut reserved = 0;
        for page in self.primary.iter().chain(self.sparse.values()) {
            hist[page.entries.len()] += 1;
            reserved += page.entries.capacity();
        }
        json!({"layout":"rank-page","width":W,"live":self.count,"primary":self.primary.len(),"outliers":self.sparse.len(),
               "histogram":hist,"record_capacity":reserved,"stored_record_bytes":std::mem::size_of::<(u32,Cell)>(),
               "inserted":self.inserted,"removed":self.removed,"shifted":self.shifts,"retired_pages":self.retired_pages})
    }
}
impl<const W: u32> std::ops::Index<&u32> for PackedCells<W> {
    type Output = Cell;
    fn index(&self, id: &u32) -> &Cell {
        self.get(id).expect("missing Cell")
    }
}

#[cfg(test)]
mod logical_page_tests {
    use super::*;
    fn cell(t: usize) -> Cell {
        Cell {
            template: t,
            started_epoch: 0,
            parent: None,
            values: Default::default(),
            facts: Default::default(),
            completed: false,
            completed_prefix: 0,
            recipe_depth: 0,
        }
    }
    fn exercise<const W: u32>() {
        let mut store = PackedCells::<W>::default();
        let mut truth = std::collections::BTreeMap::new();
        for (t, id) in [
            u32::MAX,
            W * 70 + 4,
            2,
            0,
            W - 1,
            W * 10,
            W * 70 + 3,
            W,
            W + 2,
            W + 1,
            W * 50,
            W * 70 + 4,
            0,
        ]
        .into_iter()
        .enumerate()
        {
            let old = truth.insert(id, t);
            assert_eq!(store.insert(id, cell(t)).map(|c| c.template), old);
            for (&key, &value) in &truth {
                assert_eq!(store[&key].template, value);
            }
        }
        assert!(store.primary.len() < 100);
        for id in [W + 1, 0, u32::MAX, W * 70 + 4, W + 1, W - 1] {
            assert_eq!(store.remove(&id).map(|c| c.template), truth.remove(&id));
            assert_eq!(store.len(), truth.len());
            assert_eq!(
                store
                    .iter()
                    .map(|(i, c)| (*i, c.template))
                    .collect::<std::collections::BTreeMap<_, _>>(),
                truth
            );
        }
        store.get_mut(&2).unwrap().template = 117;
        assert_eq!(store[&2].template, 117);
    }
    #[test]
    fn sparse_keys_rank_and_retirement() {
        exercise::<16>();
        exercise::<64>();
    }
}
