use std::collections::BTreeSet;
#[derive(Default)]
struct DeltaCover {
    version: Option<u64>,
    journal_version: Option<u64>,
    incomplete: bool,
    dirty: BTreeSet<Dependency>,
    live: Vec<Dependency>,
    residual: BTreeSet<Dependency>,
    owned: FxHashMap<Dependency, Child>,
    by_arm: [BTreeMap<u64, BTreeSet<Dependency>>; 3],
    ever_selected: bool,
    stats: [u64; 5],
}
pub(crate) fn changes(graph: &Graph) {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state.as_mut().filter(|s| s.composed == 4) else {
            return;
        };
        let t = s.table;
        let d = &mut s.delta;
        let version = graph.query_versions[t];
        let changes = graph
            .changes
            .tables()
            .find(|(table, _)| *table == t)
            .map(|(_, c)| c);
        if d.version.is_some()
            && d.journal_version.is_some_and(|old| old != version)
            && changes.is_none_or(|c| c.is_empty())
        {
            d.incomplete = true;
        }
        d.journal_version = Some(version);
        if d.version.is_some()
            && let Some(changes) = changes
        {
            d.stats[0] += changes.len() as u64;
            d.dirty.extend(changes.keys().copied());
        }
    });
}
fn incremental_boundary(s: &mut State, g: &Graph, rid: usize, wm: u64) -> Option<Boundary> {
    let d = &mut s.delta;
    if !d.ever_selected {
        return None;
    }
    let version = g.query_versions[s.table];
    let complete = d.incomplete
        || d.version.is_none()
        || (d.version != Some(version) && d.journal_version != Some(version));
    let dirty = if complete {
        s.frontier_stats[0] += 1;
        d.live.clear();
        d.residual.clear();
        d.owned.clear();
        for a in &mut d.by_arm {
            a.clear();
        }
        d.dirty.clear();
        g.witnesses(s.table)
    } else {
        std::mem::take(&mut d.dirty).into_iter().collect()
    };
    for w in dirty {
        s.frontier_stats[1] += 1;
        if let Some(c) = d.owned.remove(&w) {
            let arm = &mut d.by_arm[c.branch as usize];
            let group = arm.get_mut(&c.version).expect("indexed owner has epoch");
            group.remove(&w);
            if group.is_empty() {
                arm.remove(&c.version);
            }
        }
        d.residual.remove(&w);
        let old = d.live.binary_search(&w);
        let v = g
            .visible_epoch(w)
            .filter(|_| g.live_table(w) == Some(s.table));
        let Some(epoch) = v else {
            if let Ok(i) = old {
                d.stats[1] += (d.live.len() - i - 1) as u64;
                d.live.remove(i);
            }
            continue;
        };
        if let Err(i) = old {
            d.stats[1] += (d.live.len() - i) as u64;
            d.live.insert(i, w);
        }
        if let Some(c) = s
            .pending
            .get(&w)
            .filter(|c| c.version == epoch && c.macro_accepted)
        {
            if s.profile {
                s.charges[c.generation as usize - 1].counts[3] += 1;
            }
            d.by_arm[c.branch as usize]
                .entry(epoch)
                .or_default()
                .insert(w);
            d.owned.insert(w, *c);
        } else {
            d.residual.insert(w);
        }
    }
    d.version = Some(version);
    d.incomplete = false;
    if s.profile {
        // Independent audit reads the full visible table after the online update. Its
        // answers never enter the generator or the timed run.
        let source: Vec<_> = g
            .witnesses(s.table)
            .into_iter()
            .filter(|w| g.visible_epoch(*w).is_some())
            .collect();
        assert_eq!(d.live, source);
        for &w in &source {
            let eligible = s
                .pending
                .get(&w)
                .filter(|c| c.macro_accepted && Some(c.version) == g.visible_epoch(w));
            assert_eq!(
                d.owned.get(&w).map(|c| c.generation),
                eligible.map(|c| c.generation)
            );
            assert_eq!(d.residual.contains(&w), eligible.is_none());
        }
    }
    let branch = if rid == s.family.gt { 2 } else { 1 };
    let mut rows: Vec<_> = d
        .residual
        .iter()
        .map(|&w| (d.live.binary_search(&w).unwrap(), w, None))
        .collect();
    let mut fresh = 0;
    for (arm, groups) in d.by_arm.iter().enumerate() {
        for (_, members) in groups.range(wm..) {
            fresh += members.len();
            if arm == branch {
                rows.extend(
                    members
                        .iter()
                        .map(|w| (d.live.binary_search(w).unwrap(), *w, Some(d.owned[w]))),
                );
            }
        }
    }
    d.stats[2] += rows.len() as u64;
    d.stats[3] = d.stats[3].max(d.live.len() as u64);
    d.stats[4] += 1;
    rows.sort_unstable_by_key(|r| r.0);
    if s.profile {
        for c in d.owned.values() {
            let v = &mut s.charges[c.generation as usize - 1];
            v.counts[0] += 1;
            v.counts[1] += u64::from(c.version >= wm && c.branch as usize == branch);
        }
    }
    let selected = rows.len() - d.residual.len();
    s.counts[5] += selected as u64;
    s.counts[6] += (fresh - selected) as u64;
    s.counts[7] += (d.owned.len() - fresh) as u64;
    s.frontier_stats[2] += d.live.len() as u64;
    s.frontier_stats[3] += rows.len() as u64;
    s.frontier_stats[4] += selected as u64;
    s.frontier_stats[5] += d.residual.len() as u64;
    Some(Boundary {
        entries: rows.into_iter(),
        total: d.live.len(),
        omitted_fresh: fresh - selected,
    })
}
