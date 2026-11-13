//! Select finite closure routes from actual completed ancestry. Typed source
//! checks, not event counts or serialized certificates, authorize lowering.
use super::*;

impl Catalog {
    /// Offline replay of recorded successful ancestry through the installed
    /// switch. This describes dispatch, not execution or witness validity.
    /// Missing producer roots start at zero, exactly as diagnostic collection.
    pub fn describe_history_dispatch(&self, history: &J) -> Result<J> {
        let events=array(&history["events"])?;
        let states=observed_states(&self.switch,events)?;
        let rows=events.iter().zip(states).enumerate().map(|(index,(event,pc))|
            json!({"event":index,"entry":event["entry"],"unit":(pc!=0).then(||self.switch.active(pc)),
                "transfer":self.switch.signature_at(pc)})).collect::<Vec<_>>();
        Ok(json!(rows))
    }
    /// A matched entry is entered only AFTER the ordinary query has succeeded.
    /// It may retain partial RHS reuse; it never bypasses residual enumeration,
    /// primitives or mutable reads. Source coordinates are checked by combine.
    pub fn emit_matched_routes(p:&Program,plan:&mut J,routes:&[(usize,usize,usize,usize)]) -> Result<()> {
        let mut catalog=Self::parse(p,plan)?;
        let mut selected=vec![];
        let lower=|c:&Catalog|crate::result_handoff::Switch::build(p,
            c.units.iter().map(|u|u.path.as_ref()),&c.leaves,true,true,true,true,true);
        for &(producer,output,consumer,pivot) in routes {
            if producer>=p.rules.len() || consumer>=p.rules.len() {return Err("matched route rule".into());}
            let mut trial=catalog.clone();
            for entry in [(producer,None),(consumer,Some(pivot))] {
                if trial.leaves.contains_key(&entry) {continue;}
                if let Some(pivot)=entry.1 {
                    let rule=&p.rules[entry.0];
                    if !rule.seminaive || !matches!(rule.query.get(pivot).map(|a|&a.call),Some(Call::Table(_))) {
                        return Err("matched route anchor".into());
                    }
                    trial.matched_entries.entry(entry.0).or_default().push(pivot);
                }
                trial.leaves.insert(entry,trial.units.len());
                trial.units.push(Unit {path:vec![(None,entry)].into_boxed_slice()});
            }
            let join=Join {left:trial.leaves[&(producer,None)],output,right:trial.leaves[&(consumer,Some(pivot))]};
            if trial.jumps.contains_key(&join) {continue;}
            let unit=trial.combine(p,join).ok_or("invalid matched route")?;
            let path=unit.path.clone();
            trial.jumps.insert(join,trial.units.len());trial.units.push(unit);
            // Reject metadata-only additions that cannot change terminal reuse.
            let before=lower(&catalog);
            let pc=path.iter().fold(0,|pc,(op,entry)|before.observe_advance(pc,op.unwrap_or(0),*entry));
            let after=lower(&trial).transfer_signature(&path);
            if after["program"]["reuse"].as_array().is_none_or(Vec::is_empty)
                || before.signature_at(pc)==after {continue;}
            if trial.units.len()-catalog.units.len()>trial.limits.per_round {return Err("matched route budget".into());}
            trial.limits.total=trial.limits.total.max(trial.units.len());
            selected.push(json!({"producer":producer,"output":output,"consumer":consumer,"pivot":pivot}));
            catalog=trial;
        }
        // A null initial catalog with no useful typed reuse remains absent.
        // Do not manufacture roots, captures or dispatch for rejected routes.
        if catalog.units.is_empty() { return Ok(()); }
        encode_catalog(p,plan,&catalog)?;
        Self::emit_policy(p,plan,true,true,true,true,true,false,None)?;
        plan["matched_route_selection"]=json!({"routes":selected,
            "contract":"ordinary matcher completes all conditions before dispatch; existing receipts validate RHS reuse"});
        Ok(())
    }
    pub fn emit_history_closures(
        p: &Program,
        plan: &mut J,
        history: &J,
        extra_units: usize,
    ) -> Result<()> {
        if !matches!(history["schema"].as_str(),Some("eggfuse-cell-runtime-history/v1" | "eggfuse-cell-runtime-history/v2"))
            || history["program_sha256"] != p.artifact["sha256"]
        {
            return Err("closure history belongs to a different Program or schema".into());
        }
        let mut catalog = Self::parse(p, plan)?;
        if extra_units > catalog.limits.per_round {
            return Err("closure additions exceed per-round budget".into());
        }
        let original_total=catalog.limits.total;
        let capacity = catalog
            .units
            .len()
            .checked_add(extra_units)
            .ok_or("closure budget overflow")?;
        catalog.limits.total = catalog.limits.total.max(capacity);
        let events = array(&history["events"])?;
        let mut paths = Vec::<Vec<(Option<usize>, Entry)>>::new();
        let mut support = BTreeMap::<Vec<(Option<usize>, Entry)>, Vec<usize>>::new();
        let mut boundary_rejections = 0;
        for (index, event) in events.iter().enumerate() {
            let entry: Entry =
                serde_json::from_value(event["entry"].clone()).map_err(|e| e.to_string())?;
            if entry.0 >= p.rules.len() || entry.1.is_some_and(|pivot| pivot >= p.rules[entry.0].query.len()) {
                return Err("history entry is outside the source rule query".into());
            }
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
            // A newly observed producer must not hide a previously useful
            // suffix. These candidate supports overlap and are never summed
            // as applications or saved work.
            for start in 0..path.len().saturating_sub(1) {
                let mut suffix=path[start..].to_vec();
                suffix[0].0=None;
                support.entry(suffix).or_default().push(index);
            }
            paths.push(path);
        }
        let mut ranked = support
            .into_iter()
            .filter(|(_, events)| events.len() as u64 >= catalog.limits.support)
            .collect::<Vec<_>>();
        ranked.sort_by(|a, b| b.1.len().cmp(&a.1.len()).then(a.0.cmp(&b.0)));
        let lower=|catalog:&Catalog| crate::result_handoff::Switch::build(p,
            catalog.units.iter().map(|u|u.path.as_ref()),&catalog.leaves,true,true,true,true,true);
        let mut executable=None;
        let mut lowered_catalogs=0;
        let mut redundant=vec![];
        let mut selected = vec![];
        let mut added = 0;
        let mut guarded = 0;
        let mut unsupported = 0;
        let mut budget_rejections = 0;
        for (path, supporting_events) in ranked {
            let visits=supporting_events.len();
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
            let mut added_root=false;
            let mut left=if let Some(&id)=trial.leaves.get(&path[0].1) {id}
            else if let (rule,None)=path[0].1 {
                if rule>=p.rules.len() {unsupported+=1;continue;}
                let id=trial.units.len();
                trial.units.push(Unit {path:vec![(None,(rule,None))].into_boxed_slice()});
                trial.leaves.insert((rule,None),id);
                added_root=true;
                id
            } else {unsupported+=1;continue;};
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
            let new_units=joins.len()+usize::from(added_root);
            if added + new_units > extra_units {
                budget_rejections += 1;
                continue;
            }
            let lowered=(new_units!=0).then(|| {lowered_catalogs+=1;lower(&trial)});
            if let Some(lowered)=&lowered {
                let previous=executable.get_or_insert_with(|| {lowered_catalogs+=1;lower(&catalog)});
                if previous.transfer_signature(&path)==lowered.transfer_signature(&path) {
                    redundant.push(json!({"source_path":path,"support":visits,
                        "avoided_units":new_units,"reason":"existing-suffix-has-same-terminal-transfer"}));
                    continue;
                }
                // A suffix can differ in isolation yet never win at its actual
                // observed entries: a longer compiled prefix may already own
                // all of these transitions. Do not charge its marginal support
                // as new dispatch coverage. This is profile-guided admission,
                // not a proof of permanent semantic domination.
                let old_states=observed_states(previous,events)?;
                let new_states=observed_states(lowered,events)?;
                if supporting_events.iter().all(|&event|
                    previous.signature_at(old_states[event])==lowered.signature_at(new_states[event])) {
                    redundant.push(json!({"source_path":path,"support":visits,
                        "avoided_units":new_units,"reason":"actual-ancestry-already-has-same-terminal-transfer"}));
                    continue;
                }
            }
            if let Some(lowered)=lowered {executable=Some(lowered);}
            added += new_units;
            selected.push(json!({"unit":left,"support":visits,"kind":proof["kind"],
                "added_prefixes":joins.len(),"added_roots":usize::from(added_root),"source_path":path}));
            catalog = trial;
        }
        catalog.limits.total=original_total.max(catalog.units.len());
        let remap=encode_catalog(p,plan,&catalog)?;
        for row in &mut selected {
            let old=row["unit"].as_u64().unwrap() as usize;
            row["unit"]=json!(remap[&old]);
        }
        // Lower only this directory. No speculative structural expansion.
        Self::emit_policy(p, plan, true, true, true, true, true, false, None)?;
        plan["closure_selection"] = json!({"schema":"eggfuse-history-closure-selection/v1",
            "history_program":history["program_sha256"],"selected":selected,"added_units":added,
            "redundant_terminal_transfers":redundant,"admission_lowerings":lowered_catalogs,
            "boundary_rejections":boundary_rejections,"guarded_paths":guarded,
            "unsupported_paths":unsupported,"budget_rejections":budget_rejections,
            "scope":"history selects routes; existing typed result-switch rechecks executable lowering; not measured savings"});
        Ok(())
    }
}

