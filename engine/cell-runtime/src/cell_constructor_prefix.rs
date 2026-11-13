//! Continue one Cell through existing, permanent constructor results. Its Eq
//! values occupy the original slots, but become source results only after the
//! original Run certificate is checked. An invalid prefix clears those slots
//! before any allocation or source effect can observe them.
use super::*;
use crate::{graph::Graph, slots::Slots};

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) struct Step {
    operation: usize,
    table: usize,
    destination: usize,
    aliases: usize,
    ready: usize,
    owner_entry: bool,
    pub(super) keys: Vec<Arg>,
}
impl Plan {
    pub(crate) fn compile_prefix(&mut self, p: &Program, rule: usize, permanent: &[bool],
        unit_storage: impl Fn(usize)->bool, owner_entries: bool) {
        // Additional per-instruction audit effects retain their ordinary host.
        if cfg!(feature="structural-depth") || p.writes.get(rule).is_some_and(Option::is_some) { return; }
        let cell = Definition::new(p, rule).expect("checked Cell");
        let execution = &p.executions[rule];
        let mut ready = cell.rule.inputs.iter().copied().collect::<std::collections::BTreeSet<_>>();
        let mut steps = vec![];
        let mut scalar_ready = vec![];
        let mut aliases = 0;
        for (operation, instruction) in cell.template.ops.iter().enumerate() {
            if p.known_results.static_skip[rule][operation] { aliases += 1; continue; }
            if matches!(instruction, Op::Copy(..)) { continue; }
            if let Op::Let(destination, Call::Primitive(..), _) = instruction
                && (operation < execution.segments[0].end
                    || execution.input_ready.binary_search(&operation).is_ok()) {
                // Typed input-derived operations have already run in these
                // same slots. Presence still needs checking: a failed scalar
                // must stop before any later constructor is certified.
                scalar_ready.push(*destination);
                ready.insert(*destination);
                continue;
            }
            if operation < self.operation { break; }
            let Op::Let(destination,Call::Table(table),args) = instruction else { break; };
            if !p.tables[*table].virtual_fact || !p.tables[*table].constructor || !permanent[*table] { break; }
            let keys: Vec<_> = args.iter().map(|a|cell.value(a)).collect();
            if keys.iter().any(|a| matches!(a,Arg::Slot(s) if !ready.contains(s)
                || cell.template.defs.get(s).is_some_and(|&at|at>=operation))) { break; }
            ready.insert(*destination);
            let owner_entry=owner_entries && p.cell_ownership.markers[cell.rule.template].program.fields
                .get(operation).and_then(|fields|fields.last()).is_some_and(Option::is_some);
            steps.push(Step { operation, table:*table, destination:*destination, aliases, owner_entry,
                ready:scalar_ready.len(), keys });
        }
        let units = steps.last().and_then(|last|
            super::super::unit_prepare::Plan::after_prefix(p,rule,last.operation+1,unit_storage));
        if steps.len() > 1 || units.is_some() {
            scalar_ready.truncate(steps.last().unwrap().ready);
            self.scalar_ready = scalar_ready;
            self.prefix = steps;
            self.owner_entries = owner_entries;
            self.units = units.map(Box::new);
        }
    }
    pub(crate) fn prefix_width(&self) -> usize { self.prefix.len() }
    pub(crate) fn entry_operations(&self) -> impl Iterator<Item=usize> + '_ {
        self.prefix.iter().filter(|s|s.owner_entry).map(|s|s.operation)
    }
    pub(crate) fn prepare_units(&self, instance: &mut Instance,
        reads: Option<&crate::graph::query_reads::QueryReads<'_>>,
        counts: &mut super::super::unit_prepare::Counts) {
        let Some(plan) = &self.units else { return; };
        if !matches!(instance.constructor, Prepared::Prefix(_)) || instance.prepared != self.prefix.len() { return; }
        let before = (counts.rows, counts.existing);
        let units = plan.rows(instance, reads, counts);
        if units.len() == 0 { return; }
        let Prepared::Prefix(results) = std::mem::take(&mut instance.constructor) else { unreachable!() };
        counts.prefix_instances += 1;
        counts.prefix_rows += counts.rows - before.0;
        counts.prefix_existing += counts.existing - before.1;
        counts.continuation_bytes += std::mem::size_of::<PrefixUnits>() as u64;
        instance.constructor = Prepared::PrefixUnits(Box::new(PrefixUnits { results, units }));
    }
    pub(super) fn prepare_prefix(&self, instance: &mut Instance,
        reads: Option<&crate::graph::query_reads::QueryReads<'_>>,
        scratch: &mut crate::graph::query_reads::Scratch,
        work: &mut crate::graph::query_reads::Work, counts: &mut Counts) {
        let Some(reads) = reads else { counts.unavailable += 1; return; };
        let capacity = instance.values.capacity_bytes();
        let mut results = Vec::new();
        let mut completed = 0;
        let mut ready = 0;
        for step in &self.prefix {
            let mut missing = false;
            for slot in &self.scalar_ready[ready..step.ready] {
                counts.prefix_scalar_checks += 1;
                if !instance.values.contains_key(slot) { missing = true; break; }
            }
            if missing { counts.prefix_scalar_stops += 1; break; }
            ready = step.ready;
            if !reads.constructor_available(step.table) { counts.unavailable += 1; break; }
            let mut key = smallvec::SmallVec::<[Value;4]>::new();
            for arg in &step.keys {
                let value = match arg {
                    Arg::Literal(v) => v,
                    Arg::Slot(s) => match instance.values.get(s) {
                        Some(v) => v,
                        None => { counts.missing_inputs += 1; break; },
                    },
                };
                key.push(canon(value,reads.parents)); counts.key_fields += 1;
            }
            if key.len()!=step.keys.len() { break; }
            counts.key_spills += u64::from(key.spilled());
            counts.lookups += 1;
            match reads.point(step.table,&key,scratch,work) {
                Ok(Some((value,_,Dependency::Fact(witness)))) => {
                    if completed == 0 {
                        instance.values.reserve_exact(self.prefix.len());
                    }
                    debug_assert!(!instance.values.contains_key(&step.destination));
                    instance.values.insert(step.destination,value);
                    counts.prefix_layout_checks += 1;
                    if let Some(layout) = &self.result_layout
                        && let Some(slot) = layout.index(step.operation) {
                        if results.is_empty() {
                            results.reserve_exact(layout.width());
                            results.resize(layout.width(), None);
                            counts.prefix_witness_growths += 1;
                            counts.prefix_witness_bytes += (results.capacity()*std::mem::size_of::<Option<Dependency>>()) as u64;
                            counts.prefix_result_initializations += results.len() as u64;
                        }
                        results[slot] = Some(Dependency::Fact(witness));
                        counts.result_writes += 1;
                    }
                    completed += 1;
                    counts.hits += 1; counts.prefix_slot_writes += 1;
                },
                Ok(None) => { counts.misses += 1; break; },
                _ => { counts.unavailable += 1; break; },
            }
        }
        let growth = instance.values.capacity_bytes().saturating_sub(capacity);
        counts.prefix_slot_growths += u64::from(growth!=0);
        counts.prefix_capacity_bytes += growth as u64;
        if completed != 0 {
            counts.prefix_instances += 1;
            instance.prepared = completed;
            counts.prefix_progress_writes += 1;
            instance.constructor = Prepared::Prefix(results);
        }
    }
}

