from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent


def replace(text,old,new):
    if text.count(old)!=1:raise ValueError(f'expected one hook: {old[:70]}')
    return text.replace(old,new)


def install(crate):
    p=crate/'src/ordinary_witness.rs'
    s=replace(p.read_text(),'struct Store {','struct Store {forward:ForwardState,')
    s=replace(s,'let s=Store{','let s=Store{forward:ForwardState::default(),')
    s=replace(s,'"sealed_before_verifier":s.seal,','"forward":s.forward.stats,"sealed_before_verifier":s.seal,')
    s=replace(s,'let (steps,slots)=s.compile_stack(&c)?;','let (mut steps,mut slots)=s.compile_stack(&c)?;')
    s=replace(s,'            s.issued_generations.clear();','''            s.forward.active.clear();
            if s.forward.config.is_some() && steps.len()>=3{
                s.prepare_forward(&c,&mut steps,&mut slots)?;
            }
            s.issued_generations.clear();''')
    p.write_text(s+'\ninclude!("forward_feasibility.rs");\n')
    shutil.copyfile(HERE/'feasibility.rs',crate/'src/forward_feasibility.rs')
    p=crate/'src/ordinary_shortlist.rs'
    s=replace(p.read_text(),'            path.push(row.witness);','''            if !self.forward.active.is_empty() && !self.forward.permits(i,ports,now,c.watermark,c.rule.seminaive)?{continue;}
            path.push(row.witness);''')
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs'
    anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(replace(p.read_text(),anchor,'''        if let Some(config)=req.get("forward"){
            ordinary_witness::use_forward(config.clone())?;
        }
'''+anchor))
