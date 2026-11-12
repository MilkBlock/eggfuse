//! Closed-program constructor facts exported through ordinary Cell query slots.
//! Proofs exist only during Bake. A result value is NOT a constructor FactRef.
use crate::{cell::construction::{Construction, Known}, program::{Arg, Call, Op, Program}};
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Clone, Debug, Serialize)]
pub struct Proof {
    pub view: usize,
    pub constructor: usize,
    /// Constructor inputs followed by its result, projected from View columns.
    pub columns: Vec<usize>,
    pub writers: Vec<(usize, usize)>,
}

pub fn prove(p: &Program, view: usize, constructor: usize, columns: &[usize]) -> Option<Proof> {
    let v = p.tables.get(view)?;
    let c = p.tables.get(constructor)?;
    let deleted=p.templates.iter().flat_map(|t|t.ops.iter()).filter_map(|op| {
        if let Op::Hide(t,_,_)=op {Some(*t)} else {None}
    }).collect::<std::collections::BTreeSet<_>>();
    if v.constructor || v.virtual_fact || v.schema.last()?["kind"] != "Unit"
        || v.merge != serde_json::json!({"var":"old"}) || !c.constructor
        || columns.len() != c.schema.len()
        || columns.iter().zip(&c.schema).any(|(&i, sort)| i >= v.schema.len().saturating_sub(1) || v.schema[i] != *sort)
        || p.initial.iter().any(|row| row["table"] == v.name)
        || deleted.contains(&constructor) {
        return None;
    }
    let mut writers = vec![];
    for (rid,r) in p.rules.iter().enumerate() {
        let template = &p.templates[r.template];
        if !template.ops.iter().any(|op|matches!(op,Op::Set(t,_,_) if *t==view)) {continue;}
        let mut env = Construction::<usize,Arg,()>::default();
        for atom in r.query.iter() {
            let Call::Table(t) = atom.call else {continue;};
            if p.tables[t].constructor && !deleted.contains(&t) {
                let (out,key)=atom.args.split_last()?;
                env.matched(t,key.to_vec(),out.clone(),());
            } else if t==view {
                // Inductive assumption: all previously inserted rows satisfy
                // this relation. Empty initial View is the base case. EVERY
                // writer below must preserve it, including self-forwarding.
                let fields=columns.iter().map(|&col|atom.args[col].clone()).collect::<Vec<_>>();
                let (out,key)=fields.split_last()?;
                env.matched(constructor,key.to_vec(),out.clone(),());
            }
        }
        for (op,ins) in template.ops.iter().enumerate() {
            match ins {
                Op::Copy(dst,arg)=>env.copy(Arg::Slot(*dst),arg),
                Op::Let(dst,Call::Table(t),args) if p.tables[*t].constructor=> {
                    let (known,_)=env.construct(*t,args.iter().cloned(),||Some(Known {
                        value:Arg::Slot(*dst),source:(),
                    }))?;
                    env.copy(Arg::Slot(*dst),&known.value);
                }
                Op::Hide(t,_,_)=>env.forget(t),
                Op::Set(t,args,_) if *t==view=> {
                    let fields=columns.iter().map(|&col|env.resolve(&args[col])).collect::<Vec<_>>();
                    let (out,key)=fields.split_last()?;
                    let (known,_)=env.construct(constructor,key.iter().cloned(),||None)?;
                    if env.resolve(&known.value)!=*out {return None;}
                    writers.push((rid,op));
                }
                // Union effects are not used as immediate equalities. No fact
                // is inferred from mutable reads, scalar results or a future op.
                _=>(),
            }
        }
    }
    (!writers.is_empty()).then(||Proof {view,constructor,columns:columns.to_vec(),writers})
}

#[derive(Debug, Serialize)]
pub struct Projection {
    pub rule:usize,
    pub operation:usize,
    pub query_atom:usize,
    pub result_slot:usize,
    pub proof:Proof,
}

