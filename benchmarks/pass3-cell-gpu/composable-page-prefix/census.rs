#[derive(Default, serde::Serialize)]
struct PageDepth {
    failed: u64,
    repeated_failure: u64,
    offered: u64,
    shared: u64,
    read: u64,
    shared_read: u64,
    fields: u64,
    shared_fields: u64,
}
#[derive(Default, serde::Serialize)]
struct PageCensus {
    wire: WireBudget,
    active: bool,
    depth: Vec<PageDepth>,
    lcp: Vec<u64>,
    tuples: u64,
    max_width: usize,
}
fn same_page_ref(a: &crate::joint_root::Ref, b: &crate::joint_root::Ref) -> bool {
    a.atom == b.atom && a.row == b.row && a.version == b.version
}
impl PageCensus {
    fn prefixes(
        &mut self,
        now: &[crate::joint_root::Ref],
        last: &[crate::joint_root::Ref],
    ) -> usize {
        let n = now
            .iter()
            .zip(last)
            .take_while(|(a, b)| same_page_ref(a, b))
            .count();
        while self.depth.len() < now.len() {
            self.depth.push(PageDepth::default());
        }
        if self.lcp.len() <= n {
            self.lcp.resize(n + 1, 0);
        }
        self.lcp[n] += 1;
        self.tuples += 1;
        self.max_width = self.max_width.max(now.len());
        for (i, d) in self.depth.iter_mut().take(now.len()).enumerate() {
            d.offered += 1;
            d.shared += u64::from(i < n);
        }
        n
    }
    fn visited(&mut self, j: usize, n: usize, fields: usize) {
        let d = &mut self.depth[j];
        d.read += 1;
        d.fields += fields as u64;
        if j < n {
            d.shared_read += 1;
            d.shared_fields += fields as u64;
        }
    }
}
pub fn use_page_census() -> Result<()> {
    STORE.with_borrow_mut(|s| {
        s.as_mut()
            .ok_or("prefix census needs a configured multi-parent provider")?
            .compressed_census
            .active = true;
        Ok(())
    })
}

include!("prefix_wire.rs");
