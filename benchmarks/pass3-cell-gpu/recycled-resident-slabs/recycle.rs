#[derive(Default, Serialize)]
struct RecycleCosts {
    grants_into_old_holes: usize,
    published_from_old_holes: usize,
    fresh_header_slots: usize,
    new_pages: usize,
    new_pages_avoided: usize,
    empty_runs: usize,
    all_reused_runs: usize,
    directory_entries_scanned: usize,
    candidate_pages_ranked: usize,
    lanes_inspected: usize,
}

impl NativeCells {
    fn append_page(&mut self, page: Page) -> usize {
        if let Some(key) = self.free.pop() {
            self.pages[key] = Some(page);
            key
        } else {
            self.pages.push(Some(page));
            self.pages.len() - 1
        }
    }

    pub(super) fn start_reused(
        &mut self,
        epoch: u64,
        width: usize,
        count: usize,
        mut cells: impl Iterator<Item = Cell>,
        audit: bool,
    ) -> (usize, usize) {
        assert!(self.current.is_empty());
        self.epoch = epoch;
        self.width = width;
        self.audit = audit;
        self.recycling = true;
        self.reused_prefix = 0;
        self.grant_lanes.clear();
        self.stats.grants += count;
        if count == 0 {
            self.recycle.empty_runs += 1;
            return (0, 0);
        }
        if self.holes > 0 {
            self.recycle.directory_entries_scanned += self.pages.len();
            let mut candidates: Vec<_> = self
                .pages
                .iter()
                .enumerate()
                .filter_map(|(p, page)| {
                    let page = page.as_ref()?;
                    let slots = page.lanes.len();
                    (page.live < slots).then_some((p, page.live, slots))
                })
                .collect();
            // Compare occupancy ratios exactly. At equal density, prefer more available lanes.
            candidates.sort_unstable_by(|a, b| {
                (b.1 * a.2)
                    .cmp(&(a.1 * b.2))
                    .then_with(|| (b.2 - b.1).cmp(&(a.2 - a.1)))
                    .then_with(|| a.0.cmp(&b.0))
            });
            self.recycle.candidate_pages_ranked += candidates.len();
            for (p, _, _) in candidates {
                let page = self.pages[p].as_mut().unwrap();
                assert!(page.closed && page.live > 0);
                // Temporarily remove this page from closed-page accounting, including
                // unclaimed holes. Closing puts back its exact final occupancy once.
                self.holes -= page.lanes.len() - page.live;
                page.closed = false;
                self.current.push(p);
                for (slot, lane) in page.lanes.iter_mut().enumerate() {
                    self.recycle.lanes_inspected += 1;
                    if lane.frame.is_some() {
                        continue;
                    }
                    assert!(lane.id.is_none());
                    *lane = Lane::private(cells.next().expect("recycling grant"));
                    lane.freeze();
                    self.grant_lanes.push((p << 8) | slot);
                    if self.grant_lanes.len() == count {
                        break;
                    }
                }
                if self.grant_lanes.len() == count {
                    break;
                }
            }
        }
        self.reused_prefix = self.grant_lanes.len();
        let fresh = count - self.reused_prefix;
        let allocated_pages = fresh.div_ceil(width);
        self.recycle.grants_into_old_holes += self.reused_prefix;
        self.recycle.new_pages_avoided += count.div_ceil(width) - allocated_pages;
        self.recycle.new_pages += allocated_pages;
        self.recycle.fresh_header_slots += fresh;
        self.recycle.all_reused_runs += usize::from(fresh == 0);

        let mut left = fresh;
        while left > 0 {
            let n = left.min(width);
            let mut lanes: Box<[_]> = cells.by_ref().take(n).map(Lane::private).collect();
            assert_eq!(lanes.len(), n);
            for lane in &mut lanes {
                lane.freeze();
            }
            let p = self.append_page(Page {
                epoch,
                lanes,
                live: 0,
                closed: false,
            });
            self.current.push(p);
            self.grant_lanes.extend((0..n).map(|i| (p << 8) | i));
            self.occupied += n;
            left -= n;
        }
        assert!(cells.next().is_none());
        self.stats.peak_total_slots = self.stats.peak_total_slots.max(self.occupied);
        self.stats.peak_pages = self
            .stats
            .peak_pages
            .max(self.pages.len() - self.free.len());
        (fresh, allocated_pages)
    }
}