/// Discover direct query-slot projections demanded by constructor operations.
/// Does not change execution plans: receipt consumers still need real witnesses.
pub fn discover(p:&Program)->Vec<Projection> {
    let mut cache=BTreeMap::new();
    let mut found=vec![];
    for (rid,r) in p.rules.iter().enumerate() {
        let Ok(cell)=crate::cell::Definition::new(p,rid) else {continue;};
        for (op,ins) in p.templates[r.template].ops.iter().enumerate() {
            let Op::Let(_,Call::Table(t),args)=ins else {continue;};
            if !p.tables[*t].constructor {continue;}
            for (atom,a) in r.query.iter().enumerate() {
                let Call::Table(view)=a.call else {continue;};
                if p.tables[view].constructor || p.tables[view].schema.last().is_none_or(|s|s["kind"]!="Unit") {continue;}
                let input_columns=args.iter().map(|arg| {
                    let value=cell.template.resolve_copy(arg);
                    a.args[..a.args.len()-1].iter().position(|x|*x==value)
                }).collect::<Option<Vec<_>>>();
                let Some(inputs)=input_columns else {continue;};
                for (col,arg) in a.args[..a.args.len()-1].iter().enumerate() {
                    let Arg::Slot(slot)=arg else {continue;};
                    if p.tables[view].schema[col]!=*p.tables[*t].schema.last().unwrap() {continue;}
                    let mut columns=inputs.clone();columns.push(col);
                    let proof=cache.entry((view,*t,columns.clone())).or_insert_with(||prove(p,view,*t,&columns));
                    if let Some(proof)=proof {
                        found.push(Projection {rule:rid,operation:op,query_atom:atom,result_slot:*slot,proof:proof.clone()});
                        break;
                    }
                }
            }
        }
    }
    found
}

