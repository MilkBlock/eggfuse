use rustc_hash::FxHashMap;
use std::mem::size_of;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[repr(C)]
struct Word {
    id: u64,
    version: u64,
}

impl Word {
    fn from_ref(r: &Ref) -> (bool, Self) {
        let (fact, id) = match r.row {
            Dependency::Fact(f) => (true, (u64::from(f.cell) << 32) | u64::from(f.op)),
            Dependency::Function(address) => (false, address as u64),
        };
        (
            fact,
            Self {
                id,
                version: r.version,
            },
        )
    }

    fn decode(self, atom: usize, fact: bool) -> Option<Ref> {
        let row = if fact {
            Dependency::Fact(crate::graph::FactRef {
                cell: (self.id >> 32) as u32,
                op: self.id as u32,
            })
        } else {
            Dependency::Function(usize::try_from(self.id).ok()?)
        };
        Some(Ref {
            atom,
            row,
            version: self.version,
        })
    }
}

#[derive(Debug)]
struct Role {
    atom: usize,
    start: usize,
    words: usize,
    lane: usize,
    fact: bool,
    // 255 stores all words directly; 0 stores one constant word for the role.
    bytes: u8,
}

#[derive(Debug)]
struct Packed {
    roles: Box<[Role]>,
    words: Box<[Word]>,
    lanes: Box<[u8]>,
}

impl Packed {
    fn coordinate(&self, slot: usize, role: usize) -> Option<usize> {
        let r = self.roles.get(role)?;
        let index = match r.bytes {
            255 => slot,
            0 => 0,
            bytes @ (1 | 2 | 4) => {
                let p = r.lane.checked_add(slot.checked_mul(bytes as usize)?)?;
                let mut b = [0; 4];
                b[..bytes as usize]
                    .copy_from_slice(self.lanes.get(p..p.checked_add(bytes as usize)?)?);
                u32::from_le_bytes(b) as usize
            }
            _ => return None,
        };
        if index >= r.words {
            return None;
        }
        Some(index)
    }

    fn entry(&self, role: usize, index: usize) -> Option<Ref> {
        let r = self.roles.get(role)?;
        if index >= r.words {
            return None;
        }
        self.words
            .get(r.start.checked_add(index)?)?
            .decode(r.atom, r.fact)
    }
    fn parent(&self, slot: usize, role: usize) -> Option<Ref> {
        self.entry(role, self.coordinate(slot, role)?)
    }
    fn payload_bytes(&self) -> usize {
        self.roles.len() * size_of::<Role>()
            + self.words.len() * size_of::<Word>()
            + self.lanes.len()
    }
}

#[derive(Default)]
struct Column {
    atom: usize,
    fact: bool,
    words: Vec<Word>,
    ranks: Vec<u32>,
    dict: FxHashMap<Word, u32>,
}

pub(crate) struct FactorBuilder {
    cols: Vec<Column>,
    mode: u8,
    count: usize,
    // Retained only when the standalone source auditor is on.
    original: Option<Vec<Ref>>,
}

impl FactorBuilder {
    pub(crate) fn new(width: usize, mode: u8, audit: bool) -> Self {
        Self {
            cols: (0..width).map(|_| Column::default()).collect(),
            mode,
            count: 0,
            original: audit.then(Vec::new),
        }
    }
    pub(crate) fn count(&self) -> usize {
        self.count
    }

