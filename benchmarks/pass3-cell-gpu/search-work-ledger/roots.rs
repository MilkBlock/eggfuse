// Root memory snapshots are rebuilt on the native table version, including repair.
use crate::graph::{Dependency, Graph};
use crate::program::Result;
use std::collections::HashMap;

#[derive(Default)]
pub struct RootMemory {
    tables: HashMap<usize, (u64, Vec<Dependency>, Vec<(u64, u64)>)>,
}
impl RootMemory {
    pub fn read(
        &mut self,
        g: &Graph,
        t: usize,
        wm: u64,
        weights: [f32; 3],
        budget: usize,
    ) -> Result<Vec<Dependency>> {
        if self
            .tables
            .get(&t)
            .is_none_or(|(version, _, _)| *version != g.query_versions[t])
        {
            let mut rows = Vec::new();
            for w in g.witnesses(t) {
                crate::search_work::add(2, 1);
                if let Some(row) = g.row(w)?
                    && !row.hidden
                {
                    rows.push((row.epoch, w));
                }
            }
            rows.sort_unstable();
            let heads = rows
                .chunks(8)
                .map(|page| (page[0].0, page.last().unwrap().0))
                .collect();
            self.tables.insert(
                t,
                (
                    g.query_versions[t],
                    rows.into_iter().map(|(_, w)| w).collect(),
                    heads,
                ),
            );
        }
        let (_, rows, pages) = &self.tables[&t];
        let mut ranked: Vec<_> = pages
            .iter()
            .enumerate()
            .map(|(page, &(lo, hi))| {
                let age = g.epoch.saturating_sub(hi).min(32) as f32 / 32.;
                let x = [f32::from(hi >= wm), f32::from(lo >= wm), 1. - age];
                let score = x.iter().zip(weights).map(|(v, w)| v * w).sum::<f32>();
                (score, page)
            })
            .collect();
        crate::search_work::add(8, ranked.len());
        ranked.sort_unstable_by(|a, b| b.0.total_cmp(&a.0).then(a.1.cmp(&b.1)));
        Ok(ranked
            .into_iter()
            .take(budget)
            .flat_map(|(_, p)| rows[8 * p..(8 * p + 8).min(rows.len())].iter().copied())
            .collect())
    }
}
