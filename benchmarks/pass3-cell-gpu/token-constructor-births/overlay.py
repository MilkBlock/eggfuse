from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def patch(p,before,after):
    s=p.read_text()
    if s.count(before)!=1:raise ValueError((p,before))
    p.write_text(s.replace(before,after))


def install(crate):
    src=crate/'src'
    copyfile(HERE/'births.rs',src/'token_births.rs')
    patch(src/'lib.rs','pub mod joint_root;', 'pub mod joint_root;\npub mod token_births;')
    graph=src/'graph.rs'
    marker='self.stats.logical_facts_created += 1;'
    patch(graph,marker,marker+'\n        crate::token_births::first(self.epoch,f.ordered_id(),t,self.program.tables[t].constructor);')
    marker='    pub fn dynamic_construct(&mut self, t: usize, args: impl AsRef<[Value]> + IntoIterator<Item = Value>) -> Result<Value> {'
    patch(graph,marker,marker+'''
        crate::token_births::dynamic(||self.dynamic_construct_measured(t,args))
    }
'''+marker.replace('pub fn dynamic_construct','fn dynamic_construct_measured'))
    msg='            self.retire(f)?;\n        } else {\n            self.end_local_ownership'
    patch(graph,msg,"            if let Dependency::Fact(keeper)=other.witness{crate::token_births::coalesced(f.ordered_id(),keeper.ordered_id());}\n"+msg)
    digest=src/'union_digest.rs'
    patch(digest,"            self.retire(f)?;","            crate::token_births::coalesced(f.ordered_id(),keep.ordered_id());\n            self.retire(f)?;")
    spine=src/'stage_spine.rs'
    with spine.open('a') as f:
        f.write('''\nimpl Started{pub(crate) fn measured_lineage(&self)->(u64,bool){
            match self{Self::Root{id,..}=>(*id,false),Self::Live(c)=>(c.root.id,true)}
        }}\n''')
    runtime=src/'runtime.rs'
    patch(runtime,'        self.graph.spec_winner();','''        crate::token_births::begin(self.graph.epoch,crate::joint_root::staging_identity().map(|(_,serial,_)|serial),stage_cursor.as_ref().map(|s|s.measured_lineage()));
        self.graph.spec_winner();''')
    patch(runtime,'        crate::joint_root::end();','        crate::token_births::end();\n        crate::joint_root::end();')
    p=crate/'examples/joint_witness_session.rs'
    a='        let mut runtime = Executor::new(Graph::new(program.clone())?, false);'
    patch(p,a,'        eggfuse_cell_runtime::token_births::reset(req["birth_ledger"]==true);\n'+a)
    patch(p,'        if let Err(error) = runtime.execute() {','        eggfuse_cell_runtime::token_births::execution();\n        if let Err(error) = runtime.execute() {')
    patch(p,'        report["spec_cells"]=runtime.graph.spec_cells_report();','''        report["constructor_births"]=eggfuse_cell_runtime::token_births::report(&runtime.graph)?;
        report["constructor_schema"]=json!(program.tables.iter().map(|t|t.constructor).collect::<Vec<_>>());
        report["spec_cells"]=runtime.graph.spec_cells_report();''')
