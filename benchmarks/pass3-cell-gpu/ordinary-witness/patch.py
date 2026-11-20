"""Install only the independent-width >=2 provider into a private native runtime."""
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent

def swap(s,a,b):
    if s.count(a)!=1:raise ValueError(f'unsupported runtime boundary: {a!r} ({s.count(a)})')
    return s.replace(a,b)

def install(crate):
    src=Path(crate)/'src';shutil.copyfile(HERE/'ordinary.rs',src/'ordinary_witness.rs')
    lib=src/'lib.rs';lib.write_text(lib.read_text()+'\npub mod ordinary_witness;\n')
    p=src/'cell_match.rs';s=p.read_text();s=swap(s,'pub(crate) struct Instance {','pub(crate) struct Instance {\n    pub(crate) ordinary_id:usize,')
    s=swap(s,'            values, known, epoch, parent: None','            ordinary_id:0, values, known, epoch, parent: None')
    p.write_text(s)
    for fname in ('execute_kernel.rs','query_workers.rs','runtime.rs','view_exec.rs'):
        p=src/fname;s=p.read_text();s=s.replace('.push(Binding {','.push(Binding {\n                        ordinary_id:0,');p.write_text(s)
    p=src/'runtime.rs';s=p.read_text();anchor='    fn matches(&mut self, rid: usize, probe: bool) -> Result<Vec<Binding>> {'
    s=swap(s,anchor,anchor+'''
        if !probe && (self.dirty[rid] || !self.graph.program.rules[rid].seminaive)
            && let Some(residual)=crate::ordinary_witness::eligible(rid) {
            let facts=self.stage_spine.alias_query_facts(&self.graph,rid);
            let mut proposed=crate::ordinary_witness::proposals(&self.graph,rid,self.steps.len()+1,self.watermarks[rid],&facts)?;
            if residual {
                // Already-verified neural bindings are placed first. Native stable
                // dedup retains that actual transaction when a residual also found it.
                proposed.extend(self.matches_before_ordinary_witness(rid,probe)?);
            } else {
                if self.graph.program.rules[rid].seminaive{self.dirty[rid]=false;}
                self.pending[rid].clear();
            }
            return self.dedup_bindings(rid,proposed);
        }
        self.matches_before_ordinary_witness(rid,probe)
    }
    fn matches_before_ordinary_witness(&mut self, rid: usize, probe: bool) -> Result<Vec<Binding>> {''')
    anchor='        let stage_cursor = self.stage_spine.begin_step('
    s=swap(s,anchor,'        crate::ordinary_witness::assert_proposal_inputs(b.ordinary_id,&b.values,&self.graph.program.rules[rid].inputs);\n        crate::ordinary_witness::commit(b.ordinary_id,rid);\n'+anchor)
    p.write_text(s)
