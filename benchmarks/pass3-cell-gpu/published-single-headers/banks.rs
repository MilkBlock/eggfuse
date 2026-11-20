// The bank describes only visibility and stable typed addresses. It cannot invent a
// binding, advance a rule, or update a graph. Maps live in exactly one source execution.
#[derive(Default, serde::Serialize)]
pub(crate) struct HeaderWork {
    builds: u64,
    hits: u64,
    direct_inherited: u64,
    direct_materialized: u64,
    direct_borrows: u64,
    full_scans: u64,
    full_source_reads: u64,
    delta_updates: u64,
    delta_source_reads: u64,
    reused_rows: u64,
    uncovered: u64,
    notifications: u64,
    checked_rows: u64,
    stale_rejects: u64,
    fresh_builds: u64,
    fresh_hits: u64,
    fresh_scan_rows: u64,
    fresh_returned: u64,
}
pub(crate) struct HeaderBank {
    pub direct: Option<std::sync::Arc<Vec<crate::single_witness::SourceHeader>>>,
    pub rows: Vec<(Dependency, u64)>,
    pub max: u64,
    version: u64,
    offsets: std::cell::RefCell<Vec<(u64, std::rc::Rc<Vec<u32>>)>>,
}
#[derive(Default)]
struct BankHistory {
    through: u64,
    valid: bool,
    changed: std::collections::BTreeSet<Dependency>,
}
#[derive(Default)]
pub(crate) struct HeaderExchange {
    initial: Option<std::sync::Arc<std::collections::BTreeSet<Dependency>>>,
    births: std::rc::Rc<rustc_hash::FxHashSet<Dependency>>,
    views: std::collections::HashMap<usize, std::rc::Rc<HeaderBank>>,
    histories: std::collections::HashMap<usize, BankHistory>,
    pub stats: HeaderWork,
}
impl Graph {
    pub(crate) fn header_publish(&self) {
        if self.header_mode < 3 {
            return;
        }
        let mut x = self.headers.borrow_mut();
        for (t, changes) in self.changes.tables() {
            let Some(h) = x.histories.get_mut(&t) else {
                continue;
            };
            if !h.valid || h.through == self.query_versions[t] {
                continue;
            }
            // Coalescing is permitted: choose the full-source control whenever notifications
            // cannot account for every published table generation.
            if self.header_mode == 5
                || self.query_versions[t].saturating_sub(h.through) > changes.len() as u64
                || h.changed.len() + changes.len() > 16384
            {
                h.valid = false;
                x.stats.uncovered += 1;
                continue;
            }
            h.through = self.query_versions[t];
            h.changed.extend(changes.keys().copied());
            x.stats.notifications += changes.len() as u64;
        }
    }
    pub(crate) fn header_bank(&self, t: usize) -> std::rc::Rc<HeaderBank> {
        let mut x = self.headers.borrow_mut();
        let ver = self.query_versions[t];
        if let Some(b) = x.views.get(&t).cloned()
            && b.version == ver
        {
            x.stats.hits += 1;
            return b;
        }
        let prev = x.views.remove(&t);
        let history = x.histories.remove(&t);
        let can_delta = self.header_mode >= 3
            && prev.is_some()
            && history
                .as_ref()
                .is_some_and(|h| h.valid && h.through == ver);
        if self.header_mode >= 6 {
            if let Some(init) = x.initial.take() {
                x.births = std::rc::Rc::new(init.iter().copied().collect())
            }
            let births = x.births.clone();
            let header = |d, e| {
                crate::single_witness::SourceHeader::from_published(d, e, births.contains(&d))
            };
            let mut out = Vec::new();
            if can_delta {
                let b = prev
                    .as_ref()
                    .unwrap()
                    .direct
                    .as_ref()
                    .expect("direct source configured before inference");
                let mut i = 0;
                let h = history.unwrap();
                out.reserve(b.len() + h.changed.len());
                for dep in h.changed {
                    while i < b.len() && b[i].source.unwrap() < dep {
                        out.push(b[i]);
                        i += 1;
                        x.stats.direct_inherited += 1
                    }
                    if i < b.len() && b[i].source == Some(dep) {
                        i += 1;
                    }
                    x.stats.delta_source_reads += 1;
                    if let Some(e) = self.visible_epoch(dep) {
                        out.push(header(dep, e));
                        x.stats.direct_materialized += 1;
                    }
                }
                out.extend_from_slice(&b[i..]);
                x.stats.direct_inherited += (b.len() - i) as u64;
                x.stats.delta_updates += 1;
            } else {
                x.stats.full_scans += 1;
                let ids = self.witnesses(t);
                x.stats.full_source_reads += ids.len() as u64;
                out.reserve(ids.len());
                for d in ids {
                    if let Some(e) = self.visible_epoch(d) {
                        out.push(header(d, e))
                    }
                }
                x.stats.direct_materialized += out.len() as u64;
            }
            if self.header_audit {
                assert!(
                    self.witnesses(t)
                        .into_iter()
                        .filter_map(|d| self.visible_epoch(d).map(|e| (
                            Some(d),
                            e,
                            births.contains(&d)
                        )))
                        .eq(out.iter().map(|h| (h.source, h.version, h.is_initial())))
                );
                x.stats.checked_rows += out.len() as u64
            }
            let max = out.iter().map(|h| h.version).max().unwrap_or(0);
            let b = std::rc::Rc::new(HeaderBank {
                rows: vec![],
                direct: Some(std::sync::Arc::new(out)),
                max,
                version: ver,
                offsets: Default::default(),
            });
            x.views.insert(t, b.clone());
            x.histories.insert(
                t,
                BankHistory {
                    through: ver,
                    valid: true,
                    ..Default::default()
                },
            );
            x.stats.builds += 1;
            return b;
        }
        let rows = if can_delta {
            let b = prev.as_ref().unwrap();
            let h = history.unwrap();
            let mut rows = Vec::with_capacity(b.rows.len() + h.changed.len());
            let mut i = 0;
            for d in h.changed {
                while i < b.rows.len() && b.rows[i].0 < d {
                    rows.push(b.rows[i]);
                    i += 1;
                    x.stats.reused_rows += 1
                }
                if i < b.rows.len() && b.rows[i].0 == d {
                    i += 1
                }
                x.stats.delta_source_reads += 1;
                if let Some(e) = self.visible_epoch(d) {
                    rows.push((d, e))
                }
            }
            x.stats.reused_rows += (b.rows.len() - i) as u64;
            rows.extend_from_slice(&b.rows[i..]);
            x.stats.delta_updates += 1;
            rows
        } else {
            if self.header_mode == 5 && prev.is_some() {
                x.stats.stale_rejects += 1
            }
            x.stats.full_scans += 1;
            let ids = self.witnesses(t);
            x.stats.full_source_reads += ids.len() as u64;
            ids.into_iter()
                .filter_map(|d| self.visible_epoch(d).map(|e| (d, e)))
                .collect()
        };
        if self.header_audit {
            let truth = self
                .witnesses(t)
                .into_iter()
                .filter_map(|d| self.visible_epoch(d).map(|e| (d, e)))
                .collect::<Vec<_>>();
            assert_eq!(
                truth, rows,
                "published header order/epoch differs from native view"
            );
            x.stats.checked_rows += rows.len() as u64;
        }
        let max = rows.iter().map(|r| r.1).max().unwrap_or(0);
        let b = std::rc::Rc::new(HeaderBank {
            rows,
            direct: None,
            max,
            version: ver,
            offsets: Default::default(),
        });
        x.views.insert(t, b.clone());
        if self.header_mode >= 3 {
            x.histories.insert(
                t,
                BankHistory {
                    through: ver,
                    valid: true,
                    ..Default::default()
                },
            );
        }
        x.stats.builds += 1;
        b
    }
    pub(crate) fn header_offsets(&self, b: &HeaderBank, watermark: u64) -> std::rc::Rc<Vec<u32>> {
        let mut x = self.headers.borrow_mut();
        let mut ranges = b.offsets.borrow_mut();
        if let Some((_, offsets)) = ranges.iter().find(|(w, _)| *w == watermark) {
            x.stats.fresh_hits += 1;
            x.stats.fresh_returned += offsets.len() as u64;
            return offsets.clone();
        }
        let offsets = if b.max < watermark {
            vec![]
        } else {
            x.stats.fresh_scan_rows += b.len() as u64;
            (0..b.len())
                .filter_map(|i| (b.at(i).1 >= watermark).then_some(i as u32))
                .collect()
        };
        x.stats.fresh_builds += 1;
        x.stats.fresh_returned += offsets.len() as u64;
        if ranges.len() == 4 {
            ranges.remove(0);
        }
        let offsets = std::rc::Rc::new(offsets);
        ranges.push((watermark, offsets.clone()));
        offsets
    }
}
impl Graph {
    pub fn configure_header_view(&mut self, mode: u64, audit: bool) -> Result<()> {
        if mode > 7 {
            return Err("unsupported published header mode".into());
        }
        self.header_mode = mode as u8;
        self.header_audit = audit;
        Ok(())
    }
    pub fn header_view_report(&self) -> serde_json::Value {
        serde_json::json!(self.headers.borrow().stats)
    }
}

impl HeaderBank {
    pub fn len(&self) -> usize {
        self.direct.as_ref().map_or(self.rows.len(), |v| v.len())
    }
    pub fn at(&self, i: usize) -> (Dependency, u64) {
        self.direct
            .as_ref()
            .map_or_else(|| self.rows[i], |v| (v[i].source.unwrap(), v[i].version))
    }
}
impl Graph {
    pub(crate) fn remember_header_births(
        &self,
        b: std::sync::Arc<std::collections::BTreeSet<Dependency>>,
    ) {
        self.headers.borrow_mut().initial = Some(b)
    }
    pub(crate) fn direct_headers(
        &self,
        t: usize,
    ) -> std::sync::Arc<Vec<crate::single_witness::SourceHeader>> {
        let b = self.header_bank(t);
        self.headers.borrow_mut().stats.direct_borrows += 1;
        b.direct.as_ref().unwrap().clone()
    }
}
