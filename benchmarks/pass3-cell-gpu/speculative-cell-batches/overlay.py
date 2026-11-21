"""Attach speculative private Cell slabs before matching, including Run-wide issuance."""
from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    src=crate/'src'
    p=src/'slots.rs';s=p.read_text();s+='''
impl<K,V> FrameMap<K,V>{
    pub(crate) fn stage_reserved(n:usize)->Self{Self(Vec::with_capacity(n))}
    pub(crate) fn stage_allocation(&self)->usize{self.0.as_ptr() as usize}
    pub(crate) fn stage_bytes(&self)->usize{self.0.capacity()*std::mem::size_of::<(K,V)>()}
    pub(crate) fn stage_move_from(&mut self,mut src:Self){assert!(self.0.is_empty());self.0.append(&mut src.0);}
}
''';p.write_text(s)
    p=src/'joint_root.rs';s=p.read_text()
    s=change(s,'struct State{','struct State{stage_watch:bool,stage_bound:Option<Rc<Bound>>,')
    s=change(s,'Some(State{encoding:c.encoding','Some(State{stage_watch:false,stage_bound:None,encoding:c.encoding')
    s=change(s,'state.ordinal+=1;state.active=None;','state.ordinal+=1;state.active=None;state.stage_bound=None;')
    s=change(s,'        state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));','''        state.active=Some((state.ordinal,r.origin,r.serial,rid,r.template));
        if state.stage_watch{state.stage_bound=Some(bound.clone());}''')
    s=change(s,'{s.active=None;});}','{s.active=None;s.stage_bound=None;});}')
    s+='''
pub(crate) fn retain_staging_parent(enabled:bool){STATE.with_borrow_mut(|s|if let Some(st)=s{st.stage_watch=enabled;});}
pub(crate) fn staging_identity()->Option<(usize,u64,usize)>{
    STATE.with_borrow(|s|s.as_ref()?.active.map(|(_,_,serial,rid,t)|(rid,serial,t)))
}
pub(crate) fn same_staged_parent(recipe:&Recipe)->bool{
    let Some(offered)=decode(recipe) else{return false};
    STATE.with_borrow(|s|s.as_ref().and_then(|st|st.stage_bound.as_ref()).is_some_and(|b|{
        let r=&b.recipe;
        offered.serial==r.serial && offered.origin==r.origin && offered.run==r.run && offered.template==r.template &&
        Rc::ptr_eq(&offered.layout,&r.layout) && offered.refs.len()==r.refs.len() &&
        offered.refs.iter().zip(&r.refs).all(|(a,b)|a.atom==b.atom && a.row==b.row && a.version==b.version)
    }))
}
impl RootPage{pub(crate) fn stage_serial(&self)->u64{self.words[1]}}
impl MultiPage{pub(crate) fn stage_serial(&self)->u64{self.0.first_serial}}
'''
    p.write_text(s)
    p=src/'graph.rs';s=p.read_text()
    s=change(s,'pub struct Graph {','pub struct Graph {\n    pub(crate) spec_cells:Option<std::cell::RefCell<speculative::Staging>>,')
    s=change(s,'        let mut g = Self {','        let mut g = Self {spec_cells:None,')
    start=s.index('    fn new_cell(');middle=s.index('        Cell {\n            template,',start)
    q=s[start:middle];h=q.index('        let columns =')
    prep='''    fn stage_inputs(&self,template:usize,mut values:crate::slots::Slots,parent:Option<FactRef>)->(crate::slots::Slots,Option<FactRef>){
'''+q[h:]+'''        (values,parent)
    }
'''+q[:h].replace('mut values:','values:')+'        let (values,parent)=self.stage_inputs(template,values,parent);\n'
    s=s[:start]+prep+s[middle:]
    a='''        crate::joint_root::fresh(id,template)?;
        let frame=self.new_cell(template,values,parent);
        self.store_cell(id,frame);'''
    s=change(s,a,'''        crate::joint_root::fresh(id,template)?;
        if let Some(mut staged)=self.take_private(template){
            let (values,parent)=self.stage_inputs(template,values,parent);
            staged.frame.values=values;staged.frame.parent=parent;
            self.store_cell(id,staged.frame);self.check_private(id,staged.early_ptr,staged.preconstructed,true);
        }else{
            let frame=self.new_cell(template,values,parent);self.store_cell(id,frame);
        }''')
    s=change(s,'        self.store_cell(id,frame);\n        self.function_origin(i,Some(FactRef','        self.publish_private_temp(id,frame);\n        self.function_origin(i,Some(FactRef')
    s=change(s,'{crate::joint_root::fresh(cell,resumed.template)?;self.store_cell(cell, resumed);}', '{crate::joint_root::fresh(cell,resumed.template)?;self.publish_private_temp(cell, resumed);}')
    p.write_text(s+'\n#[path="speculative_staging.rs"]\npub(crate) mod speculative;\n');copyfile(HERE/'staging.rs',src/'speculative_staging.rs')
    p=src/'cell_prefix.rs';s=p.read_text()
    s=change(s,'                self.store_cell(cell, frame);','                self.publish_private_temp(cell, frame);')
    p.write_text(s)
    p=src/'runtime.rs';s=p.read_text();a='''        #[cfg(feature = "sparse-cells")]
        if rules.is_empty() && !self.audit'''
    s=change(s,a,'        self.graph.spec_run(set,&rules);\n'+a)
    s=change(s,'        let origin = b.continuation;','        self.graph.spec_winner();\n        let origin = b.continuation;')
    s=change(s,'        let rhs_end = Instant::now();','        self.graph.spec_end_run();\n        let rhs_end = Instant::now();')
    s=change(s,'            self.graph.stats.idle_scheduled_runs += 1;', '            self.graph.spec_end_run();\n            self.graph.stats.idle_scheduled_runs += 1;')
    p.write_text(s)
    p=src/'adaptive_rows.rs';s=p.read_text()
    a='                if let Some(page) = crate::joint_root::single_page(g.epoch, rid, p.pivot, &frozen) {'
    p.write_text(change(s,a,a+'\n                    if g.spec_cells.is_some(){g.spec_page(rid,page.stage_serial(),frozen.len(),crate::graph::speculative::Handle::Single(page.clone()));}'))
    p=src/'ordinary_witness.rs';s=p.read_text()
    a='                    total+=page.count();s.max_sealed_page=s.max_sealed_page.max(page.count());'
    p.write_text(change(s,a,'                    if g.spec_cells.is_some(){g.spec_page(rid,page.stage_serial(),page.count(),crate::graph::speculative::Handle::Multi(page.clone()));}\n'+a))
    p=crate/'examples/joint_witness_session.rs';s=p.read_text();a='        let initial_cells = runtime.graph.stats.cells_created;'
    s=change(s,a,'        if let Some(cfg)=req.get("spec_cells"){runtime.graph.configure_spec_cells(cfg,audit)?;}\n'+a)
    a='        report["phases_ms"]='
    p.write_text(change(s,a,'        report["spec_cells"]=runtime.graph.spec_cells_report();\n'+a))
    import importlib.util
    spec=importlib.util.spec_from_file_location("private_issuance_boundary",HERE/"boundary.py")
    boundary=importlib.util.module_from_spec(spec);spec.loader.exec_module(boundary)
    boundary.install(crate)