impl Graph {
    /// Only this checked recipe may turn prepared Eq slots into source results.
    /// Source effects have not begun, and the prefix contains no graph mutation.
    pub(crate) fn seal_constructor_prefix(&mut self, rule: usize, values: &mut Slots,
        prepared: &mut usize, results: Vec<Option<Dependency>>,
        first: &mut Option<FactRef>, units: &mut super::super::unit_prepare::Prepared)
        -> Option<(usize, Vec<Option<Dependency>>)> {
        let count = std::mem::replace(prepared,0);
        let plan = self.program.executions[rule].constructor.as_ref().expect("prepared prefix plan");
        let steps = &plan.prefix[..count];
        assert!(!steps.is_empty(), "prepared prefix has completed steps");
        self.stats.constructor_prefix_checks += 1;
        let mut checks = 0;
        // Training can be enabled after execution planning but before Run one.
        // Such a late demand cannot use witnesses the worker did not retain.
        let valid = (!self.needs_ownership_results(rule) || plan.owner_entries)
            && self.sealed_generation == Some(self.stats.unions) && steps.iter().all(|step| {
            checks += 1;
            self.constructor_prefix_table_ready(step.table)
        });
        self.stats.constructor_prefix_table_checks += checks;
        if valid {
            if plan.owner_entries {
                for index in 0..count {
                    let plan=self.program.executions[rule].constructor.as_ref().unwrap();
                    let step=&plan.prefix[index];
                    if !step.owner_entry {continue;}
                    let operation=step.operation;
                    let slot=plan.result_layout.as_ref().and_then(|layout|layout.index(operation))
                        .expect("compiled ownership result slot");
                    let witness=results[slot].expect("successful prepared constructor result");
                    self.stats.constructor_prefix_entry_reads+=1;
                    self.composition_prepared_result_entry(rule,operation,witness);
                }
            }
            Some((count, results))
        } else {
            self.stats.constructor_prefix_rejected += 1;
            let witnesses = units.witnesses();
            self.stats.unit_prepared_prefix_discarded += (units.len() - witnesses) as u64;
            self.stats.unit_prepared_prefix_witness_discarded += witnesses as u64;
            *units = Default::default();
            // Eq evidence may expire without invalidating captured scalars.
            // The initial segment had to succeed before the first prefix step.
            *prepared = self.program.executions[rule].segments[0].end;
            for step in steps {
                values.remove(&step.destination);
                self.stats.constructor_prefix_discarded_slots += 1;
            }
            // Reuse a demanded first result if present. Undemanded witnesses
            // are no longer retained solely for this rare invalidation path.
            *first = plan.result_layout.as_ref().and_then(|p|p.index(plan.operation))
                .and_then(|i|results.get(i)).copied().flatten().and_then(|w|match w {
                    Dependency::Fact(w) => Some(w), _ => None,
                });
            None
        }
    }
    pub(crate) fn consume_constructor_prefix(&mut self, rule: usize,
        count: usize, lazy: bool) -> usize {
        let steps = &self.program.executions[rule].constructor.as_ref().unwrap().prefix[..count];
        let end = steps.last().unwrap().operation + 1;
        self.stats.constructor_prefix_frames += 1;
        self.stats.constructor_prefix_operations += count as u64;
        self.stats.constructor_requests += count as u64;
        self.stats.constructor_reused += count as u64;
        // The consumed prefix includes existing scalar work. Account it once
        // here because the ordinary source interpreter no longer visits it.
        let head = self.program.executions[rule].segments[0].local_operations;
        self.stats.prepared_rhs_operations += head as u64;
        self.stats.prepared_rhs_later_operations += (steps.last().unwrap().ready - head) as u64;
        let aliases = steps.last().unwrap().aliases as u64;
        self.known_stats.static_eliminated += aliases;
        self.known_stats.avoided_lookups += aliases;
        if lazy { self.known_stats.lazy_prefix_eliminated += aliases; }
        end
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invalid_union_epoch_cannot_publish_any_prepared_composition_result() {
        for invalid in [false,true] {
            let mut g=super::super::tests::graph();
            let template=&mut g.program.templates[0];
            template.sorts.push(template.sorts[0].clone());
            template.defs.insert(2,1);
            std::sync::Arc::make_mut(&mut template.ops).push(Op::Let(2,Call::Table(0),vec![Arg::Slot(1)]));
            g.program.known_results.static_skip[0]=std::rc::Rc::new(vec![false;2]);
            g.program.executions[0]=crate::cell::execution::Plan::derive(&g.program.tables,&g.program.templates[0],&[0]);
            g.program.repair_ports=crate::graph::repair_ports::Plan::derive(&g.program);
            g.use_cell_ownership().unwrap();g.train_ownership_fragments().unwrap();
            let mut plan=Plan::derive(&g.program,0).unwrap();
            plan.compile_prefix(&g.program,0,&[true],|_|false,true);
            g.program.executions[0].constructor=Some(plan.clone());
            let effects=crate::cell::EffectPlan::compile(&g.program,0,&[],0,false);
            plan.result_layout=Some(effects.layout.clone());
            g.program.executions[0].constructor=Some(plan.clone());
            let producer=g.linked_slots(0,[(0,Value::Eq(9))].into_iter().collect(),None).unwrap();
            g.construct(producer,0,0,&[Arg::Slot(0)],1).unwrap();
            g.construct(producer,1,0,&[Arg::Slot(1)],2).unwrap();
            g.repair().unwrap();g.changes.clear();
            let mut instance=Instance::matched([(0,Value::Eq(9))].into_iter().collect(),Default::default(),0);
            plan.prepare(&mut instance,g.query_reads(&[],&mut 0).as_ref(),
                &mut Default::default(),&mut Default::default(),&mut Counts::default());
            assert_eq!(instance.prepared,2);
            g.sealed_generation=Some(g.stats.unions);
            if invalid {g.enqueue_union(Value::Eq(9),Value::Eq(7)).unwrap();g.repair().unwrap();}
            g.begin_owner_entry(0,Default::default());
            let Prepared::Prefix(results)=std::mem::take(&mut instance.constructor) else {panic!("worker prefix")};
            let prefix=g.seal_constructor_prefix(0,&mut instance.values,&mut instance.prepared,results,&mut None,&mut Default::default());
            assert_eq!(prefix.is_none(),invalid);
            let expected=if invalid {0}else{2};
            assert_eq!(g.stats.constructor_prefix_entry_reads,expected);
            assert_eq!(g.ownership_report()["stats"]["composition_result_writes"],expected);
            g.end_owner_entry();
        }
    }
    #[test]
    fn invalid_constructor_prefix_preserves_completed_scalar_slots_and_the_initial_source_position() {
        for invalid in [false,true] {
            let mut g = super::super::tests::graph();
            let template = &mut g.program.templates[0];
            template.sorts.push(template.sorts[0].clone());
            template.sorts.extend(vec![serde_json::json!({"kind":"i64"});2]);
            template.defs=[(3,0),(1,1),(4,2),(2,3)].into_iter().collect();
            template.ops=std::sync::Arc::new(vec![
                Op::Let(3,Call::Primitive("+".into(),"i64".into()),vec![Arg::Literal(Value::Int(2)),Arg::Literal(Value::Int(3))]),
                Op::Let(1,Call::Table(0),vec![Arg::Slot(0)]),
                Op::Let(4,Call::Primitive("*".into(),"i64".into()),vec![Arg::Slot(3),Arg::Literal(Value::Int(2))]),
                Op::Let(2,Call::Table(0),vec![Arg::Slot(1)]),
            ]);
            g.program.known_results.static_skip[0]=std::rc::Rc::new(vec![false;4]);
            g.program.executions[0]=crate::cell::execution::Plan::derive(&g.program.tables,&g.program.templates[0],&[0]);
            let mut plan=Plan::derive(&g.program,0).unwrap();
            plan.compile_prefix(&g.program,0,&[true], |_|false,false);
            assert_eq!(plan.prefix_width(),2);
            g.program.executions[0].constructor=Some(plan.clone());
            let producer=g.linked_slots(0,[(0,Value::Eq(9))].into_iter().collect(),None).unwrap();
            let first=g.construct(producer,1,0,&[Arg::Slot(0)],1).unwrap();
            let second=g.construct(producer,3,0,&[Arg::Slot(1)],2).unwrap();
            g.repair().unwrap();g.changes.clear();
            let mut instance=Instance::matched([(0,Value::Eq(9))].into_iter().collect(),Default::default(),0);
            g.program.executions[0].prepare(&g.program.templates[0],&mut instance,&mut Default::default());
            assert_eq!(instance.prepared,1);
            plan.prepare(&mut instance,g.query_reads(&[],&mut 0).as_ref(),
                &mut Default::default(),&mut Default::default(),&mut Counts::default());
            assert_eq!(instance.prepared,2,"constructor program progress shares the existing cursor");
            g.sealed_generation=Some(g.stats.unions);g.epoch=1;
            if invalid {g.enqueue_union(Value::Eq(9),Value::Eq(7)).unwrap();g.repair().unwrap();}
            let Prepared::Prefix(results)=std::mem::take(&mut instance.constructor) else {panic!("worker prefix")};
            let prefix=g.seal_constructor_prefix(0,&mut instance.values,&mut instance.prepared,results,&mut None,&mut Default::default());
            assert_eq!(instance.values.get(&3),Some(&Value::Int(5)));
            assert_eq!(instance.values.get(&4),Some(&Value::Int(10)));
            if invalid {
                assert!(prefix.is_none());
                assert_eq!(instance.prepared,1,"resume after the already completed initial scalar");
                assert!(!instance.values.contains_key(&1) && !instance.values.contains_key(&2));
            } else {
                assert_eq!(g.consume_constructor_prefix(0,prefix.unwrap().0,false),4);
                assert_eq!(instance.values.get(&1),Some(&first));
                assert_eq!(instance.values.get(&2),Some(&second));
                assert_eq!(g.stats.prepared_rhs_operations,1);
                assert_eq!(g.stats.prepared_rhs_later_operations,1);
            }
        }
    }

    #[test]
    fn invalid_run_or_visibility_evidence_clears_all_speculative_identities_before_source_allocation() {
        for change in ["same","union","delete"] {
            let mut p = super::super::tests::graph().program;
            p.tables.push(serde_json::from_value(serde_json::json!({
                "name":"Ticket","schema":[{"kind":"eq","name":"E"},{"kind":"Unit","name":"Unit"}],
                "constructor":false,"virtual_fact":false,"internal":false,"merge":{"var":"old"}
            })).unwrap());
            let template = &mut p.templates[0];
            template.sorts.push(template.sorts[0].clone());
            template.defs.insert(2,1);
            template.ops=std::sync::Arc::new(vec![Op::Let(1,Call::Table(0),vec![Arg::Slot(0)]),
                Op::Let(2,Call::Table(0),vec![Arg::Slot(1)]),
                Op::Set(1,vec![Arg::Slot(2)],Arg::Literal(Value::Int(0)))]);
            p.known_results.static_skip[0]=std::rc::Rc::new(vec![false;3]);
            p.executions[0]=crate::cell::execution::Plan::derive(&p.tables,&p.templates[0],&[0]);
            let mut g=Graph::new(p).unwrap();
            let mut plan=Plan::derive(&g.program,0).unwrap();
            plan.compile_prefix(&g.program,0,&[true,false], |_|true,false);
            assert_eq!(plan.prefix_width(),2);
            g.program.executions[0].constructor=Some(plan.clone());
            let producer=g.linked_slots(0,[(0,Value::Eq(9))].into_iter().collect(),None).unwrap();
            let first=g.construct(producer,0,0,&[Arg::Slot(0)],1).unwrap();
            let second=g.construct(producer,1,0,&[Arg::Slot(1)],2).unwrap();
            g.repair().unwrap();g.changes.clear();
            let mut instance=Instance::matched([(0,Value::Eq(9))].into_iter().collect(),Default::default(),0);
            plan.prepare(&mut instance,g.query_reads(&[],&mut 0).as_ref(),
                &mut Default::default(),&mut Default::default(),&mut Counts::default());
            let mut instance=rayon::ThreadPoolBuilder::new().num_threads(1).build().unwrap().install(move|| {
                plan.prepare_units(&mut instance,None,&mut Default::default());instance
            });
            assert_eq!(instance.values.get(&1),Some(&first));
            assert_eq!(instance.values.get(&2),Some(&second));
            g.sealed_generation=Some(g.stats.unions);g.epoch=1;
            match change {
                "union" => {g.enqueue_union(Value::Eq(9),Value::Eq(7)).unwrap();g.repair().unwrap();},
                "delete" => {assert!(g.hide(0,&[Value::Eq(9)],true).unwrap());},
                _ => (),
            }
            let Prepared::PrefixUnits(completed)=std::mem::take(&mut instance.constructor) else {panic!("worker prefix and actual Unit row")};
            let PrefixUnits { results,mut units }=*completed;
            assert_eq!(units.len(),1);
            let mut witness=None;
            let prefix=g.seal_constructor_prefix(0,&mut instance.values,&mut instance.prepared,results,&mut witness,&mut units);
            if change=="same" {
                let crate::cell::unit_prepare::Unit::Row {fields,..}=units.take(2).unwrap() else {panic!("prepared row")};
                assert_eq!(fields[0],second);
                assert_eq!(g.consume_constructor_prefix(0,prefix.unwrap().0,false),2);
                assert_eq!(instance.values.get(&1),Some(&first));
                assert_eq!(g.stats.constructor_prefix_operations,2);
            } else {
                assert!(prefix.is_none());
                assert_eq!(units.len(),0,"invalid identities must not survive in a dependent Unit row");
                assert_eq!(g.stats.unit_prepared_prefix_discarded,1);
                assert!(!instance.values.contains_key(&1) && !instance.values.contains_key(&2));
                let cell=g.begin_transient(0,instance.values,None).unwrap();
                assert!(witness.is_none(), "undemanded result has no extra retained witness");
                let actual=g.construct(cell,0,0,&[Arg::Slot(0)],1).unwrap();
                let next=g.construct(cell,1,0,&[Arg::Slot(1)],2).unwrap();
                if change=="delete" {assert_ne!(actual,first);assert_ne!(next,second);}
                assert_eq!(g.stats.constructor_prefix_discarded_slots,2);
            }
        }
    }
}
