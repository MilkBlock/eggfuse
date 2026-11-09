//! Residual Cell query entries and their checked producer prefixes. Query owns
//! the shared dataflow; this module retains admission and capability metadata.
use crate::{cell::{Access, Query}, program::*};
#[cfg(feature = "sparse-cells")]
use crate::cell::Field;
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, rc::Rc};
#[derive(Clone, Debug)]
pub(crate) struct Kernel {
    pub pivot: usize,
    pub query: Rc<Query>,
    /// Derived only after multi_stage's source wiring has been validated. These
    /// are shared plans, never consumer lists attached to live producers.
    pub prefixes: Vec<Prefix>,
    #[cfg(feature = "sparse-cells")]
    pub sum_filter: Option<(usize, usize, usize, Field)>,
}
#[derive(Clone, Debug)]
pub(crate) struct Prefix {
    pub template: usize,
    pub publication: usize,
    /// One entry for each leading kernel instruction. None is a primitive that
    /// must still execute; Some is the normalized query/effect donor.
    pub effects: Vec<Option<crate::multistage::WitnessSource>>,
}

/// Actual work of the residual register matcher's optional producer prefix.
/// A skipped point read may otherwise have hit PointPorts, so it is not itself
/// evidence of a skipped hash lookup.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct PrefixStats {
    pub eligible_seeds: u64,
    pub context_reads: u64,
    pub context_missing: u64,
    pub plan_lookups: u64,
    pub plan_comparisons: u64,
    pub plan_hits: u64,
    pub donor_reads: u64,
    pub donor_hits: u64,
    pub stale_fallbacks: u64,
    pub misses: crate::graph::producer::WitnessMisses,
    pub publication_probes: u64,
    pub entry_publication_reads: u64,
    pub receipt_probes: u64,
    pub receipt_steps: u64,
    pub receipt_slot_reads: u64,
    pub receipt_hits: u64,
    pub row_reads: u64,
    pub history_borrows: u64,
    pub key_fallbacks: u64,
    pub field_checks: u64,
    pub key_fields: u64,
    pub field_writes: u64,
    pub primitive_checks: u64,
    pub primitive_rejections: u64,
    pub owner_rejections: u64,
    pub result_rejections: u64,
    pub key_reads_avoided: u64,
    pub resumed_instructions: u64,
    pub resumes: u64,
}

/// Attach a contiguous, complete-key prefix to residual kernels. A route may
/// know one row of an expansion, but that never proves its whole candidate
/// domain. Likewise a later atom cannot justify skipping an earlier key read.
pub(crate) fn attach_prefixes(p: &mut Program) {
    for (&(template, publication, rid, pivot), route) in &p.multi_stage.routes {
        let Some(kernel) = p.kernels[rid][pivot].as_mut() else { continue };
        if !kernel.query.steps.iter().any(|s| matches!(s.access(), Access::Expand)) {
            continue;
        }
        let mut effects = Vec::new();
        let mut reads = 0;
        for step in &kernel.query.steps {
            match step.access() {
                Access::Expand => break,
                Access::Primitive => effects.push(None),
                Access::Key => {
                    let Some(read) = route.reads.iter().find(|r| r.atom == step.atom) else {
                        break;
                    };
                    let Some(effect) = read.witness else { break };
                    effects.push(Some(effect));
                    reads += 1;
                }
            }
        }
        if reads != 0 {
            Rc::make_mut(kernel).prefixes.push(Prefix { template, publication, effects });
        }
    }
    for kernel in p.kernels.iter_mut().flatten().flatten() {
        if !kernel.prefixes.is_empty() {
            Rc::make_mut(kernel).prefixes.sort_unstable_by_key(|p| (p.template, p.publication));
        }
    }
}

