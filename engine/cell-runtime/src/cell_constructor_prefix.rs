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
    pub(super) keys: Vec<Arg>,
}
impl Plan {
    pub(crate) fn compile_prefix(&mut self, p: &Program, rule: usize, permanent: &[bool]) {
        // Additional per-instruction audit effects retain their ordinary host.
        if cfg!(feature="structural-depth") || p.writes.get(rule).is_some_and(Option::is_some) { return; }
        let cell = Definition::new(p, rule).expect("checked Cell");
        // Only Copies precede this prefix. Scalar preparation and arbitrary
        // input-ready single-constructor probing keep their existing paths.
        if !cell.template.ops[..self.operation].iter().all(|o| matches!(o,Op::Copy(..))) { return; }
        let mut ready = cell.rule.inputs.iter().copied().collect::<std::collections::BTreeSet<_>>();
        let mut steps = vec![];
        let mut aliases = 0;
        for (operation, instruction) in cell.template.ops.iter().enumerate().skip(self.operation) {
            if p.known_results.static_skip[rule][operation] { aliases += 1; continue; }
            if matches!(instruction, Op::Copy(..)) { continue; }
            let Op::Let(destination,Call::Table(table),args) = instruction else { break; };
            if !p.tables[*table].virtual_fact || !p.tables[*table].constructor || !permanent[*table] { break; }
            let keys: Vec<_> = args.iter().map(|a|cell.value(a)).collect();
            if keys.iter().any(|a| matches!(a,Arg::Slot(s) if !ready.contains(s)
                || cell.template.defs.get(s).is_some_and(|&at|at>=operation))) { break; }
            ready.insert(*destination);
            steps.push(Step { operation, table:*table, destination:*destination, aliases, keys });
        }
        if steps.len() > 1 { self.prefix = steps; }
    }
    pub(crate) fn prefix_width(&self) -> usize { self.prefix.len() }
    pub(super) fn prepare_prefix(&self, instance: &mut Instance,
        reads: Option<&crate::graph::query_reads::QueryReads<'_>>,
        scratch: &mut crate::graph::query_reads::Scratch,
        work: &mut crate::graph::query_reads::Work, counts: &mut Counts) {
        let Some(reads) = reads else { counts.unavailable += 1; return; };
        let capacity = instance.values.capacity_bytes();
        let mut results = Vec::new();
        for step in &self.prefix {
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
                    if results.is_empty() {
                        results.reserve_exact(self.prefix.len());
                        counts.prefix_witness_growths += 1;
                        counts.prefix_witness_bytes += (results.capacity()*std::mem::size_of::<FactRef>()) as u64;
                        instance.values.reserve_exact(self.prefix.len());
                    }
                    debug_assert!(!instance.values.contains_key(&step.destination));
                    instance.values.insert(step.destination,value);
                    results.push(witness);
                    counts.hits += 1; counts.result_writes += 1; counts.prefix_slot_writes += 1;
                },
                Ok(None) => { counts.misses += 1; break; },
                _ => { counts.unavailable += 1; break; },
            }
        }
        let growth = instance.values.capacity_bytes().saturating_sub(capacity);
        counts.prefix_slot_growths += u64::from(growth!=0);
        counts.prefix_capacity_bytes += growth as u64;
        if !results.is_empty() {
            counts.prefix_instances += 1;
            instance.constructor = Prepared::Prefix(results);
        }
    }
}

