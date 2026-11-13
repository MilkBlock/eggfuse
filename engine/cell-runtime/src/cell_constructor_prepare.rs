//! Resolve constructor boundaries in the existing Run read view. A single
//! input-ready probe retains its witness; a checked permanent prefix continues
//! in the instance slots. Source validation consumes or clears those values
//! before any shared effect, preserving the original instruction order.
use crate::{cell::{Definition, Instance}, graph::{Dependency, FactRef},
    program::{Arg, Call, Op, Program}, value::{Value, canon}};
use serde::Serialize;
#[path = "cell_constructor_prefix.rs"]
mod prefix;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Plan {
    pub operation: usize,
    pub table: usize,
    // Compile once from the authoritative switch. Rules without a possible
    // result donor need no per-instance history admission checks.
    pub handoff: bool,
    owner_entries: bool,
    witness_rule:Option<std::num::NonZeroUsize>,
    keys: Vec<Arg>,
    prefix: Vec<prefix::Step>,
    // Slots established by the existing input-derived scalar program. Prefix
    // steps reference a cumulative slice; there is no second scalar evaluator.
    scalar_ready: Vec<usize>,
    pub(crate) result_layout: Option<std::sync::Arc<crate::cell::EffectLayout>>,
    units: Option<Box<super::unit_prepare::Plan>>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{graph::Graph, program::{Rule, Template}, slots::Slots, cell::QueryFacts};
    use std::{collections::BTreeMap, rc::Rc, sync::Arc};

    pub(super) fn graph() -> Graph {
        let eq = serde_json::json!({"kind":"eq","name":"E"});
        let template = Template { name:"prepared-constructor".into(), sorts:vec![eq.clone();2],
            defs:BTreeMap::from([(1,0)]), parent_columns:BTreeMap::new(),
            ops:Arc::new(vec![Op::Let(1,Call::Table(0),vec![Arg::Slot(0)])]) };
        let rule = Rule { template:0, query:Rc::new(vec![]), inputs:vec![0].into(),
            completion:Default::default(),seminaive:false,direct:None };
        let mut p:Program=serde_json::from_value(serde_json::json!({
            "multi_stage":crate::multistage::MultiStage::default(),
            "entry_schedule":crate::entry_schedule::Plan::default(),
            "tables":[{"name":"F","schema":[eq,eq],"constructor":true,"virtual_fact":true,
                "internal":false,"merge":null}],"templates":[template],"rules":[rule],
            "sets":{},"control":[],"initial":[],"table_templates":[0],"artifact":{}
        })).unwrap();
        p.known_results.static_skip=vec![Rc::new(vec![false])];
        p.executions=vec![crate::cell::execution::Plan::derive(&p.tables,&p.templates[0],&[0])];
        Graph::new(p).unwrap()
    }

    #[test]
    fn a_speculative_witness_never_assigns_an_eq_result_and_invalid_evidence_reuses_the_source_key() {
        for change in ["unchanged","delete","hide","key","union"] {
            let mut g=graph();
            let producer=g.linked_frame(0,BTreeMap::from([(0,Value::Eq(9))]),None).unwrap();
            let old=g.construct(producer,0,0,&[Arg::Slot(0)],1).unwrap();
            g.repair().unwrap(); g.changes.clear();
            let plan=Plan::derive(&g.program,0).unwrap();
            let mut values=Slots::with_capacity(2); values.insert(0,Value::Eq(9));
            let mut instance=Instance::matched(values,QueryFacts::None,0);
            let mut counts=Counts::default();
            plan.prepare(&mut instance,g.query_reads(&[],&mut 0).as_ref(),
                &mut Default::default(),&mut Default::default(),&mut counts);
            assert_eq!(counts.hits,1,"{change}");
            assert!(!instance.values.contains_key(&1),"only source execution may assign the Eq result");
            let witness=instance.constructor.take().unwrap();
            assert_eq!(witness,FactRef{cell:producer,op:0});
            g.epoch = 1; // Source effects follow the initial constructor birth.
            match change {
                "delete" => { assert!(g.hide(0,&[Value::Eq(9)],true).unwrap()); }
                "hide" => { assert!(g.hide(0,&[Value::Eq(9)],false).unwrap()); }
                "key" => { instance.values.insert(0,Value::Eq(11)); }
                "union" => { g.enqueue_union(Value::Eq(9),Value::Eq(7)).unwrap(); g.repair().unwrap(); }
                _ => (),
            }
            let cell=g.begin_transient(0,instance.values,None).unwrap();
            let lookups=g.key_lookup_calls.get();
            let result=g.construct_prepared(cell,0,0,&[Arg::Slot(0)],1,None,witness.into()).unwrap();
            let accepted=matches!(change,"unchanged"|"union");
            assert_eq!(g.key_lookup_calls.get()-lookups,u64::from(!accepted),"{change}");
            assert_eq!(g.stats.constructor_prepared_accepted,u64::from(accepted),"{change}");
            assert_eq!(g.stats.constructor_prepared_rejected,u64::from(!accepted),"{change}");
            if matches!(change,"delete"|"key") { assert_ne!(result,old,"fresh identity after {change}"); }
            else { assert_eq!(result,old,"{change}"); }
        }
    }

