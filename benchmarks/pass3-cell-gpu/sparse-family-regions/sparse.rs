type Region = (FamilyKey, usize, usize);
type SourceRoles = (usize, usize, usize, usize);
#[derive(Clone, Copy)]
struct Occurrence {
    epoch: u64,
    span: u32,
    rows: u32,
}
struct Directory {
    version: (u64, u64),
    entries: usize,
    posts: HashMap<FamilyKey, Vec<Occurrence>>,
    payload: usize,
}
#[derive(Default, Serialize)]
struct RegionCounts {
    left_rows: u64,
    left_builds: u64,
    left_reuses: u64,
    resident_payload: usize,
    peak_payload: usize,
    cache_refusals: u64,
    directory_records: u64,
    construction_key_updates: u64,
    keys_probed: u64,
    keys_absent: u64,
    epoch_checks: u64,
    no_fresh_region: u64,
    binary_steps: u64,
    materialized_regions: u64,
    skipped_missing_regions: u64,
    skipped_stale_regions: u64,
    model_port_requests: u64,
    model_table_lookups: u64,
    model_online_encodes: u64,
    lists_sorted: u64,
    posting_sorts: u64,
    packet_hash: String,
}
#[derive(Default)]
struct SparseRegions {
    enabled: bool,
    sending: bool,
    cache: HashMap<SourceRoles, Rc<Directory>>,
    counts: RegionCounts,
    digest: Sha256,
}
impl SparseRegions {
    // Native query-side state only. An entry has a span cardinality, not row addresses.
    fn directory(
        &mut self,
        role: SourceRoles,
        version: (u64, u64),
        left: &[Port],
        second: Option<&[u32]>,
        step: &StackStep,
        views: usize,
    ) -> Rc<Directory> {
        if let Some(d) = self.cache.get(&role)
            && d.version == version
        {
            self.counts.left_reuses += 1;
            return d.clone();
        }
        let span = role.3;
        let mut posts: HashMap<FamilyKey, Vec<Occurrence>> = HashMap::new();
        let mut records = 0usize;
        for (i, l) in left.iter().enumerate() {
            let block = (i / span) as u32;
            let epoch = step.frame.rows[i].epoch;
            let key = paired_code(signature(*l, true, views), second.map(|v| v[i]));
            let xs = posts.entry(key).or_default();
            if let Some(x) = xs.last_mut()
                && x.span == block
            {
                x.epoch = x.epoch.max(epoch);
                x.rows += 1;
            } else {
                xs.push(Occurrence {
                    epoch,
                    span: block,
                    rows: 1,
                });
                records += 1;
            }
        }
        let mut payload = posts.capacity() * std::mem::size_of::<(FamilyKey, Vec<Occurrence>)>();
        for xs in posts.values_mut() {
            if xs.len() > 1 {
                xs.sort_unstable_by_key(|e| (e.epoch, e.span));
                self.counts.posting_sorts += 1;
            }
            payload += xs.capacity() * std::mem::size_of::<Occurrence>();
        }
        self.counts.left_rows += left.len() as u64;
        self.counts.construction_key_updates += left.len() as u64;
        self.counts.left_builds += 1;
        self.counts.directory_records += records as u64;
        let d = Rc::new(Directory {
            posts,
            version,
            entries: records,
            payload,
        });
        if let Some(old) = self.cache.remove(&role) {
            self.counts.resident_payload -= old.payload;
        }
        if payload <= 8 << 20 {
            if self.counts.resident_payload + payload > 8 << 20 || self.cache.len() >= 1024 {
                self.cache.clear();
                self.counts.resident_payload = 0;
            }
            self.counts.resident_payload += payload;
            self.counts.peak_payload = self.counts.peak_payload.max(self.counts.resident_payload);
            self.cache.insert(role, d.clone());
        } else {
            self.counts.cache_refusals += 1;
        }
        d
    }
    fn gather(
        &mut self,
        d: &Directory,
        right: &CodeStats,
        cut: u64,
        spans: usize,
    ) -> (Vec<Vec<Region>>, u64, u64) {
        let c = &mut self.counts;
        let mut active = vec![vec![]; spans];
        let mut matched = 0usize;
        let mut age_skipped = 0usize;
        // Probe the smaller marginal dictionary. A failed probe accounts for an
        // entire source prototype; the opposite map is already complete for this generation.
        let mut resolve =
            |key: FamilyKey, ls: Option<&Vec<Occurrence>>, rs: Option<&(usize, u64)>| {
                c.keys_probed += 1;
                let (Some(ls), Some(&(rn, re))) = (ls, rs) else {
                    c.keys_absent += 1;
                    return;
                };
                matched += ls.len();
                c.epoch_checks += 1;
                let first = if re >= cut {
                    0
                } else {
                    ls.partition_point(|x| {
                        c.binary_steps += 1;
                        x.epoch < cut
                    })
                };
                if first == ls.len() {
                    c.no_fresh_region += 1;
                }
                age_skipped += first;
                for e in &ls[first..] {
                    active[e.span as usize].push((key, e.rows as usize, rn));
                }
                c.materialized_regions += (ls.len() - first) as u64;
            };
        if right.len() < d.posts.len() {
            for (&key, r) in right {
                resolve(key, d.posts.get(&key), Some(r));
            }
        } else {
            for (&key, l) in &d.posts {
                resolve(key, Some(l), right.get(&key));
            }
        }
        for xs in &mut active {
            if xs.len() > 1 {
                xs.sort_unstable_by_key(|a| a.0);
                c.lists_sorted += 1;
            }
        }
        let absent = (d.entries - matched) as u64;
        c.skipped_missing_regions += absent;
        c.skipped_stale_regions += age_skipped as u64;
        (active, absent, age_skipped as u64)
    }
}
