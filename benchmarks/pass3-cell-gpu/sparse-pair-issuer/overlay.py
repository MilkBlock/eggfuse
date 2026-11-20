from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent
def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)
def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs'
    s=change(p.read_text(),'struct Store {','struct Store {sparse_pairs:SparsePairs,')
    s=change(s,'let s=Store{','let s=Store{sparse_pairs:SparsePairs::default(),')
    s=change(s,'"equations":s.equations.stats,','"sparse_pairs":s.sparse_pairs.stats,"equations":s.equations.stats,')
    p.write_text(s+'\ninclude!("sparse_pairs.rs");\n');shutil.copyfile(HERE/'pairs.rs',src/'sparse_pairs.rs')
    p=src/'incremental_raw.rs';s=p.read_text()
    anchor='        let mut left_cols = Vec::with_capacity(right.shared.len());'
    s=change(s,anchor,'''        if self.sparse_pairs.mode>0 && cut>0 && self.sparse_delta_pair(c,steps,cut,raw)?{return Ok(());}
'''+anchor)
    # When there is no delta-only access, the full range and full forward index
    # will be used; sorting both sources by epoch cannot change the result.
    start=s.index('        let left_epochs = self.epoch_order(left);')
    end=s.index('        let radius_bins',start)
    s=s[:start]+'''        let use_epochs = self.sparse_pairs.mode==0 || (self.pair_mode>=2 && cut>0 && self.mode=="learned" && self.radius<=2);
        let left_epochs = if use_epochs{self.epoch_order(left)}else{Default::default()};
        let right_epochs = if use_epochs{self.epoch_order(right)}else{Default::default()};
        let lcut=left_epochs.partition_point(|(e,_)|*e<cut);
        let rcut=right_epochs.partition_point(|(e,_)|*e<cut);
        let right_fresh=right_epochs.len()-rcut;
        if !use_epochs{self.sparse_pairs.stats.unneeded_epoch_sorts+=1;}
'''+s[end:]
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if let Some(v)=req.get("sparse_pair"){ordinary_witness::enable_sparse_pairs(v.clone())?;}
'''+a))
