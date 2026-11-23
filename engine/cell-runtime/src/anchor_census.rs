//! Read-only counterfactual expansion of every visible source delta anchor.
use super::*;

#[derive(Default)]
pub struct Census {
    pub rows: Vec<J>,
    pub partition: bool,
    pub coverage: Vec<J>,
}

impl Executor {
    pub fn enable_anchor_census(&mut self) {
        self.anchor_census = Some(Census::default());
    }

    pub fn enable_anchor_partition(&mut self) -> Result<()> {
        self.start_tokens(None)?;
        self.export_token_memory(None)?;
        self.token_history.as_mut().unwrap().selected_anchors = Some(BTreeMap::new());
        self.anchor_census = Some(Census {
            partition: true,
            ..Default::default()
        });
        Ok(())
    }

    pub fn anchor_coverage(&self) -> Option<&[J]> {
        self.anchor_census.as_ref().map(|c| c.coverage.as_slice())
    }

    pub fn anchor_census_rows(&self) -> Option<&[J]> {
        self.anchor_census.as_ref().map(|c| c.rows.as_slice())
    }

    pub(super) fn census_anchors(
        &mut self,
        rid: usize,
        mut commits: Option<&mut Vec<Binding>>,
    ) -> Result<Option<BTreeSet<Vec<Value>>>> {
        let rule = self.graph.program.rules[rid].clone();
        let run = self.steps.len() + 1;
        let wm = self.watermarks[rid];
        self.sieve
            .prepare(rid, &self.graph, &mut self.query_indexes)?;
        let mut keys = BTreeSet::new();
        let mut has_table = false;
        let mut selected_keys = BTreeSet::new();
        for (pivot, atom) in rule.query.iter().enumerate() {
            let Call::Table(table) = atom.call else {
                continue;
            };
            if has_table && !rule.seminaive {
                continue;
            }
            has_table = true;
            let discovery = Instant::now();
            let anchors = self
                .graph
                .witnesses(table)
                .into_iter()
                .filter(|&w| {
                    self.graph
                        .visible_epoch(w)
                        .is_some_and(|v| v < self.graph.epoch && (!rule.seminaive || v >= wm))
                })
                .collect::<Vec<_>>();
            let discovery_ns = discovery.elapsed().as_nanos() as u64;
            let order = self
                .graph
                .program
                .multi_stage
                .entries
                .get(&(rid, pivot))
                .cloned();
            let selected = self
                .token_history
                .as_mut()
                .and_then(|h| h.selected_anchors.as_mut())
                .and_then(|by_role| by_role.remove(&(rid, pivot)))
                .unwrap_or_default();
            let mut selected_count = 0;
            let mut selected_ns = 0;
            let mut selected_visits = 0;
            let mut empty = 0;
            let mut proofs = 0;
            let mut expand_ns = 0;
            let mut visits = 0;
            let mut point_reads = 0;
            let mut selected_points = 0;
            let mut out = Vec::new();
            let (chosen, residual): (Vec<_>, Vec<_>) =
                anchors.iter().copied().partition(|w| selected.contains(w));
            for (is_selected, batch) in [(true, chosen), (false, residual)] {
                for witness in batch {
                    let visits_before = self.graph.stats.residual_candidates;
                    let points_before = self.continuation_stats.point_reads;
                    let started = Instant::now();
                    let row = self.graph.row(witness)?.ok_or("missing visible anchor")?;
                    let mut env = QueryEnv::new(
                        self.graph.program.templates[rule.template].sorts.len(),
                        QueryFacts::Ports(vec![None; rule.query.len()]),
                    );
                    out.clear();
                    if atom
                        .args
                        .iter()
                        .zip(row.values.iter())
                        .all(|(a, v)| bind(a, v, &mut env, &self.graph))
                    {
                        env.record(pivot, Some(witness));
                        let mut remaining = (0..rule.query.len())
                            .map(|i| i != pivot)
                            .collect::<Vec<_>>();
                        let mut epoch = row.epoch;
                        let live = if let Some(steps) = &order {
                            self.points(
                                rid,
                                &rule.query,
                                steps,
                                &mut env,
                                &mut remaining,
                                &mut epoch,
                                None,
                                false,
                            )?
                        } else {
                            true
                        };
                        if live {
                            self.solve(
                                &rule.query,
                                rid,
                                &mut remaining,
                                &mut env,
                                epoch,
                                &mut out,
                                None,
                            )?;
                        }
                    }
                    // Match the Actor's first-fresh pivot convention. The native generic
                    // latest-witness convention partitions the same bindings differently.
                    if rule.seminaive {
                        out.retain(|b| {
                            (0..pivot).all(|i| {
                                let Some(dep) = b.known.receipt(i) else {
                                    return true;
                                };
                                self.graph.visible_epoch(dep).is_some_and(|v| v < wm)
                            })
                        });
                    }
                    let elapsed = started.elapsed().as_nanos() as u64;
                    expand_ns += elapsed;
                    visits += self.graph.stats.residual_candidates - visits_before;
                    let reads = self.continuation_stats.point_reads - points_before;
                    point_reads += reads;
                    empty += usize::from(out.is_empty());
                    proofs += out.len();
                    if is_selected {
                        selected_count += 1;
                        selected_ns += elapsed;
                        selected_points += reads;
                        selected_visits += self.graph.stats.residual_candidates - visits_before;
                        selected_keys
                            .extend(out.iter().map(|b| {
                                b.input_values(&rule.inputs).cloned().collect::<Vec<_>>()
                            }));
                    }
                    if let Some(dst) = commits.as_deref_mut() {
                        dst.append(&mut out);
                    } else {
                        keys.extend(
                            out.iter()
                                .map(|b| b.input_values(&rule.inputs).cloned().collect::<Vec<_>>()),
                        );
                    }
                }
            }
            self.anchor_census.as_mut().unwrap().rows.push(json!([
                run,
                rid,
                pivot,
                wm,
                rule.seminaive,
                self.dirty[rid],
                anchors.len(),
                empty,
                proofs,
                visits,
                discovery_ns,
                expand_ns,
                selected_count,
                selected_visits,
                selected_ns,
                point_reads,
                selected_points
            ]));
        }
        if !has_table {
            self.anchor_census.as_mut().unwrap().rows.push(json!([
                run,
                rid,
                null,
                wm,
                rule.seminaive,
                self.dirty[rid],
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
            ]));
        }
        if commits.is_some() && has_table {
            self.anchor_census.as_mut().unwrap().coverage.push(json!([
                run,
                rid,
                selected_keys.len()
            ]));
        }
        Ok(has_table.then_some(keys))
    }
}
