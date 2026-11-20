// Search may read the frontier of a source relation without using any of its values.
#[derive(Default, Serialize)]
struct WatermarkStats {
    requests: u64,
    current_frames: u64,
    header_reads: u64,
    scalar_hits: u64,
    scalar_scans: u64,
    inspected_addresses: u64,
    audited: u64,
    stale_rules: u64,
    threshold_skips: u64,
    reused_proofs: u64,
    cross_generation_proofs: u64,
    expired_witnesses: u64,
    inspections: u64,
    membership_lists: u64,
}

#[derive(Default)]
struct Watermarks {
    mode: u8,
    stats: WatermarkStats,
    // Cleared with the Store at the start of each source execution.
    receipts: Vec<Option<EpochReceipt>>,
    maxima: Vec<Option<(u64, u64)>>,
}

pub fn configure_watermarks(mode: u64) -> Result<()> {
    if mode > 7 {
        return Err("unknown source frontier policy".into());
    }
    STORE.with_borrow_mut(|cell| {
        cell.as_mut().ok_or("missing parent issuer")?.watermarks.mode = mode as u8;
        Ok(())
    })
}

impl Store {
    fn source_max(&mut self, g: &Graph, table: usize) -> Result<u64> {
        let version = g.query_versions[table];
        let w = &mut self.watermarks;
        w.stats.requests += 1;
        if let Some(frame) = self.frames.get(&table).filter(|f| f.generation == version) {
            w.stats.current_frames += 1;
            return Ok(frame.max_epoch);
        }
        let epoch = if matches!(w.mode, 1 | 2 | 5) {
            w.stats.header_reads += 1;
            g.header_bank(table).max
        } else if let Some((generation, epoch)) = w.maxima.get(table).copied().flatten()
            && generation == version
        {
            w.stats.scalar_hits += 1;
            epoch
        } else {
            w.stats.scalar_scans += 1;
            let rows = g.witnesses(table);
            w.stats.inspected_addresses += rows.len() as u64;
            let epoch = rows.into_iter().filter_map(|r| g.visible_epoch(r)).max().unwrap_or(0);
            if w.maxima.len() <= table {
                w.maxima.resize(table + 1, None);
            }
            w.maxima[table] = Some((version, epoch));
            epoch
        };
        if self.detailed {
            // Use the original typed, visible source row, independent of the header path.
            let mut expected = 0;
            for address in g.witnesses(table) {
                if let Some(r) = g.row(address)? && !r.hidden {
                    expected = expected.max(r.epoch);
                }
            }
            if epoch != expected {
                return Err(format!("incorrect table frontier for {table}: {epoch} vs {expected}"));
            }
            w.stats.audited += 1;
        }
        Ok(epoch)
    }
}

#[derive(Clone, Copy)]
struct EpochReceipt {
    generation: u64,
    epoch: u64,
    witness: Option<Dependency>,
    complete: bool,
}

impl Store {
    // Every remaining[] read in the frozen issuer is a comparison with this
    // watermark, including the seminaive suffix check in the exact verifier.
    fn threshold_epoch(&mut self, g: &Graph, t: usize, mark: u64) -> Result<u64> {
        self.watermarks.stats.requests += 1;
        let generation = g.query_versions[t];
        if let Some(f) = self.frames.get(&t).filter(|f| f.generation == generation) {
            self.watermarks.stats.current_frames += 1;
            return Ok(f.max_epoch.min(mark));
        }
        let w = &mut self.watermarks;
        if w.receipts.len() <= t {
            w.receipts.resize(t + 1, None);
        }
        let mut proof = None;
        if let Some(r) = w.receipts[t] {
            if r.generation == generation && (r.complete || r.epoch >= mark) {
                w.stats.reused_proofs += 1;
                proof = Some(r);
            } else if r.generation != generation && w.mode == 7 && let Some(dep) = r.witness {
                if let Some(epoch) = g.current_member_epoch(t, dep).filter(|e| *e >= mark) {
                    w.stats.cross_generation_proofs += 1;
                    proof = Some(EpochReceipt { generation, epoch, witness: Some(dep), complete: false });
                } else {
                    w.stats.expired_witnesses += 1;
                }
            }
        }
        let r = proof.unwrap_or_else(|| {
            let mut r = EpochReceipt { generation, epoch: 0, witness: None, complete: true };
            let rows = g.witnesses(t);
            w.stats.membership_lists += rows.len() as u64;
            for dep in rows.into_iter().rev() {
                w.stats.inspections += 1;
                if let Some(e) = g.visible_epoch(dep) && e > r.epoch {
                    r.epoch = e;
                    r.witness = Some(dep);
                    if e >= mark {
                        r.complete = false;
                        break;
                    }
                }
            }
            r
        });
        w.receipts[t] = Some(r);
        if self.detailed {
            let mut max = 0;
            for dep in g.witnesses(t) {
                if let Some(row) = g.row(dep)? && !row.hidden {
                    max = max.max(row.epoch);
                }
            }
            if (max >= mark) != (r.epoch >= mark) {
                return Err(format!("invalid freshness proof at table {t}, watermark {mark}"));
            }
            w.stats.audited += 1;
        }
        Ok(r.epoch.min(mark))
    }
}
