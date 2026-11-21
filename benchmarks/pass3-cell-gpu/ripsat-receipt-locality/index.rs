#[derive(Default, Serialize)]
struct ReceiptScanCounts {
    release_calls: u64,
    possible: u64,
    visited: u64,
    excluded_by_version: u64,
    member_checks: u64,
    row_reads: u64,
    stamped: u64,
    posting_reads: u64,
    sort_items: u64,
    receiver_ns: u64,
    index_ns: u64,
    profile: bool,
}
#[derive(Default)]
struct ReceiptIndex {
    mode: u8,
    by_version: BTreeMap<usize, BTreeMap<u64, Vec<Dependency>>>,
    work: ReceiptScanCounts,
}
impl ReceiptIndex {
    fn parse(spec: &J) -> Result<Self> {
        let value = spec["receipt_scan"].as_u64().unwrap_or(0);
        if value > 2 || value != 0 && spec["partial"] != true {
            return Err("version index requires partial named receipts".into());
        }
        let mut index = Self::default();
        index.mode = value as u8;
        index.work.profile = spec["receipt_profile"] == true;
        Ok(index)
    }
    fn add(&mut self, rid: usize, w: Dependency, epoch: u64) {
        if self.mode != 2 {
            return;
        }
        let start = self.work.profile.then(std::time::Instant::now);
        self.by_version
            .entry(rid)
            .or_default()
            .entry(epoch)
            .or_default()
            .push(w);
        self.work.stamped += 1;
        if let Some(t) = start {
            self.work.index_ns += t.elapsed().as_nanos() as u64;
        }
    }
    fn fresh(&mut self, rid: usize, wm: u64) -> Vec<Dependency> {
        let mut addresses = Vec::new();
        if let Some(bins) = self.by_version.get(&rid) {
            for (_, ids) in bins.range(wm..) {
                self.work.posting_reads += 1;
                addresses.extend_from_slice(ids);
            }
        }
        if addresses.len() > 1 {
            addresses.sort_unstable();
            self.work.sort_items += addresses.len() as u64;
        }
        addresses
    }
}