    #[test]
    fn run_certificate_removes_key_reads_but_cannot_survive_union_or_replace_liveness() {
        for change in ["unchanged", "delete", "hide", "union"] {
            let mut g = graph();
            let producer = g.linked_frame(0,BTreeMap::from([(0,Value::Eq(9))]),None).unwrap();
            let old = g.construct(producer,0,0,&[Arg::Slot(0)],1).unwrap();
            g.repair().unwrap(); g.changes.clear();
            let generation = g.stats.unions;
            let mut values = Slots::with_capacity(2); values.insert(0,Value::Eq(9));
            let mut instance = Instance::matched(values,QueryFacts::None,0);
            Plan::derive(&g.program,0).unwrap().prepare(&mut instance,
                g.query_reads(&[],&mut 0).as_ref(), &mut Default::default(),
                &mut Default::default(), &mut Counts::default());
            let witness = instance.constructor.take().unwrap();
            g.epoch = 1;
            match change {
                "delete" => { assert!(g.hide(0,&[Value::Eq(9)],true).unwrap()); }
                "hide" => { assert!(g.hide(0,&[Value::Eq(9)],false).unwrap()); }
                "union" => { g.enqueue_union(Value::Eq(9),Value::Eq(7)).unwrap(); g.repair().unwrap(); }
                _ => (),
            }
            // Carry the original snapshot certificate, never reissue one using
            // the current graph generation after earlier source effects.
            g.sealed_generation = Some(generation);
            let cell = g.begin_transient(0,instance.values,None).unwrap();
            let reads = g.key_lookup_calls.get();
            let result = g.construct_prepared(cell,0,0,&[Arg::Slot(0)],1,None,witness.into()).unwrap();
            assert_eq!(g.stats.constructor_prepared_certificates,1,"{change}");
            assert_eq!(g.stats.constructor_prepared_sealed,u64::from(change == "unchanged"),"{change}");
            assert_eq!(g.stats.constructor_prepared_key_fields_avoided,u64::from(change == "unchanged"));
            assert_eq!(g.stats.constructor_prepared_fields,u64::from(change == "union"));
            assert_eq!(g.key_lookup_calls.get()-reads,u64::from(matches!(change,"delete"|"hide")));
            if change == "delete" { assert_ne!(result,old); } else { assert_eq!(result,old); }
        }
    }

