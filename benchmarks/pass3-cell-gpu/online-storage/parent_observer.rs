//! Offline observer for already accepted source bindings. It cannot influence which rule wins.
use eggfuse_cell_runtime::{executor::{CellBindingObserver,CellResultObserver,Executor},graph::{Dependency,Graph},program::{Arg,Call,Op,Program},value::{Value,canon},transfer_audit};
use serde_json::json;
use std::{cell::RefCell,collections::{BTreeMap,BTreeSet},rc::Rc,path::PathBuf};
use std::io::Write;

fn address(w:Dependency)->(u8,u64){
    match w {Dependency::Fact(f)=>(0,(u64::from(f.cell)<<32)|u64::from(f.op)),Dependency::Function(i)=>(1,i as u64)}
}

fn resolve(a:&Arg,values:&BTreeMap<usize,Value>,g:&Graph)->Option<Value>{
    match a{Arg::Literal(v)=>Some(canon(v,&g.parents)),Arg::Slot(s)=>values.get(s).map(|v|canon(v,&g.parents))}
}

fn main()->Result<(),Box<dyn std::error::Error>>{
    let args=std::env::args_os().skip(1).collect::<Vec<_>>();if args.len()!=2{return Err("usage: parent_observer PROGRAM NEW_OUTPUT".into());}
    let p=Program::parse(serde_json::from_slice(&std::fs::read(&args[0])?)?)?;
    let out=PathBuf::from(&args[1]);std::fs::create_dir(&out)?;
    let g=Graph::new(p)?;
    let mut initial=Vec::new();
    for t in 0..g.program.tables.len(){for w in g.witnesses(t){let Some(row)=g.row(w)? else{continue};if !row.hidden{initial.push((t,address(w),row.epoch,row.values.as_ref().clone()));}}}
    let mut e=Executor::new(g,false);
    let lhs=Rc::new(RefCell::new(Vec::new()));let sink=lhs.clone();
    e.binding_observer=Some(CellBindingObserver{rules:vec![true;e.graph.program.rules.len()],observe:Box::new(move|run,ordinal,rid,slots,g|{
        let rule=&g.program.rules[rid];let mut env:BTreeMap<_,_>=slots.iter().map(|(s,v)|(*s,v.clone())).collect();
        let mut witnesses=vec![None;rule.query.len()];let mut reason=vec![0;rule.query.len()];
        // Only complete functional keys can establish a unique physical witness from an observed binding.
        // Perform these read-only probes on the source snapshot, before any sibling RHS publication.
        for _ in 0..rule.query.len(){
            let mut progress=false;
            for (pos,atom) in rule.query.iter().enumerate(){
                if witnesses[pos].is_some(){continue;}
                let Call::Table(t)=atom.call else{reason[pos]=1;continue};
                let Some((result,args))=atom.args.split_last() else{reason[pos]=2;continue};
                let Some(key)=args.iter().map(|a|resolve(a,&env,g)).collect::<Option<Vec<_>>>() else{reason[pos]=3;continue};
                let Ok(Some(row))=g.lookup(t,&key) else{reason[pos]=4;continue};
                if row.hidden {reason[pos]=5;continue;}
                let actual=row.values.last().unwrap();
                if let Some(expected)=resolve(result,&env,g){if &expected!=actual{reason[pos]=6;continue;}}
                else if let Arg::Slot(slot)=result{env.insert(*slot,actual.clone());}
                witnesses[pos]=Some((t,address(row.witness),row.epoch,row.values.as_ref().clone()));reason[pos]=0;progress=true;
            }
            if !progress{break;}
        }
        sink.borrow_mut().push(json!([run,ordinal,rid,witnesses,reason]));
    })});
    let calls=Rc::new(RefCell::new(Vec::new()));let sink=calls.clone();
    let candidates=Rc::new(RefCell::new(Vec::new()));let candidate_sink=candidates.clone();
    let slots=e.graph.program.rules.iter().map(|r|{
        let mut demanded=BTreeSet::new();
        for op in e.graph.program.templates[r.template].ops.iter(){
            match op{
                Op::Let(dst,Call::Table(t),args) if e.graph.program.tables[*t].constructor=>{
                    demanded.insert(*dst);
                    for a in args{if let Arg::Slot(s)=a{demanded.insert(*s);}}
                },
                Op::Set(_,args,value)=>{
                    for a in args.iter().chain(std::iter::once(value)){if let Arg::Slot(s)=a{demanded.insert(*s);}}
                },
                _=>()
            }
        }
        demanded.into_iter().collect::<Vec<_>>()
    }).collect();
    e.result_observer=Some(CellResultObserver{slots,observe:Box::new(move|run,rid,completed,values,g|{
        let r=&g.program.rules[rid];let env:BTreeMap<_,_>=values.into_iter().filter_map(|(s,v)|v.ok().map(|x|(s,x))).collect();
        let mut addresses=Vec::new();let mut proposed=Vec::new();
        if completed{
            for (index,op) in g.program.templates[r.template].ops.iter().enumerate(){
                let (t,args,result)=match op{
                    Op::Let(dst,Call::Table(t),args) if g.program.tables[*t].constructor=>(*t,args,Some(*dst)),
                    Op::Set(t,args,_) =>(*t,args,None),
                    _=>continue,
                };
                let Some(key)=args.iter().map(|a|resolve(a,&env,g)).collect::<Option<Vec<_>>>() else{continue};
                let Ok(Some(row))=g.lookup(t,&key) else{continue};
                if row.hidden{continue;}
                if let Some(dst)=result{
                    if env.get(&dst).map(|v|canon(v,&g.parents)).as_ref()!=row.values.last(){continue;}
                }
                if let Op::Set(_,_,value)=op{
                    if let Some(candidate)=resolve(value,&env,g){ proposed.push((index,t,address(row.witness),candidate)); }
                }
                addresses.push((index,t,address(row.witness),row.epoch,row.values.as_ref().clone()));
            }
        }
        sink.borrow_mut().push(json!([run,rid,completed,addresses]));candidate_sink.borrow_mut().push(proposed);
    })});
    transfer_audit::set_active(true);transfer_audit::enable_write_audit();transfer_audit::enable_events();transfer_audit::enable_set_input_observation();
    e.execute()?;
    let snap=e.report();let events=transfer_audit::take_events().ok_or("missing source events")?;
    let mut writer=std::io::BufWriter::new(std::fs::File::create(out.join("state.json"))?);
    e.graph.write_export(&mut writer)?;writer.flush()?;
    std::fs::write(out.join("candidates.json"),serde_json::to_vec(candidates.borrow().as_slice())?)?;
    std::fs::write(out.join("audit.json"),serde_json::to_vec(&json!({"rhs":transfer_audit::take_digests(),
        "writes":transfer_audit::take_write_digests(),"resumes":transfer_audit::take_resume_digests(),"events":events}))?)?;
    std::fs::write(out.join("references.json"),serde_json::to_vec(&json!({"initial":initial,"lhs":lhs.borrow().as_slice(),
        "effects":calls.borrow().as_slice(),"runs":e.steps.len(),"source":snap["program_sha256"]}))?)?;
    Ok(())
}
