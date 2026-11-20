from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent


def change(s,old,new):
    if s.count(old)!=1:raise ValueError(f'expected one overlay hook: {old}')
    return s.replace(old,new)


def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {','struct Store {equations:EquationState,')
    s=change(s,'let s=Store{','let s=Store{equations:EquationState::default(),')
    s=change(s,'"tier":s.tier.stats,','"equations":s.equations.stats,"tier":s.tier.stats,')
    p.write_text(s+'\ninclude!("derived_pair.rs");\n');shutil.copyfile(HERE/'equations.rs',src/'derived_pair.rs')
    p=src/'incremental_raw.rs';s=p.read_text()
    marker='        let index = if self.signatures.enabled {'
    s=change(s,marker,'''        let eq = if self.equations.mode!=0{self.prepare_equation(c,steps,&right_cols[0].1)?}else{None};
        let narrow_index = eq.as_ref().is_some_and(|b|b.lookup.is_some());
        let index = if self.signatures.enabled || narrow_index {''')
    anchor='            let entries: &[usize] = if let Some(found) = reverse {\n                found\n            } else {'
    s=change(s,anchor,'''            let entries: &[usize] = if let Some(found) = reverse {
                found
            } else if narrow_index {
                let e=eq.as_ref().unwrap();
                let key=(u64::from(signature(left_cols[0].1[l],true,self.views))<<32)|u64::from(e.left[l]);
                self.equations.stats.index_probes+=1;
                e.lookup.as_ref().unwrap().get(&key).map_or(&[],Vec::as_slice)
            } else {''')
    marker='                if row.epoch.max(other.epoch) < cut {'
    s=change(s,marker,'''                if let Some(e)=&eq && (reverse.is_some()||!narrow_index){
                    self.equations.stats.pair_checks+=1;
                    if e.left[l]==u32::MAX || e.left[l]!=e.right[r]{self.equations.stats.filtered+=1;continue;}
                }
'''+marker)
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),anchor,'''        if let Some(v)=req.get("derived_ports"){ordinary_witness::configure_equations(&program,v.clone())?;}
'''+anchor))