/// Export constructor facts already encoded by a materialized Cell query row.
/// Seeds come from actual producer definitions, then all writers are checked.
/// This can inform representation changes even when no RHS requests the value.
pub fn exports(p:&Program)->Vec<Proof> {
    let mut candidates=std::collections::BTreeSet::new();
    for (rid,r) in p.rules.iter().enumerate() {
        let Ok(cell)=crate::cell::Definition::new(p,rid) else {continue;};
        for ins in p.templates[r.template].ops.iter() {
            let Op::Set(view,args,_)=ins else {continue;};
            if p.tables[*view].constructor || p.tables[*view].schema.last().is_none_or(|s|s["kind"]!="Unit") {continue;}
            let fields=args.iter().map(|a|cell.template.resolve_copy(a)).collect::<Vec<_>>();
            for relation in cell.local_relations() {
                if !p.tables[relation.table].constructor {continue;}
                let columns=relation.columns().map(|a| {
                    let value=cell.template.resolve_copy(a);
                    fields.iter().position(|x|*x==value)
                }).collect::<Option<Vec<_>>>();
                if let Some(columns)=columns {candidates.insert((*view,relation.table,columns));}
            }
        }
    }
    candidates.into_iter().filter_map(|(v,c,cols)|prove(p,v,c,&cols)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::program::{Atom,Rule,Template};
    use crate::value::Value;
    use std::{rc::Rc,sync::Arc};
    use serde_json::json;
    fn s(i:usize)->Arg {Arg::Slot(i)}
    fn unit()->Arg {Arg::Literal(Value::Int(0))}
    fn fixture()->Program {
        let eq=json!({"name":"E","kind":"eq"});
        let template=Template {name:"producer".into(),sorts:vec![eq.clone();4],
            defs:BTreeMap::from([(1,0)]),parent_columns:BTreeMap::new(),
            ops:Arc::new(vec![Op::Let(1,Call::Table(0),vec![s(0)]),Op::Set(1,vec![s(0),s(1)],unit())])};
        let rule=Rule {template:0,query:Rc::new(vec![]),inputs:vec![0].into(),
            completion:Default::default(),seminaive:false,direct:None};
        serde_json::from_value(json!({
            "multi_stage":crate::multistage::MultiStage::default(),
            "entry_schedule":crate::entry_schedule::Plan::default(),
            "tables":[{"name":"F","schema":[eq,eq],"constructor":true,"virtual_fact":true,"internal":false,"merge":null},
                {"name":"View","schema":[eq,eq,{"name":"Unit","kind":"Unit"}],"constructor":false,"virtual_fact":false,"internal":false,"merge":{"var":"old"}}],
            "templates":[template],"rules":[rule],"sets":{},"control":[],"initial":[],"table_templates":[0,0],"artifact":{}
        })).unwrap()
    }
    #[test]
    fn induction_accepts_constructor_and_forwarding_but_checks_every_writer() {
        let mut p=fixture();
        assert_eq!(prove(&p,1,0,&[0,1]).unwrap().writers,vec![(0,1)]);
        let mut recursive=p.rules[0].clone();recursive.template=1;
        recursive.query=Rc::new(vec![Atom {call:Call::Table(1),args:vec![s(0),s(1),s(2)]}]);
        p.rules.push(recursive);
        let mut forward=p.templates[0].clone();forward.ops=Arc::new(vec![Op::Set(1,vec![s(0),s(1)],unit())]);
        p.templates.push(forward);
        assert_eq!(prove(&p,1,0,&[0,1]).unwrap().writers.len(),2);
        p.templates[1].ops=Arc::new(vec![Op::Set(1,vec![s(0),s(3)],unit())]);
        assert!(prove(&p,1,0,&[0,1]).is_none());
    }
    #[test]
    fn deleted_query_constructor_cannot_alias_a_fresh_rhs_result() {
        let mut p=fixture();
        let mut h=p.tables[0].clone();h.name="H".into();p.tables.push(h);
        p.rules[0].query=Rc::new(vec![Atom {call:Call::Table(2),args:vec![s(0),s(1)]}]);
        p.templates[0].ops=Arc::new(vec![Op::Let(2,Call::Table(2),vec![s(0)]),
            Op::Let(3,Call::Table(0),vec![s(1)]),Op::Set(1,vec![s(2),s(3)],unit())]);
        assert!(prove(&p,1,0,&[0,1]).is_some());
        let mut deleter=p.templates[0].clone();deleter.ops=Arc::new(vec![Op::Hide(2,vec![s(0)],true)]);
        p.templates.push(deleter);
        assert!(prove(&p,1,0,&[0,1]).is_none());
    }
    #[test]
    fn discovery_exports_values_without_manufacturing_a_constructor_receipt() {
        let mut p=fixture();
        let mut r=p.rules[0].clone();r.template=1;
        r.query=Rc::new(vec![Atom {call:Call::Table(1),args:vec![s(0),s(1),s(2)]}]);
        let mut t=p.templates[0].clone();
        t.ops=Arc::new(vec![Op::Let(3,Call::Table(0),vec![s(0)])]);
        t.defs=BTreeMap::from([(3,0)]);
        p.templates.push(t);p.rules.push(r);
        let found=discover(&p);
        assert_eq!(found.len(),1);
        assert_eq!((found[0].rule,found[0].operation,found[0].query_atom,found[0].result_slot),(1,0,0,1));
        assert_eq!(exports(&p).len(),1);
        // The only exported evidence is a value slot and all-writer proof.
        // It does not enable a runtime alias or claim the View witness is F.
        assert!(p.known_results.static_skip.is_empty());
    }
    #[test]
    fn rejects_unproved_initial_rows_deletion_and_future_construction() {
        let mut p=fixture();
        p.initial.push(json!({"table":"View"}));
        assert!(prove(&p,1,0,&[0,1]).is_none());p.initial.clear();
        Arc::make_mut(&mut p.templates[0].ops).push(Op::Hide(0,vec![s(0)],true));
        assert!(prove(&p,1,0,&[0,1]).is_none());
        p=fixture();Arc::make_mut(&mut p.templates[0].ops).swap(0,1);
        assert!(prove(&p,1,0,&[0,1]).is_none());
    }
    #[test]
    fn repeated_constructors_and_copies_share_actual_output_but_union_is_not_immediate() {
        let mut p=fixture();
        p.templates[0].ops=Arc::new(vec![Op::Let(1,Call::Table(0),vec![s(0)]),
            Op::Copy(2,s(0)),Op::Let(3,Call::Table(0),vec![s(2)]),Op::Set(1,vec![s(2),s(3)],unit())]);
        assert!(prove(&p,1,0,&[0,1]).is_some());
        p.templates[0].ops=Arc::new(vec![Op::Let(1,Call::Table(0),vec![s(0)]),
            Op::Union(s(1),s(2)),Op::Set(1,vec![s(0),s(2)],unit())]);
        assert!(prove(&p,1,0,&[0,1]).is_none());
    }
}
