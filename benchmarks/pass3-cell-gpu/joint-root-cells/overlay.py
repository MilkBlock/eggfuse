"""A raw single/tuple issue supplies the primary Cell recipe and drives its exact source allocation."""
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent

def patch(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise RuntimeError((p.name,a[:86],s.count(a)))
    p.write_text(s.replace(a,b))

def install(crate):
    src=Path(crate)/'src';shutil.copy2(HERE/'recipe.rs',src/'joint_root.rs')
    with (src/'lib.rs').open('a') as f:f.write('\npub mod joint_root;\n')
    p=src/'single_witness.rs'
    patch(p,'struct Token{id:u64,','struct Token{recipe:Option<crate::joint_root::Recipe>,id:u64,')
    patch(p,'struct Mark{token:Token,','struct Mark{pub(crate) root_recipe:Option<std::rc::Rc<crate::joint_root::Bound>>,token:Token,')
    a='self.serial+=1;offers.push((Token{id:self.serial,'
    patch(p,a,'''let recipe=if send && learned && matches!(self.mode.as_str(),"learned"|"guarded"|"zero-state"){
                crate::joint_root::issue("single",g.epoch,rid,row.as_ref().zip(p.pivot).map(|(row,atom)|
                    crate::joint_root::Ref{atom,row:row.witness,version:row.epoch}).into_iter())
            }else{None};
            self.serial+=1;offers.push((Token{recipe,id:self.serial,''')
    a='binding.known=binding.known.tagged(Mark{token,values,witnesses});'
    patch(p,a,'''let root_recipe=crate::joint_root::bind_single(token.recipe.clone(),g,rid,&binding.known,&binding.values)?;
                    binding.known=binding.known.tagged(Mark{root_recipe,token,values,witnesses});''')
    p=src/'ordinary_witness.rs'
    patch(p,'struct Ticket {local_token_id:usize,','struct Ticket {#[serde(skip)] root_recipe:Option<Rc<crate::joint_root::Bound>>,local_token_id:usize,')
    patch(p,'struct Store {hint_fault:u8,','struct Store {root_offers:Vec<Option<crate::joint_root::Recipe>>,hint_fault:u8,')
    patch(p,'let s=Store{hint_fault,','let s=Store{root_offers:vec![],hint_fault,')
    patch(p,'struct Prefix {','struct Prefix {root_recipe:Option<crate::joint_root::Recipe>,')
    patch(p,'let p=Prefix{latents:','let p=Prefix{root_recipe:None,latents:')
    a='            let mut b=Instance::matched(p.slots,'
    patch(p,a,'''            let root_recipe=crate::joint_root::bind(p.root_recipe.take(),c.graph,self.rule,&p.witness,&p.slots)?;
'''+a)
    patch(p,'self.tickets.push(Ticket{local_token_id:','self.tickets.push(Ticket{root_recipe,local_token_id:')
    with p.open('a') as f:f.write('''
pub(crate) fn allocation_recipe(id:usize)->Option<Rc<crate::joint_root::Bound>>{
    if id==0 {return None;}
    STORE.with_borrow(|s|s.as_ref().and_then(|s|s.tickets.get(id-1)).and_then(|t|t.root_recipe.clone()))
}
''')
    p=src/'ordinary_shortlist.rs'
    a='''            if self.accel>=5{
                self.flat.extend(path.iter().copied().zip(self.flat_offsets.iter().copied()));'''
    patch(p,a,'''            let refs=steps.iter().zip(path.iter()).map(|(step,w)|crate::joint_root::Ref{
                atom:step.atom,row:*w,version:c.graph.visible_epoch(*w).expect("sealed visible root")});
            self.root_offers.push(crate::joint_root::issue("multi",c.graph.epoch,self.rule,refs));
'''+a)
    patch(p,'        let mut flat=std::mem::take(&mut self.flat);','''        let mut flat=std::mem::take(&mut self.flat);
        let proposals=std::mem::take(&mut self.root_offers);
        assert_eq!(proposals.len(),flat.len()/c.pick_count);''')
    patch(p,'        for packet in flat.chunks_exact(c.pick_count){\n            let mut exact=base.clone();',
            '        for (packet,recipe) in flat.chunks_exact(c.pick_count).zip(proposals){\n            let mut exact=base.clone();exact.root_recipe=recipe;')
    p=src/'ordinary_witness.rs'
    patch(p,'            for parents in raw{\n                let mut exact=p.clone();','''            let stack_recipes=if s.accel==4{std::mem::take(&mut s.root_offers)}else{vec![]};
            if s.accel==4{assert_eq!(stack_recipes.len(),raw.len());}
            let mut stack_recipes=stack_recipes.into_iter();
            for parents in raw{
                let mut exact=p.clone();exact.root_recipe=stack_recipes.next().flatten();''')
    p=src/'runtime.rs'
    a='        let template = self.graph.program.rules[rid].template;\n        let origin = b.continuation;'
    patch(p,a,'''        let recipe=b.known.neural().and_then(|m|m.root_recipe.clone()).or_else(||crate::ordinary_witness::allocation_recipe(b.ordinary_id));
        let template=crate::joint_root::consume(recipe,rid,self.graph.epoch,self.graph.program.rules[rid].template,&mut b.values)?;
        let origin = b.continuation;''')
    patch(p,'self.graph.start_completion(rid, &mut b.values,','self.graph.start_completion(rid, template, &mut b.values,')
    patch(p,'me.graph.linked_slots(template, values, b.parent)?','me.graph.linked_root_slots(template, values, b.parent)?')
    patch(p,'        crate::joint_merge::end();','        crate::joint_root::end();\n        crate::joint_merge::end();')
    p=src/'graph.rs'
    a='    pub(crate) fn linked_slots('
    patch(p,a,'''    pub(crate) fn linked_root_slots(&mut self,template:usize,values:crate::slots::Slots,parent:Option<FactRef>)->Result<u32>{
        let id=self.reserve_cell_id()?;
        crate::joint_root::fresh(id,template)?;
        let frame=self.new_cell(template,values,parent);
        self.store_cell(id,frame);
        Ok(id)
    }
'''+a)
    # The sparse layout is not enabled for this joint build. Preserve its early returns when type checking.
    patch(p,'    fn keep_writer(&mut self,i:usize,id:u32,op:usize,mut frame:Cell){',
          '    fn keep_writer(&mut self,i:usize,id:u32,op:usize,mut frame:Cell)->Result<()>{')
    s=p.read_text().replace('self.keep_writer(i,id,write.op,frame);','self.keep_writer(i,id,write.op,frame)?;')
    s=s.replace('if i<u32::MAX as usize {self.inline_writer(i,id,op,frame);return;}','if i<u32::MAX as usize {self.inline_writer(i,id,op,frame);return Ok(());}')
    p.write_text(s)
    patch(p,'        self.store_cell(id,frame);\n        self.function_origin(i,Some(FactRef{cell:id,op:op as u32}));',
          '        crate::joint_root::fresh(id,frame.template)?;\n        self.store_cell(id,frame);\n        self.function_origin(i,Some(FactRef{cell:id,op:op as u32})); Ok(())')
    patch(p,'    pub(crate) fn start_completion(\n        &mut self,\n        rule: usize,','    pub(crate) fn start_completion(\n        &mut self,\n        rule: usize,\n        template: usize,')
    patch(p,'        let template = self.program.rules[rule].template;\n        let ops = self.program.templates[template].ops.clone();','        let ops = self.program.templates[template].ops.clone();')
    patch(p,'            self.store_cell(cell, resumed);','            {crate::joint_root::fresh(cell,resumed.template)?;self.store_cell(cell, resumed);}')
    p=src/'cell_prefix.rs';patch(p,'                self.store_cell(cell, frame);','                crate::joint_root::fresh(cell,frame.template)?;\n                self.store_cell(cell, frame);')
    p=Path(crate)/'examples/joint_witness_session.rs'
    a='        let initial_cells = runtime.graph.stats.cells_created;'
    patch(p,a,'''        let root_config=req["root_config"].as_str().map(std::fs::read).transpose()?;
        eggfuse_cell_runtime::joint_root::configure(&program,root_config.as_deref(),audit)?;
'''+a)
    patch(p,'            writeln!(out, "{}", failure)?;','            failure["root_recipe"]=eggfuse_cell_runtime::joint_root::report();\n            writeln!(out, "{}", failure)?;')
    a='        report["merge_child"]=eggfuse_cell_runtime::joint_merge::report();'
    patch(p,a,'        report["root_recipe"]=eggfuse_cell_runtime::joint_root::report();\n'+a)
