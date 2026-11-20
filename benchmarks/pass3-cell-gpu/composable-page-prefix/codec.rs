// Offline archive diagnostic attached to already-frozen original pages. No source query is issued here.
// Each checkpoint owns complete witnesses; seeks only read this immutable tuple stream.
#[derive(Default, serde::Serialize)]
struct WireBudget {
    pages: u64,
    tuples: u64,
    raw_bytes: u64,
    first_bytes: u64,
    full_bytes: u64,
    block_first_bytes: u64,
    block_full_bytes: u64,
    peak_raw: u64,
    peak_full: u64,
    page_allocation_count: u64,
    encoded_buffer_allocations: u64,
    seek_checks: u64,
    field_replay_checks: u64,
    max_seek_tuples: usize,
}
fn words(p: &crate::joint_root::Ref) -> [u64; 4] {
    let (tag, physical) = match p.row {
        Dependency::Fact(f) => (1, (u64::from(f.cell) << 32) | u64::from(f.op)),
        Dependency::Function(i) => (2, i as u64),
    };
    [p.atom as u64, tag, physical, p.version]
}
fn tuple_lcp(page: &crate::joint_root::MultiPage, i: usize) -> usize {
    if i == 0 {
        return 0;
    }
    page.parents(i)
        .iter()
        .zip(page.parents(i - 1))
        .take_while(|(a, b)| same_page_ref(a, b))
        .count()
}
struct Wire {
    body: Vec<u8>,
    offsets: Vec<u32>,
}
impl Wire {
    fn encode(page: &crate::joint_root::MultiPage, limit: usize, block: usize) -> Self {
        let mut body_bytes = 0;
        for i in 0..page.count() {
            let lcp = if i % block == 0 {
                0
            } else {
                tuple_lcp(page, i).min(limit)
            };
            body_bytes += 1 + 32 * (page.parents(i).len() - lcp);
        }
        let mut body = Vec::with_capacity(body_bytes);
        let mut offsets = Vec::with_capacity(page.count().div_ceil(block));
        for i in 0..page.count() {
            let row = page.parents(i);
            let lcp = if i % block == 0 {
                offsets.push(u32::try_from(body.len()).expect("bounded page"));
                0
            } else {
                tuple_lcp(page, i).min(limit)
            };
            body.push(u8::try_from(lcp).expect("page prefix exceeds one byte"));
            for entry in &row[lcp..] {
                for v in words(entry) {
                    body.extend_from_slice(&v.to_le_bytes());
                }
            }
        }
        assert_eq!(body_bytes, body.len());
        Self { body, offsets }
    }
    fn step(&self, pos: &mut usize, prev: &mut Vec<[u64; 4]>, row: &[crate::joint_root::Ref]) {
        let share = self.body[*pos] as usize;
        *pos += 1;
        assert!(share <= prev.len() && share <= row.len());
        prev.truncate(share);
        for _ in share..row.len() {
            let w = std::array::from_fn(|_| {
                let n = u64::from_le_bytes(self.body[*pos..*pos + 8].try_into().unwrap());
                *pos += 8;
                n
            });
            prev.push(w);
        }
        assert!(
            row.iter().map(words).eq(prev.iter().copied()),
            "decoded source address, atom, or version changed"
        );
    }
    fn allocation_bytes(&self) -> u64 {
        (self.body.capacity() + self.offsets.capacity() * std::mem::size_of::<u32>()) as u64
    }
}
impl WireBudget {
    fn observe(&mut self, page: &crate::joint_root::MultiPage) {
        let count = page.count();
        if count == 0 {
            return;
        }
        let raw = (count * page.parents(0).len() * 32) as u64;
        self.raw_bytes += raw;
        self.pages += 1;
        self.tuples += count as u64;
        self.peak_raw = self.peak_raw.max(raw);
        self.page_allocation_count += 1;
        // Two separate schema choices. Body plus restart directory make exactly two allocations.
        for (limit, block) in [
            (1, usize::MAX),
            (usize::MAX, usize::MAX),
            (1, 32),
            (usize::MAX, 32),
        ] {
            let archive = Wire::encode(page, limit, block);
            let charged = archive.allocation_bytes();
            match (limit, block) {
                (1, usize::MAX) => self.first_bytes += charged,
                (_, usize::MAX) => self.full_bytes += charged,
                (1, _) => self.block_first_bytes += charged,
                _ => {
                    self.block_full_bytes += charged;
                    self.peak_full = self.peak_full.max(charged);
                    self.encoded_buffer_allocations += 2;
                }
            }
            let mut pos = 0;
            let mut prior = Vec::with_capacity(page.parents(0).len());
            for i in 0..count {
                archive.step(&mut pos, &mut prior, page.parents(i));
                self.field_replay_checks += page.parents(i).len() as u64;
            }
            assert_eq!(pos, archive.body.len());
            if block == 32 {
                // Seek backwards through checkpoint blocks, issuing the final tuple of each block independently.
                for b in (0..archive.offsets.len()).rev() {
                    let start = b * block;
                    let end = (start + block).min(count);
                    prior.clear();
                    let mut at = archive.offsets[b] as usize;
                    for i in start..end {
                        archive.step(&mut at, &mut prior, page.parents(i));
                    }
                    self.seek_checks += 1;
                    self.max_seek_tuples = self.max_seek_tuples.max(end - start);
                }
            }
        }
    }
}
