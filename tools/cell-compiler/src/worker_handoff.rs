//! Checked preparation for worker-to-RHS/Entry ownership transfer.
//! This sidecar grants no execution permission; ordinary instructions and Run
//! boundaries remain authoritative. Consumers must validate before using it.
use eggfuse_cell_runtime::{program::{Program, Op, Call, Arg}, checksum::artifact_digest};
use serde_json::{Value, json};
use std::collections::BTreeSet;

fn slots(args: impl IntoIterator<Item=Arg>) -> Vec<usize> {
    args.into_iter().filter_map(|a| if let Arg::Slot(s)=a {Some(s)} else {None})
        .collect::<BTreeSet<_>>().into_iter().collect()
}

pub fn compile(p: &Program) -> Value {
    let rules: Vec<_> = p.rules.iter().enumerate().map(|(rid,r)| {
        let t=&p.templates[r.template];
        let effects:Vec<_>=t.ops.iter().enumerate().map(|(op,ins)| {
            let (reads,write,table,kind)=match ins {
                Op::Copy(dst,a)=>(vec![a.clone()],Some(*dst),None,"copy"),
                Op::Let(dst,Call::Primitive(..),args)=>(args.clone(),Some(*dst),None,"primitive"),
                Op::Let(dst,Call::Table(table),args)=>(args.clone(),Some(*dst),Some(*table),
                    if p.tables[*table].constructor {"constructor"} else {"mutable-read"}),
                Op::Set(table,args,value)=>{let mut a=args.clone();a.push(value.clone());(a,None,Some(*table),"set")},
                Op::Union(a,b)=>(vec![a.clone(),b.clone()],None,None,"union"),
                Op::Hide(table,args,_)=>(args.clone(),None,Some(*table),"hide"),
                Op::Panic=>(vec![],None,None,"panic"),
            };
            let entries:Vec<_>=table.into_iter().flat_map(|table|
                p.artifact["entry_schedule"]["nodes"].as_array().into_iter().flatten()
                    .filter(move |node|node["table"]==p.tables[table].name)
                    .map(|node|node["id"].clone())).collect();
            json!({"entry_candidates":entries,"operation":op,"reads":slots(reads),"writes":write,"table":table,"kind":kind,
                "result_address":match ins { Op::Let(_,Call::Table(_),_) | Op::Set(..) => Some("actual-returned-receipt"), Op::Copy(..) | Op::Let(_,Call::Primitive(..),_) => Some("local-slot"), _=>None },
                "worker_execution_proved":false})
        }).collect();
        let used:BTreeSet<_>=effects.iter().flat_map(|e|e["reads"].as_array().unwrap().iter().map(|v|v.as_u64().unwrap() as usize)).collect();
        json!({"rule":rid,"template":r.template,"frame_slots":t.sorts.len(),
            "matched_input_slots":r.inputs.as_ref(),
            "rhs_input_slots":r.inputs.iter().filter(|s|used.contains(s)).collect::<Vec<_>>(),
            "slot_definitions":t.defs,
            "effects":effects,
            "required_order":"original-rule-and-match-ordinal",
            "established_after":"successful-match-and-winner-selection"})
    }).collect();
    let mut result=json!({"schema":"eggfuse-worker-handoff/v1",
        "program":p.artifact["sha256"],"rules":rules,
        "stage_contracts":p.iterative.state_contracts(p),
        "obligations":["residual-enumeration","winner-and-delta-ownership","original-run-and-effect-order",
            "current-equality","mutable-read-validity","visibility","retirement-and-generation",
            "actual-constructor-receipt","cross-thread-ownership"],
        "authority":"preparation-only; no query, effect or publication may be elided solely from this sidecar"});
    result["entry_schedule"]=p.artifact["entry_schedule"].clone();
    result["sha256"]=artifact_digest(&result).into();
    result
}

pub fn validate(p:&Program, raw:&Value) -> Result<(),String> {
    if *raw==compile(p) {Ok(())} else {Err("worker handoff differs from checked Cell instructions/catalog".into())}
}
