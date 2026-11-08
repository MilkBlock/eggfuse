//! Bound proof for source RHSs made only of copies, scalar arithmetic, explicit
//! equality and constructor Set. Whole-table reads remain ready before probing.
//! It does not publish speculative writes or evaluate a custom merge.
use super::*;
use crate::graph::cell_ownership::completion::{Batch, Birth};

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
        let mut batch = Batch::default();
        let mut all_noop = true;
        let mut ops = 0;
        let mut reads = 0;
        let mut slots = 0;
        let mut growths = 0;
        let mut overlay_checks = 0;
        let mut budget_rejected = false;
        // Source unions commit after all bindings. This finite overlay therefore
        // uses the current exact keys, including births by earlier bindings.
        let mut valid = true;
        'bindings: for (rid, binding) in patch.iter() {
            let template = &self.graph.program.templates[self.graph.program.rules[*rid].template];
            let mut values = binding.values.clone();
            slots += values.len() as u64;
            growths += u64::from(!values.is_empty());
            for op in template.ops.iter() {
                if ops + overlay_checks >= 4096 {
                    budget_rejected = true;
                    valid = false;
                    break 'bindings;
                }
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
                let mut pair = |a: &Value, b: &Value| -> Result<()> {
                    let (Value::Eq(a), Value::Eq(b)) = (a, b) else {
                        return Err("pure-epoch union requires equality values".into());
                    };
                    if a != b {
                        let before = batch.pairs.capacity();
                        batch.pairs.push((*a, *b));
                        growths += u64::from(before != batch.pairs.capacity());
                    }
                    Ok(())
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
                        pair(&a, &b)?;
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
                        reads += 1;
                        let old = self.graph.lookup_canonical(*t, &key)?;
                        if let Some(old) = old {
                            let old = old.values.last().unwrap();
                            all_noop &= old == &value;
                            pair(old, &value)?;
                        } else {
                            all_noop = false;
                            let mut previous = None;
                            for birth in &batch.births {
                                if ops + overlay_checks >= 4096 {
                                    budget_rejected = true;
                                    valid = false;
                                    break 'bindings;
                                }
                                overlay_checks += 1;
                                if birth.table == *t && birth.key == key {
                                    previous = Some(birth.output);
                                    break;
                                }
                            }
                            if let Some(old) = previous {
                                pair(&Value::Eq(old), &value)?;
                            } else {
                                let Value::Eq(output) = value else {
                                    return Err(
                                        "pure-epoch constructor requires equality output".into()
                                    );
                                };
                                let before = batch.births.capacity();
                                batch.births.push(Birth {
                                    table: *t,
                                    key,
                                    output,
                                });
                                growths += u64::from(before != batch.births.capacity());
                            }
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
        stats.bound_rhs_overlay_checks += overlay_checks;
        stats.bound_rhs_source_pairs += batch.pairs.len() as u64;
        stats.bound_rhs_birth_sites += batch.births.len() as u64;
        stats.bound_rhs_budget_rejections += u64::from(budget_rejected);
        if !valid {
            return Ok(false);
        }
        let accepted = all_noop
            || self.graph.pure_epoch_closure(
                &batch,
                self.completion.as_ref().unwrap().forecast.as_ref().unwrap(),
            )?;
        if accepted {
            let stats = &mut self.completion.as_mut().unwrap().stats;
            stats.bound_rhs_accepts += 1;
            stats.bound_rhs_noop_accepts += u64::from(all_noop);
            stats.bound_rhs_bindings += patch.len as u64;
        }
        Ok(accepted)
    }
}
