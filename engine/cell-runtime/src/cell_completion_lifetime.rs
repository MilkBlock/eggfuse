//! A conservative completed-state projection derived from authoritative readers.
//! No runtime fact graph: this is a list of original Cell slot numbers.
use crate::program::{Arg,Op,Program};
use std::collections::BTreeSet;
fn retained_slots(p:&Program,rid:usize)->Option<Box<[usize]>> {
    let rule=&p.rules[rid];
    let t=&p.templates[rule.template];
    let mut used=BTreeSet::new();
    let mut pending=Vec::new();
    let mut read=|arg:&Arg| {if let Arg::Slot(s)=arg {pending.push(*s);}};
    // Completed facts (including retired facts retained by a child) can still
    // read their recipe columns. Completed scalar/equality/visibility effects
    // cannot read their old operands again.
    for op in t.ops.iter() {
        match op {
            Op::Let(dst,crate::program::Call::Table(_),args)=>{
                read(&Arg::Slot(*dst));args.iter().for_each(&mut read);
            },
            Op::Set(_,args,v)=>{args.iter().for_each(&mut read);read(v);},
            _=>{},
        }
    }
    // Existing Entries may read producer query inputs, not only RHS columns.
    for route in p.multi_stage.routes.values().filter(|r|r.producer==rid) {
        for field in route.reads.iter().flat_map(|r|r.columns.iter()) {read(field);}
    }
    let aliases=p.known_results.static_slots.get(rule.template)?;
    while let Some(slot)=pending.pop() {
        if !used.insert(slot) {continue;}
        // Copies are lazy. Constructor aliases can point to a real matched
        // result owned by another Cell and must never become synthetic IDs.
        let source=aliases.get(slot).and_then(Option::as_ref).or_else(|| {
            let op=t.ops.get(*t.defs.get(&slot)?)?;
            if let Op::Copy(_,arg)=op {Some(arg)} else {None}
        });
        if let Some(Arg::Slot(source))=source {pending.push(*source);}
    }
    Some(used.into_iter().collect::<Vec<_>>().into_boxed_slice())
}
pub(crate) fn parent_layout(p:&Program,rid:usize)->Option<Box<[usize]>> {
    let rule=&p.rules[rid];
    let t=&p.templates[rule.template];
    if t.parent_columns.is_empty() {return None;}
    let used=retained_slots(p,rid)?;
    // This is the complete remaining read obligation, not an all-or-nothing
    // promise that every value has a local symbolic provider. The runtime may
    // retain only the uncovered actual values before releasing the parent.
    Some(t.parent_columns.keys().filter(|s|used.binary_search(s).is_ok())
        .copied().collect::<Vec<_>>().into_boxed_slice())
}

/// Retire dead execution state after result capture; live recipes remain readable.
pub(crate) fn dead_slots(p:&Program,rid:usize)->Option<Box<[usize]>> {
    let live=retained_slots(p,rid)?;
    let mut dead=(0..p.templates[p.rules[rid].template].sorts.len()).filter(|s|live.binary_search(s).is_err()).collect::<Vec<_>>();
    dead.sort_unstable();dead.dedup();
    (!dead.is_empty()).then(||dead.into_boxed_slice())
}

/// Stable constructor operands are the authoritative copies of completed scalar
/// bindings. Keep all possible local providers: an RHS may reuse a foreign node.
pub(crate) fn scalar_layout(p:&Program,rid:usize)->Box<[(usize,u32,usize)]> {
    let rule=&p.rules[rid];
    // Slot reads address a template; do not assume arbitrary rule/template IDs coincide.
    if rule.template!=rid {return Box::default();}
    let t=&p.templates[rule.template];
    let mut fields=BTreeSet::new();
    for (op,instruction) in t.ops.iter().enumerate() {
        let Op::Let(_,crate::program::Call::Table(table),args)=instruction else {continue;};
        if !p.tables[*table].constructor {continue;}
        for (col,arg) in args.iter().enumerate() {
            let mut arg=arg;
            for _ in 0..t.sorts.len() {
                let Arg::Slot(slot)=arg else {break;};
                if !matches!(t.sorts[*slot]["kind"].as_str(),Some("i64"|"bool"|"f64"|"String")) {break;}
                fields.insert((*slot,op as u32,col));
                let source=p.known_results.static_slots[rule.template].get(*slot).and_then(Option::as_ref)
                    .or_else(|| match t.ops.get(*t.defs.get(slot)?)? {Op::Copy(_,a)=>Some(a),_=>None});
                let Some(source)=source else {break;};arg=source;
            }
        }
    }
    fields.into_iter().collect::<Vec<_>>().into_boxed_slice()
}
