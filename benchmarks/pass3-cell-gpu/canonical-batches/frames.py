"""Hold a compiler-proved slot mask only for the active source RHS at the observed union generation."""
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent
def install(crate):
    src=crate/'src'
    def one(path,old,new):
        file=src/path;s=file.read_text()
        if s.count(old)!=1:raise ValueError((path,old[:80],s.count(old)))
        file.write_text(s.replace(old,new))
    prefix=src/'cell_prefix.rs'
    prefix_text=prefix.read_text()
    old='    #[cfg(feature = "sparse-cells")]\n    const SEALED_INPUTS: bool'
    if prefix_text.count(old)!=3:raise ValueError('expected the original source and local prefix permissions')
    prefix.write_text(prefix_text.replace(old,'    const SEALED_INPUTS: bool'))
    one('graph.rs','pub struct Graph {','pub struct Graph {\n    canon_frames:CanonicalFrames,')
    one('graph.rs','            joint_allocations: None,','            canon_frames:Default::default(),\n            joint_allocations: None,')
    one('graph.rs','        let id=self.reserve_cell_id()?;\n        crate::joint_root::fresh(id,template)?;',
        '        let id=self.reserve_cell_id()?;\n        self.canon_frames.frame(id,template,self.stats.unions);\n        crate::joint_root::fresh(id,template)?;')
    one('graph.rs','        self.stats.single_writes += 1;','        self.canon_frames.frame(id,template,self.stats.unions);\n        self.stats.single_writes += 1;')
    one('cell_prefix.rs','        let mut frame = self.new_cell(template, values, parent);',
        '        if P::SEALED_INPUTS{self.canon_frames.frame(cell,template,self.stats.unions);}\n        let mut frame = self.new_cell(template, values, parent);')
    one('graph.rs','        let (lo, hi) = (a.min(b), a.max(b));','        let (lo, hi) = (a.min(b), a.max(b));\n        self.canon_frames.cell=None;')
    one('graph.rs','        if let Some(v) = values.get(&i).or_else(|| inputs.and_then(|v| v.get(&i))) {','''        if let Some(v) = values.get(&i).or_else(|| inputs.and_then(|v| v.get(&i))) {
            if let Value::Eq(x)=v && let Some(kind)=self.canon_frames.protected(cell,i){
                if self.canon_frames.check && crate::value::root(&self.parents,*x)!=*x{return Err("current-frame slot is not a canonical source value".into());}
                if self.canon_frames.audit{let mut n=self.canon_frames.reads.get();n[kind]+=1;self.canon_frames.reads.set(n);}
                return Ok(v.clone());
            }''')
    one('runtime.rs','        #[cfg(feature = "sparse-cells")]\n        let binding_generation = self.graph.stats.unions;',
        '        let binding_generation = self.graph.stats.unions;')
    one('runtime.rs','                let applied = self.apply(','                self.graph.begin_canonical_rhs(rid,binding_generation);\n                let applied = self.apply(')
    one('runtime.rs','                applied?;','                self.graph.finish_canonical_rhs();\n                applied?;')
    shutil.copyfile(HERE/'frame.rs',src/'canonical_frames.rs')
    with (src/'graph.rs').open('a') as f:f.write('''
include!("canonical_frames.rs");
impl Graph{
    pub(crate) fn begin_canonical_rhs(&mut self,rid:usize,generation:u64){self.canon_frames.begin(rid,generation);}
    pub(crate) fn finish_canonical_rhs(&mut self){self.canon_frames.cell=None;self.canon_frames.inputs=0;self.canon_frames.derived=0;}
}
''')
    p=crate/'examples/joint_witness_session.rs';s=p.read_text().replace('        let initial_cells = runtime.graph.stats.cells_created;', '''        runtime.graph.configure_canonical_frames(u8::try_from(req["canon_frame"].as_u64().unwrap_or(0))?,req["canon_audit"]==true,req["canon_check"]==true)?;
        let initial_cells = runtime.graph.stats.cells_created;''').replace('        report["canon_work"]=', '        report["canon_frame"]=runtime.graph.frame_proof_report();\n        report["canon_work"]=')
    p.write_text(s)

    e=src/'parent_epoch.rs'
    one('parent_epoch.rs','    pub fn contains_key(&self, id: &u64) -> bool {','''    pub fn contains_key(&self, id: &u64) -> bool {
        if self.batch.audit && self.batch.phase!=0{DIRECT_CONTAINS.with_borrow_mut(|s|s[self.batch.phase as usize]+=1);}
''')
    with e.open('a') as f:f.write('''
thread_local!{static DIRECT_CONTAINS:std::cell::RefCell<[u64;3]>=const{std::cell::RefCell::new([0;3])};}
impl Parents{pub fn take_contains(&self)->[u64;3]{DIRECT_CONTAINS.take()}}
''')
    s=p.read_text()
    s=s.replace('        let initial_cells = runtime.graph.stats.cells_created;', '        let _=runtime.graph.parents.take_contains();\n        let initial_cells = runtime.graph.stats.cells_created;')
    s=s.replace('        report["canon_work"]=', '        report["canon_contains"]=json!(runtime.graph.parents.take_contains());\n        report["canon_work"]=')
    p.write_text(s)
