//! A conservative completed-state projection derived from authoritative readers.
//! No runtime fact graph: this is a list of original Cell slot numbers.
use crate::program::{Arg,Op,Program};
use std::collections::BTreeSet;
fn retained_slots(p:&Program,rid:usize)->Option<Box<[usize]>> {
    let rule=&p.rules[rid];
    let t=&p.templates[rule.template];
    let mut used=BTreeSet::new();
    let mut read=|arg:&Arg| {if let Arg::Slot(s)=arg {used.insert(*s);}};
    for op in t.ops.iter() {
        match op {
            Op::Copy(dst,a)=>{read(&Arg::Slot(*dst));read(a);},
            Op::Let(dst,_,args)=>{read(&Arg::Slot(*dst));args.iter().for_each(&mut read);},
            Op::Hide(_,args,_)=>args.iter().for_each(&mut read),
            Op::Set(_,args,v)=>{args.iter().for_each(&mut read);read(v);},
            Op::Union(a,b)=>{read(a);read(b);},
            Op::Panic=>{},
        }
    }
    // A constructor result may be a captured query result, not its synthetic
    // Cell-local address. Include aliases even if the result is never a key.
    for arg in p.known_results.static_slots.get(rule.template)?.iter().flatten() {read(arg);}
    // Existing cross-stage readers can project producer query inputs directly.
    for route in p.multi_stage.routes.values().filter(|r|r.producer==rid) {
        for field in route.reads.iter().flat_map(|r|r.columns.iter()) {read(field);}
    }
    Some(used.into_iter().collect::<Vec<_>>().into_boxed_slice())
}
pub(crate) fn parent_layout(p:&Program,rid:usize)->Option<Box<[usize]>> {
    let rule=&p.rules[rid];
    let t=&p.templates[rule.template];
    if t.parent_columns.is_empty() {return None;}
    let used=retained_slots(p,rid)?;
    let ports=&p.cell_ownership.markers.get(rule.template)?.program.slots;
    let mut retained=Vec::new();
    for &slot in t.parent_columns.keys().filter(|s|used.binary_search(s).is_ok()) {
        ports.get(slot).copied().flatten()?;
        retained.push(slot);
    }
    Some(retained.into_boxed_slice())
}

/// Store only proven dead matched inputs, not another copy of every live slot.
pub(crate) fn dead_inputs(p:&Program,rid:usize)->Option<Box<[usize]>> {
    let live=retained_slots(p,rid)?;
    let mut dead=p.rules[rid].inputs.iter().copied().filter(|s|live.binary_search(s).is_err()).collect::<Vec<_>>();
    dead.sort_unstable();dead.dedup();
    (!dead.is_empty()).then(||dead.into_boxed_slice())
}
