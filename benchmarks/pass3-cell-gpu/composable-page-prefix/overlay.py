"""Instrument immutable native multi-parent pages before and during source verification."""
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent
def replace(path,before,after):
    s=path.read_text()
    if s.count(before)!=1:raise ValueError((path.name,before[:75],s.count(before)))
    path.write_text(s.replace(before,after))
def install(crate):
    src=crate/'src';m=src/'ordinary_witness.rs'
    replace(m,'struct Store {','struct Store {compressed_census:PageCensus,')
    replace(m,'let s=Store{','let s=Store{compressed_census:PageCensus::default(),')
    replace(m,'json!({"pages":s.pages,','json!({"prefix_census":s.compressed_census,"ref_bytes":std::mem::size_of::<crate::joint_root::Ref>(),"pages":s.pages,')
    replace(m,'                for i in 0..page.count(){\n                    let parents=page.parents(i);','''                for i in 0..page.count(){
                    let parents=page.parents(i);
                    let lcp=if s.compressed_census.active {
                        let prior=if i>0{page.parents(i-1)}else{&[]};
                        s.compressed_census.prefixes(parents,prior)
                    }else{0};''')
    replace(m,'                        let Some(row)=g.row(parent.row)? else{ok=false;break;};', '''                        let Some(row)=g.row(parent.row)? else{ok=false;break;};
                        if s.compressed_census.active{s.compressed_census.visited(j,lcp,row.values.len());}''')
    replace(m,'                for i in 0..page.count(){\n                    let parents=page.parents(i);', '''                if s.compressed_census.active{s.compressed_census.wire.observe(&page);}
                for i in 0..page.count(){
                    let parents=page.parents(i);''')
    replace(m,'                            if s.detailed{s.classify_parent_failure(g,rule,id,&row,&exact);}',
                   '''                            if s.compressed_census.active{
                                let d=&mut s.compressed_census.depth[j];d.failed+=1;d.repeated_failure+=u64::from(j<lcp);
                            }
                            if s.detailed{s.classify_parent_failure(g,rule,id,&row,&exact);}''')
    shutil.copyfile(HERE/'codec.rs',src/'prefix_wire.rs')
    shutil.copyfile(HERE/'census.rs',src/'page_prefix_census.rs')
    with m.open('a') as f:f.write('\ninclude!("page_prefix_census.rs");\n')
    driver=crate/'examples/joint_witness_session.rs'
    replace(driver,'        let initial_cells = runtime.graph.stats.cells_created;','''        if req["prefix_census"]==true { ordinary_witness::use_page_census()?; }
        let initial_cells = runtime.graph.stats.cells_created;''')
