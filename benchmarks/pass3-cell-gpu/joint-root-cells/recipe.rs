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
#[derive(Clone,Copy,Default,Deserialize,Serialize)]
#[serde(rename_all="snake_case")]
pub enum Encoding { #[default] Full, SharedWire, Resident, CheckedSlots }

#[derive(Clone,Debug)]
pub(crate) struct Recipe(Body);
#[derive(Clone,Debug)]
enum Body {
    Full(Rc<[u8]>),
    SharedWire { layout: Rc<Layout>, bytes: Rc<[u8]> },
    Resident(Rc<Decoded>),
}
#[derive(Clone,Debug)]
struct Decoded{serial:u64,origin:&'static str,run:u64,layout:Rc<Layout>,template:usize,refs:Vec<Ref>,ports:Option<Vec<Field>>}
fn write_word(bytes:&mut Vec<u8>,value:u64){bytes.extend_from_slice(&value.to_le_bytes());}
fn decode(packet:&Recipe)->Option<Decoded>{
    let (bytes,shared)=match &packet.0{
        Body::Full(bytes)=>(bytes,None),
        Body::SharedWire{layout,bytes}=>(bytes,Some(layout)),
        Body::Resident(decoded)=>return Some((**decoded).clone()),
    };
    if bytes.len()%8!=0{return None;}
    let mut words=bytes.chunks_exact(8).map(|v|u64::from_le_bytes(v.try_into().unwrap()));
    if words.next()?!=if shared.is_some(){0x32524345}else{0x31524345}{return None;}
    let serial=words.next()?;let origin=match words.next()?{1=>"single",2=>"multi",_=>return None};
    let run=words.next()?;let rid=usize::try_from(words.next()?).ok()?;let template=usize::try_from(words.next()?).ok()?;
    let layout=STATE.with_borrow(|s|s.as_ref()?.layout.get(rid).cloned())?;
    if shared.is_some_and(|cached|!Rc::ptr_eq(cached,&layout)){return None;}
    let count=usize::try_from(words.next()?).ok()?;
    let width=if shared.is_some(){0}else{usize::try_from(words.next()?).ok()?};
    if count.checked_add(width)?.checked_mul(4)?!=words.len() || (shared.is_none() && width!=layout.fields.len()){return None;}
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
    Some(Decoded{serial,origin,run,layout,template,refs,ports:shared.is_none().then_some(ports)})
}
#[derive(Clone,Debug)]
pub(crate) struct Bound{recipe:Decoded,values:BoundValues}
#[derive(Clone,Debug)]
enum BoundValues { Retained(Slots), TakeOnce(RefCell<Option<Slots>>) }
impl BoundValues {
    fn deliver(&self)->Result<Slots>{
        match self{
            Self::Retained(values)=>Ok(values.clone()),
            Self::TakeOnce(values)=>values.borrow_mut().take().ok_or_else(||"consumed root recipe reused".into())
        }
    }
}
#[derive(Deserialize)]
pub struct Config{pub control:String,pub forbid_fallback:bool,#[serde(default)]pub encoding:Encoding}
struct State{encoding:Encoding,layout:Vec<Rc<Layout>>,mode:String,forbid:bool,serial:u64,ordinal:usize,active:Option<(usize,&'static str,u64,usize,usize)>,
             decodes:u64,header_checks:u64,slot_transfers:u64,
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
    STATE.with_borrow_mut(|s|*s=Some(State{encoding:c.encoding,layout,mode:c.control,forbid:c.forbid_fallback,serial:0,ordinal:0,active:None,audit,
        decodes:0,header_checks:0,slot_transfers:0,emitted:[0;2],wire_bytes:0,wire_hash:14695981039346656037,sealed:0,rejected:0,applied:0,allocated:0,raw:14695981039346656037,commits:vec![],fresh:vec![],fault:None}));Ok(())
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
        if matches!(state.encoding,Encoding::Resident|Encoding::CheckedSlots){
            return Some(Recipe(Body::Resident(Rc::new(Decoded{serial:state.serial,origin,run,layout,template,refs,ports:None}))));
        }
        let shared=matches!(state.encoding,Encoding::SharedWire);
        let field_count=if shared{0}else{layout.fields.len()};
        let mut wire=Vec::with_capacity(64+32*(refs.len()+field_count));
        for w in [if shared{0x32524345}else{0x31524345},state.serial,if origin=="single"{1}else{2},run,rid as u64,template as u64,refs.len() as u64]{
            write_word(&mut wire,w);
        }
        if !shared{write_word(&mut wire,layout.fields.len() as u64);}
        for r in refs{
            let (tag,id)=match r.row{Dependency::Fact(f)=>(1,(u64::from(f.cell)<<32)|u64::from(f.op)),Dependency::Function(i)=>(2,i as u64)};
            for word in [r.atom as u64,tag,id,r.version]{write_word(&mut wire,word);}
        }
        for f in layout.fields.iter().take(field_count){
            for word in [f.slot as u64,f.atom as u64,f.column as u64,f.kind.map_or(u64::MAX,|t|t as u64)]{write_word(&mut wire,word);}
        }
        state.wire_bytes+=wire.len() as u64;
        if state.audit{for v in wire.chunks_exact(8){state.wire_hash=(state.wire_hash^u64::from_le_bytes(v.try_into().unwrap())).wrapping_mul(1099511628211);}}
        let bytes=wire.into();
        Some(Recipe(if shared{Body::SharedWire{layout,bytes}}else{Body::Full(bytes)}))
    })
}
pub(crate) fn bind(input:Option<Recipe>,g:&Graph,rid:usize,known:&[Option<Dependency>],verified:&Slots)->Result<Option<Rc<Bound>>>{
    let Some(packet)=input else{return Ok(None)};
    let rejected=||{STATE.with_borrow_mut(|s|s.as_mut().unwrap().rejected+=1);Ok(None)};
    let Some(recipe)=decode(&packet) else{return rejected()};
    let rule=&g.program.rules[rid];
    if recipe.layout.rid!=rid||recipe.template!=rule.template||recipe.run!=g.epoch||recipe.ports.as_ref().is_some_and(|fields|fields!=&recipe.layout.fields){return rejected();}
    if matches!(packet.0,Body::Resident(_)) && !STATE.with_borrow(|s|s.as_ref()
        .and_then(|state|state.layout.get(rid)).is_some_and(|current|Rc::ptr_eq(current,&recipe.layout))){return rejected();}
    let share_checked=STATE.with_borrow(|s|s.as_ref().is_some_and(|state|matches!(state.encoding,Encoding::CheckedSlots)));
    if share_checked{
        // known and verified are the receipts and slot environment returned by the
        // exact source matcher on this same immutable Graph view. The compiled
        // layout attests that each projected slot is that atom/column's variable.
        // Bind the recipe's input buffer from these already checked projections.
        let mut checks=0;
        for reference in &recipe.refs{
            if known.get(reference.atom)!=Some(&Some(reference.row)){return rejected();}
            if g.visible_epoch(reference.row)!=Some(reference.version){return rejected();}
            let Some(atom)=rule.query.get(reference.atom) else{return rejected()};
            if !matches!(atom.call,Call::Table(t) if Some(t)==g.live_table(reference.row)){return rejected();}
            checks+=1;
        }
        let mut values=Slots::default();
        for field in &recipe.layout.fields{
            if let Some(table)=field.kind{
                let Some(source)=known.get(field.atom).and_then(|w|*w) else{return rejected()};
                if g.live_table(source)!=Some(table) || g.visible_epoch(source).is_none(){return rejected();}
                checks+=1;
            }
            let Some(value)=verified.get(&field.slot) else{return rejected()};
            values.insert(field.slot,value.clone());
        }
        STATE.with_borrow_mut(|s|{let s=s.as_mut().unwrap();s.sealed+=1;s.header_checks+=checks;});
        return Ok(Some(Rc::new(Bound{recipe,values:BoundValues::TakeOnce(RefCell::new(Some(values)))})));
    }
    let mut rows=BTreeMap::new();
    let mut decodes=0;
    for reference in &recipe.refs{
        if known.get(reference.atom)!=Some(&Some(reference.row)){return rejected();}
        let Some(row)=g.row(reference.row)? else{return rejected()};
        if row.hidden||row.epoch!=reference.version||!matches!(rule.query[reference.atom].call,Call::Table(t) if t==row.table){return rejected();}
        rows.insert(reference.atom,row);decodes+=1;
    }
    let mut fields=Vec::new();
    for f in recipe.ports.as_ref().unwrap_or(&recipe.layout.fields){
        let v=if let Some(t)=f.kind{
            if !rows.contains_key(&f.atom){
                let Some(w)=known.get(f.atom).and_then(|v|*v) else{return rejected()};
                let Some(row)=g.row(w)? else{return rejected()};rows.insert(f.atom,row);decodes+=1;
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
    STATE.with_borrow_mut(|s|{let s=s.as_mut().unwrap();s.sealed+=1;s.decodes+=decodes;});
    Ok(Some(Rc::new(Bound{recipe,values:BoundValues::Retained(fields.into_iter().collect())})))
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
        let values=bound.values.deliver()?;
        if r.run!=epoch||r.layout.rid!=rid||r.template!=source_template||r.layout.fields.iter().any(|f|inputs.get(&f.slot)!=values.get(&f.slot)){
            return Err("root recipe changed across source commit".into());
        }
        if state.mode=="shadow"{return Ok(source_template);}
        *inputs=values;state.applied+=1;if matches!(state.encoding,Encoding::CheckedSlots){state.slot_transfers+=1;}
        state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));
        if state.audit{state.commits.push(json!([state.ordinal,r.origin,r.serial,rid,r.template,epoch,r.refs,inputs]));}
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
    STATE.with_borrow(|s|s.as_ref().map_or(J::Null,|s|json!({"root_row_decodes":s.decodes,"root_header_checks":s.header_checks,"owned_slot_transfers":s.slot_transfers,"encoding":s.encoding,"mode":s.mode,"emitted":s.emitted,"raw_hash":s.raw.to_string(),"wire_bytes":s.wire_bytes,"wire_hash":s.wire_hash.to_string(),
        "sealed":s.sealed,"rejected":s.rejected,"applied":s.applied,"allocated":s.allocated,"commits":s.commits,"fresh":s.fresh,
        "rhs":s.ordinal,"fault":s.fault})))
}
