// A learned query/key signature has the same compatibility relation in every
// typed table. Factor this relation out of individual table versions. A table
// indexes only its own physical rows; exact source predicates are still checked
// after sealing the resulting ordered address tuples.
use rustc_hash::{FxHashMap, FxHashSet};

const CODE_MASK: u32 = (1 << B) - 1;
fn packed(port: Port, key: bool, views: usize) -> u32 {
    let axis = usize::from(key);
    let mut value = if key {
        port.key as u32
    } else {
        port.query as u32
    };
    for i in 1..views {
        value |= (port.extra[i - 1][axis] as u32) << (B * i);
    }
    value
}
fn matches_codes(q: u32, k: u32, views: usize, radius: u32) -> bool {
    let delta = q ^ k;
    (0..views).all(|i| ((delta >> (B * i)) & CODE_MASK).count_ones() <= radius)
}
#[derive(Default, Serialize)]
struct SignatureStats {
    global_keys: u64,
    global_queries: u64,
    verified_code_pairs: u64,
    compatible_code_pairs: u64,
    built_table_indexes: u64,
    indexed_rows: u64,
    shortlist_reads: u64,
    multi_group_reads: u64,
    joined_buckets: u64,
    nonempty_buckets: u64,
    empty_lists: u64,
    single_bucket_returns: u64,
}
struct GlobalTable {
    version: u64,
    bins: FxHashMap<u32, Rc<Vec<usize>>>,
    first: Vec<u16>,
    merged: RefCell<FxHashMap<u32, Rc<Vec<usize>>>>,
}
struct SignatureJoin {
    enabled: bool,
    seen: FxHashSet<u32>,
    keys: Vec<Vec<u32>>,
    queries: Vec<Vec<u32>>,
    neighbors: FxHashMap<u32, Rc<Vec<u32>>>,
    tables: FxHashMap<(usize, usize), Rc<GlobalTable>>,
    empty: Rc<Vec<usize>>,
    stats: SignatureStats,
}
impl SignatureJoin {
    fn new(enabled: bool) -> Self {
        Self {
            enabled,
            seen: Default::default(),
            keys: if enabled {
                vec![vec![]; 1 << B]
            } else {
                vec![]
            },
            queries: if enabled {
                vec![vec![]; 1 << B]
            } else {
                vec![]
            },
            neighbors: Default::default(),
            tables: Default::default(),
            empty: Rc::new(Vec::new()),
            stats: Default::default(),
        }
    }
    fn add_key(&mut self, k: u32, masks: &[u16], views: usize, radius: u32) {
        if !self.seen.insert(k) {
            return;
        }
        self.stats.global_keys += 1;
        let first = (k & CODE_MASK) as u16;
        self.keys[first as usize].push(k);
        for &delta in masks {
            for &q in &self.queries[(first ^ delta) as usize] {
                self.stats.verified_code_pairs += 1;
                if matches_codes(q, k, views, radius) {
                    Rc::make_mut(self.neighbors.get_mut(&q).unwrap()).push(k);
                    self.stats.compatible_code_pairs += 1;
                }
            }
        }
    }
    fn query(&mut self, q: u32, masks: &[u16], views: usize, radius: u32) -> Rc<Vec<u32>> {
        if let Some(found) = self.neighbors.get(&q) {
            return found.clone();
        }
        let mut found = vec![];
        self.stats.global_queries += 1;
        let first = (q & CODE_MASK) as u16;
        self.queries[first as usize].push(q);
        for &delta in masks {
            for &k in &self.keys[(first ^ delta) as usize] {
                self.stats.verified_code_pairs += 1;
                if matches_codes(q, k, views, radius) {
                    found.push(k);
                    self.stats.compatible_code_pairs += 1;
                }
            }
        }
        let result = Rc::new(found);
        self.neighbors.insert(q, result.clone());
        result
    }
}
impl Store {
    fn full_code_table(&mut self, frame: &Frame, col: usize) -> Rc<GlobalTable> {
        let id = (frame.table, col);
        if let Some(old) = self.signatures.tables.get(&id)
            && old.version == frame.generation
        {
            return old.clone();
        }
        let mut bins: FxHashMap<u32, Rc<Vec<usize>>> = FxHashMap::default();
        let mut first = Vec::with_capacity(frame.rows.len());
        for (i, row) in frame.rows.iter().enumerate() {
            let code = packed(self.code(&row.values[col]), true, self.views);
            self.signatures
                .add_key(code, &self.reverse_masks, self.views, self.radius);
            first.push((code & CODE_MASK) as u16);
            Rc::get_mut(bins.entry(code).or_default()).unwrap().push(i);
        }
        self.signatures.stats.built_table_indexes += 1;
        self.signatures.stats.indexed_rows += first.len() as u64;
        let table = Rc::new(GlobalTable {
            version: frame.generation,
            bins,
            first,
            merged: Default::default(),
        });
        self.signatures.tables.insert(id, table.clone());
        table
    }
    fn full_code_list(&mut self, tab: &GlobalTable, port: Port) -> Rc<Vec<usize>> {
        self.signatures.stats.shortlist_reads += 1;
        let q = packed(port, false, self.views);
        let keys = self
            .signatures
            .query(q, &self.reverse_masks, self.views, self.radius);
        if keys.len() <= 1 {
            if let Some(k) = keys.first()
                && let Some(rows) = tab.bins.get(k)
            {
                self.signatures.stats.single_bucket_returns += 1;
                return rows.clone();
            }
            self.signatures.stats.empty_lists += 1;
            return self.signatures.empty.clone();
        }
        self.signatures.stats.multi_group_reads += 1;
        if let Some(prev) = tab.merged.borrow().get(&q) {
            return prev.clone();
        }
        let mut relevant = keys.iter().filter_map(|k| tab.bins.get(k));
        let first = relevant.next();
        let second = relevant.next();
        let result = match (first, second) {
            (None, _) => self.signatures.empty.clone(),
            (Some(rows), None) => rows.clone(),
            (Some(x), Some(y)) => {
                let mut selected = Vec::with_capacity(x.len() + y.len());
                selected.extend(x.iter().copied());
                selected.extend(y.iter().copied());
                for positions in relevant {
                    selected.extend(positions.iter().copied());
                }
                let first = (q & CODE_MASK) as u16;
                selected.sort_unstable_by_key(|i| {
                    let key = tab.first[*i];
                    let order = if self.radius <= 1 {
                        let d = first ^ key;
                        if d == 0 {
                            0
                        } else {
                            1 + d.trailing_zeros() as u16
                        }
                    } else {
                        key
                    };
                    (order, *i)
                });
                Rc::new(selected)
            }
        };
        self.signatures.stats.joined_buckets += keys.len() as u64;
        self.signatures.stats.nonempty_buckets +=
            keys.iter().filter(|k| tab.bins.contains_key(k)).count() as u64;
        // An existing table snapshot cannot gain a missing key when another
        // table introduces a new global signature. Its merged lists remain valid.
        tab.merged.borrow_mut().insert(q, result.clone());
        result
    }
}
