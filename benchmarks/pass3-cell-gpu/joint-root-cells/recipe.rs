//! A recipe is issued alongside the chosen physical witnesses. Its projection instructions are
//! compiler data. Only the completed recipe can provide the owned inputs of a new primary Cell.
use crate::{cell::QueryFacts,graph::{Dependency,Graph},program::{Arg,Call,Program,Result},slots::Slots,value::Value};
use serde::{Deserialize,Serialize};
use serde_json::{json,Value as J};
use std::{cell::RefCell,collections::BTreeMap,rc::Rc};

#[derive(Clone,Debug,Serialize,PartialEq,Eq)]
struct Field{slot:usize,atom:usize,column:usize,kind:Option<usize>}
#[derive(Clone,Debug)]
struct Layout{rid:usize,template:usize,fields:Vec<Field>}
#[derive(Clone,Debug,Serialize)]
pub(crate) struct Ref{pub atom:usize,pub row:Dependency,pub version:u64}
#[derive(Clone,Debug)]
pub(crate) struct Recipe{wire:Rc<[u8]>}
#[derive(Clone,Debug)]
struct Decoded{serial:u64,origin:&'static str,run:u64,layout:Rc<Layout>,template:usize,refs:Vec<Ref>,ports:Vec<Field>}
fn write_word(bytes:&mut Vec<u8>,value:u64){bytes.extend_from_slice(&value.to_le_bytes());}
fn decode(packet:&Recipe)->Option<Decoded>{
    if packet.wire.len()%8!=0{return None;}
    let mut words=packet.wire.chunks_exact(8).map(|v|u64::from_le_bytes(v.try_into().unwrap()));
    if words.next()?!=0x31524345{return None;}
    let serial=words.next()?;let origin=match words.next()?{1=>"single",2=>"multi",_=>return None};
    let run=words.next()?;let rid=usize::try_from(words.next()?).ok()?;let template=usize::try_from(words.next()?).ok()?;
    let layout=STATE.with_borrow(|s|s.as_ref()?.layout.get(rid).cloned())?;
    let count=usize::try_from(words.next()?).ok()?;let width=usize::try_from(words.next()?).ok()?;
    if count.checked_add(width)?.checked_mul(4)?!=words.len() || width!=layout.fields.len(){return None;}
    let mut refs=Vec::with_capacity(count);
    for _ in 0..count{
        let atom=usize::try_from(words.next()?).ok()?;let tag=words.next()?;let id=words.next()?;let version=words.next()?;
        let row=match tag{1=>Dependency::Fact(crate::graph::FactRef{cell:(id>>32) as u32,op:id as u32}),
                          2=>Dependency::Function(usize::try_from(id).ok()?),_=>return None};
        refs.push(Ref{atom,row,version});
    }
    let mut ports=Vec::with_capacity(width);
    for _ in 0..width{
        let slot=usize::try_from(words.next()?).ok()?;let atom=usize::try_from(words.next()?).ok()?;
        let column=usize::try_from(words.next()?).ok()?;let table=words.next()?;
        let kind=if table==u64::MAX{None}else{Some(usize::try_from(table).ok()?)};
        ports.push(Field{slot,atom,column,kind});
    }
    Some(Decoded{serial,origin,run,layout,template,refs,ports})
}
#[derive(Clone,Debug)]
pub(crate) struct Bound{recipe:Decoded,values:Slots}
#[derive(Deserialize)]
pub struct Config{pub control:String,pub forbid_fallback:bool}
struct State{layout:Vec<Rc<Layout>>,mode:String,forbid:bool,serial:u64,ordinal:usize,active:Option<(usize,&'static str,u64,usize,usize)>,
             audit:bool,emitted:[u64;2],wire_bytes:u64,wire_hash:u64,sealed:u64,rejected:u64,applied:u64,allocated:u64,raw:u64,
             commits:Vec<J>,fresh:Vec<J>,fault:Option<J>}
thread_local!{static STATE:RefCell<Option<State>>=const{RefCell::new(None)};}
pub fn configure(program:&Program,data:Option<&[u8]>,audit:bool)->Result<()>{
    let Some(bytes)=data else{STATE.with_borrow_mut(|s|*s=None);return Ok(())};let c:Config=serde_json::from_slice(bytes).map_err(|e|e.to_string())?;
    if !matches!(c.control.as_str(),"use"|"withhold"|"wrong-template"|"wrong-port"|"shadow"){return Err("unknown root recipe control".into());}
    let mut layout=vec![];
    for (rid,rule) in program.rules.iter().enumerate(){
        let mut fields=Vec::new();
        for &slot in rule.inputs.iter(){
            // Prefer a table-backed occurrence. A primitive-only result is supplied by the checked primitive instruction.
            let field=rule.query.iter().enumerate().flat_map(|(atom,a)|a.args.iter().enumerate().filter_map(move |(column,arg)|
                matches!(arg,Arg::Slot(s) if *s==slot).then(||Field{slot,atom,column,kind:match a.call{Call::Table(t)=>Some(t),_=>None}})))
                .min_by_key(|f|(f.kind.is_none(),f.atom,f.column)).ok_or("RHS input lacks a source projection")?;
            fields.push(field);
        }
        layout.push(Rc::new(Layout{rid,template:rule.template,fields}));
    }
    STATE.with_borrow_mut(|s|*s=Some(State{layout,mode:c.control,forbid:c.forbid_fallback,serial:0,ordinal:0,active:None,audit,
        emitted:[0;2],wire_bytes:0,wire_hash:14695981039346656037,sealed:0,rejected:0,applied:0,allocated:0,raw:14695981039346656037,commits:vec![],fresh:vec![],fault:None}));Ok(())
}
pub(crate) fn issue(origin:&'static str,run:u64,rid:usize,refs:impl Iterator<Item=Ref>)->Option<Recipe>{
    STATE.with_borrow_mut(|s|{
        let state=s.as_mut()?;let layout=state.layout.get(rid)?.clone();
        state.serial+=1;state.emitted[usize::from(origin=="multi")]+=1;
        let mut refs:Vec<_>=refs.collect();
        // The immutable neural choice and its pre-check addresses are hashed before interventions.
        for word in [state.serial,run,rid as u64,layout.template as u64,refs.len() as u64]{state.raw=(state.raw^word).wrapping_mul(1099511628211);}
        for r in &refs {
            let (tag,id)=match r.row{Dependency::Fact(f)=>(1,(u64::from(f.cell)<<32)|u64::from(f.op)),Dependency::Function(i)=>(2,i as u64)};
            for word in [r.atom as u64,tag,id,r.version]{state.raw=(state.raw^word).wrapping_mul(1099511628211);}
        }
        if state.mode=="withhold"{return None;}
        let template=if state.mode=="wrong-template"{layout.template.wrapping_add(1)}else{layout.template};
        if state.mode=="wrong-port"{
            if let Some(r)=refs.first_mut(){r.version=r.version.wrapping_add(1);}
            else{refs.push(Ref{atom:usize::MAX,row:Dependency::Function(0),version:u64::MAX});}
        }
        let mut wire=Vec::with_capacity(64+32*(refs.len()+layout.fields.len()));
        for w in [0x31524345,state.serial,if origin=="single"{1}else{2},run,rid as u64,template as u64,refs.len() as u64,layout.fields.len() as u64]{
            write_word(&mut wire,w);
        }
        for r in refs{
            let (tag,id)=match r.row{Dependency::Fact(f)=>(1,(u64::from(f.cell)<<32)|u64::from(f.op)),Dependency::Function(i)=>(2,i as u64)};
            for word in [r.atom as u64,tag,id,r.version]{write_word(&mut wire,word);}
        }
        for f in &layout.fields{
            for word in [f.slot as u64,f.atom as u64,f.column as u64,f.kind.map_or(u64::MAX,|t|t as u64)]{write_word(&mut wire,word);}
        }
        state.wire_bytes+=wire.len() as u64;
        if state.audit{for v in wire.chunks_exact(8){state.wire_hash=(state.wire_hash^u64::from_le_bytes(v.try_into().unwrap())).wrapping_mul(1099511628211);}}
        Some(Recipe{wire:wire.into()})
    })
}
pub(crate) fn bind(input:Option<Recipe>,g:&Graph,rid:usize,known:&[Option<Dependency>],verified:&Slots)->Result<Option<Rc<Bound>>>{
    let Some(packet)=input else{return Ok(None)};
    let rejected=||{STATE.with_borrow_mut(|s|s.as_mut().unwrap().rejected+=1);Ok(None)};
    let Some(recipe)=decode(&packet) else{return rejected()};
    let rule=&g.program.rules[rid];
    if recipe.layout.rid!=rid||recipe.template!=rule.template||recipe.run!=g.epoch||recipe.ports!=recipe.layout.fields{return rejected();}
    let mut rows=BTreeMap::new();
    for reference in &recipe.refs{
        if known.get(reference.atom)!=Some(&Some(reference.row)){return rejected();}
        let Some(row)=g.row(reference.row)? else{return rejected()};
        if row.hidden||row.epoch!=reference.version||!matches!(rule.query[reference.atom].call,Call::Table(t) if t==row.table){return rejected();}
        rows.insert(reference.atom,row);
    }
    let mut fields=Vec::new();
    for f in &recipe.ports{
        let v=if let Some(t)=f.kind{
            if !rows.contains_key(&f.atom){
                let Some(w)=known.get(f.atom).and_then(|v|*v) else{return rejected()};
                let Some(row)=g.row(w)? else{return rejected()};rows.insert(f.atom,row);
            }
            let row=&rows[&f.atom];
            if row.hidden||row.table!=t{return rejected();}
            let Some(v)=row.values.get(f.column) else{return rejected()};v.clone()
        }else{
            let Some(v)=verified.get(&f.slot) else{return rejected()};v.clone()
        };
        if verified.get(&f.slot)!=Some(&v){return rejected();}
        fields.push((f.slot,v));
    }
    STATE.with_borrow_mut(|s|s.as_mut().unwrap().sealed+=1);
    Ok(Some(Rc::new(Bound{recipe,values:fields.into_iter().collect()})))
}
pub(crate) fn bind_single(input:Option<Recipe>,g:&Graph,rid:usize,known:&QueryFacts,verified:&Slots)->Result<Option<Rc<Bound>>>{
    if input.is_none(){return Ok(None);}
    let deps:Vec<_>=(0..g.program.rules[rid].query.len()).map(|i|known.receipt(i)).collect();
    bind(input,g,rid,&deps,verified)
}
pub(crate) fn consume(bound:Option<Rc<Bound>>,rid:usize,epoch:u64,source_template:usize,inputs:&mut Slots)->Result<usize>{
    STATE.with_borrow_mut(|s|{
        let Some(state)=s.as_mut()else{return Ok(source_template)};state.ordinal+=1;state.active=None;
        let Some(bound)=bound else{return Ok(source_template)};
        let r=&bound.recipe;
        if r.run!=epoch||r.layout.rid!=rid||r.template!=source_template||r.layout.fields.iter().any(|f|inputs.get(&f.slot)!=bound.values.get(&f.slot)){
            return Err("root recipe changed across source commit".into());
        }
        if state.mode=="shadow"{return Ok(source_template);}
        *inputs=bound.values.clone();state.applied+=1;
        state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));
        if state.audit{state.commits.push(json!([state.ordinal,r.origin,r.serial,rid,r.template,epoch,r.refs,bound.values]));}
        Ok(r.template)
    })
}
/// Called only on the actual primary RHS store branches, immediately before a physical frame is inserted.
pub(crate) fn fresh(id:u32,template:usize)->Result<()>{
    STATE.with_borrow_mut(|s|{
        let Some(s)=s.as_mut()else{return Ok(())};
        if let Some((ord,provider,serial,rid,selected))=s.active{
            if selected!=template{return Err("root allocation used a different recipe".into());}
            s.allocated+=1;if s.audit{s.fresh.push(json!([id,ord,rid,template,provider,serial]));}
        }else if s.forbid{
            s.fault=Some(json!([id,s.ordinal,template]));return Err(format!("no verified root recipe for fresh Cell {id} at RHS {} template {template}",s.ordinal));
        }
        Ok(())
    })
}
pub(crate) fn end(){STATE.with_borrow_mut(|s|if let Some(s)=s{s.active=None;});}
pub fn report()->J{
    STATE.with_borrow(|s|s.as_ref().map_or(J::Null,|s|json!({"mode":s.mode,"emitted":s.emitted,"raw_hash":s.raw.to_string(),"wire_bytes":s.wire_bytes,"wire_hash":s.wire_hash.to_string(),
        "sealed":s.sealed,"rejected":s.rejected,"applied":s.applied,"allocated":s.allocated,"commits":s.commits,"fresh":s.fresh,
        "rhs":s.ordinal,"fault":s.fault})))
}
