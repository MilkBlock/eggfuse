from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def change(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)

def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {','struct Store {premises:PagePremises,')
    s=change(s,'let s=Store{','let s=Store{premises:PagePremises::default(),')
    s=change(s,'"pages":s.pages,','"premises":s.premises.stats,"pages":s.pages,')
    a='                for page in pages{'
    s=change(s,a,a+'\n                if s.premises.mode!=0{s.verify_shared_page(&c,&p,&page,&mut out)?;continue;}')
    s=change(s,'self.counts.point_reads+=1;\n                    if let Some(row)=c.graph.lookup(*t,&operands)?',
             'if let Some(row)=self.suffix_point(c.graph,*t,&operands)?')
    p.write_text(s+'\ninclude!("page_premises.rs");\n')
    copyfile(HERE/'premises.rs',src/'page_premises.rs')
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if let Some(n)=req["page_premises"].as_u64(){ordinary_witness::configure_page_premises(&program,n)?;}
'''+a))
