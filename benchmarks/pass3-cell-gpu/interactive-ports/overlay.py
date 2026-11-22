from pathlib import Path
from shutil import copyfile


def install(crate):
    graph = crate/'src/graph.rs'
    s = graph.read_text()
    old = '            self.stats.constructor_reused += 1;\n\n            let value = row.values.last()'
    if s.count(old) != 1:
        raise ValueError('unexpected constructor return site')
    graph.write_text(s.replace(old,'''            self.stats.constructor_reused += 1;
            if !row.hidden {
                crate::transfer_audit::constructor_return(t, row.witness);
            }

            let value = row.values.last()'''))
    with (crate/'src/transfer_audit.rs').open('a') as f:
        f.write('''
pub(crate) fn constructor_return(table:usize, w:crate::graph::Dependency) {
    event(||serde_json::json!(["returned",table,w,SOURCE.get()]));
}
''')
    copyfile(Path(__file__).with_name('session.rs'),crate/'examples/joint_witness_session.rs')
