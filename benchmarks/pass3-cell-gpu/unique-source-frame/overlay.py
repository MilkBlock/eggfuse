import shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent

def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)

def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {','struct Store {frame_edits:FrameEdits,');s=change(s,'let s=Store{','let s=Store{frame_edits:FrameEdits::default(),')
    s=change(s,'"tier":s.tier.stats,','"frame_edits":s.frame_edits,"tier":s.tier.stats,')
    p.write_text(s+'\ninclude!("edit_frame.rs");\n');shutil.copyfile(HERE/'edit.rs',src/'edit_frame.rs')
    p=src/'incremental_raw.rs';s=p.read_text()
    anchor='        let mut prior = old.rows.iter().peekable();'
    s=change(s,anchor,'''        let _retained_reader=self.frame_edits.hold_control.then(||old.clone());
        if self.frame_edits.mode!=0 && Rc::strong_count(old)==1 && Rc::weak_count(old)==0{
            return self.edit_unique_frame(graph,table,generation,&change.changed);
        }
        if self.frame_edits.mode!=0{self.frame_edits.copy_fallback+=1;}
'''+anchor);p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if let Some(v)=req.get("edit_frames"){ordinary_witness::enable_frame_edits(v.clone())?;}
'''+a))
