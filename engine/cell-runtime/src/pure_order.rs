//! A same-table overlap can commute only when the complete old equality
//! frontier is disjoint from the new source effects and every affected result.
//! A missing frontier retains the original order fence; digest/type similarity
//! never proves this independence.
use super::*;

#[derive(Default)]
pub(super) struct Order {
    source_disjoint: Option<bool>,
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unavailable_frontiers_and_source_aliases_cannot_certify_independence() {
        let mut forecast = Forecast {
            tables: 1,
            groups: vec![Influence {
                roots: None,
                table: 0,
                tables: vec![true],
                reads: vec![],
                pure: true,
                global: false,
            }],
        };
        let mut counts = Counts::default();
        let mut batch = Batch::default();
        batch.pairs.push((2, 3));
        assert_eq!(
            Order::default().preserves(0, 4, &batch, &forecast, &mut counts, 0),
            Some(false)
        );
        assert_eq!(counts.pure_epoch_frontier_unknown, 1);
        forecast.groups[0].roots = Some([2].into_iter().collect());
        // Disjoint constructor outputs cannot excuse a source union touching
        // an older result. Both source endpoints are part of the obligation.
        assert_eq!(
            Order::default().preserves(0, 4, &batch, &forecast, &mut counts, 0),
            Some(false)
        );
        batch.pairs.clear();
        batch.births.push(Birth {
            table: 0,
            key: smallvec::smallvec![Value::Eq(2)],
            output: 4,
        });
        assert_eq!(
            Order::default().preserves(0, 4, &batch, &forecast, &mut counts, 0),
            Some(false)
        );
        batch.births[0].key.clear();
        batch.births[0].output = 2;
        assert_eq!(
            Order::default().preserves(0, 4, &batch, &forecast, &mut counts, 0),
            Some(false)
        );
        batch.births.clear();
        assert_eq!(
            Order::default().preserves(0, 4, &batch, &forecast, &mut counts, 0),
            Some(true)
        );
        counts.pure_epoch_frontier_checks = MAX_VISITS;
        assert_eq!(
            Order::default().preserves(0, 4, &batch, &forecast, &mut counts, 0),
            None
        );
    }
}
impl Order {
    fn root_disjoint(
        id: u64,
        forecast: &Forecast,
        counts: &mut Counts,
        before: u64,
    ) -> Option<bool> {
        if cost(counts) - before >= MAX_VISITS {
            return None;
        }
        counts.pure_epoch_frontier_roots += 1;
        for group in &forecast.groups {
            if cost(counts) - before >= MAX_VISITS {
                return None;
            }
            counts.pure_epoch_frontier_checks += 1;
            let Some(roots) = &group.roots else {
                counts.pure_epoch_frontier_unknown += 1;
                return Some(false);
            };
            if roots.contains(&id) {
                counts.pure_epoch_frontier_conflicts += 1;
                return Some(false);
            }
        }
        Some(true)
    }
    fn sources_disjoint(
        &mut self,
        batch: &Batch,
        forecast: &Forecast,
        counts: &mut Counts,
        before: u64,
    ) -> Option<bool> {
        if let Some(disjoint) = self.source_disjoint {
            return Some(disjoint);
        }
        let sources = batch.pairs.iter().flat_map(|&(a, b)| [a, b]);
        let births = batch.births.iter().flat_map(|birth| {
            birth
                .key
                .iter()
                .filter_map(|value| match value {
                    Value::Eq(id) => Some(*id),
                    _ => None,
                })
                .chain(std::iter::once(birth.output))
        });
        for id in sources.chain(births) {
            if !Self::root_disjoint(id, forecast, counts, before)? {
                self.source_disjoint = Some(false);
                return Some(false);
            }
        }
        self.source_disjoint = Some(true);
        Some(true)
    }
    pub(super) fn preserves(
        &mut self,
        table: usize,
        output: u64,
        batch: &Batch,
        forecast: &Forecast,
        counts: &mut Counts,
        before: u64,
    ) -> Option<bool> {
        let (ready, checks) = forecast.readiness(&[table]);
        counts.pure_epoch_order_checks += checks;
        if ready {
            // Complete influence visits result-only uses too: if this result
            // belonged to its frontier, its owning table would be affected.
            return Some(true);
        }
        counts.pure_epoch_order_refinements += 1;
        // The source endpoints and new sites must not change/extend an older
        // closure. Each subsequent affected constructor checks its result too,
        // so a chain cannot silently re-enter the old frontier downstream.
        let disjoint = self.sources_disjoint(batch, forecast, counts, before)?
            && Self::root_disjoint(output, forecast, counts, before)?;
        if disjoint {
            counts.pure_epoch_order_disjoint += 1;
        } else {
            counts.pure_epoch_order_rejections += 1;
            *counts.pure_epoch_order_tables.entry(table).or_default() += 1;
        }
        Some(disjoint)
    }
}