    pub(crate) fn append(&mut self, refs: impl ExactSizeIterator<Item = Ref>) -> Result<()> {
        if refs.len() != self.cols.len() {
            return Err("incomplete encoded parent tuple".into());
        }
        for (c, r) in self.cols.iter_mut().zip(refs) {
            let (fact, word) = Word::from_ref(&r);
            if self.count == 0 {
                c.atom = r.atom;
                c.fact = fact;
            } else if c.atom != r.atom || c.fact != fact {
                return Err("inconsistent source role in issued page".into());
            }
            if self.mode == 1 {
                c.words.push(word);
            } else {
                let next = u32::try_from(c.words.len()).map_err(|_| "role dictionary too large")?;
                let rank = *c.dict.entry(word).or_insert_with(|| {
                    c.words.push(word);
                    next
                });
                c.ranks.push(rank);
            }
            if let Some(v) = &mut self.original {
                v.push(r);
            }
        }
        self.count += 1;
        Ok(())
    }
    fn finish(self, fault: bool, stats: &mut FactorStats) -> Result<Packed> {
        let mut words = vec![];
        let mut lanes = vec![];
        let mut roles = Vec::with_capacity(self.cols.len());
        let width = self.cols.len();
        let mut corrupted = false;
        for c in self.cols {
            let unique = c.words.len();
            if unique == 0 {
                return Err("empty role in sealed page".into());
            }
            let bytes = if unique == 1 {
                0
            } else if unique <= 256 {
                1
            } else if unique <= 65536 {
                2
            } else {
                4
            };
            let direct = self.mode == 1
                || (self.mode >= 3
                    && unique * size_of::<Word>() + self.count * bytes
                        >= self.count * size_of::<Word>());
            let data_start = words.len();
            let lane = lanes.len();
            if direct {
                if self.mode == 1 {
                    words.extend_from_slice(&c.words);
                } else {
                    words.extend(c.ranks.iter().map(|i| c.words[*i as usize]));
                }
                stats.direct_roles += 1;
            } else {
                words.extend_from_slice(&c.words);
                if bytes > 0 {
                    for rank in c.ranks {
                        lanes.extend_from_slice(&rank.to_le_bytes()[..bytes]);
                    }
                }
                stats.dictionary_roles += 1;
                stats.constant_roles += u64::from(bytes == 0);
            }
            roles.push(Role {
                atom: c.atom,
                start: data_start,
                words: words.len() - data_start,
                lane,
                fact: c.fact,
                bytes: if direct { 255 } else { bytes as u8 },
            });
        }
        let mut packed = Packed {
            roles: roles.into_boxed_slice(),
            words: words.into_boxed_slice(),
            lanes: lanes.into_boxed_slice(),
        };
        if let Some(original) = self.original {
            for (i, r) in original.iter().enumerate() {
                let q = packed
                    .parent(i / width, i % width)
                    .ok_or("encoded audit coordinate invalid")?;
                if q.atom != r.atom || q.row != r.row || q.version != r.version {
                    return Err("encoded page changed an issued parent".into());
                }
            }
            stats.checked_refs += original.len() as u64;
        }
        if fault {
            for r in packed.roles.iter() {
                if matches!(r.bytes, 1 | 2 | 4) && (r.words as u64) < (1u64 << (8 * r.bytes)) {
                    let bad = (r.words as u32).to_le_bytes();
                    packed.lanes[r.lane..r.lane + r.bytes as usize]
                        .copy_from_slice(&bad[..r.bytes as usize]);
                    corrupted = true;
                    break;
                }
            }
        }
        stats.coordinate_faults += u64::from(corrupted);
        stats.word_bytes += (packed.words.len() * size_of::<Word>()) as u64;
        stats.lane_bytes += packed.lanes.len() as u64;
        stats.role_bytes += (packed.roles.len() * size_of::<Role>()) as u64;
        Ok(packed)
    }
}

#[derive(Debug)]
enum FactorStore {
    Flat(Vec<Ref>),
    Packed(Box<Packed>),
}

impl FactorStore {
    fn read<'a>(&'a self, slot: usize, width: usize, buf: &'a mut Vec<Ref>) -> Result<&'a [Ref]> {
        match self {
            Self::Flat(refs) => {
                let k = slot.checked_mul(width).ok_or("flat page offset overflow")?;
                refs.get(k..k.checked_add(width).ok_or("flat page end overflow")?)
                    .ok_or_else(|| "flat page offset out of range".into())
            }
            Self::Packed(p) => {
                buf.clear();
                for role in 0..width {
                    buf.push(
                        p.parent(slot, role)
                            .ok_or("invalid encoded parent coordinate")?,
                    );
                }
                Ok(buf)
            }
        }
    }
}

#[derive(Default, Serialize)]
struct FactorStats {
    pages: u64,
    canonical_wire_bytes: u64,
    audited_wire_bytes: u64,
    encoded_wire_hash: u64,
    refs: u64,
    flat_transfer_bytes: u64,
    body_bytes: u64,
    retained_bytes: u64,
    flat_pages: u64,
    packed_pages: u64,
    streamed_pages: u64,
    direct_roles: u64,
    dictionary_roles: u64,
    constant_roles: u64,
    word_bytes: u64,
    lane_bytes: u64,
    role_bytes: u64,
    checked_refs: u64,
    coordinate_faults: u64,
}

pub fn configure_factor(mode: u64, fault: bool) -> Result<()> {
    if mode > 4 || (fault && mode != 2) {
        return Err("invalid factor policy".into());
    }
    STATE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("root issuer not configured")?;
        s.factor_mode = mode as u8;
        s.factor_fault = fault;
        Ok(())
    })
}

pub(crate) fn streamed_page(
    run: u64,
    rid: usize,
    builder: FactorBuilder,
    fault: u8,
) -> Result<MultiPage> {
    let count = builder.count;
    let width = builder.cols.len();
    STATE.with_borrow_mut(|s| {
        let st = s.as_mut().ok_or("no root issuer")?;
        let packed = builder.finish(false, &mut st.factor_stats)?;
        st.factor_stats.streamed_pages += 1;
        seal_factor_page(
            run,
            rid,
            width,
            count,
            FactorStore::Packed(Box::new(packed)),
            fault,
            st,
        )
    })
}