    #[test]
    fn rejected_snapshot_uses_exact_keys_without_repeating_the_certificate() {
        use crate::graph::ConstructorWitness;
        assert_eq!(std::mem::size_of::<Option<ConstructorWitness>>(),std::mem::size_of::<Option<FactRef>>());
        for change in ["delete","hide","union"] {
            let mut g=graph();
            let producer=g.linked_frame(0,BTreeMap::from([(0,Value::Eq(9))]),None).unwrap();
            let old=g.construct(producer,0,0,&[Arg::Slot(0)],1).unwrap();g.repair().unwrap();
            let generation=g.stats.unions;
            let witness=FactRef{cell:producer,op:0};
            g.epoch=1;
            match change {
                "delete"=>{g.hide(0,&[Value::Eq(9)],true).unwrap();},
                "hide"=>{g.hide(0,&[Value::Eq(9)],false).unwrap();},
                _=>{g.enqueue_union(Value::Eq(9),Value::Eq(7)).unwrap();g.repair().unwrap();},
            }
            g.sealed_generation=Some(generation);
            let mut values=Slots::with_capacity(1);values.insert(0,Value::Eq(9));
            let cell=g.begin_transient(0,values,None).unwrap();
            assert!(g.sealed_constructor_result(cell,0,witness).unwrap().is_none());
            let mut receipt=None;
            let value=g.construct_prepared(cell,0,0,&[Arg::Slot(0)],1,Some(&mut receipt),ConstructorWitness::Key(witness)).unwrap();
            assert_eq!(g.stats.constructor_prepared_certificates,1,"{change}");
            assert_eq!(g.stats.constructor_prepared_fields,u64::from(change=="union"));
            assert_eq!(g.stats.constructor_prepared_rejected,u64::from(change!="union"));
            if change=="delete" {assert_ne!(value,old);assert_ne!(receipt,Some(Dependency::Fact(witness)));}
            else {assert_eq!(value,old);assert_eq!(receipt,Some(Dependency::Fact(witness)));}
        }
    }
}
#[derive(Debug, Default)]
pub(crate) enum Prepared {
    #[default]
    Untried,
    Absent,
    Found(FactRef),
    // Demanded actual results already occupy the source Effects layout.
    // Progress uses Instance.prepared; no temporary per-constructor receipt log.
    Prefix(Vec<Option<Dependency>>),
    // Only mixed Cells allocate this holder; the ordinary Instance and the
    // source Execution keep their existing sizes and actual result layouts.
    PrefixUnits(Box<PrefixUnits>),
    // Input-only Unit cells have no constructor preparation. Reuse this
    // mutually exclusive state instead of widening every matched Instance.
    Units(super::unit_prepare::Prepared),
}
#[derive(Debug)]
pub(crate) struct PrefixUnits {
    pub results: Vec<Option<Dependency>>,
    pub units: super::unit_prepare::Prepared,
}
impl Prepared {
    pub fn pending(&self) -> bool { matches!(self, Self::Untried) }
    #[cfg(test)]
    pub fn take(&mut self) -> Option<FactRef> {
        match std::mem::replace(self, Self::Absent) { Self::Found(f) => Some(f), _ => None }
    }
}
#[derive(Default, Serialize)]
pub(crate) struct Counts {
    pub attempts: u64,
    pub unavailable: u64,
    pub missing_inputs: u64,
    pub key_fields: u64,
    pub key_spills: u64,
    pub lookups: u64,
    pub hits: u64,
    pub misses: u64,
    pub result_writes: u64,
    pub prefix_instances: u64,
    pub prefix_slot_writes: u64,
    pub prefix_slot_growths: u64,
    pub prefix_capacity_bytes: u64,
    pub prefix_witness_growths: u64,
    pub prefix_witness_bytes: u64,
    pub prefix_layout_checks: u64,
    pub prefix_result_initializations: u64,
    pub prefix_progress_writes: u64,
    pub prefix_scalar_checks: u64,
    pub prefix_scalar_stops: u64,
    pub witnesses:crate::graph::query_reads::PreparedWork,
}
impl Counts {
    pub fn add(&mut self, other: &Self) {
        macro_rules! add { ($($f:ident),*) => { $(self.$f += other.$f;)* }; }
        add!(attempts, unavailable, missing_inputs, key_fields, key_spills, lookups, hits, misses, result_writes);
        add!(prefix_instances, prefix_slot_writes, prefix_slot_growths, prefix_capacity_bytes,
            prefix_witness_growths, prefix_witness_bytes);
        add!(prefix_layout_checks, prefix_result_initializations, prefix_progress_writes);
        add!(prefix_scalar_checks, prefix_scalar_stops);
        self.witnesses.add(&other.witnesses);
    }
}
impl Plan {
    pub fn complete(&self, instance: &mut Instance, reads: Option<&crate::graph::query_reads::QueryReads<'_>>,
        scratch: &mut crate::graph::query_reads::Scratch, work: &mut crate::graph::query_reads::Work,
        counts: &mut super::execution::Counts) {
        self.prepare(instance, reads, scratch, work, &mut counts.constructor);
        self.prepare_units(instance, reads, &mut counts.units);
    }
    pub fn has_unit_tail(&self) -> bool { self.units.is_some() }
    pub fn derive(p: &Program, rule: usize) -> Option<Self> {
        let cell = Definition::new(p, rule).ok()?;
        // Captured input rewrites need a stronger temporal alias proof.
        if cell.rule.inputs.iter().any(|s| cell.template.defs.contains_key(s)) { return None; }
        let scalar = &p.executions[rule];
        let mut ready = cell.rule.inputs.iter().copied().collect::<std::collections::BTreeSet<_>>();
        ready.extend(scalar.segments[0].outputs.iter().copied());
        for &op in &scalar.input_ready {
            if let Op::Let(dst, ..) = cell.template.ops[op] { ready.insert(dst); }
        }
        for (operation, op) in cell.template.ops.iter().enumerate() {
            if matches!(op, Op::Hide(..) | Op::Panic) { break; }
            if p.known_results.static_skip[rule][operation] { continue; }
            let Op::Let(_, Call::Table(table), args) = op else { continue };
            if !p.tables[*table].constructor || !p.tables[*table].virtual_fact { continue; }
            let keys: Vec<_> = args.iter().map(|a| cell.value(a)).collect();
            if keys.iter().all(|a| match a {
                Arg::Literal(_) => true,
                Arg::Slot(s) => ready.contains(s) && cell.template.defs.get(s).is_none_or(|&at| at < operation),
            }) { return Some(Self { operation, table:*table,
                handoff: p.iterative.supplies_operation(rule, operation), owner_entries:false,
                witness_rule:p.cell_ownership.has_witness_routes(rule).then(||std::num::NonZeroUsize::new(rule+1).unwrap()),
                keys, prefix:vec![], scalar_ready:vec![], result_layout:None, units:None }); }
        }
        None
    }
    pub fn storage_bytes(&self) -> usize { self.keys.capacity() * std::mem::size_of::<Arg>()
        + self.prefix.capacity() * std::mem::size_of::<prefix::Step>()
        + self.scalar_ready.capacity() * std::mem::size_of::<usize>()
        + self.prefix.iter().map(|s|s.keys.capacity()*std::mem::size_of::<Arg>()).sum::<usize>()
        + self.units.as_ref().map_or(0, |p|std::mem::size_of::<super::unit_prepare::Plan>()+p.storage_bytes()) }
    pub fn prepare(&self, instance: &mut Instance, reads: Option<&crate::graph::query_reads::QueryReads<'_>>,
        scratch: &mut crate::graph::query_reads::Scratch, work: &mut crate::graph::query_reads::Work,
        counts: &mut Counts) {
        if !instance.constructor.pending() { return; }
        instance.constructor = Prepared::Absent;
        counts.attempts += 1;
        if !self.prefix.is_empty() {
            self.prepare_prefix(instance, reads, scratch, work, counts);
            return;
        }
        let Some(reads) = reads else {
            counts.unavailable += 1; return;
        };
        match self.probe(self.operation,self.table,&self.keys,instance,reads,scratch,work,counts,&mut Default::default()) {
            Ok(Some((_, _, Dependency::Fact(fact)))) => {
                instance.constructor = Prepared::Found(fact);
                counts.hits += 1;
                counts.result_writes += 1;
            }
            Ok(None) => counts.misses += 1,
            // Speculation cannot introduce a query failure. The source
            // operation remains responsible at its original effect position.
            _ => counts.unavailable += 1,
        }
    }
    pub(super) fn probe(&self,operation:usize,table:usize,args:&[Arg],instance:&Instance,
        reads:&crate::graph::query_reads::QueryReads<'_>,scratch:&mut crate::graph::query_reads::Scratch,
        work:&mut crate::graph::query_reads::Work,counts:&mut Counts,
        selection:&mut crate::graph::query_reads::PreparedSelection)
        ->std::result::Result<Option<(Value,u64,Dependency)>,()> {
        let Counts{key_fields,key_spills,missing_inputs,witnesses,..}=counts;
        let mut make_key=|| {
            let mut values=smallvec::SmallVec::<[Value;4]>::new();
            for arg in args {
                let value=match arg {
                    Arg::Literal(v)=>v,
                    Arg::Slot(slot)=>match instance.values.get(slot) {
                        Some(v)=>v,None=>{*missing_inputs+=1;return Err(());}
                    },
                };
                *key_fields+=1;values.push(canon(value,reads.parents));
            }
            *key_spills+=u64::from(values.spilled());Ok(values)
        };
        let Some(rule)=self.witness_rule else {
            if !reads.constructor_available(table) {return Err(());}
            let key=make_key()?;
            counts.lookups+=1;
            return reads.point(table,&key,scratch,work).map_err(|_|());
        };
        let mut key=None;
        if let Some(result)=reads.prepared_witness(rule.get()-1,operation,table,&instance.known,
                selection,witnesses,work,&mut key,&mut make_key) {return Ok(Some(result));}
        if !reads.constructor_available(table) {return Err(());}
        let key=key.get_or_insert_with(make_key).as_ref().map_err(|_|())?;
        counts.lookups+=1;
        reads.point(table,key,scratch,work).map_err(|_|())
    }
}
