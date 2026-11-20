import shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent

def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)

def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs'
    s=change(p.read_text(),'struct Store {','struct Store {atoms:AtomChecks,')
    s=change(s,'let s=Store{','let s=Store{atoms:AtomChecks::default(),')
    s=change(s,'"forward":s.forward.stats,','"atom_constraints":s.atoms.stats,"forward":s.forward.stats,')
    s=change(s,'            s.issued_generations.clear();','''            if s.atoms.mode>0{s.prepare_atom_checks(&c,&steps);}
            s.issued_generations.clear();''')
    marker='if !extend(g,rule,id,&row,&mut exact){ok=false;break;}'
    s=change(s,marker,'''if !extend(g,rule,id,&row,&mut exact){
                            if s.detailed{s.classify_parent_failure(g,rule,id,&row,&exact);}
                            ok=false;break;
                        }''')
    p.write_text(s+'\ninclude!("atom_checks.rs");\n');shutil.copyfile(HERE/'checks.rs',src/'atom_checks.rs')
    p=src/'ordinary_shortlist.rs'
    s=change(p.read_text(),'            if self.early.active.is_some()', '''            if self.atoms.mode>0 && !self.local_codes_permit(i,j,row){continue;}
            if self.early.active.is_some()''');p.write_text(s)
    p=src/'incremental_raw.rs'
    s=change(p.read_text(),'            self.pair_stats.first_candidates += 1;', '''            if self.atoms.mode>0 && !self.local_codes_permit(0,l,row){continue;}
            self.pair_stats.first_candidates += 1;''')
    # Guard in the original right loop and preserve the independent source address.
    s=change(s,'                let other = &right.frame.rows[r];','''                let other = &right.frame.rows[r];
                if self.atoms.mode>0 && !self.local_codes_permit(1,r,other){continue;}''')
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if let Some(mode)=req["atom_constraints"].as_u64(){ordinary_witness::enable_atom_checks(mode)?;}
'''+a))
