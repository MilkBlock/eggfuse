"""Add a verification-first physical child allocator to a private joint Rust build."""
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent

def replace(path,before,after):
    s=path.read_text()
    if s.count(before)!=1:raise ValueError((path.name,before[:64],s.count(before)))
    path.write_text(s.replace(before,after))

def install(crate):
    src=Path(crate)/'src'
    shutil.copy2(HERE/'child.rs',src/'joint_merge.rs')
    with (src/'lib.rs').open('a') as f:f.write('\npub mod joint_merge;\n')
    native_multi=src/'ordinary_witness.rs'
    replace(native_multi,'struct Ticket {run:usize,rule:usize,','struct Ticket {local_token_id:usize,run:usize,rule:usize,')
    replace(native_multi,'self.tickets.push(Ticket{run:self.run,','self.tickets.push(Ticket{local_token_id:self.tickets.len()+1,run:self.run,')
    with (src/'single_witness.rs').open('a') as f:f.write('\nimpl Mark { pub(crate) fn sealed_token_id(&self)->u64 {self.token.id} }\n')
    replace(src/'runtime.rs','        crate::ordinary_witness::commit(b.ordinary_id,rid);','''        crate::ordinary_witness::commit(b.ordinary_id,rid);
        crate::joint_merge::begin(rid,self.graph.epoch,b.known.neural().map(|m|m.sealed_token_id()),b.ordinary_id);''')
    replace(src/'runtime.rs','        self.graph.joint_issuer=None;','''        crate::joint_merge::end();
        self.graph.joint_issuer=None;''')
    g=src/'graph.rs'
    anchor='            let index = self.set_function_from(t, &key, value, Some((cell, op, source)))?;'
    replace(g,anchor,'''            crate::joint_merge::issue(self,cell,op,t,&key,&value)?;
'''+anchor+'''
            crate::joint_merge::finish();''')
    # The accepted packet is the allocator input. The default source implementation is reachable
    # only when there is no valid child; no post-commit tagging of the default allocator is used.
    code=g.read_text();a=code.index('    pub fn dynamic_construct(');b=code.index('        if let Some(row) = self.lookup_canonical(t, &key)? {',a)
    code=code[:b]+'''        if let Some(packet)=crate::joint_merge::take(self,t,&key)?{
            if let Some(existing)=self.lookup_canonical(packet.table,&packet.arguments)?{
                crate::joint_merge::allocated(packet.id,None);
                return Ok(existing.values.last().unwrap().clone());
            }
            let columns=packet.arguments.iter().cloned().enumerate().collect();
            let id=self.linked_slots(packet.template,columns,None)?;
            self.stats.constructor_requests+=1;
            let result=self.insert_constructor(id,0,packet.table,&packet.arguments,packet.arguments.len())?;
            crate::joint_merge::allocated(packet.id,Some(id));
            return Ok(result);
        }
'''+code[b:];anchor='''        let dst = args.as_ref().len();
        let cell = self.linked_slots('''
    assert code.count(anchor)==1
    code=code.replace(anchor,'''        crate::joint_merge::allow_default_fresh(t)?;
'''+anchor)
    g.write_text(code)
    session=Path(crate)/'examples/joint_witness_session.rs'
    replace(session,'            writeln!(out, "{}", failure)?;', '''            failure["merge_child"]=eggfuse_cell_runtime::joint_merge::report();
            writeln!(out, "{}", failure)?;''')
    marker='        let initial_cells = runtime.graph.stats.cells_created;'
    replace(session,marker,'''        let merge_config=req["merge_config"].as_str().map(std::fs::read).transpose()?;
        eggfuse_cell_runtime::joint_merge::configure(&program,merge_config.as_deref(),audit)?;
'''+marker)
    replace(session,'        if audit {\n            transfer_audit::set_active(false);','''        report["merge_child"]=eggfuse_cell_runtime::joint_merge::report();
        if audit {
            transfer_audit::set_active(false);''')
