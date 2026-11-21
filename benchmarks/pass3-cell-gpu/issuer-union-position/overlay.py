from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def rep(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    src=crate/'src'
    p=src/'lib.rs';p.write_text(p.read_text()+'\npub mod issuer_union;\n')
    copyfile(HERE/'position.rs',src/'issuer_union.rs')
    p=src/'joint_root.rs';s=p.read_text()
    a='        let Some(state)=s.as_mut()else{return Ok(source_template)};state.ordinal+=1;state.active=None;'
    s=rep(s,a,'        crate::issuer_union::end_root();\n'+a)
    anchor='        state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));'
    s=rep(s,anchor,anchor+'\n        crate::issuer_union::committed(rid,r.serial,state.ordinal,inputs);')
    anchor='pub(crate) fn end(){STATE.with_borrow_mut'
    s=rep(s,anchor,'pub(crate) fn end(){crate::issuer_union::end_root();STATE.with_borrow_mut')
    s+='''\npub(crate) fn observe_single_union(g:&Graph,rid:usize,packet:&Option<Recipe>)->Result<()> {
        let Some(packet)=packet else{return Ok(())};
        let r=decode(packet).ok_or("missing union position recipe")?;
        if r.layout.rid!=rid || r.run!=g.epoch {return Err("foreign union position recipe".into())}
        crate::issuer_union::offer(g,rid,r.serial,&r.refs)
    }
    pub(crate) fn observe_multi_union(g:&Graph,rid:usize,page:&MultiPage)->Result<()> {
        for i in 0..page.count(){crate::issuer_union::offer(g,rid,page.0.first_serial+i as u64,page.parents(i))?;}
        Ok(())
    }\n'''
    p.write_text(s)
    p=src/'single_witness.rs';s=p.read_text();a='};self.work[0]+=n as u64;'
    p.write_text(rep(s,a,'''};if crate::issuer_union::interested(rid) {
            for (t,_,send) in &offers {if *send {crate::joint_root::observe_single_union(g,rid,&t.recipe)?;}}
            crate::issuer_union::seal();
        }self.work[0]+=n as u64;'''))
    p=src/'ordinary_witness.rs';s=p.read_text()
    a='                for page in pages{'
    p.write_text(rep(s,a,'''                if crate::issuer_union::interested(rid) {
                    for page in &pages {crate::joint_root::observe_multi_union(g,rid,page)?;}
                    crate::issuer_union::seal();
                }
'''+a))
    p=src/'cell_eval.rs';a='                g.enqueue_source_union(a, b)?;'
    p.write_text(rep(p.read_text(),a,'                if crate::issuer_union::enabled(){\n                    if let Some(cell)=g.cells.get(&self.cell){crate::issuer_union::explicit(self.cell,cell.template,op);}\n                    else{crate::issuer_union::tag("unidentified_explicit");}\n                }\n'+a))
    p=src/'graph.rs';s=p.read_text()
    a='                    self.enqueue_source_union(a, b)?;'
    s=rep(s,a,'                    crate::issuer_union::explicit(cell,template,op);\n'+a)
    a='        self.pending_unions.push((a, b));'
    s=rep(s,a,'        crate::issuer_union::queued(a,b);\n'+a)
    a='    fn union(&mut self, a: u64, b: u64) -> Result<()> {'
    s=rep(s,a,a+'\n        let original=(a,b);')
    start=s.index(a);mark='        if a == b {';i=s.index(mark,start)
    s=s[:i]+'''        if crate::issuer_union::enabled(){crate::issuer_union::before(self,original,(a,b),if a==b{0}else{self.uses.get(&a.max(b)).map_or(0,|r|r.len())})?;}
'''+s[i:]
    a='        let displaced = affected.len();'
    s=rep(s,a,a+'\n        crate::issuer_union::original_reader_count(displaced)?;')
    mark='                self.enqueue_union(old.values.last().unwrap().clone(), value)?'
    s=rep(s,mark,'                crate::issuer_union::tag("constructor_set");\n'+mark)
    mark='            self.enqueue_union(\n                result.unwrap_or_else'
    s=rep(s,mark,'            crate::issuer_union::tag("constructor_collision");\n'+mark)
    p.write_text(s)
    p=src/'cell_prefix.rs';s=p.read_text();a='if changed { self.enqueue_union(value.clone(), rhs)?; }'
    p.write_text(rep(s,a,'if changed { crate::issuer_union::tag("prefix_constructor_set"); self.enqueue_union(value.clone(), rhs)?; }'))
    p=src/'cell_handoff.rs';s=p.read_text();a='else { g.enqueue_union(value.clone(), rhs)?; }'
    p.write_text(rep(s,a,'else { crate::issuer_union::tag("continuation_constructor_set"); g.enqueue_union(value.clone(), rhs)?; }'))
    p=src/'union_digest.rs';a='                self.enqueue_union(result, other_result)?;'
    p.write_text(rep(p.read_text(),a,'                crate::issuer_union::tag("digest_constructor_collision");\n'+a))
    p=src/'repair_cells.rs';a='                    self.enqueue_union(value(a), value(b))?;'
    p.write_text(rep(p.read_text(),a,'                    crate::issuer_union::tag("repair_variant");\n'+a))
    p=crate/'examples/joint_witness_session.rs';s=p.read_text();a='        let initial_cells = runtime.graph.stats.cells_created;'
    s=rep(s,a,'        eggfuse_cell_runtime::issuer_union::configure(&runtime.graph,&req["union_position"])?;\n'+a)
    a='        let profile_work = req.get("cpu_profile").map'
    p.write_text(rep(s,a,'        report["union_position"]=eggfuse_cell_runtime::issuer_union::finish()?;\n'+a))