/// Producer leaves precede joins in the portable format. Adding one must rebase
/// *all* old joins, not silently reinterpret their positional ids. Paths remain
/// authoritative and are checked again by the ordinary catalog parser.
fn encode_catalog(p:&Program,plan:&mut J,catalog:&Catalog)->Result<BTreeMap<Id,Id>> {
    let roots=catalog.leaves.keys().filter_map(|&(rule,pivot)|pivot.is_none().then_some(rule)).collect::<Vec<_>>();
    let seed=Catalog::seed_with_roots(p,catalog.limits,&roots)?;
    let mut raw=plan.clone();
    for field in ["schema","recipe","seed","limits","joins"] {raw[field]=seed[field].clone();}
    if roots.is_empty() {raw.as_object_mut().unwrap().remove("producer_roots");}
    else {raw["producer_roots"]=json!(roots);}
    for field in ["rhs_handoffs","state_plan","completion"] {raw.as_object_mut().unwrap().remove(field);}
    let matched=catalog.matched_entries.iter().flat_map(|(&r,atoms)|atoms.iter().map(move |&a|(r,a))).collect::<Vec<_>>();
    if matched.is_empty() {raw.as_object_mut().unwrap().remove("matched_entries");}
    else {raw["matched_entries"]=json!(matched);}
    let seeded=Catalog::parse(p,&raw)?;
    let mut remap=catalog.leaves.iter().map(|(entry,&old)|(old,seeded.leaves[entry])).collect::<BTreeMap<_,_>>();
    let mut joins=catalog.jumps.iter().map(|(join,&target)|(target,*join)).collect::<Vec<_>>();
    joins.sort_by_key(|&(target,_)|target);
    for (old,join) in joins {
        let mapped=Join {left:*remap.get(&join.left).ok_or("closure prefix mapping missing")?,
            right:*remap.get(&join.right).ok_or("closure consumer mapping missing")?,output:join.output};
        let next=remap.len();
        remap.insert(old,next);
        raw["joins"].as_array_mut().unwrap().push(json!(mapped));
    }
    if let Some(extensions)=raw.get_mut("completion_extensions").and_then(J::as_array_mut) {
        for extension in extensions {
            for side in ["from","to"] {
                let mut join:Join=serde_json::from_value(extension[side].clone()).map_err(|e|e.to_string())?;
                join.left=*remap.get(&join.left).ok_or("closure provenance prefix missing")?;
                join.right=*remap.get(&join.right).ok_or("closure provenance consumer missing")?;
                extension[side]=json!(join);
            }
        }
    }
    let checked=Catalog::parse(p,&raw)?;
    if remap.len()!=catalog.units.len() || remap.iter().any(|(&old,&new)|catalog.units[old].path!=checked.units[new].path) {
        return Err("closure reindex changed a source path".into());
    }
    *plan=raw;
    Ok(remap)
}

fn observed_states(switch:&crate::result_handoff::Switch, events:&[J])->Result<Vec<usize>> {
    if !switch.enabled() {return Err("history dispatch requires an installed switch".into());}
    let mut states=Vec::with_capacity(events.len());
    for (index,event) in events.iter().enumerate() {
        let entry:Entry=serde_json::from_value(event["entry"].clone()).map_err(|e|e.to_string())?;
        let parent:Option<usize>=serde_json::from_value(event["parent"].clone()).map_err(|e|e.to_string())?;
        let before=if let Some(parent)=parent {
            if parent>=index {return Err("history ancestry must point backwards".into());}
            states[parent]
        } else {0};
        let output=event["output"].as_u64().ok_or("history output missing")? as usize;
        states.push(switch.observe_advance(before,output,entry));
    }
    Ok(states)
}
