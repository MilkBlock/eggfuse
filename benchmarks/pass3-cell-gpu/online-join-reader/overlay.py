from pathlib import Path
from shutil import copyfile


def install(crate):
    d=Path(__file__).resolve().parent
    copyfile(d/'issuer.rs',crate/'src/live_issuer.rs')
    with (crate/'src/lib.rs').open('a') as stream:
        stream.write('\npub mod live_issuer;\n')
    path=crate/'src/named_only.rs'
    receiver = path.read_text()
    receiver = receiver.replace("    pub rejected: usize,", "    pub rejected: usize,\n    pub primitive_rejects: BTreeMap<String,u64>,")
    for anchor in ("let Some(value) = g.primitive(op, &values, ty)? else {",
                   "if !g.bind(dest, &value, &mut frame) {"):
        if receiver.count(anchor) != 1:
            raise ValueError("unexpected primitive verification site")
        receiver = receiver.replace(anchor, anchor+"\n                    *self.primitive_rejects.entry(op.clone()).or_default() += 1;")
    path.write_text(receiver)
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
