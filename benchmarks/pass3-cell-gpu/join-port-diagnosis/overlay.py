"""Evaluation-only capture immediately before the native LHS matcher."""
from pathlib import Path
from shutil import copyfile


def install(crate):
    copyfile(Path(__file__).with_name('capture.rs'),crate/'src/join_capture.rs')
    with (crate/'src/lib.rs').open('a') as out:
        out.write('\npub mod join_capture;\n')
    path=crate/'src/runtime.rs'
    source=path.read_text()
    entry='fn matches(&mut self, rid: usize, probe: bool) -> Result<Vec<Binding>> {'
    if source.count(entry)!=1:
        raise ValueError('unexpected matching entry')
    path.write_text(source.replace(entry,entry+'''
        if !probe && self.dirty[rid] {
            crate::join_capture::observe(&self.graph,rid,self.steps.len()+1,self.watermarks[rid])?;
        }'''))
    path=crate/'examples/joint_witness_session.rs'
    source=path.read_text()
    mark='writeln!(out, "{}", report)?;'
    if source.count(mark)!=1:
        raise ValueError('unexpected report')
    path.write_text(source.replace(mark,'report["join_inputs"]=json!(eggfuse_cell_runtime::join_capture::take());\n        '+mark))
