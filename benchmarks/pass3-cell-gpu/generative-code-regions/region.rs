// A region transmits a prefix predicate, an aligned root interval and a bounded
// rank window in each matching public right posting. No prototype list is sent.
const REGION_ROOTS: usize = 256;
const REGION_PAIRS: usize = 4096;
const REGION_MAGIC: u64 = 0x524547494f4e0000;
const REGION_BYTES: usize = 128;

#[derive(Default, Serialize)]
struct RegionWork {
    mode: u8,
    weights: [f64; 3],
    corrupt: bool,
    evaluated_prefixes: u64,
    empty_prefixes: u64,
    model_calls: u64,
    chosen_splits: u64,
    coarse_leaves: u64,
    fine_leaves: u64,
    physical_windows: u64,
    digest_keys_sender: u64,
    digest_keys_receiver: u64,
    receiver_key_reads: u64,
    receiver_indexed_epochs: u64,
    max_keys: u64,
    max_pairs: u64,
}

fn region_prefix(code: u64, depth: u8) -> u64 {
    // Hash the entire frozen key (also its scalar component on compound routes),
    // then read fixed low bits. Exact equality always uses the untouched full key.
    mix(code) & ((1u64 << depth) - 1)
}
fn region_commit(keys: impl Iterator<Item = u64>) -> [u8; 32] {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    for k in keys {
        h.update(k.to_le_bytes());
    }
    h.finalize().into()
}
#[derive(Clone, Copy)]
struct KeyMass {
    code: u64,
    left: usize,
    right: usize,
}
impl Store {
    fn emit_region_leaf(
        &mut self,
        c: &Context,
        steps: &[StackStep],
        compound: bool,
        lo: usize,
        hi: usize,
        depth: u8,
        prefix: u64,
        keys: &[KeyMass],
        out: &mut Vec<Vec<u8>>,
    ) {
        if keys.is_empty() {
            self.family.region.empty_prefixes += 1;
            return;
        }
        let rows: usize = keys.iter().map(|k| k.left).sum();
        let max_right = keys.iter().map(|k| k.right).max().unwrap();
        let volume: usize = keys.iter().map(|k| k.left * k.right).sum();
        let window = if volume <= REGION_PAIRS {
            max_right.min(REGION_PAIRS)
        } else {
            REGION_PAIRS / rows
        };
        assert!(rows <= REGION_ROOTS && window > 0);
        let mut active = Vec::new();
        for off in (0..max_right).step_by(window) {
            active.clear();
            let mut extent = 0;
            for k in keys.iter().filter(|k| k.right > off) {
                extent += k.left * (k.right - off).min(window);
                active.push(k.code);
            }
            assert!(extent > 0 && extent <= REGION_PAIRS);
            let digest = region_commit(active.iter().copied());
            let prefix_word =
                REGION_MAGIC | (u64::from(compound) << 8) | (u64::from(depth) << 4) | prefix;
            let mut wire = Vec::with_capacity(REGION_BYTES);
            for word in [
                prefix_word,
                c.graph.epoch,
                self.rule as u64,
                steps[0].frame.generation,
                steps[1].frame.generation,
                c.graph.stats.unions,
                lo as u64,
                hi as u64,
                off as u64,
                window as u64,
                (extent + usize::from(self.family.fault)) as u64,
                active.len() as u64,
            ] {
                wire.extend(word.to_le_bytes());
            }
            wire.extend(digest);
            self.family.region.digest_keys_sender += active.len() as u64;
            self.family.region.max_keys = self.family.region.max_keys.max(active.len() as u64);
            self.family.region.max_pairs = self.family.region.max_pairs.max(extent as u64);
            self.family.region.physical_windows += 1;
            self.family.metrics.actions += 1;
            self.family.metrics.keys_issued += active.len() as u64;
            self.family.metrics.candidate_bound += extent as u64;
            self.family.metrics.wire_bytes += wire.len() as u64;
            if compound {
                self.family.compound_work.compound_packets += 1;
                self.family.compound_work.compound_keys += active.len() as u64;
                self.family.compound_work.compound_bytes += wire.len() as u64;
            }
            out.push(wire);
        }
    }
    fn issue_regions(
        &mut self,
        c: &Context,
        steps: &[StackStep],
        left: &[Port],
        right: &CodeStats,
        second: Option<&[u32]>,
        cut: u64,
    ) -> Vec<Vec<u8>> {
        let mut out = Vec::new();
        for (block, chunk) in left.chunks(REGION_ROOTS).enumerate() {
            let lo = block * REGION_ROOTS;
            let hi = lo + chunk.len();
            self.family.metrics.inspected_left += chunk.len() as u64;
            self.family.metrics.spans += 1;
            let mut left_hist = BTreeMap::<u64, (usize, u64)>::new();
            for (i, l) in chunk.iter().enumerate() {
                let code = paired_code(signature(*l, true, self.views), second.map(|s| s[lo + i]));
                let e = left_hist.entry(code).or_default();
                e.0 += 1;
                e.1 = e.1.max(steps[0].frame.rows[lo + i].epoch);
            }
            let mut bins: [Vec<KeyMass>; 2] = Default::default();
            for (code, (nl, el)) in left_hist {
                self.family.metrics.prototypes += 1;
                let Some(&(nr, er)) = right.get(&code) else {
                    self.family.metrics.absent += 1;
                    continue;
                };
                if el.max(er) < cut {
                    self.family.metrics.stale += 1;
                    continue;
                }
                bins[region_prefix(code, 1) as usize].push(KeyMass {
                    code,
                    left: nl,
                    right: nr,
                });
            }
            for (prefix, keys) in bins.iter().enumerate() {
                self.family.region.evaluated_prefixes += 1;
                if keys.is_empty() {
                    self.family.region.empty_prefixes += 1;
                    continue;
                }
                let volume: usize = keys.iter().map(|x| x.left * x.right).sum();
                self.family.metrics.matched_min_packets += volume.div_ceil(REGION_PAIRS) as u64;
                // Frozen three-coefficient head reuses the donor-trained bucket features,
                // now evaluated on this typed region's prospective marginal volume.
                let mut split = false;
                if self.family.region.mode == 2 && keys.len() > 1 {
                    self.family.region.model_calls += 1;
                    let w = self.family.region.weights;
                    let z = w[0]
                        + w[1] * (volume as f64).ln()
                        + w[2] * (steps[1].frame.rows.len() as f64).ln_1p() / 8.;
                    split = z < 0.;
                }
                if split {
                    self.family.region.chosen_splits += 1;
                    for child in [prefix as u64, prefix as u64 + 2] {
                        self.family.region.evaluated_prefixes += 1;
                        let sub: Vec<_> = keys
                            .iter()
                            .copied()
                            .filter(|k| region_prefix(k.code, 2) == child)
                            .collect();
                        self.family.region.fine_leaves += u64::from(!sub.is_empty());
                        self.emit_region_leaf(
                            c,
                            steps,
                            second.is_some(),
                            lo,
                            hi,
                            2,
                            child,
                            &sub,
                            &mut out,
                        );
                    }
                } else {
                    self.family.region.coarse_leaves += 1;
                    self.emit_region_leaf(
                        c,
                        steps,
                        second.is_some(),
                        lo,
                        hi,
                        1,
                        prefix as u64,
                        keys,
                        &mut out,
                    );
                }
            }
        }
        out
    }
}
fn decode_region(
    wire: &[u8],
    id: u64,
    compound: bool,
    epoch: u64,
    rid: usize,
    lg: u64,
    rg: u64,
    union: u64,
    cut: u64,
    lp: &SourceProjection,
    rp: &SourceProjection,
    stats: &mut RegionWork,
) -> Result<Packet> {
    if wire.len() != REGION_BYTES {
        return Err("invalid region length".into());
    }
    let w = |i: usize| u64::from_le_bytes(wire[i * 8..i * 8 + 8].try_into().unwrap());
    let d = ((w(0) >> 4) & 15) as u8;
    let p = w(0) & 15;
    if !(1..=2).contains(&d)
        || p >= (1 << d)
        || w(0) != (REGION_MAGIC | (u64::from(compound) << 8) | (u64::from(d) << 4) | p)
        || w(1) != epoch
        || w(2) != rid as u64
        || w(3) != lg
        || w(4) != rg
        || w(5) != union
    {
        return Err("invalid region coordinate".into());
    }
    let lo = w(6) as usize;
    let hi = w(7) as usize;
    let offset = w(8) as usize;
    let limit = w(9) as usize;
    let extent = w(10) as usize;
    if lo >= lp.codes.len()
        || lo % REGION_ROOTS != 0
        || hi != lo.saturating_add(REGION_ROOTS).min(lp.codes.len())
        || limit == 0
        || limit > REGION_PAIRS
        || offset % limit != 0
        || extent == 0
        || extent > REGION_PAIRS
    {
        return Err("invalid region scope".into());
    }
    // Receiver only reads independently generated public code/epoch views.
    let mut heads = BTreeMap::<u64, (usize, u64)>::new();
    for i in lo..hi {
        stats.receiver_key_reads += 1;
        let k = lp.codes[i];
        if region_prefix(k, d) != p {
            continue;
        }
        let e = heads.entry(k).or_default();
        e.0 += 1;
        e.1 = e.1.max(lp.headers[i].1);
    }
    let mut keys = Vec::new();
    let mut observed = 0;
    for (k, (n, left_epoch)) in heads {
        let Some(rows) = rp.postings.get(&k) else {
            continue;
        };
        if rows.len() <= offset || left_epoch.max(rp.region_max_epoch[&k]) < cut {
            continue;
        }
        observed += n * (rows.len() - offset).min(limit);
        keys.push(k);
    }
    stats.digest_keys_receiver += keys.len() as u64;
    if keys.len() != w(11) as usize || region_commit(keys.iter().copied())[..] != wire[96..] {
        return Err("region public learned-key coverage mismatch".into());
    }
    if observed != extent {
        return Err("region public pair extent mismatch".into());
    }
    Ok(Packet {
        epoch,
        rid,
        left_gen: lg,
        right_gen: rg,
        lo,
        hi,
        keys,
        offset,
        limit,
        extent,
        id,
    })
}
