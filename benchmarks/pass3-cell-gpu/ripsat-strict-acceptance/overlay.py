"""Read actual returned FactRefs on diagnostic Runs. Leave original authorization and execution intact."""
def replace(path,old,new):
    txt=path.read_text()
    if txt.count(old)!=1:raise ValueError((path,old))
    path.write_text(txt.replace(old,new))


def install(crate):
    src=crate/'src';p=src/'strict_named.rs'
    with p.open('a') as f:
        f.write('''
pub(crate) fn inspected_return(g:&Graph,op:usize,w:Dependency,kind:&str){
    let Some((rid,serial,_))=crate::joint_root::staging_identity() else{return;};
    let record=S.with_borrow(|v|v.as_ref().is_some_and(|s|s.record_links && s.links.last().is_some_and(|r|r[0]==serial)));
    if record{crate::transfer_audit::event(||json!(["observed-signed-return",serial,rid,g.epoch,op,w,g.visible_epoch(w),kind]));}
}
''')
    p=src/'runtime.rs'
    old='            if self.graph.known_stats.elide_static(aliases, i) {'
    replace(p,old,old+'''
                crate::strict_named::inspected_static_alias(i);''')
    with (src/'strict_named.rs').open('a') as f:
        f.write('''
pub(crate) fn inspected_static_alias(op:usize){
    let Some((rid,serial,_))=crate::joint_root::staging_identity() else{return;};
    if S.with_borrow(|v|v.as_ref().is_some_and(|s|s.record_links && s.links.last().is_some_and(|r|r[0]==serial))){
        crate::transfer_audit::event(||json!(["observed-signed-static-alias",serial,rid,op]));
    }
}
''')
    g=src/'graph.rs'
    old='            self.stats.constructor_reused += 1;\n\n            let value = row.values.last().unwrap().clone();'
    replace(g,old,'            crate::strict_named::inspected_return(self,op,row.witness,"let-intern-hit");\n'+old)
    old='        if let Some(old) = self.lookup_canonical(t, &key)? {'
    replace(g,old,old+'\n            crate::strict_named::inspected_return(self,op,old.witness,"set-existing-row");')
    # Handle an actually selected handoff at the point where the physical witness
    # is about to be returned by the (already existing) checked source operation.
    p=src/'cell_handoff.rs'
    old='        receipts.record_handoff(input.op, witness, input, original, g.program.iterative.tracks_slots());'
    replace(p,old,'        crate::strict_named::inspected_return(g,input.op,witness,"verified-handoff");\n'+old)
