from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def change(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)

def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {','struct Store {library:PageLibrary,')
    s=change(s,'let s=Store{','let s=Store{library:PageLibrary::default(),')
    s=change(s,'"word_verifier":s.word_verifier.stats,','"page_library":s.library.stats,"word_verifier":s.word_verifier.stats,')
    a='        let rule=&g.program.rules[rid];'
    s=change(s,a,'        s.apply_page_library(rid)?;\n'+a)
    p.write_text(s+'\ninclude!("page_library.rs");\n')
    copyfile(HERE/'library.rs',src/'page_library.rs')
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if let Some(v)=req.get("page_library"){ordinary_witness::install_page_library(v.clone())?;}
'''+a))
