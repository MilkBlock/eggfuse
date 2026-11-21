from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def rep(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=rep(s,'struct Store {','struct Store {block_handoff:bool,')
    s=rep(s,'let s=Store{','let s=Store{block_handoff:false,')
    a='            let root_recipe=crate::joint_root::bind(p.root_recipe.take(),c.graph,self.rule,&p.witness,&p.slots)?;'
    s=rep(s,a,a+'''
            self.finish_root_binding(c,p,out,root_recipe)
        }
        fn finish_root_binding(&mut self,c:&Context,p:Prefix,out:&mut Vec<Instance>,root_recipe:Option<Rc<crate::joint_root::Bound>>)->Result<()> {''')
    p.write_text(s+'\ninclude!("checked_block_handoff.rs");\n');copyfile(HERE/'handoff.rs',src/'checked_block_handoff.rs')
    p=src/'joint_root.rs';s=p.read_text()
    s=rep(s,'struct State{','struct State{block_bind:u8,block_proofs:BlockBindStats,')
    s=rep(s,'Some(State{factor_mode:0,','Some(State{block_bind:0,block_proofs:Default::default(),factor_mode:0,')
    s=rep(s,'"factor":s.factor_stats,','"block_proofs":s.block_proofs,"factor":s.factor_stats,')
    p.write_text(s+'\ninclude!("root_block_handoff.rs");\n');copyfile(HERE/'root.rs',src/'root_block_handoff.rs')
    p=src/'batched_block.rs';s=p.read_text()
    s=rep(s,'        ports: &mut PortMemo,','        checked_lane: Option<(&MultiPage,usize)>,\n        ports: &mut PortMemo,')
    p.write_text(rep(s,'        self.complete_source_binding(c, exact, out)','''        if self.block_handoff && let Some((page,slot))=checked_lane {
            let recipe=exact.root_recipe.take();
            let proof=CheckedBlock{graph:c.graph,rule:self.rule,page,slot,known:&exact.witness,values:&exact.slots};
            let bound=crate::joint_root::bind_completed_block(recipe,proof)?;
            self.counts.validated+=1;
            return self.finish_root_binding(c,exact,out,bound)
        }
        self.complete_source_binding(c, exact, out)'''))
    p=src/'page_premises.rs';p.write_text(rep(p.read_text(),',epoch,exact,&mut ports,out)?',',epoch,exact,None,&mut ports,out)?'))
    p=src/'coordinate_program.rs';p.write_text(rep(p.read_text(),', epoch, exact, &mut memo, out)?',', epoch, exact, Some((page,i)), &mut memo, out)?'))
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(rep(p.read_text(),a,'''        if let Some(n)=req["verified_page_handoff"].as_u64(){eggfuse_cell_runtime::joint_root::configure_block_bind(n)?;}
'''+a))
