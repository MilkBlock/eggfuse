"""Build a separate verifier executable whose rule entry accepts only named premises."""
from pathlib import Path
from shutil import copyfile


def install(crate):
    here = Path(__file__).resolve().parent
    runtime = crate / 'src/runtime.rs'
    source = runtime.read_text()
    start = source.index('    fn matches(&mut self, rid: usize, probe: bool)')
    end = source.index('    fn matches_before_ordinary_witness', start)
    source = source[:start] + '''    fn matches(&mut self, rid: usize, probe: bool) -> Result<Vec<Binding>> {
        if probe { return Err("schedule probe lacks named evidence".into()); }
        let rows = self.issued.verify(crate::named_only::Snapshot::new(&self.graph), &self.graph.program.rules[rid], self.steps.len()+1, rid, self.watermarks[rid])?;
        self.pending[rid].clear();
        if self.graph.program.rules[rid].seminaive { self.dirty[rid]=false; }
        self.dedup_bindings(rid,rows)
    }
''' + source[end:]
    for old, new in [('pub struct Executor {','pub struct Executor {\n    pub issued: crate::named_only::Inbox,'),
                     ('steps: vec![],','steps: vec![], issued: Default::default(),')]:
        if source.count(old) != 1:
            raise ValueError(old)
        source = source.replace(old, new)
    runtime.write_text(source)
    copyfile(here/'snapshot.rs', crate/'src/named_snapshot.rs')
    copyfile(here/'receiver.rs', crate/'src/named_only.rs')
    with (crate/'src/lib.rs').open('a') as file:
        file.write('\npub mod named_only;\n')
    copyfile(here/'session.rs', crate/'examples/joint_witness_session.rs')
