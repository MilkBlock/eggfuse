from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def change(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)

def install(crate):
    src=crate/'src';p=src/'graph.rs';s=p.read_text()
    s=change(s,'pub struct Graph {','pub struct Graph {locator:Locator,')
    s=change(s,'        let mut g = Self {','        let mut g = Self {locator:Locator::default(),')
    a='        let native = self.native_signal(hi);'
    s=change(s,a,'''        let located=if self.locator.mode!=0 {self.locate_before_union(hi,lo)}else{None};
'''+a)
    s=change(s,'            self.mark_affected(&affected, hi, lo);','''            if let Some(readers)=&located {self.mark_located(readers.iter(),hi,lo);}
            else {self.mark_affected(&affected,hi,lo);}''')
    s=change(s,'        for d in affected.iter() {\n            #[cfg(feature = "spine-blocks")]','''        self.mark_located(affected.iter(),from,to);
    }
    fn mark_located<'a>(&mut self,readers:impl Iterator<Item=&'a Dependency>,from:u64,to:u64) {
        for d in readers {
            #[cfg(feature = "spine-blocks")]''')
    a='            if !retained && let Dependency::Fact(f) = d\n                && let Some(state)'
    s=change(s,a,'''            let timer=self.locator.profile.then(std::time::Instant::now);
            let patched=!retained && self.locator.mode!=0 && self.use_located_port(*d,from,to);
            if let Some(start)=timer{self.locator.stats.dispatch_patch_ns+=start.elapsed().as_nanos() as u64;}
            if !patched && !retained && let Dependency::Fact(f) = d
                && let Some(state)''')
    p.write_text(s+'\ninclude!("union_location.rs");\n');copyfile(HERE/'locator.rs',src/'union_location.rs')
    p=src/'joint_root.rs';s=p.read_text()
    s=change(s,'struct State{','struct State{location_enabled:bool,location_parents:smallvec::SmallVec<[Dependency;4]>,')
    s=change(s,'Some(State{encoding:c.encoding','Some(State{location_enabled:false,location_parents:Default::default(),encoding:c.encoding')
    a='state.ordinal+=1;state.active=None;'
    s=change(s,a,a+'if state.location_enabled{state.location_parents.clear();}')
    a='        *inputs=values;state.applied+=1;'
    s=change(s,a,'''        if state.location_enabled{state.location_parents.extend(r.refs.iter().take(4).map(|p|p.row));}
'''+a)
    p.write_text(s+'''
pub fn enable_locator_inputs(){
    STATE.with_borrow_mut(|s|{if let Some(st)=s.as_mut(){st.location_enabled=true;}})
}
pub(crate) fn locator_parents()->smallvec::SmallVec<[Dependency;4]>{
    STATE.with_borrow(|s|s.as_ref().filter(|s|s.active.is_some()).map(|s|s.location_parents.clone()).unwrap_or_default())
}
''')
    p=crate/'examples/joint_witness_session.rs';s=p.read_text();a='        let initial_cells = runtime.graph.stats.cells_created;'
    s=change(s,a,'''        if let Some(v)=req.get("union_locator"){
            if v["parent_ports"]!=false {eggfuse_cell_runtime::joint_root::enable_locator_inputs();}
            runtime.graph.use_union_locator(v,audit)?;
        }
'''+a)
    a='        let profile_work = req.get("cpu_profile").map'
    p.write_text(change(s,a,'        report["union_locator"]=runtime.graph.union_location_report();\n'+a))
