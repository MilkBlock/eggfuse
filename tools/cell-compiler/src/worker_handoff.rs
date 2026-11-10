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

// Share identical ordered scalar vectors (including table sets and masks).
// Preserve ordering; these are not approximate digests or equality proofs.
fn pack_forecast(mut value:Value)->Value {
    fn visit(v:&mut Value, ids:&mut std::collections::BTreeMap<String,usize>, arrays:&mut Vec<Value>) {
        match v {
            Value::Array(a) if a.iter().all(|x|x.is_number() || x.is_boolean()) => {
                let key=serde_json::to_string(v).unwrap();
                let id=if let Some(id)=ids.get(&key) {*id} else {
                    let id=arrays.len();ids.insert(key,id);arrays.push(v.clone());id
                };
                *v=json!({"vector":id});
            },
            Value::Array(a)=>for x in a {visit(x,ids,arrays)},
            Value::Object(o)=>for x in o.values_mut() {visit(x,ids,arrays)},
            _=>(),
        }
    }
    let mut vectors=vec![];
    visit(&mut value,&mut Default::default(),&mut vectors);
    json!({"vectors":vectors,"body":value})
}

pub fn compile(p: &Program) -> Value {
    let mut rules: Vec<_> = p.rules.iter().enumerate().map(|(rid,r)| {
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
            json!({"entry_route":table,"operation":op,"reads":slots(reads),"writes":write,"table":table,"kind":kind,
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
    let mut layouts=Vec::new();
    let mut by_template=std::collections::BTreeMap::new();
    for rule in &mut rules {
        let template=rule["template"].as_u64().unwrap();
        let object=rule.as_object_mut().unwrap();
        let mut effects=object.remove("effects").unwrap();
        for effect in effects.as_array_mut().unwrap() {
            let fields=effect.as_object_mut().unwrap();
            // Position is the operation ordinal; route is the table; kind
            // determines address semantics. Permission is global and false.
            for key in ["operation","entry_route","result_address","worker_execution_proved"] {fields.remove(key);}
        }
        let layout=json!({"effects":effects,
            "frame_slots":object.remove("frame_slots").unwrap(),
            "slot_definitions":object.remove("slot_definitions").unwrap()});
        let index=*by_template.entry(template).or_insert_with(|| {
            let index=layouts.len();layouts.push(layout);index
        });
        object.insert("layout".into(),json!(index));
        object.remove("required_order");object.remove("established_after");
    }
    // Tables own candidate routes once; effects refer to the shared route.
    let routes:Vec<_>=p.tables.iter().map(|table|
        p.artifact["entry_schedule"]["nodes"].as_array().into_iter().flatten()
            .filter(|node|node["table"]==table.name)
            .map(|node|node["id"].clone()).collect::<Vec<_>>()).collect();
    let mut contracts=p.iterative.state_contracts(p);
    for contract in contracts.as_array_mut().unwrap() {
        if contract["initial"]==true { continue; }
        // The exact program digest binds the rule's query, sorts and effects.
        // Preserve stage-specific pivot, proofs, transitions and retention.
        let pivot=contract["interface"]["pivot"].clone();
        let object=contract.as_object_mut().unwrap();
        object.remove("interface");object.remove("effects");object.remove("environment");
        object.insert("pivot".into(),pivot);
    }
    let completion=match eggfuse_cell_runtime::completion_plan::Plan::derive(p) {
        Ok(plan)=>json!({"status":"derived","plan":pack_forecast(serde_json::to_value(plan).unwrap())}),
        Err(error)=>json!({"status":"unsupported","reason":error}),
    };
    let mut result=json!({"schema":"eggfuse-worker-handoff/v3",
        "program":p.artifact["sha256"],"rules":rules,"layouts":layouts,
        "required_order":"original-rule-and-match-ordinal",
        "established_after":"successful-match-and-winner-selection",
        "worker_execution_proved":false,
        "stage_contracts":contracts,"entry_routes":routes,
        "completion_forecast":completion,
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn forecast_vectors_roundtrip_without_losing_order_or_masks() {
        fn expand(v:&Value, arrays:&Value)->Value {
            if let Some(i)=v.get("vector").and_then(Value::as_u64) {return arrays[i as usize].clone()}
            match v {
                Value::Array(a)=>Value::Array(a.iter().map(|x|expand(x,arrays)).collect()),
                Value::Object(o)=>Value::Object(o.iter().map(|(k,x)|(k.clone(),expand(x,arrays))).collect()),
                _=>v.clone(),
            }
        }
        let original=json!({"a":[1,2],"b":[1,2],"c":[2,1],"d":[true,false],"empty":[]});
        let packed=pack_forecast(original.clone());
        assert_eq!(packed["vectors"].as_array().unwrap().len(),4);
        assert_eq!(expand(&packed["body"],&packed["vectors"]),original);
    }
}
