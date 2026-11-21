from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def replace(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=replace(s,'struct Store {','struct Store {word_verifier:WordProgram,')
    s=replace(s,'let s=Store{','let s=Store{word_verifier:WordProgram::default(),')
    s=replace(s,'"blocks":s.blocks,','"word_verifier":s.word_verifier.stats,"blocks":s.blocks,')
    mark='                if s.premises.mode!=0{s.verify_shared_page'
    s=replace(s,mark,'                if s.word_verifier.mode!=0 && s.verify_word_page(&c,&p,&page,&mut out)?{continue;}\n'+mark)
    p.write_text(s+'\ninclude!("coordinate_program.rs");\n')
    copyfile(HERE/'coordinates.rs',src/'coordinate_program.rs')
    p=src/'page_premises.rs';s=p.read_text()
    s=replace(s,'        let mut rows = SmallRows::new();','        let mut scratch=Vec::new();\n        let mut rows = SmallRows::new();')
    p.write_text(replace(s,'let parents = page.parents(i);','let parents=page.read_parents(i,&mut scratch)?;'))
    p=src/'batched_block.rs';p.write_text(replace(p.read_text(),'type PortMemo = SourceMap<(usize, Dependency, u64), Option<Row>>;',''))
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(replace(p.read_text(),a,'''        if let Some(m)=req["coordinate_verify"].as_u64(){ordinary_witness::configure_word_verifier(m)?;}
'''+a))
