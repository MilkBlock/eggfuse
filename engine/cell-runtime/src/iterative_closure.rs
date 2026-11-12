//! Select finite closure routes from actual completed ancestry. Typed source
//! checks, not event counts or serialized certificates, authorize lowering.
use super::*;

impl Catalog {
    pub fn emit_history_closures(
        p: &Program,
        plan: &mut J,
        history: &J,
        extra_units: usize,
    ) -> Result<()> {
        if history["schema"] != "eggfuse-cell-runtime-history/v1"
            || history["program_sha256"] != p.artifact["sha256"]
        {
            return Err("closure history belongs to a different Program or schema".into());
        }
        let mut catalog = Self::parse(p, plan)?;
        if extra_units > catalog.limits.per_round {
            return Err("closure additions exceed per-round budget".into());
        }
        let capacity = catalog
            .units
            .len()
            .checked_add(extra_units)
            .ok_or("closure budget overflow")?;
        catalog.limits.total = catalog.limits.total.max(capacity);
        let events = array(&history["events"])?;
        let mut paths = Vec::<Vec<(Option<usize>, Entry)>>::new();
        let mut support = BTreeMap::<Vec<(Option<usize>, Entry)>, u64>::new();
        let mut boundary_rejections = 0;
        for (index, event) in events.iter().enumerate() {
            let entry: Entry =
                serde_json::from_value(event["entry"].clone()).map_err(|e| e.to_string())?;
            let parent: Option<usize> = serde_json::from_value(event["parent"].clone())
                .map_err(|e| e.to_string())?;
            let run = event["run"].as_u64().ok_or("history Run missing")?;
            let mut path = if let Some(parent) = parent {
                if parent >= index {
                    return Err("history ancestry must point backwards".into());
                }
                let previous = events[parent]["run"].as_u64().ok_or("parent Run missing")?;
                if previous >= run {
                    boundary_rejections += 1;
                    vec![]
                } else {
                    paths[parent].clone()
                }
            } else {
                vec![]
            };
            let output = event["output"].as_u64().ok_or("history output missing")? as usize;
            path.push(((!path.is_empty()).then_some(output), entry));
            let limit = catalog.limits.depth.min(catalog.limits.nodes);
            if path.len() > limit {
                path.remove(0);
                path[0].0 = None;
            }
            if path.len() > 1 {
                *support.entry(path.clone()).or_default() += 1;
            }
            paths.push(path);
        }
        let mut ranked = support
            .into_iter()
            .filter(|(_, n)| *n >= catalog.limits.support)
            .collect::<Vec<_>>();
        ranked.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        let mut selected = vec![];
        let mut added = 0;
        let mut guarded = 0;
        let mut unsupported = 0;
        let mut budget_rejections = 0;
        for (path, visits) in ranked {
            let proof = crate::cell_completion::cross_run_closure_transfer(p, &path);
            match proof["kind"].as_str() {
                Some("saturated" | "internal_completion") => (),
                Some("guarded") => {
                    guarded += 1;
                    continue;
                }
                _ => {
                    unsupported += 1;
                    continue;
                }
            }
            let mut trial = catalog.clone();
            let mut joins = vec![];
            let Some(mut left) = trial.leaves.get(&path[0].1).copied() else {
                unsupported += 1;
                continue;
            };
            let mut valid = true;
            for end in 2..=path.len() {
                if let Some(id) = trial
                    .units
                    .iter()
                    .position(|u| u.path.as_ref() == &path[..end])
                {
                    left = id;
                    continue;
                }
                let Some(right) = trial.leaves.get(&path[end - 1].1).copied() else {
                    valid = false;
                    break;
                };
                let join = Join {
                    left,
                    output: path[end - 1].0.ok_or("closure path lacks publication")?,
                    right,
                };
                let Some(unit) = trial.combine(p, join) else {
                    valid = false;
                    break;
                };
                if unit.path.as_ref() != &path[..end] {
                    valid = false;
                    break;
                }
                left = trial.units.len();
                trial.units.push(unit);
                trial.jumps.insert(join, left);
                joins.push(join);
            }
            if !valid {
                unsupported += 1;
                continue;
            }
            if added + joins.len() > extra_units {
                budget_rejections += 1;
                continue;
            }
            added += joins.len();
            plan["joins"]
                .as_array_mut()
                .ok_or("missing joins")?
                .extend(joins.iter().map(|j| json!(j)));
            selected.push(json!({"unit":left,"support":visits,"kind":proof["kind"],"added_prefixes":joins.len(),"source_path":path}));
            catalog = trial;
        }
        plan["limits"]["total"] = json!(catalog.limits.total);
        // Lower only this directory. No speculative structural expansion.
        Self::emit_policy(p, plan, true, true, true, true, true, false, None)?;
        plan["closure_selection"] = json!({"schema":"eggfuse-history-closure-selection/v1",
            "history_program":history["program_sha256"],"selected":selected,"added_units":added,
            "boundary_rejections":boundary_rejections,"guarded_paths":guarded,
            "unsupported_paths":unsupported,"budget_rejections":budget_rejections,
            "scope":"history selects routes; existing typed result-switch rechecks executable lowering; not measured savings"});
        Ok(())
    }
}
