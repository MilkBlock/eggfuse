//! Checked register programs for connected queries with at most one index
//! expansion. Every other read is a complete key or a bound primitive.
use crate::{cell::Access, program::*};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, rc::Rc};
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Step {
    pub atom: usize,
    pub access: Access,
    pub assign: Vec<(usize, usize)>,
    pub check: Vec<(usize, Arg)>,
    pub bound: Vec<(usize, Arg)>,
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Kernel {
    pub pivot: usize,
    pub seed: Vec<(usize, usize)>,
    pub steps: Vec<Step>,
    /// Derived only after multi_stage's source wiring has been validated. These
    /// are shared plans, never consumer lists attached to live producers.
    #[serde(skip)]
    pub prefixes: Vec<Prefix>,
    #[cfg(feature = "sparse-cells")]
    #[serde(skip)]
    pub sum_filter: Option<(usize, usize, usize, Arg)>,
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
        if !kernel.steps.iter().any(|s| matches!(s.access, Access::Expand)) {
            continue;
        }
        let mut effects = Vec::new();
        let mut reads = 0;
        for step in &kernel.steps {
            match step.access {
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
    let mut known = BTreeSet::new();
    let mut seed = vec![];
    for (col, a) in r.query[pivot].args.iter().enumerate() {
        if let Arg::Slot(s) = a
            && known.insert(*s)
        {
            seed.push((col, *s));
        }
    }
    let mut steps = vec![];
    for (atom, access) in crate::cell::query_order(r, pivot, 1)? {
        let a = &r.query[atom];
        let available = |v: &Arg| matches!(v, Arg::Literal(_)) || matches!(v, Arg::Slot(s) if known.contains(s));
        let bound = a
            .args
            .iter()
            .enumerate()
            .filter(|(_, v)| available(v))
            .map(|(c, v)| (c, v.clone()))
            .collect();
        let mut assign = vec![];
        let mut check = vec![];
        let last = a.args.len() - 1;
        for (col, v) in a.args.iter().enumerate() {
            if let Arg::Slot(s) = v
                && known.insert(*s)
            {
                assign.push((col, *s));
            } else if col == last || matches!(access, Access::Expand) {
                check.push((col, v.clone()));
            }
        }
        steps.push(Step {
            atom,
            access,
            assign,
            check,
            bound,
        });
    }
    #[cfg(feature = "sparse-cells")]
    let sum_filter = steps.windows(2).find_map(|pair| {
        let (expand, guard) = (&pair[0], &pair[1]);
        if !matches!(expand.access, Access::Expand) || !guard.assign.is_empty() {
            return None;
        }
        let table = &r.query[expand.atom];
        let check = &r.query[guard.atom];
        if !matches!(&check.call, Call::Primitive(name, sort) if name == "+" && sort == "i64") {
            return None;
        }
        let [left,right,target] = check.args.as_slice() else { return None };
        if expand.assign.iter().any(|(_,slot)| target == &Arg::Slot(*slot)) {
            return None;
        }
        Some((expand.atom, table.args.iter().position(|a| a == left)?,
            table.args.iter().position(|a| a == right)?, target.clone()))
    });
    Some(Kernel { pivot, seed, steps, prefixes: vec![],
        #[cfg(feature = "sparse-cells")]
        sum_filter,
    })
}

/// A single functional write with a pure operand prefix. Its committed tuple
/// is also the only possible published anchor of this RHS.
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Write {
    #[cfg(feature="sparse-cells")]
    #[serde(skip)] pub(crate) ports: Option<PortWrite>,
    pub op: usize,
    pub table: usize,
    pub key: Vec<Arg>,
    pub value: Arg,
    pub prefix: Vec<(usize, String, String, Vec<Arg>)>,
}
#[cfg(feature="sparse-cells")]
#[derive(Clone,Debug)]
pub(crate) struct PortWrite {
    key: usize, value: Arg, add: Option<(usize,Arg,Arg)>,
}
#[cfg(feature="sparse-cells")]
impl PortWrite {
    fn derive(p:&Program,r:&Rule,table:usize,keys:&[Arg],value:&Arg,ops:&[(usize,String,String,Vec<Arg>)])->Option<Self>{
        let [Arg::Slot(key)]=keys else{return None};
        if p.tables[table].schema[0]["kind"]!="eq" || p.tables[table].schema.last()?["kind"]!="i64" || !r.inputs.contains(key){return None}
        let input=|a:&Arg|match a {Arg::Slot(s)=>r.inputs.contains(s) && p.templates[r.template].sorts[*s]["kind"]=="i64",Arg::Literal(crate::value::Value::Int(_))=>true,_=>false};
        let add=match ops {
            [] if input(value)=>None,
            [(dst,op,sort,args)] if op=="+" && sort=="i64" && value==&Arg::Slot(*dst)=>{
                let [a,b]=args.as_slice() else{return None};
                if !input(a)||!input(b){return None}
                Some((*dst,a.clone(),b.clone()))
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
            for ins in prefix {
                match ins {
                    Op::Copy(..) => {}
                    Op::Let(dst, Call::Primitive(name, sort), args)
                        if !name.starts_with("cell-key-") =>
                    {
                        calc.push((
                            *dst,
                            name.clone(),
                            sort.clone(),
                            args.iter().map(norm).collect(),
                        ))
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
