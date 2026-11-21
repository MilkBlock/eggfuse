type FamilyKey = u32;
type CodeStats = HashMap<FamilyKey, (usize, u64)>;
struct SourceProjection {
    generation: u64,
    union: u64,
    headers: Rc<Vec<(Dependency, u64)>>,
    codes: Rc<Vec<FamilyKey>>,
    postings: Rc<HashMap<FamilyKey, Vec<u32>>>,
}
#[derive(Clone)]
struct Packet {
    epoch: u64,
    rid: usize,
    left_gen: u64,
    right_gen: u64,
    lo: usize,
    hi: usize,
    keys: Vec<FamilyKey>,
    offset: usize,
    limit: usize,
    extent: usize,
    id: u64,
}
impl Packet {
    fn wire(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(72 + 4 * self.keys.len());
        for w in [
            self.epoch,
            self.rid as u64,
            self.left_gen,
            self.right_gen,
            self.lo as u64,
            self.hi as u64,
            self.offset as u64,
            self.limit as u64,
            self.extent as u64,
        ] {
            out.extend_from_slice(&w.to_le_bytes());
        }
        for k in &self.keys {
            out.extend_from_slice(&k.to_le_bytes());
        }
        out
    }
    fn read(buf: &[u8], id: u64) -> Result<Self> {
        if buf.len() <= 72 || buf.len() > 104 || (buf.len() - 72) % 4 != 0 {
            return Err("invalid family packet length".into());
        }
        let words: Vec<u64> = buf[..72]
            .chunks_exact(8)
            .map(|p| u64::from_le_bytes(p.try_into().unwrap()))
            .collect();
        let keys = buf[72..]
            .chunks_exact(4)
            .map(|p| u32::from_le_bytes(p.try_into().unwrap()))
            .collect();
        Ok(Self {
            epoch: words[0],
            rid: words[1] as usize,
            left_gen: words[2],
            right_gen: words[3],
            lo: words[4] as usize,
            hi: words[5] as usize,
            offset: words[6] as usize,
            limit: words[7] as usize,
            extent: words[8] as usize,
            id,
            keys,
        })
    }
}
#[derive(Default, Serialize)]
struct FamilyMetrics {
    source_pair_ms: f64,
    issue_ms: f64,
    receiver_ms: f64,
    calls: u64,
    skipped_clean: u64,
    inspected_left: u64,
    prototypes: u64,
    absent: u64,
    stale: u64,
    spans: u64,
    actions: u64,
    keys_issued: u64,
    candidate_bound: u64,
    receiver_pairs: u64,
    private_rows: u64,
    empty_actions: u64,
    sender_marginal_rows: u64,
    receiver_public_decodes: u64,
    receiver_cache_hits: u64,
    wire_bytes: u64,
    upper_min_packets: u64,
    matched_min_packets: u64,
}
#[derive(Default)]
struct Family {
    mode: u8,
    fault: bool,
    trace: bool,
    phase: bool,
    metrics: FamilyMetrics,
    hist: HashMap<(usize, usize), (u64, u64, Rc<CodeStats>)>,
    public: HashMap<(usize, usize), Rc<SourceProjection>>,
    origins: Vec<[u64; 2]>,
    examples: Vec<Vec<u8>>,
    rules: HashMap<usize, [u64; 4]>,
    ready: Option<crate::joint_root::MultiPage>,
}
pub fn configure_family(cfg: &Json) -> Result<()> {
    STORE.with_borrow_mut(|s| {
        let s = s.as_mut().ok_or("missing family model")?;
        let mode = cfg["mode"].as_u64().unwrap_or(0);
        if mode > 2
            || !s.packed_lookup
            || s.radius != 0
            || s.mode != "learned"
            || s.pair_mode != 3
            || !s
                .model
                .q
                .iter()
                .flatten()
                .zip(s.model.k.iter().flatten())
                .all(|(a, b)| a.to_bits() == b.to_bits())
        {
            return Err("frame families need the complete guarded tied-key two-parent model".into());
        }
        s.family.mode = mode as u8;
        s.family.fault = cfg["fault"] == true;
        s.family.trace = cfg["trace"] == true;
        s.family.phase = cfg["phase"] == true;
        Ok(())
    })
}
impl Store {
    fn family_hist(&mut self, step: &StackStep, col: usize, codes: &[Port]) -> Rc<CodeStats> {
        let tag = (step.table, col);
        let f = &step.frame;
        if let Some((g, u, x)) = self.family.hist.get(&tag)
            && (*g, *u) == (f.generation, f.born_at_union)
        {
            return x.clone();
        }
        let mut m = CodeStats::new();
        for (r, p) in f.rows.iter().zip(codes) {
            let entry = m.entry(signature(*p, false, self.views)).or_default();
            entry.0 += 1;
            entry.1 = entry.1.max(r.epoch);
        }
        self.family.metrics.sender_marginal_rows += f.rows.len() as u64;
        let m = Rc::new(m);
        self.family
            .hist
            .insert(tag, (f.generation, f.born_at_union, m.clone()));
        m
    }
    fn family_public(
        &mut self,
        g: &Graph,
        step: &StackStep,
        col: usize,
    ) -> Result<Rc<SourceProjection>> {
        let key = (step.table, col);
        let f = &step.frame;
        if let Some(x) = self.family.public.get(&key)
            && x.generation == f.generation
            && x.union == g.stats.unions
        {
            self.family.metrics.receiver_cache_hits += 1;
            return Ok(x.clone());
        }
        let mut rows = Vec::new();
        let mut codes = Vec::new();
        let mut bins: HashMap<FamilyKey, Vec<u32>> = HashMap::new();
        for w in g.witnesses(step.table) {
            if let Some(r) = g.row(w)?.filter(|r| r.table == step.table && !r.hidden) {
                let i = u32::try_from(rows.len()).map_err(|e| e.to_string())?;
                let code = signature(self.code(&r.values[col]), false, self.views);
                // Projection ordering must agree with the canonical public iterator used by this executable.
                if !f
                    .rows
                    .get(i as usize)
                    .is_some_and(|s| s.witness == w && s.epoch == r.epoch)
                {
                    return Err("public source frontier mismatch".into());
                }
                rows.push((w, r.epoch));
                codes.push(code);
                bins.entry(code).or_default().push(i);
            }
        }
        if rows.len() != f.rows.len() {
            return Err("public source size mismatch".into());
        }
        self.family.metrics.receiver_public_decodes += rows.len() as u64;
        let p = Rc::new(SourceProjection {
            generation: f.generation,
            union: g.stats.unions,
            headers: Rc::new(rows),
            codes: Rc::new(codes),
            postings: Rc::new(bins),
        });
        self.family.public.insert(key, p.clone());
        Ok(p)
    }
    fn issue_families(
        &mut self,
        c: &Context,
        steps: &[StackStep],
        left: &[Port],
        right: &CodeStats,
        cut: u64,
    ) -> Vec<Vec<u8>> {
        let mut packets = Vec::new();
        let (span, key_cap, limit) = if self.family.mode == 1 {
            (8usize, 2usize, 64usize)
        } else {
            (32, 8, 256)
        };
        let stat = &mut self.family.metrics;
        for (block, ls) in left.chunks(span).enumerate() {
            stat.spans += 1;
            stat.inspected_left += ls.len() as u64;
            let lo = span * block;
            let hi = lo + ls.len();
            let mut heads = BTreeMap::<FamilyKey, (usize, u64)>::new();
            for (i, l) in ls.iter().enumerate() {
                let e = heads.entry(signature(*l, true, self.views)).or_default();
                e.0 += 1;
                e.1 = e.1.max(steps[0].frame.rows[lo + i].epoch);
            }
            let mut keys = Vec::new();
            let mut extent = 0;
            let mut active_codes = 0usize;
            let mut volume_bound = 0usize;
            let mut push = |keys: Vec<u32>, off: usize, window: usize, extent: usize| {
                stat.actions += 1;
                stat.keys_issued += keys.len() as u64;
                stat.candidate_bound += extent as u64;
                // Actual compact payload carries nine u64 header words followed by its u32 learned prototypes.
                stat.wire_bytes += (72 + keys.len() * 4) as u64;
                packets.push(
                    Packet {
                        epoch: c.graph.epoch,
                        rid: self.rule,
                        left_gen: steps[0].frame.generation,
                        right_gen: steps[1].frame.generation,
                        lo,
                        hi,
                        keys,
                        offset: off,
                        limit: window,
                        extent: extent + usize::from(self.family.fault),
                        id: stat.actions,
                    }
                    .wire(),
                );
            };
            for (code, (lcount, lmax)) in heads {
                stat.prototypes += 1;
                let Some(&(rn, rmax)) = right.get(&code) else {
                    stat.absent += 1;
                    continue;
                };
                if lmax.max(rmax) < cut {
                    stat.stale += 1;
                    continue;
                }
                let volume = lcount * rn;
                active_codes += 1;
                volume_bound += volume;
                if extent > 0 && (extent + volume > limit || keys.len() == key_cap) {
                    push(std::mem::take(&mut keys), 0, limit, extent);
                    extent = 0;
                }
                if volume > limit {
                    let chunk = limit / lcount;
                    for start in (0..rn).step_by(chunk) {
                        let n = (rn - start).min(chunk);
                        push(vec![code], start, n, n * lcount);
                    }
                } else {
                    keys.push(code);
                    extent += volume;
                }
            }
            if extent > 0 {
                push(keys, 0, limit, extent);
            }
            stat.matched_min_packets += active_codes
                .div_ceil(key_cap)
                .max(volume_bound.div_ceil(limit)) as u64;
        }
        packets
    }
    fn family_two(&mut self, c: &Context, steps: &[StackStep]) -> Result<()> {
        let issue_clock = self.family.phase.then(std::time::Instant::now);
        self.family.metrics.calls += 1;
        let (left, right) = (&steps[0], &steps[1]);
        let (rc, slot) = right.shared[0];
        let lc = left
            .publish
            .iter()
            .find(|(_, s)| *s == slot)
            .ok_or("missing shared root slot")?
            .0;
        let mark = if c.rule.seminaive { c.watermark } else { 0 };
        let cut = if c.remaining[2] < mark { mark } else { 0 };
        if left.frame.max_epoch.max(right.frame.max_epoch) < cut {
            self.family.metrics.skipped_clean += 1;
            return Ok(());
        }
        let rp = self.projected_column(right, rc);
        let lp = self.projected_column(left, lc);
        let hist = self.family_hist(right, rc, &rp);
        let first_action = self.family.metrics.actions + 1;
        let before = self.family.metrics.candidate_bound;
        let packets = self.issue_families(c, steps, &lp, &hist, cut);
        let rule = self.family.rules.entry(self.rule).or_default();
        rule[0] += 1;
        rule[1] += packets.len() as u64;
        rule[2] += self.family.metrics.candidate_bound - before;
        if let Some(t) = issue_clock {
            self.family.metrics.issue_ms += t.elapsed().as_secs_f64() * 1000.;
        }
        if packets.is_empty() {
            return Ok(());
        }
        let receiver_clock = self.family.phase.then(std::time::Instant::now);
        let lp = self.family_public(c.graph, left, lc)?;
        let rp = self.family_public(c.graph, right, rc)?;
        let guards = if mark > 0 {
            self.age_guards(c, steps)?
        } else {
            (vec![], vec![])
        };
        let eq = self.equations.plans.get(self.rule).and_then(|e| e.clone());
        let mut other = vec![];
        for &(rcol, s) in right.shared.iter().skip(1) {
            let lcol = left
                .publish
                .iter()
                .find(|(_, k)| *k == s)
                .ok_or("missing second pair column")?
                .0;
            other.push((
                self.projected_column(left, lcol),
                self.projected_column(right, rcol),
            ));
        }
        let (max_roots, max_keys, max_pairs) = if self.family.mode == 1 {
            (8, 2, 64)
        } else {
            (32, 8, 256)
        };
        let mut winners: Vec<(u32, u32, u64)> = vec![];
        let mut left_eq = HashMap::new();
        for (offset, wire) in packets.into_iter().enumerate() {
            let p = Packet::read(&wire, first_action + offset as u64)?;
            if p.epoch != c.graph.epoch
                || p.rid != self.rule
                || p.left_gen != c.graph.query_versions[left.table]
                || p.right_gen != c.graph.query_versions[right.table]
                || p.hi <= p.lo
                || p.hi > lp.codes.len()
                || p.hi - p.lo > max_roots
                || p.keys.is_empty()
                || p.keys.len() > max_keys
                || p.extent > max_pairs
                || p.limit == 0
                || p.limit > max_pairs
                || p.keys.windows(2).any(|x| x[0] >= x[1])
            {
                return Err("invalid family scope or bounds".into());
            }
            if self.family.trace && self.family.examples.len() < 4 {
                self.family.examples.push(wire.clone());
            }
            let start = winners.len();
            let mut visited = 0;
            for l in p.lo..p.hi {
                let code = lp.codes[l];
                if p.keys.binary_search(&code).is_err() {
                    continue;
                }
                let posting = rp
                    .postings
                    .get(&code)
                    .ok_or("unoccupied family prototype")?;
                if p.offset >= posting.len() {
                    return Err("family posting offset exceeds extent".into());
                }
                let end = p
                    .offset
                    .checked_add(p.limit)
                    .ok_or("family posting bound overflow")?
                    .min(posting.len());
                let row = &left.frame.rows[l];
                // Evaluate all pre-existing guards without allowing any guard to supply parent identities.
                let prefix_ok = row.epoch.max(right.frame.max_epoch) >= cut
                    && (mark == 0
                        || row.epoch >= mark
                        || could_have_delta(&guards.0, l, None, mark)
                        || could_have_delta(&guards.1, l, None, mark))
                    && (self.atoms.mode == 0 || self.local_codes_permit(0, l, row));
                for &r in &posting[p.offset..end] {
                    visited += 1;
                    if visited > max_pairs {
                        return Err("family expansion exceeds public bound".into());
                    }
                    if !prefix_ok {
                        continue;
                    }
                    let j = r as usize;
                    let row2 = &right.frame.rows[j];
                    let epoch = row.epoch.max(row2.epoch);
                    if epoch < cut
                        || (mark > 0
                            && epoch < mark
                            && !could_have_delta(&guards.1, l, Some(j), mark))
                        || (self.atoms.mode > 0 && !self.local_codes_permit(1, j, row2))
                        || !other.iter().all(|(ls, rs)| self.compatible(ls[l], rs[j]))
                    {
                        continue;
                    }
                    if let Some(eq) = &eq {
                        let a = *left_eq
                            .entry(l)
                            .or_insert_with(|| self.lazy_equation_value(c, eq, 0, row));
                        let b = self.lazy_equation_value(c, eq, 1, row2);
                        if matches!((a,b),(Some(x),Some(y)) if x==u32::MAX || x!=y) {
                            continue;
                        }
                    }
                    winners.push((l as u32, r, p.id));
                }
            }
            if visited != p.extent {
                return Err("regenerated family extent differs".into());
            }
            self.family.metrics.receiver_pairs += visited as u64;
            self.family.metrics.empty_actions += u64::from(winners.len() == start);
        }
        winners.sort_unstable_by_key(|&(l, r, _)| (l, r));
        if winners
            .windows(2)
            .any(|w| w[0].0 == w[1].0 && w[0].1 == w[1].1)
        {
            return Err("duplicate generated family pair".into());
        }
        let n = winners.len();
        self.family.rules.get_mut(&self.rule).unwrap()[3] += n as u64;
        self.family.metrics.private_rows += n as u64;
        self.family.metrics.upper_min_packets += n.div_ceil(max_pairs) as u64;
        self.counts.raw_tuples += n as u64;
        self.counts.raw_root_slots += 2 * n as u64;
        if n == 0 {
            if let Some(t) = receiver_clock {
                self.family.metrics.receiver_ms += t.elapsed().as_secs_f64() * 1000.;
            }
            return Ok(());
        }
        let pairs = winners.iter().map(|&(l, r, _)| [l, r]).collect();
        let page = crate::joint_root::family_page(
            c.graph.epoch,
            self.rule,
            [left.atom, right.atom],
            [lp.headers.clone(), rp.headers.clone()],
            pairs,
        )?;
        if self.family.trace {
            for (i, &(_, _, action)) in winners.iter().enumerate() {
                self.family
                    .origins
                    .push([page.stage_serial() + i as u64, action]);
            }
        }
        self.family.ready = Some(page);
        if let Some(t) = receiver_clock {
            self.family.metrics.receiver_ms += t.elapsed().as_secs_f64() * 1000.;
        }
        Ok(())
    }
}
