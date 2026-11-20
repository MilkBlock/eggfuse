"""Install the read-sharing plan only on ordered RHS constructor lookup sites."""
import shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
def replace(path,anchor,value):
    s=path.read_text()
    if s.count(anchor)!=1:raise ValueError((path.name,anchor[:75],s.count(anchor)))
    path.write_text(s.replace(anchor,value))
def install(crate):
    src=crate/'src'
    g=src/'graph.rs'
    replace(g,'pub struct Graph {','pub struct Graph {\n    rhs_reads:RhsReads,')
    replace(g,'            joint_allocations: None,','            rhs_reads:Default::default(),\n            joint_allocations: None,')
    replace(g,'let row = self.lookup_canonical(t, &key)?;\n        if let Some(row) = row {',
              'let row = self.rhs_lookup(t,&key,0)?;\n        if let Some(row) = row {')
    replace(g,'if let Some(row) = self.lookup_canonical(t, &key)? {\n            return Ok(row.values.last().unwrap().clone());',
              'if let Some(row) = self.rhs_lookup(t,&key,2)? {\n            return Ok(row.values.last().unwrap().clone());')
    replace(src/'cell_prefix.rs','if let Some(row) = self.lookup_canonical(table, &key)? {',
                 'if let Some(row) = self.rhs_lookup(table, &key,1)? {')
    shutil.copy2(HERE/'reads.rs',src/'ordered_reads.rs')
    with g.open('a') as f:f.write('\ninclude!("ordered_reads.rs");\n')
    p=crate/'examples/joint_witness_session.rs'
    replace(p,'        let initial_cells = runtime.graph.stats.cells_created;', '''        runtime.graph.configure_ordered_reads(u8::try_from(req["rhs_reads"].as_u64().unwrap_or(0))?,req["verify_rhs_reads"]==true)?;
        let initial_cells = runtime.graph.stats.cells_created;''')
    replace(p,'        report["phases_ms"]=','        report["rhs_reads"]=runtime.graph.rhs_read_report();\n        report["phases_ms"]=')
    import importlib.util
    sp=importlib.util.spec_from_file_location("ordered_projection",HERE/"projection.py")
    module=importlib.util.module_from_spec(sp);sp.loader.exec_module(module)
    module.install(crate)