pub(crate) type Kernels = Vec<Vec<Option<Rc<Kernel>>>>;
pub(crate) fn derive(rules: &[Rule]) -> Kernels {
    rules
        .iter()
        .map(|r| {
            (0..r.query.len())
                .map(|pivot| plan(r, pivot).map(Rc::new))
                .collect()
        })
        .collect()
}
fn plan(r: &Rule, pivot: usize) -> Option<Kernel> {
    if !r.seminaive || r.direct.is_some() || !matches!(r.query[pivot].call, Call::Table(_)) {
        return None;
    }
    let query = Rc::new(Query::residual(r, pivot)?);
    #[cfg(feature = "sparse-cells")]
    let sum_filter = query.steps.windows(2).enumerate().find_map(|(pc, pair)| {
        let (expand, guard) = (&pair[0], &pair[1]);
        if expand.expansion.is_none() { return None; }
        let target = guard.check_result.as_ref()?;
        if matches!(target, Field::Column { step, .. } if *step == pc) { return None; }
        if !matches!(&guard.call, Call::Primitive(name, sort) if name == "+" && sort == "i64") {
            return None;
        }
        let table = &r.query[expand.atom];
        let check = &r.query[guard.atom];
        let [left, right, _] = check.args.as_slice() else { return None };
        Some((expand.atom, table.args.iter().position(|a| a == left)?,
            table.args.iter().position(|a| a == right)?, target.clone()))
    });
    Some(Kernel { pivot, query, prefixes: vec![],
        #[cfg(feature = "sparse-cells")]
        sum_filter,
    })
}

/// Project the shared program back to the historical artifact's SSA coordinates.
/// These assignments are compatibility metadata only; the loader never retains
/// or executes a second register plan. Order and access come from Cell Query.
pub(crate) fn wire(rules: &[Rule], kernels: &Kernels) -> serde_json::Value {
    use serde_json::{Value as J, json};
    // Move built JSON arrays into their parents. Serializing a Value tree again
    // duplicates every nested node and inflates the loader's peak allocation.
    J::Array(rules.iter().zip(kernels).map(|(rule, entries)| J::Array(entries.iter().map(|entry| {
        let Some(kernel) = entry else { return J::Null };
        let mut known = BTreeSet::new();
        let seed = rule.query[kernel.pivot].args.iter().enumerate().filter_map(|(col, a)| {
            if let Arg::Slot(s) = a && known.insert(*s) { Some((col, *s)) } else { None }
        }).collect::<Vec<_>>();
        let steps = kernel.query.steps.iter().map(|step| {
            let atom = &rule.query[step.atom];
            let bound = atom.args.iter().enumerate().filter(|(_, a)| {
                matches!(a, Arg::Literal(_)) || matches!(a, Arg::Slot(s) if known.contains(s))
            }).collect::<Vec<_>>();
            let mut assign = Vec::new();
            let mut check = Vec::new();
            for (col, arg) in atom.args.iter().enumerate() {
                if let Arg::Slot(s) = arg && known.insert(*s) {
                    assign.push((col, *s));
                } else if col + 1 == atom.args.len() || step.expansion.is_some() {
                    check.push((col, arg));
                }
            }
            json!({"atom":step.atom,"access":step.access(),"assign":assign,"check":check,"bound":bound})
        }).collect::<Vec<_>>();
        J::Object(serde_json::Map::from_iter([
            ("pivot".into(), kernel.pivot.into()),
            ("seed".into(), json!(seed)),
            ("steps".into(), J::Array(steps)),
        ]))
    }).collect())).collect())
}