impl Graph {
    /// Only this checked recipe may turn prepared Eq slots into source results.
    /// Source effects have not begun, and the prefix contains no graph mutation.
    pub(crate) fn seal_constructor_prefix(&mut self, rule: usize, values: &mut Slots,
        results: Vec<FactRef>, first: &mut Option<FactRef>) -> Option<Vec<FactRef>> {
        let steps = &self.program.executions[rule].constructor.as_ref().expect("prepared prefix plan").prefix[..results.len()];
        self.stats.constructor_prefix_checks += 1;
        let mut checks = 0;
        let valid = self.sealed_generation == Some(self.stats.unions) && steps.iter().all(|step| {
            checks += 1;
            self.constructor_prefix_table_ready(step.table)
        });
        self.stats.constructor_prefix_table_checks += checks;
        if valid { Some(results) } else {
            self.stats.constructor_prefix_rejected += 1;
            for step in steps {
                values.remove(&step.destination);
                self.stats.constructor_prefix_discarded_slots += 1;
            }
            // The first witness still has the original single-operation proof
            // shape. It may use exact source validation; no speculative Eq stays.
            *first = Some(results[0]);
            None
        }
    }
    pub(crate) fn consume_constructor_prefix(&mut self, rule: usize,
        results: Vec<FactRef>, effects: &mut crate::cell::Effects, lazy: bool) -> usize {
        let steps = &self.program.executions[rule].constructor.as_ref().unwrap().prefix[..results.len()];
        let end = steps.last().unwrap().operation + 1;
        self.stats.constructor_prefix_frames += 1;
        self.stats.constructor_prefix_operations += results.len() as u64;
        self.stats.constructor_requests += results.len() as u64;
        self.stats.constructor_reused += results.len() as u64;
        let aliases = steps.last().unwrap().aliases as u64;
        self.known_stats.static_eliminated += aliases;
        self.known_stats.avoided_lookups += aliases;
        if lazy { self.known_stats.lazy_prefix_eliminated += aliases; }
        for (step,witness) in steps.iter().zip(results) {
            if let Some(slot) = effects.slot(step.operation) {
                *slot = Some(Dependency::Fact(witness));
                self.stats.constructor_prefix_receipt_writes += 1;
            }
        }
        end
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invalid_run_or_visibility_evidence_clears_all_speculative_identities_before_source_allocation() {
        for change in ["same","union","delete"] {
            let mut g = super::super::tests::graph();
            let template = &mut g.program.templates[0];
            template.sorts.push(template.sorts[0].clone());
            template.defs.insert(2,1);
            template.ops=std::sync::Arc::new(vec![Op::Let(1,Call::Table(0),vec![Arg::Slot(0)]),
                Op::Let(2,Call::Table(0),vec![Arg::Slot(1)])]);
            g.program.known_results.static_skip[0]=std::rc::Rc::new(vec![false;2]);
            g.program.executions[0]=crate::cell::execution::Plan::derive(&g.program.tables,&g.program.templates[0],&[0]);
            let mut plan=Plan::derive(&g.program,0).unwrap();
            plan.compile_prefix(&g.program,0,&[true]);
            assert_eq!(plan.prefix_width(),2);
            g.program.executions[0].constructor=Some(plan.clone());
            let producer=g.linked_slots(0,[(0,Value::Eq(9))].into_iter().collect(),None).unwrap();
            let first=g.construct(producer,0,0,&[Arg::Slot(0)],1).unwrap();
            let second=g.construct(producer,1,0,&[Arg::Slot(1)],2).unwrap();
            g.repair().unwrap();g.changes.clear();
            let mut instance=Instance::matched([(0,Value::Eq(9))].into_iter().collect(),Default::default(),0);
            plan.prepare(&mut instance,g.query_reads(&[],&mut 0).as_ref(),
                &mut Default::default(),&mut Default::default(),&mut Counts::default());
            assert_eq!(instance.values.get(&1),Some(&first));
            assert_eq!(instance.values.get(&2),Some(&second));
            g.sealed_generation=Some(g.stats.unions);g.epoch=1;
            match change {
                "union" => {g.enqueue_union(Value::Eq(9),Value::Eq(7)).unwrap();g.repair().unwrap();},
                "delete" => {assert!(g.hide(0,&[Value::Eq(9)],true).unwrap());},
                _ => (),
            }
            let Prepared::Prefix(results)=std::mem::take(&mut instance.constructor) else {panic!("worker prefix")};
            let mut witness=None;
            let prefix=g.seal_constructor_prefix(0,&mut instance.values,results,&mut witness);
            if change=="same" {
                let mut effects=crate::cell::Effects::default();
                assert_eq!(g.consume_constructor_prefix(0,prefix.unwrap(),&mut effects,false),2);
                assert_eq!(instance.values.get(&1),Some(&first));
                assert_eq!(g.stats.constructor_prefix_operations,2);
            } else {
                assert!(prefix.is_none());
                assert!(!instance.values.contains_key(&1) && !instance.values.contains_key(&2));
                let cell=g.begin_transient(0,instance.values,None).unwrap();
                let actual=g.construct_prepared(cell,0,0,&[Arg::Slot(0)],1,None,witness.unwrap()).unwrap();
                let next=g.construct(cell,1,0,&[Arg::Slot(1)],2).unwrap();
                if change=="delete" {assert_ne!(actual,first);assert_ne!(next,second);}
                assert_eq!(g.stats.constructor_prefix_discarded_slots,2);
            }
        }
    }
}
