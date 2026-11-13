//! Passive RHS coverage before execution, including applies with no births.
use super::*;

#[derive(Default, Serialize)]
struct Counts {
    applications: u64,
    covered_prefix_ops: u64,
    rhs_ops: u64,
    query_atoms: u64,
    prefix_copy_ops: u64,
    prefix_static_alias_ops: u64,
    prefix_remaining_effect_ops: u64,
}
// Static positions only: no instance/eclass/value IDs survive observation.
type Sites = Vec<(usize, usize, u32)>;
#[derive(Default)]
pub(super) struct Trace {
    witnesses: BTreeMap<(usize, usize, Vec<usize>, Sites, Sites, bool), u64>,
    rows: BTreeMap<(usize, Option<usize>, bool, &'static str), Counts>,
    component_checks: u64,
    fact_checks: u64,
}
impl Trace {
    pub(super) fn report(&self) -> J {
        let rows = self
            .rows
            .iter()
            .map(|(&(rule, shape, cross_epoch, reason), counts)| {
                json!({"rule":rule,"shape":shape,"cross_epoch":cross_epoch,
                "outcome":reason,"counts":counts})
            })
            .collect::<Vec<_>>();
        let witnesses = self.witnesses.iter().map(|((rule,shape,codes,anchors,results,full),applications)|
            json!({"rule":rule,"shape":shape,"frame_codes":codes,"query_sites":anchors,"rhs_sites":results,
                "applications":applications,"coverage":if *full {"full_rhs"} else {"checked_prefix"}})).collect::<Vec<_>>();
        // Compatibility projection of the same recipes, not a second trace.
        let mut paths=BTreeMap::<(usize,usize,Sites,Sites),u64>::new();
        for ((rule,shape,_,anchors,sites,_),applications) in &self.witnesses {
            *paths.entry((*rule,*shape,sites.clone(),anchors.clone())).or_default()+=applications;
        }
        let paths=paths.into_iter().map(|((rule,shape,sites,anchors),applications)|json!({"rule":rule,"shape":shape,"constructor_positions":sites,"query_positions":anchors,"applications":applications})).collect::<Vec<_>>();
        json!({"rows":rows,"witness_recipes":witnesses,"witness_paths":paths,
            "witness_path_scope":"projection of observed full RHS and checked-prefix recipes; positions contain no instance IDs and do not alone prove executable replacement",
            "witness_contract":"positions are [query atom or RHS operation, component frame, fact operation]; only local matched receipts are listed; full query and dynamic key/visibility obligations remain authoritative; observations are not static proofs",
            "component_checks":self.component_checks,"fact_checks":self.fact_checks,
            "scope":"one observation per actual apply entry; rhs_covered means current matched RHS effects already witnessed inside one live Cell component",
            "limitations":"not a saturation certificate for all matches; query elimination, delta ownership, audit replacement and future invalidation still require compilation; unsupported effects are not skippable; no saved work claimed"})
    }
}
fn argument(arg: &Arg, values: &BTreeMap<usize, Value>, parents: &Parents) -> Option<Value> {
    Some(canon(
        match arg {
            Arg::Slot(s) => values.get(s)?,
            Arg::Literal(v) => v,
        },
        parents,
    ))
}
impl Graph {
    pub(crate) fn observe_saturated_apply(
        &mut self,
        rid: usize,
        binding: &crate::cell::Instance,
        pending_peers: bool,
    ) {
        let Some(owner) = &self.ownership else {
            return;
        };
        if owner.composition.catalog_trace.is_none() {
            return;
        }
        let mut components = BTreeSet::new();
        for atom in 0..self.program.rules[rid].query.len() {
            if let Some(Dependency::Fact(f)) = binding.known.receipt(atom) {
                if let Some(frame) = owner.composition.frames.get(&self.cells, &f.cell) {
                    components.insert(frame.component);
                }
            }
        }
        let rule = &self.program.rules[rid];
        let ops = &self.program.templates[rule.template].ops;
        let mut best = (None, false, "no_local_component", 0);
        let mut checks = 0;
        let mut witness_recipes = Vec::new();
        let mut fact_checks = 0;
        if pending_peers || !owner.pending.is_empty() {
            best.2 = "pending_completion";
        } else {
            if components.is_empty() {
                let empty = Component {
                    shape: 0,
                    frames: Default::default(),
                    signals: vec![],
                };
                let (prefix, reason, _, _) =
                    self.covered_rhs(&empty, ops, &rule.inputs, &binding.values);
                best.3 = prefix;
                best.2 = if reason == "rhs_covered" {
                    "rhs_covered_by_inputs"
                } else if reason == "missing_local_constructor" {
                    "no_local_component"
                } else {
                    reason
                };
            }
            for id in components {
                let Some(component) = owner
                    .composition
                    .components
                    .get(id as usize)
                    .and_then(Option::as_ref)
                else {
                    continue;
                };
                checks += 1;
                let (prefix, reason, visited, results) =
                    self.covered_rhs(component, ops, &rule.inputs, &binding.values);
                fact_checks += visited;
                let cross = component.frames.iter().any(|id| {
                    self.cells
                        .cell_metadata(*id)
                        .is_some_and(|c| c.started_epoch != self.epoch)
                });
                if best.0.is_none() || prefix > best.3 || reason == "rhs_covered" {
                    best = (Some(component.shape), cross, reason, prefix);
                }
                // The successfully checked prefix remains useful even when a
                // later operation needs execution. Routes replace individual
                // lookups; this never certifies the unobserved suffix.
                if !results.is_empty() {
                    let anchors = (0..rule.query.len()).filter_map(|atom| {
                        let Dependency::Fact(f) = binding.known.receipt(atom)? else { return None; };
                        let frame = component.frames.iter().position(|id| *id == f.cell)?;
                        Some((atom, frame, f.op))
                    }).collect::<Sites>();
                    let codes = component.frames.iter().map(|id| owner.composition.frames.at(&self.cells, id).code).collect();
                    witness_recipes.push((rid, component.shape, codes, anchors, results, reason=="rhs_covered"));
                }
                if reason == "rhs_covered" { break; }
            }
        }
        let trace = &mut self
            .ownership
            .as_mut()
            .unwrap()
            .composition
            .catalog_trace
            .as_mut()
            .unwrap()
            .saturation;
        for recipe in witness_recipes {
            *trace.witnesses.entry(recipe).or_default() += 1;
        }
        trace.component_checks += checks;
        trace.fact_checks += fact_checks;
        let counts = trace.rows.entry((rid, best.0, best.1, best.2)).or_default();
        counts.applications += 1;
        counts.covered_prefix_ops += best.3 as u64;
        counts.rhs_ops += ops.len() as u64;
        counts.query_atoms += rule.query.len() as u64;
        for (op, instruction) in ops.iter().enumerate().take(best.3) {
            if matches!(instruction, Op::Copy(..)) {
                counts.prefix_copy_ops += 1;
            } else if self.program.known_results.static_skip.get(rid)
                .and_then(|s|s.get(op)) == Some(&true) {
                counts.prefix_static_alias_ops += 1;
            } else {
                counts.prefix_remaining_effect_ops += 1;
            }
        }
    }
    fn covered_rhs(
        &self,
        component: &Component,
        ops: &[Op],
        inputs: &[usize],
        input: &crate::slots::Slots,
    ) -> (usize, &'static str, u64, Sites) {
        // Proof scratch only. Exclude prepared RHS outputs: those are not
        // evidence that their effects already existed before this application.
        let mut values = BTreeMap::new();
        let mut sites = Vec::new();
        for slot in inputs {
            let Some(value) = input.get(slot) else {
                return (0, "missing_input", 0, sites);
            };
            values.insert(*slot, canon(value, &self.parents));
        }
        let mut visits = 0;
        for (index, op) in ops.iter().enumerate() {
            let reason = match op {
                Op::Copy(dst, arg) => match argument(arg, &values, &self.parents) {
                    Some(v) => {
                        values.insert(*dst, v);
                        None
                    }
                    None => Some("unbound_operand"),
                },
                Op::Union(a, b) => match (
                    argument(a, &values, &self.parents),
                    argument(b, &values, &self.parents),
                ) {
                    (Some(Value::Eq(a)), Some(Value::Eq(b))) if a == b => None,
                    (Some(Value::Eq(_)), Some(Value::Eq(_))) => Some("nontrivial_union"),
                    _ => Some("unproved_union_operand"),
                },
                Op::Let(dst, Call::Table(table), args)
                    if self.program.tables[*table].constructor
                        && self.program.tables[*table].virtual_fact =>
                {
                    let Some(key) = args
                        .iter()
                        .map(|a| argument(a, &values, &self.parents))
                        .collect::<Option<Vec<_>>>()
                    else {
                        return (index, "unbound_operand", visits, sites);
                    };
                    let mut found = None;
                    'frames: for (frame, id) in component.frames.iter().enumerate() {
                        for (fact, state) in self.cells.fact_states(*id) {
                            if !state.owned || state.hidden {
                                continue;
                            }
                            visits += 1;
                            let Ok(Some(row)) = self.fact(fact) else {
                                continue;
                            };
                            if row.table == *table
                                && row.values.len() == key.len() + 1
                                && row
                                    .values
                                    .iter()
                                    .zip(&key)
                                    .all(|(a, b)| canon(a, &self.parents) == *b)
                            {
                                found = row.values.last().map(|v| (canon(v, &self.parents), frame, fact.op));
                                break 'frames;
                            }
                        }
                    }
                    match found {
                        Some((v, frame, operation)) => {
                            sites.push((index, frame, operation));
                            values.insert(*dst, v);
                            None
                        }
                        None => Some("missing_local_constructor"),
                    }
                }
                Op::Let(_, Call::Table(_), _) => Some("mutable_or_uncovered_read"),
                Op::Let(_, Call::Primitive(..), _) => Some("primitive_proof_missing"),
                Op::Set(..) => Some("write_effect"),
                Op::Hide(..) => Some("visibility_effect"),
                Op::Panic => Some("failure_effect"),
            };
            if let Some(reason) = reason {
                return (index, reason, visits, sites);
            }
        }
        (ops.len(), "rhs_covered", visits, sites)
    }
}
