//! Bound proof for source RHSs made only of copies, scalar arithmetic, explicit
//! equality and constructor Set. Whole-table reads remain ready before probing.
//! It does not publish speculative writes or evaluate a custom merge.
use super::*;

impl Executor {
    pub(super) fn admit_pure_epoch(&mut self, patch: &StagePatch) -> Result<bool> {
        let state = self.completion.as_ref().unwrap();
        if !state.pure_epochs {
            return Ok(false);
        }
        let plan = self.graph.program.completion_plan.as_ref().unwrap().clone();
        let forecast = state
            .forecast
            .as_ref()
            .ok_or("missing pure-epoch forecast")?;
        if forecast.has_ordered_tasks() {
            return Ok(false);
        }
        let mut checks = 0;
        let mut rules = 0;
        for (rid, _) in &patch.groups {
            rules += 1;
            let Some(writes) = &plan.rule_demands[*rid].pure_writes else {
                let stats = &mut self.completion.as_mut().unwrap().stats;
                stats.readiness_dependency_checks += checks;
                stats.bound_rhs_rule_checks += rules;
                return Ok(false);
            };
            let (ready, cost) = forecast.readiness(writes);
            checks += cost;
            if !ready {
                let stats = &mut self.completion.as_mut().unwrap().stats;
                stats.readiness_dependency_checks += checks;
                stats.bound_rhs_rule_checks += rules;
                return Ok(false);
            }
        }
        self.completion
            .as_mut()
            .unwrap()
            .stats
            .readiness_dependency_checks += checks;
        self.completion
            .as_mut()
            .unwrap()
            .stats
            .bound_rhs_rule_checks += rules;
        let mut seeds = smallvec::SmallVec::<[u64; 16]>::new();
        let mut all_noop = true;
        let mut ops = 0;
        let mut reads = 0;
        let mut slots = 0;
        let mut growths = 0;
        // Pending unions are not committed between bindings in a source Run.
        // We collect every Set output even for absent keys: two earlier/later
        // births of the same key can union those outputs when the RHS executes.
        let mut valid = true;
        'bindings: for (rid, binding) in patch.iter() {
            let template = &self.graph.program.templates[self.graph.program.rules[*rid].template];
            let mut values = binding.values.clone();
            slots += values.len() as u64;
            growths += u64::from(!values.is_empty());
            for op in template.ops.iter() {
                ops += 1;
                let arg = |a: &Arg| -> Option<Value> {
                    Some(canon(
                        match a {
                            Arg::Slot(s) => values.get(s)?,
                            Arg::Literal(v) => v,
                        },
                        &self.graph.parents,
                    ))
                };
                let mut record = |v: &Value| {
                    if let Value::Eq(root) = v {
                        let before = seeds.capacity();
                        seeds.push(*root);
                        growths += u64::from(before != seeds.capacity());
                    }
                };
                match op {
                    Op::Copy(dst, a) => {
                        let Some(v) = arg(a) else {
                            valid = false;
                            break 'bindings;
                        };
                        let before = values.capacity();
                        values.insert(*dst, v);
                        slots += 1;
                        growths += u64::from(before != values.capacity());
                    }
                    Op::Let(dst, Call::Primitive(name, sort), args) => {
                        let Some(args) = args
                            .iter()
                            .map(arg)
                            .collect::<Option<smallvec::SmallVec<[Value; 2]>>>()
                        else {
                            valid = false;
                            break 'bindings;
                        };
                        let Ok(Some(v)) =
                            value::primitive(name, &args, sort, self.graph.program.key_nodes())
                        else {
                            valid = false;
                            break 'bindings;
                        };
                        let before = values.capacity();
                        values.insert(*dst, v);
                        slots += 1;
                        growths += u64::from(before != values.capacity());
                    }
                    Op::Union(a, b) => {
                        let (Some(a), Some(b)) = (arg(a), arg(b)) else {
                            valid = false;
                            break 'bindings;
                        };
                        all_noop &= a == b;
                        record(&a);
                        record(&b);
                    }
                    Op::Set(t, key, value) => {
                        let Some(key) = key
                            .iter()
                            .map(arg)
                            .collect::<Option<smallvec::SmallVec<[Value; 4]>>>()
                        else {
                            valid = false;
                            break 'bindings;
                        };
                        let Some(value) = arg(value) else {
                            valid = false;
                            break 'bindings;
                        };
                        for v in &key {
                            record(v);
                        }
                        record(&value);
                        reads += 1;
                        let old = self.graph.lookup_canonical(*t, &key)?;
                        all_noop &= old
                            .as_ref()
                            .is_some_and(|r| r.values.last() == Some(&value));
                        if let Some(old) = old {
                            record(old.values.last().unwrap());
                        }
                    }
                    _ => return Err("invalid checked pure-epoch program".into()),
                }
            }
        }
        let stats = &mut self.completion.as_mut().unwrap().stats;
        stats.bound_rhs_attempts += 1;
        stats.bound_rhs_ops += ops;
        stats.bound_rhs_key_reads += reads;
        stats.bound_rhs_value_slots += slots;
        stats.bound_rhs_scratch_growths += growths;
        if !valid {
            return Ok(false);
        }
        let accepted = all_noop || self.graph.pure_epoch_closure(&seeds)?;
        if accepted {
            let stats = &mut self.completion.as_mut().unwrap().stats;
            stats.bound_rhs_accepts += 1;
            stats.bound_rhs_noop_accepts += u64::from(all_noop);
            stats.bound_rhs_bindings += patch.len as u64;
        }
        Ok(accepted)
    }
}
