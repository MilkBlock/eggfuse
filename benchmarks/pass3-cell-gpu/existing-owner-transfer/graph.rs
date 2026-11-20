use serde_json::{Value as JV, json};
use std::collections::{BTreeMap as TrialMap, BTreeSet as TrialSet};

impl Graph {
    fn state_for_sources(&self, ids: &[u32]) -> Result<Vec<JV>> {
        let mut out = vec![];
        for &id in ids {
            for op in self.cells.owner_ops(id) {
                let r = FactRef { cell: id, op };
                if let Some(row) = self.row(Dependency::Fact(r))? {
                    out.push(json!({"ref":r,"table":row.table,"fields":row.values.iter().collect::<Vec<_>>(),
                                  "epoch":row.epoch,"hidden":row.hidden}));
                }
            }
        }
        Ok(out)
    }
    fn external_readers(&self, ids: &[u32]) -> Result<Vec<JV>> {
        let mut targets = TrialMap::new();
        for &id in ids {
            for op in self.cells.owner_ops(id) {
                let addr = FactRef { cell: id, op };
                if let Some(row) = self.row(Dependency::Fact(addr))?
                    && !row.hidden
                    && let Some(Value::Eq(e)) = row.values.last()
                {
                    targets.entry(root(&self.parents, *e)).or_insert(addr);
                }
            }
        }
        let mut found = vec![];
        for t in 0..self.program.tables.len() {
            for address in self.witnesses(t) {
                if matches!(address,Dependency::Fact(f) if ids.contains(&f.cell)) {
                    continue;
                }
                let Some(row) = self.row(address)? else {
                    continue;
                };
                if row.hidden {
                    continue;
                }
                for (col, v) in row
                    .values
                    .iter()
                    .enumerate()
                    .take(row.values.len().saturating_sub(1))
                {
                    if let Value::Eq(e) = v
                        && let Some(target) = targets.get(&root(&self.parents, *e))
                    {
                        found.push(json!([address, t, col, root(&self.parents, *e), target]));
                    }
                }
            }
        }
        found.sort_by_cached_key(|v| v.to_string());
        Ok(found)
    }
    pub fn existing_owner_read(&self, ids: &[u32]) -> Result<JV> {
        Ok(
            json!({"old_refs":self.state_for_sources(ids)?,"external_readers":self.external_readers(ids)?}),
        )
    }
    pub fn force_owner_repair(
        &mut self,
        ids: &[u32],
        old_members: &[(u32, usize)],
        pick: usize,
    ) -> Result<JV> {
        let mut values = TrialMap::<String, Vec<(u64, FactRef, usize)>>::new();
        for &id in ids {
            for op in self.cells.owner_ops(id) {
                let addr = FactRef { cell: id, op };
                let Some(r) = self.row(Dependency::Fact(addr))? else {
                    continue;
                };
                let table = &self.program.tables[r.table];
                for (column, (v, sort)) in r.values.iter().zip(&table.schema).enumerate() {
                    if let Value::Eq(n) = v {
                        values.entry(sort.to_string()).or_default().push((
                            root(&self.parents, *n),
                            addr,
                            column,
                        ));
                    }
                }
            }
        }
        let owners: TrialMap<_, _> = old_members.iter().copied().collect();
        let mut seen = TrialSet::new();
        let mut candidates = vec![];
        for (sort, vs) in values {
            if sort.contains('@') {
                continue;
            }
            for first in &vs {
                for other in &vs {
                    if first.0 >= other.0
                        || owners[&first.1.cell] == owners[&other.1.cell]
                        || !seen.insert((first.0, other.0))
                    {
                        continue;
                    }
                    candidates.push((sort.clone(), *first, *other));
                }
            }
        }
        let Some((sort, first, other)) = candidates.get(pick) else {
            return Ok(json!({"exhausted_candidates":candidates.len()}));
        };
        let n = self.stats.unions;
        let mut record = json!({"sort":sort,"left":first,"right":other,"previous_owners":[owners[&first.1.cell],owners[&other.1.cell]],"index":pick,"candidates":candidates.len()});
        if let Err(error) = self.union(first.0, other.0).and_then(|()| self.repair()) {
            record["rejected_by_source"] = json!(error);
            return Ok(record);
        }
        if root(&self.parents, first.0) != root(&self.parents, other.0) {
            return Err("failed to close requested equality".into());
        }
        record["union_delta"] = json!(self.stats.unions - n);
        record["canonical"] = json!(root(&self.parents, first.0));
        Ok(record)
    }
    /// Candidate domain before applying any policy. Each group must be one proved compiler shape.
    pub fn existing_owner_boundary(
        &mut self,
        mode: &str,
        choose: bool,
        expected_ids: &[u32],
        accounting: fn(bool) -> [usize; 4],
    ) -> Result<JV> {
        let already_split = !expected_ids.is_empty();
        if self.active_rhs.is_some()
            || !self.ownership_settled()
            || !self.pending_unions.is_empty()
            || !self.dirty.is_empty()
        {
            return Err("graph is not at a settled Run boundary".into());
        }
        let Some(m) = &self.ownership else {
            return Err("missing checked ownership program".into());
        };
        let components: Vec<_> = m
            .composition
            .components
            .iter()
            .enumerate()
            .filter_map(|(id, c)| {
                let c = c.as_ref()?;
                Some((id, c.shape, c.frames.to_vec()))
            })
            .collect();
        let mut domain = [0u64; 7];
        let mut event = JV::Null;
        for (component, shape, ids) in components {
            domain[0] += 1;
            if ids.len() < 2 {
                continue;
            }
            domain[1] += 1;
            let ordinary = ids.iter().all(|id| {
                self.cells.get(id).is_some_and(|c| {
                    c.completed
                        && c.parent.is_none()
                        && !c.facts.is_empty()
                        && c.values.is_unshared()
                        && c.facts.iter().all(|(&op, s)| {
                            s.owned && self.stable_node(FactRef { cell: *id, op }).is_some()
                        })
                })
            });
            if ordinary {
                domain[2] += 1;
            }
            if ordinary && choose && !already_split && mode.starts_with("split") && event.is_null()
            {
                // Create two real, disjoint old owners. No member is added during the later action.
                // Use the original transfer's eligibility and allocation routines, then wait a full Run.
                if ids.len() < 3 || self.external_readers(&ids)?.is_empty() {
                    continue;
                }
                let cut = ids.len().div_ceil(2);
                if !self.cells.can_transfer_completed(&ids[..cut])
                    || !self.cells.can_transfer_completed(&ids[cut..])
                {
                    continue;
                }
                if !self.cells.transfer_completed(&ids[..cut])
                    || !self.cells.transfer_completed(&ids[cut..])
                {
                    return Err("checked split failed".into());
                }
                let members: Vec<_> = ids
                    .iter()
                    .map(|id| (*id, self.cells.physical_owner(*id).unwrap().0))
                    .collect();
                event = json!({"kind":"seed_existing_owners","component":component,"shape":shape,"epoch":self.epoch,"members":members,"ids":ids});
                continue;
            }
            let old: Option<Vec<_>> = ids
                .iter()
                .map(|id| self.cells.physical_owner(*id))
                .collect();
            let Some(old) = old else { continue };
            domain[3] += 1;
            let owners = old.iter().map(|v| v.0).collect::<TrialSet<_>>();
            if owners.len() < 2 {
                continue;
            };
            domain[4] += 1;
            if owners.len() != 2 {
                continue;
            };
            domain[5] += 1;
            if old
                .iter()
                .any(|(owner, width)| old.iter().filter(|r| r.0 == *owner).count() != *width)
            {
                continue;
            }
            domain[6] += 1;
            if !choose
                || !event.is_null()
                || mode == "census"
                || (!already_split && mode.starts_with("split"))
            {
                continue;
            }
            if already_split && ids != expected_ids {
                continue;
            }
            let initial = self.existing_owner_read(&ids)?;
            if initial["external_readers"].as_array().unwrap().is_empty() {
                continue;
            }
            let mut allocation = None;
            let before = self.cells.live_owner_charge();
            let mapping = |g: &Self| {
                ids.iter()
                    .map(|id| (*id, g.cells.physical_owner(*id).unwrap().0))
                    .collect::<Vec<_>>()
            };
            let previous = mapping(self);
            let claimed_epoch = if mode.ends_with("stale") {
                self.epoch.checked_sub(1).unwrap_or(u64::MAX)
            } else {
                self.epoch
            };
            let outcome = if self.epoch != claimed_epoch {
                json!({"rejected":"epoch","offered_epoch":claimed_epoch})
            } else if mode.ends_with("partial") {
                // Keep one member from each old owner while dropping an attached sibling if possible.
                let exclude = old.iter().position(|v| v.1 >= 2);
                let mut input = ids.clone();
                if let Some(i) = exclude {
                    input.remove(i);
                } else {
                    input.pop();
                }
                if self.cells.extend_completed(&input).is_some() {
                    return Err("accepted unproved partial old group".into());
                }
                json!({"rejected":"incomplete_old_group","offered":input})
            } else if mode.ends_with("merge") {
                let from = accounting(true);
                let result = self.cells.extend_completed(&ids);
                let to = accounting(false);
                allocation = Some((from, to));
                let (added, merged, slots, facts) =
                    result.ok_or("valid fully covered old group was not merged")?;
                if added != 0 || merged != 1 {
                    return Err("expected only consolidation of two existing owners".into());
                }
                json!({"added":added,"merged":merged,"copied_slots":slots,"copied_fact_states":facts})
            } else {
                json!({"control":"keep_both"})
            };
            let after = self.cells.live_owner_charge();
            let end = self.existing_owner_read(&ids)?;
            if end != initial {
                return Err("transfer changed readable row/reader state".into());
            }
            event = json!({"kind":"existing_pair","component":component,"shape":shape,"old_epoch":self.epoch,"new_epoch":self.epoch,
                         "left_owner":old[0].0,"right_owner":old.iter().find(|r|r.0!=old[0].0).unwrap().0,
                         "destination":self.cells.physical_owner(ids[0]).unwrap().0,"ids":ids,
                         "old_members":previous,"new_members":mapping(self),
                         "member_source_templates":ids.iter().map(|id|self.cells.completed_meta(*id).unwrap().template).collect::<Vec<_>>(),
                         "member_birth_epochs":ids.iter().map(|id|self.cells.completed_meta(*id).unwrap().started_epoch).collect::<Vec<_>>(),
                         "retired_owner_ids":if outcome["merged"]==1 {owners.iter().copied().filter(|id|*id!=self.cells.physical_owner(ids[0]).unwrap().0).collect::<Vec<_>>()}else{vec![]},"old":initial,"new":end,
                         "old_charge":before,"new_charge":after,"allocation":allocation,"outcome":outcome});
        }
        Ok(json!({"domain":domain,"event":event}))
    }
}
