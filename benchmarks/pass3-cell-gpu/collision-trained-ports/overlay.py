import shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent

def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)

def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs'
    s=change(p.read_text(),'struct Store {','struct Store {secondary:Option<BakedCodes>,hard_pairs:HardPairs,')
    s=change(s,'let s=Store{','let s=Store{secondary:None,hard_pairs:HardPairs::default(),')
    s=change(s,'"atom_constraints":s.atoms.stats,','"hard_pairs":s.hard_pairs.report(),"atom_constraints":s.atoms.stats,')
    s=change(s,'if let Some(table)=&self.baked_codes{return table.port(v,self.views);}', '''if let Some(table)=&self.baked_codes{
            if let Some(extra)=&self.secondary{
                let seed=code_seed(v);let (query,key)=table.pair(mix(seed));
                let (q,k)=extra.pair(mix(seed^0x8220e116bd89aae9));
                return Port{query,key,certified:0,uncertain:0,extra:[[q,k,0,0],[0;4]]};
            }
            return table.port(v,self.views);
        }''')
    p.write_text(s+'\ninclude!("hard_port_pairs.rs");\n')
    p=src/'atom_checks.rs';s=p.read_text()
    s=change(s,'self.atoms.stats.failure_literal += 1;', 'self.hard_pairs.record(&canon(l,&g.parents),v);self.atoms.stats.failure_literal += 1;')
    s=change(s,'let repeated =', 'self.hard_pairs.record(p.slots.get(s).unwrap(),v);\n                    let repeated =')
    p.write_text(s)
    shutil.copyfile(HERE/'pairs.rs',src/'hard_port_pairs.rs')
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if req["capture_collisions"].as_bool()==Some(true){ordinary_witness::capture_collisions()?;}
        if let Some(path)=req["secondary_weights"].as_str(){
            let table=req["secondary_codes"].as_str().ok_or("missing extra port table")?;
            ordinary_witness::use_secondary(&std::fs::read(path)?,&std::fs::read(table)?)?;
        }
'''+a))