pub(crate) fn multi_page(
    run: u64,
    rid: usize,
    width: usize,
    refs: Vec<Ref>,
    fault: u8,
) -> Result<MultiPage> {
    if width < 2 || refs.is_empty() || refs.len() % width != 0 {
        return Err("incomplete multi-parent page".into());
    }
    let count = refs.len() / width;
    STATE.with_borrow_mut(|s| {
        let st = s.as_mut().ok_or("multi page requires active issuer")?;
        let store = if st.factor_mode == 0 {
            FactorStore::Flat(refs)
        } else {
            let mut builder = FactorBuilder::new(width, st.factor_mode, st.audit);
            let mut input = refs.into_iter();
            for _ in 0..count {
                builder.append(input.by_ref().take(width))?;
            }
            FactorStore::Packed(Box::new(
                builder.finish(st.factor_fault, &mut st.factor_stats)?,
            ))
        };
        seal_factor_page(run, rid, width, count, store, fault, st)
    })
}

fn seal_factor_page(
    run: u64,
    rid: usize,
    width: usize,
    count: usize,
    store: FactorStore,
    fault: u8,
    st: &mut State,
) -> Result<MultiPage> {
    if !matches!(st.encoding, Encoding::Resident | Encoding::CheckedSlots) {
        return Err("multi page requires resident root encoding".into());
    }
    let layout = st.layout.get(rid).ok_or("invalid page rule")?.clone();
    let first_serial = st.serial.checked_add(1).ok_or("root serial overflow")?;
    let end = st
        .serial
        .checked_add(count as u64)
        .ok_or("root page serial overflow")?;
    let template = if st.mode == "wrong-template" || fault == 2 {
        layout.template.wrapping_add(1)
    } else {
        layout.template
    };
    let mut buf = Vec::new();
    for slot in 0..count {
        for word in [
            first_serial + slot as u64,
            run,
            rid as u64,
            layout.template as u64,
            width as u64,
        ] {
            st.raw = (st.raw ^ word).wrapping_mul(1099511628211);
        }
        for r in store.read(slot, width, &mut buf)? {
            let (fact, value) = Word::from_ref(r);
            for word in [
                r.atom as u64,
                if fact { 1 } else { 2 },
                value.id,
                value.version,
            ] {
                st.raw = (st.raw ^ word).wrapping_mul(1099511628211);
            }
        }
    }
    st.serial = end;
    st.emitted[1] += count as u64;
    let stats = &mut st.factor_stats;
    stats.canonical_wire_bytes += store.wire_bytes() as u64;
    if st.audit {
        let flags = u64::from(fault == 3 || st.mode == "withhold")
            | (u64::from(fault == 1 || st.mode == "wrong-port") << 1);
        let encoded = u64::from(matches!(&store, FactorStore::Packed(_)));
        store.audit_wire(
            [
                0x31475046,
                run,
                rid as u64,
                template as u64,
                first_serial,
                count as u64,
                width as u64,
                flags,
                encoded,
            ],
            stats,
        )?;
    }
    stats.pages += 1;
    stats.refs += (width * count) as u64;
    stats.flat_transfer_bytes += (width * count * size_of::<Ref>()) as u64;
    let (body, capacity) = match &store {
        FactorStore::Flat(v) => {
            stats.flat_pages += 1;
            (v.len() * size_of::<Ref>(), v.capacity() * size_of::<Ref>())
        }
        FactorStore::Packed(p) => {
            stats.packed_pages += 1;
            (p.payload_bytes(), p.payload_bytes() + size_of::<Packed>())
        }
    };
    stats.body_bytes += body as u64;
    stats.retained_bytes += (capacity + size_of::<MultiPageData>() + 2 * size_of::<usize>()) as u64;
    Ok(MultiPage(Rc::new(MultiPageData {
        run,
        first_serial,
        width,
        count,
        layout,
        template,
        store,
        withheld: st.mode == "withhold" || fault == 3,
        invalid_version: st.mode == "wrong-port" || fault == 1,
    })))
}

// All three indices are page-local. These accessors let a verifier reuse the
// exact checked source row for one role/word while preserving tuple order.
impl MultiPage {
    pub(crate) fn role_len(&self, role: usize) -> Option<usize> {
        let FactorStore::Packed(p) = &self.0.store else {
            return None;
        };
        Some(p.roles.get(role)?.words)
    }

    pub(crate) fn role_parent(&self, role: usize, coordinate: usize) -> Option<Ref> {
        let FactorStore::Packed(p) = &self.0.store else {
            return None;
        };
        p.entry(role, coordinate)
    }

    pub(crate) fn coordinate(&self, slot: usize, role: usize) -> Result<Option<usize>> {
        if slot >= self.0.count || role >= self.0.width {
            return Err("invalid tuple/role position".into());
        }
        let FactorStore::Packed(p) = &self.0.store else {
            return Ok(None);
        };
        Ok(Some(
            p.coordinate(slot, role)
                .ok_or("invalid encoded parent coordinate")?,
        ))
    }
}

include!("factor_wire.rs");
