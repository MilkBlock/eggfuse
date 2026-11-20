// Fixed little-endian export of one native receipt page used by the detailed
// audit. Offsets are implicit in the dictionary counts and coordinate widths.
const WIRE_HEAD: usize = 9 * 8;
const WIRE_ROLE: usize = 8 + 1 + 1 + 8;

impl FactorStore {
    fn wire_bytes(&self) -> usize {
        WIRE_HEAD
            + match self {
                Self::Flat(refs) => refs.len() * 32,
                Self::Packed(p) => p.roles.len() * WIRE_ROLE + p.words.len() * 16 + p.lanes.len(),
            }
    }

    fn audit_wire(&self, header: [u64; 9], stats: &mut FactorStats) -> Result<()> {
        let count = usize::try_from(header[5]).map_err(|_| "invalid wire count")?;
        let width = usize::try_from(header[6]).map_err(|_| "invalid wire width")?;
        let mut bytes = Vec::with_capacity(self.wire_bytes());
        for w in header {
            bytes.extend_from_slice(&w.to_le_bytes());
        }
        match self {
            Self::Flat(refs) => {
                for r in refs {
                    let (fact, v) = Word::from_ref(r);
                    for x in [r.atom as u64, u64::from(fact), v.id, v.version] {
                        bytes.extend_from_slice(&x.to_le_bytes());
                    }
                }
            }
            Self::Packed(p) => {
                for r in &p.roles {
                    bytes.extend_from_slice(&(r.atom as u64).to_le_bytes());
                    bytes.extend([u8::from(r.fact), r.bytes]);
                    bytes.extend_from_slice(&(r.words as u64).to_le_bytes());
                    for v in &p.words[r.start..r.start + r.words] {
                        bytes.extend_from_slice(&v.id.to_le_bytes());
                        bytes.extend_from_slice(&v.version.to_le_bytes());
                    }
                    if r.bytes != 255 {
                        bytes
                            .extend_from_slice(&p.lanes[r.lane..r.lane + count * r.bytes as usize]);
                    }
                }
            }
        }
        if bytes.len() != self.wire_bytes() {
            return Err("incorrect canonical wire size".into());
        }
        let mut wire = bytes.as_slice();
        for expected in header {
            if wire_word(&mut wire)? != expected {
                return Err("wrong page header".into());
            }
        }
        let mut scratch = Vec::new();
        if header[8] == 0 {
            for slot in 0..count {
                for r in self.read(slot, width, &mut scratch)? {
                    let (fact, v) = Word::from_ref(r);
                    if [
                        wire_word(&mut wire)?,
                        wire_word(&mut wire)?,
                        wire_word(&mut wire)?,
                        wire_word(&mut wire)?,
                    ] != [r.atom as u64, u64::from(fact), v.id, v.version]
                    {
                        return Err("incorrect flat wire row".into());
                    }
                }
            }
        } else {
            let mut roles = Vec::with_capacity(width);
            for _ in 0..width {
                let atom = wire_word(&mut wire)?;
                let shape = wire_take(&mut wire, 2)?;
                if shape[0] > 1 || !matches!(shape[1], 0 | 1 | 2 | 4 | 255) {
                    return Err("invalid wire role".into());
                }
                let words =
                    usize::try_from(wire_word(&mut wire)?).map_err(|_| "oversized wire role")?;
                let dict = wire_take(
                    &mut wire,
                    words.checked_mul(16).ok_or("wire word overflow")?,
                )?;
                let size = if shape[1] == 255 {
                    0
                } else {
                    count
                        .checked_mul(shape[1] as usize)
                        .ok_or("wire rank overflow")?
                };
                let ids = wire_take(&mut wire, size)?;
                roles.push((atom, shape[0], shape[1], dict, ids));
            }
            for slot in 0..count {
                for ((&ref_atom, fact, lane, dict, ids), r) in roles
                    .iter()
                    .map(|(a, b, c, d, e)| (a, *b, *c, *d, *e))
                    .zip(self.read(slot, width, &mut scratch)?)
                {
                    let rank = if lane == 255 {
                        slot
                    } else {
                        let mut v = [0; 4];
                        let n = lane as usize;
                        v[..n].copy_from_slice(&ids[slot * n..(slot + 1) * n]);
                        u32::from_le_bytes(v) as usize
                    };
                    let mut ins = dict
                        .get(rank * 16..rank * 16 + 16)
                        .ok_or("invalid rank on exported wire")?;
                    let (kind, w) = Word::from_ref(r);
                    if (wire_word(&mut ins)?, wire_word(&mut ins)?, fact, ref_atom)
                        != (w.id, w.version, u8::from(kind), r.atom as u64)
                    {
                        return Err("wrong physical parent on exported wire".into());
                    }
                }
            }
        }
        if !wire.is_empty() {
            return Err("trailing encoded parent wire".into());
        }
        stats.audited_wire_bytes += bytes.len() as u64;
        for b in bytes {
            stats.encoded_wire_hash =
                (stats.encoded_wire_hash ^ u64::from(b)).wrapping_mul(1099511628211);
        }
        Ok(())
    }
}

fn wire_take<'a>(input: &mut &'a [u8], n: usize) -> Result<&'a [u8]> {
    let (a, b) = input.split_at_checked(n).ok_or("truncated parent wire")?;
    *input = b;
    Ok(a)
}
fn wire_word(input: &mut &[u8]) -> Result<u64> {
    Ok(u64::from_le_bytes(wire_take(input, 8)?.try_into().unwrap()))
}

#[cfg(test)]
mod factor_coordinate_tests {
    use super::*;

    #[test]
    fn encoded_coordinates_and_versions() {
        for (count, lane) in [(1, 0), (256, 1), (257, 2), (65536, 2), (65537, 4)] {
            let mut b = FactorBuilder::new(2, 2, true);
            for i in 0..count {
                b.append(
                    [
                        Ref {
                            atom: 2,
                            row: Dependency::Function(1),
                            version: 8,
                        },
                        Ref {
                            atom: 7,
                            row: Dependency::Function(i / 2),
                            version: (i % 2) as u64,
                        },
                    ]
                    .into_iter(),
                )
                .unwrap();
            }
            let mut stats = FactorStats::default();
            let p = b.finish(false, &mut stats).unwrap();
            assert_eq!((p.roles[0].bytes, p.roles[1].bytes), (0, lane));
            assert_eq!(
                p.entry(1, count - 1).unwrap().version,
                ((count - 1) % 2) as u64
            );
            assert!(p.entry(1, count).is_none());
            let storage = FactorStore::Packed(Box::new(p));
            storage
                .audit_wire([0x31475046, 1, 1, 5, 1, count as u64, 2, 0, 1], &mut stats)
                .unwrap();
            assert_eq!(storage.wire_bytes(), stats.audited_wire_bytes as usize);
        }
    }
}