/// A single functional write with a pure operand prefix. Its committed tuple
/// is also the only possible published anchor of this RHS.
#[derive(Clone, Debug)]
pub(crate) struct Write {
    #[cfg(feature="sparse-cells")]
    pub(crate) ports: Option<PortWrite>,
    pub op: usize,
    pub table: usize,
    pub key: Vec<Arg>,
    pub value: Arg,
    pub prefix: Vec<usize>,
}
#[cfg(feature="sparse-cells")]
#[derive(Clone,Debug)]
pub(crate) struct PortWrite {
    key: usize, value: Arg, add: Option<(usize,Arg,Arg)>,
}
#[cfg(feature="sparse-cells")]
impl PortWrite {
    fn derive(p:&Program,r:&Rule,table:usize,keys:&[Arg],value:&Arg,ops:&[usize])->Option<Self>{
        let [Arg::Slot(key)]=keys else{return None};
        if p.tables[table].schema[0]["kind"]!="eq" || p.tables[table].schema.last()?["kind"]!="i64" || !r.inputs.contains(key){return None}
        let input=|a:&Arg|match a {Arg::Slot(s)=>r.inputs.contains(s) && p.templates[r.template].sorts[*s]["kind"]=="i64",Arg::Literal(crate::value::Value::Int(_))=>true,_=>false};
        let add=match ops {
            [] if input(value)=>None,
            [position]=>{
                let template=&p.templates[r.template];
                let Op::Let(dst,Call::Primitive(op,sort),args)=&template.ops[*position] else{return None};
                if op!="+" || sort!="i64" || value!=&Arg::Slot(*dst){return None}
                let [a,b]=args.as_slice() else{return None};
                let (a,b)=(template.resolve_copy(a),template.resolve_copy(b));
                if !input(&a)||!input(&b){return None}
                Some((*dst,a,b))
            },
            _=>return None,
        };
        Some(Self{key:*key,value:value.clone(),add})
    }
    pub(crate) fn project(&self,slots:&crate::slots::Slots,parents:&crate::value::Parents)->Result<(crate::value::Value,i64,Option<usize>)>{
        use crate::value::Value;
        let Value::Eq(key)=slots[&self.key] else{return Err("invalid producer expression port".into())};
        let int=|a:&Arg|match a {Arg::Literal(Value::Int(v))=>Ok(*v),Arg::Slot(s)=>match &slots[s]{Value::Int(v)=>Ok(*v),_=>Err("invalid integer port".to_string())},_=>Err("invalid integer operand".to_string())};
        let (v,dst)=if let Some((dst,a,b))=&self.add{(int(a)?.checked_add(int(b)?).ok_or("RHS primitive failed: +")?,Some(*dst))}else{(int(&self.value)?,None)};
        Ok((Value::Eq(crate::value::root(parents,key)),v,dst))
    }
}
pub(crate) fn writes(p: &Program) -> Vec<Option<Rc<Write>>> {
    p.rules
        .iter()
        .map(|r| {
            let t = &p.templates[r.template];
            let (Op::Set(table, key, value), prefix) = t.ops.split_last()? else {
                return None;
            };
            if p.tables[*table].virtual_fact
                || (!p.tables[*table].merge.is_null() && p.physical.merges[*table].is_none())
            {
                return None;
            }
            let norm = |a: &Arg| t.resolve_copy(a);
            let mut calc = vec![];
            for (position, ins) in prefix.iter().enumerate() {
                match ins {
                    Op::Copy(..) => {}
                    Op::Let(_, Call::Primitive(name, _), _)
                        if !name.starts_with("cell-key-") =>
                    {
                        calc.push(position)
                    }
                    _ => return None,
                }
            }
            let key=key.iter().map(norm).collect::<Vec<_>>();
            let value=norm(value);
            Some(Rc::new(Write {
                #[cfg(feature="sparse-cells")]
                ports:PortWrite::derive(p,r,*table,&key,&value,&calc),
                op: prefix.len(),
                table: *table,
                key,
                value,
                prefix: calc,
            }))
        })
        .collect()
}

/// Preserve the existing artifact from source Cell instructions. The runtime
/// retains the scalar prefix's positions, never a second primitive program.
pub(crate) fn writes_wire(p: &Program) -> serde_json::Value {
    use serde_json::{Value as J, json};
    J::Array(p.writes.iter().enumerate().map(|(rid, write)| {
        let Some(write) = write else { return J::Null };
        let template = &p.templates[p.rules[rid].template];
        let prefix = write.prefix.iter().map(|&position| {
            let Op::Let(dst, Call::Primitive(name, sort), args) = &template.ops[position] else {
                unreachable!("validated scalar Cell prefix")
            };
            json!([dst, name, sort, args.iter().map(|a| template.resolve_copy(a)).collect::<Vec<_>>()])
        }).collect::<Vec<_>>();
        json!({"op":write.op,"table":write.table,"key":write.key,"value":write.value,"prefix":prefix})
    }).collect())
}
