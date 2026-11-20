// Stored frontier contains only relationships proved by the two typed leaf plans.
#[derive(Default)]
struct Cover {
    stamp: Option<(u64, u64)>,
    residual: Vec<(usize, Dependency)>,
    by_epoch: [BTreeMap<u64, Vec<(usize, Child)>>; 3],
    visible: usize,
    owners: usize,
}
pub struct Boundary {
    pub entries: std::vec::IntoIter<(usize, Dependency, Option<Child>)>,
    pub total: usize,
    pub omitted_fresh: usize,
}
pub fn boundary(g: &Graph, rid: usize, wm: u64) -> Option<Boundary> {
    STATE.with_borrow_mut(|state| {
        let s = state.as_mut()?;
        if s.composed == 0
            || g.witness_count(s.table) >= (1 << 24)
            || s.mode != Mode::Baked
            || (rid != s.family.eq && rid != s.family.gt)
        {
            return None;
        }
        if s.composed == 4 {
            return incremental_boundary(s, g, rid, wm);
        }
        let stamp = (g.query_versions[s.table], s.tx.completed);
        if s.cover.stamp != Some(stamp) {
            let cover = &mut s.cover;
            cover.residual.clear();
            for b in &mut cover.by_epoch {
                b.clear();
            }
            cover.visible = 0;
            cover.owners = 0;
            for w in g.witnesses(s.table) {
                s.frontier_stats[1] += 1;
                let Some(epoch) = g.visible_epoch(w) else {
                    continue;
                };
                let idx = cover.visible;
                cover.visible += 1;
                if let Some(c) = s
                    .pending
                    .get(&w)
                    .filter(|c| c.version == epoch && c.macro_accepted)
                {
                    if s.profile {
                        s.charges[c.generation as usize - 1].counts[3] += 1;
                    }
                    cover.by_epoch[c.branch as usize]
                        .entry(epoch)
                        .or_default()
                        .push((idx, *c));
                    cover.owners += 1;
                } else {
                    cover.residual.push((idx, w));
                }
            }
            cover.stamp = Some(stamp);
            s.frontier_stats[0] += 1;
        }
        let c = &s.cover;
        let branch = if rid == s.family.gt { 2 } else { 1 };
        let mut rows: Vec<_> = c.residual.iter().map(|&(idx, w)| (idx, w, None)).collect();
        let mut fresh = 0;
        for (arm, epochs) in c.by_epoch.iter().enumerate() {
            for group in epochs.range(wm..).map(|(_, group)| group) {
                fresh += group.len();
                if arm == branch {
                    rows.extend(group.iter().map(|(idx, c)| (*idx, c.source, Some(*c))));
                }
            }
        }
        if s.profile {
            for (arm, epochs) in c.by_epoch.iter().enumerate() {
                for (epoch, items) in epochs {
                    for (_, item) in items {
                        let v = &mut s.charges[item.generation as usize - 1];
                        v.counts[0] += 1;
                        v.counts[1] += u64::from(*epoch >= wm && arm == branch);
                    }
                }
            }
        }
        rows.sort_unstable_by_key(|row| row.0);
        let selected = rows.len() - c.residual.len();
        s.counts[5] += selected as u64;
        s.counts[6] += (fresh - selected) as u64;
        s.counts[7] += (c.owners - fresh) as u64;
        s.frontier_stats[2] += c.visible as u64;
        s.frontier_stats[3] += rows.len() as u64;
        s.frontier_stats[4] += selected as u64;
        s.frontier_stats[5] += c.residual.len() as u64;
        Some(Boundary {
            entries: rows.into_iter(),
            total: c.visible,
            omitted_fresh: fresh - selected,
        })
    })
}
pub(crate) fn fuse_seal() -> bool {
    STATE.with_borrow(|s| s.as_ref().is_some_and(|s| s.composed >= 2))
}
pub(crate) fn charged(fields: usize) {
    STATE.with_borrow_mut(|s| {
        let s = s.as_mut().unwrap();
        s.frontier_stats[6] += 1;
        s.frontier_stats[7] += fields as u64;
    });
}
pub(crate) fn inline_child() -> bool {
    STATE.with_borrow(|s| s.as_ref().is_some_and(|s| s.composed >= 3))
}
pub(crate) fn absorbed() {
    STATE.with_borrow_mut(|s| s.as_mut().unwrap().frontier_stats[8] += 1);
}

#[derive(Deserialize, Clone)]
struct MacroPolicy {
    weights: [f32; 8],
    bias: f32,
    threshold: f32,
}
#[derive(serde::Serialize)]
struct Charge {
    /// observed source state at true publication
    root: usize,
    owner: u64,
    producer: usize,
    effect: usize,
    issue: u64,
    version: u64,
    generation: u64,
    value: i64,
    depth: usize,
    features: [f32; 8],
    selected: bool,
    superseded: u64,
    visible_version_misses: u64,
    /// source candidate encounter, matching fresh branch, native win, owned header inspected during frontier rebuild
    counts: [u64; 4],
}
fn features(c: &Child, threshold: i64) -> [f32; 8] {
    [
        1.,
        (c.producer % 64) as f32 / 63.,
        (c.effect.min(15) as f32) / 15.,
        (c.value.clamp(-32, 32) as f32) / 32.,
        (c.depth.min(16) as f32) / 16.,
        (c.value == threshold) as u8 as f32,
        (c.value > threshold) as u8 as f32,
        (c.depth > 1) as u8 as f32,
    ]
}
fn admit(s: &mut State, c: &Child) -> bool {
    let x = features(c, s.family.threshold);
    let selected = s.composed > 0
        && s.macro_policy.as_ref().is_none_or(|p| {
            x.iter().zip(p.weights).fold(p.bias, |v, (x, w)| v + x * w) >= p.threshold
        });
    s.delta.ever_selected |= selected;
    if s.profile {
        s.charges.push(Charge {
            root: c.root,
            owner: c.owner,
            producer: c.producer,
            effect: c.effect,
            issue: c.issue,
            version: c.version,
            generation: c.generation,
            value: c.value,
            depth: c.depth,
            features: x,
            selected,
            superseded: 0,
            visible_version_misses: 0,
            counts: [0; 4],
        });
    }
    selected
}
fn audit_read(s: &mut State, c: Child, fresh: bool, branch: usize) {
    if !s.profile {
        return;
    }
    let r = &mut s.charges[c.generation as usize - 1];
    r.counts[0] += 1;
    r.counts[1] += u64::from(fresh && c.branch as usize == branch);
}
