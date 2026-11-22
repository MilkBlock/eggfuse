from pathlib import Path
from shutil import copyfile


def install(crate):
    d=Path(__file__).resolve().parent
    copyfile(d/'issuer.rs',crate/'src/live_issuer.rs')
    with (crate/'src/lib.rs').open('a') as stream:
        stream.write('\npub mod live_issuer;\n')
    path=crate/'src/named_only.rs'
    with path.open('a') as stream:
        stream.write('''
impl Packet {
    pub(crate) fn issue(run:usize,rule:usize,parents:Vec<(Dependency,u64)>)->Self{Self{run,rule,parents}}
}
''')
    path=crate/'src/runtime.rs'
    text=path.read_text()
    key='        let rows = self.issued.verify'
    if text.count(key)!=1:
        raise ValueError('unexpected rule entry')
    path.write_text(text.replace(key,'''        crate::live_issuer::submit(&self.graph,self.steps.len()+1,rid,self.watermarks[rid],&mut self.issued)?;
'''+key))
    copyfile(d/'session.rs',crate/'examples/joint_witness_session.rs')
