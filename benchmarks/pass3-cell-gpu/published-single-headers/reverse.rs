#[derive(Default, Serialize)]
struct ReverseHeaderStats {
    attempts: u64,
    view_builds: u64,
    view_hits: u64,
    build_source_rows: u64,
    domain_keys: u64,
    rejected_dense: u64,
    routed_calls: u64,
    source_rows: u64,
    selected: u64,
    enumerated_offsets: u64,
    audited: u64,
    evictions: u64,
    peak_bytes: usize,
}
struct SourcePostings {
    generation: u64,
    union: u64,
    last: u64,
    starts: Vec<u32>,
    ids: Vec<u32>,
    occupied: Vec<u16>,
}
impl SourcePostings {
    fn bytes(&self) -> usize {
        self.starts.capacity() * 4 + self.ids.capacity() * 4 + self.occupied.capacity() * 2
    }
}
#[derive(Default)]
struct HeaderRouter {
    views: HashMap<(usize, usize), SourcePostings>,
    tick: u64,
    stats: ReverseHeaderStats,
}
impl HeaderRouter {
    const LIMIT: usize = 2 << 20;
    fn route(
        &mut self,
        g: &Graph,
        owner: usize,
        col: usize,
        bank: &[SourceHeader],
        codes: &[u16],
        proofs: &[ProofAtom],
        wm: u64,
        encode: &impl Fn(&Value) -> usize,
    ) -> Option<(Vec<SourceHeader>, u64)> {
        if bank.len() < 128 || codes.len() != bank.len() {
            return None;
        }
        self.stats.attempts += 1;
        self.tick += 1;
        let key = (owner, col);
        let stamp = g.query_versions[owner];
        let available = self.views.get(&key).is_some_and(|v| {
            v.generation == stamp && v.union == g.stats.unions && v.ids.len() == bank.len()
        });
        if !available {
            self.views.remove(&key);
            let mut counts = vec![0u32; (1 << B) + 1];
            for &k in codes {
                counts[k as usize + 1] += 1
            }
            let occupied = counts[1..]
                .iter()
                .enumerate()
                .filter_map(|(i, &n)| (n != 0).then_some(i as u16))
                .collect::<Vec<_>>();
            for i in 1..counts.len() {
                counts[i] += counts[i - 1]
            }
            let mut cursor = counts.clone();
            let mut ids = vec![0; bank.len()];
            for (i, &k) in codes.iter().enumerate() {
                let ptr = &mut cursor[k as usize];
                ids[*ptr as usize] = i as u32;
                *ptr += 1;
            }
            let p = SourcePostings {
                generation: stamp,
                union: g.stats.unions,
                last: self.tick,
                starts: counts,
                ids,
                occupied,
            };
            let need = p.bytes();
            if need > Self::LIMIT {
                return None;
            }
            let mut used: usize = self.views.values().map(SourcePostings::bytes).sum();
            while used + need > Self::LIMIT {
                let k = *self.views.iter().min_by_key(|(_, v)| v.last)?.0;
                used -= self.views.remove(&k)?.bytes();
                self.stats.evictions += 1
            }
            self.views.insert(key, p);
            self.stats.peak_bytes = self.stats.peak_bytes.max(used + need);
            self.stats.view_builds += 1;
            self.stats.build_source_rows += bank.len() as u64;
        } else {
            self.stats.view_hits += 1
        }
        let p = self.views.get_mut(&key)?;
        p.last = self.tick;
        let mut probe_count = 0u64;
        let mut hits = Vec::new();
        let mut size = 0;
        for &k in &p.occupied {
            self.stats.domain_keys += 1;
            if proofs.iter().any(|a| {
                a.parts.iter().zip(&a.cols).all(|(src, (_, dir))| {
                    let Some(hi) = dir else { return true };
                    let j = match src {
                        KeyPart::Port(_) => usize::from(k),
                        KeyPart::Constant(v) => encode(v),
                    };
                    probe_count += 1;
                    hi[j] >= wm
                })
            }) {
                let j = k as usize;
                size += (p.starts[j + 1] - p.starts[j]) as usize;
                hits.push(k)
            }
        }
        let view = g.header_bank(owner);
        let fresh = g.header_offsets(&view, wm);
        if size + fresh.len() > bank.len() / 2 {
            self.stats.rejected_dense += 1;
            return None;
        }
        let mut offsets = Vec::with_capacity(size + fresh.len());
        offsets.extend_from_slice(&fresh);
        for k in hits {
            let i = k as usize;
            offsets.extend_from_slice(&p.ids[p.starts[i] as usize..p.starts[i + 1] as usize]);
        }
        self.stats.enumerated_offsets += offsets.len() as u64;
        offsets.sort_unstable();
        offsets.dedup();
        if g.header_audit {
            let expected = (0..bank.len()).filter(|&i| {
                bank[i].version >= wm
                    || proofs.iter().any(|a| {
                        a.parts.iter().zip(&a.cols).all(|(s, (_, d))| {
                            d.as_ref().is_none_or(|hi| {
                                hi[match s {
                                    KeyPart::Port(_) => codes[i] as usize,
                                    KeyPart::Constant(v) => encode(v),
                                }] >= wm
                            })
                        })
                    })
            });
            assert!(
                expected.eq(offsets.iter().map(|i| *i as usize)),
                "posting produced a wrong or missing learned source"
            );
            self.stats.audited += bank.len() as u64
        }
        self.stats.routed_calls += 1;
        self.stats.source_rows += bank.len() as u64;
        self.stats.selected += offsets.len() as u64;
        Some((
            offsets.into_iter().map(|i| bank[i as usize]).collect(),
            probe_count,
        ))
    }
}
